import io

import pdfplumber
import pytest
from docx import Document

from services.cv_export import export_filename, find_font, to_docx, to_pdf

CV = {
    "name": "Айгерим Нурланова",
    "role": "Backend-разработчик",
    "email": "aigerim@example.com",
    "github": "https://github.com/aigerim",
    "summary": "Backend developer from Қазақстан with 2 years of Python.",
    # the LLM returns these in different shapes — all must work
    "experience": [
        {"title": "Backend Developer", "company": "DemoTech", "period": "2023 – now",
         "description": ["Built REST APIs with FastAPI", "Cut response time by 30%"]},
        {"title": "Intern", "company": "Steppe Soft", "period": "2022", "description": "Wrote tests\nFixed bugs"},
    ],
    "projects": [{"name": "SeekJobs", "tech": ["Python", "Next.js"], "description": "Job matching app"}],
    "education": [{"degree": "BSc Computer Science", "school": "AITU", "period": "2019 – 2023"}],
    "skills": ["Python", {"name": "Docker"}, "PostgreSQL"],
    "certificates": [{"name": "AWS Cloud Practitioner", "authority": "Amazon"}, "IELTS 7.0"],
}


def pdf_text(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_pdf_has_real_text():
    data = to_pdf(CV)
    assert data.startswith(b"%PDF-")
    text = pdf_text(data)
    for expected in ("Backend Developer", "DemoTech", "Built REST APIs with FastAPI", "Wrote tests", "AITU", "Amazon"):
        assert expected in text


@pytest.mark.skipif(find_font() is None, reason="no Unicode TTF font on this machine")
def test_pdf_shows_russian_and_kazakh_letters():
    text = pdf_text(to_pdf(CV))
    assert "Айгерим Нурланова" in text
    assert "Қазақстан" in text


def test_docx_content_and_bullets():
    doc = Document(io.BytesIO(to_docx(CV)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Айгерим Нурланова" in text and "Қазақстан" in text
    assert "Built REST APIs with FastAPI" in [p.text for p in doc.paragraphs if p.style.name == "List Bullet"]


def test_docx_section_border_is_in_valid_position():
    """Word refuses files whose <w:pPr> children are out of schema order."""
    doc = Document(io.BytesIO(to_docx(CV)))
    for p in doc.paragraphs:
        tags = [child.tag.split("}")[1] for child in p._p.pPr] if p._p.pPr is not None else []
        if "pBdr" in tags and "spacing" in tags:
            assert tags.index("pBdr") < tags.index("spacing")


def test_empty_cv_does_not_crash():
    assert to_pdf({}).startswith(b"%PDF-")
    assert to_docx({})[:2] == b"PK"


def test_filename_keeps_cyrillic():
    assert export_filename(CV, "pdf") == "CV_Айгерим_Нурланова_Backend-разработчик.pdf"


@pytest.mark.parametrize("fmt, media", [
    ("pdf", "application/pdf"),
    ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
])
def test_export_endpoint(client, fmt, media):
    r = client.post("/api/cv/export", json={"cv": CV, "format": fmt})
    assert r.status_code == 200
    assert r.headers["content-type"] == media
    assert "filename*=UTF-8''CV_" in r.headers["content-disposition"]


def test_export_rejects_unknown_format(client):
    assert client.post("/api/cv/export", json={"cv": CV, "format": "exe"}).status_code == 422
