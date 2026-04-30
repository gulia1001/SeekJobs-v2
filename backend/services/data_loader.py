"""
Loads and processes the same dataset used by the Streamlit dashboard.
Primary source: analysis_ready_jobs_salary_fixed_v3.csv
Fallback:  join jobs_entity_clean + jobs_salary_clean_v3 + jobs_skills_clean

Files are produced by pipeline/run_pipeline.py. Set DATA_DIR to point
somewhere else (e.g. /data inside Docker).
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger("seekjobs.loader")

# ── paths ──────────────────────────────────────────────────────────────────
_BACKEND  = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR") or (_BACKEND.parent / "pipeline" / "data"))

FINAL   = DATA_DIR / "final"
INTERIM = DATA_DIR / "interim"

MAIN_CSV    = FINAL   / "analysis_ready_jobs_salary_fixed_v3.csv"
ENTITY_CSV  = FINAL   / "jobs_entity_clean.csv"
SALARY_CSV  = FINAL   / "jobs_salary_clean_v3.csv"
SKILLS_CSV  = FINAL   / "jobs_skills_clean.csv"
ENRICHED_CSV = INTERIM / "enriched_jobs_full_v1.csv"

SKILL_COLS = ["hard_skills_clean", "soft_skills_clean", "tech_stack_clean", "skills_all_clean"]


# ── skill parsing (identical to app/data/loader.py) ────────────────────────
def safe_parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    elif isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null", "[]"}:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                parsed = [p.strip() for p in text.split(",") if p.strip()]
        items = parsed if isinstance(parsed, list) else [parsed]
    else:
        items = [value]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item is None or (isinstance(item, float) and pd.isna(item)):
            continue
        token = str(item).strip()
        if not token:
            continue
        key = token.casefold()
        if key not in seen:
            seen.add(key)
            cleaned.append(token)
    return cleaned


def _combine_skills(row: pd.Series) -> list[str]:
    """Merge hard_skills, soft_skills, tech_stack into one deduplicated list."""
    seen: set[str] = set()
    out: list[str] = []
    for col in SKILL_COLS:
        for s in safe_parse_list(row.get(col)):
            key = s.casefold()
            if key not in seen:
                seen.add(key)
                out.append(s)
    return out


# ── salary display (identical to app/data/loader.py) ───────────────────────
def build_salary_label(row: pd.Series) -> str:
    currency = str(row.get("currency_clean") or "KZT")
    avg = row.get("salary_avg_clean")
    frm = row.get("salary_from_clean")
    to  = row.get("salary_to_clean")
    fmt = lambda n: f"{int(n):,}".replace(",", " ")
    if pd.notna(avg)  and avg:  return f"{fmt(avg)} {currency}"
    if pd.notna(frm) and pd.notna(to) and frm and to:
        return f"{fmt(frm)} – {fmt(to)} {currency}"
    if pd.notna(frm) and frm:   return f"от {fmt(frm)} {currency}"
    if pd.notna(to)  and to:    return f"до {fmt(to)} {currency}"
    return "Salary not listed"


# ── load & prepare ──────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def load_jobs() -> pd.DataFrame:
    if MAIN_CSV.exists():
        log.info("Loading main CSV: %s", MAIN_CSV)
        return _load_main()
    if ENTITY_CSV.exists() and SKILLS_CSV.exists():
        log.info("Building from final CSVs in %s", FINAL)
        return _build_from_parts()
    if ENRICHED_CSV.exists():
        log.info("Loading enriched CSV: %s", ENRICHED_CSV)
        return _load_enriched()
    log.error("No job data found under %s — run pipeline/run_pipeline.py or set DATA_DIR", DATA_DIR)
    return pd.DataFrame()


def _load_main() -> pd.DataFrame:
    """Load analysis_ready_jobs_salary_fixed_v3.csv — same file as Streamlit app."""
    df = pd.read_csv(MAIN_CSV, low_memory=False, encoding="utf-8-sig")
    log.info("Raw rows: %d", len(df))

    # numeric columns
    for col in ["salary_from_clean", "salary_to_clean", "salary_avg_clean", "skills_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # boolean columns
    for col in ["dedup_keep_for_analytics", "usable_for_skill_analytics",
                "usable_for_salary_analytics", "usable_for_employer_analytics"]:
        if col in df.columns:
            df[col] = df[col].apply(_to_bool)

    # build combined skill list (same as Streamlit's _prepare_dataframe)
    df["skills_all_clean_list"] = df.apply(_combine_skills, axis=1)

    # fill required string columns
    for col in ["title_final", "company_clean", "city_norm", "category_filled",
                "level_filled", "work_format_norm", "currency_clean", "source",
                "description", "description_clean_v2", "requirements_clean"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    df["currency_clean"] = df["currency_clean"].replace("", "KZT")

    # keep only analytics-grade rows with a valid title
    if "dedup_keep_for_analytics" in df.columns:
        df = df[df["dedup_keep_for_analytics"]]

    df = df[df["title_final"].str.strip() != ""]
    log.info("After dedup filter: %d rows", len(df))
    return df.reset_index(drop=True)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):   return value
    if pd.isna(value):            return False
    if isinstance(value, (int, float)): return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def _build_from_parts() -> pd.DataFrame:
    """Join entity + salary + skills CSVs when the main file isn't available."""
    entity = pd.read_csv(ENTITY_CSV, low_memory=False, encoding="utf-8-sig")
    salary = pd.read_csv(SALARY_CSV, low_memory=False, encoding="utf-8-sig")
    skills = pd.read_csv(SKILLS_CSV, low_memory=False, encoding="utf-8-sig")

    skills_agg = (
        skills.groupby("job_id")["skill"]
        .apply(list).reset_index()
        .rename(columns={"job_id": "id", "skill": "skills_all_clean_list"})
    )
    df = entity.merge(
        salary[["id", "salary_from_clean", "salary_to_clean", "salary_avg_clean", "currency_clean"]],
        on="id", how="left"
    ).merge(skills_agg, on="id", how="left")

    df["skills_all_clean_list"] = df["skills_all_clean_list"].apply(
        lambda x: x if isinstance(x, list) else []
    )
    df["currency_clean"] = df["currency_clean"].fillna("KZT")
    df = df[df["title_final"].notna() & (df["title_final"].str.strip() != "")]
    log.info("Built from parts: %d rows", len(df))
    return df.reset_index(drop=True)


