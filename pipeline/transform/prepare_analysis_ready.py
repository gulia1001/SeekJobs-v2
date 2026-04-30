from __future__ import annotations

# %%
import hashlib
import html
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# %%
# Paths and top-level configuration
BASE_PATH = Path(__file__).resolve().parents[1]  # pipeline/
DATA_DIR = BASE_PATH / "data"
INPUT_PATH = DATA_DIR / "interim" / "enriched_jobs_full_v1.csv"
ANALYSIS_READY_PATH = DATA_DIR / "final" / "analysis_ready_jobs.csv"
SALARY_MART_PATH = DATA_DIR / "final" / "jobs_salary_clean.csv"
SKILLS_MART_PATH = DATA_DIR / "final" / "jobs_skills_clean.csv"
ENTITY_MART_PATH = DATA_DIR / "final" / "jobs_entity_clean.csv"
QUALITY_REPORT_JSON_PATH = DATA_DIR / "reports" / "data_quality_report.json"
QUALITY_REPORT_MD_PATH = BASE_PATH / "docs" / "reports" / "data_quality_report.md"
HEADER_AUDIT_JSON_PATH = DATA_DIR / "reports" / "header_parse_audit.json"
HEADER_AUDIT_MD_PATH = BASE_PATH / "docs" / "reports" / "header_parse_audit.md"
STILL_BAD_ROWS_PATH = DATA_DIR / "reports" / "still_bad_rows.csv"

MISSING_LIKE_STRINGS = {"", "unknown", "none", "null", "nan", "n/a", "na"}
SALARY_OUTLIER_THRESHOLD = 10_000_000

JSON_ARRAY_COLUMNS = [
    "hard_skills",
    "soft_skills",
    "tech_stack",
    "review_flags",
    "conflict_flags",
    "validation_fixes",
]

JSON_OBJECT_COLUMNS = [
    "parser_hints",
    "parser_quality",
    "final_field_sources",
    "final_field_confidence",
]

JSON_COLUMNS = JSON_ARRAY_COLUMNS + JSON_OBJECT_COLUMNS

STRUCTURED_SOURCES = {"hh_kz", "kaspi_jobs", "kolesa_jobs"}
SOURCE_PRIORITY = {
    "hh_kz": 4,
    "kaspi_jobs": 3,
    "kolesa_jobs": 3,
    "Freedom Broker": 2,
    "Work IT KZ": 1,
    "Zhumys Bar IT": 1,
    "IT Vacancy KZ": 1,
    "ITcom KZ": 1,
    "Halyk Jumys": 1,
    "Insfera For You": 1,
}

VALID_CATEGORY_VALUES = {
    "data",
    "software_engineering",
    "qa",
    "devops",
    "product",
    "design",
    "analytics",
    "security",
    "management",
    "support",
    "marketing",
    "sales",
    "hr",
    "finance",
    "other",
}

VALID_LEVEL_VALUES = {"intern", "junior", "middle", "senior", "lead", "manager"}
VALID_EMPLOYMENT_VALUES = {"full_time", "part_time", "contract", "internship", "temporary"}
VALID_WORK_FORMAT_VALUES = {"office", "remote", "hybrid"}
VALID_ENGLISH_LEVEL_VALUES = {"a1", "a2", "b1", "b2", "c1", "c2", "not_required"}
VALID_CURRENCY_VALUES = {"KZT", "USD", "EUR", "RUB", "KGS"}

CATEGORY_NORMALIZATION_MAP = {
    "backend": "software_engineering",
    "frontend": "software_engineering",
    "front_end": "software_engineering",
    "fullstack": "software_engineering",
    "mobile": "software_engineering",
    "java_engineer": "software_engineering",
    "python_developer": "software_engineering",
    "dotnet_developer": "software_engineering",
    "data_analyst": "analytics",
    "data_engineer": "data",
    "data_scientist": "data",
    "ml_engineer": "data",
    "product_analyst": "analytics",
    "business_analyst": "analytics",
    "system_analyst": "analytics",
    "project_manager": "management",
    "product_manager": "product",
    "ui_ux_designer": "design",
    "head": "management",
}

LEVEL_NORMALIZATION_MAP = {
    "mid": "middle",
    "middle+": "middle",
    "middle plus": "middle",
    "sr": "senior",
    "senior+": "senior",
    "jr": "junior",
    "head": "manager",
}

TITLE_VARIANT_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(front[\s-]?end|react(?:\.js)? developer|vue(?:\.js)? developer|angular developer)\b"), "Frontend Developer"),
    (re.compile(r"(?i)\b(back[\s-]?end|backend developer|python developer|java developer|golang developer|node(?:\.js)? developer|c#/.net software developer|php developer)\b"), "Backend Developer"),
    (re.compile(r"(?i)\bfull[\s-]?stack\b"), "Fullstack Developer"),
    (re.compile(r"(?i)\b(data analyst|bi analyst|business intelligence analyst)\b"), "Data Analyst"),
    (re.compile(r"(?i)\b(system analyst|business analyst|product analyst)\b"), "Business Analyst"),
    (re.compile(r"(?i)\bdata scientist\b"), "Data Scientist"),
    (re.compile(r"(?i)\b(machine learning engineer|ml engineer)\b"), "ML Engineer"),
    (re.compile(r"(?i)\b(data engineer)\b"), "Data Engineer"),
    (re.compile(r"(?i)\b(qa engineer|test automation engineer|tester|sdet|quality assurance)\b"), "QA Engineer"),
    (re.compile(r"(?i)\b(devops engineer|site reliability engineer|sre)\b"), "DevOps Engineer"),
    (re.compile(r"(?i)\b(product manager|product owner)\b"), "Product Manager"),
    (re.compile(r"(?i)\b(project manager)\b"), "Project Manager"),
    (re.compile(r"(?i)\b(ui/?ux designer|product designer|ux designer|ui designer)\b"), "UI/UX Designer"),
]

CONTACT_KEYWORD_PATTERN = re.compile(
    r"(?i)\b(контакт[ыа]?|contact|contacts|whatsapp|telegram|tg|резюме|отправить резюме|write to|direct|send cv|cv|resume|whatsupp|whatsup)\b"
)
PROMO_PATTERNS = [
    re.compile(r"(?i)\bapply now\b"),
    re.compile(r"(?i)\bno experience\?\s*no problem\b"),
    re.compile(r"(?i)\bwe['’]ll teach you everything you need to succeed\b"),
    re.compile(r"(?i)\bпишите в direct\b"),
    re.compile(r"(?i)\bоткликайтесь\b"),
    re.compile(r"(?i)\bждем ваше резюме\b"),
]


