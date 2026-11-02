"""The job dataset used for matching and the job list.

Where jobs come from (first one with data wins):
1. The jobs database — DATABASE_URL, or DATA_DIR/jobs.db (SQLite) if it exists.
   Filled daily by pipeline/run_daily.py from Telegram channels. Only active jobs
   posted in the last JOB_MAX_AGE_DAYS days are used; the same job posted in
   several channels is shown once.
2. The older batch CSV files in DATA_DIR/final (analysis_ready_jobs_salary_fixed_v3.csv).

The dataset is reloaded every JOBS_RELOAD_SECONDS, so new jobs appear without a restart.
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from services.skills import (
    COMMON_SKILLS, NON_TECHNICAL, find_skills, keyed, level_fit, score_job, skill_key,
)

log = logging.getLogger("seekjobs.loader")

# ── settings ───────────────────────────────────────────────────────────────
_BACKEND  = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("DATA_DIR") or (_BACKEND.parent / "pipeline" / "data"))
DATABASE_URL = os.getenv("DATABASE_URL") or ""
JOB_MAX_AGE_DAYS = int(os.getenv("JOB_MAX_AGE_DAYS") or 45)
RELOAD_SECONDS = int(os.getenv("JOBS_RELOAD_SECONDS") or 600)

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


def clean_url(value) -> str:
    """Job link, or "" for missing/invalid values (pandas NaN must not become "nan")."""
    return value.strip() if isinstance(value, str) and value.strip().startswith("http") else ""


def posted_at_iso(row: pd.Series) -> str | None:
    """'2026-11-02T09:12:55Z' or None (CSV datasets have no post date)."""
    value = row.get("posted_at")
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── load & prepare ──────────────────────────────────────────────────────────
# current dataset + things derived from it (vocabulary, demand ranking)
_state: dict[str, Any] = {"df": None, "loaded_at": 0.0, "vocab": None, "demand": None}
_lock = threading.Lock()


def load_jobs() -> pd.DataFrame:
    """Current job dataset; reloaded from the source every RELOAD_SECONDS."""
    if _state["df"] is not None and time.monotonic() - _state["loaded_at"] < RELOAD_SECONDS:
        return _state["df"]
    with _lock:
        if _state["df"] is not None and time.monotonic() - _state["loaded_at"] < RELOAD_SECONDS:
            return _state["df"]
        try:
            df = _load_raw()
        except Exception:
            log.exception("Loading jobs failed")
            if _state["df"] is None:
                raise
            df = _state["df"]  # keep serving the previous dataset
        if not df.empty and "match_skills" not in df.columns:
            df["match_skills"] = df.apply(_match_skills, axis=1, result_type="reduce")
        _state.update(df=df, loaded_at=time.monotonic(), vocab=None, demand=None)
        return df


def database_url() -> str | None:
    if DATABASE_URL:
        return DATABASE_URL
    sqlite_file = DATA_DIR / "jobs.db"
    return f"sqlite:///{sqlite_file.as_posix()}" if sqlite_file.exists() else None


def _load_raw() -> pd.DataFrame:
    url = database_url()
    if url:
        df = _load_db(url)
        if not df.empty:
            return df
        log.warning("Jobs database has no fresh active jobs — trying CSV files")
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


def _match_skills(row: pd.Series) -> dict[str, str]:
    """Skills used for scoring: hard skills + tech stack (soft skills like
    'communication' are left out — CVs rarely list them, so they'd only lower scores)."""
    hard = safe_parse_list(row.get("hard_skills_clean")) + safe_parse_list(row.get("tech_stack_clean"))
    skills = keyed(hard or row.get("skills_all_clean_list") or [])
    return {k: v for k, v in skills.items() if k not in NON_TECHNICAL}


_engines: dict[str, Any] = {}

# jobs table column (written by pipeline/db.py) -> column name used in this module
_DB_COLUMNS = {
    "title": "title_final", "company": "company_clean", "city": "city_norm",
    "category": "category_filled", "level": "level_filled", "work_format": "work_format_norm",
    "salary_from": "salary_from_clean", "salary_to": "salary_to_clean",
    "salary_avg": "salary_avg_clean", "currency": "currency_clean",
    "skills": "hard_skills_clean", "description": "description_clean_v2",
}


def _load_db(url: str) -> pd.DataFrame:
    """Active jobs posted in the last JOB_MAX_AGE_DAYS days, newest first, one per dedup_key."""
    from sqlalchemy import MetaData, Table, create_engine, inspect, select

    engine = _engines.get(url)
    if engine is None:
        engine = _engines[url] = create_engine(url, pool_pre_ping=True)
    if not inspect(engine).has_table("jobs"):
        log.warning("No 'jobs' table in %s — run pipeline/run_daily.py", url.split("@")[-1])
        return pd.DataFrame()

    jobs = Table("jobs", MetaData(), autoload_with=engine)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=JOB_MAX_AGE_DAYS)
    query = (
        select(jobs)
        .where(jobs.c.is_active == True, jobs.c.posted_at >= cutoff)  # noqa: E712
        .order_by(jobs.c.posted_at.desc())
    )
    with engine.connect() as conn:
        df = pd.DataFrame(conn.execute(query).mappings().all())
    if df.empty:
        return df

    df = df.rename(columns=_DB_COLUMNS)
    df = df.drop_duplicates("dedup_key", keep="first")  # same job in several channels
    df["skills_all_clean_list"] = df["hard_skills_clean"].apply(safe_parse_list)
    for col in ["salary_from_clean", "salary_to_clean", "salary_avg_clean"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["title_final", "company_clean", "city_norm", "category_filled", "level_filled",
                "work_format_norm", "currency_clean", "source", "description_clean_v2"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["currency_clean"] = df["currency_clean"].replace("", "KZT")
    df["dedup_keep_for_analytics"] = True
    df["usable_for_salary_analytics"] = df["salary_avg_clean"].notna() & (df["currency_clean"] == "KZT")
    df = df[df["title_final"] != ""]
    log.info("Loaded %d fresh jobs from database (last %d days)", len(df), JOB_MAX_AGE_DAYS)
    return df.reset_index(drop=True)


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
def get_known_skills() -> list[str]:
    """All skills from the dataset, most frequent first."""
    from collections import Counter
    df = load_jobs()
    if _state["vocab"] is not None and _state["df"] is df:
        return _state["vocab"]
    counter: Counter[str] = Counter()
    if not df.empty:
        for lst in df["skills_all_clean_list"]:
            counter.update(lst)
    skills = [s for s, _ in counter.most_common()]
    log.info("Skills vocabulary: %d unique terms", len(skills))
    _state["vocab"] = skills
    return skills


def get_vocab() -> list[str]:
    """Dataset skills (most frequent first) plus the built-in list of common IT skills."""
    return get_known_skills() + COMMON_SKILLS


def _demand_rank() -> dict[str, int]:
    """skill key -> position in the market-frequency list (0 = most demanded)."""
    df = load_jobs()
    if _state["demand"] is not None and _state["df"] is df:
        return _state["demand"]
    rank: dict[str, int] = {}
    for i, s in enumerate(get_known_skills()):
        rank.setdefault(skill_key(s), i)
    _state["demand"] = rank
    return rank


# ── matching ────────────────────────────────────────────────────────────────
def find_matching_vacancies(
    candidate_skills: list[str],
    *,
    categories: list[str] | None = None,
    level: str = "",
    salary_min: float | None = None,
    user_level: str = "",
    top_n: int = 5,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Rank jobs for a candidate. categories=None searches every category.

    Returns the top_n rows with match_score (0–1 share of the job's skills the
    candidate has), matched_skills and missing_skills (most in-demand first).
    Jobs where the candidate has none of the skills are dropped.
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

    user_keys = set(keyed(candidate_skills))
    demand = _demand_rank()
    scores = [score_job(user_keys, skills) for skills in filtered["match_skills"]]

    filtered = filtered.copy()
    filtered["match_score"] = [s[0] for s in scores]
    # a junior sees senior/lead roles lower in the list (score shown to the user is unchanged)
    filtered["_rank_score"] = [s[1] * level_fit(user_level, lvl) for s, lvl in zip(scores, filtered["level_filled"])]
    filtered["matched_skills"] = [s[2] for s in scores]
    filtered["missing_skills"] = [
        sorted(s[3], key=lambda name: demand.get(skill_key(name), len(demand)))[:8] for s in scores
    ]
    filtered["_n_matched"] = [len(s[2]) for s in scores]
    filtered = filtered[filtered["_n_matched"] > 0]

    sort_cols = ["_rank_score", "_n_matched"] + (
        ["salary_avg_clean"] if "salary_avg_clean" in filtered.columns else []
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


# ── CV text analysis ────────────────────────────────────────────────────────
def extract_skills_from_text(
    text: str,
    known_skills: list[str] | None = None,
    max_skills: int = 40,
) -> list[str]:
    """Known skills in free text (CV, repo summary) — see skills.find_skills."""
    return find_skills(text, get_vocab() if known_skills is None else known_skills, max_skills)


_CV_LEVELS = [
    ("intern", r"intern\w*|trainee|стаж[её]р\w*|стажировк\w*"),
    ("junior", r"junior|джуниор\w*|младш\w*"),
    ("middle", r"middle|mid-level"),
    ("senior", r"senior|сеньор\w*|старш\w*"),
    ("lead", r"team ?lead|tech ?lead|тимлид\w*|техлид\w*|head of|lead (?:developer|engineer)"),
]
_CV_LEVEL_RE = [(lvl, re.compile(rf"(?i)(?<![\w-])(?:{p})(?![\w-])")) for lvl, p in _CV_LEVELS]


def detect_cv_level(text: str, years: int | None) -> str:
    """The level the CV mentions first (usually its headline), else from years of
    experience, else '' (unknown) — never a guess."""
    best: tuple[int, str] | None = None
    for level, rx in _CV_LEVEL_RE:
        m = rx.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), level)
    if best:
        return best[1]
    if years is None:
        return ""
    return "senior" if years >= 5 else "middle" if years >= 3 else "junior"


def summarize_cv_text(text: str, known_skills: list[str] | None = None) -> dict:
    """Skills, years of experience, level and English level found in CV text."""
    clean = text.strip()
    skills = extract_skills_from_text(clean, known_skills)

    years = None
    m = re.search(r"(?<!\d)(\d{1,2})\+?\s*(?:years?|лет|года|год)(?!\w)", clean, re.IGNORECASE)
    if m:
        years = int(m.group(1))

    eng = None
    em = re.search(r"\b(a1|a2|b1|b2|c1|c2)\b", clean, re.IGNORECASE)
    if em:
        eng = em.group(1).upper()

    return {"skills": skills, "years_experience": years, "level": detect_cv_level(clean, years),
            "english_level": eng, "preview": clean[:400]}
