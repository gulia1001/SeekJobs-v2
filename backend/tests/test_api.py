def all_matches(body):
    return [m for group in body["by_role"].values() for m in group["matches"]]


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_jobs_list_hides_duplicates(client):
    body = client.get("/api/jobs", params={"limit": 50}).json()
    assert body["total"] == 7  # 8 fixture rows, 1 flagged as duplicate
    assert all("duplicate" not in j["title"].lower() for j in body["jobs"])


def test_cv_only_analysis_works(client, cv_upload):
    """Regression: CV without GitHub/LinkedIn used to crash with HTTP 500."""
    r = client.post("/api/analyze", files=cv_upload)
    assert r.status_code == 200
    profile = r.json()["profile"]
    assert "Aigerim" in profile["cv_text"]
    assert {"Python", "FastAPI", "PostgreSQL", "Docker"} <= set(profile["skills"])  # "Postgres" in CV


def test_no_role_searches_all_categories(client, cv_upload):
    """Regression: no role used to search a non-existent 'backend' category → 0 matches."""
    body = client.post("/api/analyze", files=cv_upload).json()
    assert list(body["by_role"]) == ["best_matches"]
    top = body["by_role"]["best_matches"]["matches"][0]
    assert top["job"]["title"] == "Backend Developer (Python)"
    assert top["score"] == 100
    assert top["job"]["url"] == "https://hh.kz/vacancy/1"
    assert "Communication" not in top["skills_missing"]  # soft skills don't count
    assert top["reason"] == "You have 4 of 4 skills this job asks for."


def test_role_filter(client, cv_upload):
    body = client.post("/api/analyze", files=cv_upload, data={"target_roles": ["devops"]}).json()
    matches = body["by_role"]["devops"]["matches"]
    assert [m["job"]["title"] for m in matches] == ["DevOps Engineer"]
    assert matches[0]["skills_matched"] == ["Docker"]
    assert matches[0]["score"] == 25


def test_duplicates_and_zero_overlap_jobs_are_not_matched(client, cv_upload):
    titles = [m["job"]["title"] for m in all_matches(client.post("/api/analyze", files=cv_upload).json())]
    assert not any("duplicate" in t.lower() for t in titles)
    assert "Frontend Developer" not in titles  # no shared skills


def test_cyrillic_cv(client):
    cv = "Программист 1С, 3 года опыта. Знаю SQL.".encode()
    body = client.post("/api/analyze", files={"cv_file": ("cv.txt", cv, "text/plain")}).json()
    titles = [m["job"]["title"] for m in all_matches(body)]
    assert "Программист 1С" in titles
    job = next(m["job"] for m in all_matches(body) if m["job"]["title"] == "Программист 1С")
    assert job["url"] == ""  # missing link must not become "nan"


def test_salary_with_spaces(client, cv_upload):
    r = client.post("/api/analyze", files=cv_upload, data={"preferred_salary": "500 000"})
    assert r.status_code == 200
    assert all_matches(r.json())[0]["salary_comparison"]["user_expected"] == 500000


def test_unreadable_salary_is_ignored(client, cv_upload):
    r = client.post("/api/analyze", files=cv_upload, data={"preferred_salary": "a lot"})
    assert r.status_code == 200
    assert all_matches(r.json())[0]["salary_comparison"]["user_expected"] is None


def test_no_input_is_rejected(client):
    assert client.post("/api/analyze").status_code == 422


def test_old_doc_format_is_rejected(client):
    r = client.post("/api/analyze", files={"cv_file": ("cv.doc", b"binary", "application/msword")})
    assert r.status_code == 415


def test_large_file_is_rejected(client):
    big = b"a" * (5 * 1024 * 1024 + 1)
    assert client.post("/api/analyze", files={"cv_file": ("cv.txt", big, "text/plain")}).status_code == 413


def test_fallback_cv_lists_only_candidate_skills(client):
    profile = {"name": "Aigerim", "skills": ["Python", "Docker"]}
    cv = client.post("/api/cv/generate", json={
        "job_id": "j5", "job_title": "DevOps Engineer",
        "job_skills": ["Kubernetes", "Docker", "Terraform"], "user_profile": profile,
    }).json()
    assert cv["skills"] == ["Docker", "Python"]  # job's skills first, but never ones she lacks


def test_cors_allows_only_configured_origins(client):
    ok = client.options("/api/health", headers={"Origin": "http://localhost:3001", "Access-Control-Request-Method": "GET"})
    bad = client.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3001"
    assert "access-control-allow-origin" not in bad.headers


def test_fallback_cv_takes_name_and_email_from_cv_text(client, cv_upload):
    profile = client.post("/api/analyze", files=cv_upload).json()["profile"]
    cv = client.post("/api/cv/generate", json={
        "job_id": "j1", "job_title": "Backend Developer", "job_skills": ["Python"],
        "user_profile": profile, "cv_text": profile["cv_text"],
    }).json()
    assert cv["name"] == "Aigerim Nurlanova"
    assert cv["email"] == "aigerim@example.com"
