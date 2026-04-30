"""Analyze a public GitHub profile: repos, stack signals, activity, resume bullets."""
import re
from datetime import datetime, timezone



CANDIDATE_FILES = [
    "README.md",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "pom.xml",
    "build.gradle",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "Gemfile",
    "next.config.js",
    "next.config.ts",
    "vite.config.js",
    "vite.config.ts",
    "tsconfig.json",
    "tailwind.config.js",
    "tailwind.config.ts",
]

FILE_STACK_SIGNALS = {
    "package.json": ["Node.js"],
    "requirements.txt": ["Python"],
    "pyproject.toml": ["Python"],
    "Pipfile": ["Python"],
    "Dockerfile": ["Docker"],
    "docker-compose.yml": ["Docker Compose"],
    "docker-compose.yaml": ["Docker Compose"],
    "pom.xml": ["Java", "Maven"],
    "build.gradle": ["Java", "Gradle"],
    "Cargo.toml": ["Rust"],
    "go.mod": ["Go"],
    "composer.json": ["PHP"],
    "Gemfile": ["Ruby"],
    "next.config.js": ["Next.js"],
    "next.config.ts": ["Next.js"],
    "vite.config.js": ["Vite"],
    "vite.config.ts": ["Vite"],
    "tsconfig.json": ["TypeScript"],
    "tailwind.config.js": ["Tailwind CSS"],
    "tailwind.config.ts": ["Tailwind CSS"],
}

KEYWORD_STACK_SIGNALS = {
    "react": "React",
    "next": "Next.js",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "svelte": "Svelte",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "express": "Express",
    "nestjs": "NestJS",
    "playwright": "Playwright",
    "selenium": "Selenium",
    "beautifulsoup": "BeautifulSoup",
    "scrapy": "Scrapy",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "scikit-learn": "scikit-learn",
    "pandas": "pandas",
    "numpy": "NumPy",
    "postgres": "PostgreSQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "tailwind": "Tailwind CSS",
    "docker": "Docker",
}

TYPE_RULES = [
    ("scraper", ["scrap", "crawl", "selenium", "playwright", "beautifulsoup", "scrapy"]),
    ("bot", ["bot", "telegram", "discord", "slack"]),
    ("ml", ["machine learning", "deep learning", "neural", "pytorch", "tensorflow", "scikit-learn", "notebook"]),
    ("frontend", ["react", "next", "vue", "angular", "frontend", "tailwind", "vite"]),
    ("api", ["api", "fastapi", "flask", "django", "express", "nestjs", "graphql", "backend"]),
    ("automation", ["automation", "script", "cli", "workflow", "cron"]),
]


def analyze_profile(
    client,
    username,
    max_repos=12,
    max_commit_pages=2,
    include_forks=False,
    llm_client=None,
    llm_top_n=5,
):
    user = client.get_user(username)
    repos = client.list_public_repos(username, include_forks=include_forks)
    pinned_repo_names = set(safe_call(client.get_pinned_repos, username, default=[]))

    analyzed_repos = []
    for repo in repos[:max_repos]:
        analyzed_repos.append(
            analyze_repo(
                client=client,
                username=username,
                repo=repo,
                pinned_repo_names=pinned_repo_names,
                max_commit_pages=max_commit_pages,
            )
        )

    analyzed_repos.sort(key=lambda item: item["resume_score"], reverse=True)

    if llm_client:
        for repo_data in analyzed_repos[:llm_top_n]:
            repo_data["llm_resume"] = llm_client.enrich_repo(build_repo_llm_payload(repo_data))

    profile_summary = {
        "username": user.get("login", username),
        "name": user.get("name"),
        "bio": user.get("bio"),
        "company": user.get("company"),
        "blog": user.get("blog"),
        "location": user.get("location"),
        "followers": user.get("followers"),
        "public_repos": user.get("public_repos"),
        "profile_url": user.get("html_url"),
        "pinned_repo_names": sorted(pinned_repo_names),
        "repos": analyzed_repos,
    }

    if llm_client:
        profile_summary["llm_profile_resume"] = llm_client.build_profile_resume(
            build_profile_llm_payload(profile_summary)
        )

    return profile_summary