# %%
def normalize_whitespace(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def is_missing_like(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    except ValueError:
        pass
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str):
        lowered = normalize_whitespace(value).lower()
        return lowered in MISSING_LIKE_STRINGS or lowered == "[]"
    return False


def is_meaningful_text(value: Any, min_len: int = 2) -> bool:
    text = normalize_whitespace(value)
    return bool(text) and text.lower() not in MISSING_LIKE_STRINGS and len(text) >= min_len


def standardize_scalar_missing(value: Any) -> Any:
    if isinstance(value, str):
        text = normalize_whitespace(html.unescape(value))
        return pd.NA if text.lower() in MISSING_LIKE_STRINGS else text
    return value


def safe_json_loads(value: Any, default: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, (list, dict)):
        return value
    text = normalize_whitespace(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def json_dumps_or_na(value: Any) -> Any:
    if is_missing_like(value):
        return pd.NA
    return json.dumps(value, ensure_ascii=False)


def normalize_key(value: Any) -> str:
    text = normalize_whitespace(value).lower()
    text = re.sub(r"[^0-9a-zа-яё]+", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def md5_text(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def safe_int(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "cp1251"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"Unable to read {path} with encodings {encodings}") from last_error


def standardize_missing_like_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    for column in cleaned.columns:
        if cleaned[column].dtype == "object":
            cleaned[column] = cleaned[column].map(standardize_scalar_missing)
    return cleaned


def count_missing_like(series: pd.Series) -> int:
    if series.dtype == "object":
        return int(series.map(is_missing_like).sum())
    return int(series.isna().sum())


def numeric_or_none(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class SalaryParseResult:
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


@dataclass(slots=True)
class HeaderParseResult:
    title: str | None = None
    company: str | None = None
    city: str | None = None
    pattern: str = "no_match"
    confidence: float = 0.0


# %%
def audit_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    column_profiles = []
    for column in df.columns:
        series = df[column]
        sample_values = [
            value
            for value in series.dropna().astype(str).head(5).tolist()
        ]
        column_profiles.append(
            {
                "column": column,
                "dtype": str(series.dtype),
                "missing_like": count_missing_like(series),
                "missing_pct": round(count_missing_like(series) / len(df) * 100, 2),
                "sample_values": sample_values,
            }
        )

    categorical_snapshots: dict[str, Any] = {}
    for column in df.columns:
        series = df[column]
        if series.dtype != "object":
            continue
        unique_non_missing = series.dropna().astype(str).nunique()
        if unique_non_missing <= 40 or column in {
            "source",
            "city",
            "category",
            "level",
            "employment",
            "work_format",
            "currency",
            "english_level",
            "llm_merge_status",
            "llm_model",
        }:
            categorical_snapshots[column] = (
                series.fillna("<NA>").astype(str).value_counts(dropna=False).head(15).to_dict()
            )

    json_validation: dict[str, Any] = {}
    for column in JSON_COLUMNS:
        valid = 0
        invalid = 0
        for value in df[column].dropna():
            try:
                json.loads(value)
                valid += 1
            except Exception:  # noqa: BLE001
                invalid += 1
        json_validation[column] = {
            "non_null": int(df[column].notna().sum()),
            "valid_json_rows": valid,
            "invalid_json_rows": invalid,
        }

    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": column_profiles,
        "categorical_snapshots": categorical_snapshots,
        "json_validation": json_validation,
    }


def print_discovery_summary(report: dict[str, Any]) -> None:
    print("=" * 100)
    print("DISCOVERED DATASET SUMMARY")
    print("=" * 100)
    print(f"Rows: {report['row_count']:,}")
    print(f"Columns: {report['column_count']}")
    print("\nColumns, dtypes, missingness, and sample values:")
    for item in report["columns"]:
        samples = "; ".join(item["sample_values"][:3]) or "<no non-null sample>"
        print(
            f"- {item['column']}: dtype={item['dtype']}, "
            f"missing_like={item['missing_like']:,} ({item['missing_pct']}%), "
            f"samples={samples[:180]}"
        )
    print("\nJSON validation summary:")
    for column, info in report["json_validation"].items():
        print(
            f"- {column}: non_null={info['non_null']:,}, "
            f"valid={info['valid_json_rows']:,}, invalid={info['invalid_json_rows']:,}"
        )
    print("=" * 100)


# %%
def strip_emojis(text: str) -> str:
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F6FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "]",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub(" ", text)


def clean_description_v2(text: Any) -> tuple[str | pd._libs.missing.NAType, bool, int, int]:
    if not is_meaningful_text(text, min_len=5):
        return pd.NA, False, 0, 0

    original = html.unescape(str(text))
    cleaned = original.replace("\r", "\n")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}\b", " ", cleaned)
    cleaned = re.sub(r"(?<!\w)@\w{3,}", " ", cleaned)
    cleaned = re.sub(r"(?<!\w)#[\w\-_А-Яа-яЁё]+", " ", cleaned)

    lines = [line.strip() for line in re.split(r"[\n]+", cleaned) if line.strip()]
    kept_lines: list[str] = []
    for line in lines:
        line_normalized = normalize_whitespace(line)
        has_contact_keyword = bool(CONTACT_KEYWORD_PATTERN.search(line_normalized))
        has_contact_token = bool(
            re.search(r"\+?\d[\d\-\s()]{7,}\d", line_normalized)
            or re.search(r"\b[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}\b", line_normalized)
            or re.search(r"(?<!\w)@\w{3,}", line_normalized)
            or re.search(r"https?://\S+|www\.\S+", line_normalized, flags=re.IGNORECASE)
        )
        if has_contact_keyword and has_contact_token:
            continue
        kept_lines.append(line_normalized)
    cleaned = "\n".join(kept_lines) if kept_lines else cleaned

    cleaned = re.sub(
        r"(?i)\b(контакт[ыа]?|contact|contacts|whatsapp|telegram|tg|резюме|отправить резюме|write to|direct|send cv|resume)\b[:\s\-]{0,5}[^\n.;]{0,180}",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\+?\d[\d\-\s()]{8,}\d", " ", cleaned)
    cleaned = strip_emojis(cleaned)
    for pattern in PROMO_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"[•▪◾◆▶➤✔✅]+", " ", cleaned)
    cleaned = re.sub(r"[|]{2,}", " ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s*([,:;])\s*", r"\1 ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" -–—\n\t")

    removed_chars = max(0, len(original) - len(cleaned))
    changed = cleaned != normalize_whitespace(original)
    if not is_meaningful_text(cleaned, min_len=20):
        cleaned = normalize_whitespace(original)
        removed_chars = max(0, len(original) - len(cleaned))
        changed = cleaned != normalize_whitespace(original)

    return cleaned or pd.NA, changed, len(cleaned or ""), removed_chars


# %%
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
    if any(token in joined for token in ["RUB", "RUR", "РУБ"]):
        return "RUB"
    if "KGS" in joined:
        return "KGS"
    return pd.NA


def looks_like_phone_number(value: Any) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    digits = re.sub(r"\D", "", str(value))
    return len(digits) in {10, 11} and digits.startswith(("7", "8"))


def amount_from_token(number_text: str, unit_text: str | None) -> float | None:
    cleaned_number = number_text.replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        value = float(cleaned_number)
    except ValueError:
        return None
    unit = normalize_whitespace(unit_text).lower()
    if unit in {"млн", "миллион", "миллиона", "миллионов", "million", "m"}:
        value *= 1_000_000
    elif unit in {"k", "к", "тыс", "тысяч", "thousand"}:
        value *= 1_000
    return float(value)


def extract_amounts_from_text(text: str) -> list[float]:
    amount_pattern = re.compile(
        r"(?<!\d)(\d{1,3}(?:[ \xa0]?\d{3})+|\d+(?:[.,]\d+)?)\s*(млн|миллион(?:а|ов)?|million|тыс|тысяч|thousand|k|к|m)?",
        flags=re.IGNORECASE,
    )
    amounts: list[float] = []
    for number_text, unit_text in amount_pattern.findall(text):
        value = amount_from_token(number_text, unit_text)
        if value is None:
            continue
        digits_only = re.sub(r"\D", "", number_text)
        if len(digits_only) in {10, 11} and digits_only.startswith(("7", "8")) and unit_text.strip() == "":
            continue
        amounts.append(value)
    return amounts


def extract_salary_candidate_text(salary_raw: Any, description_clean_v2: Any, description: Any) -> tuple[str, str]:
    if is_meaningful_text(salary_raw):
        return str(salary_raw), "salary_raw"

    description_sources = [description_clean_v2, description]
    for value in description_sources:
        if not is_meaningful_text(value, min_len=20):
            continue
        text = str(value)
        keyword_match = re.search(
            r"(?is)(зарплата|salary|оклад)[^.\n]{0,120}",
            text,
        )
        if keyword_match:
            return keyword_match.group(0), "description_keyword"
        currency_match = re.search(
            r"(?is)(?:от|до)?\s*\d[\d\s,.]*(?:[-–—]\s*\d[\d\s,.]*)?\s*(?:₸|тг|тенге|usd|\$|eur|€|rub|rur|руб|млн|k|к)",
            text,
        )
        if currency_match:
            return currency_match.group(0), "description_currency_pattern"
    return "", "missing"


def parse_salary_candidate(text: str) -> tuple[float | None, float | None, str]:
    normalized = normalize_whitespace(text).lower()
    if not normalized:
        return None, None, "missing"

    amounts = extract_amounts_from_text(normalized)
    if not amounts:
        return None, None, "missing"

    if len(amounts) >= 2 and re.search(r"(?i)\b(от|from)\b", normalized) and re.search(r"(?i)\b(до|to)\b", normalized):
        return min(amounts[0], amounts[1]), max(amounts[0], amounts[1]), "parsed_range"
    if len(amounts) >= 2 and re.search(r"[-–—]", normalized):
        return min(amounts[0], amounts[1]), max(amounts[0], amounts[1]), "parsed_range"
    if len(amounts) == 1 and re.search(r"(?i)\b(от|from)\b", normalized):
        return amounts[0], None, "parsed_lower_bound"
    if len(amounts) == 1 and re.search(r"(?i)\b(до|to)\b", normalized):
        return None, amounts[0], "parsed_upper_bound"
    if len(amounts) == 1:
        return amounts[0], None, "parsed_single"
    return None, None, "ambiguous"


def sanitize_salary_numeric(value: Any) -> tuple[float | None, list[str]]:
    flags: list[str] = []
    numeric = numeric_or_none(value)
    if numeric is None:
        return None, flags
    if math.isclose(numeric, 0.0):
        flags.append("zero_value")
        return None, flags
    if looks_like_phone_number(int(numeric)):
        flags.append("phone_like_numeric")
        return None, flags
    if numeric > SALARY_OUTLIER_THRESHOLD:
        flags.append("outlier_numeric")
        return None, flags
    return float(numeric), flags


def build_salary_clean_result(row: pd.Series) -> SalaryParseResult:
    raw_text, parse_source = extract_salary_candidate_text(
        row.get("salary_raw"),
        row.get("description_clean_v2"),
        row.get("description"),
    )
    currency_clean = normalize_currency(row.get("currency"), raw_text)

    contact_leak_flag = bool(
        looks_like_phone_number(row.get("salary_from"))
        or looks_like_phone_number(row.get("salary_to"))
        or re.search(r"\+?\d[\d\-\s()]{8,}\d", raw_text)
    )
    outlier_flag = False
    zero_flag = False
    fix_flags: list[str] = []

    existing_from, existing_from_flags = sanitize_salary_numeric(row.get("salary_from"))
    existing_to, existing_to_flags = sanitize_salary_numeric(row.get("salary_to"))
    fix_flags.extend(existing_from_flags + existing_to_flags)
    zero_flag = zero_flag or "zero_value" in fix_flags
    outlier_flag = outlier_flag or "outlier_numeric" in fix_flags

    parsed_from, parsed_to, parsed_quality = parse_salary_candidate(raw_text)
    if parsed_from is not None and parsed_from > SALARY_OUTLIER_THRESHOLD:
        parsed_from = None
        parsed_quality = "outlier_removed"
        outlier_flag = True
        fix_flags.append("parsed_from_outlier_removed")
    if parsed_to is not None and parsed_to > SALARY_OUTLIER_THRESHOLD:
        parsed_to = None
        parsed_quality = "outlier_removed"
        outlier_flag = True
        fix_flags.append("parsed_to_outlier_removed")
    if parsed_from is not None and math.isclose(parsed_from, 0.0):
        parsed_from = None
        zero_flag = True
        fix_flags.append("parsed_from_zero_removed")
    if parsed_to is not None and math.isclose(parsed_to, 0.0):
        parsed_to = None
        zero_flag = True
        fix_flags.append("parsed_to_zero_removed")

    if contact_leak_flag:
        return SalaryParseResult(
            salary_from_clean=None,
            salary_to_clean=None,
            salary_avg_clean=None,
            currency_clean=currency_clean if currency_clean in VALID_CURRENCY_VALUES else pd.NA,
            salary_parse_quality="contact_leak",
            salary_is_suspicious=True,
            salary_outlier_flag=outlier_flag,
            salary_contact_leak_flag=True,
            salary_zero_flag=zero_flag,
            salary_usable_for_analytics=False,
            salary_fix_flags=sorted(set(fix_flags + ["contact_leak_detected"])),
            salary_parse_source=parse_source,
        )

    salary_from_clean = parsed_from if parsed_from is not None else existing_from
    salary_to_clean = parsed_to if parsed_to is not None else existing_to
    parse_quality = parsed_quality if parsed_quality != "missing" else "existing_numeric"

    if salary_from_clean is None and salary_to_clean is None:
        parse_quality = "missing"
    elif parsed_from is None and parsed_to is None and (existing_from is not None or existing_to is not None):
        parse_quality = "existing_numeric"
    elif (parsed_from is not None or parsed_to is not None) and (existing_from is not None or existing_to is not None):
        parse_quality = f"mixed_{parsed_quality}"

    if salary_from_clean is not None and salary_to_clean is not None and salary_from_clean > salary_to_clean:
        salary_from_clean, salary_to_clean = salary_to_clean, salary_from_clean
        fix_flags.append("salary_range_swapped_v2")

    if salary_from_clean is not None and salary_from_clean > SALARY_OUTLIER_THRESHOLD:
        salary_from_clean = None
        outlier_flag = True
        fix_flags.append("salary_from_outlier_removed")
    if salary_to_clean is not None and salary_to_clean > SALARY_OUTLIER_THRESHOLD:
        salary_to_clean = None
        outlier_flag = True
        fix_flags.append("salary_to_outlier_removed")

    salary_avg_clean: float | None = None
    if salary_from_clean is not None and salary_to_clean is not None:
        salary_avg_clean = float((salary_from_clean + salary_to_clean) / 2)
    elif salary_from_clean is not None:
        salary_avg_clean = float(salary_from_clean)
    elif salary_to_clean is not None:
        salary_avg_clean = float(salary_to_clean)

    suspicious = bool(contact_leak_flag or outlier_flag)
    usable = bool(
        not suspicious
        and currency_clean in VALID_CURRENCY_VALUES
        and (salary_from_clean is not None or salary_to_clean is not None)
    )
    if zero_flag and salary_from_clean is None and salary_to_clean is None:
        parse_quality = "zero_only"
    if outlier_flag and salary_from_clean is None and salary_to_clean is None:
        parse_quality = "outlier_removed"

    return SalaryParseResult(
        salary_from_clean=salary_from_clean,
        salary_to_clean=salary_to_clean,
        salary_avg_clean=salary_avg_clean,
        currency_clean=currency_clean if currency_clean in VALID_CURRENCY_VALUES else pd.NA,
        salary_parse_quality=parse_quality,
        salary_is_suspicious=suspicious or zero_flag,
        salary_outlier_flag=outlier_flag,
        salary_contact_leak_flag=contact_leak_flag,
        salary_zero_flag=zero_flag,
        salary_usable_for_analytics=usable,
        salary_fix_flags=sorted(set(fix_flags)),
        salary_parse_source=parse_source,
    )


# %%
def normalize_category(value: Any) -> Any:
    text = normalize_key(value).replace(" ", "_")
    if not text or text in MISSING_LIKE_STRINGS:
        return pd.NA
    text = CATEGORY_NORMALIZATION_MAP.get(text, text)
    return text if text in VALID_CATEGORY_VALUES else pd.NA


def normalize_level(value: Any) -> Any:
    text = normalize_key(value).replace(" ", "_")
    if not text or text in MISSING_LIKE_STRINGS:
        return pd.NA
    text = LEVEL_NORMALIZATION_MAP.get(text, text)
    return text if text in VALID_LEVEL_VALUES else pd.NA


def normalize_employment(value: Any) -> Any:
    text = normalize_key(value).replace(" ", "_")
    if not text or text in MISSING_LIKE_STRINGS:
        return pd.NA
    mappings = {
        "fulltime": "full_time",
        "full_time": "full_time",
        "parttime": "part_time",
        "part_time": "part_time",
        "freelance": "contract",
        "contractor": "contract",
        "intern": "internship",
    }
    text = mappings.get(text, text)
    return text if text in VALID_EMPLOYMENT_VALUES else pd.NA


def normalize_work_format(value: Any) -> Any:
    text = normalize_key(value).replace(" ", "_")
    if not text or text in MISSING_LIKE_STRINGS:
        return pd.NA
    if any(term in text for term in ["hybrid", "гибрид"]):
        return "hybrid"
    if any(term in text for term in ["remote", "удален", "дистанцион"]):
        return "remote"
    if any(term in text for term in ["office", "onsite", "on_site", "офис"]):
        return "office"
    return pd.NA


def normalize_city(value: Any) -> Any:
    text = normalize_whitespace(value).lower()
    if not text or text in MISSING_LIKE_STRINGS:
        return pd.NA
    if any(token in text for token in ["алматы", "almaty"]):
        return "almaty"
    if any(token in text for token in ["астана", "astana", "nur-sultan", "нур-султан"]):
        return "astana"
    if any(token in text for token in ["remote", "удален", "дистанцион"]):
        return "remote"
    if text in {"other", "другой"}:
        return "other"
    return "other"


def normalize_english_level(value: Any) -> Any:
    text = normalize_key(value).replace(" ", "_")
    if not text or text in MISSING_LIKE_STRINGS:
        return pd.NA
    return text if text in VALID_ENGLISH_LEVEL_VALUES else pd.NA


def parse_json_list(value: Any) -> list[str]:
    parsed = safe_json_loads(value, [])
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, str):
        items = re.split(r"[;,/|]\s*", parsed)
    else:
        items = []
    cleaned: list[str] = []
    for item in items:
        text = normalize_whitespace(item)
        if is_meaningful_text(text, min_len=1):
            cleaned.append(text)
    return cleaned


def canonicalize_skill(skill: str, context_text: str = "") -> str | None:
    if not is_meaningful_text(skill, min_len=1):
        return None
    raw = normalize_whitespace(skill)
    lower = raw.lower()
    mapping = {
        "git": "Git",
        "python": "Python",
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "py spark": "PySpark",
        "pyspark": "PySpark",
        "k8s": "Kubernetes",
        "kubernetes": "Kubernetes",
        "1с": "1C",
        "1c": "1C",
        "react.js": "React",
        "reactjs": "React",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "ci cd": "CI/CD",
        "ci/cd": "CI/CD",
        "cicd": "CI/CD",
    }
    if lower in mapping:
        return mapping[lower]
    if lower == "js":
        if any(
            token in context_text.lower()
            for token in [
                "developer",
                "frontend",
                "backend",
                "engineer",
                "react",
                "vue",
                "angular",
                "node",
                "typescript",
                "javascript",
                "програм",
                "разработ",
            ]
        ):
            return "JavaScript"
        return "JS"
    if len(raw) <= 4 and raw.isupper():
        return raw
    if lower in {"sql", "excel", "docker", "linux", "power bi", "figma", "django", "flask", "airflow", "tableau"}:
        title_map = {
            "sql": "SQL",
            "excel": "Excel",
            "docker": "Docker",
            "linux": "Linux",
            "power bi": "Power BI",
            "figma": "Figma",
            "django": "Django",
            "flask": "Flask",
            "airflow": "Apache Airflow",
            "tableau": "Tableau",
        }
        return title_map[lower]
    return raw


def canonicalize_skill_list(items: list[str], context_text: str = "") -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items:
        canonical = canonicalize_skill(item, context_text=context_text)
        if not canonical:
            continue
        key = canonical.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(canonical)
    return cleaned


def determine_top_skill_family(skills: list[str]) -> Any:
    if not skills:
        return pd.NA
    family_map = {
        "Python": "data_and_backend",
        "SQL": "data_and_backend",
        "PostgreSQL": "data_and_backend",
        "PySpark": "data_and_backend",
        "Apache Airflow": "data_and_backend",
        "JavaScript": "frontend_and_web",
        "React": "frontend_and_web",
        "Node.js": "frontend_and_web",
        "TypeScript": "frontend_and_web",
        "Kubernetes": "devops_and_cloud",
        "Docker": "devops_and_cloud",
        "CI/CD": "devops_and_cloud",
        "Linux": "devops_and_cloud",
        "Selenium": "qa_and_testing",
        "Postman": "qa_and_testing",
        "Cypress": "qa_and_testing",
        "Power BI": "analytics_and_bi",
        "Tableau": "analytics_and_bi",
        "Figma": "design",
        "1C": "erp_and_business_systems",
    }
    counts = Counter(family_map.get(skill, "other") for skill in skills)
    return counts.most_common(1)[0][0]


def combine_context_text(row: pd.Series) -> str:
    parts = [
        row.get("title"),
        row.get("title_normalized"),
        row.get("description_clean_v2"),
        row.get("requirements_clean"),
        row.get("responsibilities_clean"),
    ]
    return " ".join(normalize_whitespace(part) for part in parts if is_meaningful_text(part))


def infer_category(row: pd.Series) -> tuple[Any, str, float]:
    if is_meaningful_text(row.get("category_norm")):
        return row.get("category_norm"), "existing_valid", 1.0

    text = combine_context_text(row).lower()
    skills = set(row.get("_skills_all_list", []))
    scores: Counter[str] = Counter()

    def add_if(match_terms: list[str], category: str, weight: int) -> None:
        if any(term in text for term in match_terms):
            scores[category] += weight

    def add_skill_if(match_terms: list[str], category: str, weight: int) -> None:
        if any(term in {skill.lower() for skill in skills} for term in match_terms):
            scores[category] += weight

    add_if(["data engineer", "data scientist", "ml engineer", "machine learning", "etl", "dwh"], "data", 4)
    add_if(["data analyst", "business analyst", "system analyst", "product analyst", "bi analyst", "dashboard"], "analytics", 4)
    add_if(["qa engineer", "tester", "test automation", "selenium", "postman", "sdet"], "qa", 5)
    add_if(["devops", "site reliability", "sre", "terraform", "kubernetes", "docker", "ci/cd", "ansible"], "devops", 5)
    add_if(["product manager", "product owner"], "product", 5)
    add_if(["project manager", "team lead", "delivery manager", "engineering manager", "head of", "director"], "management", 5)
    add_if(["ui/ux", "ux designer", "ui designer", "product designer", "figma"], "design", 5)
    add_if(["security", "soc", "siem", "pentest", "cyber"], "security", 5)
    add_if(["support", "helpdesk", "technical support"], "support", 5)
    add_if(["marketing", "smm", "brand manager", "media planner"], "marketing", 4)
    add_if(["sales", "account executive", "business development", "head of sales"], "sales", 4)
    add_if(["recruiter", "hr", "talent acquisition"], "hr", 4)
    add_if(["finance", "accountant", "auditor", "financial analyst"], "finance", 4)
    add_if(
        [
            "developer",
            "разработчик",
            "software engineer",
            "backend",
            "frontend",
            "fullstack",
            "mobile",
            "android",
            "ios",
        ],
        "software_engineering",
        4,
    )

    add_skill_if(["python", "sql", "pyspark", "postgresql", "apache airflow"], "data", 2)
    add_skill_if(["power bi", "tableau"], "analytics", 2)
    add_skill_if(["selenium", "postman", "cypress"], "qa", 3)
    add_skill_if(["docker", "kubernetes", "ci/cd", "linux"], "devops", 3)
    add_skill_if(["react", "node.js", "javascript"], "software_engineering", 2)
    add_skill_if(["figma"], "design", 2)

    if not scores:
        return pd.NA, "unresolved", 0.0

    top_two = scores.most_common(2)
    best_category, best_score = top_two[0]
    next_score = top_two[1][1] if len(top_two) > 1 else 0
    if best_score < 4 or (best_score - next_score) < 2:
        return pd.NA, "unresolved", 0.0
    confidence = 0.9 if best_score >= 6 else 0.78
    source = "rule_based_high" if confidence >= 0.85 else "rule_based_medium"
    return best_category, source, confidence


def infer_level(row: pd.Series) -> tuple[Any, str, float]:
    if is_meaningful_text(row.get("level_norm")):
        return row.get("level_norm"), "existing_valid", 1.0

    text = combine_context_text(row).lower()
    title_text = " ".join(
        normalize_whitespace(part).lower()
        for part in [row.get("title"), row.get("title_normalized"), row.get("title_final")]
        if is_meaningful_text(part)
    )
    experience_min = numeric_or_none(row.get("experience_min"))
    internship_regex = re.compile(r"(?i)\b(intern|internship|trainee)\b|стаж[её]р|стажировка")
    junior_regex = re.compile(r"(?i)\b(junior|jr)\b|начинающ")
    middle_regex = re.compile(r"(?i)\b(middle|mid-level)\b")
    senior_regex = re.compile(r"(?i)\b(senior|sr)\b")

    if internship_regex.search(title_text):
        return "intern", "title_rule_high", 0.95
    if any(term in title_text for term in ["lead", "tech lead", "team lead"]) or "руководитель группы" in title_text:
        return "lead", "title_rule_high", 0.95
    if senior_regex.search(title_text):
        return "senior", "title_rule_high", 0.95
    if junior_regex.search(title_text):
        return "junior", "title_rule_high", 0.95
    if middle_regex.search(title_text):
        return "middle", "title_rule_high", 0.95
    if any(term in title_text for term in ["head of", "director", "chief", "начальник", "руководитель"]) or "engineering manager" in title_text:
        return "manager", "title_rule_high", 0.92

    if internship_regex.search(text):
        return "intern", "text_rule_medium", 0.82
    if junior_regex.search(text) or any(term in text for term in ["0-1 year", "0–1", "0-1"]):
        return "junior", "text_rule_medium", 0.8
    if middle_regex.search(text) or any(term in text for term in ["2-4 years", "2–4"]):
        return "middle", "text_rule_medium", 0.8
    if senior_regex.search(text) or any(term in text for term in ["5+ years", "5 years", "более 5 лет"]):
        return "senior", "text_rule_medium", 0.82

    if experience_min is not None:
        if experience_min == 0 and internship_regex.search(text):
            return "intern", "experience_plus_text", 0.78
        if 0 < experience_min <= 1:
            return "junior", "experience_rule_medium", 0.72
        if 2 <= experience_min <= 4:
            return "middle", "experience_rule_medium", 0.72
        if experience_min >= 5:
            return "senior", "experience_rule_medium", 0.74

    return pd.NA, "unresolved", 0.0


# %%
def clean_title_text(value: Any) -> Any:
    if not is_meaningful_text(value, min_len=2):
        return pd.NA
    text = normalize_whitespace(value)
    text = re.sub(r"(?i)^(vacancy|вакансия|позиция|role)\s*[:\-]\s*", "", text)
    text = re.sub(r"[|]{2,}", " ", text)
    text = text.strip(" -–—")
    return text or pd.NA


def normalize_title_variant(title: Any) -> Any:
    if not is_meaningful_text(title, min_len=2):
        return pd.NA
    title_text = str(title)
    lowered = title_text.lower()
    # Preserve specific titles that already carry useful stack or seniority detail.
    if any(
        token in lowered
        for token in [
            ".net",
            "asp.net",
            "angular",
            "react",
            "vue",
            "java",
            "python",
            "golang",
            "c#",
            "c++",
            "node",
            "qa ",
            " ai",
            " ml",
            "senior",
            "middle",
            "junior",
            "lead",
            "fullstack",
            "/",
            "(",
        ]
    ):
        return title_text
    for pattern, replacement in TITLE_VARIANT_RULES:
        if pattern.search(title_text):
            return replacement
    return title_text


def title_looks_valid(value: Any) -> bool:
    if not is_meaningful_text(value, min_len=3):
        return False
    text = normalize_whitespace(value)
    lowered = text.lower()
    if lowered in {
        "ищет",
        "нужен",
        "нужна",
        "требуется",
        "вакансия",
        "должность",
        "компания",
        "разработчика",
        "разработчикa",
    }:
        return False
    if len(text.split()) == 1 and lowered in {"backend", "frontend", "fullstack", "developer", "engineer", "analyst"}:
        return False
    if any(token in lowered for token in ["контакты:", "резюме", "whatsapp", "telegram", "@"]):
        return False
    if lowered.startswith(("всем привет", "друзья", "приветствую", "присоединяйтесь", "переходите по ссылке", "войди в it")):
        return False
    return True


def clean_header_company_candidate(value: Any) -> Any:
    cleaned = clean_company_value(value)
    if not is_meaningful_text(cleaned, min_len=2):
        return pd.NA
    text = normalize_whitespace(cleaned)
    text = re.sub(r"(?i)\s+(ищет|в команду|на позицию|требуется)\b.*$", "", text).strip()
    text = re.sub(r"\s+https?://\S+$", "", text, flags=re.IGNORECASE).strip()
    if not is_meaningful_text(text, min_len=2):
        return pd.NA
    if len(text.split()) > 12:
        return pd.NA
    return text


def company_looks_valid(value: Any) -> bool:
    if not is_meaningful_text(value, min_len=2):
        return False
    text = normalize_whitespace(value)
    lowered = text.lower()
    if lowered in {"команда", "компания", "вакансия"}:
        return False
    if lowered.startswith(("основные", "обязанности", "требования", "условия", "зарплата", "резюме")):
        return False
    if len(text.split()) > 12:
        return False
    if re.search(r"(?i)\b(ищет|требуется|в поисках|проводит набор)\b", text):
        return False
    return True


def clean_header_title_candidate(value: Any) -> Any:
    cleaned = clean_title_text(value)
    if not title_looks_valid(cleaned):
        return pd.NA
    text = normalize_whitespace(cleaned)
    text = re.sub(r'\s+(?:АО|ТОО|ИП|JSC|LLP)\b.*$', "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"(?i)\b(казахстан|г\.)\b.*$", "", text).strip(" -–—,")
    text = re.sub(r"\s{2,}", " ", text)
    if not title_looks_valid(text):
        return pd.NA
    return text


def clean_header_city_candidate(value: Any) -> Any:
    normalized = normalize_city(value)
    return normalized if is_meaningful_text(normalized, min_len=3) else pd.NA


def extract_header_window(text: Any, max_len: int = 900) -> str:
    if not is_meaningful_text(text, min_len=10):
        return ""
    source = str(text).replace("\r", "\n")
    cutoff_patterns = [
        r"(?i)\bтребования\s*[:\-]",
        r"(?i)\bобязанности\s*[:\-]",
        r"(?i)\bусловия\s*[:\-]",
        r"(?i)\brequirements\s*[:\-]",
        r"(?i)\bresponsibilities\s*[:\-]",
        r"(?i)\babout the role\b",
    ]
    cutoff = len(source)
    for pattern in cutoff_patterns:
        match = re.search(pattern, source)
        if match:
            cutoff = min(cutoff, match.start())
    header = source[:cutoff]
    header = re.split(r"\n", header)[0:4]
    compact = " ".join(normalize_whitespace(part) for part in header if normalize_whitespace(part))
    return compact[:max_len]


def parse_semistructured_header(text: Any) -> HeaderParseResult:
    header = extract_header_window(text)
    if not header:
        return HeaderParseResult()

    # Pattern 1: Title (City) Company ищет ...
    pattern_1 = re.compile(
        r'^(?P<title>.+?)\s*\(\s*(?P<city>[^)]+)\s*\)\s*(?P<company>(?:АО|ТОО|ИП|JSC|LLP)\s*["«][^"»]+["»]|[^.]{3,120}?)\s+ищет\b',
        flags=re.IGNORECASE,
    )
    match = pattern_1.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=clean_header_city_candidate(match.group("city")),
            pattern="title_city_company_is_hiring",
            confidence=0.95,
        )

    # Pattern 1b: Title Company City Salary/ЗП...
    pattern_1b = re.compile(
        r'^(?P<title>[A-Za-zА-Яа-я0-9+/#().,\- ]{4,120}?)\s+(?P<company>[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9&"«»()./\-+ ]{2,80}?)\s+(?P<city>Алматы|Астана|Нур-Султан|Nur-Sultan)\b.*?(?:\bЗП\b|\bзарплата\b|\bsalary\b)',
        flags=re.IGNORECASE,
    )
    match = pattern_1b.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=clean_header_city_candidate(match.group("city")),
            pattern="title_company_city_salary",
            confidence=0.9,
        )

    # Pattern 2: Должность: ... Компания: ... Город/Локация: ...
    pattern_2 = re.compile(
        r"(?is)(?:должность|вакансия)\s*:\s*(?P<title>.+?)\s+(?:компания)\s*:\s*(?P<company>.+?)\s+(?:город|локация|location)\s*:\s*(?P<city>.+?)(?:\s+(?:формат|занятость|оплата|зарплата)\s*:|$)"
    )
    match = pattern_2.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=clean_header_city_candidate(match.group("city")),
            pattern="labeled_title_company_city",
            confidence=0.97,
        )

    # Pattern 3: Компания X ищет ... на позицию Y
    pattern_3 = re.compile(
        r"(?is)(?:компания\s+)?(?P<company>[^.]{2,120}?)\s+ищет\b.+?\b(?:на\s+позицию|позиция|вакансия)\s*[:\-]?\s*(?P<title>[A-Za-zА-Яа-я0-9+/#().,\- ]{4,120})"
    )
    match = pattern_3.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=None,
            pattern="company_hiring_for_position",
            confidence=0.88,
        )

    # Pattern 3b: Команда/Company X в поисках Title
    pattern_3b = re.compile(
        r'(?is)(?:команда|company|компания)\s+(?P<company>[^.]{2,120}?)\s+(?:в\s+поисках|ищет)\s+(?P<title>[A-Za-zА-Яа-я0-9+/#().,\- ]{4,120})'
    )
    match = pattern_3b.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=None,
            pattern="company_searching_for_title",
            confidence=0.9,
        )

    # Pattern 4: Вакансия: Title Компания: ... Локация: ...
    pattern_4 = re.compile(
        r"(?is)(?:вакансия)\s*:\s*(?P<title>.+?)\s+(?:компания)\s*:\s*(?P<company>.+?)\s+(?:локация|город|location)\s*:\s*(?P<city>.+?)(?:\s+(?:формат|занятость|зарплата)\s*:|$)"
    )
    match = pattern_4.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=clean_header_city_candidate(match.group("city")),
            pattern="vacancy_company_location",
            confidence=0.97,
        )

    # Pattern 4b: Title Компания: ... Локация: ...
    pattern_4b = re.compile(
        r"(?is)^(?P<title>.+?)\s+(?:компания)\s*:\s*(?P<company>.+?)\s+(?:локация|город|location)\s*:\s*(?P<city>.+?)(?:\s+(?:формат|занятость|зарплата|резюме)\b|$)"
    )
    match = pattern_4b.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=clean_header_city_candidate(match.group("city")),
            pattern="title_company_location",
            confidence=0.94,
        )

    # Pattern 4c: Title, Company
    pattern_4c = re.compile(
        r'^(?P<title>[^,|]{4,120})\s*,\s*(?P<company>[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9&"«»()./\-+ ]{1,80})(?:\s*(?:\||г\.|алматы|астана|нур-султан|location|локация|зарплата|зп|основные)\b|$)',
        flags=re.IGNORECASE,
    )
    match = pattern_4c.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=None,
            pattern="title_comma_company",
            confidence=0.86,
        )

    # Pattern 4d: Title | City
    pattern_4d = re.compile(
        r'^(?P<title>[^|]{4,120})\|\s*(?P<city>Алматы|Астана|Нур-Султан|Nur-Sultan)\b',
        flags=re.IGNORECASE,
    )
    match = pattern_4d.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=None,
            city=clean_header_city_candidate(match.group("city")),
            pattern="title_pipe_city",
            confidence=0.84,
        )

    # Pattern 5: Company ищет ... разработчика / аналитика / инженера
    pattern_5 = re.compile(
        r"(?is)(?:компания\s+)?(?P<company>[^.]{2,120}?)\s+ищет\b.{0,80}?\b(?P<title>(?:backend|frontend|fullstack|java|python|golang|go|qa|devops|data|system|business|product|mobile|android|ios|ml)[^.!?]{0,80}?(?:разработчик|developer|engineer|аналитик|designer|manager))\b"
    )
    match = pattern_5.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=None,
            pattern="company_hiring_title_inline",
            confidence=0.84,
        )

    # Pattern 5b: Company требует/требуется Title
    pattern_5b = re.compile(
        r'(?is)(?:компания\s+)?(?P<company>[^.]{2,120}?)\s+(?:требуется|требуются|нужен|нужна)\s*[:\-]?\s*(?P<title>[A-Za-zА-Яа-я0-9+/#().,\- ]{4,120})'
    )
    match = pattern_5b.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=clean_header_company_candidate(match.group("company")),
            city=None,
            pattern="company_requires_title",
            confidence=0.88,
        )

    # Pattern 6: Title Формат/Резюме/Локация...
    pattern_6 = re.compile(
        r"(?is)^(?P<title>[A-Za-zА-Яа-я0-9+/#().,\- ]{4,120}?)\s+(?:формат|резюме|локация|город|location|зарплатная\s+вилка|зп)\b"
    )
    match = pattern_6.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=None,
            city=None,
            pattern="title_before_header_labels",
            confidence=0.82,
        )

    # Pattern 6b: Требуется Title ...
    pattern_6b = re.compile(
        r'(?is)^(?:требуется|нужен|нужна|ищем)\s+(?P<title>[A-Za-zА-Яа-я0-9+/#().,\- ]{4,120}?)(?:\s+(?:в|на)\s+(?:команду|позицию)\b|[.!?]|$)'
    )
    match = pattern_6b.search(header)
    if match:
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=None,
            city=None,
            pattern="required_title_only",
            confidence=0.83,
        )

    # Pattern 6c: We are looking for Title ... Company later in header
    pattern_6c = re.compile(
        r'(?is)(?:мы\s+ищем|ищем|we are looking for)\s+(?P<title>[A-Za-zА-Яа-я0-9+/#().,\- ]{4,120}?)(?:\s+в\s+нашу\s+команду|\!|\.|$)'
    )
    match = pattern_6c.search(header)
    if match:
        company_match = re.search(r'(?is)(?:т[оo]{2}|ао|ип)\s*["«]?[A-Za-zА-Яа-яЁё0-9&"«»()./\-+ ]{2,90}', header)
        company = clean_header_company_candidate(company_match.group(0)) if company_match else None
        return HeaderParseResult(
            title=clean_header_title_candidate(match.group("title")),
            company=company,
            city=None,
            pattern="looking_for_title",
            confidence=0.8,
        )

    # Pattern 7: Компания X ищет ...
    pattern_7 = re.compile(
        r"(?is)(?:компания\s+)?(?P<company>[^.]{2,120}?)\s+ищет\b"
    )
    match = pattern_7.search(header)
    if match:
        return HeaderParseResult(
            title=None,
            company=clean_header_company_candidate(match.group("company")),
            city=None,
            pattern="company_hiring_only",
            confidence=0.8,
        )

    return HeaderParseResult()


