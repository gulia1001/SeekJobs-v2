import os
import tempfile
import uuid
from pathlib import Path

# Must be set before the app (and services.data_loader) is imported.
os.environ["DATA_DIR"] = str(Path(__file__).parent / "fixtures" / "data")
os.environ["GROQ_API_KEY"] = ""  # never call the real LLM from tests
os.environ["DATABASE_URL"] = ""  # use the CSV fixture, never a developer's real jobs database
os.environ["APP_DATABASE_URL"] = f"sqlite:///{(Path(tempfile.mkdtemp()) / 'app.db').as_posix()}"  # fresh accounts DB
os.environ["TELEGRAM_BOT_USERNAME"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CV_TEXT = """Aigerim Nurlanova
aigerim@example.com
Backend developer, 2 years of experience with Python, FastAPI, Postgres and Docker.
Built REST APIs at a small Almaty startup. English B2.
"""


@pytest.fixture(scope="session")
def client():
    from main import app

    with TestClient(app) as c:  # runs startup (loads the fixture jobs)
        yield c


@pytest.fixture
def cv_upload():
    return {"cv_file": ("cv.txt", CV_TEXT.encode(), "text/plain")}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from services.auth import llm_limiter, login_limiter

    login_limiter.reset()
    llm_limiter.reset()


def new_account(client, language="ru", **extra):
    """Register a fresh user; returns (headers, user)."""
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": "correct horse 42",
                                                "language": language, "consent": True, **extra})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["user"]


@pytest.fixture
def account(client):
    return new_account(client)


@pytest.fixture
def profile_payload():
    return {"skills": ["Python", "FastAPI", "PostgreSQL", "Docker"], "level": "middle",
            "target_roles": [], "preferred_salary": 600000, "cv_text": CV_TEXT}
