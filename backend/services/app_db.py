"""Database for the app's own data: accounts, saved profiles, tracked applications, Telegram links.

APP_DATABASE_URL, else DATABASE_URL (Docker: the same Postgres as the jobs, separate tables),
else a local SQLite file backend/data/app.db. Personal data lives here — see /privacy.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table, Text,
    UniqueConstraint, create_engine, inspect, text,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("name", String(120)),
    Column("language", String(2), nullable=False, default="ru"),   # ru | kk | en
    Column("consent_at", DateTime, nullable=False),                 # personal-data consent
    Column("created_at", DateTime, nullable=False),
)

sessions = Table(
    "sessions", metadata,
    Column("token_hash", String(64), primary_key=True),             # sha256 of the bearer token
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("created_at", DateTime, nullable=False),
    Column("expires_at", DateTime, nullable=False),
)

profiles = Table(
    "profiles", metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("skills", Text, nullable=False, default="[]"),            # JSON list
    Column("level", String(16)),
    Column("target_roles", Text, nullable=False, default="[]"),      # JSON list
    Column("preferred_salary", Float),
    Column("cv_text", Text),
    Column("github_url", Text),
    Column("linkedin_url", Text),
    Column("notify", Boolean, nullable=False, default=True),         # daily Telegram digest
    Column("updated_at", DateTime, nullable=False),
)

applications = Table(
    "applications", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("job_id", String(160), nullable=False),
    # snapshot: jobs expire from the jobs table, the tracker keeps what the user saw
    Column("title", Text, nullable=False),
    Column("company", Text),
    Column("url", Text),
    Column("status", String(16), nullable=False, default="saved"),
    Column("notes", Text),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),
)

telegram_links = Table(
    "telegram_links", metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("chat_id", String(32), unique=True),                       # NULL until the bot confirms
    Column("link_code", String(32), unique=True),                     # one-time code for /start <code>
    Column("code_expires_at", DateTime),
    Column("linked_at", DateTime),
)

notifications_sent = Table(
    "notifications_sent", metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("job_id", String(160), primary_key=True),
    Column("sent_at", DateTime, nullable=False),
)

APPLICATION_STATUSES = ("saved", "applied", "interview", "offer", "rejected")
LANGUAGES = ("ru", "kk", "en")

_BACKEND = Path(__file__).resolve().parents[1]
_engine: Engine | None = None
_engine_url: str | None = None
_SCHEMA_LOCK_ID = 4_206_918


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def app_database_url() -> str:
    url = os.getenv("APP_DATABASE_URL") or os.getenv("DATABASE_URL")
    if url:
        return url
    (_BACKEND / "data").mkdir(exist_ok=True)
    return f"sqlite:///{(_BACKEND / 'data' / 'app.db').as_posix()}"


def get_engine() -> Engine:
    """One engine per process (re-created if the URL changes, e.g. in tests)."""
    global _engine, _engine_url
    url = app_database_url()
    if _engine is None or url != _engine_url:
        engine = create_engine(url, pool_pre_ping=True)
        if engine.dialect.name == "sqlite":
            from sqlalchemy import event

            @event.listens_for(engine, "connect")
            def _sqlite_foreign_keys(dbapi_conn, _):  # ON DELETE CASCADE needs this in SQLite
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

        ensure_schema(engine)
        _engine, _engine_url = engine, url
    return _engine


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _SCHEMA_LOCK_ID})
        metadata.create_all(conn)
        insp = inspect(conn)
        for table in metadata.sorted_tables:  # add columns that newer code defines
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} "
                                      f"{col.type.compile(dialect=conn.dialect)}"))