def infer_title_from_description(text: Any) -> Any:
    if not is_meaningful_text(text, min_len=20):
        return pd.NA
    source = str(text)
    header_result = parse_semistructured_header(source)
    if title_looks_valid(header_result.title):
        return header_result.title
    patterns = [
        re.compile(r"(?i)(?:ищем|нужен|нужна|требуется|vacancy|position|role)\s+([A-Za-zА-Яа-я0-9+/#().,\- ]{4,80})"),
        re.compile(r"(?i)\b([A-Za-zА-Яа-я0-9+/#().,\- ]{4,80})\s+(?:в команду|to join the team)\b"),
    ]
    for pattern in patterns:
        match = pattern.search(source)
        if not match:
            continue
        candidate = clean_title_text(match.group(1))
        if title_looks_valid(candidate):
            return candidate
    first_sentence = re.split(r"[.!?\n]", source, maxsplit=1)[0]
    if len(first_sentence.split()) <= 10 and any(
        term in first_sentence.lower()
        for term in [
            "developer",
            "engineer",
            "manager",
            "analyst",
            "designer",
            "разработчик",
            "аналитик",
            "менеджер",
            "инженер",
            "дизайнер",
        ]
    ):
        candidate = clean_title_text(first_sentence)
        if title_looks_valid(candidate):
            return candidate
    return pd.NA


