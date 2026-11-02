"""Daily job collection — no LLM or API key needed.

  1. fetch new posts from public Telegram channels (scrapers/telegram_channels.txt)
  2. keep vacancy posts and extract title, company, city, salary, level, skills with rules
  3. save raw posts + jobs to the database (DATABASE_URL, default: data/jobs.db)
  4. hide jobs older than --max-age-days

Usage (from the pipeline/ folder):
  python run_daily.py                          # incremental; the first run looks back --days
  python run_daily.py --days 60                # look further back on the first run
  python run_daily.py --channels devkz_jobs itvacancykz
  python run_daily.py --reextract              # re-run extraction on all saved posts (after improving rules)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()  # same .env as the backend (DATABASE_URL etc.) — must run before db reads settings

import db  # noqa: E402
from extract.rules import EXTRACTOR_VERSION, extract_job, is_vacancy  # noqa: E402
from scrapers.telegram import Channel, fetch_channel, load_channels  # noqa: E402

log = logging.getLogger("pipeline")


def job_row(source: str, source_id: str, url: str, posted_at, text: str,
            default_company: str, max_age_days: int, now) -> dict | None:
    """One jobs-table row from a raw post, or None if it is not a vacancy."""
    if not is_vacancy(text):
        return None
    fields = extract_job(text, default_company)
    if not fields:
        return None
    fields["skills"] = json.dumps(fields["skills"], ensure_ascii=False)
    return {
        "id": f"{source}/{source_id}",
        "source": source,
        "source_id": source_id,
        "source_url": url,
        **fields,
        "posted_at": posted_at,
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": posted_at >= now - timedelta(days=max_age_days),
        "extractor": EXTRACTOR_VERSION,
    }


def collect(engine, channels: list[Channel], days: int, max_pages: int) -> list[dict]:
    """New raw posts from all channels (already saved to raw_posts)."""
    now = db.utcnow()
    new_posts: list[dict] = []
    for ch in channels:
        source = f"telegram:{ch.handle}"
        after_id = db.last_source_id(engine, source)
        posts = fetch_channel(ch.handle, since=now - timedelta(days=days), after_id=after_id, max_pages=max_pages)
        rows = [{"source": source, "source_id": str(p.message_id), "url": p.url, "posted_at": p.posted_at,
                 "text": p.text, "fetched_at": now} for p in posts]
        saved = db.save_raw_posts(engine, rows)
        log.info("%-16s %3d new posts%s", ch.handle, len(saved), "" if after_id else f" (first run, last {days} days)")
        new_posts += saved
    return new_posts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30, help="how far back the first run of a channel looks")
    parser.add_argument("--max-age-days", type=int, default=45, help="hide jobs posted longer ago than this")
    parser.add_argument("--max-pages", type=int, default=50, help="max preview pages per channel (20 posts each)")
    parser.add_argument("--channels", nargs="*", help="only these channels (default: all in telegram_channels.txt)")
    parser.add_argument("--reextract", action="store_true", help="re-run extraction on every saved post")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    channels = load_channels()
    defaults = {f"telegram:{c.handle}": c.company for c in channels}
    if args.channels:  # may also name channels that are not in the file yet
        known = {c.handle: c for c in channels}
        channels = [known.get(h.lstrip("@"), Channel(h.lstrip("@"))) for h in args.channels]

    engine = db.get_engine()
    log.info("Database: %s", engine.url.render_as_string(hide_password=True))

    posts = db.all_raw_posts(engine) if args.reextract else collect(engine, channels, args.days, args.max_pages)

    now = db.utcnow()
    rows = [row for p in posts if (row := job_row(
        p["source"], p["source_id"], p["url"], p["posted_at"], p["text"],
        defaults.get(p["source"], ""), args.max_age_days, now))]
    db.upsert_jobs(engine, rows)
    hidden = db.deactivate_old(engine, args.max_age_days)

    log.info("Posts processed: %d  →  vacancies saved: %d  |  hidden as too old: %d  |  active jobs now: %d",
             len(posts), len(rows), hidden, db.count_jobs(engine))
    return 0


if __name__ == "__main__":
    sys.exit(main())
