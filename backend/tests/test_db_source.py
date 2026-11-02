"""The backend reads the jobs table that pipeline/db.py writes — test that contract end to end."""
import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

from services import data_loader

_spec = importlib.util.spec_from_file_location(
    "pipeline_db", Path(__file__).resolve().parents[2] / "pipeline" / "db.py")
pipeline_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pipeline_db)


def job(id_, title, *, days_ago=1, active=True, dedup=None, skills=("Python",), salary=None, url=None):
    now = pipeline_db.utcnow()
    return {
        "id": f"telegram:test/{id_}", "source": "telegram:test", "source_id": str(id_),
        "source_url": url or f"https://t.me/test/{id_}", "title": title, "company": "DemoCo",
        "city": "Almaty", "category": "software_engineering", "level": "middle", "work_format": "office",
        "employment": "full_time", "salary_from": salary, "salary_to": salary, "salary_avg": salary,
        "currency": "KZT" if salary else None, "experience_min": None,
        "skills": json.dumps(list(skills)), "description": f"{title} vacancy",
        "posted_at": now - timedelta(days=days_ago), "first_seen_at": now, "last_seen_at": now,
        "is_active": active, "dedup_key": dedup or f"k{id_}", "extractor": "rules-v1",
    }


@pytest.fixture
def jobs_db(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}"
    engine = pipeline_db.get_engine(url)
    pipeline_db.upsert_jobs(engine, [
        job(1, "Python Developer", days_ago=1, skills=("Python", "FastAPI", "PostgreSQL"), salary=700000),
        job(2, "Old Python Developer", days_ago=90),                      # too old
        job(3, "Closed Python Developer", active=False),                  # inactive
        job(4, "Go Developer (repost)", days_ago=5, dedup="same", skills=("Go",)),
        job(5, "Go Developer", days_ago=2, dedup="same", skills=("Go", "Docker")),  # newer copy wins
    ])
    monkeypatch.setattr(data_loader, "DATABASE_URL", url)
    data_loader._state["df"] = None  # force a reload from the database
    yield engine
    data_loader._state["df"] = None  # next test reloads the CSV fixture


def test_only_fresh_active_unique_jobs(jobs_db):
    titles = list(data_loader.load_jobs()["title_final"])
    assert titles == ["Python Developer", "Go Developer"]  # newest first, one per dedup_key


def test_jobs_api_has_post_date_and_link(client, jobs_db):
    jobs = client.get("/api/jobs").json()["jobs"]
    python = next(j for j in jobs if j["title"] == "Python Developer")
    assert python["posted_at"].endswith("Z")
    assert python["url"] == "https://t.me/test/1"
    assert python["salary_display"] == "700 000 KZT"


def test_matching_uses_database_jobs(client, jobs_db, cv_upload):
    body = client.post("/api/analyze", files=cv_upload).json()
    top = body["by_role"]["best_matches"]["matches"][0]
    assert top["job"]["title"] == "Python Developer"
    assert top["job"]["posted_at"]
    assert top["score"] == 100  # Python, FastAPI, Postgres are all in the CV


def test_empty_database_falls_back_to_csv(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    pipeline_db.get_engine(url)  # tables exist but are empty
    monkeypatch.setattr(data_loader, "DATABASE_URL", url)
    data_loader._state["df"] = None
    try:
        assert len(data_loader.load_jobs()) == 7  # the CSV fixture
    finally:
        data_loader._state["df"] = None
