from __future__ import annotations

from typing import Any, Iterable

import pandas as pd
import streamlit as st

from app.config import QUALITY_ORDER


def _sorted_options(series: pd.Series) -> list[str]:
    values = [value for value in series.dropna().astype(str).str.strip().unique().tolist() if value and value != "nan"]
    return sorted(values)


def render_sidebar_filters(
    df: pd.DataFrame,
    *,
    prefix: str,
    include: Iterable[str],
    default_quality: list[str] | None = None,
    title: str = "Filters",
) -> dict[str, Any]:
    include_set = set(include)
    filters: dict[str, Any] = {}
    default_quality = default_quality if default_quality is not None else [tier for tier in ["A", "B"] if tier in _sorted_options(df["quality_tier"].astype(str))]

    st.sidebar.markdown(f"### {title}")

    if "city" in include_set and "city_norm" in df.columns:
        filters["city"] = st.sidebar.multiselect(
            "City",
            options=_sorted_options(df["city_norm"]),
            key=f"{prefix}_city",
        )

    if "category" in include_set and "category_filled" in df.columns:
        filters["category"] = st.sidebar.multiselect(
            "Category",
            options=_sorted_options(df["category_filled"]),
            key=f"{prefix}_category",
        )

    if "level" in include_set and "level_filled" in df.columns:
        options = _sorted_options(df["level_filled"].astype(str))
        filters["level"] = st.sidebar.multiselect(
            "Level",
            options=options,
            key=f"{prefix}_level",
        )

    if "work_format" in include_set and "work_format_norm" in df.columns:
        filters["work_format"] = st.sidebar.multiselect(
            "Work format",
            options=_sorted_options(df["work_format_norm"].astype(str)),
            key=f"{prefix}_work_format",
        )

    if "source" in include_set and "source_family" in df.columns:
        filters["source"] = st.sidebar.multiselect(
            "Source family",
            options=_sorted_options(df["source_family"]),
            key=f"{prefix}_source",
        )

    if "quality_tier" in include_set and "quality_tier" in df.columns:
        quality_options = [tier for tier in QUALITY_ORDER if tier in _sorted_options(df["quality_tier"].astype(str))]
        filters["quality_tier"] = st.sidebar.multiselect(
            "Quality tier",
            options=quality_options,
            default=default_quality,
            key=f"{prefix}_quality",
        )

    if "english_required" in include_set and "english_required" in df.columns:
        filters["english_required"] = st.sidebar.selectbox(
            "English requirement",
            options=["Any", "Required", "Not required"],
            index=0,
            key=f"{prefix}_english_required",
        )

    if "company" in include_set and "company_clean" in df.columns:
        filters["company"] = st.sidebar.multiselect(
            "Company",
            options=_sorted_options(df["company_clean"])[:200],
            key=f"{prefix}_company",
        )

    if "salary_range" in include_set and "salary_avg_clean" in df.columns:
        salary_values = df["salary_avg_clean"].dropna()
        if not salary_values.empty:
            min_value = int(max(0, salary_values.min() // 50_000 * 50_000))
            max_value = int((salary_values.max() // 50_000 + 1) * 50_000)
            filters["salary_range"] = st.sidebar.slider(
                "Salary range",
                min_value=min_value,
                max_value=max_value,
                value=(min_value, max_value),
                step=50_000,
                key=f"{prefix}_salary_range",
            )

    if "min_vacancies" in include_set:
        filters["min_vacancies"] = st.sidebar.slider(
            "Minimum vacancies per skill",
            min_value=3,
            max_value=100,
            value=10,
            step=1,
            key=f"{prefix}_min_vacancies",
        )

    if "skill_type" in include_set:
        filters["skill_type"] = st.sidebar.radio(
            "Skill set",
            options=["all", "hard", "soft", "tech_stack"],
            index=0,
            key=f"{prefix}_skill_type",
        )

    return filters


def apply_filters(df: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    filtered = df.copy()
    if filters.get("city"):
        filtered = filtered[filtered["city_norm"].isin(filters["city"])]
    if filters.get("category"):
        filtered = filtered[filtered["category_filled"].isin(filters["category"])]
    if filters.get("level"):
        filtered = filtered[filtered["level_filled"].astype(str).isin(filters["level"])]
    if filters.get("work_format"):
        filtered = filtered[filtered["work_format_norm"].astype(str).isin(filters["work_format"])]
    if filters.get("source"):
        filtered = filtered[filtered["source_family"].isin(filters["source"])]
    if filters.get("quality_tier"):
        filtered = filtered[filtered["quality_tier"].astype(str).isin(filters["quality_tier"])]
    if filters.get("company"):
        filtered = filtered[filtered["company_clean"].isin(filters["company"])]

    english_required = filters.get("english_required")
    if english_required == "Required":
        filtered = filtered[filtered["english_required"]]
    elif english_required == "Not required":
        filtered = filtered[~filtered["english_required"]]

    salary_range = filters.get("salary_range")
    if salary_range and "salary_avg_clean" in filtered.columns:
        salary_min, salary_max = salary_range
        filtered = filtered[
            filtered["salary_avg_clean"].isna()
            | filtered["salary_avg_clean"].between(salary_min, salary_max, inclusive="both")
        ]
    return filtered
