"""Accounts, saved profile, application tracker, Telegram linking, stats, AI limit."""
import pytest

from conftest import new_account
from services.auth import hash_password, verify_password


def register(client, email, password="correct horse 42", **extra):
    body = {"email": email, "password": password, "consent": True, **extra}
    return client.post("/api/auth/register", json=body)


# ── auth ────────────────────────────────────────────────────────────────────
def test_password_hash_is_salted_and_verifiable():
    a, b = hash_password("secret pass"), hash_password("secret pass")
    assert a != b and a.startswith("scrypt$")
    assert verify_password("secret pass", a) and not verify_password("wrong pass", a)


def test_register_login_logout(client):
    r = register(client, "Aigerim@Example.com", name="Aigerim", language="kk")
    assert r.status_code == 201
    assert r.json()["user"] == {"id": r.json()["user"]["id"], "email": "aigerim@example.com",
                                "name": "Aigerim", "language": "kk"}

    assert register(client, "aigerim@example.com").status_code == 409  # same email, any case
    assert client.post("/api/auth/login", json={"email": "aigerim@example.com", "password": "nope nope"}).status_code == 401

    token = client.post("/api/auth/login", json={"email": " AIGERIM@example.com ", "password": "correct horse 42"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/me", headers=headers).json()["user"]["language"] == "kk"

    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/me", headers=headers).status_code == 401  # token no longer works


@pytest.mark.parametrize("payload, message", [
    ({"email": "not-an-email", "password": "correct horse 42", "consent": True}, "valid email"),
    ({"email": "a@example.com", "password": "short", "consent": True}, "8 to 128"),
    ({"email": "b@example.com", "password": "correct horse 42", "consent": False}, "personal data"),
])
def test_register_validation(client, payload, message):
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 422 and message in r.json()["detail"]


def test_login_attempts_are_limited(client):
    register(client, "limited@example.com")
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "limited@example.com", "password": "wrong password"})
    r = client.post("/api/auth/login", json={"email": "limited@example.com", "password": "correct horse 42"})
    assert r.status_code == 429


