"""The daily ETL steps. Used by both the Airflow DAG (airflow/dags/seekjobs_daily.py)
and the command line (run_daily.py), so there is one implementation.

  extract_channel   E  fetch one channel; save new posts, notice edited and deleted ones
  transform_load    T+L  new/changed posts -> vacancy filter + rules -> jobs table;
                         posts edited to "вакансия закрыта" or deleted -> job hidden
  expire_old_jobs      hide jobs posted more than MAX_AGE_DAYS ago
  quality_check        fail loudly when the data stops looking right

What keeps the data relevant: only vacancies (no CV posts, ads, events), closed and
deleted posts are hidden, old jobs expire, and the last RECHECK_DAYS of every channel
are re-read each day so edits are seen.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select

import db
from extract.rules import EXTRACTOR_VERSION, extract_job, is_vacancy
from scrapers.telegram import Channel, fetch_channel

log = logging.getLogger("pipeline.etl")

FIRST_RUN_DAYS = 30   # how far back a channel's first collection goes
RECHECK_DAYS = 7      # re-read this many recent days every run to notice edits / deletions
MAX_AGE_DAYS = 45     # jobs older than this are hidden

# data quality thresholds
QC_NO_POSTS_DAYS = 3          # error: no new post in any channel for this long
QC_MIN_RECENT_POSTS = 20      # only judge the vacancy rate when there are enough posts
QC_MIN_VACANCY_RATE = 0.20    # error: fewer recent posts recognized as vacancies
QC_STALE_CHANNEL_DAYS = 21    # warning: a channel that stopped posting
QC_MIN_FIELD_COVERAGE = {"city": 0.5, "skills": 0.4}  # warnings


class DataQualityError(RuntimeError):
    pass


def source_of(channel: Channel | str) -> str:
    return f"telegram:{channel.handle if isinstance(channel, Channel) else channel}"


# ── E ───────────────────────────────────────────────────────────────────────
def extract_channel(engine, channel: Channel, *, first_run_days: int = FIRST_RUN_DAYS,
                    recheck_days: int = RECHECK_DAYS, max_pages: int = 50,
                    raise_errors: bool = False, fetch=None) -> dict:
    """Fetch one channel and sync it into raw_posts. Returns counts for the logs / Airflow."""
    fetch = fetch or fetch_channel
    source = source_of(channel)
    now = db.utcnow()
    last_id, last_posted = db.newest_post(engine, source)
    if last_id:
        # everything since the last saved post (covers days the job did not run),
        # and at least the last week so edits and deletions are noticed
        since = min(now - timedelta(days=recheck_days), last_posted or now)
    else:
        since = now - timedelta(days=first_run_days)
    posts = fetch(channel.handle, since=since, after_id=0, max_pages=max_pages, raise_errors=raise_errors)
    rows = [{"source": source, "source_id": str(p.message_id), "url": p.url, "posted_at": p.posted_at,
             "text": p.text, "fetched_at": now} for p in posts]
    stats = db.sync_raw_posts(engine, source, rows, now)
    result = {"channel": channel.handle, "fetched": len(posts), **stats, "first_run": not last_id}
    log.info("%-16s fetched %3d | new %3d | edited %2d | deleted %2d%s", channel.handle, len(posts),
             stats["new"], stats["edited"], stats["deleted"], " (first run)" if not last_id else "")
    return result


# ── T + L ───────────────────────────────────────────────────────────────────
def job_row(post: dict, default_company: str, max_age_days: int, now: datetime) -> dict | None:
    """One jobs-table row from a raw post, or None if it is not (or no longer) a vacancy."""
    if not is_vacancy(post["text"]):
        return None
    fields = extract_job(post["text"], default_company)
    if not fields:
        return None
    fields["skills"] = json.dumps(fields["skills"], ensure_ascii=False)
    active = post["posted_at"] >= now - timedelta(days=max_age_days)
    return {
        "id": f"{post['source']}/{post['source_id']}",
        "source": post["source"],
        "source_id": post["source_id"],
        "source_url": post["url"],
        **fields,
        "posted_at": post["posted_at"],
        "first_seen_at": now,
        "last_seen_at": now,
        "is_active": active,
        "inactive_reason": None if active else "expired",
        "extractor": EXTRACTOR_VERSION,
    }


def transform_load(engine, default_companies: dict[str, str], *, max_age_days: int = MAX_AGE_DAYS) -> dict:
    """Process every new / edited / deleted raw post into the jobs table."""
    posts = db.unprocessed_posts(engine)
    now = db.utcnow()
    upserts, closed, deleted = [], [], []
    for p in posts:
        job_id = f"{p['source']}/{p['source_id']}"
        if p["deleted_at"] is not None:
            deleted.append(job_id)
            continue
        row = job_row(p, default_companies.get(p["source"], ""), max_age_days, now)
        if row:
            upserts.append(row)
        else:
            closed.append(job_id)  # not a vacancy (any more) — e.g. edited to "вакансия закрыта"
    db.upsert_jobs(engine, upserts)
    result = {
        "posts": len(posts),
        "vacancies": len(upserts),
        "closed": db.deactivate_jobs(engine, closed, "closed"),
        "deleted": db.deactivate_jobs(engine, deleted, "deleted"),
    }
    db.mark_processed(engine, [(p["source"], p["source_id"]) for p in posts], now)
    log.info("transform: %(posts)d posts -> %(vacancies)d vacancies | hidden: %(closed)d closed, "
             "%(deleted)d deleted", result)
    return result


def expire_old_jobs(engine, max_age_days: int = MAX_AGE_DAYS) -> int:
    hidden = db.deactivate_old(engine, max_age_days)
    log.info("expire: %d jobs older than %d days hidden", hidden, max_age_days)
    return hidden


# ── data quality ────────────────────────────────────────────────────────────
def quality_check(engine, channels: list[Channel], *, raise_on_error: bool = True) -> dict:
    """Checks that the data still looks right. Errors raise DataQualityError (the Airflow
    task fails and alerts); warnings are only reported."""
    now = db.utcnow()
    rp, jb = db.raw_posts, db.jobs
    errors: list[str] = []
    warnings: list[str] = []
    with engine.connect() as conn:
        active = conn.execute(select(func.count()).select_from(jb).where(jb.c.is_active == True)).scalar_one()  # noqa: E712
        recent_posts = conn.execute(select(func.count()).select_from(rp).where(
            rp.c.posted_at >= now - timedelta(days=QC_NO_POSTS_DAYS))).scalar_one()
        week_posts = conn.execute(select(func.count()).select_from(rp).where(
            rp.c.posted_at >= now - timedelta(days=7), rp.c.deleted_at.is_(None))).scalar_one()
        week_jobs = conn.execute(select(jb.c.city, jb.c.skills).where(
            jb.c.posted_at >= now - timedelta(days=7))).all()
        newest = dict(conn.execute(select(rp.c.source, func.max(rp.c.posted_at)).group_by(rp.c.source)).all())

    if active == 0:
        errors.append("No active jobs in the database.")
    if recent_posts == 0:
        errors.append(f"No new posts from any channel in {QC_NO_POSTS_DAYS} days — "
                      "Telegram's page layout may have changed (scrapers/telegram.py).")
    rate = len(week_jobs) / week_posts if week_posts else None
    if rate is not None and week_posts >= QC_MIN_RECENT_POSTS and rate < QC_MIN_VACANCY_RATE:
        errors.append(f"Only {rate:.0%} of {week_posts} posts this week were recognized as vacancies — "
                      "check extract/rules.py.")
    if week_jobs:
        coverage = {
            "city": sum(bool(c) for c, _ in week_jobs) / len(week_jobs),
            "skills": sum(bool(s and s != "[]") for _, s in week_jobs) / len(week_jobs),
        }
        for field, minimum in QC_MIN_FIELD_COVERAGE.items():
            if coverage[field] < minimum:
                warnings.append(f"Only {coverage[field]:.0%} of this week's jobs have a {field}.")
    for ch in channels:
        last = newest.get(source_of(ch))
        if last is None:
            warnings.append(f"{ch.handle}: no posts collected yet.")
        elif now - last > timedelta(days=QC_STALE_CHANNEL_DAYS):
            warnings.append(f"{ch.handle}: no new posts for {(now - last).days} days — still a good source?")

    report = {"active_jobs": active, "posts_last_3_days": recent_posts, "posts_last_7_days": week_posts,
              "jobs_last_7_days": len(week_jobs), "vacancy_rate_7_days": round(rate, 2) if rate is not None else None,
              "errors": errors, "warnings": warnings}
    for w in warnings:
        log.warning("quality: %s", w)
    if errors:
        for e in errors:
            log.error("quality: %s", e)
        if raise_on_error:
            raise DataQualityError("; ".join(errors))
    else:
        log.info("quality: OK — %d active jobs, %d posts this week, vacancy rate %s",
                 active, week_posts, report["vacancy_rate_7_days"])
    return report
