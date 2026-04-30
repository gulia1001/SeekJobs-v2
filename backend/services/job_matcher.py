"""Match a user profile against jobs using the existing app logic."""
import logging
import os

import pandas as pd
from groq import AsyncGroq

from services.data_loader import (
    find_matching_vacancies,
    get_market_salary,
    load_jobs,
    build_salary_label,
)

log = logging.getLogger("seekjobs.matcher")


def _salary_status(expected: float | None, market_avg: float) -> str:
    if not expected or not market_avg:
        return "unknown"
    if expected < market_avg * 0.9:
        return "below"
    if expected > market_avg * 1.1:
        return "above"
    return "at"


def _row_to_job(row: pd.Series) -> dict:
    sal_avg = row.get("salary_avg_clean")
    sal_from = row.get("salary_from_clean")
    sal_to = row.get("salary_to_clean")
    if pd.isna(sal_avg) if sal_avg is not None else True:
        sal_avg = None
    if pd.isna(sal_from) if sal_from is not None else True:
        sal_from = None
    if pd.isna(sal_to) if sal_to is not None else True:
        sal_to = None

    return {
        "id": str(row.get("id", "")),
        "title": str(row.get("title_final", "")),
        "company": str(row.get("company_clean", "")),
        "city": str(row.get("city_norm", "")),
        "category": str(row.get("category_filled", "")),
        "level": str(row.get("level_filled", "")),
        "work_format": str(row.get("work_format_norm", "")),
        "salary_from": float(sal_from) if sal_from is not None else None,
        "salary_to": float(sal_to) if sal_to is not None else None,
        "salary_avg": float(sal_avg) if sal_avg is not None else None,
        "currency": str(row.get("currency_clean", "KZT")),
        "skills": list(row.get("skills_all_clean_list") or []),
        "source": str(row.get("source", "")),
        "salary_display": build_salary_label(row),
    }


async def match_jobs(
    user_skills: list[str],
    target_roles: list[str],
    preferred_salary: float | None = None,
    top_n: int = 5,
) -> dict:
    """
    Returns {role: {market_avg_salary, currency, matches: [...]}} for each role.
    Uses the same jaccard_score + find_matching_vacancies logic as the Streamlit app.
    """
    df = load_jobs()

    log.info(
        "Dataset: %d rows | user_skills: %d | roles: %s | salary: %s",
        len(df), len(user_skills), target_roles, preferred_salary,
    )

    if df.empty:
        log.warning("No job data available — CSVs not found or empty")
        return {}

    roles = target_roles if target_roles else ["backend"]
    result: dict = {}

    for role in roles:
        market = get_market_salary(role, df)
        log.info("Role=%s  market_avg=%s  market_count=%s", role, market["avg"], market["count"])

        matches_df = find_matching_vacancies(
            user_skills,
            categories=[role],
            salary_min=None,
            top_n=top_n,
            df=df,
        )

        log.info("Role=%s  candidates_found=%d", role, len(matches_df))

        if matches_df.empty:
            result[role] = {"market_avg_salary": market["avg"], "currency": "KZT", "matches": []}
            continue

        matches = []
        for i, (_, row) in enumerate(matches_df.iterrows(), 1):
            score = round(float(row.get("match_score", 0)) * 100)
            job = _row_to_job(row)
            matched = list(row.get("matched_skills", []))
            missing = list(row.get("missing_skills", []))

            log.info(
                "  #%d  %s @ %s  score=%d%%  matched=%s  missing=%s",
                i, job["title"], job["company"], score,
                matched[:4], missing[:4],
            )

            sal_avg = job.get("salary_avg")
            matches.append({
                "rank": i,
                "score": score,
                "job": job,
                "reason": "",  # filled by LLM below
                "skills_matched": matched,
                "skills_missing": missing,
                "salary_comparison": {
                    "user_expected": preferred_salary,
                    "job_avg": sal_avg,
                    "market_avg": market["avg"],
                    "status": _salary_status(preferred_salary, market["avg"]),
                },
            })

        matches = await _enrich_reasons(matches, user_skills, role)

        result[role] = {
            "market_avg_salary": market["avg"],
            "currency": "KZT",
            "matches": matches,
        }

    return result


async def _enrich_reasons(matches: list[dict], user_skills: list[str], role: str) -> list[dict]:
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key or not matches:
        for m in matches:
            m["reason"] = f"Matched {len(m['skills_matched'])} skill(s) for {role}."
        return matches

    try:
        client = AsyncGroq(api_key=groq_key)
        lines = "\n".join(
            f"{m['rank']}. {m['job']['title']} at {m['job']['company']} "
            f"(score {m['score']}%, matched: {', '.join(m['skills_matched'][:4])}, "
            f"missing: {', '.join(m['skills_missing'][:3])})"
            for m in matches
        )
        prompt = (
            f"User skills: {', '.join(user_skills[:15])}.\n"
            f"Target role: {role}.\n\n"
            f"Write ONE sentence (≤20 words) for each match explaining why it fits:\n{lines}\n\n"
            f"Reply with exactly {len(matches)} numbered lines like: '1. ...'  '2. ...' etc."
        )
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.4,
        )
        reply_lines = resp.choices[0].message.content.strip().split("\n")
        for m in matches:
            line = next((l for l in reply_lines if l.startswith(f"{m['rank']}.")), "")
            m["reason"] = line.split(".", 1)[-1].strip() if line else f"Good {role} match."
    except Exception as e:
        log.warning("Groq reason enrichment failed: %s", e)
        for m in matches:
            m["reason"] = f"Matched {len(m['skills_matched'])} skill(s) for {role}."

    return matches
