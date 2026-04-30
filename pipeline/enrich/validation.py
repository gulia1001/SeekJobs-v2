from __future__ import annotations

import re
from typing import Any

import pandas as pd

from enrich.config import PipelineConfig, STRUCTURED_SOURCES
from enrich.schemas import VacancyExtraction


MERGE_FIELDS = [
    "title_normalized",
    "company",
    "city",
    "category",
    "level",
    "employment",
    "work_format",
    "experience_min",
    "experience_max",
    "english_mention",
    "english_required",
    "english_level",
    "requirements_clean",
    "responsibilities_clean",
    "hard_skills",
    "soft_skills",
    "tech_stack",
    "salary_raw",
    "salary_from",
    "salary_to",
    "currency",
    "salary_period",
    "salary_gross",
]


def is_missing_like(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"", "unknown", "nan", "none", "null", "[]"}
    if isinstance(value, list):
        return len(value) == 0
    return False


def normalize_city(city: str | None) -> str | None:
    if not city:
        return None
    normalized = " ".join(city.split()).strip().lower()
    if any(token in normalized for token in ["алматы", "almaty"]):
        return "almaty"
    if any(token in normalized for token in ["астана", "astana", "nur-sultan", "нур-султан"]):
        return "astana"
    if any(token in normalized for token in ["remote", "удален", "удаленно", "дистанцион"]):
        return "remote"
    return "other"


def canonicalize_skill(skill: str, context_text: str = "") -> str | None:
    if not skill:
        return None
    normalized = " ".join(skill.split()).strip()
    lower = normalized.lower()
    mapping = {
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "py spark": "PySpark",
        "pyspark": "PySpark",
        "k8s": "Kubernetes",
        "kubernetes": "Kubernetes",
    }
    if lower in mapping:
        return mapping[lower]

    if lower == "js":
        programming_context_terms = [
            "developer",
            "engineer",
            "frontend",
            "backend",
            "react",
            "vue",
            "angular",
            "node",
            "typescript",
            "javascript",
            "web",
            "software",
            "programming",
        ]
        context_lower = context_text.lower()
        if any(term in context_lower for term in programming_context_terms):
            return "JavaScript"
        return normalized

    return normalized


def canonicalize_skill_list(items: list[str], context_text: str = "") -> list[str]:
    seen = set()
    cleaned = []
    for item in items:
        canonical = canonicalize_skill(item, context_text=context_text)
        if not canonical:
            continue
        key = canonical.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(canonical)
    return cleaned


def compute_salary_avg(salary_from: Any, salary_to: Any) -> float | None:
    if pd.notna(salary_from) and pd.notna(salary_to):
        return float((float(salary_from) + float(salary_to)) / 2)
    if pd.notna(salary_from):
        return float(salary_from)
    if pd.notna(salary_to):
        return float(salary_to)
    return None


def sanitize_extraction(extraction: VacancyExtraction, context_text: str) -> dict[str, Any]:
    payload = extraction.model_dump(mode="python")
    payload["llm_confidence_raw"] = payload.get("llm_confidence", 0.0)
    payload["city"] = normalize_city(payload.get("city"))
    payload["category"] = payload["category"].value
    payload["level"] = payload["level"].value
    payload["employment"] = payload["employment"].value
    payload["work_format"] = payload["work_format"].value
    payload["english_level"] = payload["english_level"].value
    payload["currency"] = payload["currency"].value
    payload["salary_raw"] = _fill_salary_raw_from_text_if_missing(payload, context_text)
    payload["hard_skills"] = canonicalize_skill_list(payload.get("hard_skills", []), context_text=context_text)
    payload["soft_skills"] = canonicalize_skill_list(payload.get("soft_skills", []), context_text=context_text)
    payload["tech_stack"] = canonicalize_skill_list(payload.get("tech_stack", []), context_text=context_text)
    return payload


def _serialize_list_if_needed(value: Any) -> Any:
    if isinstance(value, list):
        return value if value else None
    return value