def _load_enriched() -> pd.DataFrame:
    """Last-resort fallback using the enriched interim CSV."""
    df = pd.read_csv(ENRICHED_CSV, low_memory=False, encoding="utf-8-sig")
    df = df.rename(columns={
        "category": "category_filled", "level": "level_filled",
        "city": "city_norm", "company": "company_clean",
        "title": "title_final", "work_format": "work_format_norm",
        "salary_avg": "salary_avg_clean", "salary_from": "salary_from_clean",
        "salary_to": "salary_to_clean",
    })
    df["skills_all_clean_list"] = df.apply(_combine_skills, axis=1)
    df["currency_clean"] = df.get("currency", "KZT")
    df = df[df["title_final"].notna() & (df["title_final"].str.strip() != "")]
    log.info("Loaded enriched fallback: %d rows", len(df))
    return df.reset_index(drop=True)


# ── skills vocabulary ───────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_known_skills(df_hash: int = 0) -> list[str]:
    """All skills from the dataset, most frequent first."""
    from collections import Counter
    df = load_jobs()
    if df.empty:
        return []
    counter: Counter[str] = Counter()
    for lst in df["skills_all_clean_list"]:
        counter.update(lst)
    skills = [s for s, _ in counter.most_common()]
    log.info("Skills vocabulary: %d unique terms", len(skills))
    return skills


def get_vocab() -> list[str]:
    return get_known_skills()


