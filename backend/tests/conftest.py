import os
from pathlib import Path

# Must be set before the app (and services.data_loader) is imported.
os.environ["DATA_DIR"] = str(Path(__file__).parent / "fixtures" / "data")
os.environ["GROQ_API_KEY"] = ""  # never call the real LLM from tests
os.environ["APIFY_TOKEN"] = ""

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
