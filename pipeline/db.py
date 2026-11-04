"""Jobs database: SQLite by default (one file, no setup), Postgres in production.

Tables
  raw_posts  every collected post, unchanged — lets us re-extract later with better rules or an LLM
  jobs       structured vacancies; the backend reads this table (backend/services/data_loader.py)

Set DATABASE_URL to use another database, e.g.
  postgresql+psycopg://seekjobs:secret@localhost:5432/seekjobs
Default: sqlite:///<pipeline>/data/jobs.db
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import (
    Boolean, Column, DateTime, Float, MetaData, String, Table, Text, create_engine, func, inspect,
    select, text, tuple_, update,
)
from sqlalchemy.engine import Engine

DATA_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent / "data")

metadata = MetaData()

raw_posts = Table(
    "raw_posts", metadata,
    Column("source", String(64), primary_key=True),      # e.g. "telegram:devkz_jobs"
    Column("source_id", String(64), primary_key=True),   # message id in that source
    Column("url", Text),
    Column("posted_at", DateTime, index=True),            # UTC
    Column("text", Text, nullable=False),
    Column("fetched_at", DateTime, nullable=False),
    Column("processed_at", DateTime, index=True),         # NULL = new/edited/deleted, transform it next
    Column("deleted_at", DateTime),                       # post disappeared from the channel
)

jobs = Table(
    "jobs", metadata,
    Column("id", String(160), primary_key=True),          # "<source>/<source_id>"
    Column("source", String(64), nullable=False, index=True),
    Column("source_id", String(64), nullable=False),
    Column("source_url", Text),
    Column("title", Text, nullable=False),
    Column("company", Text),
    Column("city", String(64)),
    Column("category", String(32), index=True),
    Column("level", String(16)),
    Column("work_format", String(16)),
    Column("employment", String(16)),
    Column("salary_from", Float),
    Column("salary_to", Float),
    Column("salary_avg", Float),
    Column("currency", String(8)),
    Column("experience_min", Float),
    Column("skills", Text),                               # JSON list of skill names
    Column("description", Text),
    Column("posted_at", DateTime, index=True),            # UTC
    Column("first_seen_at", DateTime),
    Column("last_seen_at", DateTime),
    Column("is_active", Boolean, nullable=False, default=True, index=True),
    Column("inactive_reason", String(16)),                # "expired", "closed" or "deleted"
    Column("dedup_key", String(64), index=True),          # same job posted in several channels
    Column("extractor", String(32)),                      # "rules-v1", later e.g. "llm-v1"
)

_CHUNK = 200  # rows per INSERT (keeps SQLite under its parameter limit)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(DATA_DIR / 'jobs.db').as_posix()}"


def get_engine(url: str | None = None) -> Engine:
    engine = create_engine(url or database_url(), pool_pre_ping=True)
    ensure_schema(engine)
    return engine


_SCHEMA_LOCK_ID = 4_206_917  # any constant: Postgres advisory lock for schema changes


def ensure_schema(engine: Engine) -> None:
    """Create missing tables and columns. Safe when several tasks start at once (Airflow runs
    the channel tasks in parallel): on Postgres they take turns via an advisory lock."""
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SCHEMA_LOCK_ID})
        metadata.create_all(conn)
        _add_missing_columns(conn)


def _add_missing_columns(conn) -> None:
    """Tiny migration: add columns that newer code defines to tables created by older code."""
    insp = inspect(conn)
    for table in metadata.sorted_tables:
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(dialect=conn.dialect)
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}"))


def _insert(engine: Engine, table: Table):
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(table)


def _chunks(rows: list[dict]) -> Iterable[list[dict]]:
    for i in range(0, len(rows), _CHUNK):
        yield rows[i:i + _CHUNK]


# ── raw posts ───────────────────────────────────────────────────────────────
def last_source_id(engine: Engine, source: str) -> int:
    """Highest numeric message id already saved for a source (0 if none)."""
    return newest_post(engine, source)[0]


def newest_post(engine: Engine, source: str) -> tuple[int, datetime | None]:
    """(highest numeric message id, its posted_at) for a source; (0, None) if none."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(raw_posts.c.source_id, raw_posts.c.posted_at).where(raw_posts.c.source == source)
        ).all()
    numeric = [(int(i), p) for i, p in rows if str(i).isdigit()]
    return max(numeric, default=(0, None))


def save_raw_posts(engine: Engine, rows: list[dict]) -> list[dict]:
    """Insert posts that are not saved yet; returns the new ones."""
    if not rows:
        return []
    new: list[dict] = []
    with engine.begin() as conn:
        for source in {r["source"] for r in rows}:
            ids = [r["source_id"] for r in rows if r["source"] == source]
            existing = set(conn.execute(
                select(raw_posts.c.source_id).where(raw_posts.c.source == source, raw_posts.c.source_id.in_(ids))
            ).scalars())
            new += [r for r in rows if r["source"] == source and r["source_id"] not in existing]
        for chunk in _chunks(new):
            conn.execute(raw_posts.insert(), chunk)
    return new


