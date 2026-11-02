"""LinkedIn profile PDF ("Save to PDF"): two columns — sidebar left, main text right."""
import pytest
from fpdf import FPDF

from services.linkedin_pdf import parse_linkedin_text, pdf_text

SIDEBAR = ["Contact", "www.linkedin.com/in/aigerim-n", "(LinkedIn)", "Top Skills", "FastAPI",
           "PostgreSQL", "Docker", "Certifications", "AWS Cloud Practitioner"]
MAIN = ["Aigerim Nurlanova", "Backend Developer at DemoTech", "Almaty, Kazakhstan", "Summary",
        "Backend developer who likes clean APIs.", "Experience", "DemoTech", "Backend Developer",
        "2023 - Present", "Built REST APIs with Python and Kafka.", "Education", "AITU"]


def linkedin_like_pdf() -> bytes:
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for i in range(max(len(SIDEBAR), len(MAIN))):  # same rows in both columns, like the real file
        y = 20 + i * 8
        if i < len(SIDEBAR):
            pdf.text(12, y, SIDEBAR[i])
        if i < len(MAIN):
            pdf.text(80, y, MAIN[i])
    return bytes(pdf.output())


@pytest.fixture(scope="module")
def parsed():
    return parse_linkedin_text(pdf_text(linkedin_like_pdf()))


def test_columns_are_not_mixed(parsed):
    assert "Top Skills\nFastAPI" in parsed["text"]


def test_sections(parsed):
    assert parsed["skills"] == ["FastAPI", "PostgreSQL", "Docker"]
    assert parsed["certifications"] == [{"name": "AWS Cloud Practitioner", "authority": ""}]
    assert parsed["linkedin_url"] == "https://www.linkedin.com/in/aigerim-n"


def test_russian_headings():
    text = "Контактная информация\nlinkedin.com/in/ivan\nОсновные навыки\nPython\nSQL\nОпыт работы\nKaspi"
    parsed = parse_linkedin_text(text)
    assert parsed["skills"] == ["Python", "SQL"]
    assert parsed["linkedin_url"] == "https://www.linkedin.com/in/ivan"


def test_analyze_with_linkedin_pdf_only(client):
    r = client.post("/api/analyze", files={"linkedin_pdf": ("Profile.pdf", linkedin_like_pdf(), "application/pdf")})
    assert r.status_code == 200
    profile = r.json()["profile"]
    assert {"FastAPI", "PostgreSQL", "Docker", "Python"} <= set(profile["skills"])
    assert profile["linkedin_url"] == "https://www.linkedin.com/in/aigerim-n"
    assert profile["certifications"][0]["name"] == "AWS Cloud Practitioner"
    assert "Built REST APIs" in profile["cv_text"]  # experience reaches the tailored CV


def test_linkedin_upload_must_be_pdf(client):
    r = client.post("/api/analyze", files={"linkedin_pdf": ("profile.docx", b"PK..", "application/octet-stream")})
    assert r.status_code == 415


def test_broken_pdf_gives_clear_error(client):
    r = client.post("/api/analyze", files={"linkedin_pdf": ("Profile.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 422
    assert "Save to PDF" in r.json()["detail"]