def clean_company_value(value: Any) -> Any:
    if not is_meaningful_text(value, min_len=2):
        return pd.NA
    text = normalize_whitespace(value)
    text = re.sub(r"(?i)^(компания|company)\s*[:\-]\s*", "", text)
    text = text.strip(" -–—")
    company_map = {
        "kaspi": "Kaspi.kz",
        "kaspi.kz": "Kaspi.kz",
        "tele2 altel": "Tele2/Altel",
        "tele2/altel": "Tele2/Altel",
    }
    key = normalize_key(text)
    return company_map.get(key, text)


def is_company_suspicious(value: Any) -> bool:
    if not is_meaningful_text(value, min_len=2):
        return False
    text = str(value)
    punct_count = len(re.findall(r"[,:;!?()]", text))
    sentence_count = len(re.findall(r"[.!?]", text))
    return any(
        [
            len(text) > 120,
            sentence_count >= 2,
            punct_count >= 8,
            bool(CONTACT_KEYWORD_PATTERN.search(text)),
            bool(re.search(r"\+?\d[\d\-\s()]{8,}\d", text)),
            len(text.split()) > 20,
        ]
    )


# %%
def build_second_pass_dedup(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["source_priority_v2"] = work["source"].map(SOURCE_PRIORITY).fillna(0).astype(int)
    work["posted_at_dt"] = pd.to_datetime(work["posted_at"], errors="coerce", utc=True)
    work["posted_week_bucket"] = work["posted_at_dt"].dt.tz_convert(None).dt.to_period("W").astype(str)
    work["title_key_v2"] = work["title_final"].map(normalize_key)
    work["company_key_v2"] = work["company_clean"].map(normalize_key)
    work["city_key_v2"] = work["city_norm"].fillna("unknown")
    work["category_key_v2"] = work["category_filled"].fillna("unknown")
    work["description_key_v2"] = (
        work["description_clean_v2"]
        .fillna("")
        .astype(str)
        .map(lambda value: md5_text(normalize_key(value)[:500])[:12] if value else "none")
    )

    dedup_keys: list[str] = []
    for _, row in work.iterrows():
        title_key = row["title_key_v2"]
        company_key = row["company_key_v2"]
        if title_key and company_key:
            dedup_basis = [title_key, company_key, row["city_key_v2"], row["category_key_v2"], row["posted_week_bucket"]]
        else:
            dedup_basis = [title_key, row["city_key_v2"], row["category_key_v2"], row["description_key_v2"], row["posted_week_bucket"]]
        dedup_keys.append(md5_text("|".join(dedup_basis)))
    work["dedup_key_v2"] = dedup_keys

    group_sizes = work.groupby("dedup_key_v2")["id"].transform("size")
    work["same_role_duplicate_group"] = np.where(group_sizes > 1, work["dedup_key_v2"], pd.NA)
    work["is_duplicate_v2"] = (group_sizes > 1) | work["is_duplicate"].fillna(False).astype(bool)

    completeness_fields = [
        "title_final",
        "company_clean",
        "city_norm",
        "category_filled",
        "level_filled",
        "hard_skills_clean",
        "requirements_clean",
        "responsibilities_clean",
    ]
    work["_completeness_score_v2"] = work[completeness_fields].apply(lambda row: sum(not is_missing_like(value) for value in row), axis=1)
    work["_dedup_priority_score_v2"] = (
        work["source_priority_v2"] * 100
        + (~work["llm_review_flag"].fillna(False)).astype(int) * 20
        + work["salary_usable_for_analytics"].fillna(False).astype(int) * 10
        + work["skills_count"].fillna(0).astype(int)
        + work["_completeness_score_v2"].astype(int) * 2
        + work["description_clean_len"].fillna(0).astype(int) / 1000
        + work["llm_confidence"].fillna(0.0)
    )
    work["_dedup_rank_v2"] = work.groupby("dedup_key_v2")["_dedup_priority_score_v2"].rank(method="first", ascending=False)
    work["dedup_keep_for_analytics"] = (~work["is_duplicate_v2"]) | (work["_dedup_rank_v2"] == 1)

    return work


def assign_quality_tier(row: pd.Series) -> str:
    structured = bool(row.get("is_structured_source"))
    duplicate_not_kept = bool(row.get("is_duplicate_v2")) and not bool(row.get("dedup_keep_for_analytics"))
    severe = bool(
        duplicate_not_kept
        or row.get("salary_contact_leak_flag")
        or (row.get("company_is_suspicious") and is_missing_like(row.get("company_clean")))
    )
    if severe:
        return "D"

    core_ok = all(
        [
            is_meaningful_text(row.get("title_final"), min_len=3),
            is_meaningful_text(row.get("category_filled"), min_len=3),
            is_meaningful_text(row.get("city_norm"), min_len=3),
        ]
    )
    no_major_flags = not bool(row.get("llm_review_flag")) and not bool(row.get("salary_is_suspicious")) and not bool(row.get("company_is_suspicious"))
    if structured and bool(row.get("dedup_keep_for_analytics")) and core_ok and no_major_flags:
        return "A"
    if bool(row.get("dedup_keep_for_analytics")) and core_ok and not bool(row.get("company_is_suspicious")):
        return "B"
    if is_meaningful_text(row.get("description_clean_v2"), min_len=30) and (
        is_meaningful_text(row.get("category_filled"), min_len=3) or row.get("skills_count", 0) > 0
    ):
        return "C"
    return "D"


# %%
def build_quality_report(df_before: pd.DataFrame, df_after: pd.DataFrame, discovery_report: dict[str, Any]) -> dict[str, Any]:
    def coverage(series: pd.Series) -> float:
        return round((1 - count_missing_like(series) / len(series)) * 100, 2)

    def unique_skills_count(series: pd.Series) -> int:
        counter: set[str] = set()
        for value in series.dropna():
            for item in safe_json_loads(value, []):
                counter.add(str(item))
        return len(counter)

    key_before_fields = ["category", "level", "company", "salary_from", "salary_to", "description_clean", "english_level"]
    key_after_fields = ["category_filled", "level_filled", "company_clean", "salary_from_clean", "salary_to_clean", "description_clean_v2", "english_level_norm"]

    before_missingness = {field: coverage(df_before[field]) for field in key_before_fields}
    after_missingness = {field: coverage(df_after[field]) for field in key_after_fields}

    report = {
        "input_path": str(INPUT_PATH.name),
        "output_path": str(ANALYSIS_READY_PATH.name),
        "row_count_before": int(len(df_before)),
        "row_count_after": int(len(df_after)),
        "column_count_before": int(len(df_before.columns)),
        "column_count_after": int(len(df_after.columns)),
        "discovery_report": discovery_report,
        "coverage_before_pct": before_missingness,
        "coverage_after_pct": after_missingness,
        "description_clean_v2": {
            "changed_rows": int(df_after["description_clean_changed"].fillna(False).sum()),
            "avg_length": round(float(df_after["description_clean_len"].fillna(0).mean()), 2),
            "removed_chars_total": int(df_after["description_clean_removed_chars"].fillna(0).sum()),
        },
        "salary_cleaning": {
            "usable_for_analytics_rows": int(df_after["salary_usable_for_analytics"].fillna(False).sum()),
            "suspicious_rows": int(df_after["salary_is_suspicious"].fillna(False).sum()),
            "outlier_flag_rows": int(df_after["salary_outlier_flag"].fillna(False).sum()),
            "contact_leak_rows": int(df_after["salary_contact_leak_flag"].fillna(False).sum()),
            "zero_flag_rows": int(df_after["salary_zero_flag"].fillna(False).sum()),
        },
        "company_cleaning": {
            "suspicious_rows": int(df_after["company_is_suspicious"].fillna(False).sum()),
            "usable_for_employer_analytics_rows": int(df_after["usable_for_employer_analytics"].fillna(False).sum()),
        },
        "deduplication": {
            "original_duplicate_rows": int(df_after["is_duplicate"].fillna(False).sum()),
            "duplicate_rows_v2": int(df_after["is_duplicate_v2"].fillna(False).sum()),
            "kept_for_analytics_rows": int(df_after["dedup_keep_for_analytics"].fillna(False).sum()),
        },
        "category_level_backfill": {
            "category_coverage_before": coverage(df_before["category"]),
            "category_coverage_after": coverage(df_after["category_filled"]),
            "level_coverage_before": coverage(df_before["level"]),
            "level_coverage_after": coverage(df_after["level_filled"]),
        },
        "skills": {
            "hard_skills_unique_before": unique_skills_count(df_before["hard_skills"]),
            "hard_skills_unique_after": unique_skills_count(df_after["hard_skills_clean"]),
            "rows_with_skills_after": int(df_after["skills_count"].fillna(0).gt(0).sum()),
        },
        "quality_tier_distribution": df_after["quality_tier"].value_counts(dropna=False).to_dict(),
        "analytics_usability": {
            "usable_for_salary_analytics": int(df_after["usable_for_salary_analytics"].fillna(False).sum()),
            "usable_for_skill_analytics": int(df_after["usable_for_skill_analytics"].fillna(False).sum()),
            "usable_for_employer_analytics": int(df_after["usable_for_employer_analytics"].fillna(False).sum()),
            "usable_for_category_analytics": int(df_after["usable_for_category_analytics"].fillna(False).sum()),
        },
    }
    return report


def build_header_parse_audit(df: pd.DataFrame) -> dict[str, Any]:
    tele = df[df["is_telegram_source"] == True].copy()
    matched = tele[tele["header_parse_pattern"] != "no_match"].copy()
    still_bad = tele[tele["title_final"].isna() | tele["company_clean"].isna()].copy()

    def compact_header(text: Any) -> str:
        return extract_header_window(text, max_len=220)

    matched["header_window"] = matched["description_clean_v2"].map(compact_header)
    still_bad["header_window"] = still_bad["description_clean_v2"].map(compact_header)

    pattern_examples: dict[str, list[dict[str, Any]]] = {}
    for pattern, group in matched.groupby("header_parse_pattern", dropna=False):
        examples = group[
            [
                "id",
                "source",
                "header_window",
                "header_extracted_title",
                "header_extracted_company",
                "header_extracted_city",
                "title_final",
                "company_clean",
            ]
        ].head(5)
        pattern_examples[str(pattern)] = examples.to_dict(orient="records")

    report = {
        "telegram_rows": int(len(tele)),
        "matched_rows": int(len(matched)),
        "matched_pct": round((len(matched) / len(tele) * 100), 2) if len(tele) else 0.0,
        "pattern_counts": matched["header_parse_pattern"].value_counts(dropna=False).to_dict(),
        "pattern_examples": pattern_examples,
        "still_bad_rows": int(len(still_bad)),
        "still_bad_pct": round((len(still_bad) / len(tele) * 100), 2) if len(tele) else 0.0,
        "still_bad_top_headers": still_bad["header_window"].value_counts().head(30).to_dict(),
        "still_bad_sample": still_bad[
            [
                "id",
                "source",
                "header_parse_pattern",
                "header_window",
                "title_final",
                "company_clean",
                "category_filled",
                "level_filled",
            ]
        ]
        .head(50)
        .to_dict(orient="records"),
    }
    return report


def header_audit_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Header Parse Mini Audit",
        "",
        "## Coverage",
        f"- Telegram rows: `{report['telegram_rows']:,}`",
        f"- Matched header rows: `{report['matched_rows']:,}`",
        f"- Matched share: `{report['matched_pct']}%`",
        f"- Still-bad rows (`title_final` or `company_clean` missing): `{report['still_bad_rows']:,}`",
        f"- Still-bad share: `{report['still_bad_pct']}%`",
        "",
        "## Pattern Counts",
    ]
    for pattern, count in report["pattern_counts"].items():
        lines.append(f"- `{pattern}`: `{count:,}`")

    lines.extend(["", "## Top Unresolved Header Windows"])
    for header, count in report["still_bad_top_headers"].items():
        lines.append(f"- `{count}`: {header}")

    lines.extend(["", "## Pattern Examples"])
    for pattern, examples in report["pattern_examples"].items():
        lines.append(f"### {pattern}")
        for example in examples[:3]:
            lines.append(
                f"- `{example['id']}` | title=`{example['header_extracted_title']}` | company=`{example['header_extracted_company']}` | city=`{example['header_extracted_city']}`"
            )
            lines.append(f"  header: {example['header_window']}")
    return "\n".join(lines) + "\n"


