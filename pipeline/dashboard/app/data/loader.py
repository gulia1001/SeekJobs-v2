from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from app.config import (
    BOOLEAN_COLUMNS,
    CITY_ORDER,
    DATASET_PATH,
    LEVEL_ORDER,
    NUMERIC_COLUMNS,
    QUALITY_ORDER,
    REQUIRED_COLUMNS,
    SKILL_COLUMNS,
    SOURCE_FAMILY_MAP,
    STRUCTURED_SALARY_SOURCES,
    WORK_FORMAT_ORDER,
)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "t"}


def _safe_parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    elif isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                parsed = [part.strip() for part in text.split(",") if part.strip()]
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
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(token)
    return cleaned


def _normalize_source_family(source: Any) -> str:
    text = str(source or "").strip()
    if text in SOURCE_FAMILY_MAP:
        return SOURCE_FAMILY_MAP[text]
    if text:
        return "telegram"
    return "other"


def _normalize_city_bucket(city: Any) -> str:
    text = str(city or "").strip().lower()
    if text in {"almaty", "astana", "remote"}:
        return text
    if not text:
        return "other"
    return "other"


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    for column, default in REQUIRED_COLUMNS.items():
        if column not in frame.columns:
            frame[column] = default
    return frame


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    frame = _ensure_columns(df)

    for column in NUMERIC_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    for column in BOOLEAN_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].apply(_to_bool)

    for column in SKILL_COLUMNS:
        frame[f"{column}_list"] = frame[column].apply(_safe_parse_list)

    for column in [
        "title_final",
        "company_clean",
        "city_norm",
        "category_filled",
        "level_filled",
        "employment_norm",
        "work_format_norm",
        "currency_clean",
        "quality_tier",
        "source",
        "source_url",
        "requirements_clean",
        "description",
        "description_clean_v2",
    ]:
        if column in frame.columns:
            frame[column] = frame[column].fillna("").astype(str).str.strip()

    frame["source_family"] = frame["source"].apply(_normalize_source_family)
    frame["city_bucket"] = frame["city_norm"].apply(_normalize_city_bucket)
    frame["posted_at_dt"] = pd.to_datetime(frame.get("posted_at"), errors="coerce")
    frame["scraped_at_dt"] = pd.to_datetime(frame.get("scraped_at"), errors="coerce")
    frame["quality_tier"] = pd.Categorical(frame["quality_tier"], QUALITY_ORDER, ordered=True)
    frame["level_filled"] = pd.Categorical(frame["level_filled"], LEVEL_ORDER, ordered=True)
    frame["work_format_norm"] = pd.Categorical(
        frame["work_format_norm"], WORK_FORMAT_ORDER, ordered=True
    )
    frame["city_bucket"] = pd.Categorical(frame["city_bucket"], CITY_ORDER, ordered=True)
    frame["skills_count"] = pd.to_numeric(frame["skills_count"], errors="coerce").fillna(0).astype(int)
    frame["structured_salary_source_flag"] = frame["source"].isin(STRUCTURED_SALARY_SOURCES)
    frame["salary_structured_analytics_flag"] = (
        frame["usable_for_salary_analytics"] & frame["structured_salary_source_flag"]
    )
    frame["salary_avg_analytics"] = frame["salary_avg_clean"].where(frame["salary_structured_analytics_flag"])
    frame["salary_from_analytics"] = frame["salary_from_clean"].where(frame["salary_structured_analytics_flag"])
    frame["salary_to_analytics"] = frame["salary_to_clean"].where(frame["salary_structured_analytics_flag"])
    frame["salary_display"] = frame.apply(build_salary_label, axis=1)
    frame["title_display"] = frame["title_final"].replace("", "Untitled vacancy")
    frame["company_display"] = frame["company_clean"].replace("", "Company not specified")
    frame["category_display"] = frame["category_filled"].replace("", "unresolved")
    frame["level_display"] = frame["level_filled"].astype(str).replace("nan", "").replace("", "unresolved")
    return frame


@st.cache_data(ttl=3600, show_spinner=False)
def load_data(path: str | Path = DATASET_PATH) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    return _prepare_dataframe(frame)


@st.cache_data(ttl=3600, show_spinner=False)
def load_dataset_bundle(path: str | Path = DATASET_PATH) -> dict[str, Any]:
    df = load_data(path)
    structured_base = df[df["dedup_keep_for_analytics"] & df["structured_salary_source_flag"]].copy()
    bundle = {
        "all": df,
        "base": df[df["dedup_keep_for_analytics"]].copy(),
        "base_structured": structured_base,
        "salary": df[df["salary_structured_analytics_flag"]].copy(),
        "skills": df[df["usable_for_skill_analytics"]].copy(),
        "employer": df[df["usable_for_employer_analytics"]].copy(),
        "category": df[df["usable_for_category_analytics"]].copy(),
        "known_skills": get_known_skills(df),
    }
    return bundle


def get_known_skills(df: pd.DataFrame) -> list[str]:
    counter: Counter[str] = Counter()
    for column in [f"{col}_list" for col in SKILL_COLUMNS]:
        if column not in df.columns:
            continue
        for values in df[column]:
            counter.update(values)
    return [skill for skill, _ in counter.most_common()]


def explode_skills(
    df: pd.DataFrame,
    list_column: str = "skills_all_clean_list",
    output_column: str = "skill",
) -> pd.DataFrame:
    if list_column not in df.columns:
        return pd.DataFrame(columns=[*df.columns, output_column])
    exploded = df.copy()
    exploded[output_column] = exploded[list_column]
    exploded = exploded.explode(output_column)
    exploded[output_column] = exploded[output_column].fillna("").astype(str).str.strip()
    return exploded[exploded[output_column] != ""]


