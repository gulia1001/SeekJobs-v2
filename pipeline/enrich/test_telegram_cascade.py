from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from enrich.telegram_prefill import (
    reconcile_prefill_and_llm,
    telegram_prefill_extract,
    telegram_prefill_quality,
    validate_final_telegram_record,
)


def run_case(name: str, text: str, llm_result: dict, expected: dict) -> None:
    prefill = telegram_prefill_extract(text)
    quality = telegram_prefill_quality(prefill, text)
    reconciled = reconcile_prefill_and_llm(quality, llm_result)
    validated = validate_final_telegram_record(reconciled)

    for field, value in expected.items():
        assert validated.get(field) == value, (
            f"{name}: field={field!r}, expected={value!r}, got={validated.get(field)!r}"
        )


def main() -> None:
    run_case(
        name="labelled_fields",
        text=(
            "Компания: Internet Company PS\n"
            "Город: Алматы\n"
            "Формат: удаленный/гибрид\n"
            "Занятость: полная\n"
            "Зарплата: до 1 000 000 тг\n"
            "Опыт: от 2 лет"
        ),
        llm_result={
            "company": None,
            "city": None,
            "employment": "unknown",
            "work_format": "unknown",
            "salary_raw": None,
            "salary_from": None,
            "salary_to": None,
            "currency": "unknown",
            "experience_min": None,
            "experience_max": None,
            "category": "software_engineering",
            "title_normalized": "Python Developer",
            "level": "senior",
            "requirements_clean": None,
            "responsibilities_clean": None,
            "hard_skills": [],
            "soft_skills": [],
            "tech_stack": [],
            "english_mention": False,
            "english_required": None,
            "english_level": "unknown",
        },
        expected={
            "company": "Internet Company PS",
            "city": "almaty",
            "employment": "full_time",
            "work_format": "hybrid",
            "salary_to": 1000000,
            "currency": "KZT",
            "experience_min": 2.0,
        },
    )

    run_case(
        name="free_text_only",
        text="Ищем Backend Developer, remote, full time, 3+ years of Python and Django, salary 4000 USD.",
        llm_result={
            "company": None,
            "city": "remote",
            "employment": "full_time",
            "work_format": "remote",
            "salary_raw": "4000 USD",
            "salary_from": 4000,
            "salary_to": None,
            "currency": "USD",
            "experience_min": 3,
            "experience_max": None,
            "category": "software_engineering",
            "title_normalized": "Backend Developer",
            "level": "middle",
            "requirements_clean": "3+ years of Python and Django.",
            "responsibilities_clean": "Build backend services.",
            "hard_skills": ["Python", "Django"],
            "soft_skills": [],
            "tech_stack": ["Python", "Django"],
            "english_mention": False,
            "english_required": None,
            "english_level": "unknown",
        },
        expected={
            "title_normalized": "Backend Developer",
            "employment": "full_time",
            "work_format": "remote",
            "currency": "USD",
        },
    )

    run_case(
        name="parser_llm_conflict_city",
        text="Город: Алматы\nКомпания: Test Company",
        llm_result={
            "company": "Test Company",
            "city": "astana",
            "employment": "unknown",
            "work_format": "unknown",
            "salary_raw": None,
            "salary_from": None,
            "salary_to": None,
            "currency": "unknown",
            "experience_min": None,
            "experience_max": None,
            "category": "software_engineering",
            "title_normalized": "Developer",
            "level": "middle",
            "requirements_clean": None,
            "responsibilities_clean": None,
            "hard_skills": [],
            "soft_skills": [],
            "tech_stack": [],
            "english_mention": False,
            "english_required": None,
            "english_level": "unknown",
        },
        expected={
            "city": "almaty",
        },
    )

    run_case(
        name="salary_swap_fix",
        text="Зарплата: 700000 - 300000 тг",
        llm_result={
            "company": None,
            "city": None,
            "employment": "unknown",
            "work_format": "unknown",
            "salary_raw": "700000 - 300000 тг",
            "salary_from": 700000,
            "salary_to": 300000,
            "currency": "KZT",
            "experience_min": None,
            "experience_max": None,
            "category": "unknown",
            "title_normalized": None,
            "level": "unknown",
            "requirements_clean": None,
            "responsibilities_clean": None,
            "hard_skills": [],
            "soft_skills": [],
            "tech_stack": [],
            "english_mention": False,
            "english_required": None,
            "english_level": "unknown",
        },
        expected={
            "salary_from": 300000,
            "salary_to": 700000,
        },
    )

    run_case(
        name="english_reset_without_mention",
        text="Ищем QA Engineer. Manual testing, SQL.",
        llm_result={
            "company": None,
            "city": None,
            "employment": "full_time",
            "work_format": "office",
            "salary_raw": None,
            "salary_from": None,
            "salary_to": None,
            "currency": "unknown",
            "experience_min": None,
            "experience_max": None,
            "category": "qa",
            "title_normalized": "QA Engineer",
            "level": "junior",
            "requirements_clean": None,
            "responsibilities_clean": None,
            "hard_skills": ["SQL"],
            "soft_skills": [],
            "tech_stack": [],
            "english_mention": False,
            "english_required": True,
            "english_level": "c2",
        },
        expected={
            "english_required": False,
            "english_level": None,
        },
    )

    run_case(
        name="mixed_ru_en",
        text="Company: Bee Lab\nГород: Astana\nWork format: remote\nEmployment: full-time",
        llm_result={
            "company": "Bee Lab",
            "city": "astana",
            "employment": "full_time",
            "work_format": "remote",
            "salary_raw": None,
            "salary_from": None,
            "salary_to": None,
            "currency": "unknown",
            "experience_min": None,
            "experience_max": None,
            "category": "software_engineering",
            "title_normalized": "Developer",
            "level": "middle",
            "requirements_clean": None,
            "responsibilities_clean": None,
            "hard_skills": [],
            "soft_skills": [],
            "tech_stack": [],
            "english_mention": True,
            "english_required": False,
            "english_level": "b2",
        },
        expected={
            "company": "Bee Lab",
            "city": "astana",
            "work_format": "remote",
        },
    )

    run_case(
        name="unknown_city",
        text="Город: Караганда",
        llm_result={
            "company": None,
            "city": None,
            "employment": "unknown",
            "work_format": "unknown",
            "salary_raw": None,
            "salary_from": None,
            "salary_to": None,
            "currency": "unknown",
            "experience_min": None,
            "experience_max": None,
            "category": "unknown",
            "title_normalized": None,
            "level": "unknown",
            "requirements_clean": None,
            "responsibilities_clean": None,
            "hard_skills": [],
            "soft_skills": [],
            "tech_stack": [],
            "english_mention": False,
            "english_required": None,
            "english_level": "unknown",
        },
        expected={
            "city": "other",
        },
    )

    run_case(
        name="internship_review",
        text="Занятость: стажировка",
        llm_result={
            "company": None,
            "city": None,
            "employment": "internship",
            "work_format": "office",
            "salary_raw": None,
            "salary_from": None,
            "salary_to": None,
            "currency": "unknown",
            "experience_min": None,
            "experience_max": None,
            "category": "data",
            "title_normalized": "Data Intern",
            "level": "senior",
            "requirements_clean": None,
            "responsibilities_clean": None,
            "hard_skills": [],
            "soft_skills": [],
            "tech_stack": [],
            "english_mention": False,
            "english_required": None,
            "english_level": "unknown",
        },
        expected={
            "employment": "internship",
        },
    )

    run_case(
        name="short_description",
        text="Python vacancy",
        llm_result={
            "company": None,
            "city": None,
            "employment": "unknown",
            "work_format": "unknown",
            "salary_raw": None,
            "salary_from": None,
            "salary_to": None,
            "currency": "unknown",
            "experience_min": None,
            "experience_max": None,
            "category": "software_engineering",
            "title_normalized": "Python Developer",
            "level": "unknown",
            "requirements_clean": None,
            "responsibilities_clean": None,
            "hard_skills": ["Python", "Python"],
            "soft_skills": [],
            "tech_stack": [],
            "english_mention": False,
            "english_required": None,
            "english_level": "unknown",
        },
        expected={
            "hard_skills": ["Python"],
        },
    )

    print("telegram cascade tests: OK")


if __name__ == "__main__":
    main()