def report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Data Quality Report",
        "",
        "## Dataset Shape",
        f"- Rows before: `{report['row_count_before']:,}`",
        f"- Rows after: `{report['row_count_after']:,}`",
        f"- Columns before: `{report['column_count_before']}`",
        f"- Columns after: `{report['column_count_after']}`",
        "",
        "## Coverage Before/After",
    ]
    for field, value in report["coverage_before_pct"].items():
        after_field = {
            "category": "category_filled",
            "level": "level_filled",
            "company": "company_clean",
            "salary_from": "salary_from_clean",
            "salary_to": "salary_to_clean",
            "description_clean": "description_clean_v2",
            "english_level": "english_level_norm",
        }[field]
        lines.append(
            f"- `{field}`: `{value}%` -> `{report['coverage_after_pct'][after_field]}%`"
        )
    lines.extend(
        [
            "",
            "## Cleaning Counters",
            f"- `description_clean_v2` changed rows: `{report['description_clean_v2']['changed_rows']:,}`",
            f"- Salary suspicious rows: `{report['salary_cleaning']['suspicious_rows']:,}`",
            f"- Salary contact leak rows: `{report['salary_cleaning']['contact_leak_rows']:,}`",
            f"- Salary outlier rows: `{report['salary_cleaning']['outlier_flag_rows']:,}`",
            f"- Salary usable rows: `{report['salary_cleaning']['usable_for_analytics_rows']:,}`",
            f"- Suspicious company rows: `{report['company_cleaning']['suspicious_rows']:,}`",
            f"- Original duplicate rows: `{report['deduplication']['original_duplicate_rows']:,}`",
            f"- Duplicate rows v2: `{report['deduplication']['duplicate_rows_v2']:,}`",
            f"- Analytics-kept rows: `{report['deduplication']['kept_for_analytics_rows']:,}`",
            "",
            "## Skills",
            f"- Unique hard skills before: `{report['skills']['hard_skills_unique_before']:,}`",
            f"- Unique hard skills after: `{report['skills']['hard_skills_unique_after']:,}`",
            f"- Rows with cleaned skills: `{report['skills']['rows_with_skills_after']:,}`",
            "",
            "## Quality Tiers",
        ]
    )
    for tier, count in report["quality_tier_distribution"].items():
        lines.append(f"- `{tier}`: `{count:,}`")
    lines.extend(
        [
            "",
            "## Analytics Usability",
            f"- Salary analytics rows: `{report['analytics_usability']['usable_for_salary_analytics']:,}`",
            f"- Skill analytics rows: `{report['analytics_usability']['usable_for_skill_analytics']:,}`",
            f"- Employer analytics rows: `{report['analytics_usability']['usable_for_employer_analytics']:,}`",
            f"- Category analytics rows: `{report['analytics_usability']['usable_for_category_analytics']:,}`",
        ]
    )
    return "\n".join(lines) + "\n"


