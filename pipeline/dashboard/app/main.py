from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.components.cards import page_header
from app.config import APP_ICON, APP_TITLE, GLOBAL_CSS
from app.data.loader import compute_salary_coverage, load_dataset_bundle
from app.pages import PAGE_DEFINITIONS, load_page_module


def run() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    bundle = load_dataset_bundle()
    df = bundle["all"]
    df_base = bundle["base"]
    df_base_structured = bundle["base_structured"]
    df_salary = bundle["salary"]

    st.sidebar.markdown("## 🇰🇿 IT Jobs KZ")
    st.sidebar.markdown("**Market Intelligence Dashboard**")
    st.sidebar.markdown("*Analysis-ready MVP*")
    st.sidebar.metric("Vacancies in base", f"{len(df_base):,}")

    latest_date = df["scraped_at_dt"].dropna().max()
    if latest_date is not None and not str(latest_date) == "NaT":
        st.sidebar.metric("Updated", latest_date.strftime("%Y-%m-%d"))

    salary_coverage = compute_salary_coverage(len(df_base_structured), len(df_salary))
    st.sidebar.metric("Salary coverage", f"{salary_coverage:.1f}%")
    st.sidebar.caption(
        "Base layer uses `dedup_keep_for_analytics=True`. Salary analytics use only structured sources: `hh_kz`, `kaspi_jobs`, `kolesa_jobs`."
    )

    if "selected_page" not in st.session_state:
        st.session_state.selected_page = PAGE_DEFINITIONS[0].key

    selected_page = next(p for p in PAGE_DEFINITIONS if p.key == st.session_state.selected_page)

    page_header(
        APP_TITLE,
        "Production-style Streamlit dashboard built on `analysis_ready_jobs_salary_fixed_v3.csv`. Salary analytics are intentionally restricted to structured sources: `hh_kz`, `kaspi_jobs`, and `kolesa_jobs`.",
    )

    st.markdown("### Navigation")
    cols = st.columns(len(PAGE_DEFINITIONS), gap="small")
    for i, page in enumerate(PAGE_DEFINITIONS):
        with cols[i]:
            if st.button(f"{page.icon} {page.label}", key=f"nav_{page.key}"):
                st.session_state.selected_page = page.key
                st.rerun()

    st.markdown("---")

    module = load_page_module(selected_page)
    module.render(bundle)


if __name__ == "__main__":
    run()
