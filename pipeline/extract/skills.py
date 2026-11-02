"""Skill-name normalization, skill extraction from text, and job scoring.

skill_key() maps spelling variants of the same skill to one key, so a CV that says
"Postgres" matches a job asking for "PostgreSQL", and "React.js" matches "React".

find_skills() finds known skills in free text (CVs, vacancy posts, hashtags).

score_job() scores a job by how many of the JOB's skills the candidate has
(coverage). Unlike Jaccard similarity, this does not punish candidates who list
many skills: knowing 30 things doesn't make you a worse fit for a job needing 5.

NOTE: this file is shared — an identical copy lives in pipeline/extract/skills.py
(a test checks they match). Edit one, copy it to the other.
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
    "rails": "rubyonrails", "ror": "rubyonrails",
    "aspnetcore": "aspnet",
    "efcore": "entityframework", "entityframeworkcore": "entityframework",
    "springframework": "spring",
    "tailwind": "tailwindcss",
    "mui": "materialui",
    "apachekafka": "kafka", "apachespark": "spark", "pyspark": "spark", "apacheairflow": "airflow",
    "abtest": "abtesting", "abtests": "abtesting",
    "llms": "llm", "largelanguagemodels": "llm",
    "1спредприятие": "1c", "1cпредприятие": "1c", "1centerprise": "1c",
    "photoshop": "adobephotoshop", "illustrator": "adobeillustrator",
    # languages spoken (Russian spelling is common in KZ job posts)
    "английский": "english", "английскийязык": "english", "englishlanguage": "english",
    "казахский": "kazakh", "казахскийязык": "kazakh", "қазақтілі": "kazakh",
}

# Built-in vocabulary of common IT skills — used to find skills in vacancy posts and
# CVs when no job dataset is available (the dataset's own skill names are added on top).
COMMON_SKILLS = [
    # languages
    "Python", "Java", "JavaScript", "TypeScript", "Go", "C++", "C#", "PHP", "Ruby", "Kotlin",
    "Swift", "Dart", "Scala", "Rust", "SQL", "Bash", "PowerShell", "Objective-C", "Perl",
    "Elixir", "MATLAB", "Solidity", "1C", "ABAP", "Delphi", "VBA", "Groovy",
    # backend
    "Django", "Django REST Framework", "Flask", "FastAPI", "Spring", "Spring Boot", "Hibernate",
    ".NET", "ASP.NET", "Entity Framework", "Node.js", "Express", "NestJS", "Laravel", "Symfony",
    "Yii", "Ruby on Rails", "Gin", "Ktor", "Quarkus", "Microservices", "REST API", "GraphQL",
    "gRPC", "WebSocket", "OOP", "SOLID", "Design Patterns", "Clean Architecture", "DDD", "TDD",
    # frontend
    "React", "Next.js", "Vue", "Nuxt.js", "Angular", "Svelte", "Redux", "MobX", "jQuery",
    "HTML", "CSS", "SCSS", "Tailwind CSS", "Bootstrap", "Webpack", "Vite", "Material UI",
    "Storybook", "RxJS", "Three.js",
    # mobile
    "Android", "iOS", "Flutter", "React Native", "SwiftUI", "Jetpack Compose", "Xamarin",
    "UIKit", "Kotlin Multiplatform",
    # databases & data infrastructure
    "PostgreSQL", "MySQL", "SQL Server", "Oracle", "SQLite", "MongoDB", "Redis",
    "Elasticsearch", "ClickHouse", "Cassandra", "DynamoDB", "MariaDB", "Neo4j", "Firebase",
    "Supabase", "Greenplum", "Snowflake", "BigQuery", "Vertica", "Tarantool", "OpenSearch",
    "Kafka", "RabbitMQ", "NATS", "Celery", "Airflow", "Spark", "Hadoop", "Flink", "dbt",
    "Hive", "Trino", "NiFi", "Databricks", "ETL", "DWH",
    # devops & cloud
    "Docker", "Kubernetes", "Helm", "Terraform", "Ansible", "Jenkins", "GitLab CI",
    "GitHub Actions", "CI/CD", "ArgoCD", "Prometheus", "Grafana", "ELK", "Nginx", "Linux",
    "AWS", "Azure", "GCP", "Yandex Cloud", "OpenShift", "Istio", "Vault", "Zabbix",
    "Git", "GitLab", "GitHub", "VMware", "Hyper-V", "Proxmox", "Windows Server",
    "Active Directory", "TCP/IP", "Cisco", "MikroTik", "VPN", "DNS",
    # data science & analytics
    "Pandas", "NumPy", "scikit-learn", "TensorFlow", "PyTorch", "Keras", "Machine Learning",
    "Deep Learning", "NLP", "Computer Vision", "LLM", "OpenCV", "Hugging Face", "LangChain",
    "XGBoost", "CatBoost", "LightGBM", "Statistics", "A/B testing", "MLOps", "MLflow",
    "Jupyter", "Data Science", "Power BI", "Tableau", "Looker", "Superset", "Metabase",
    "Excel", "Google Sheets", "Google Analytics", "Yandex Metrica", "Amplitude", "Qlik",
    # QA
    "Selenium", "Playwright", "Cypress", "Postman", "JMeter", "Appium", "pytest", "JUnit",
    "TestNG", "Allure", "Manual Testing", "Test Automation", "API Testing", "Load Testing",
    # design
    "Figma", "Sketch", "Adobe Photoshop", "Adobe Illustrator", "Adobe XD", "After Effects",
    "Blender", "UI/UX", "Prototyping", "Miro",
    # process & business systems
    "Agile", "Scrum", "Kanban", "Jira", "Confluence", "BPMN", "UML", "SAP", "Bitrix24",
    "CRM", "ERP",
    # security
    "SIEM", "SOC", "Pentest", "OWASP", "ISO 27001", "Burp Suite", "Wireshark", "DLP",
    # spoken languages often required in KZ
    "English", "Kazakh",
]

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


# 1–2 letter words that are real skills (others like "a", "в", or the "R" in "R&D" are ignored)
_SHORT_ALLOW = {"ai", "bi", "ci", "ml", "nlp", "qa", "ui", "ux", "js",
                "go", "c#", "c++", "1c", "1с", "hr"}
_WORD = re.compile(r"[\w#+.]+")
_MAX_PHRASE_WORDS = 4
# single words that are also common English words: only count the exact spelling
# (".NET" not "net" as in "salary net", "Go" not "go to market")
_EXACT_CASE = {"net": {"NET"}, "go": {"Go"}}  # "GO" is also a T-SQL keyword


def find_skills(text: str, vocabulary: Iterable[str], max_skills: int = 40) -> list[str]:
    """Known skills found in free text, in order of appearance (vocabulary spelling).

    Every 1–4 word phrase is normalized with skill_key(), so 'Postgres', 'CI/CD',
    'scikit-learn', 'Node.js' or the hashtag '#cpp' match 'PostgreSQL', 'CI/CD',
    'scikit-learn', 'NodeJS', 'C++'.
    """
    if not text or not text.strip():
        return []
    vocab: dict[str, str] = {}
    for s in vocabulary:
        vocab.setdefault(skill_key(s), s)
    vocab.pop("", None)

    # strip sentence dots and hashtag signs ('#python' -> 'python'; 'C#' keeps its '#')
    words = [w.strip(".").lstrip("#") for w in _WORD.findall(text)]
    words = [w for w in words if w]
    found: list[str] = []
    seen: set[str] = set()
    for i in range(len(words)):
        for n in range(_MAX_PHRASE_WORDS, 0, -1):  # longest phrase first: "Spring Boot" before "Spring"
            if i + n > len(words):
                continue
            phrase = " ".join(words[i:i + n])
            raw = base_key(phrase)
            if len(raw) <= 2 and raw not in _SHORT_ALLOW:
                continue
            key = skill_key(phrase)
            if n == 1 and raw in _EXACT_CASE and phrase not in _EXACT_CASE[raw]:
                continue
            if key in vocab and key not in seen:
                seen.add(key)
                found.append(vocab[key])
                if len(found) >= max_skills:
                    return found
    return found


def score_job(user_keys: set[str], job_skills: dict[str, str]) -> tuple[float, float, list[str], list[str]]:
    """Return (coverage, rank_score, matched, missing) for one job.

    coverage   = share of the job's skills the candidate has (shown to the user)
    rank_score = coverage weighted by evidence, used for sorting: a job whose post
                 names only 1–3 skills can't outrank a detailed one (1 of 1 -> 0.25,
                 7 of 9 -> 0.78, 4 of 4 -> 1.0)
    """
    if not job_skills:
        return 0.0, 0.0, [], []
    matched = [name for k, name in job_skills.items() if k in user_keys]
    missing = [name for k, name in job_skills.items() if k not in user_keys]
    n = len(job_skills)
    coverage = len(matched) / n
    rank_score = coverage * min(1.0, n / 4)
    return coverage, rank_score, matched, missing


# requirements that are not technical skills — shown, but not used for match scores
NON_TECHNICAL = {"english", "kazakh"}

_LEVEL_ORDER = {"intern": 0, "junior": 1, "middle": 2, "senior": 3, "lead": 4, "manager": 4}


def level_fit(user_level: str | None, job_level: str | None) -> float:
    """Ranking multiplier: a junior sees senior/lead roles lower (and a senior sees intern roles lower)."""
    if user_level not in _LEVEL_ORDER or job_level not in _LEVEL_ORDER:
        return 1.0
    gap = _LEVEL_ORDER[job_level] - _LEVEL_ORDER[user_level]
    if gap >= 2:
        return 0.5
    if gap == 1:
        return 0.85
    if gap <= -2:
        return 0.8
    return 1.0
