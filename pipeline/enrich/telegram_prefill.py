from __future__ import annotations

import re
from typing import Any


PREFILL_FIELDS = [
    "company",
    "city",
    "employment",
    "work_format",
    "salary_raw",
    "salary_from",
    "salary_to",
    "currency",
    "experience_min",
    "experience_max",
]

PARSER_FIRST_FIELDS = set(PREFILL_FIELDS)
LLM_FIRST_FIELDS = {
    "title_normalized",
    "category",
    "level",
    "requirements_clean",
    "responsibilities_clean",
    "hard_skills",
    "soft_skills",
    "tech_stack",
}
HYBRID_FIELDS = {"company", "city", "title_normalized"}


LABEL_PATTERNS = {
    "company": [
        re.compile(r"(?im)^(?:компания|company)\s*[:\-]\s*(.+)$"),
    ],
    "city": [
        re.compile(r"(?im)^(?:город|city|location|локация)\s*[:\-]\s*(.+)$"),
    ],
    "employment": [
        re.compile(r"(?im)^(?:занятость|employment)\s*[:\-]\s*(.+)$"),
    ],
    "work_format": [
        re.compile(r"(?im)^(?:формат|work format|format)\s*[:\-]\s*(.+)$"),
    ],
    "salary_raw": [
        re.compile(r"(?im)^(?:зарплата|salary)\s*[:\-]\s*(.+)$"),
    ],
    "experience": [
        re.compile(r"(?im)^(?:опыт|experience)\s*[:\-]\s*(.+)$"),
    ],
}


def _normalize_whitespace(text: str | None) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(text.replace("\xa0", " ").split()).strip()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return _normalize_whitespace(value).lower() in {"", "unknown", "none", "null", "n/a"}
    if isinstance(value, list):
        return len(value) == 0
    return False


def _normalize_city(value: str | None) -> str | None:
    text = _normalize_whitespace(value).lower()
    if not text:
        return None
    if any(token in text for token in ["алматы", "almaty"]):
        return "almaty"
    if any(token in text for token in ["астана", "astana", "nur-sultan", "нур-султан"]):
        return "astana"
    if any(token in text for token in ["remote", "удален", "дистанцион"]):
        return "remote"
    if len(text) >= 2:
        return "other"
    return None


def _normalize_employment(value: str | None) -> str | None:
    text = _normalize_whitespace(value).lower()
    if not text:
        return None
    mapping = [
        (["полная", "full time", "full-time", "fulltime"], "full_time"),
        (["частичная", "part time", "part-time", "parttime"], "part_time"),
        (["contract", "контракт", "contractor"], "contract"),
        (["intern", "стаж", "internship"], "internship"),
        (["temporary", "временн"], "temporary"),
        (["freelance", "freelancer", "project"], "contract"),
    ]
    for terms, normalized in mapping:
        if any(term in text for term in terms):
            return normalized
    return None


def _normalize_work_format(value: str | None) -> str | None:
    text = _normalize_whitespace(value).lower()
    if not text:
        return None
    if any(term in text for term in ["гибрид", "hybrid"]):
        return "hybrid"
    if any(term in text for term in ["удален", "remote", "дистанцион", "work from home", "home office"]):
        return "remote"
    if any(term in text for term in ["onsite", "on-site", "офис", "office", "в офисе"]):
        return "office"
    return None


def _normalize_currency(value: str | None) -> str | None:
    text = _normalize_whitespace(value).upper()
    if not text:
        return None
    if any(token in text for token in ["KZT", "ТГ", "₸", "ТЕНГЕ"]):
        return "KZT"
    if any(token in text for token in ["USD", "$"]):
        return "USD"
    if any(token in text for token in ["EUR", "€"]):
        return "EUR"
    if any(token in text for token in ["RUB", "RUR", "РУБ"]):
        return "RUB"
    return None


