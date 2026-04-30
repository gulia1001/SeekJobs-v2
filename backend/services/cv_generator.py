"""Generate a tailored CV using Groq LLM in LaTeX and JSON formats."""
import json
import logging
import os
from groq import AsyncGroq

log = logging.getLogger("seekjobs.cv")


async def generate_tailored_cv(
    job_title: str,
    job_skills: list[str],
    user_profile: dict,
    cv_text: str = "",
    output_format: str = "both",
) -> dict:
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return _fallback_cv(job_title, job_skills, user_profile)

    client = AsyncGroq(api_key=groq_key)

    user_skills = user_profile.get("skills", [])
    user_name = user_profile.get("name") or "Candidate"
    github_summary = user_profile.get("github_summary") or ""
    linkedin_summary = user_profile.get("linkedin_summary") or ""

    combined_info = "\n".join(filter(None, [
        f"Original CV/Bio: {cv_text[:6000]}" if cv_text else "",
        f"GitHub Activity: {github_summary}" if github_summary else "",
        f"LinkedIn Headline/Exp: {linkedin_summary}" if linkedin_summary else "",
        f"Detected skills: {', '.join(user_skills)}",
    ]))
    
    github_url = user_profile.get("github_url") or ""
    linkedin_url = user_profile.get("linkedin_url") or ""
    top_repos = user_profile.get("top_repos") or []
    certifications = user_profile.get("certifications") or []
    
    repos_str = "\n".join([f"- {r['name']}: {r['description']} (Stack: {', '.join(r['stack'])})" for r in top_repos[:5]])
    certs_str = "\n".join([f"- {c['name']} from {c.get('authority', 'N/A')}" for c in certifications])

    prompt = f"""You are a world-class executive CV writer. Create a high-impact, ONE-PAGE tailored CV.

CANDIDATE DATA:
Name: {user_name}
{combined_info}
GitHub: {github_url}
Top Projects:\n{repos_str}
LinkedIn: {linkedin_url}
Certifications:\n{certs_str}

TARGET VACANCY:
Title: {job_title}
Key Skills: {', '.join(job_skills)}

INSTRUCTIONS:
1. Generate a JSON response with the fields below.
2. The 'latex' field must contain a complete, professional LaTeX document using 'article' class. 
3. Use a clean, modern design (similar to the 'Standard CV' or 'John Doe' templates on Overleaf).
4. HIGHLIGHT projects from GitHub that demonstrate the 'Key Skills' of the vacancy.
5. TAILOR the professional summary to explain exactly why this candidate is the best fit for {job_title}.
6. Rephrase experience to lead with achievements (Action Verb + Task + Result).

TRUTHFULNESS RULES (most important — a CV with invented facts hurts the candidate):
- Use ONLY facts found in CANDIDATE DATA above. You may rephrase, reorder and choose what to emphasize.
- NEVER invent employers, job titles, dates, schools, degrees, certificates, numbers/metrics, or contact details.
- Only list skills the candidate actually has. Do NOT add a vacancy Key Skill the candidate lacks.
- If there is no data for a section (e.g. experience or education), return an empty list and leave that section out of the LaTeX.
- "email": copy it from the CV text if present, otherwise "".

OUTPUT JSON STRUCTURE:
{{
  "name": "{user_name}",
  "role": "{job_title}",
  "email": "",
  "github": "{github_url}",
  "linkedin": "{linkedin_url}",
  "summary": "...",
  "experience": [
    {{"title": "...", "company": "...", "period": "...", "description": "..."}}
  ],
  "education": [
    {{"degree": "...", "school": "...", "period": "..."}}
  ],
  "projects": [
    {{"name": "...", "description": "...", "tech": "..."}}
  ],
  "skills": ["...", "..."],
  "certificates": ["...", "..."],
  "latex": "Full LaTeX code here"
}}

LATEX TEMPLATE REQUIREMENTS:
- Use \\documentclass[11pt,letterpaper]{{article}}
- Use \\usepackage[margin=0.5in]{{geometry}}
- Use \\usepackage{{titlesec}} for section styling.
- Use \\usepackage{{hyperref}} for links.
- Use \\usepackage{{enumitem}} for lists.
- Sections: Summary, Technical Skills, Experience, Projects (from GitHub), Education, Certifications.
- MUST FIT ON ONE PAGE. Use max 3 experience entries and max 2 bullets each.
- Professional summary must be under 40 words.
- Output ONLY valid JSON."
"""

    try:
        resp = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        cv_data = json.loads(raw)
        
        # Normalize field names just in case
        if "certifications" in cv_data and "certificates" not in cv_data:
            cv_data["certificates"] = cv_data.pop("certifications")
            
        log.debug("AI generated CV keys: %s", list(cv_data.keys()))

        # Ensure we have all required fields
        if "latex" not in cv_data or not cv_data["latex"]:
            log.info("LaTeX missing from AI response, generating fallback")
            cv_data["latex"] = _generate_latex_fallback(cv_data, job_title, job_skills)

        return cv_data
    except Exception as e:
        log.warning("AI CV generation failed, using fallback: %s", e)
        return _fallback_cv(job_title, job_skills, user_profile, github_url, linkedin_url)