# %%
def build_skills_mart(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    skill_specs = [
        ("hard_skills_clean", "hard_skill"),
        ("soft_skills_clean", "soft_skill"),
        ("tech_stack_clean", "tech_stack"),
    ]
    for _, row in df.iterrows():
        for column, skill_type in skill_specs:
            for skill in safe_json_loads(row.get(column), []):
                rows.append(
                    {
                        "job_id": row["id"],
                        "skill": skill,
                        "skill_type": skill_type,
                        "category_norm": row.get("category_filled"),
                        "level_norm": row.get("level_filled"),
                        "source": row.get("source"),
                        "city_norm": row.get("city_norm"),
                        "posted_at": row.get("posted_at"),
                    }
                )
    return pd.DataFrame(rows)


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
        "salary_parse_quality",
        "salary_fix_flags",
        "posted_at",
    ]
    mart = df[df["usable_for_salary_analytics"].fillna(False)].copy()
    return mart[columns]


def build_entity_mart(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "id",
        "source",
        "title_final",
        "title_is_inferred",
        "company_clean",
        "company_is_suspicious",
        "category_filled",
        "level_filled",
        "city_norm",
        "employment_norm",
        "work_format_norm",
        "quality_tier",
        "dedup_keep_for_analytics",
        "posted_at",
    ]
    return df[columns].copy()