def _parse_salary_text(text: str | None) -> tuple[str | None, int | None, int | None, str | None]:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return None, None, None, None

    currency = _normalize_currency(normalized)
    numbers = [
        int(match.replace(" ", ""))
        for match in re.findall(r"(\d[\d ]+)", normalized)
        if match.replace(" ", "").isdigit()
    ]
    if not numbers:
        return normalized, None, None, currency

    lowered = normalized.lower()
    if ("до" in lowered or "to" in lowered) and len(numbers) == 1:
        return normalized, None, numbers[0], currency
    if ("от" in lowered or "from" in lowered) and len(numbers) == 1:
        return normalized, numbers[0], None, currency
    if len(numbers) >= 2:
        return normalized, min(numbers[0], numbers[1]), max(numbers[0], numbers[1]), currency
    return normalized, numbers[0], None, currency


def _parse_experience_text(text: str | None) -> tuple[float | None, float | None]:
    normalized = _normalize_whitespace(text).lower()
    if not normalized:
        return None, None
    if "нет опыта" in normalized or "no experience" in normalized:
        return 0.0, 0.0

    from_to = re.search(r"(?:от|from)\s*(\d+(?:[.,]\d+)?)\s*(?:г|лет|years?)?.{0,12}?(?:до|to)\s*(\d+(?:[.,]\d+)?)", normalized)
    if from_to:
        a = float(from_to.group(1).replace(",", "."))
        b = float(from_to.group(2).replace(",", "."))
        return min(a, b), max(a, b)

    ranged = re.search(r"(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*(?:г|лет|years?)", normalized)
    if ranged:
        a = float(ranged.group(1).replace(",", "."))
        b = float(ranged.group(2).replace(",", "."))
        return min(a, b), max(a, b)

    minimum = re.search(r"(?:от|from|more than|более)\s*(\d+(?:[.,]\d+)?)", normalized)
    if minimum:
        return float(minimum.group(1).replace(",", ".")), None

    maximum = re.search(r"(?:до|up to)\s*(\d+(?:[.,]\d+)?)", normalized)
    if maximum:
        return 0.0, float(maximum.group(1).replace(",", "."))

    single = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:\+)?\s*(?:г|лет|years?)", normalized)
    if single:
        value = float(single.group(1).replace(",", "."))
        return value, value

    return None, None


def _extract_label_value(text: str, field: str) -> tuple[str | None, str]:
    for pattern in LABEL_PATTERNS.get(field, []):
        match = pattern.search(text)
        if match:
            value = _normalize_whitespace(match.group(1))
            if value:
                return value, "rule_label"
    return None, "missing"


def _extract_medium_city(text: str) -> tuple[str | None, str]:
    if re.search(r"(?i)(?:#алматы|\bалматы\b|\balmaty\b)", text):
        return "almaty", "regex_in_text"
    if re.search(r"(?i)(?:#астана|\bастана\b|\bastana\b|\bnur-sultan\b)", text):
        return "astana", "regex_in_text"
    return None, "missing"


def _extract_medium_work_format(text: str) -> tuple[str | None, str]:
    normalized = _normalize_whitespace(text).lower()
    if any(term in normalized for term in ["удаленный/гибрид", "удалённый/гибрид", "remote/hybrid"]):
        return "hybrid", "regex_in_text"
    value = _normalize_work_format(normalized)
    return (value, "regex_in_text") if value else (None, "missing")


def _extract_medium_employment(text: str) -> tuple[str | None, str]:
    value = _normalize_employment(text)
    return (value, "regex_in_text") if value else (None, "missing")