def sync_raw_posts(engine: Engine, source: str, rows: list[dict], now: datetime) -> dict:
    """Save a fresh fetch of one channel and compare it with what is stored:
    new posts are inserted, edited posts updated, and posts that vanished inside the
    fetched id range are marked deleted. Changed posts get processed_at = NULL so the
    transform step looks at them again."""
    fetched = {r["source_id"]: r for r in rows}
    if not fetched:
        return {"new": 0, "edited": 0, "deleted": 0}
    lo, hi = min(int(i) for i in fetched), max(int(i) for i in fetched)
    with engine.connect() as conn:
        stored = {
            r.source_id: r for r in conn.execute(
                select(raw_posts.c.source_id, raw_posts.c.text, raw_posts.c.deleted_at)
                .where(raw_posts.c.source == source)
            )
            if str(r.source_id).isdigit() and lo <= int(r.source_id) <= hi
        }
    new = [r for sid, r in fetched.items() if sid not in stored]
    edited = [r for sid, r in fetched.items()
              if sid in stored and (stored[sid].text != r["text"] or stored[sid].deleted_at is not None)]
    deleted = [sid for sid, r in stored.items() if sid not in fetched and r.deleted_at is None]

    with engine.begin() as conn:
        for chunk in _chunks(new):
            conn.execute(raw_posts.insert(), [{**r, "processed_at": None, "deleted_at": None} for r in chunk])
        for r in edited:
            conn.execute(update(raw_posts)
                         .where(raw_posts.c.source == source, raw_posts.c.source_id == r["source_id"])
                         .values(text=r["text"], fetched_at=now, processed_at=None, deleted_at=None))
        if deleted:
            conn.execute(update(raw_posts)
                         .where(raw_posts.c.source == source, raw_posts.c.source_id.in_(deleted))
                         .values(deleted_at=now, processed_at=None))
    return {"new": len(new), "edited": len(edited), "deleted": len(deleted)}


def unprocessed_posts(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(raw_posts).where(raw_posts.c.processed_at.is_(None))).mappings()]


def mark_processed(engine: Engine, keys: list[tuple[str, str]], now: datetime) -> None:
    with engine.begin() as conn:
        for i in range(0, len(keys), _CHUNK):
            chunk = keys[i:i + _CHUNK]
            conn.execute(update(raw_posts)
                         .where(tuple_(raw_posts.c.source, raw_posts.c.source_id).in_(chunk))
                         .values(processed_at=now))


def reset_processed(engine: Engine) -> None:
    """Make the next transform step re-read every saved post (after improving the rules)."""
    with engine.begin() as conn:
        conn.execute(update(raw_posts).values(processed_at=None))


def all_raw_posts(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(raw_posts)).mappings()]


# ── jobs ────────────────────────────────────────────────────────────────────
def upsert_jobs(engine: Engine, rows: list[dict]) -> int:
    """Insert new jobs, update existing ones (keeps their first_seen_at)."""
    if not rows:
        return 0
    keep = {"id", "first_seen_at"}
    with engine.begin() as conn:
        for chunk in _chunks(rows):
            stmt = _insert(engine, jobs).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[jobs.c.id],
                set_={c.name: stmt.excluded[c.name] for c in jobs.columns if c.name not in keep},
            )
            conn.execute(stmt)
    return len(rows)


def deactivate_jobs(engine: Engine, ids: list[str], reason: str) -> int:
    """Hide these jobs (if active). Returns how many were hidden."""
    if not ids:
        return 0
    hidden = 0
    with engine.begin() as conn:
        for i in range(0, len(ids), _CHUNK):
            result = conn.execute(
                update(jobs).where(jobs.c.id.in_(ids[i:i + _CHUNK]), jobs.c.is_active == True)  # noqa: E712
                .values(is_active=False, inactive_reason=reason)
            )
            hidden += result.rowcount or 0
    return hidden


def deactivate_old(engine: Engine, max_age_days: int) -> int:
    """Hide jobs posted more than max_age_days ago. Returns how many were hidden."""
    cutoff = utcnow() - timedelta(days=max_age_days)
    with engine.begin() as conn:
        result = conn.execute(
            update(jobs).where(jobs.c.is_active == True, jobs.c.posted_at < cutoff)  # noqa: E712
            .values(is_active=False, inactive_reason="expired")
        )
    return result.rowcount or 0


def count_jobs(engine: Engine, active_only: bool = True) -> int:
    query = select(func.count()).select_from(jobs)
    if active_only:
        query = query.where(jobs.c.is_active == True)  # noqa: E712
    with engine.connect() as conn:
        return conn.execute(query).scalar_one()
