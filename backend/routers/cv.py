"""POST /api/cv/generate — generate a tailored CV for a specific job."""
from fastapi import APIRouter
from pydantic import BaseModel

from services.cv_generator import generate_tailored_cv

router = APIRouter()


class CVRequest(BaseModel):
    job_id: str
    job_title: str
    job_skills: list[str] = []
    user_profile: dict = {}
    cv_text: str = ""


@router.post("/cv/generate")
async def generate_cv(req: CVRequest):
    cv = await generate_tailored_cv(
        job_title=req.job_title,
        job_skills=req.job_skills,
        user_profile=req.user_profile,
        cv_text=req.cv_text,
    )
    return cv
