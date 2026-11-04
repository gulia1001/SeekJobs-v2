"""Daily job collection from the command line — the same steps the Airflow DAG runs.
No LLM or API key needed.

Usage (from the pipeline/ folder):
  python run_daily.py                    # all steps: extract -> transform -> expire -> check
  python run_daily.py extract            # only collect posts (all channels, or --channels …)
  python run_daily.py transform          # only turn new/edited/deleted posts into jobs
  python run_daily.py expire             # only hide old jobs
  python run_daily.py check              # only run the data quality checks
  python run_daily.py --reextract        # re-run extraction on all saved posts (after improving rules)
  python run_daily.py --channels devkz_jobs itvacancykz --days 60

Database: DATABASE_URL (from the environment or ../.env), default data/jobs.db.
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()  # same .env as the backend (DATABASE_URL etc.) — must run before db reads settings

import db  # noqa: E402
import etl  # noqa: E402
from scrapers.telegram import Channel, load_channels  # noqa: E402

log = logging.getLogger("pipeline")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", nargs="?", default="all", choices=["all", "extract", "transform", "expire", "check"])
    parser.add_argument("--days", type=int, default=etl.FIRST_RUN_DAYS, help="how far back a channel's first run looks")
    parser.add_argument("--max-age-days", type=int, default=etl.MAX_AGE_DAYS, help="hide jobs posted longer ago")
    parser.add_argument("--max-pages", type=int, default=50, help="max preview pages per channel (20 posts each)")
    parser.add_argument("--channels", nargs="*", help="only these channels (default: all in telegram_channels.txt)")
    parser.add_argument("--reextract", action="store_true", help="re-run extraction on every saved post")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    all_channels = load_channels()
    companies = {etl.source_of(c): c.company for c in all_channels}
    channels = all_channels
    if args.channels:  # may also name channels that are not in the file yet
        known = {c.handle: c for c in all_channels}
        channels = [known.get(h.lstrip("@"), Channel(h.lstrip("@"))) for h in args.channels]

    engine = db.get_engine()
    log.info("Database: %s", engine.url.render_as_string(hide_password=True))
    run = {s: args.step in ("all", s) for s in ("extract", "transform", "expire", "check")}

    if args.reextract:
        db.reset_processed(engine)
        run["extract"], run["transform"] = False, True
    if run["extract"]:
        for ch in channels:
            etl.extract_channel(engine, ch, first_run_days=args.days, max_pages=args.max_pages)
    if run["transform"]:
        etl.transform_load(engine, companies, max_age_days=args.max_age_days)
    if run["expire"]:
        etl.expire_old_jobs(engine, args.max_age_days)
    if run["check"]:
        report = etl.quality_check(engine, all_channels, raise_on_error=False)
        if report["errors"]:
            return 1
    log.info("Active jobs now: %d", db.count_jobs(engine))
    return 0


if __name__ == "__main__":
    sys.exit(main())