def _has_meaningful_text(value: Any, min_length: int = 3) -> bool:
    if not isinstance(value, str):
        return False
    normalized = " ".join(value.split()).strip()
    if len(normalized) < min_length:
        return False
    return normalized.lower() not in {"unknown", "none", "null", "n/a"}


def _has_list_items(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _extract_salary_candidates_from_text(text: str) -> list[str]:
    if not text:
        return []
    pattern = re.compile(
        r"\b\d[\d\s,.–—-]*(?:-\s*\d[\d\s,.–—-]*)?\s*(?:₸|тг|тенге|usd|eur|kzt|rub|rur|руб|\$|€|₽)\b(?:\s*(?:per|/|в|в\s+месяц|в\s+год|месяц|год|hour|week|month|year))?",
        re.I,
    )
    candidates = [match.group(0).strip(" .,-;:") for match in pattern.finditer(text)]
    return candidates


def _matches_salary_candidate(candidate: str, payload: dict[str, Any]) -> bool:
    if not candidate:
        return False
    currency = payload.get("currency")
    if currency and currency != "unknown" and currency.lower() not in candidate.lower():
        return False
    salary_from = payload.get("salary_from")
    salary_to = payload.get("salary_to")
    if salary_from is not None and str(int(salary_from)) in re.sub(r"\D+", "", candidate):
        return True
    if salary_to is not None and str(int(salary_to)) in re.sub(r"\D+", "", candidate):
        return True
    return False


def _fill_salary_raw_from_text_if_missing(payload: dict[str, Any], context_text: str) -> str | None:
    current_raw = payload.get("salary_raw")
    if _has_meaningful_text(current_raw, min_length=2):
        return current_raw
    if not any(
        [
            payload.get("salary_from") is not None,
            payload.get("salary_to") is not None,
            payload.get("currency") not in {None, "unknown"},
        ]
    ):
        return current_raw

    candidates = _extract_salary_candidates_from_text(str(context_text))
    if not candidates:
        return current_raw
    if len(candidates) == 1:
        return candidates[0]
    for candidate in candidates:
        if _matches_salary_candidate(candidate, payload):
            return candidate
    return candidates[0]


def _has_salary_signal(extraction: dict[str, Any]) -> bool:
    return any(
        [
            _has_meaningful_text(extraction.get("salary_raw"), min_length=2),
            extraction.get("salary_from") is not None,
            extraction.get("salary_to") is not None,
            extraction.get("currency") not in {None, "unknown"},
        ]
    )


def _has_english_signal(extraction: dict[str, Any]) -> bool:
    return (
        extraction.get("english_mention") is True
        or extraction.get("english_required") is not None
        or extraction.get("english_level") not in {None, "unknown"}
    )


def compute_extraction_confidence(
    row: pd.Series,
    extraction: dict[str, Any],
    config: PipelineConfig,
) -> tuple[float, dict[str, Any]]:
    source = str(row.get("source") or "")
    is_telegram = source not in STRUCTURED_SOURCES

    signals = {
        "title_normalized": _has_meaningful_text(extraction.get("title_normalized")),
        "company": _has_meaningful_text(extraction.get("company")),
        "city": extraction.get("city") in {"almaty", "astana", "remote"},
        "category": extraction.get("category") not in {None, "unknown"},
        "level": extraction.get("level") not in {None, "unknown"},
        "employment": extraction.get("employment") not in {None, "unknown"},
        "work_format": extraction.get("work_format") not in {None, "unknown"},
        "requirements_clean": _has_meaningful_text(extraction.get("requirements_clean"), min_length=20),
        "responsibilities_clean": _has_meaningful_text(extraction.get("responsibilities_clean"), min_length=20),
        "hard_skills": _has_list_items(extraction.get("hard_skills")),
        "soft_skills": _has_list_items(extraction.get("soft_skills")),
        "tech_stack": _has_list_items(extraction.get("tech_stack")),
        "english": _has_english_signal(extraction),
        "experience": extraction.get("experience_min") is not None or extraction.get("experience_max") is not None,
        "salary": _has_salary_signal(extraction),
    }

    score = min(0.15, 0.02 * sum(1 for present in signals.values() if present))
    if signals["category"]:
        score += 0.14
    if signals["level"]:
        score += 0.07
    if signals["title_normalized"]:
        score += 0.08
    if signals["company"]:
        score += 0.06 + (0.04 if is_telegram else 0.0)
    if signals["city"]:
        score += 0.04 + (0.03 if is_telegram else 0.0)
    if signals["employment"]:
        score += 0.05
    if signals["work_format"]:
        score += 0.05
    if signals["requirements_clean"]:
        score += 0.10
    if signals["responsibilities_clean"]:
        score += 0.10
    if signals["hard_skills"]:
        score += 0.10
    if signals["tech_stack"]:
        score += 0.06
    if signals["soft_skills"]:
        score += 0.03
    if signals["english"]:
        score += 0.04
    if signals["experience"]:
        score += 0.04
    if signals["salary"]:
        score += 0.04

    major_signal_count = sum(
        [
            signals["title_normalized"],
            signals["company"],
            signals["category"],
            signals["requirements_clean"],
            signals["responsibilities_clean"],
            signals["hard_skills"] or signals["tech_stack"],
        ]
    )
    if major_signal_count == 0:
        score = 0.0
    elif major_signal_count == 1:
        score -= 0.12

    raw_confidence = 0.0
    try:
        raw_confidence = max(0.0, min(float(extraction.get("llm_confidence_raw") or 0.0), 1.0))
    except (TypeError, ValueError):
        raw_confidence = 0.0
    score += raw_confidence * config.raw_model_confidence_weight

    score = max(0.0, min(score, 1.0))
    return round(score, 4), {
        "signal_count": sum(1 for present in signals.values() if present),
        "major_signal_count": int(major_signal_count),
        "raw_llm_confidence": raw_confidence,
        "signals": signals,
    }


def merge_row_with_extraction(row: pd.Series, extraction: dict[str, Any], config: PipelineConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = row.to_dict()
    changes = {}

    confidence, confidence_meta = compute_extraction_confidence(row, extraction, config)
    has_extraction = any(not is_missing_like(extraction.get(field)) for field in MERGE_FIELDS)
    if confidence < config.low_confidence_threshold and not has_extraction:
        updated["llm_confidence"] = max(confidence, float(row.get("llm_confidence") or 0.0))
        updated["llm_review_flag"] = False
        updated["llm_merge_status"] = "skipped_low_confidence"
        return updated, {
            "merged_fields": [],
            "merge_status": "skipped_low_confidence",
            "llm_confidence": confidence,
            "confidence_meta": confidence_meta,
        }

    review_flag = True if confidence < config.review_confidence_threshold else False

    for field in MERGE_FIELDS:
        incoming = _serialize_list_if_needed(extraction.get(field))
        if is_missing_like(incoming):
            continue
        current = updated.get(field)
        if field == "english_mention":
            if incoming is True and current is not True:
                updated[field] = True
                changes[field] = True
            continue
        if is_missing_like(current):
            updated[field] = incoming
            changes[field] = incoming

    updated["salary_avg"] = compute_salary_avg(updated.get("salary_from"), updated.get("salary_to"))
    updated["llm_confidence"] = max(confidence, float(row.get("llm_confidence") or 0.0))
    updated["llm_review_flag"] = review_flag
    updated["llm_merge_status"] = "merged_with_review" if review_flag else "auto_merged"

    if changes:
        previous_method = str(row.get("extraction_method") or "").strip().lower()
        updated["extraction_method"] = "llm" if previous_method in {"", "nan", "none"} else "mixed"
    else:
        updated["llm_merge_status"] = "no_missing_targets"

    return updated, {
        "merged_fields": sorted(changes.keys()),
        "merge_status": updated["llm_merge_status"],
        "llm_confidence": confidence,
        "review_flag": review_flag,
        "confidence_meta": confidence_meta,
    }