def _fallback_cv(job_title: str, job_skills: list[str], user_profile: dict, github_url: str = "", linkedin_url: str = "") -> dict:
    name = user_profile.get("name") or "Candidate"
    # Only the candidate's own skills — the ones this job asks for come first.
    wanted = {s.casefold() for s in job_skills}
    own = list(dict.fromkeys(user_profile.get("skills", [])))
    skills = sorted(own, key=lambda s: s.casefold() not in wanted)[:15]
    
    cv_data = {
        "name": name,
        "role": job_title,
        "email": user_profile.get("email") or "",
        "github": github_url or user_profile.get("github_url") or "",
        "linkedin": linkedin_url or user_profile.get("linkedin_url") or "",
        "summary": (
            f"Skilled professional with expertise in {', '.join(skills[:3])}. "
            f"Seeking {job_title} position."
        ),
        "experience": [],
        "projects": [],
        "education": [],
        "skills": skills,
        "certificates": [],
        "tailored_note": f"This CV highlights skills most relevant to the {job_title} role.",
    }
    
    # Generate LaTeX fallback
    cv_data["latex"] = _generate_latex_fallback(cv_data, job_title, job_skills)
    return cv_data


def _generate_latex_fallback(cv_data: dict, job_title: str, job_skills: list[str]) -> str:
    """Generate a one-page LaTeX CV."""
    name = cv_data.get("name", "Candidate")
    email = cv_data.get("email", "")
    github = cv_data.get("github", "")
    linkedin = cv_data.get("linkedin", "")
    summary = cv_data.get("summary", "")
    skills = cv_data.get("skills", [])[:15]
    experience = cv_data.get("experience", [])[:3]
    projects = cv_data.get("projects", [])[:3]
    education = cv_data.get("education", [])[:2]
    certificates = cv_data.get("certificates", [])[:3]
    
    contact_info = []
    if email:
        contact_info.append(f"\\href{{mailto:{email}}}{{{email}}}")
    if linkedin:
        contact_info.append(f"\\href{{{linkedin}}}{{LinkedIn}}")
    if github:
        contact_info.append(f"\\href{{{github}}}{{GitHub}}")
    
    contact_str = " | ".join(contact_info)
    
    latex = f"""\\documentclass[11pt,letterpaper]{{article}}
\\usepackage[margin=0.5in]{{geometry}}
\\usepackage{{hyperref}}
\\usepackage{{enumitem}}
\\usepackage{{titlesec}}
\\setlist{{nolistsep}}
\\raggedbottom

\\titleformat{{\\section}}{{\\bfseries\\large}}{{}}{{0em}}{{\\uppercase}}[\\titlerule]
\\titlespacing{{\\section}}{{0pt}}{{8pt}}{{4pt}}

\\begin{{document}}
\\thispagestyle{{empty}}

% Header
{{\\centering
\\textbf{{\\Large {name}}} \\\\
{job_title} \\\\
{contact_str}
}}

% Professional Summary
\\section{{Professional Summary}}
{summary}

% Skills
\\section{{Technical Skills}}
\\textbf{{Key Skills:}} {', '.join(skills)}

% Experience
"""
    
    if experience:
        latex += "\\section{{Experience}}\n"
        for exp in experience:
            title = exp.get("title", "")
            company = exp.get("company", "")
            period = exp.get("period", "")
            desc = exp.get("description", "")
            latex += f"\\textbf{{{title}}} — {company} \\hfill \\textit{{{period}}} \\\\\n"
            latex += f"{desc} \\\\\n\\vspace{{4pt}}\n"

    if projects:
        latex += "\\section{{Projects}}\n"
        for proj in projects:
            pname = proj.get("name", "")
            pdesc = proj.get("description", "")
            ptech = proj.get("tech", "")
            latex += f"\\textbf{{{pname}}} ({ptech}) \\\\\n"
            latex += f"{pdesc} \\\\\n\\vspace{{4pt}}\n"

    if education:
        latex += "\\section{{Education}}\n"
        for edu in education:
            degree = edu.get("degree", "")
            school = edu.get("school", "")
            period = edu.get("period", "")
            latex += f"\\textbf{{{degree}}} — {school} \\hfill \\textit{{{period}}} \\\\\n"

    if certificates:
        latex += "\\section{{Certifications}}\n"
        latex += "\\begin{itemize}\n"
        for cert in certificates:
            latex += f"\\item {cert}\n"
        latex += "\\end{itemize}\n"

    latex += "\\end{document}"
    return latex
