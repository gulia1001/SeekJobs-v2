"""Read a LinkedIn profile PDF — the file a person downloads from their own profile
(LinkedIn → your profile → "More" / "Resources" → "Save to PDF").

No scraping: LinkedIn forbids it and sued scraping services. The PDF has a narrow left
sidebar (Contact, Top Skills, Languages, Certifications) and a main column (name, headline,
Summary, Experience, Education). English and Russian LinkedIn interfaces are supported.
"""
from __future__ import annotations

import io
import re

_SECTIONS = {
    "contact": ["contact", "контактная информация", "контакты"],
    "skills": ["top skills", "основные навыки", "навыки"],
    "languages": ["languages", "языки"],
    "certifications": ["certifications", "licenses & certifications", "сертификаты",
                       "лицензии и сертификаты", "сертификаты и лицензии"],
    "honors": ["honors-awards", "награды"],
    "publications": ["publications", "публикации"],
    "summary": ["summary", "общие сведения", "о себе"],
    "experience": ["experience", "опыт работы", "опыт"],
    "education": ["education", "образование"],
}
_HEADING = {name.casefold(): section for section, names in _SECTIONS.items() for name in names}
_PROFILE_URL = re.compile(r"(?:www\.)?linkedin\.com/in/[\w\-%]+", re.IGNORECASE)
SIDEBAR_SHARE = 0.32  # left part of the page that holds the sidebar
COLUMN_BREAK = "\f"


def pdf_text(content: bytes) -> str:
    """Sidebar text first, then the main column — reading the page row by row would mix them."""
    import pdfplumber

    sidebar, main = [], []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            split = page.width * SIDEBAR_SHARE
            sidebar.append(page.crop((0, 0, split, page.height)).extract_text() or "")
            main.append(page.crop((split, 0, page.width, page.height)).extract_text() or "")
    # form feed marks where the sidebar ends, so its last section doesn't swallow the main column
    columns = ("\n".join(sidebar).strip() + f"\n{COLUMN_BREAK}\n" + "\n".join(main).strip()).strip()
    if any(line.strip().casefold() in _HEADING for line in columns.splitlines()):
        return columns
    # not the usual two-column layout — read the page normally
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "header"
    for raw in text.split("\n"):
        if raw.strip(" \r") == COLUMN_BREAK:
            current = "header"  # main column starts with name + headline
            continue
        line = raw.strip()
        if not line or re.fullmatch(r"page \d+ of \d+|страница \d+ из \d+", line, re.IGNORECASE):
            continue
        heading = _HEADING.get(line.casefold())
        if heading:
            current = heading
            continue
        sections.setdefault(current, []).append(line)
    return sections


def parse_linkedin_text(text: str) -> dict:
    sections = split_sections(text)
    url = _PROFILE_URL.search(text)
    return {
        "skills": [s for s in sections.get("skills", []) if 1 < len(s) <= 40][:20],
        "certifications": [{"name": c, "authority": ""} for c in sections.get("certifications", [])
                           if len(c) > 2][:15],
        "linkedin_url": f"https://www.{url.group(0).removeprefix('www.')}" if url else "",
        "text": text,
    }