def test_me_needs_login(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer made-up"}).status_code == 401


def test_change_language(client, account):
    headers, _ = account
    assert client.patch("/api/me", headers=headers, json={"language": "en"}).json()["user"]["language"] == "en"
    assert client.patch("/api/me", headers=headers, json={"language": "de"}).status_code == 422


# ── profile + matches ───────────────────────────────────────────────────────
def test_saved_profile_gives_matches_without_upload(client, account, profile_payload):
    headers, _ = account
    assert client.get("/api/me/matches", headers=headers).status_code == 404  # nothing saved yet

    saved = client.put("/api/me/profile", headers=headers, json=profile_payload).json()["profile"]
    assert saved["skills"] == ["Python", "FastAPI", "PostgreSQL", "Docker"]
    assert saved["has_cv_text"] is True and saved["notify"] is True

    me = client.get("/api/me", headers=headers).json()
    assert me["profile"]["level"] == "middle"

    matches = client.get("/api/me/matches", headers=headers).json()["by_role"]["best_matches"]["matches"]
    assert matches[0]["job"]["title"] == "Backend Developer (Python)"


def test_profile_needs_skills(client, account):
    headers, _ = account
    assert client.put("/api/me/profile", headers=headers, json={"skills": []}).status_code == 422


# ── tracker ─────────────────────────────────────────────────────────────────
def test_application_tracker(client, account):
    headers, _ = account
    r = client.post("/api/me/applications", headers=headers, json={"job_id": "j1"})
    assert r.status_code == 201
    app = r.json()["application"]
    assert (app["title"], app["company"], app["status"]) == ("Backend Developer (Python)", "DemoTech", "saved")
    assert app["url"] == "https://hh.kz/vacancy/1"

    again = client.post("/api/me/applications", headers=headers, json={"job_id": "j1"})
    assert again.status_code == 200 and again.json()["application"]["id"] == app["id"]  # no duplicates
    assert client.post("/api/me/applications", headers=headers, json={"job_id": "nope"}).status_code == 404

    upd = client.patch(f"/api/me/applications/{app['id']}", headers=headers,
                       json={"status": "interview", "notes": "Call on Friday"}).json()["application"]
    assert (upd["status"], upd["notes"]) == ("interview", "Call on Friday")
    assert client.patch(f"/api/me/applications/{app['id']}", headers=headers, json={"status": "hired"}).status_code == 422

    listing = client.get("/api/me/applications", headers=headers).json()
    assert [a["id"] for a in listing["applications"]] == [app["id"]]
    assert listing["statuses"] == ["saved", "applied", "interview", "offer", "rejected"]

    assert client.delete(f"/api/me/applications/{app['id']}", headers=headers).status_code == 204
    assert client.get("/api/me/applications", headers=headers).json()["applications"] == []


def test_users_cannot_touch_each_others_applications(client, account):
    headers, _ = account
    other_headers, _ = new_account(client)
    app_id = client.post("/api/me/applications", headers=headers, json={"job_id": "j2"}).json()["application"]["id"]
    assert client.patch(f"/api/me/applications/{app_id}", headers=other_headers, json={"status": "offer"}).status_code == 404
    assert client.delete(f"/api/me/applications/{app_id}", headers=other_headers).status_code == 404
    assert client.get("/api/me/applications", headers=other_headers).json()["applications"] == []


# ── delete account ──────────────────────────────────────────────────────────
def test_delete_account_removes_everything(client, profile_payload):
    headers, user = new_account(client)
    client.put("/api/me/profile", headers=headers, json=profile_payload)
    client.post("/api/me/applications", headers=headers, json={"job_id": "j1"})

    assert client.delete("/api/me", headers=headers).status_code == 204
    assert client.get("/api/me", headers=headers).status_code == 401

    from sqlalchemy import func, select

    from services import app_db
    with app_db.get_engine().connect() as conn:
        for table in (app_db.users, app_db.profiles, app_db.applications, app_db.sessions):
            col = table.c.id if table is app_db.users else table.c.user_id
            assert conn.execute(select(func.count()).select_from(table).where(col == user["id"])).scalar_one() == 0


# ── telegram link ───────────────────────────────────────────────────────────
def test_telegram_link_needs_a_configured_bot(client, account, monkeypatch):
    headers, _ = account
    assert client.post("/api/me/telegram", headers=headers).status_code == 503
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "SeekJobsTestBot")
    body = client.post("/api/me/telegram", headers=headers).json()
    assert body["url"].startswith("https://t.me/SeekJobsTestBot?start=")
    assert client.get("/api/me/telegram", headers=headers).json() == {"linked": False, "bot_username": "SeekJobsTestBot"}


# ── stats + AI limit ────────────────────────────────────────────────────────
def test_stats_are_real_numbers(client):
    s = client.get("/api/stats").json()
    assert s["active_jobs"] == 7
    assert s["median_salary_kzt"] == 725000  # median of 450k, 500k, 700k, 750k, 1.2M, 1.5M
    assert s["sources"] == 4


def test_ai_cv_limit_per_user(client, account, monkeypatch):
    from routers import cv as cv_router
    from services import auth

    calls = []

    async def fake_generate(**kwargs):
        calls.append(kwargs["use_llm"])
        return {"name": "X", "skills": []}

    monkeypatch.setenv("GROQ_API_KEY", "test-key")  # pretend an LLM is configured
    monkeypatch.setattr(cv_router, "generate_tailored_cv", fake_generate)
    monkeypatch.setattr(auth.llm_limiter, "limit", 2)
    headers, _ = account
    body = {"job_id": "j1", "job_title": "Backend Developer"}
    results = [client.post("/api/cv/generate", headers=headers, json=body).json() for _ in range(3)]
    assert calls == [True, True, False]
    assert [r["ai_limit_reached"] for r in results] == [False, False, True]

    # another user has their own allowance
    other, _ = new_account(client)
    assert client.post("/api/cv/generate", headers=other, json=body).json()["ai_limit_reached"] is False
