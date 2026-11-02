import json
import os
from datetime import timedelta

import pytest

import db


@pytest.fixture
def engine(tmp_path):
    # set TEST_DATABASE_URL (e.g. a Postgres in CI) to run these against another database
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}"
    eng = db.get_engine(url)
    with eng.begin() as conn:  # clean slate for shared databases
        conn.execute(db.jobs.delete())
        conn.execute(db.raw_posts.delete())
    return eng


def raw(source_id, source="telegram:demo"):
    now = db.utcnow()
    return {"source": source, "source_id": str(source_id), "url": f"https://t.me/demo/{source_id}",
            "posted_at": now, "text": f"post {source_id}", "fetched_at": now}


def job(id_, title="Python Developer", days_ago=1):
    now = db.utcnow()
    return {"id": f"telegram:demo/{id_}", "source": "telegram:demo", "source_id": str(id_),
            "source_url": f"https://t.me/demo/{id_}", "title": title, "company": "Demo", "city": "Almaty",
            "category": "software_engineering", "level": "middle", "work_format": "office", "employment": "",
            "salary_from": None, "salary_to": None, "salary_avg": None, "currency": None,
            "experience_min": None, "skills": json.dumps(["Python"]), "description": title,
            "posted_at": now - timedelta(days=days_ago), "first_seen_at": now, "last_seen_at": now,
            "is_active": True, "dedup_key": f"k{id_}", "extractor": "rules-v1"}


def test_raw_posts_are_saved_once(engine):
    assert len(db.save_raw_posts(engine, [raw(1), raw(2)])) == 2
    assert [r["source_id"] for r in db.save_raw_posts(engine, [raw(2), raw(3)])] == ["3"]
    assert len(db.all_raw_posts(engine)) == 3


def test_last_source_id_is_numeric(engine):
    db.save_raw_posts(engine, [raw(9), raw(10), raw(100, source="telegram:other")])
    assert db.last_source_id(engine, "telegram:demo") == 10  # not "9" (text order)
    assert db.last_source_id(engine, "telegram:none") == 0


def test_upsert_updates_but_keeps_first_seen(engine):
    first = job(1)
    db.upsert_jobs(engine, [first])
    later = job(1, title="Senior Python Developer")
    later["first_seen_at"] = first["first_seen_at"] + timedelta(days=3)
    db.upsert_jobs(engine, [later])
    with engine.connect() as conn:
        row = conn.execute(db.jobs.select()).mappings().one()
    assert row["title"] == "Senior Python Developer"
    assert row["first_seen_at"] == first["first_seen_at"]


def test_old_jobs_are_hidden(engine):
    db.upsert_jobs(engine, [job(1, days_ago=2), job(2, days_ago=60)])
    assert db.deactivate_old(engine, max_age_days=45) == 1
    assert db.count_jobs(engine) == 1
    assert db.count_jobs(engine, active_only=False) == 2
