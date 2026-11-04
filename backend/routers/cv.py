"""CV endpoints: generate a tailored CV for a job, export it to PDF / Word."""
import asyncio
import os
import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from services.auth import llm_limiter, optional_user
from services.cv_export import export_filename, to_docx, to_pdf
from services.cv_generator import generate_tailored_cv

router = APIRouter()

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class CVRequest(BaseModel):
    job_id: str
    job_title: str
    job_skills: list[str] = []
    user_profile: dict = {}
    cv_text: str = ""


class CVExportRequest(BaseModel):
    cv: dict
    format: Literal["pdf", "docx"] = "pdf"


@router.post("/cv/generate")
async def generate_cv(req: CVRequest, request: Request, user: dict | None = Depends(optional_user)):
    # AI spending limit: LLM_DAILY_LIMIT AI-written CVs per user (or per IP when logged out) per day;
    # after that the CV is built from the user's data without the LLM
    llm_configured = bool(os.getenv("GROQ_API_KEY"))
    key = f"user:{user['id']}" if user else f"ip:{request.client.host if request.client else '?'}"
    use_llm = llm_configured and llm_limiter.allow(key)
    cv = await generate_tailored_cv(
        job_title=req.job_title,
        job_skills=req.job_skills,
        user_profile=req.user_profile,
        cv_text=req.cv_text,
        use_llm=use_llm,
    )
    cv["ai_limit_reached"] = llm_configured and not use_llm
    return cv


@router.post("/cv/export")
async def export_cv(req: CVExportRequest):
    build = to_pdf if req.format == "pdf" else to_docx
    content = await asyncio.to_thread(build, req.cv)
    filename = export_filename(req.cv, req.format)
    # plain-ASCII fallback for old browsers; modern ones use the UTF-8 filename*
    ascii_name = re.sub(r"_+", "_", filename.encode("ascii", "ignore").decode())
    if ascii_name.startswith("."):
        ascii_name = "CV" + ascii_name
    return Response(
        content,
        media_type=MEDIA_TYPES[req.format],
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"},
    )
