"""POST /api/analyze — parse profile sources, match jobs, return results."""
import asyncio
import logging
import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.cv_parser import parse_cv
from services.data_loader import extract_skills_from_text, get_vocab, summarize_cv_text
from services.github_service import analyze_github
from services.job_matcher import match_jobs
from services.linkedin_pdf import parse_linkedin_text
from services.linkedin_pdf import pdf_text as linkedin_pdf_text
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


async def _read_upload(file: UploadFile, allowed: set[str], what: str) -> bytes:
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        hint = ("Please upload your CV as PDF, Word (.docx) or .txt. Old .doc files: open in Word "
                "and 'Save as' .docx.") if what == "CV" else f"The {what} must be a PDF file."
        raise HTTPException(415, hint)
    if file.size and file.size > MAX_CV_BYTES:
        raise HTTPException(413, f"{what} file is larger than 5 MB.")
    content = await file.read()
    if len(content) > MAX_CV_BYTES:
        raise HTTPException(413, f"{what} file is larger than 5 MB.")
    return content


async def _read_cv(cv_file: UploadFile) -> str:
    content = await _read_upload(cv_file, ALLOWED_CV_TYPES, "CV")
    text = await asyncio.to_thread(parse_cv, content, cv_file.filename)
    if text.startswith("[") and "parse error" in text[:30]:
        log.warning("CV parse failed: %s", text)
        return ""
    return text


async def _read_linkedin_pdf(file: UploadFile) -> dict:
    content = await _read_upload(file, {"pdf"}, "LinkedIn PDF")
    try:
        text = await asyncio.to_thread(linkedin_pdf_text, content)
    except Exception as e:  # damaged or not really a PDF
        log.warning("LinkedIn PDF parse failed: %s", e)
        raise HTTPException(422, "Could not read the LinkedIn PDF. Download it again with 'Save to PDF'.")
    return parse_linkedin_text(text)


@router.post("/analyze")
async def analyze(
    cv_file: UploadFile | None = File(None),
    linkedin_pdf: UploadFile | None = File(None),
    github_url: str = Form(""),
    preferred_salary: str = Form(""),
    target_roles: list[str] = Form([]),
):
    github_url = github_url.strip()
    has_cv = bool(cv_file and cv_file.filename)
    has_li = bool(linkedin_pdf and linkedin_pdf.filename)
    if not (has_cv or github_url or has_li):
        raise HTTPException(422, "Upload a CV or a LinkedIn PDF, or provide a GitHub link.")

    all_skills: list[str] = []
    user_level = ""  # from the CV text, used to rank jobs at the right level higher
    profile_name: str | None = None
    cv_text = ""
    gh: dict = {}  # GitHub result — stays empty if no GitHub URL was given
    li: dict = {}  # LinkedIn PDF result — stays empty if no LinkedIn PDF was uploaded

    known = get_vocab()

    # ── 1. CV ─────────────────────────────────────────────────────────────
    if has_cv:
        cv_text = await _read_cv(cv_file)
        cv_summary = summarize_cv_text(cv_text, known)
        cv_skills, user_level = cv_summary["skills"], cv_summary["level"]
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

    # ── 3. LinkedIn profile PDF (the user's own export — no scraping) ──────
    if has_li:
        li = await _read_linkedin_pdf(linkedin_pdf)
        all_skills.extend(li["skills"] + extract_skills_from_text(li["text"], known))
        # the tailored CV can use the LinkedIn experience too
        cv_text = "\n\n".join(filter(None, [cv_text, li["text"]]))
        log.info("LinkedIn PDF: %d top skills, %d certifications", len(li["skills"]), len(li["certifications"]))

    # 'Postgres' and 'PostgreSQL' count once
    unique_skills = dedupe_skills(all_skills)
    log.info("Total unique skills: %d  sources: cv=%s github=%s linkedin=%s",
             len(unique_skills), has_cv, bool(github_url), has_li)

    if not unique_skills:
        tried = ", ".join(filter(None, [
            f"CV ({cv_file.filename})" if has_cv else "",
            f"GitHub ({github_url[:40]})" if github_url else "",
            "LinkedIn PDF" if has_li else "",
        ]))
        raise HTTPException(
            422,
            f"Could not extract skills from: {tried}. Check that the GitHub username exists, "
            "or upload a CV / LinkedIn PDF that lists your skills.",
        )

    # ── 4. Match ───────────────────────────────────────────────────────────
    roles = [r for r in target_roles if r.strip()]
    salary_val = parse_salary(preferred_salary)
    by_role = await match_jobs(user_skills=unique_skills, target_roles=roles,
                               preferred_salary=salary_val, user_level=user_level)
    log.info("Result: %d roles  total_matches=%d", len(by_role), sum(len(v["matches"]) for v in by_role.values()))

    return {
        "profile": {
            "name": profile_name,
            "skills": unique_skills,
            "github_summary": gh.get("summary", ""),
            "linkedin_summary": "",
            "github_url": github_url,
            "linkedin_url": li.get("linkedin_url", ""),
            "top_repos": gh.get("top_repos", []),
            "certifications": li.get("certifications", []),
            # sent back by the client to /cv/generate so the tailored CV uses real facts
            "cv_text": cv_text,
            "level": user_level,
        },
        "by_role": by_role,
    }
