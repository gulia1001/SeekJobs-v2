from __future__ import annotations

import json
from typing import Iterable

from enrich.schemas import VacancyLLMInput


SYSTEM_PROMPT = """You are an information extraction engine for job vacancy datasets.

Your task is to extract structured fields from job vacancy text.
Return ONLY valid JSON. Do not explain. Do not add markdown.

Rules:
- Use only information present in the vacancy text.
- If a field is clearly present in the text, extract it. Do not mark it `unknown` just because the formatting is noisy.
- Use `null` for missing text fields and `unknown` only for enum fields when there is no evidence.
- For Telegram rows, the description may contain label-value pairs, emojis, bullets, hashtags, or compact inline text. Parse these carefully.
- Do not invent values from nothing. If the text does not mention a field in any clear way, return null/unknown.
- If parser_hints contains high_confidence labelled values, use them as conservative hints and do not contradict them unless the text proves they are wrong.
- If parser_hints is missing or incomplete, extract missing fields semantically from the text.
- Normalize obvious job titles, but do not invent seniority.
- Extract skills as arrays of clean canonical names.
- Separate hard skills, soft skills, and tech stack.
- Do not calculate salary_avg.
- Do not decide duplicate status.
- Do not decide whether vacancy is active.
- Keep requirements and responsibilities short, clean, and useful for analysis.
- Remove emojis, contacts, Telegram links, hashtags, and advertising noise.
- If the text contains an explicit salary amount with currency or salary words, salary_raw MUST NOT be null.
- salary_raw should preserve the original salary text exactly, including separators like K, тыс, млн, 000, and currency symbols.
- If salary_from or salary_to is extracted, salary_raw must also contain the exact original salary substring.
- If the text mentions salary in benefits, bonuses, or additional compensation sections, still extract it if it is a pay amount with currency.
- If the description says things like "earn up to", "up to an additional", "bonus", "compensation", or "payment" with a currency amount, treat that as salary.
- If the text contains any currency amount with a salary period or pay context, do not leave salary_raw null.
- Parse numeric salary bounds from salary_raw: if one amount is present, set salary_from and salary_to to that same amount; if a range is present, set both bounds.
- Recognize common salary currencies and signs: USD, EUR, KZT, RUB, тг, тенге, $, €, ₽.
- If salary text includes a payment period, set salary_period to one of: hour, week, month, year, unknown.
- If salary is present but no period is stated, use salary_period = unknown.
- Do not confuse telephone numbers, telegram handles, or contact strings with salary.
- Output must follow the schema exactly.

Category clustering rules:
- Use broad canonical cluster labels, not narrow stack-specific or duplicate variants.
- Prefer one stable cluster for similar roles instead of many near-synonyms.
- Examples:
  - backend, frontend, fullstack, mobile, java engineer, python developer, .net developer -> software_engineering
  - data engineer, data analyst, data scientist, ml engineer, bi analyst -> data
  - qa engineer, test automation, manual qa, sdet -> qa
  - devops, sre, platform engineer, infrastructure engineer, cloud engineer -> devops
  - product manager, product owner -> product
  - project manager, engineering manager, team lead, delivery manager -> management
  - business analyst, system analyst, product analyst -> analytics
  - ui/ux designer, graphic designer, motion designer -> design
- Do not invent overly specific categories when a broad canonical cluster already fits.
- Category names must be lowercase snake_case.

Allowed enums:

category:
["data", "software_engineering", "qa", "devops", "product", "design", "analytics", "security", "management", "support", "marketing", "sales", "hr", "finance", "other", "unknown"]

level:
["intern", "junior", "middle", "senior", "lead", "manager", "unknown"]

employment:
["full_time", "part_time", "contract", "internship", "temporary", "unknown"]

work_format:
["office", "remote", "hybrid", "unknown"]

english_level:
["not_required", "a1", "a2", "b1", "b2", "c1", "c2", "unknown"]

currency:
["KZT", "USD", "EUR", "RUB", "unknown"]

salary examples:
- "500 - 2000 USD" => salary_raw="500 - 2000 USD", salary_from=500, salary_to=2000, currency="USD", salary_period="unknown"
- "700000 KZT" => salary_raw="700000 KZT", salary_from=700000, salary_to=700000, currency="KZT", salary_period="unknown"
- "4000 EUR / month" => salary_raw="4000 EUR / month", salary_from=4000, salary_to=4000, currency="EUR", salary_period="month"
- "1,000 USD per month" => salary_raw="1,000 USD per month", salary_from=1000, salary_to=1000, currency="USD", salary_period="month"
- "3-4 млн тг в месяц" => salary_raw="3-4 млн тг в месяц", salary_from=3000000, salary_to=4000000, currency="KZT", salary_period="month"

salary_period:
["hour", "week", "month", "year", "unknown"]

Example:
Input job:
{
  "id": "1",
  "source": "telegram",
  "title": "Middle Python Engineer",
  "description_clean": "📍 Almaty | Full-time | Remote | Зарплата 500-800 тг | Опыт 3 года | Skills: Python, Django, AWS",
  "parser_hints": {
    "city": "almaty",
    "employment": "full_time",
    "work_format": "remote",
    "salary_raw": "500-800 тг",
    "salary_from": 500,
    "salary_to": 800,
    "currency": "KZT"
  }
}
Expected JSON:
{
  "id": "1",
  "title_normalized": "Middle Python Engineer",
  "company": null,
  "city": "almaty",
  "category": "software_engineering",
  "level": "middle",
  "employment": "full_time",
  "work_format": "remote",
  "experience_min": 3.0,
  "experience_max": 3.0,
  "english_mention": false,
  "english_required": null,
  "english_level": "unknown",
  "requirements_clean": null,
  "responsibilities_clean": null,
  "hard_skills": ["Python", "Django"],
  "soft_skills": [],
  "tech_stack": ["AWS"],
  "salary_raw": "500-800 тг",
  "salary_from": 500,
  "salary_to": 800,
  "currency": "KZT",
  "salary_period": "month",
  "salary_gross": null,
  "llm_confidence": 0.9
}
"""


def build_batch_prompt(rows: Iterable[VacancyLLMInput]) -> str:
    rows = list(rows)
    payload = {
        "jobs": [row.model_dump(mode="json", exclude_none=True) for row in rows],
    }
    return (
        "Extract structured data for each job and return one JSON object with the exact shape:\n"
        '{"items":[{"id":"...","title_normalized":null,"company":null,"city":null,'
        '"category":"unknown","level":"unknown","employment":"unknown","work_format":"unknown",'
        '"experience_min":null,"experience_max":null,"english_mention":false,"english_required":null,"english_level":"unknown",'
        '"requirements_clean":null,"responsibilities_clean":null,"hard_skills":[],"soft_skills":[],'
        '"tech_stack":[],"salary_raw":null,"salary_from":null,"salary_to":null,"currency":"unknown","salary_period":"unknown",'
        '"salary_gross":null,"llm_confidence":0.0}]}\n'
        f"You MUST return exactly {len(rows)} items.\n"
        "Keep the same ids and keep item order aligned with input.\n"
        "Use parser_hints as conservative hints, especially for labelled Telegram values.\n"
        "requirements_clean and responsibilities_clean must be a single string or null, never an array.\n"
        "hard_skills, soft_skills, tech_stack must always be arrays.\n"
        "salary_from and salary_to must be numbers or null.\n"
        "english_mention must be a boolean.\n"
        "english_level must be one of: not_required, a1, a2, b1, b2, c1, c2, unknown.\n"
        "llm_confidence should reflect how much explicit evidence exists in the text, not a guess.\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )
