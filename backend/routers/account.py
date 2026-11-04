"""Accounts, saved profile, application tracker and Telegram linking.

All /api/me/* endpoints need `Authorization: Bearer <token>` from register/login.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from services import app_db
from services.auth import (
    bearer_token, check_credentials_format, create_session, current_user, end_session,
    hash_password, login_limiter, public_user, verify_password,
)
from services.job_matcher import get_job, match_jobs
from services.skills import dedupe_skills

router = APIRouter()
log = logging.getLogger("seekjobs.account")

Language = Literal["ru", "kk", "en"]
Status = Literal["saved", "applied", "interview", "offer", "rejected"]
LINK_CODE_MINUTES = 15


# ── auth ────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = Field("", max_length=120)
    language: Language = "ru"
    consent: bool = False  # agreed to the processing of personal data


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/register", status_code=201)
def register(req: RegisterRequest):
    email = check_credentials_format(req.email, req.password)
    if not req.consent:
        raise HTTPException(422, "Please agree to the processing of your personal data to create an account.")
    now = app_db.utcnow()
    try:
        with app_db.get_engine().begin() as conn:
            user_id = conn.execute(insert(app_db.users).values(
                email=email, password_hash=hash_password(req.password), name=req.name.strip(),
                language=req.language, consent_at=now, created_at=now,
            )).inserted_primary_key[0]
            token = create_session(conn, user_id)
    except IntegrityError:
        raise HTTPException(409, "An account with this email already exists. Please log in.")
    return {"token": token, "user": {"id": user_id, "email": email, "name": req.name.strip(),
                                     "language": req.language}}


@router.post("/auth/login")
def login(req: LoginRequest, request: Request):
    email = req.email.strip().lower()
    ip = request.client.host if request.client else "?"
    if not (login_limiter.allow(f"email:{email}") and login_limiter.allow(f"ip:{ip}")):
        raise HTTPException(429, "Too many login attempts. Please wait 15 minutes and try again.")
    with app_db.get_engine().begin() as conn:
        row = conn.execute(select(app_db.users).where(app_db.users.c.email == email)).mappings().first()
        if not row or not verify_password(req.password, row["password_hash"]):
            raise HTTPException(401, "Wrong email or password.")
        token = create_session(conn, row["id"])
    return {"token": token, "user": public_user(dict(row))}


@router.post("/auth/logout", status_code=204)
def logout(authorization: str | None = Header(None), user: dict = Depends(current_user)):
    with app_db.get_engine().begin() as conn:
        end_session(conn, bearer_token(authorization))
    return Response(status_code=204)


# ── me ──────────────────────────────────────────────────────────────────────
def _profile(conn, user_id: int) -> dict | None:
    row = conn.execute(select(app_db.profiles).where(app_db.profiles.c.user_id == user_id)).mappings().first()
    if not row:
        return None
    p = dict(row)
    return {
        "skills": json.loads(p["skills"] or "[]"),
        "level": p["level"] or "",
        "target_roles": json.loads(p["target_roles"] or "[]"),
        "preferred_salary": p["preferred_salary"],
        "github_url": p["github_url"] or "",
        "linkedin_url": p["linkedin_url"] or "",
        "has_cv_text": bool(p["cv_text"]),
        "notify": bool(p["notify"]),
        "updated_at": p["updated_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _telegram(conn, user_id: int) -> dict:
    row = conn.execute(select(app_db.telegram_links).where(app_db.telegram_links.c.user_id == user_id)).mappings().first()
    return {"linked": bool(row and row["chat_id"]), "bot_username": os.getenv("TELEGRAM_BOT_USERNAME") or ""}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    with app_db.get_engine().connect() as conn:
        return {"user": public_user(user), "profile": _profile(conn, user["id"]), "telegram": _telegram(conn, user["id"])}


class UserUpdate(BaseModel):
    name: str | None = Field(None, max_length=120)
    language: Language | None = None


@router.patch("/me")
def update_me(req: UserUpdate, user: dict = Depends(current_user)):
    values = {k: v for k, v in {"name": req.name, "language": req.language}.items() if v is not None}
    if values:
        with app_db.get_engine().begin() as conn:
            conn.execute(update(app_db.users).where(app_db.users.c.id == user["id"]).values(**values))
    return {"user": public_user({**user, **values})}


@router.delete("/me", status_code=204)
def delete_me(user: dict = Depends(current_user)):
    """Delete the account and everything stored about the user (right to erasure)."""
    uid = user["id"]
    with app_db.get_engine().begin() as conn:
        for table in (app_db.notifications_sent, app_db.telegram_links, app_db.applications,
                      app_db.profiles, app_db.sessions):
            conn.execute(delete(table).where(table.c.user_id == uid))
        conn.execute(delete(app_db.users).where(app_db.users.c.id == uid))
    log.info("Deleted account %s", uid)
    return Response(status_code=204)


# ── saved profile + matches ─────────────────────────────────────────────────
class ProfileRequest(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=200)
    level: str = Field("", max_length=16)
    target_roles: list[str] = Field(default_factory=list, max_length=20)
    preferred_salary: float | None = Field(None, ge=0)
    cv_text: str = Field("", max_length=50_000)
    github_url: str = Field("", max_length=300)
    linkedin_url: str = Field("", max_length=300)
    notify: bool = True


@router.put("/me/profile")
def save_profile(req: ProfileRequest, user: dict = Depends(current_user)):
    skills = dedupe_skills(s.strip() for s in req.skills if s.strip())
    if not skills:
        raise HTTPException(422, "The profile has no skills yet. Analyze a CV first.")
    values = {
        "skills": json.dumps(skills, ensure_ascii=False), "level": req.level,
        "target_roles": json.dumps([r for r in req.target_roles if r], ensure_ascii=False),
        "preferred_salary": req.preferred_salary, "cv_text": req.cv_text or None,
        "github_url": req.github_url, "linkedin_url": req.linkedin_url, "notify": req.notify,
        "updated_at": app_db.utcnow(),
    }
    with app_db.get_engine().begin() as conn:
        exists = conn.execute(select(app_db.profiles.c.user_id).where(app_db.profiles.c.user_id == user["id"])).first()
        if exists:
            conn.execute(update(app_db.profiles).where(app_db.profiles.c.user_id == user["id"]).values(**values))
        else:
            conn.execute(insert(app_db.profiles).values(user_id=user["id"], **values))
        return {"profile": _profile(conn, user["id"])}


@router.get("/me/matches")
async def my_matches(user: dict = Depends(current_user)):
    """Fresh matches for the saved profile — no need to upload the CV again."""
    with app_db.get_engine().connect() as conn:
        profile = _profile(conn, user["id"])
    if not profile:
        raise HTTPException(404, "No saved profile yet. Analyze your CV and save it first.")
    by_role = await match_jobs(user_skills=profile["skills"], target_roles=profile["target_roles"],
                               preferred_salary=profile["preferred_salary"], user_level=profile["level"])
    return {"profile": profile, "by_role": by_role}


# ── application tracker ─────────────────────────────────────────────────────
def _application(row) -> dict:
    a = dict(row)
    for key in ("created_at", "updated_at"):
        a[key] = a[key].strftime("%Y-%m-%dT%H:%M:%SZ")
    a.pop("user_id", None)
    return a


@router.get("/me/applications")
def list_applications(user: dict = Depends(current_user)):
    a = app_db.applications
    with app_db.get_engine().connect() as conn:
        rows = conn.execute(select(a).where(a.c.user_id == user["id"]).order_by(a.c.updated_at.desc())).mappings()
        return {"applications": [_application(r) for r in rows], "statuses": list(app_db.APPLICATION_STATUSES)}


class ApplicationCreate(BaseModel):
    job_id: str = Field(..., max_length=160)
    status: Status = "saved"


@router.post("/me/applications", status_code=201)
def add_application(req: ApplicationCreate, response: Response, user: dict = Depends(current_user)):
    a = app_db.applications
    with app_db.get_engine().begin() as conn:
        existing = conn.execute(select(a).where(a.c.user_id == user["id"], a.c.job_id == req.job_id)).mappings().first()
        if existing:
            response.status_code = 200
            return {"application": _application(existing)}
        job = get_job(req.job_id)
        if not job:
            raise HTTPException(404, "This job is no longer available.")
        now = app_db.utcnow()
        new_id = conn.execute(insert(a).values(
            user_id=user["id"], job_id=req.job_id, title=job["title"], company=job["company"] or None,
            url=job["url"] or None, status=req.status, created_at=now, updated_at=now,
        )).inserted_primary_key[0]
        row = conn.execute(select(a).where(a.c.id == new_id)).mappings().one()
        return {"application": _application(row)}


class ApplicationUpdate(BaseModel):
    status: Status | None = None
    notes: str | None = Field(None, max_length=5000)


@router.patch("/me/applications/{app_id}")
def update_application(app_id: int, req: ApplicationUpdate, user: dict = Depends(current_user)):
    a = app_db.applications
    values = {k: v for k, v in {"status": req.status, "notes": req.notes}.items() if v is not None}
    with app_db.get_engine().begin() as conn:
        result = conn.execute(update(a).where(a.c.id == app_id, a.c.user_id == user["id"])
                              .values(**values, updated_at=app_db.utcnow()))
        if result.rowcount == 0:
            raise HTTPException(404, "Application not found.")
        return {"application": _application(conn.execute(select(a).where(a.c.id == app_id)).mappings().one())}


@router.delete("/me/applications/{app_id}", status_code=204)
def delete_application(app_id: int, user: dict = Depends(current_user)):
    a = app_db.applications
    with app_db.get_engine().begin() as conn:
        if conn.execute(delete(a).where(a.c.id == app_id, a.c.user_id == user["id"])).rowcount == 0:
            raise HTTPException(404, "Application not found.")
    return Response(status_code=204)


# ── Telegram ────────────────────────────────────────────────────────────────
@router.get("/me/telegram")
def telegram_status(user: dict = Depends(current_user)):
    with app_db.get_engine().connect() as conn:
        return _telegram(conn, user["id"])


@router.post("/me/telegram")
def telegram_link(user: dict = Depends(current_user)):
    """One-time link: open it, press Start in Telegram, and the bot connects this account."""
    bot = os.getenv("TELEGRAM_BOT_USERNAME")
    if not bot:
        raise HTTPException(503, "The Telegram bot is not set up on this server yet.")
    code = secrets.token_urlsafe(12)
    expires = app_db.utcnow() + timedelta(minutes=LINK_CODE_MINUTES)
    t = app_db.telegram_links
    with app_db.get_engine().begin() as conn:
        if conn.execute(select(t.c.user_id).where(t.c.user_id == user["id"])).first():
            conn.execute(update(t).where(t.c.user_id == user["id"]).values(link_code=code, code_expires_at=expires))
        else:
            conn.execute(insert(t).values(user_id=user["id"], link_code=code, code_expires_at=expires))
    return {"url": f"https://t.me/{bot}?start={code}", "expires_in_minutes": LINK_CODE_MINUTES}


@router.delete("/me/telegram", status_code=204)
def telegram_unlink(user: dict = Depends(current_user)):
    with app_db.get_engine().begin() as conn:
        conn.execute(delete(app_db.telegram_links).where(app_db.telegram_links.c.user_id == user["id"]))
    return Response(status_code=204)
