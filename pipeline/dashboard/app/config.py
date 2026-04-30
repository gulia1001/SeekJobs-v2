from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
PIPELINE_DIR = APP_DIR.parents[1]
DATASET_PATH = PIPELINE_DIR / "data" / "final" / "analysis_ready_jobs_salary_fixed_v3.csv"

APP_TITLE = "IT Jobs KZ Market Intelligence Dashboard"
APP_ICON = "🇰🇿"

COLORS = {
    "bg_primary": "#FFFFFF",
    "bg_card": "#F8FAFC",
    "bg_elevated": "#E2E8F0",
    "accent_blue": "#2563EB",
    "accent_violet": "#7C3AED",
    "accent_cyan": "#0891B2",
    "accent_green": "#059669",
    "accent_orange": "#D97706",
    "accent_red": "#DC2626",
    "text_primary": "#1E293B",
    "text_secondary": "#64748B",
    "text_muted": "#94A3B8",
    "gradient_main": ["#2563EB", "#7C3AED", "#0891B2"],
    "gradient_warm": ["#D97706", "#DC2626", "#7C3AED"],
    "gradient_cool": ["#059669", "#2563EB", "#0891B2"],
}

LEVEL_ORDER = ["intern", "junior", "middle", "senior", "lead", "manager"]
WORK_FORMAT_ORDER = ["office", "hybrid", "remote"]
QUALITY_ORDER = ["A", "B", "C", "D"]
CITY_ORDER = ["almaty", "astana", "other", "remote"]

BOOLEAN_COLUMNS = [
    "english_required",
    "dedup_keep_for_analytics",
    "usable_for_salary_analytics",
    "usable_for_skill_analytics",
    "usable_for_employer_analytics",
    "usable_for_category_analytics",
    "salary_usable_for_analytics",
]

NUMERIC_COLUMNS = [
    "experience_min",
    "experience_max",
    "salary_from_clean",
    "salary_to_clean",
    "salary_avg_clean",
    "skills_count",
    "header_parse_confidence",
]

SKILL_COLUMNS = [
    "hard_skills_clean",
    "soft_skills_clean",
    "tech_stack_clean",
    "skills_all_clean",
]

REQUIRED_COLUMNS = {
    "id": "",
    "source": "Unknown",
    "source_url": "",
    "title_final": "",
    "company_clean": "",
    "city_norm": "",
    "category_filled": "",
    "level_filled": "",
    "experience_min": None,
    "experience_max": None,
    "employment_norm": "",
    "work_format_norm": "",
    "salary_from_clean": None,
    "salary_to_clean": None,
    "salary_avg_clean": None,
    "currency_clean": "",
    "hard_skills_clean": "[]",
    "soft_skills_clean": "[]",
    "tech_stack_clean": "[]",
    "skills_all_clean": "[]",
    "skills_count": 0,
    "english_required": False,
    "english_level_norm": "",
    "quality_tier": "D",
    "dedup_keep_for_analytics": False,
    "usable_for_salary_analytics": False,
    "usable_for_skill_analytics": False,
    "usable_for_employer_analytics": False,
    "usable_for_category_analytics": False,
}

SOURCE_FAMILY_MAP = {
    "hh_kz": "hh_kz",
    "kaspi_jobs": "kaspi",
    "kolesa_jobs": "kolesa",
}

STRUCTURED_SALARY_SOURCES = {"hh_kz", "kaspi_jobs", "kolesa_jobs"}

