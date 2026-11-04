"""Accounts: password hashing, login sessions, the current-user dependency, and rate limits."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import Header, HTTPException
from sqlalchemy import insert, select

from services import app_db

SESSION_DAYS = 30
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


# ── passwords ───────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """scrypt with a random salt (Python standard library, no extra dependency)."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(digest.hex(), digest_hex)


def check_credentials_format(email: str, password: str) -> str:
    """Normalized email, or HTTP 422 with a message the user can act on."""
    email = email.strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise HTTPException(422, "Please enter a valid email address.")
    if not 8 <= len(password) <= 128:
        raise HTTPException(422, "The password must be 8 to 128 characters long.")
    return email


# ── sessions ────────────────────────────────────────────────────────────────
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: int) -> str:
    """New login token. Only its hash is stored, so a database leak exposes no usable tokens."""
    token = secrets.token_urlsafe(32)
    now = app_db.utcnow()
    conn.execute(insert(app_db.sessions).values(
        token_hash=_token_hash(token), user_id=user_id, created_at=now,
        expires_at=now + timedelta(days=SESSION_DAYS)))
    return token


def end_session(conn, token: str) -> None:
    conn.execute(app_db.sessions.delete().where(app_db.sessions.c.token_hash == _token_hash(token)))


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def current_user(authorization: str | None = Header(None)) -> dict:
    """FastAPI dependency: the logged-in user, or HTTP 401."""
    token = bearer_token(authorization)
    if not token:
        raise HTTPException(401, "Please log in.")
    u, s = app_db.users, app_db.sessions
    with app_db.get_engine().connect() as conn:
        row = conn.execute(
            select(u).join(s, s.c.user_id == u.c.id)
            .where(s.c.token_hash == _token_hash(token), s.c.expires_at > app_db.utcnow())
        ).mappings().first()
    if not row:
        raise HTTPException(401, "Your session has expired. Please log in again.")
    return dict(row)


def optional_user(authorization: str | None = Header(None)) -> dict | None:
    """The logged-in user if a valid token was sent, else None (for endpoints that work for both)."""
    if not bearer_token(authorization):
        return None
    try:
        return current_user(authorization)
    except HTTPException:
        return None


def public_user(row: dict) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row.get("name") or "",
            "language": row.get("language") or "ru"}


# ── rate limits (per process — enough for one server) ───────────────────────
class RateLimiter:
    """At most `limit` hits per `window` seconds for each key."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = RateLimiter(limit=10, window=15 * 60)          # per email and per IP
llm_limiter = RateLimiter(limit=int(os.getenv("LLM_DAILY_LIMIT") or 20), window=24 * 3600)