def _extract_medium_salary(text: str) -> tuple[str | None, int | None, int | None, str | None, str]:
    keyword_match = re.search(
        r"(?i)(?:зарплата|salary)[^\n]{0,80}",
        text,
    )
    currency_match = re.search(
        r"(?i)(?:от|до)?\s*\d[\d\s]*(?:\s*[-–—]\s*\d[\d\s]*)?\s*(?:₸|тг|тенге|usd|\$|eur|€|rub|rur|руб)\b",
        text,
    )
    candidate = keyword_match.group(0) if keyword_match else (currency_match.group(0) if currency_match else None)
    if candidate:
        raw, salary_from, salary_to, currency = _parse_salary_text(candidate)
        numeric_values = [value for value in [salary_from, salary_to] if value is not None]
        if numeric_values and max(numeric_values) < 1000 and currency is None:
            return None, None, None, None, "missing"
        if any(item is not None for item in [raw, salary_from, salary_to, currency]):
            return raw, salary_from, salary_to, currency, "regex_in_text"
    return None, None, None, None, "missing"


def _extract_medium_experience(text: str) -> tuple[float | None, float | None, str]:
    experience_match = re.search(
        r"(?i)(?:опыт(?: работы)?|experience).{0,20}?(\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?)\s*(?:\+)?\s*(?:г|лет|years?)",
        text,
    )
    if experience_match:
        experience_min, experience_max = _parse_experience_text(experience_match.group(0))
        if experience_min is not None or experience_max is not None:
            return experience_min, experience_max, "regex_in_text"
    return None, None, "missing"