GLOBAL_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap');

    .stApp {
        background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
        color: #0F172A;
        font-family: 'Montserrat', sans-serif;
        font-size: 16px;
        min-height: 100vh;
    }

    .block-container {
        max-width: 1400px;
        padding-top: 3rem;
        padding-bottom: 2.5rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #2563EB 0%, #7C3AED 45%, #93C5FD 100%);
        border-right: 1px solid rgba(255,255,255,0.12);
        color: #F8FAFC;
        box-shadow: 6px 0 30px rgba(56,189,248,0.08);
    }

    [data-testid="stSidebar"] * {
        color: #F8FAFC !important;
    }

    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown span,
    [data-testid="stSidebar"] .stMarkdown div {
        color: #F8FAFC !important;
    }

    [data-testid="stSidebar"] .stMetricValue,
    [data-testid="stSidebar"] .stMetricLabel,
    [data-testid="stSidebar"] .stMetricDelta {
        color: #F8FAFC !important;
    }

    [data-testid="stSidebar"] .css-1d391kg,
    [data-testid="stSidebar"] .css-15tx938 {
        background-color: rgba(255,255,255,0.08) !important;
    }

    .page-header {
        background: linear-gradient(135deg, #2563EB 0%, #7C3AED 52%, #0891B2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: clamp(2.4rem, 4vw, 3.2rem);
        font-weight: 800;
        line-height: 1.05;
        margin-top: 0.1rem;
        margin-bottom: 0.35rem;
        font-family: 'Montserrat', sans-serif;
        max-width: 100%;
        word-break: break-word;
    }

    .page-subtitle {
        color: #334155;
        margin-bottom: 1.2rem;
        max-width: 980px;
        font-size: clamp(1rem, 1.1vw, 1.15rem);
        font-weight: 500;
        line-height: 1.6;
    }

    @media (max-width: 980px) {
        .block-container {
            padding-left: 1.2rem;
            padding-right: 1.2rem;
        }
        .page-header {
            font-size: clamp(2rem, 8vw, 2.8rem);
        }
        .page-subtitle {
            font-size: 1rem;
            max-width: 100%;
        }
        .navigation-button {
            width: 100%;
        }
    }

    .metric-card {
        background: linear-gradient(135deg, #F8FAFC 0%, #E2E8F0 100%);
        border: 1px solid #CBD5E1;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        min-height: 126px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }

    .metric-label {
        color: #64748B;
        font-size: 0.95rem;
        margin-top: 0.45rem;
        font-weight: 500;
    }

    .metric-value {
        color: #1E293B;
        font-size: 1.9rem;
        font-weight: 800;
        line-height: 1.15;
        margin-top: 0.35rem;
    }

    .metric-delta {
        color: #64748B;
        font-size: 0.92rem;
        margin-top: 0.42rem;
    }

    .section-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06);
    }

    .insight-card {
        background: linear-gradient(160deg, #F8FAFC, #E2E8F0);
        border-left: 4px solid #2563EB;
        border-radius: 14px;
        padding: 0.95rem 1rem;
        color: #1E293B;
        margin-bottom: 0.8rem;
    }

    .job-card {
        background: linear-gradient(135deg, #F8FAFC, #E2E8F0);
        border: 1px solid #0891B2;
        border-radius: 18px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.9rem;
    }

    .job-title {
        color: #1E293B;
        font-size: 1.1rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .job-meta {
        color: #64748B;
        font-size: 0.95rem;
        margin-bottom: 0.45rem;
    }

    .pill {
        display: inline-block;
        padding: 0.25rem 0.55rem;
        margin: 0 0.35rem 0.35rem 0;
        border-radius: 999px;
        background: rgba(37,99,235,0.1);
        color: #1D4ED8;
        font-size: 0.82rem;
        font-weight: 500;
    }

    .stub-box {
        background: rgba(217,119,6,0.1);
        border: 1px solid rgba(217,119,6,0.3);
        border-radius: 14px;
        padding: 0.95rem 1rem;
        color: #92400E;
    }

    .small-note {
        color: #64748B;
        font-size: 0.88rem;
    }

    .stButton > button {
        background: linear-gradient(135deg, #2563EB 0%, #7C3AED 100%);
        color: white;
        border: none;
        border-radius: 18px;
        font-weight: 600;
        padding: 0.75rem 1.4rem;
        box-shadow: 0 6px 22px rgba(37,99,235,0.22);
        font-family: 'Montserrat', sans-serif;
        font-size: 1rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.35rem;
    }

    .stTabs [data-baseweb="tab"] {
        background: #F8FAFC;
        border-radius: 12px;
        border: 1px solid #E2E8F0;
        color: #64748B;
        font-weight: 500;
    }

    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: #2563EB;
        color: white;
    }

    .navigation-button {
        display: inline-block;
        margin: 0.5rem 0.75rem 0.5rem 0;
        padding: 0.75rem 1.4rem;
        background: linear-gradient(135deg, #2563EB 0%, #7C3AED 100%);
        color: white;
        border-radius: 18px;
        text-decoration: none;
        font-weight: 600;
        font-family: 'Montserrat', sans-serif;
        font-size: 1rem;
        box-shadow: 0 6px 24px rgba(37,99,235,0.16);
        transition: transform 0.2s, box-shadow 0.2s;
        width: 100%;
        text-align: center;
    }

    .navigation-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 26px rgba(37,99,235,0.22);
    }

    .js-plotly-plot .main-svg text,
    .js-plotly-plot .main-svg .xtick text,
    .js-plotly-plot .main-svg .ytick text,
    .js-plotly-plot .main-svg .legend text {
        fill: #0F172A !important;
    }

    .js-plotly-plot .main-svg .xaxis line,
    .js-plotly-plot .main-svg .yaxis line,
    .js-plotly-plot .main-svg .xaxis path,
    .js-plotly-plot .main-svg .yaxis path {
        stroke: #CBD5E1 !important;
    }

    .js-plotly-plot .main-svg .gridlayer .xgrid,
    .js-plotly-plot .main-svg .gridlayer .ygrid {
        stroke: rgba(148,163,184,0.24) !important;
    }

    .js-plotly-plot .plotly {
        background: transparent !important;
    }
</style>
"""
