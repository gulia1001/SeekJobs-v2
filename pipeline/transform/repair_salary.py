from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


BASE_PATH = Path(__file__).resolve().parents[1]  # pipeline/
DATA_DIR = BASE_PATH / "data"
INPUT_DATASET_PATH = DATA_DIR / "final" / "analysis_ready_jobs.csv"
OUTPUT_DATASET_PATH = DATA_DIR / "final" / "analysis_ready_jobs_salary_fixed_v3.csv"
OUTPUT_SALARY_MART_PATH = DATA_DIR / "final" / "jobs_salary_clean_v3.csv"
OUTPUT_MANUAL_REVIEW_PATH = DATA_DIR / "final" / "salary_manual_review_cases_v3.csv"
OUTPUT_SUMMARY_PATH = DATA_DIR / "reports" / "salary_repair_summary_v3.json"

VALID_CURRENCY_VALUES = {"KZT", "USD", "EUR", "RUB", "KGS", "GBP"}
SALARY_OUTLIER_THRESHOLD = 10_000_000

SALARY_BOUNDARY_PATTERN = re.compile(
    r"(?i)\b(company|requirements|responsibilities|about|english|location|format|experience|skills|contacts?|"
    r"компания|требован|обязанност|формат|город|опыт|навык|контакт|резюме|почта|email|e-mail)\b|https?://|www\.|@\w+"
)
SALARY_KEYWORD_PATTERN = re.compile(r"(?i)\b(зарплата|salary|оклад|salary range|salary fork|salary estimate)\b")
SALARY_CONTEXT_PATTERN = re.compile(r"(?i)\b(зарплата|salary|оклад|salary range|salary fork|salary estimate|зп|на руки|gross|net|тенге|usd|eur|gbp|руб|₸|\$|€|£)\b")
CONTACT_KEYWORD_PATTERN = re.compile(
    r"(?i)\b(контакт[ыа]?|contact|contacts|whatsapp|telegram|tg|phone|tel|direct|email|e-mail|send cv|resume|резюме)\b"
)
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\-\s()]{8,}\d)(?!\d)")
RANGE_SEPARATOR_PATTERN = re.compile(r"[-–—]|\bto\b|\bдо\b", flags=re.IGNORECASE)
LOWER_BOUND_PATTERN = re.compile(r"\b(from|от|starting from|upwards of)\b", flags=re.IGNORECASE)
UPPER_BOUND_PATTERN = re.compile(r"\b(to|до|up to|не более)\b", flags=re.IGNORECASE)


def normalize_whitespace(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def is_meaningful_text(value: Any, min_len: int = 2) -> bool:
    text = normalize_whitespace(value)
    return bool(text) and text.lower() not in {"", "unknown", "none", "null", "nan", "n/a", "na"} and len(text) >= min_len


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "cp1251"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"Unable to read {path}") from last_error


def json_dumps_or_na(value: Any) -> Any:
    if value in (None, [], {}, ""):
        return pd.NA
    return json.dumps(value, ensure_ascii=False)


