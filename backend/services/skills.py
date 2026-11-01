"""Skill-name normalization and job scoring.

skill_key() maps spelling variants of the same skill to one key, so a CV that says
"Postgres" matches a job asking for "PostgreSQL", and "React.js" matches "React".

score_job() scores a job by how many of the JOB's skills the candidate has
(coverage). Unlike Jaccard similarity, this does not punish candidates who list
many skills: knowing 30 things doesn't make you a worse fit for a job needing 5.
"""
from __future__ import annotations

import re
from typing import Iterable

# variant key -> canonical key (both after _base_key normalization)
_ALIASES = {
    # databases
    "postgres": "postgresql", "postgre": "postgresql", "psql": "postgresql", "pgsql": "postgresql",
    "mssql": "sqlserver", "mssqlserver": "sqlserver", "microsoftsqlserver": "sqlserver",
    "mongo": "mongodb",
    "elastic": "elasticsearch",
    "rabbit": "rabbitmq",
    # languages
    "js": "javascript", "ecmascript": "javascript", "es6": "javascript", "vanillajs": "javascript",
    "ts": "typescript",
    "golang": "go",
    "python3": "python", "py": "python",
    "csharp": "c#",
    "cpp": "c++",
    "dotnet": "net", "netcore": "net", "netframework": "net",
    "html5": "html", "css3": "css",
    "1с": "1c",  # Cyrillic "С" — very common in Kazakhstan vacancies
    # frameworks / runtimes
    "reactjs": "react", "react18": "react",
    "vuejs": "vue", "vue3": "vue", "vue2": "vue",
    "angularjs": "angular",
    "node": "nodejs",
    "next": "nextjs",
    "nuxt": "nuxtjs",
    "nest": "nestjs",
    "expressjs": "express",
    "sklearn": "scikitlearn",
    "drf": "djangorestframework",
    # infra / practices
    "k8s": "kubernetes",
    "amazonwebservices": "aws",
    "googlecloud": "gcp", "googlecloudplatform": "gcp",
    "microsoftazure": "azure",
    "rest": "restapi", "restful": "restapi", "restfulapi": "restapi", "restapis": "restapi",
    "ml": "machinelearning",
    "dl": "deeplearning",
    "naturallanguageprocessing": "nlp",
    "artificialintelligence": "ai",
    "msexcel": "excel", "microsoftexcel": "excel",
    # languages spoken (Russian spelling is common in KZ job posts)
    "английский": "english", "английскийязык": "english", "englishlanguage": "english",
}

_STRIP = re.compile(r"[\s\-_./,:;()'\"]+")


def base_key(name: str) -> str:
    """Lowercase, no spaces/punctuation — before alias mapping."""
    # keep '#' and '+' so C, C# and C++ stay different skills
    return _STRIP.sub("", str(name).casefold().strip())


def skill_key(name: str) -> str:
    """Canonical comparison key for a skill name ('' for blank input)."""
    key = base_key(name)
    return _ALIASES.get(key, key)


def keyed(skills: Iterable[str]) -> dict[str, str]:
    """{key: first display name} — dedupes variants like 'Postgres' + 'PostgreSQL'."""
    out: dict[str, str] = {}
    for s in skills:
        if not s:
            continue
        k = skill_key(s)
        if k and k not in out:
            out[k] = str(s).strip()
    return out


def dedupe_skills(skills: Iterable[str]) -> list[str]:
    return list(keyed(skills).values())


def score_job(user_keys: set[str], job_skills: dict[str, str]) -> tuple[float, float, list[str], list[str]]:
    """Return (coverage, rank_score, matched, missing) for one job.

    coverage   = share of the job's skills the candidate has (shown to the user)
    rank_score = smoothed coverage used for sorting, so a job listing 5 skills you
                 all have ranks above a job listing just 1 skill
    """
    if not job_skills:
        return 0.0, 0.0, [], []
    matched = [name for k, name in job_skills.items() if k in user_keys]
    missing = [name for k, name in job_skills.items() if k not in user_keys]
    n = len(job_skills)
    coverage = len(matched) / n
    rank_score = (len(matched) + 1) / (n + 2)
    return coverage, rank_score, matched, missing
