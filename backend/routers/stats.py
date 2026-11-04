"""GET /api/stats — real numbers for the landing page (instead of made-up marketing figures)."""
import pandas as pd
from fastapi import APIRouter

from services.data_loader import get_market_salary, load_jobs

router = APIRouter()


@router.get("/stats")
def stats():
    df = load_jobs()
    if df.empty:
        return {"active_jobs": 0, "median_salary_kzt": None, "sources": 0, "newest_post_at": None}
    median = get_market_salary("", df)["avg"]
    newest = None
    if "posted_at" in df.columns and df["posted_at"].notna().any():
        newest = pd.Timestamp(df["posted_at"].max()).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "active_jobs": int(len(df)),
        "median_salary_kzt": median or None,
        "sources": int(df["source"].nunique()) if "source" in df.columns else 0,
        "newest_post_at": newest,
    }