def numeric_or_none(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class AmountToken:
    value: float
    raw: str
    unit_multiplier: int
    explicit_unit: bool
    start: int
    end: int


@dataclass(slots=True)
class ParsedSalaryCandidate:
    salary_from: float | None
    salary_to: float | None
    parse_quality: str
    period: str | None
    confidence: str
    manual_review_flag: bool
    manual_review_category: str | None
    candidate_from: float | None
    candidate_to: float | None


@dataclass(slots=True)
class SalaryRepairResult:
    salary_from_clean: float | None
    salary_to_clean: float | None
    salary_avg_clean: float | None
    currency_clean: str | None
    salary_parse_quality: str
    salary_is_suspicious: bool
    salary_outlier_flag: bool
    salary_contact_leak_flag: bool
    salary_zero_flag: bool
    salary_usable_for_analytics: bool
    salary_fix_flags: list[str]
    salary_parse_source: str
    salary_period: str | None
    salary_source_basis_v2: str
    salary_source_conflict_flag: bool
    salary_manual_review_flag: bool
    salary_manual_review_category: str | None
    salary_from_candidate_v2: float | None
    salary_to_candidate_v2: float | None


def trim_salary_clause(text: str, *, max_len: int = 220) -> str:
    normalized = normalize_whitespace(text)
    if not normalized:
        return ""
    sentence_boundary = re.search(r"[.!?](?:\s|$)", normalized)
    if sentence_boundary and sentence_boundary.start() > 10:
        normalized = normalized[: sentence_boundary.start()].strip(" ,;:-")
    boundary_match = SALARY_BOUNDARY_PATTERN.search(normalized)
    if boundary_match and boundary_match.start() > 12:
        normalized = normalized[: boundary_match.start()].strip(" ,;:-")
    return normalized[:max_len].strip(" ,;:-")


def extract_salary_candidate_text(row: pd.Series) -> tuple[str, str]:
    salary_raw = row.get("salary_raw")
    if is_meaningful_text(salary_raw):
        return trim_salary_clause(str(salary_raw)), "salary_raw"

    for field_name in ["description_clean_v2", "description"]:
        value = row.get(field_name)
        if not is_meaningful_text(value, min_len=20):
            continue
        text = normalize_whitespace(value)
        keyword_match = SALARY_KEYWORD_PATTERN.search(text)
        if keyword_match:
            snippet = text[keyword_match.start() : keyword_match.start() + 220]
            trimmed = trim_salary_clause(snippet)
            if re.search(r"\d", trimmed) and SALARY_CONTEXT_PATTERN.search(trimmed):
                return trimmed, f"{field_name}_salary_keyword"
        currency_match = re.search(
            r"(?i)(?:[$€£₸]|usd|eur|gbp|kzt|тг|тенге|руб)[^\n]{0,80}\d|\d[^\n]{0,80}(?:[$€£₸]|usd|eur|gbp|kzt|тг|тенге|руб)",
            text,
        )
        if currency_match:
            window_start = max(0, currency_match.start() - 40)
            window_end = min(len(text), currency_match.end() + 80)
            snippet = text[window_start:window_end]
            trimmed = trim_salary_clause(snippet)
            if SALARY_CONTEXT_PATTERN.search(trimmed):
                return trimmed, f"{field_name}_currency_pattern"
    return "", "missing"


def normalize_currency(value: Any, fallback_text: str = "") -> str | pd._libs.missing.NAType:
    candidates = [normalize_whitespace(value).upper(), normalize_whitespace(fallback_text).upper()]
    joined = " ".join(part for part in candidates if part)
    if not joined:
        return pd.NA
    if any(token in joined for token in ["KZT", "₸", "ТГ", "ТЕНГЕ"]):
        return "KZT"
    if any(token in joined for token in ["USD", "$"]):
        return "USD"
    if any(token in joined for token in ["EUR", "€"]):
        return "EUR"
    if any(token in joined for token in ["GBP", "£"]):
        return "GBP"
    if any(token in joined for token in ["RUB", "RUR", "РУБ", "₽"]):
        return "RUB"
    if "KGS" in joined:
        return "KGS"
    return pd.NA


def looks_like_phone_number(value: Any) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    digits = re.sub(r"\D", "", str(value))
    return len(digits) in {10, 11} and digits.startswith(("7", "8"))


def has_explicit_contact_signal(text: str) -> bool:
    normalized = normalize_whitespace(text)
    if not normalized:
        return False
    if EMAIL_PATTERN.search(normalized):
        return True
    phone_match = PHONE_PATTERN.search(normalized)
    if phone_match and (CONTACT_KEYWORD_PATTERN.search(normalized) or "+" in phone_match.group(0)):
        return True
    return bool(CONTACT_KEYWORD_PATTERN.search(normalized) and phone_match)


def _normalize_numeric_token(number_text: str) -> float | None:
    cleaned = re.sub(r"[€$£₸]", "", number_text).replace("\xa0", " ").strip()
    cleaned = re.sub(r"(?<=\d)\s+(?=\d{3}(\D|$))", "", cleaned)
    compact = cleaned.replace(" ", "")
    if not compact:
        return None

    if "," in compact and "." in compact:
        last_comma = compact.rfind(",")
        last_dot = compact.rfind(".")
        decimal_sep = "," if last_comma > last_dot else "."
        thousands_sep = "." if decimal_sep == "," else ","
        if re.fullmatch(rf"\d{{1,3}}(?:\{thousands_sep}\d{{3}})+(?:\{decimal_sep}\d{{1,2}})?", compact):
            normalized = compact.replace(thousands_sep, "")
            if decimal_sep == ",":
                normalized = normalized.replace(",", ".")
            return float(normalized)
        return float(compact.replace(",", "").replace(".", ""))

    if "," in compact:
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", compact):
            return float(compact.replace(",", ""))
        if re.fullmatch(r"\d+,\d{1,2}", compact):
            return float(compact.replace(",", "."))
        if compact.count(",") == 1 and len(compact.split(",")[1]) == 3:
            return float(compact.replace(",", ""))
        return float(compact.replace(",", ""))

    if "." in compact:
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", compact):
            return float(compact.replace(".", "").replace(",", "."))
        if re.fullmatch(r"\d+\.\d{1,2}", compact):
            return float(compact)
        if compact.count(".") == 1 and len(compact.split(".")[1]) == 3:
            return float(compact.replace(".", ""))
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", compact):
            return float(compact.replace(".", ""))
        return float(compact.replace(".", ""))

    return float(compact)


def unit_multiplier_from_text(unit_text: str) -> int:
    unit = normalize_whitespace(unit_text).lower().rstrip(".")
    if unit in {"млн", "миллион", "миллиона", "миллионов", "million", "mln", "m"}:
        return 1_000_000
    if unit in {"k", "к", "тыс", "тысяч", "thousand"}:
        return 1_000
    return 1


def sanitize_salary_amount(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0:
        return None
    if value > SALARY_OUTLIER_THRESHOLD:
        return None
    return float(value)


def detect_salary_periods(text: str) -> set[str]:
    normalized = normalize_whitespace(text).lower()
    periods: set[str] = set()
    if re.search(r"(?i)(per hour|/ ?hour|в ?час|/ ?час|hourly|в час)", normalized):
        periods.add("hour")
    if re.search(r"(?i)(per day|/ ?day|p/day|в день|за день|daily)", normalized):
        periods.add("day")
    if re.search(r"(?i)(per year|per annum|/ ?year|год(?:овых|овая|овой)?|в год|annual|annum)", normalized):
        periods.add("year")
    if re.search(r"(?i)(per month|/ ?month|/ ?mo\b|/ ?мес|в месяц|monthly|month)", normalized):
        periods.add("month")
    return periods


def extract_amount_tokens(text: str) -> list[AmountToken]:
    amount_pattern = re.compile(
        r"([€$£₸]?\s*\d[\d\s\xa0.,]{0,18}\d|\d)(?:\s*(млн\.?|миллион(?:а|ов)?|million|mln|тыс\.?|тысяч|thousand|k(?![a-z])|к(?![а-яa-z])|m(?![a-z])))?",
        flags=re.IGNORECASE,
    )
    provisional_tokens: list[AmountToken] = []

    for match in amount_pattern.finditer(text):
        number_text, unit_text = match.groups()
        parsed = _normalize_numeric_token(number_text)
        if parsed is None:
            continue
        multiplier = unit_multiplier_from_text(unit_text or "")
        value = float(parsed * multiplier)
        digits_only = re.sub(r"\D", "", str(number_text))
        if len(digits_only) in {10, 11} and digits_only.startswith(("7", "8")) and multiplier == 1:
            continue
        if value <= 0:
            continue
        provisional_tokens.append(
            AmountToken(
                value=value,
                raw=match.group(0),
                unit_multiplier=multiplier,
                explicit_unit=multiplier > 1,
                start=match.start(),
                end=match.end(),
            )
        )
    if not provisional_tokens:
        return []

    tokens_with_inferred_units: list[AmountToken] = []
    for idx, token in enumerate(provisional_tokens):
        if token.explicit_unit or token.value >= 10_000:
            tokens_with_inferred_units.append(token)
            continue

        inferred_multiplier = 1
        adjacent_candidates: list[int] = []
        for neighbor_idx in (idx - 1, idx + 1):
            if not (0 <= neighbor_idx < len(provisional_tokens)):
                continue
            neighbor = provisional_tokens[neighbor_idx]
            if not neighbor.explicit_unit or neighbor.unit_multiplier <= 1:
                continue
            left = token.end if neighbor_idx > idx else neighbor.end
            right = neighbor.start if neighbor_idx > idx else token.start
            between = normalize_whitespace(text[left:right]).lower()
            if RANGE_SEPARATOR_PATTERN.search(between) or between in {"", "and", "&", ",", "/"}:
                adjacent_candidates.append(neighbor.unit_multiplier)

        if adjacent_candidates:
            inferred_multiplier = max(adjacent_candidates)
            base_value = _normalize_numeric_token(token.raw) or token.value
            if inferred_multiplier == 1_000_000 and base_value >= 100:
                inferred_multiplier = 1_000
            inferred_value = float(base_value * inferred_multiplier)
            if inferred_value > 0:
                token = AmountToken(
                    value=inferred_value,
                    raw=token.raw,
                    unit_multiplier=inferred_multiplier,
                    explicit_unit=False,
                    start=token.start,
                    end=token.end,
                )
        tokens_with_inferred_units.append(token)

    combined_tokens: list[AmountToken] = []
    idx = 0
    while idx < len(tokens_with_inferred_units):
        token = tokens_with_inferred_units[idx]
        if idx + 1 < len(tokens_with_inferred_units):
            next_token = tokens_with_inferred_units[idx + 1]
            between = normalize_whitespace(text[token.end : next_token.start]).lower()
            if (
                token.explicit_unit
                and next_token.explicit_unit
                and token.unit_multiplier == 1_000_000
                and next_token.unit_multiplier == 1_000
                and not RANGE_SEPARATOR_PATTERN.search(between)
                and re.fullmatch(r"[\s,./+()a-zа-я-]*", between)
            ):
                combined_value = token.value + next_token.value
                combined_tokens.append(
                    AmountToken(
                        value=combined_value,
                        raw=f"{token.raw} {next_token.raw}",
                        unit_multiplier=1_000_000,
                        explicit_unit=True,
                        start=token.start,
                        end=next_token.end,
                    )
                )
                idx += 2
                continue
        combined_tokens.append(token)
        idx += 1
    return combined_tokens


def sanitize_existing_numeric(value: Any) -> tuple[float | None, list[str]]:
    flags: list[str] = []
    numeric = numeric_or_none(value)
    if numeric is None:
        return None, flags
    if math.isclose(numeric, 0.0):
        flags.append("zero_value_removed")
        return None, flags
    if looks_like_phone_number(int(numeric)):
        flags.append("phone_like_numeric_removed")
        return None, flags
    if numeric > SALARY_OUTLIER_THRESHOLD:
        flags.append("outlier_numeric_removed")
        return None, flags
    return float(numeric), flags


def classify_manual_review(text: str, tokens: list[AmountToken], periods: set[str]) -> tuple[bool, str | None]:
    normalized = normalize_whitespace(text).lower()
    if has_explicit_contact_signal(text):
        return True, "contact_or_noise"
    if len(periods) > 1:
        return True, "mixed_salary_periods"
    if len(tokens) >= 3 and re.search(r"(?i)\b(bonus|allowance|equity|stock|kpi|gross \+|net \+|преми|бонус)\b", normalized):
        return True, "base_salary_plus_bonus_mix"
    if re.search(r"(?i)\b(junior|middle|senior|lead|intern|part-time|full-time|contract|day|hour|year|annum)\b", normalized) and re.search(r"(?i)(?:\bor\b|или|/)", normalized) and len(tokens) >= 2:
        return True, "multi_variant_compensation"
    if len(tokens) > 2:
        return True, "too_many_amounts"
    return False, None


def infer_parse_quality(text: str, tokens: list[AmountToken]) -> str:
    normalized = normalize_whitespace(text).lower()
    if len(tokens) >= 2 and RANGE_SEPARATOR_PATTERN.search(normalized):
        return "parsed_range_v2"
    if len(tokens) == 1 and LOWER_BOUND_PATTERN.search(normalized):
        return "parsed_lower_bound_v2"
    if len(tokens) == 1 and UPPER_BOUND_PATTERN.search(normalized):
        return "parsed_upper_bound_v2"
    if len(tokens) == 1:
        return "parsed_single_v2"
    if len(tokens) >= 2:
        return "parsed_range_v2"
    return "missing"


def parse_salary_candidate(text: str) -> ParsedSalaryCandidate:
    normalized = normalize_whitespace(text)
    if not normalized:
        return ParsedSalaryCandidate(None, None, "missing", None, "none", False, None, None, None)

    periods = detect_salary_periods(normalized)
    tokens = extract_amount_tokens(normalized)
    manual_review_flag, manual_review_category = classify_manual_review(normalized, tokens, periods)

    if not tokens:
        if manual_review_flag:
            return ParsedSalaryCandidate(None, None, "manual_review_complex_v2", next(iter(periods), None), "low", True, manual_review_category, None, None)
        return ParsedSalaryCandidate(None, None, "missing", next(iter(periods), None), "none", False, None, None, None)

    parse_quality = infer_parse_quality(normalized, tokens)
    period = next(iter(periods), None) if len(periods) == 1 else None
    confidence = "high" if parse_quality == "parsed_range_v2" and not manual_review_flag else "medium"

    candidate_from: float | None = None
    candidate_to: float | None = None
    if parse_quality == "parsed_range_v2" and len(tokens) >= 2:
        candidate_from = min(tokens[0].value, tokens[1].value)
        candidate_to = max(tokens[0].value, tokens[1].value)
    elif parse_quality == "parsed_lower_bound_v2":
        candidate_from = tokens[0].value
    elif parse_quality == "parsed_upper_bound_v2":
        candidate_to = tokens[0].value
    elif parse_quality == "parsed_single_v2":
        candidate_from = tokens[0].value

    candidate_from = sanitize_salary_amount(candidate_from)
    candidate_to = sanitize_salary_amount(candidate_to)

    if candidate_from is not None and candidate_to is not None and candidate_from > candidate_to:
        candidate_from, candidate_to = candidate_to, candidate_from

    if manual_review_flag:
        return ParsedSalaryCandidate(
            None,
            None,
            "manual_review_complex_v2",
            period,
            "low",
            True,
            manual_review_category,
            candidate_from,
            candidate_to,
        )

    return ParsedSalaryCandidate(
        candidate_from,
        candidate_to,
        parse_quality,
        period,
        confidence,
        False,
        None,
        candidate_from,
        candidate_to,
    )


def values_conflict_major(
    parsed_from: float | None,
    parsed_to: float | None,
    existing_from: float | None,
    existing_to: float | None,
) -> bool:
    parsed_values = [value for value in [parsed_from, parsed_to] if value is not None]
    existing_values = [value for value in [existing_from, existing_to] if value is not None]
    if not parsed_values or not existing_values:
        return False
    parsed_anchor = sum(parsed_values) / len(parsed_values)
    existing_anchor = sum(existing_values) / len(existing_values)
    if parsed_anchor <= 0 or existing_anchor <= 0:
        return False
    ratio = max(parsed_anchor, existing_anchor) / min(parsed_anchor, existing_anchor)
    return ratio >= 20


def make_salary_avg(salary_from: float | None, salary_to: float | None) -> float | None:
    if salary_from is not None and salary_to is not None:
        return float((salary_from + salary_to) / 2)
    if salary_from is not None:
        return float(salary_from)
    if salary_to is not None:
        return float(salary_to)
    return None


def build_salary_repair_result(row: pd.Series) -> SalaryRepairResult:
    raw_text, parse_source = extract_salary_candidate_text(row)
    currency_clean = normalize_currency(row.get("currency_clean"), raw_text)
    if currency_clean is pd.NA:
        currency_clean = normalize_currency(row.get("currency"), raw_text)

    existing_from, existing_from_flags = sanitize_existing_numeric(row.get("salary_from"))
    existing_to, existing_to_flags = sanitize_existing_numeric(row.get("salary_to"))
    legacy_zero_flag = "zero_value_removed" in existing_from_flags + existing_to_flags
    legacy_outlier_flag = "outlier_numeric_removed" in existing_from_flags + existing_to_flags
    fix_flags = list(existing_from_flags + existing_to_flags)

    parsed = parse_salary_candidate(raw_text)
    if (
        parse_source != "salary_raw"
        and (parsed.salary_from is not None or parsed.salary_to is not None)
        and currency_clean not in VALID_CURRENCY_VALUES
    ):
        fix_flags.append("description_parse_without_currency_ignored")
        parsed = ParsedSalaryCandidate(
            salary_from=None,
            salary_to=None,
            parse_quality="missing",
            period=parsed.period,
            confidence="none",
            manual_review_flag=False,
            manual_review_category=None,
            candidate_from=parsed.candidate_from,
            candidate_to=parsed.candidate_to,
        )
    if (
        parse_source.endswith("currency_pattern")
        and parsed.parse_quality == "parsed_single_v2"
        and (parsed.salary_from is not None or parsed.salary_to is not None)
    ):
        fix_flags.append("single_value_description_currency_pattern_sent_to_review")
        parsed = ParsedSalaryCandidate(
            salary_from=None,
            salary_to=None,
            parse_quality="manual_review_complex_v2",
            period=parsed.period,
            confidence="low",
            manual_review_flag=True,
            manual_review_category="single_value_description_currency_pattern",
            candidate_from=parsed.candidate_from,
            candidate_to=parsed.candidate_to,
        )
    source_conflict_flag = values_conflict_major(
        parsed.salary_from,
        parsed.salary_to,
        existing_from,
        existing_to,
    )

    if parsed.manual_review_flag:
        return SalaryRepairResult(
            salary_from_clean=None,
            salary_to_clean=None,
            salary_avg_clean=None,
            currency_clean=currency_clean if currency_clean in VALID_CURRENCY_VALUES else pd.NA,
            salary_parse_quality=parsed.parse_quality,
            salary_is_suspicious=True,
            salary_outlier_flag=legacy_outlier_flag,
            salary_contact_leak_flag=parsed.manual_review_category == "contact_or_noise",
            salary_zero_flag=legacy_zero_flag,
            salary_usable_for_analytics=False,
            salary_fix_flags=sorted(set(fix_flags + ["manual_review_required"])),
            salary_parse_source=parse_source,
            salary_period=parsed.period,
            salary_source_basis_v2="manual_review_queue",
            salary_source_conflict_flag=source_conflict_flag,
            salary_manual_review_flag=True,
            salary_manual_review_category=parsed.manual_review_category,
            salary_from_candidate_v2=parsed.candidate_from,
            salary_to_candidate_v2=parsed.candidate_to,
        )

    salary_from_clean: float | None = None
    salary_to_clean: float | None = None
    salary_source_basis_v2 = "missing"
    salary_parse_quality = parsed.parse_quality
    manual_review_flag = False
    manual_review_category = None

    if parsed.salary_from is not None or parsed.salary_to is not None:
        salary_from_clean = parsed.salary_from
        salary_to_clean = parsed.salary_to
        salary_source_basis_v2 = "text_parsed"
        if source_conflict_flag and parsed.confidence != "high":
            manual_review_flag = True
            manual_review_category = "source_conflict_major"
    elif existing_from is not None or existing_to is not None:
        salary_from_clean = existing_from
        salary_to_clean = existing_to
        salary_source_basis_v2 = "existing_numeric_fallback"
        salary_parse_quality = "existing_numeric_v2"

    if salary_from_clean is not None and salary_to_clean is not None and salary_from_clean > salary_to_clean:
        salary_from_clean, salary_to_clean = salary_to_clean, salary_from_clean
        fix_flags.append("range_swapped_v2")

    outlier_flag = legacy_outlier_flag
    salary_from_clean = sanitize_salary_amount(salary_from_clean)
    salary_to_clean = sanitize_salary_amount(salary_to_clean)
    if salary_from_clean is None and parsed.salary_from is not None:
        outlier_flag = True
        fix_flags.append("salary_from_outlier_removed_v2")
    if salary_to_clean is None and parsed.salary_to is not None:
        outlier_flag = True
        fix_flags.append("salary_to_outlier_removed_v2")
    if salary_from_clean is not None and salary_from_clean > SALARY_OUTLIER_THRESHOLD:
        salary_from_clean = None
        outlier_flag = True
        fix_flags.append("salary_from_outlier_removed_v2")
    if salary_to_clean is not None and salary_to_clean > SALARY_OUTLIER_THRESHOLD:
        salary_to_clean = None
        outlier_flag = True
        fix_flags.append("salary_to_outlier_removed_v2")

    if manual_review_flag:
        return SalaryRepairResult(
            salary_from_clean=None,
            salary_to_clean=None,
            salary_avg_clean=None,
            currency_clean=currency_clean if currency_clean in VALID_CURRENCY_VALUES else pd.NA,
            salary_parse_quality="manual_review_complex_v2",
            salary_is_suspicious=True,
            salary_outlier_flag=outlier_flag,
            salary_contact_leak_flag=False,
            salary_zero_flag=legacy_zero_flag,
            salary_usable_for_analytics=False,
            salary_fix_flags=sorted(set(fix_flags + ["source_conflict_manual_review"])),
            salary_parse_source=parse_source,
            salary_period=parsed.period,
            salary_source_basis_v2="manual_review_queue",
            salary_source_conflict_flag=True,
            salary_manual_review_flag=True,
            salary_manual_review_category=manual_review_category,
            salary_from_candidate_v2=parsed.candidate_from,
            salary_to_candidate_v2=parsed.candidate_to,
        )

    salary_avg_clean = make_salary_avg(salary_from_clean, salary_to_clean)
    zero_flag = legacy_zero_flag and salary_from_clean is None and salary_to_clean is None
    suspicious = bool(outlier_flag or zero_flag)
    usable = bool(
        not suspicious
        and not source_conflict_flag
        and currency_clean in VALID_CURRENCY_VALUES
        and (parsed.period in {None, "month"})
        and (salary_from_clean is not None or salary_to_clean is not None)
    )

    return SalaryRepairResult(
        salary_from_clean=salary_from_clean,
        salary_to_clean=salary_to_clean,
        salary_avg_clean=salary_avg_clean,
        currency_clean=currency_clean if currency_clean in VALID_CURRENCY_VALUES else pd.NA,
        salary_parse_quality=salary_parse_quality if salary_from_clean is not None or salary_to_clean is not None else "missing",
        salary_is_suspicious=suspicious,
        salary_outlier_flag=outlier_flag,
        salary_contact_leak_flag=False,
        salary_zero_flag=zero_flag,
        salary_usable_for_analytics=usable,
        salary_fix_flags=sorted(set(fix_flags)),
        salary_parse_source=parse_source,
        salary_period=parsed.period,
        salary_source_basis_v2=salary_source_basis_v2,
        salary_source_conflict_flag=source_conflict_flag,
        salary_manual_review_flag=False,
        salary_manual_review_category=None,
        salary_from_candidate_v2=parsed.candidate_from,
        salary_to_candidate_v2=parsed.candidate_to,
    )


def build_salary_mart(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "id",
        "source",
        "title_final",
        "company_clean",
        "city_norm",
        "category_filled",
        "level_filled",
        "salary_from_clean",
        "salary_to_clean",
        "salary_avg_clean",
        "currency_clean",
        "salary_period",
        "salary_parse_quality",
        "salary_source_basis_v2",
        "salary_source_conflict_flag",
        "salary_manual_review_flag",
        "salary_manual_review_category",
        "salary_fix_flags",
        "posted_at",
    ]
    mart = df[df["usable_for_salary_analytics"].fillna(False)].copy()
    return mart[columns]


def build_manual_review_mart(df: pd.DataFrame) -> pd.DataFrame:
    review_mask = df["salary_manual_review_flag"].fillna(False)
    columns = [
        "id",
        "source",
        "source_url",
        "title_final",
        "company_clean",
        "city_norm",
        "category_filled",
        "level_filled",
        "salary_raw",
        "salary_from",
        "salary_to",
        "salary_avg",
        "currency",
        "salary_from_candidate_v2",
        "salary_to_candidate_v2",
        "currency_clean",
        "salary_period",
        "salary_parse_quality",
        "salary_parse_source",
        "salary_source_basis_v2",
        "salary_source_conflict_flag",
        "salary_manual_review_category",
        "salary_fix_flags",
        "description_clean_v2",
    ]
    return df.loc[review_mask, columns].copy()


def prepare_salary_repaired_dataset() -> tuple[pd.DataFrame, dict[str, Any]]:
    df = read_csv_with_fallback(INPUT_DATASET_PATH)

    previous_salary_columns = {
        "salary_from_clean_prev": df.get("salary_from_clean"),
        "salary_to_clean_prev": df.get("salary_to_clean"),
        "salary_avg_clean_prev": df.get("salary_avg_clean"),
        "currency_clean_prev": df.get("currency_clean"),
        "salary_parse_quality_prev": df.get("salary_parse_quality"),
    }
    for column, values in previous_salary_columns.items():
        df[column] = values

    repair_results = df.apply(build_salary_repair_result, axis=1)
    df["salary_from_clean"] = [result.salary_from_clean for result in repair_results]
    df["salary_to_clean"] = [result.salary_to_clean for result in repair_results]
    df["salary_avg_clean"] = [result.salary_avg_clean for result in repair_results]
    df["currency_clean"] = [result.currency_clean for result in repair_results]
    df["salary_parse_quality"] = [result.salary_parse_quality for result in repair_results]
    df["salary_is_suspicious"] = [result.salary_is_suspicious for result in repair_results]
    df["salary_outlier_flag"] = [result.salary_outlier_flag for result in repair_results]
    df["salary_contact_leak_flag"] = [result.salary_contact_leak_flag for result in repair_results]
    df["salary_zero_flag"] = [result.salary_zero_flag for result in repair_results]
    df["salary_usable_for_analytics"] = [result.salary_usable_for_analytics for result in repair_results]
    df["salary_fix_flags"] = [json_dumps_or_na(result.salary_fix_flags) for result in repair_results]
    df["salary_parse_source"] = [result.salary_parse_source for result in repair_results]
    df["salary_period"] = [result.salary_period for result in repair_results]
    df["salary_source_basis_v2"] = [result.salary_source_basis_v2 for result in repair_results]
    df["salary_source_conflict_flag"] = [result.salary_source_conflict_flag for result in repair_results]
    df["salary_manual_review_flag"] = [result.salary_manual_review_flag for result in repair_results]
    df["salary_manual_review_category"] = [result.salary_manual_review_category for result in repair_results]
    df["salary_from_candidate_v2"] = [result.salary_from_candidate_v2 for result in repair_results]
    df["salary_to_candidate_v2"] = [result.salary_to_candidate_v2 for result in repair_results]

    if "dedup_keep_for_analytics" in df.columns:
        df["usable_for_salary_analytics"] = df["salary_usable_for_analytics"].fillna(False) & df["dedup_keep_for_analytics"].fillna(False)
    else:
        df["usable_for_salary_analytics"] = df["salary_usable_for_analytics"].fillna(False)

    summary = {
        "input_dataset": str(INPUT_DATASET_PATH),
        "output_dataset": str(OUTPUT_DATASET_PATH),
        "rows": int(len(df)),
        "usable_for_salary_analytics_rows": int(df["usable_for_salary_analytics"].fillna(False).sum()),
        "manual_review_rows": int(df["salary_manual_review_flag"].fillna(False).sum()),
        "source_conflict_rows": int(df["salary_source_conflict_flag"].fillna(False).sum()),
        "salary_period_distribution": df["salary_period"].fillna("unknown").astype(str).value_counts().to_dict(),
        "salary_parse_quality_distribution": df["salary_parse_quality"].fillna("unknown").astype(str).value_counts().to_dict(),
        "manual_review_category_distribution": df["salary_manual_review_category"].fillna("none").astype(str).value_counts().to_dict(),
    }
    return df, summary


def main() -> None:
    df_repaired, summary = prepare_salary_repaired_dataset()
    salary_mart = build_salary_mart(df_repaired)
    review_mart = build_manual_review_mart(df_repaired)

    df_repaired.to_csv(OUTPUT_DATASET_PATH, index=False, encoding="utf-8")
    salary_mart.to_csv(OUTPUT_SALARY_MART_PATH, index=False, encoding="utf-8")
    review_mart.to_csv(OUTPUT_MANUAL_REVIEW_PATH, index=False, encoding="utf-8")
    OUTPUT_SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Salary repair v3 complete.")
    print(f"- repaired dataset: {OUTPUT_DATASET_PATH}")
    print(f"- salary mart v3: {OUTPUT_SALARY_MART_PATH}")
    print(f"- manual review queue v3: {OUTPUT_MANUAL_REVIEW_PATH}")
    print(f"- summary: {OUTPUT_SUMMARY_PATH}")
    print(f"- usable salary analytics rows: {summary['usable_for_salary_analytics_rows']:,}")
    print(f"- manual review rows: {summary['manual_review_rows']:,}")


if __name__ == "__main__":
    main()