def analyze_repo(client, username, repo, pinned_repo_names, max_commit_pages):
    owner = repo["owner"]["login"]
    name = repo["name"]
    default_branch = repo.get("default_branch")

    languages = safe_call(client.get_repo_languages, owner, name, default={})
    readme_text = safe_call(client.get_repo_readme, owner, name, default=None)
    root_entries = safe_call(client.get_root_files, owner, name, ref=default_branch, default=[])
    root_files = [entry.get("name") for entry in root_entries if entry.get("name")]

    candidate_contents = {}
    for file_name in CANDIDATE_FILES:
        if file_name in root_files:
            candidate_contents[file_name] = safe_call(
                client.get_file_text,
                owner,
                name,
                file_name,
                ref=default_branch,
                default=None,
            )

    commits = safe_call(
        client.list_commits,
        owner,
        name,
        author=username,
        max_pages=max_commit_pages,
        default=[],
    )

    stack = detect_stack(languages, root_files, candidate_contents, readme_text)
    project_type = detect_project_type(repo, readme_text, root_files, stack)
    business_goal = infer_business_goal(repo, readme_text)
    activity = build_activity_summary(commits)
    readme_excerpt = extract_readme_excerpt(readme_text)

    analysis = {
        "name": name,
        "full_name": repo.get("full_name"),
        "html_url": repo.get("html_url"),
        "homepage": repo.get("homepage"),
        "description": repo.get("description"),
        "topics": repo.get("topics", []),
        "language": repo.get("language"),
        "languages": languages,
        "stargazers_count": repo.get("stargazers_count", 0),
        "forks_count": repo.get("forks_count", 0),
        "watchers_count": repo.get("watchers_count", 0),
        "open_issues_count": repo.get("open_issues_count", 0),
        "updated_at": repo.get("updated_at"),
        "pushed_at": repo.get("pushed_at"),
        "created_at": repo.get("created_at"),
        "size_kb": repo.get("size"),
        "archived": repo.get("archived", False),
        "fork": repo.get("fork", False),
        "default_branch": default_branch,
        "readme_excerpt": readme_excerpt,
        "root_files": root_files,
        "candidate_file_presence": sorted(candidate_contents.keys()),
        "stack_signals": stack,
        "project_type": project_type,
        "business_goal": business_goal,
        "activity": activity,
        "is_pinned": name in pinned_repo_names,
    }
    analysis["resume_score"] = score_repo(analysis)
    analysis["heuristic_resume_bullets"] = build_resume_bullets(analysis)
    return analysis