# ── jaccard matching (identical to app/data/loader.py) ─────────────────────
def jaccard_score(a: list[str], b: list[str]) -> float:
    sa = {s.casefold() for s in a if s}
    sb = {s.casefold() for s in b if s}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def find_matching_vacancies(
    candidate_skills: list[str],
    *,
    categories: list[str] | None = None,
    level: str = "",
    salary_min: float | None = None,
    top_n: int = 5,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Direct port of app/data/loader.py::find_matching_vacancies.
    Returns ranked DataFrame with match_score, matched_skills, missing_skills.
    """
    if df is None:
        df = load_jobs()
    if df.empty:
        return df

    filtered = df.copy()

    if categories:
        filtered = filtered[filtered["category_filled"].isin(categories)]
    if level:
        filtered = filtered[filtered["level_filled"].astype(str) == level]
    if salary_min is not None and "salary_avg_clean" in filtered.columns:
        filtered = filtered[
            filtered["salary_avg_clean"].isna() | (filtered["salary_avg_clean"] >= salary_min)
        ]

    if filtered.empty:
        return filtered

    cand_lower = {s.casefold() for s in candidate_skills}

    filtered = filtered.copy()
    filtered["match_score"] = filtered["skills_all_clean_list"].apply(
        lambda skills: jaccard_score(candidate_skills, skills)
    )
    filtered["matched_skills"] = filtered["skills_all_clean_list"].apply(
        lambda skills: sorted({s for s in skills if s.casefold() in cand_lower})
    )
    filtered["missing_skills"] = filtered["skills_all_clean_list"].apply(
        lambda skills: sorted({s for s in skills if s.casefold() not in cand_lower})[:8]
    )

    sort_cols = ["match_score", "salary_avg_clean"] + (
        ["skills_count"] if "skills_count" in filtered.columns else []
    )
    return (
        filtered
        .sort_values(sort_cols, ascending=False, na_position="last")
        .head(top_n)
    )


def get_market_salary(category: str, df: pd.DataFrame | None = None) -> dict:
    """Median salary + count for a category (salary-quality rows only)."""
    if df is None:
        df = load_jobs()
    if df.empty:
        return {"avg": 0, "currency": "KZT", "count": 0}

    sub = df[df["category_filled"] == category] if category else df
    col = "salary_avg_clean"
    if "usable_for_salary_analytics" in sub.columns:
        sub = sub[sub["usable_for_salary_analytics"]]
    sal = pd.to_numeric(sub[col], errors="coerce").dropna()
    sal = sal[sal > 0]
    return {
        "avg": int(sal.median()) if not sal.empty else 0,
        "currency": "KZT",
        "count": len(sal),
    }


# ── CV text analysis (ported from app/data/loader.py) ──────────────────────
_SHORT_ALLOW = {"ai", "bi", "ci", "ml", "nlp", "qa", "ui", "ux",
                "go", "c#", "c++", "1c", "hr", "r"}


def extract_skills_from_text(
    text: str,
    known_skills: list[str] | None = None,
    max_skills: int = 40,
) -> list[str]:
    """Exact port of app/data/loader.py::extract_known_skills_from_text."""
    if not text.strip():
        return []
    if known_skills is None:
        known_skills = get_vocab()
    lowered = text.casefold()
    found: list[str] = []
    seen: set[str] = set()
    for skill in sorted(known_skills, key=len, reverse=True):
        if len(found) >= max_skills:
            break
        token = skill.strip()
        if not token:
            continue
        norm = token.casefold()
        if len(norm) <= 2 and norm not in _SHORT_ALLOW:
            continue
        if re.search(rf"(?<!\w){re.escape(norm)}(?!\w)", lowered):
            if norm not in seen:
                seen.add(norm)
                found.append(token)
    return found


def summarize_cv_text(text: str, known_skills: list[str] | None = None) -> dict:
    """Exact port of app/data/loader.py::summarize_resume_text."""
    clean = text.strip()
    skills = extract_skills_from_text(clean, known_skills)

    years = None
    m = re.search(r"(\d+)\+?\s*(?:years?|лет|года|год)", clean, re.IGNORECASE)
    if m:
        years = int(m.group(1))

    level = "junior"
    low = clean.casefold()
    if any(w in low for w in ["lead", "head", "руковод", "team lead"]):   level = "lead"
    elif any(w in low for w in ["senior", "старш", "sr."]):               level = "senior"
    elif any(w in low for w in ["middle", "mid-level", "mid "]):          level = "middle"
    elif any(w in low for w in ["intern", "стаж", "trainee"]):            level = "intern"

    eng = None
    em = re.search(r"\b(a1|a2|b1|b2|c1|c2)\b", clean, re.IGNORECASE)
    if em:
        eng = em.group(1).upper()

    return {"skills": skills, "years_experience": years, "level": level,
            "english_level": eng, "preview": clean[:400]}