def build_salary_label(row: pd.Series) -> str:
    currency = row.get("currency_clean") or "KZT"
    salary_avg = row.get("salary_avg_clean")
    salary_from = row.get("salary_from_clean")
    salary_to = row.get("salary_to_clean")
    if pd.notna(salary_avg):
        return f"{int(salary_avg):,} {currency}".replace(",", " ")
    if pd.notna(salary_from) and pd.notna(salary_to):
        return f"{int(salary_from):,} - {int(salary_to):,} {currency}".replace(",", " ")
    if pd.notna(salary_from):
        return f"from {int(salary_from):,} {currency}".replace(",", " ")
    if pd.notna(salary_to):
        return f"up to {int(salary_to):,} {currency}".replace(",", " ")
    return "Salary not specified"


def compute_salary_coverage(total_count: int, salary_count: int) -> float:
    if total_count <= 0:
        return 0.0
    return round(salary_count / total_count * 100, 1)


def get_top_skills_for_role(
    df: pd.DataFrame,
    category: str,
    level: str,
    list_column: str = "skills_all_clean_list",
    top_n: int = 20,
) -> list[str]:
    filtered = df.copy()
    if category:
        filtered = filtered[filtered["category_filled"] == category]
    if level:
        filtered = filtered[filtered["level_filled"].astype(str) == level]
    exploded = explode_skills(filtered, list_column=list_column)
    if exploded.empty:
        return []
    return exploded["skill"].value_counts().head(top_n).index.tolist()


def extract_known_skills_from_text(text: str, known_skills: list[str], max_skills: int = 40) -> list[str]:
    if not text.strip():
        return []
    lowered = text.casefold()
    found: list[str] = []
    seen: set[str] = set()
    short_skill_allowlist = {"ai", "bi", "ci", "ml", "nlp", "qa", "ui", "ux", "go", "c#", "c++", "1c", "hr"}
    for skill in sorted(known_skills, key=len, reverse=True):
        if len(found) >= max_skills:
            break
        token = skill.strip()
        if not token:
            continue
        normalized = token.casefold()
        if len(normalized) <= 2 and normalized not in short_skill_allowlist:
            continue
        pattern = re.escape(token.casefold())
        if re.search(rf"(?<!\w){pattern}(?!\w)", lowered):
            key = normalized
            if key not in seen:
                seen.add(key)
                found.append(token)
    return found


def summarize_resume_text(text: str, known_skills: list[str]) -> dict[str, Any]:
    clean_text = text.strip()
    skills = extract_known_skills_from_text(clean_text, known_skills)
    years = None
    match = re.search(r"(\d+)\+?\s*(?:years|year|лет|года|год)", clean_text, flags=re.IGNORECASE)
    if match:
        years = int(match.group(1))

    level = "junior"
    lowered = clean_text.casefold()
    if any(word in lowered for word in ["lead", "head", "руковод", "team lead"]):
        level = "lead"
    elif any(word in lowered for word in ["senior", "старш", "sr."]):
        level = "senior"
    elif any(word in lowered for word in ["middle", "mid-level", "mid "]):
        level = "middle"
    elif any(word in lowered for word in ["intern", "стаж", "trainee"]):
        level = "intern"

    english_level = None
    eng_match = re.search(r"\b(a1|a2|b1|b2|c1|c2)\b", clean_text, flags=re.IGNORECASE)
    if eng_match:
        english_level = eng_match.group(1).upper()

    return {
        "hard_skills": skills,
        "soft_skills": [],
        "tech_stack": skills,
        "years_experience": years,
        "current_level": level,
        "english_level": english_level,
        "summary": clean_text[:400],
    }


def jaccard_score(skills_a: list[str], skills_b: list[str]) -> float:
    a = {skill.casefold() for skill in skills_a if skill}
    b = {skill.casefold() for skill in skills_b if skill}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_matching_vacancies(
    df: pd.DataFrame,
    candidate_skills: list[str],
    *,
    category: str = "",
    level: str = "",
    city: str = "",
    work_format: str = "",
    salary_min: int | float | None = None,
    top_n: int = 10,
    list_column: str = "skills_all_clean_list",
) -> pd.DataFrame:
    filtered = df.copy()
    if category:
        filtered = filtered[filtered["category_filled"] == category]
    if level:
        filtered = filtered[filtered["level_filled"].astype(str) == level]
    if city:
        filtered = filtered[filtered["city_norm"] == city]
    if work_format:
        filtered = filtered[filtered["work_format_norm"].astype(str) == work_format]
    if salary_min is not None and "salary_avg_clean" in filtered.columns:
        filtered = filtered[
            filtered["salary_avg_clean"].isna() | (filtered["salary_avg_clean"] >= salary_min)
        ]

    if filtered.empty:
        return filtered

    filtered = filtered.copy()
    filtered["match_score"] = filtered[list_column].apply(lambda skills: jaccard_score(candidate_skills, skills))
    filtered["matched_skills"] = filtered[list_column].apply(
        lambda skills: sorted(
            {skill for skill in skills if skill.casefold() in {s.casefold() for s in candidate_skills}}
        )
    )
    filtered["missing_skills_for_job"] = filtered[list_column].apply(
        lambda skills: sorted(
            {skill for skill in skills if skill.casefold() not in {s.casefold() for s in candidate_skills}}
        )[:8]
    )
    filtered = filtered.sort_values(
        ["match_score", "salary_avg_clean", "skills_count"],
        ascending=[False, False, False],
    )
    return filtered.head(top_n)


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 1)
