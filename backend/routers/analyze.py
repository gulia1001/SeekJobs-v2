"""POST /api/analyze — parse profile sources, match jobs, return results."""
import logging
import os

from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request

from services.cv_parser import parse_cv
from services.github_service import analyze_github
from services.linkedin_service import parse_linkedin
from services.job_matcher import match_jobs
from services.data_loader import (
    extract_skills_from_text,
    summarize_cv_text,
    get_vocab,
)

router = APIRouter()
log = logging.getLogger("seekjobs.analyze")


@router.post("/analyze")
@router.post("/analyze/")
@router.get("/analyze")
@router.get("/analyze/")
@router.post("/process")
@router.get("/process")
async def analyze(
    cv_file: UploadFile | None = File(None),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    preferred_salary: str = Form(""),
    target_roles: list[str] = Form([]),
    request: Request = None,
):
    if request and request.method == "GET":
        return {"error": "Please use POST to analyze your profile.", "detected_method": "GET"}
    all_skills: list[str] = []
    profile_name: str | None = None
    github_summary: str = ""
    linkedin_summary: str = ""
    cv_text: str = ""
    gh: dict = {}  # GitHub result — stays empty if no GitHub URL was given
    li: dict = {}  # LinkedIn result — stays empty if no LinkedIn URL was given

    # Pre-load known skills vocabulary once (cached)
    known = get_vocab()
    log.info("Known skills vocabulary: %d terms", len(known))

    # ── 1. CV ─────────────────────────────────────────────────────────────
    if cv_file and cv_file.filename:
        log.info("Parsing CV: %s (%d bytes)", cv_file.filename, cv_file.size or 0)
        content = await cv_file.read()
        cv_text = parse_cv(content, cv_file.filename)
        if cv_text.startswith("[") and "parse error" in cv_text[:30]:
            log.warning("CV parse failed: %s", cv_text)
            cv_text = ""
        cv_data = summarize_cv_text(cv_text, known)
        skills_from_cv = cv_data.get("skills", [])
        log.info("CV skills extracted: %d  preview: %s", len(skills_from_cv), skills_from_cv[:8])
        all_skills.extend(skills_from_cv)

    # ── 2. GitHub ──────────────────────────────────────────────────────────
    if github_url.strip():
        log.info("Analyzing GitHub: %s", github_url.strip())
        gh = analyze_github(github_url.strip())
        gh_skills = gh.get("skills", [])
        gh_error = gh.get("error")
        if gh_error:
            log.warning("GitHub error: %s", gh_error)
        else:
            log.info("GitHub skills: %d  summary: %s", len(gh_skills), gh.get("summary", "")[:80])
        # Also scan GitHub repo descriptions through the known-skills vocabulary
        if gh.get("summary"):
            extra = extract_skills_from_text(gh["summary"], known)
            log.info("GitHub text → extra skills: %s", extra[:6])
            gh_skills = list({s.casefold(): s for s in gh_skills + extra}.values())
        all_skills.extend(gh_skills)
        github_summary = gh.get("summary", "")
        if not profile_name:
            profile_name = gh.get("username")

    # ── 3. LinkedIn ────────────────────────────────────────────────────────
    if linkedin_url.strip():
        log.info("Parsing LinkedIn: %s", linkedin_url.strip())
        li = await parse_linkedin(linkedin_url.strip())
        li_error = li.get("error")
        if li_error:
            log.warning("LinkedIn error: %s", li_error)
        li_skills = li.get("skills", [])
        log.info("LinkedIn skills: %d  name: %s", len(li_skills), li.get("fullName"))
        # Also scan experience text for vocabulary matches
        exp_text = " ".join(
            f"{e.get('title','')} {e.get('company','')}" for e in li.get("experience", [])
        )
        if exp_text:
            extra = extract_skills_from_text(exp_text, known)
            log.info("LinkedIn exp text → extra skills: %s", extra[:6])
            li_skills = list({s.casefold(): s for s in li_skills + extra}.values())
        all_skills.extend(li_skills)
        linkedin_summary = li.get("headline") or li.get("fullName") or ""
        if not profile_name:
            profile_name = li.get("fullName")

    # ── Deduplicate ────────────────────────────────────────────────────────
    seen: set[str] = set()
    unique_skills: list[str] = []
    for s in all_skills:
        key = s.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique_skills.append(s)

    log.info(
        "Total unique skills: %d  sources: cv=%s github=%s linkedin=%s",
        len(unique_skills),
        bool(cv_file and cv_file.filename),
        bool(github_url.strip()),
        bool(linkedin_url.strip()),
    )

    if not unique_skills:
        tried = ", ".join(filter(None, [
            f"CV ({cv_file.filename})" if cv_file and cv_file.filename else "",
            f"GitHub ({github_url.strip()[:40]})" if github_url.strip() else "",
            "LinkedIn" if linkedin_url.strip() else "",
        ])) or "no sources provided"
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract skills from: {tried}. "
                   "Check the GitHub username exists, the LinkedIn URL is public, "
                   "or upload a CV file.",
        )

    # ── 4. Match ───────────────────────────────────────────────────────────
    salary_val = float(preferred_salary) if preferred_salary.strip() else None
    log.info("Matching: roles=%s  salary=%s", target_roles, salary_val)
    by_role = await match_jobs(
        user_skills=unique_skills,
        target_roles=target_roles,
        preferred_salary=salary_val,
        top_n=5,
    )

    log.info("Result: %d roles  total_matches=%d",
             len(by_role), sum(len(v["matches"]) for v in by_role.values()))

    return {
        "profile": {
            "name": profile_name,
            "skills": unique_skills,
            "github_summary": github_summary,
            "linkedin_summary": linkedin_summary,
            "github_url": github_url.strip(),
            "linkedin_url": linkedin_url.strip(),
            "top_repos": gh.get("top_repos", []),
            "certifications": li.get("certifications", []),
            # sent back by the client to /cv/generate so the tailored CV uses real facts
            "cv_text": cv_text,
        },
        "by_role": by_role,
    }
