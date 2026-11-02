import pytest

from routers.analyze import parse_salary
from services.data_loader import extract_skills_from_text
from services.skills import dedupe_skills, keyed, score_job, skill_key


@pytest.mark.parametrize("variants", [
    ["PostgreSQL", "Postgres", "postgresql", "psql"],
    ["React", "React.js", "ReactJS", "react js"],
    ["Node.js", "NodeJS", "node"],
    ["JavaScript", "JS", "javascript"],
    ["Kubernetes", "k8s"],
    ["1C", "1С"],  # Latin C and Cyrillic С
    ["CI/CD", "CI CD", "cicd"],
    ["scikit-learn", "sklearn", "Scikit Learn"],
    ["English", "Английский язык"],
])
def test_variants_share_one_key(variants):
    assert len({skill_key(v) for v in variants}) == 1


def test_c_family_stays_distinct():
    assert len({skill_key("C"), skill_key("C#"), skill_key("C++")}) == 3


def test_dedupe_keeps_first_spelling():
    assert dedupe_skills(["Postgres", "PostgreSQL", "Docker", "docker"]) == ["Postgres", "Docker"]


def test_coverage_is_share_of_job_skills():
    job = keyed(["Python", "FastAPI", "PostgreSQL", "Docker"])
    coverage, _, matched, missing = score_job(set(keyed(["python", "Postgres"])), job)
    assert coverage == 0.5
    assert matched == ["Python", "PostgreSQL"]
    assert missing == ["FastAPI", "Docker"]


def test_many_skills_are_not_penalized():
    """Old Jaccard scoring gave a broader candidate a LOWER score for the same job."""
    job = keyed(["Python", "FastAPI"])
    narrow = set(keyed(["Python", "FastAPI"]))
    broad = narrow | set(keyed([f"Skill{i}" for i in range(30)]))
    assert score_job(narrow, job)[0] == score_job(broad, job)[0] == 1.0


def test_more_evidence_ranks_higher():
    user = set(keyed(["Python", "FastAPI", "Docker", "SQL", "Git"]))
    one_of_one = score_job(user, keyed(["Python"]))
    five_of_five = score_job(user, keyed(["Python", "FastAPI", "Docker", "SQL", "Git"]))
    assert one_of_one[0] == five_of_five[0] == 1.0
    assert five_of_five[1] > one_of_one[1]


def test_extract_skills_handles_variants_and_punctuation():
    vocab = ["NodeJS", "PostgreSQL", "scikit-learn", "CI/CD", "Spring Boot", "Docker", "1С"]
    text = "Worked with Node.js, Postgres; ML via scikit-learn. Set up CI/CD and Spring Boot apps. Docker. Также 1С."
    assert extract_skills_from_text(text, vocab) == [
        "NodeJS", "PostgreSQL", "scikit-learn", "CI/CD", "Spring Boot", "Docker", "1С",
    ]


def test_extract_skips_short_noise_words():
    assert extract_skills_from_text("I am a dev", ["a", "am", "I"]) == []


@pytest.mark.parametrize("raw, expected", [
    ("500000", 500000), ("500 000", 500000), ("500 000 ₸", 500000),
    ("500k", 500000), ("500 тыс", 500000), ("", None), ("abc", None), ("0", None),
])
def test_parse_salary(raw, expected):
    assert parse_salary(raw) == expected


@pytest.mark.parametrize("text, expected", [
    ("Айгерим Нурланова\nBackend developer", "Айгерим Нурланова"),
    ("Curriculum Vitae\nJohn Smith\n...", "John Smith"),
    ("Software Engineer\nJohn Smith", ""),          # a job title is not a name
    ("Python, FastAPI, Docker", ""),
    ("", ""),
])
def test_guess_name(text, expected):
    from services.cv_generator import _guess_name
    assert _guess_name(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Junior Backend-разработчик\nОпыт: стажировка в DemoTech", "junior"),  # headline wins over the internship
    ("Senior Python Developer, 6 years", "senior"),
    ("Python developer, 5 лет опыта", "senior"),  # no level word -> years
    ("Python developer, 2 года опыта", "junior"),
    ("Strong leadership, always ahead of deadlines", ""),  # no false "lead"
    ("Python developer since 2025 год", ""),  # a year is not years of experience
    ("", ""),
])
def test_cv_level(text, expected):
    from services.data_loader import summarize_cv_text
    assert summarize_cv_text(text, ["Python"])["level"] == expected


def test_level_fit():
    from services.skills import level_fit
    assert level_fit("junior", "senior") == 0.5
    assert level_fit("junior", "middle") == 0.85
    assert level_fit("junior", "junior") == level_fit("", "senior") == level_fit("junior", "unknown") == 1.0


def test_spoken_languages_do_not_count_as_match_skills():
    import pandas as pd
    from services.data_loader import _match_skills
    assert list(_match_skills(pd.Series({"hard_skills_clean": '["English", "Python", "Казахский язык"]'}))) == ["python"]


def test_english_level_is_detected():
    from services.data_loader import summarize_cv_text
    assert summarize_cv_text("Junior developer. English B2, Russian C2.", ["Python"])["english_level"] == "B2"
