"""The ETL steps end to end with a fake Telegram (no network)."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, inspect, select, text

import db
import etl
import run_daily
from scrapers.telegram import Channel, Post

VACANCY = """Должность: Python разработчик
Компания: Demo Digital
Город: Астана
Оплата: 400-500 тыс. тг. на руки
Требования: Python, Django, PostgreSQL"""

GO_VACANCY = """Должность: Go разработчик
Компания: Demo Go
Город: Алматы
Требования: Go, Docker, Kubernetes. Опыт от 3 лет"""

NOT_VACANCY = "Подписывайтесь на канал, впереди много интересного!"


class FakeTelegram:
    """Plays a channel: returns the posts it currently holds (respecting `since`)."""

    def __init__(self, posts_by_channel):
        self.posts = posts_by_channel
        self.calls = []

    def __call__(self, handle, *, since, after_id=0, max_pages=50, **_):
        self.calls.append((handle, since))
        return [p for p in self.posts.get(handle, []) if p.message_id > after_id and p.posted_at >= since]


def post(channel, message_id, text, days_ago=1.0):
    return Post(channel=channel, message_id=message_id, posted_at=db.utcnow() - timedelta(days=days_ago),
                text=text, url=f"https://t.me/{channel}/{message_id}")


@pytest.fixture
def engine(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    return db.get_engine(url)


def jobs_by_id(engine):
    with engine.connect() as conn:
        return {r["id"]: r for r in conn.execute(select(db.jobs)).mappings()}


def test_full_run_from_command_line(engine, monkeypatch):
    fake = FakeTelegram({
        "workitkz": [post("workitkz", 1, VACANCY), post("workitkz", 2, NOT_VACANCY)],
        "halyk_jumys": [post("halyk_jumys", 7, "Оператор call-центра | Павлодар\nОбязанности: консультации\n"
                                                "Требования: грамотная речь")],
    })
    monkeypatch.setattr(etl, "fetch_channel", fake)

    assert run_daily.main(["--channels", "workitkz", "halyk_jumys"]) == 0

    jobs = jobs_by_id(engine)
    assert set(jobs) == {"telegram:workitkz/1", "telegram:halyk_jumys/7"}
    python = jobs["telegram:workitkz/1"]
    assert (python["title"], python["company"], python["city"]) == ("Python разработчик", "Demo Digital", "Astana")
    assert (python["salary_from"], python["salary_to"]) == (400_000, 500_000)
    assert python["source_url"] == "https://t.me/workitkz/1"
    assert jobs["telegram:halyk_jumys/7"]["company"] == "Halyk Bank"  # default from telegram_channels.txt
    assert len(db.all_raw_posts(engine)) == 3  # non-vacancies are kept as raw posts too
    assert db.unprocessed_posts(engine) == []

    # second run: nothing new, nothing duplicated
    assert run_daily.main(["--channels", "workitkz", "halyk_jumys"]) == 0
    assert db.count_jobs(engine) == 2

    # re-extraction rebuilds jobs from saved posts without fetching
    monkeypatch.setattr(etl, "fetch_channel", None)
    assert run_daily.main(["--reextract"]) == 0
    assert db.count_jobs(engine) == 2


def test_closed_and_deleted_posts_hide_their_jobs(engine):
    ch = Channel("workitkz")
    fake = FakeTelegram({"workitkz": [post("workitkz", 1, VACANCY), post("workitkz", 2, GO_VACANCY),
                                      post("workitkz", 3, VACANCY.replace("Python", "Java"))]})
    etl.extract_channel(engine, ch, fetch=fake)
    assert etl.transform_load(engine, {})["vacancies"] == 3

    # next day: post 1 was edited to say the vacancy is closed, post 2 was deleted
    fake.posts["workitkz"] = [post("workitkz", 1, "#вакансия закрыта\n" + VACANCY),
                              post("workitkz", 3, VACANCY.replace("Python", "Java"))]
    stats = etl.extract_channel(engine, ch, fetch=fake)
    assert (stats["new"], stats["edited"], stats["deleted"]) == (0, 1, 1)
    assert etl.transform_load(engine, {}) == {"posts": 2, "vacancies": 0, "closed": 1, "deleted": 1}

    jobs = jobs_by_id(engine)
    assert (jobs["telegram:workitkz/1"]["is_active"], jobs["telegram:workitkz/1"]["inactive_reason"]) == (False, "closed")
    assert (jobs["telegram:workitkz/2"]["is_active"], jobs["telegram:workitkz/2"]["inactive_reason"]) == (False, "deleted")
    assert jobs["telegram:workitkz/3"]["is_active"] is True


def test_recheck_window_and_catch_up_after_missed_days(engine):
    ch = Channel("devkz_jobs")
    fake = FakeTelegram({"devkz_jobs": [post("devkz_jobs", 10, VACANCY, days_ago=20)]})
    etl.extract_channel(engine, ch, fetch=fake)
    first_since = fake.calls[-1][1]
    assert db.utcnow() - first_since > timedelta(days=29)  # first run looks back 30 days

    etl.extract_channel(engine, ch, fetch=fake)
    since = fake.calls[-1][1]
    # last saved post is 20 days old (job did not run for a while) -> go back to it, not only 7 days
    assert timedelta(days=19) < db.utcnow() - since < timedelta(days=21)


def test_old_jobs_expire(engine):
    fake = FakeTelegram({"workitkz": [post("workitkz", 1, VACANCY, days_ago=60), post("workitkz", 2, GO_VACANCY)]})
    etl.extract_channel(engine, Channel("workitkz"), fetch=fake, first_run_days=90)
    etl.transform_load(engine, {})
    jobs = jobs_by_id(engine)
    assert (jobs["telegram:workitkz/1"]["is_active"], jobs["telegram:workitkz/1"]["inactive_reason"]) == (False, "expired")
    assert db.count_jobs(engine) == 1


def test_quality_check_passes_on_healthy_data(engine):
    fake = FakeTelegram({"workitkz": [post("workitkz", 1, VACANCY), post("workitkz", 2, GO_VACANCY)]})
    etl.extract_channel(engine, Channel("workitkz"), fetch=fake)
    etl.transform_load(engine, {})
    report = etl.quality_check(engine, [Channel("workitkz"), Channel("silent_channel")])
    assert report["errors"] == []
    assert report["active_jobs"] == 2
    assert any("silent_channel" in w for w in report["warnings"])


def test_quality_check_fails_when_nothing_new(engine):
    fake = FakeTelegram({"workitkz": [post("workitkz", 1, VACANCY, days_ago=10)]})
    etl.extract_channel(engine, Channel("workitkz"), fetch=fake)
    etl.transform_load(engine, {})
    with pytest.raises(etl.DataQualityError, match="No new posts"):
        etl.quality_check(engine, [Channel("workitkz")])


def test_quality_check_fails_when_rules_stop_recognizing_vacancies(engine):
    posts = [post("workitkz", i, NOT_VACANCY + f" #{i}") for i in range(1, 25)] + [post("workitkz", 30, VACANCY)]
    etl.extract_channel(engine, Channel("workitkz"), fetch=FakeTelegram({"workitkz": posts}))
    etl.transform_load(engine, {})
    with pytest.raises(etl.DataQualityError, match="recognized as vacancies"):
        etl.quality_check(engine, [Channel("workitkz")])
    assert run_daily.main(["check"]) == 1  # the command line reports it with exit code 1


def test_old_database_gets_new_columns(tmp_path):
    """jobs.db files created before this version gain the new columns automatically."""
    url = f"sqlite:///{(tmp_path / 'old.db').as_posix()}"
    with create_engine(url).begin() as conn:
        conn.execute(text("CREATE TABLE raw_posts (source VARCHAR(64), source_id VARCHAR(64), url TEXT, "
                          "posted_at DATETIME, text TEXT NOT NULL, fetched_at DATETIME NOT NULL, "
                          "PRIMARY KEY (source, source_id))"))
        conn.execute(text("INSERT INTO raw_posts VALUES ('telegram:x', '1', 'u', '2026-11-01 10:00:00', 't', "
                          "'2026-11-01 10:00:00')"))
    engine = db.get_engine(url)
    columns = {c["name"] for c in inspect(engine).get_columns("raw_posts")}
    assert {"processed_at", "deleted_at"} <= columns
    assert len(db.unprocessed_posts(engine)) == 1  # old rows are picked up by the next transform