# %%
def prepare_analysis_ready_dataset() -> tuple[pd.DataFrame, dict[str, Any]]:
    df_raw = read_csv_with_fallback(INPUT_PATH)
    df = standardize_missing_like_dataframe(df_raw)

    discovery_report = audit_dataframe(df)
    print_discovery_summary(discovery_report)

    df["is_telegram_source"] = ~df["source"].isin(STRUCTURED_SOURCES)
    df["is_structured_source"] = df["source"].isin(STRUCTURED_SOURCES)

    description_results = df["description"].map(clean_description_v2)
    df["description_clean_v2"] = description_results.map(lambda item: item[0])
    df["description_clean_changed"] = description_results.map(lambda item: item[1]).astype(bool)
    df["description_clean_len"] = description_results.map(lambda item: item[2]).astype("Int64")
    df["description_clean_removed_chars"] = description_results.map(lambda item: item[3]).astype("Int64")

    header_parse_results = df["description_clean_v2"].map(parse_semistructured_header)
    df["header_extracted_title"] = [result.title for result in header_parse_results]
    df["header_extracted_company"] = [result.company for result in header_parse_results]
    df["header_extracted_city"] = [result.city for result in header_parse_results]
    df["header_parse_pattern"] = [result.pattern for result in header_parse_results]
    df["header_parse_confidence"] = [result.confidence for result in header_parse_results]

    salary_results = df.apply(build_salary_clean_result, axis=1)
    df["salary_from_clean"] = [result.salary_from_clean for result in salary_results]
    df["salary_to_clean"] = [result.salary_to_clean for result in salary_results]
    df["salary_avg_clean"] = [result.salary_avg_clean for result in salary_results]
    df["currency_clean"] = [result.currency_clean for result in salary_results]
    df["salary_parse_quality"] = [result.salary_parse_quality for result in salary_results]
    df["salary_is_suspicious"] = [result.salary_is_suspicious for result in salary_results]
    df["salary_outlier_flag"] = [result.salary_outlier_flag for result in salary_results]
    df["salary_contact_leak_flag"] = [result.salary_contact_leak_flag for result in salary_results]
    df["salary_zero_flag"] = [result.salary_zero_flag for result in salary_results]
    df["salary_usable_for_analytics"] = [result.salary_usable_for_analytics for result in salary_results]
    df["salary_fix_flags"] = [json_dumps_or_na(result.salary_fix_flags) for result in salary_results]
    df["salary_parse_source"] = [result.salary_parse_source for result in salary_results]

    df["english_level_norm"] = df["english_level"].map(normalize_english_level)
    df["english_level_invalid_flag"] = df["english_level"].notna() & df["english_level_norm"].isna()
    df["category_norm"] = df["category"].map(normalize_category)
    df["level_norm"] = df["level"].map(normalize_level)
    df["employment_norm"] = df["employment"].map(normalize_employment)
    df["work_format_norm"] = df["work_format"].map(normalize_work_format)
    df["city_norm"] = df["city"].map(normalize_city)
    df["city_source_v2"] = np.where(df["city_norm"].notna(), "existing_city", "missing")
    header_city_norm = df["header_extracted_city"].map(clean_header_city_candidate)
    city_backfill_mask = df["city_norm"].isna() & header_city_norm.notna()
    df.loc[city_backfill_mask, "city_norm"] = header_city_norm.loc[city_backfill_mask]
    df.loc[city_backfill_mask, "city_source_v2"] = "header_parse"
    df["currency_clean"] = df.apply(
        lambda row: row["currency_clean"] if row["currency_clean"] in VALID_CURRENCY_VALUES else normalize_currency(row["currency"], row["salary_raw"]),
        axis=1,
    )

    df["_hard_skills_list_raw"] = df["hard_skills"].map(parse_json_list)
    df["_soft_skills_list_raw"] = df["soft_skills"].map(parse_json_list)
    df["_tech_stack_list_raw"] = df["tech_stack"].map(parse_json_list)

    df["title_clean"] = df["title"].map(clean_title_text)
    title_normalized_clean = df["title_normalized"].map(clean_title_text)
    header_title_clean = df["header_extracted_title"].map(clean_header_title_candidate)

    title_final: list[Any] = []
    title_is_inferred: list[bool] = []
    title_source_v2: list[str] = []
    for _, row in df.iterrows():
        raw_title = row.get("title_clean")
        normalized_title = title_normalized_clean.loc[row.name]
        header_title = header_title_clean.loc[row.name]
        inferred_from_description = infer_title_from_description(row.get("description_clean_v2"))
        if is_meaningful_text(raw_title, min_len=3):
            title_final.append(normalize_title_variant(raw_title))
            title_is_inferred.append(False)
            title_source_v2.append("raw_title")
        elif is_meaningful_text(normalized_title, min_len=3):
            title_final.append(normalize_title_variant(normalized_title))
            title_is_inferred.append(True)
            title_source_v2.append("title_normalized")
        elif title_looks_valid(header_title):
            title_final.append(normalize_title_variant(header_title))
            title_is_inferred.append(True)
            title_source_v2.append("header_parse")
        elif is_meaningful_text(inferred_from_description, min_len=3):
            title_final.append(normalize_title_variant(inferred_from_description))
            title_is_inferred.append(True)
            title_source_v2.append("description_rule")
        else:
            title_final.append(pd.NA)
            title_is_inferred.append(False)
            title_source_v2.append("missing")
    df["title_final"] = title_final
    df["title_is_inferred"] = title_is_inferred
    df["title_source_v2"] = title_source_v2

    company_clean: list[Any] = []
    company_source_v2: list[str] = []
    company_is_suspicious: list[bool] = []
    header_company_clean = df["header_extracted_company"].map(clean_header_company_candidate)
    for _, row in df.iterrows():
        raw_company = row.get("company")
        header_company = header_company_clean.loc[row.name]
        cleaned = clean_company_value(raw_company)
        chosen_company = cleaned if is_meaningful_text(cleaned, min_len=2) else header_company
        suspicious = is_company_suspicious(chosen_company)
        company_is_suspicious.append(suspicious)
        if suspicious:
            company_clean.append(pd.NA)
            company_source_v2.append("dropped_suspicious")
        elif is_meaningful_text(cleaned, min_len=2):
            company_clean.append(cleaned)
            company_source_v2.append("cleaned_existing")
        elif is_meaningful_text(header_company, min_len=2):
            company_clean.append(header_company)
            company_source_v2.append("header_parse")
        else:
            company_clean.append(pd.NA)
            company_source_v2.append("missing")
    df["company_clean"] = company_clean
    df["company_is_suspicious"] = company_is_suspicious
    df["company_source_v2"] = company_source_v2

    context_series = df.apply(combine_context_text, axis=1)
    df["_hard_skills_list_clean"] = [
        canonicalize_skill_list(items, context_text=context)
        for items, context in zip(df["_hard_skills_list_raw"], context_series, strict=False)
    ]
    df["_soft_skills_list_clean"] = [
        canonicalize_skill_list(items, context_text=context)
        for items, context in zip(df["_soft_skills_list_raw"], context_series, strict=False)
    ]
    df["_tech_stack_list_clean"] = [
        canonicalize_skill_list(items, context_text=context)
        for items, context in zip(df["_tech_stack_list_raw"], context_series, strict=False)
    ]
    df["_skills_all_list"] = [
        canonicalize_skill_list(hard + tech + soft, context_text=context)
        for hard, tech, soft, context in zip(
            df["_hard_skills_list_clean"],
            df["_tech_stack_list_clean"],
            df["_soft_skills_list_clean"],
            context_series,
            strict=False,
        )
    ]
    df["hard_skills_clean"] = df["_hard_skills_list_clean"].map(json_dumps_or_na)
    df["soft_skills_clean"] = df["_soft_skills_list_clean"].map(json_dumps_or_na)
    df["tech_stack_clean"] = df["_tech_stack_list_clean"].map(json_dumps_or_na)
    df["skills_all_clean"] = df["_skills_all_list"].map(json_dumps_or_na)
    df["skills_count"] = df["_skills_all_list"].map(len).astype("Int64")
    df["top_skill_family"] = df["_skills_all_list"].map(determine_top_skill_family)

    category_results = df.apply(infer_category, axis=1)
    df["category_filled"] = [item[0] for item in category_results]
    df["category_source_v2"] = [item[1] for item in category_results]
    df["category_confidence_v2"] = [item[2] for item in category_results]

    level_results = df.apply(infer_level, axis=1)
    df["level_filled"] = [item[0] for item in level_results]
    df["level_source_v2"] = [item[1] for item in level_results]
    df["level_confidence_v2"] = [item[2] for item in level_results]

    internship_markers = (
        context_series.str.lower().str.contains(r"\b(?:intern|internship|trainee|стажер|стажёр|стажировка)\b", regex=True)
        | df["employment_norm"].eq("internship")
        | df["level_filled"].eq("intern")
    )
    df["internship_flag_v2"] = internship_markers.fillna(False)
    df["internship_consistency_flag"] = np.select(
        [
            df["employment_norm"].eq("internship") & df["level_filled"].eq("intern"),
            df["employment_norm"].eq("internship") & ~df["level_filled"].eq("intern"),
            df["level_filled"].eq("intern") & ~df["employment_norm"].eq("internship"),
        ],
        ["consistent", "employment_without_intern_level", "intern_level_without_internship_employment"],
        default="not_applicable",
    )

    df = build_second_pass_dedup(df)

    df["quality_tier"] = df.apply(assign_quality_tier, axis=1)
    df["usable_for_salary_analytics"] = df["salary_usable_for_analytics"] & df["dedup_keep_for_analytics"].fillna(False)
    df["usable_for_employer_analytics"] = (
        df["dedup_keep_for_analytics"].fillna(False)
        & df["company_clean"].notna()
        & ~df["company_is_suspicious"].fillna(False)
    )
    df["usable_for_skill_analytics"] = (
        df["dedup_keep_for_analytics"].fillna(False)
        & df["skills_count"].fillna(0).gt(0)
        & df["description_clean_v2"].notna()
    )
    df["usable_for_category_analytics"] = (
        df["dedup_keep_for_analytics"].fillna(False)
        & df["category_filled"].notna()
    )

    object_json_columns = [
        "hard_skills_clean",
        "soft_skills_clean",
        "tech_stack_clean",
        "skills_all_clean",
        "salary_fix_flags",
    ]
    for column in object_json_columns:
        df[column] = df[column].astype("object")

    temp_columns = [
        "_hard_skills_list_raw",
        "_soft_skills_list_raw",
        "_tech_stack_list_raw",
        "_hard_skills_list_clean",
        "_soft_skills_list_clean",
        "_tech_stack_list_clean",
        "_skills_all_list",
        "_completeness_score_v2",
        "_dedup_priority_score_v2",
        "_dedup_rank_v2",
        "title_key_v2",
        "company_key_v2",
        "city_key_v2",
        "category_key_v2",
        "description_key_v2",
        "source_priority_v2",
        "posted_at_dt",
        "posted_week_bucket",
    ]
    df = df.drop(columns=[column for column in temp_columns if column in df.columns])

    quality_report = build_quality_report(df_raw, df, discovery_report)
    return df, quality_report