def safe_call(func, *args, default=None, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        return default


def detect_stack(languages, root_files, candidate_contents, readme_text):
    signals = []

    for file_name in root_files:
        signals.extend(FILE_STACK_SIGNALS.get(file_name, []))

    top_languages = sorted(languages.items(), key=lambda item: item[1], reverse=True)[:4]
    signals.extend(language_name for language_name, _ in top_languages)

    searchable = " ".join(
        value for value in candidate_contents.values() if isinstance(value, str)
    )
    searchable = f"{searchable}\n{readme_text or ''}".lower()

    for keyword, label in KEYWORD_STACK_SIGNALS.items():
        if keyword in searchable:
            signals.append(label)

    seen = []
    for item in signals:
        if item and item not in seen:
            seen.append(item)
    return seen[:8]


def detect_project_type(repo, readme_text, root_files, stack):
    searchable = " ".join(
        [
            repo.get("name", ""),
            repo.get("description") or "",
            " ".join(repo.get("topics") or []),
            " ".join(root_files),
            " ".join(stack),
            readme_text or "",
        ]
    ).lower()

    for label, keywords in TYPE_RULES:
        if any(keyword in searchable for keyword in keywords):
            return label
    return "general"


def infer_business_goal(repo, readme_text):
    description = (repo.get("description") or "").strip()
    if description:
        return description

    if readme_text:
        cleaned = clean_markdown(readme_text)
        for paragraph in cleaned.split("\n\n"):
            text = paragraph.strip()
            if len(text) >= 40:
                return squeeze_text(text, 220)

    return "Public repository with unclear end-user goal"


def extract_readme_excerpt(readme_text, limit=800):
    if not readme_text:
        return None
    cleaned = clean_markdown(readme_text)
    return squeeze_text(cleaned, limit)


def clean_markdown(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def squeeze_text(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def build_activity_summary(commits):
    if not commits:
        return {
            "sampled_commit_count": 0,
            "last_commit_at": None,
            "first_sampled_commit_at": None,
            "active_days_in_sample": 0,
            "sample_window_days": None,
        }

    dates = []
    for commit in commits:
        date_str = (
            commit.get("commit", {})
            .get("author", {})
            .get("date")
        )
        if date_str:
            dates.append(parse_iso_datetime(date_str))

    if not dates:
        return {
            "sampled_commit_count": len(commits),
            "last_commit_at": None,
            "first_sampled_commit_at": None,
            "active_days_in_sample": 0,
            "sample_window_days": None,
        }

    dates.sort()
    unique_days = {date.date().isoformat() for date in dates}
    window_days = (dates[-1] - dates[0]).days or 1
    return {
        "sampled_commit_count": len(commits),
        "last_commit_at": dates[-1].isoformat(),
        "first_sampled_commit_at": dates[0].isoformat(),
        "active_days_in_sample": len(unique_days),
        "sample_window_days": window_days,
    }


def parse_iso_datetime(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def score_repo(analysis):
    score = 0
    score += analysis["stargazers_count"] * 5
    score += analysis["forks_count"] * 3
    score += 12 if analysis["homepage"] else 0
    score += 10 if analysis["is_pinned"] else 0
    score += 8 if analysis["readme_excerpt"] else 0
    score += 6 if analysis["activity"]["sampled_commit_count"] else 0
    score += min(len(analysis["stack_signals"]), 5) * 2
    score -= 20 if analysis["archived"] else 0
    return score


def build_resume_bullets(analysis):
    project_type = analysis["project_type"]
    stack = ", ".join(analysis["stack_signals"][:5]) or "public technologies"
    goal = analysis["business_goal"]
    bullets = [
        f"Built and maintained a {project_type} project focused on {goal.lower()}.",
        f"Worked with {stack} and published the solution as a public GitHub repository.",
    ]

    if analysis["activity"]["sampled_commit_count"]:
        bullets.append(
            f"Shipped at least {analysis['activity']['sampled_commit_count']} sampled commits with visible public development activity."
        )
    return bullets[:3]


def build_repo_llm_payload(repo_data):
    return {
        "name": repo_data["name"],
        "description": repo_data["description"],
        "project_type": repo_data["project_type"],
        "business_goal": repo_data["business_goal"],
        "topics": repo_data["topics"],
        "primary_language": repo_data["language"],
        "languages": repo_data["languages"],
        "stack_signals": repo_data["stack_signals"],
        "homepage": repo_data["homepage"],
        "stars": repo_data["stargazers_count"],
        "forks": repo_data["forks_count"],
        "updated_at": repo_data["updated_at"],
        "root_files": repo_data["root_files"],
        "readme_excerpt": repo_data["readme_excerpt"],
        "activity": repo_data["activity"],
    }


def build_profile_llm_payload(profile_summary):
    top_repos = []
    for repo in profile_summary["repos"][:5]:
        top_repos.append(
            {
                "name": repo["name"],
                "project_type": repo["project_type"],
                "business_goal": repo["business_goal"],
                "stack_signals": repo["stack_signals"],
                "stars": repo["stargazers_count"],
                "forks": repo["forks_count"],
                "updated_at": repo["updated_at"],
                "heuristic_resume_bullets": repo["heuristic_resume_bullets"],
                "llm_resume": repo.get("llm_resume"),
            }
        )

    return {
        "username": profile_summary["username"],
        "name": profile_summary["name"],
        "bio": profile_summary["bio"],
        "company": profile_summary["company"],
        "location": profile_summary["location"],
        "followers": profile_summary["followers"],
        "top_repos": top_repos,
    }
