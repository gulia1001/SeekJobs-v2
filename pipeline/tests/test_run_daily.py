"""run_daily end to end with a fake Telegram (no network)."""
from datetime import timedelta

from sqlalchemy import select

import db
import run_daily
from scrapers.telegram import Post

VACANCY = """Должность: Python разработчик
Компания: Demo Digital
Город: Астана
Оплата: 400-500 тыс. тг. на руки
Требования: Python, Django, PostgreSQL"""

NOT_VACANCY = "Подписывайтесь на канал, впереди много интересного!"


def fake_fetch(posts_by_channel):
    def fetch(handle, *, since, after_id=0, max_pages=50, **_):
        return [p for p in posts_by_channel.get(handle, []) if p.message_id > after_id]
    return fetch


def post(channel, message_id, text, days_ago=1):
    return Post(channel=channel, message_id=message_id, posted_at=db.utcnow() - timedelta(days=days_ago),
                text=text, url=f"https://t.me/{channel}/{message_id}")


def test_collect_extract_save(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(run_daily, "fetch_channel", fake_fetch({
        "workitkz": [post("workitkz", 1, VACANCY), post("workitkz", 2, NOT_VACANCY)],
        "halyk_jumys": [post("halyk_jumys", 7, "Оператор call-центра | Павлодар\nОбязанности: консультации\n"
                                                "Требования: грамотная речь")],
    }))

    assert run_daily.main(["--channels", "workitkz", "halyk_jumys"]) == 0

    engine = db.get_engine(url)
    with engine.connect() as conn:
        jobs = {r["id"]: r for r in conn.execute(select(db.jobs)).mappings()}
    assert set(jobs) == {"telegram:workitkz/1", "telegram:halyk_jumys/7"}
    python = jobs["telegram:workitkz/1"]
    assert (python["title"], python["company"], python["city"]) == ("Python разработчик", "Demo Digital", "Astana")
    assert (python["salary_from"], python["salary_to"]) == (400_000, 500_000)
    assert python["source_url"] == "https://t.me/workitkz/1"
    assert jobs["telegram:halyk_jumys/7"]["company"] == "Halyk Bank"  # default from telegram_channels.txt
    assert len(db.all_raw_posts(engine)) == 3  # non-vacancies are kept as raw posts too

    # second run: nothing new, nothing duplicated
    assert run_daily.main(["--channels", "workitkz", "halyk_jumys"]) == 0
    assert db.count_jobs(engine) == 2

    # re-extraction rebuilds jobs from saved posts without fetching
    monkeypatch.setattr(run_daily, "fetch_channel", None)
    assert run_daily.main(["--reextract"]) == 0
    assert db.count_jobs(engine) == 2