def _build_prefill_with_meta(text: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    raw_text = text or ""
    prefill = {field: None for field in PREFILL_FIELDS}
    meta = {
        field: {"value": None, "source": "missing", "confidence": "missing"}
        for field in PREFILL_FIELDS
    }

    company_value, company_source = _extract_label_value(raw_text, "company")
    if company_value:
        prefill["company"] = company_value
        meta["company"] = {"value": company_value, "source": company_source, "confidence": "high_confidence"}

    city_value, city_source = _extract_label_value(raw_text, "city")
    normalized_city = _normalize_city(city_value)
    if normalized_city:
        prefill["city"] = normalized_city
        meta["city"] = {"value": normalized_city, "source": "normalized_label", "confidence": "high_confidence"}
    else:
        city_value, city_source = _extract_medium_city(raw_text)
        if city_value:
            prefill["city"] = city_value
            meta["city"] = {"value": city_value, "source": city_source, "confidence": "medium_confidence"}

    employment_value, employment_source = _extract_label_value(raw_text, "employment")
    normalized_employment = _normalize_employment(employment_value)
    if normalized_employment:
        prefill["employment"] = normalized_employment
        meta["employment"] = {
            "value": normalized_employment,
            "source": "normalized_label",
            "confidence": "high_confidence",
        }
    else:
        employment_value, employment_source = _extract_medium_employment(raw_text)
        if employment_value:
            prefill["employment"] = employment_value
            meta["employment"] = {"value": employment_value, "source": employment_source, "confidence": "medium_confidence"}

    work_format_value, work_format_source = _extract_label_value(raw_text, "work_format")
    normalized_work_format = _normalize_work_format(work_format_value)
    if normalized_work_format:
        prefill["work_format"] = normalized_work_format
        meta["work_format"] = {
            "value": normalized_work_format,
            "source": "normalized_label",
            "confidence": "high_confidence",
        }
    else:
        work_format_value, work_format_source = _extract_medium_work_format(raw_text)
        if work_format_value:
            prefill["work_format"] = work_format_value
            meta["work_format"] = {
                "value": work_format_value,
                "source": work_format_source,
                "confidence": "medium_confidence",
            }

    salary_label_value, salary_source = _extract_label_value(raw_text, "salary_raw")
    salary_raw, salary_from, salary_to, currency = _parse_salary_text(salary_label_value)
    if any(value is not None for value in [salary_raw, salary_from, salary_to, currency]):
        prefill["salary_raw"] = salary_raw
        prefill["salary_from"] = salary_from
        prefill["salary_to"] = salary_to
        prefill["currency"] = currency
        for field, value in {
            "salary_raw": salary_raw,
            "salary_from": salary_from,
            "salary_to": salary_to,
            "currency": currency,
        }.items():
            if value is not None:
                meta[field] = {"value": value, "source": "rule_label", "confidence": "high_confidence"}
    else:
        salary_raw, salary_from, salary_to, currency, salary_source = _extract_medium_salary(raw_text)
        for field, value in {
            "salary_raw": salary_raw,
            "salary_from": salary_from,
            "salary_to": salary_to,
            "currency": currency,
        }.items():
            if value is not None:
                prefill[field] = value
                meta[field] = {"value": value, "source": salary_source, "confidence": "medium_confidence"}

    experience_value, experience_source = _extract_label_value(raw_text, "experience")
    experience_min, experience_max = _parse_experience_text(experience_value)
    if experience_min is not None or experience_max is not None:
        prefill["experience_min"] = experience_min
        prefill["experience_max"] = experience_max
        if experience_min is not None:
            meta["experience_min"] = {"value": experience_min, "source": "rule_label", "confidence": "high_confidence"}
        if experience_max is not None:
            meta["experience_max"] = {"value": experience_max, "source": "rule_label", "confidence": "high_confidence"}
    else:
        experience_min, experience_max, experience_source = _extract_medium_experience(raw_text)
        if experience_min is not None:
            prefill["experience_min"] = experience_min
            meta["experience_min"] = {
                "value": experience_min,
                "source": experience_source,
                "confidence": "medium_confidence",
            }
        if experience_max is not None:
            prefill["experience_max"] = experience_max
            meta["experience_max"] = {
                "value": experience_max,
                "source": experience_source,
                "confidence": "medium_confidence",
            }

    return prefill, meta


def telegram_prefill_extract(text: str) -> dict[str, Any]:
    """Extract conservative Telegram parser-first fields from raw text."""
    prefill, _ = _build_prefill_with_meta(text)
    return prefill


def telegram_prefill_quality(prefill: dict[str, Any], text: str) -> dict[str, dict[str, Any]]:
    """Return per-field parser provenance and confidence for Telegram prefill."""
    rebuilt_prefill, meta = _build_prefill_with_meta(text)
    for field in PREFILL_FIELDS:
        if prefill.get(field) != rebuilt_prefill.get(field) and not _is_missing(prefill.get(field)):
            meta[field] = {
                "value": prefill.get(field),
                "source": "regex_in_text",
                "confidence": "medium_confidence",
            }
    return meta


def compact_parser_hints(parser_quality: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Drop missing parser hints before sending them into the LLM prompt."""
    return {
        field: meta
        for field, meta in parser_quality.items()
        if meta.get("confidence") != "missing" and meta.get("value") is not None
    }


def _values_equal(left: Any, right: Any) -> bool:
    if _is_missing(left) and _is_missing(right):
        return True
    if isinstance(left, list) or isinstance(right, list):
        left_list = left if isinstance(left, list) else ([] if _is_missing(left) else [left])
        right_list = right if isinstance(right, list) else ([] if _is_missing(right) else [right])
        return left_list == right_list
    if isinstance(left, str) and isinstance(right, str):
        return _normalize_whitespace(left).lower() == _normalize_whitespace(right).lower()
    return left == right


def reconcile_prefill_and_llm(prefill: dict[str, dict[str, Any]], llm_result: dict[str, Any]) -> dict[str, Any]:
    """
    Reconcile parser hints and LLM output using field-aware merge policy.

    Returns a dict with final values and metadata maps:
    - final_field_sources
    - final_field_confidence
    - review_flags
    - conflict_flags
    """

    final_result = dict(llm_result)
    final_sources: dict[str, str] = {}
    final_confidence: dict[str, str] = {}
    review_flags: list[str] = []
    conflict_flags: list[str] = []

    all_fields = set(PREFILL_FIELDS) | LLM_FIRST_FIELDS | HYBRID_FIELDS | {"english_mention", "english_level"}

    for field in all_fields:
        parser_meta = prefill.get(field, {"value": None, "source": "missing", "confidence": "missing"})
        parser_value = parser_meta.get("value")
        parser_confidence = parser_meta.get("confidence", "missing")
        llm_value = llm_result.get(field)

        chosen_value = llm_value
        chosen_source = "llm_semantic" if not _is_missing(llm_value) else "missing"
        chosen_confidence = "medium_confidence" if not _is_missing(llm_value) else "missing"

        if field in PARSER_FIRST_FIELDS:
            if parser_confidence == "high_confidence":
                chosen_value = parser_value
                chosen_source = parser_meta.get("source", "rule_label")
                chosen_confidence = "high_confidence"
                if not _is_missing(llm_value) and not _values_equal(parser_value, llm_value):
                    conflict_flags.append(field)
                    review_flags.append(field)
            elif parser_confidence == "medium_confidence":
                chosen_value = parser_value if _is_missing(llm_value) or not _values_equal(parser_value, llm_value) else llm_value
                chosen_source = parser_meta.get("source", "regex_in_text")
                chosen_confidence = "medium_confidence"
                if not _is_missing(llm_value):
                    if _values_equal(parser_value, llm_value):
                        chosen_source = "parser_confirmed_by_llm"
                        chosen_confidence = "high_confidence"
                    else:
                        conflict_flags.append(field)
                        review_flags.append(field)
            elif not _is_missing(llm_value):
                chosen_value = llm_value
                chosen_source = "llm_semantic"
                chosen_confidence = "medium_confidence"

        elif field in LLM_FIRST_FIELDS:
            if not _is_missing(llm_value):
                chosen_value = llm_value
                chosen_source = "llm_semantic"
                chosen_confidence = "medium_confidence"
            elif parser_confidence != "missing":
                chosen_value = parser_value
                chosen_source = parser_meta.get("source", "missing")
                chosen_confidence = parser_confidence

        elif field in HYBRID_FIELDS:
            if field == "title_normalized":
                if not _is_missing(llm_value):
                    chosen_value = llm_value
                    chosen_source = "llm_semantic"
                    chosen_confidence = "medium_confidence"
            else:
                if parser_confidence == "high_confidence":
                    chosen_value = parser_value
                    chosen_source = parser_meta.get("source", "rule_label")
                    chosen_confidence = "high_confidence"
                    if not _is_missing(llm_value) and not _values_equal(parser_value, llm_value):
                        conflict_flags.append(field)
                        review_flags.append(field)
                elif parser_confidence == "medium_confidence":
                    if _is_missing(llm_value):
                        chosen_value = parser_value
                        chosen_source = parser_meta.get("source", "regex_in_text")
                        chosen_confidence = "medium_confidence"
                    elif _values_equal(parser_value, llm_value):
                        chosen_value = llm_value
                        chosen_source = "parser_confirmed_by_llm"
                        chosen_confidence = "high_confidence"
                    else:
                        chosen_value = parser_value
                        chosen_source = parser_meta.get("source", "regex_in_text")
                        chosen_confidence = "medium_confidence"
                        conflict_flags.append(field)
                        review_flags.append(field)
                elif not _is_missing(llm_value):
                    chosen_value = llm_value
                    chosen_source = "llm_semantic"
                    chosen_confidence = "medium_confidence"

        final_result[field] = chosen_value
        final_sources[field] = chosen_source
        final_confidence[field] = chosen_confidence

    final_result["review_flags"] = sorted(set(review_flags))
    final_result["conflict_flags"] = sorted(set(conflict_flags))
    final_result["final_field_sources"] = final_sources
    final_result["final_field_confidence"] = final_confidence
    return final_result


def validate_final_telegram_record(record: dict[str, Any]) -> dict[str, Any]:
    """
    Post-validate reconciled Telegram extraction.

    Returns validated record with:
    - validation_fixes
    - possibly updated review_flags
    """

    validated = dict(record)
    fixes: list[str] = list(validated.get("validation_fixes", []) or [])
    review_flags = set(validated.get("review_flags", []) or [])

    salary_from = validated.get("salary_from")
    salary_to = validated.get("salary_to")
    if salary_from is not None and salary_from < 0:
        validated["salary_from"] = None
        fixes.append("salary_from_negative_to_null")
    if salary_to is not None and salary_to < 0:
        validated["salary_to"] = None
        fixes.append("salary_to_negative_to_null")
    if validated.get("salary_from") is not None and validated.get("salary_to") is not None:
        if validated["salary_from"] > validated["salary_to"]:
            validated["salary_from"], validated["salary_to"] = validated["salary_to"], validated["salary_from"]
            fixes.append("salary_range_swapped")

    validated["currency"] = _normalize_currency(validated.get("currency")) or None
    if validated.get("salary_raw") and validated.get("currency") is None:
        _, _, _, normalized_currency = _parse_salary_text(validated["salary_raw"])
        if normalized_currency:
            validated["currency"] = normalized_currency
            fixes.append("currency_normalized_from_salary_raw")

    english_mention = validated.get("english_mention")
    if english_mention is False:
        if validated.get("english_level") not in {None, "unknown"}:
            validated["english_level"] = None
            fixes.append("english_level_reset_without_mention")
        if validated.get("english_required") not in {None, False}:
            validated["english_required"] = False
            fixes.append("english_required_reset_without_mention")
    if validated.get("english_level") not in {None, "a1", "a2", "b1", "b2", "c1", "c2", "unknown"}:
        validated["english_level"] = None
        fixes.append("english_level_out_of_enum")

    if validated.get("employment") not in {"full_time", "part_time", "contract", "internship", "temporary", "unknown", None}:
        validated["employment"] = "unknown"
        fixes.append("employment_out_of_enum")
    if validated.get("work_format") not in {"office", "remote", "hybrid", "unknown", None}:
        validated["work_format"] = "unknown"
        fixes.append("work_format_out_of_enum")

    normalized_city = _normalize_city(validated.get("city"))
    if normalized_city and normalized_city != validated.get("city"):
        validated["city"] = normalized_city
        fixes.append("city_normalized")

    experience_min = validated.get("experience_min")
    experience_max = validated.get("experience_max")
    if experience_min is not None and experience_min < 0:
        validated["experience_min"] = None
        fixes.append("experience_min_negative_to_null")
    if experience_max is not None and experience_max < 0:
        validated["experience_max"] = None
        fixes.append("experience_max_negative_to_null")
    if validated.get("experience_min") is not None and validated.get("experience_max") is not None:
        if validated["experience_min"] > validated["experience_max"]:
            validated["experience_min"], validated["experience_max"] = validated["experience_max"], validated["experience_min"]
            fixes.append("experience_range_swapped")

    for field in ["hard_skills", "soft_skills", "tech_stack"]:
        value = validated.get(field)
        if value is None:
            validated[field] = []
            continue
        if not isinstance(value, list):
            value = [value]
            fixes.append(f"{field}_wrapped_to_list")
        cleaned = []
        seen = set()
        for item in value:
            text = _normalize_whitespace(str(item))
            if not text:
                continue
            key = text.lower()
            if key not in seen:
                seen.add(key)
                cleaned.append(text)
        if cleaned != value:
            fixes.append(f"{field}_deduplicated")
        validated[field] = cleaned

    if validated.get("employment") == "internship" and validated.get("level") not in {None, "intern", "junior", "unknown"}:
        review_flags.add("internship_level_consistency")
        fixes.append("internship_level_review")

    validated["review_flags"] = sorted(review_flags)
    validated["validation_fixes"] = sorted(set(fixes))
    return validated