# %%
def main() -> None:
    df_final, quality_report = prepare_analysis_ready_dataset()
    header_audit_report = build_header_parse_audit(df_final)
    still_bad_rows = df_final[
        (df_final["is_telegram_source"] == True)
        & (df_final["title_final"].isna() | df_final["company_clean"].isna())
    ].copy()

    print("Exporting curated analytical layer and marts...")
    df_final.to_csv(ANALYSIS_READY_PATH, index=False, encoding="utf-8")
    build_salary_mart(df_final).to_csv(SALARY_MART_PATH, index=False, encoding="utf-8")
    build_skills_mart(df_final).to_csv(SKILLS_MART_PATH, index=False, encoding="utf-8")
    build_entity_mart(df_final).to_csv(ENTITY_MART_PATH, index=False, encoding="utf-8")
    QUALITY_REPORT_JSON_PATH.write_text(json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8")
    QUALITY_REPORT_MD_PATH.write_text(report_to_markdown(quality_report), encoding="utf-8")
    HEADER_AUDIT_JSON_PATH.write_text(json.dumps(header_audit_report, ensure_ascii=False, indent=2), encoding="utf-8")
    HEADER_AUDIT_MD_PATH.write_text(header_audit_to_markdown(header_audit_report), encoding="utf-8")
    still_bad_rows.to_csv(STILL_BAD_ROWS_PATH, index=False, encoding="utf-8")

    print("Done.")
    print(f"- analysis_ready_jobs.csv: {ANALYSIS_READY_PATH}")
    print(f"- jobs_salary_clean.csv: {SALARY_MART_PATH}")
    print(f"- jobs_skills_clean.csv: {SKILLS_MART_PATH}")
    print(f"- jobs_entity_clean.csv: {ENTITY_MART_PATH}")
    print(f"- data_quality_report.json: {QUALITY_REPORT_JSON_PATH}")
    print(f"- data_quality_report.md: {QUALITY_REPORT_MD_PATH}")
    print(f"- header_parse_audit.json: {HEADER_AUDIT_JSON_PATH}")
    print(f"- header_parse_audit.md: {HEADER_AUDIT_MD_PATH}")
    print(f"- still_bad_rows.csv: {STILL_BAD_ROWS_PATH}")


if __name__ == "__main__":
    main()
