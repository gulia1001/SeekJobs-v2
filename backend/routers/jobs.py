import logging
import pandas as pd
from fastapi import APIRouter, Query
from services.data_loader import load_jobs, build_salary_label

router = APIRouter()
log = logging.getLogger("seekjobs.jobs")


def _row_to_dict(row: pd.Series) -> dict:
    def _float(v):
        try:
            f = float(v)
            return None if pd.isna(f) else f
        except (TypeError, ValueError):
            return None

    return {
        "id": str(row.get("id", "")),
        "title": str(row.get("title_final", "")),
        "company": str(row.get("company_clean", "")),
        "city": str(row.get("city_norm", "")),
        "category": str(row.get("category_filled", "")),
        "level": str(row.get("level_filled", "")),
        "work_format": str(row.get("work_format_norm", "")),
        "salary_from": _float(row.get("salary_from_clean")),
        "salary_to": _float(row.get("salary_to_clean")),
        "salary_avg": _float(row.get("salary_avg_clean")),
        "currency": str(row.get("currency_clean") or "KZT"),
        "skills": list(row.get("skills_all_clean_list") or []),
        "source": str(row.get("source", "")),
        "description": str(row.get("description_clean_v2") or row.get("description") or row.get("requirements_clean") or ""),
        "url": str(row.get("source_url", "")),
        "salary_display": build_salary_label(row),
    }


@router.get("/jobs")
@router.get("/jobs/")
async def list_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    category: str = Query(None),
    level: str = Query(None),
    format: str = Query(None),
):
    df = load_jobs()

    if df.empty:
        log.warning("No data — CSVs not loaded")
        return {"jobs": [], "total": 0, "page": page, "pages": 1}

    # filter
    mask = pd.Series([True] * len(df), index=df.index)
    if "dedup_keep_for_analytics" in df.columns:
        mask &= df["dedup_keep_for_analytics"].fillna(True).astype(bool)
    if category:
        mask &= df["category_filled"].astype(str) == category
    if level:
        mask &= df["level_filled"].astype(str) == level
    if format:
        mask &= df["work_format_norm"].astype(str) == format

    filtered = df[mask]
    total = len(filtered)
    log.info("GET /jobs  category=%s level=%s format=%s  total=%d  page=%d",
             category, level, format, total, page)

    skip = (page - 1) * limit
    page_df = filtered.iloc[skip: skip + limit]

    return {
        "jobs": [_row_to_dict(row) for _, row in page_df.iterrows()],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // limit)),
    }
