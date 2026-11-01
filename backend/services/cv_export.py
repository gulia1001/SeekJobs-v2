"""Export a generated CV (the JSON from cv_generator) to PDF or Word (.docx).

Both outputs contain real text (not images), so applicant-tracking systems can read them.
The PDF needs a Unicode TTF font for Russian/Kazakh text. It is found on the system
(DejaVu on Linux/Docker, Arial on Windows/macOS) or set with CV_FONT_REGULAR / CV_FONT_BOLD.
"""
from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("seekjobs.cv_export")

_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]

# order of <w:pPr> children after <w:pBdr> (Word rejects out-of-order elements)
_PBDR_SUCCESSORS = (
    "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
    "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
    "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
    "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
    "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)


def find_font() -> tuple[str, str | None] | None:
    """(regular, bold) TTF paths, or None if no Unicode font is available."""
    candidates = [(os.getenv("CV_FONT_REGULAR", ""), os.getenv("CV_FONT_BOLD", ""))] + _FONT_CANDIDATES
    for regular, bold in candidates:
        if regular and Path(regular).is_file():
            return regular, bold if bold and Path(bold).is_file() else None
    return None


# ── normalize the LLM's JSON (shapes vary: str vs list vs dict) ─────────────
def _s(value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    if isinstance(value, dict):
        return _s(value.get("name") or value.get("title"))
    if isinstance(value, (list, tuple)):
        return ", ".join(t for t in (_s(v) for v in value) if t)
    return str(value).strip()


def _lines(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = [_s(v) for v in value]
    else:
        items = [line.strip(" \t-•*") for line in _s(value).splitlines()]
    return [i for i in items if i]


def _names(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [n for n in (_s(v) for v in (value or [])) if n]


def normalize_cv(cv: dict) -> dict:
    def certificate(c) -> str:
        if isinstance(c, dict):
            return " — ".join(filter(None, [_s(c.get("name") or c.get("title")), _s(c.get("authority"))]))
        return _s(c)

    return {
        "name": _s(cv.get("name")) or "Candidate",
        "role": _s(cv.get("role")),
        "contacts": [c for c in (_s(cv.get(k)) for k in ("email", "phone", "linkedin", "github")) if c],
        "summary": _s(cv.get("summary")),
        "skills": _names(cv.get("skills")),
        "experience": [
            {"left": " — ".join(filter(None, [_s(e.get("title")), _s(e.get("company"))])),
             "right": _s(e.get("period")), "lines": _lines(e.get("description"))}
            for e in (cv.get("experience") or []) if isinstance(e, dict)
        ],
        "projects": [
            {"left": _s(p.get("name")) + (f" ({_s(p.get('tech'))})" if _s(p.get("tech")) else ""),
             "right": "", "lines": _lines(p.get("description"))}
            for p in (cv.get("projects") or []) if isinstance(p, dict)
        ],
        "education": [
            {"left": " — ".join(filter(None, [_s(e.get("degree")), _s(e.get("school"))])),
             "right": _s(e.get("period")), "lines": []}
            for e in (cv.get("education") or []) if isinstance(e, dict)
        ],
        "certificates": [c for c in (certificate(c) for c in (cv.get("certificates") or [])) if c],
    }


def export_filename(cv: dict, ext: str) -> str:
    base = "_".join(filter(None, ["CV", _s(cv.get("name")), _s(cv.get("role"))]))
    base = re.sub(r"[^\w-]+", "_", base).strip("_")[:80]
    return f"{base or 'CV'}.{ext}"


# ── PDF ─────────────────────────────────────────────────────────────────────
def to_pdf(cv: dict) -> bytes:
    from fpdf import FPDF

    data = normalize_cv(cv)
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(15, 14, 15)
    pdf.set_auto_page_break(True, margin=14)
    pdf.add_page()

    font = find_font()
    if font:
        pdf.add_font("CV", "", font[0])
        pdf.add_font("CV", "B", font[1] or font[0])
        family, bullet = "CV", "•"
        clean = lambda t: t  # noqa: E731
    else:
        log.warning("No Unicode TTF font found; non-Latin text will show as '?'. Set CV_FONT_REGULAR.")
        family, bullet = "Helvetica", "-"
        clean = lambda t: t.replace("—", "-").encode("latin-1", "replace").decode("latin-1")  # noqa: E731

    width = pdf.epw

    def text(t: str, size: float, bold=False, color=(40, 40, 40), h=4.8):
        pdf.set_font(family, "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.multi_cell(0, h, clean(t), new_x="LMARGIN", new_y="NEXT")

    def section(title: str):
        pdf.ln(2.5)
        pdf.set_font(family, "B", 11)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(0, 6, clean(title.upper()), new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y()
        pdf.set_draw_color(160, 160, 160)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, y, pdf.l_margin + width, y)
        pdf.ln(1.5)

    def entry(item: dict):
        left, right = clean(item["left"]), clean(item["right"])
        pdf.set_font(family, "", 9)
        right_w = pdf.get_string_width(right) + 1 if right else 0
        pdf.set_font(family, "B", 10)
        pdf.set_text_color(0, 0, 0)
        if right and pdf.get_string_width(left) + right_w + 2 <= width:
            pdf.cell(width - right_w, 5, left)
            pdf.set_font(family, "", 9)
            pdf.set_text_color(90, 90, 90)
            pdf.cell(right_w, 5, right, align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 5, left, new_x="LMARGIN", new_y="NEXT")
            if right:
                text(right, 9, color=(90, 90, 90), h=4.5)
        pdf.set_font(family, "", 10)
        pdf.set_text_color(40, 40, 40)
        for line in item["lines"]:
            pdf.set_x(pdf.l_margin + 3)
            pdf.multi_cell(width - 3, 4.8, f"{bullet} {clean(line)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.2)

    text(data["name"], 18, bold=True, color=(0, 0, 0), h=8)
    if data["role"]:
        text(data["role"], 11.5, color=(70, 70, 70), h=6)
    if data["contacts"]:
        text("  |  ".join(data["contacts"]), 9, color=(70, 70, 70), h=4.5)
    if data["summary"]:
        section("Professional Summary")
        text(data["summary"], 10)
    if data["skills"]:
        section("Technical Skills")
        text(", ".join(data["skills"]), 10)
    for title, key in (("Experience", "experience"), ("Projects", "projects"), ("Education", "education")):
        if data[key]:
            section(title)
            for item in data[key]:
                entry(item)
    if data["certificates"]:
        section("Certifications")
        for c in data["certificates"]:
            text(f"{bullet} {c}", 10)

    return bytes(pdf.output())


# ── Word ────────────────────────────────────────────────────────────────────
def to_docx(cv: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Emu, Pt, RGBColor

    data = normalize_cv(cv)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)  # A4
    sec.left_margin = sec.right_margin = Cm(1.6)
    sec.top_margin = sec.bottom_margin = Cm(1.4)
    usable = Emu(sec.page_width - sec.left_margin - sec.right_margin)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)

    def para(text: str = "", size: float | None = None, bold=False, color=None, after=2.0):
        p = doc.add_paragraph()
        if text:
            run = p.add_run(text)
            run.bold = bold
            if size:
                run.font.size = Pt(size)
            if color:
                run.font.color.rgb = RGBColor(*color)
        p.paragraph_format.space_after = Pt(after)
        return p

    def section(title: str):
        p = para(title.upper(), size=11, bold=True, after=3)
        p.paragraph_format.space_before = Pt(8)
        border = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "999999")):
            bottom.set(qn(k), v)
        border.append(bottom)
        p._p.get_or_add_pPr().insert_element_before(border, *_PBDR_SUCCESSORS)

    def entry(item: dict):
        p = para(after=1)
        p.paragraph_format.tab_stops.add_tab_stop(usable, WD_TAB_ALIGNMENT.RIGHT)
        p.add_run(item["left"]).bold = True
        if item["right"]:
            run = p.add_run("\t" + item["right"])
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(90, 90, 90)
        for line in item["lines"]:
            doc.add_paragraph(line, style="List Bullet").paragraph_format.space_after = Pt(1)

    para(data["name"], size=20, bold=True, after=0)
    if data["role"]:
        para(data["role"], size=12, color=(70, 70, 70), after=0)
    if data["contacts"]:
        para("  |  ".join(data["contacts"]), size=9, color=(70, 70, 70), after=4)
    if data["summary"]:
        section("Professional Summary")
        para(data["summary"])
    if data["skills"]:
        section("Technical Skills")
        para(", ".join(data["skills"]))
    for title, key in (("Experience", "experience"), ("Projects", "projects"), ("Education", "education")):
        if data[key]:
            section(title)
            for item in data[key]:
                entry(item)
    if data["certificates"]:
        section("Certifications")
        for c in data["certificates"]:
            doc.add_paragraph(c, style="List Bullet")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
