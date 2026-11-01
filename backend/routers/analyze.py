"""POST /api/analyze — parse profile sources, match jobs, return results."""
import asyncio
import logging
import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.cv_parser import parse_cv
from services.data_loader import extract_skills_from_text, get_vocab, summarize_cv_text
from services.github_service import analyze_github
from services.job_matcher import match_jobs
from services.linkedin_service import parse_linkedin
from services.skills import dedupe_skills

router = APIRouter()
log = logging.getLogger("seekjobs.analyze")

MAX_CV_BYTES = 5 * 1024 * 1024
ALLOWED_CV_TYPES = {"pdf", "docx", "txt"}


def parse_salary(value: str) -> float | None:
    """'500 000', '500000₸', '500k' -> number; anything unreadable -> None."""
    text = value.strip().lower().replace(",", ".")
    m = re.match(r"^(\d[\d\s.]*)\s*(k|к|тыс)?", text)
    if not m:
        return None
    digits = re.sub(r"\s", "", m.group(1))
    try:
        number = float(digits)
    except ValueError:
        return None
    if m.group(2):
        number *= 1000
    return number if number > 0 else None


async def _read_cv(cv_file: UploadFile) -> str:
    ext = cv_file.filename.rsplit(".", 1)[-1].lower() if "." in cv_file.filename else ""
    if ext not in ALLOWED_CV_TYPES:
        raise HTTPException(415, "Please upload your CV as PDF, Word (.docx) or .txt. "
                                 "Old .doc files: open in Word and 'Save as' .docx.")
    if cv_file.size and cv_file.size > MAX_CV_BYTES:
        raise HTTPException(413, "CV file is larger than 5 MB.")
    content = await cv_file.read()
    if len(content) > MAX_CV_BYTES:
        raise HTTPException(413, "CV file is larger than 5 MB.")
    text = await asyncio.to_thread(parse_cv, content, cv_file.filename)
    if text.startswith("[") and "parse error" in text[:30]:
        log.warning("CV parse failed: %s", text)
        return ""
    return text


@router.post("/analyze")
async def analyze(
    cv_file: UploadFile | None = File(None),
    linkedin_url: str = Form(""),
    github_url: str = Form(""),
    preferred_salary: str = Form(""),
    target_roles: list[str] = Form([]),
):
    github_url, linkedin_url = github_url.strip(), linkedin_url.strip()
    has_cv = bool(cv_file and cv_file.filename)
    if not (has_cv or github_url or linkedin_url):
        raise HTTPException(422, "Upload a CV or provide a GitHub or LinkedIn link.")

    all_skills: list[str] = []
    profile_name: str | None = None
    cv_text = ""
    gh: dict = {}  # GitHub result — stays empty if no GitHub URL was given
    li: dict = {}  # LinkedIn result — stays empty if no LinkedIn URL was given

    known = get_vocab()

    # ── 1. CV ─────────────────────────────────────────────────────────────
    if has_cv:
        cv_text = await _read_cv(cv_file)
        cv_skills = summarize_cv_text(cv_text, known).get("skills", [])
        log.info("CV %s: %d skills  preview: %s", cv_file.filename, len(cv_skills), cv_skills[:8])
        all_skills.extend(cv_skills)

    # ── 2. GitHub (sync HTTP calls → run off the event loop) ───────────────
    if github_url:
        gh = await asyncio.to_thread(analyze_github, github_url)
        if gh.get("error"):
            log.warning("GitHub error: %s", gh["error"])
        gh_skills = gh.get("skills", [])
        if gh.get("summary"):
            gh_skills += extract_skills_from_text(gh["summary"], known)
        all_skills.extend(gh_skills)
        profile_name = profile_name or gh.get("username")

    # ── 3. LinkedIn ────────────────────────────────────────────────────────
    if linkedin_url:
        li = await parse_linkedin(linkedin_url)
        if li.get("error"):
            log.warning("LinkedIn error: %s", li["error"])
        li_skills = li.get("skills", [])
        exp_text = " ".join(f"{e.get('title', '')} {e.get('company', '')}" for e in li.get("experience", []))
        if exp_text.strip():
            li_skills += extract_skills_from_text(exp_text, known)
        all_skills.extend(li_skills)
        profile_name = profile_name or li.get("fullName")

    # 'Postgres' and 'PostgreSQL' count once
    unique_skills = dedupe_skills(all_skills)
    log.info("Total unique skills: %d  sources: cv=%s github=%s linkedin=%s",
             len(unique_skills), has_cv, bool(github_url), bool(linkedin_url))

    if not unique_skills:
        tried = ", ".join(filter(None, [
            f"CV ({cv_file.filename})" if has_cv else "",
            f"GitHub ({github_url[:40]})" if github_url else "",
            "LinkedIn" if linkedin_url else "",
        ]))
        raise HTTPException(
            422,
            f"Could not extract skills from: {tried}. Check that the GitHub username exists, "
            "the LinkedIn URL is public, or upload a CV that lists your skills.",
        )

    # ── 4. Match ───────────────────────────────────────────────────────────
    roles = [r for r in target_roles if r.strip()]
    salary_val = parse_salary(preferred_salary)
    by_role = await match_jobs(user_skills=unique_skills, target_roles=roles, preferred_salary=salary_val)
    log.info("Result: %d roles  total_matches=%d", len(by_role), sum(len(v["matches"]) for v in by_role.values()))

    return {
        "profile": {
            "name": profile_name,
            "skills": unique_skills,
            "github_summary": gh.get("summary", ""),
            "linkedin_summary": li.get("headline") or li.get("fullName") or "",
            "github_url": github_url,
            "linkedin_url": linkedin_url,
            "top_repos": gh.get("top_repos", []),
            "certifications": li.get("certifications", []),
            # sent back by the client to /cv/generate so the tailored CV uses real facts
            "cv_text": cv_text,
        },
        "by_role": by_role,
    }
