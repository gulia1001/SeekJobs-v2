from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components.cards import page_header, render_metric_cards
from app.components.charts import apply_figure_style, empty_figure, heatmap_chart, horizontal_bar
from app.components.filters import apply_filters, render_sidebar_filters
from app.data.loader import compute_salary_coverage


def render(bundle: dict[str, object]) -> None:
    df_base = bundle["base"]
    df_employer = bundle["employer"]

    page_header(
        "🏢 Companies",
        "Employer hiring patterns, salary positioning, role mix, and work-format strategy across the most active companies in the dataset. Salary metrics on this page use structured sources only.",
    )

    filters = render_sidebar_filters(
        df_employer,
        prefix="companies",
        include=["city", "category", "level", "work_format", "source", "quality_tier", "company", "salary_range"],
        title="Company filters",
    )
    employer_filtered = apply_filters(df_employer, filters)
    base_filtered = apply_filters(df_base, filters)

    if employer_filtered.empty:
        st.warning("No employer-usable vacancies match the current filters.")
        return

    company_counts = employer_filtered["company_clean"].replace("", pd.NA).dropna().value_counts()
    salary_coverage = compute_salary_coverage(len(base_filtered), employer_filtered["salary_avg_analytics"].notna().sum())
    render_metric_cards(
        [
            {"icon": "🏢", "label": "Companies in slice", "value": f"{company_counts.size:,}", "delta": "Usable for employer analytics", "color": "accent_blue"},
            {"icon": "📣", "label": "Hiring companies", "value": f"{int((company_counts >= 2).sum()):,}", "delta": "At least 2 open roles", "color": "accent_violet"},
            {"icon": "💰", "label": "Salary coverage", "value": f"{salary_coverage:.1f}%", "delta": "Rows with salary data", "color": "accent_green"},
            {"icon": "🌐", "label": "Remote share", "value": f"{(employer_filtered['work_format_norm'].astype(str) == 'remote').mean() * 100:.1f}%", "delta": "Within employer slice", "color": "accent_orange"},
        ]
    )

    company_summary = (
        employer_filtered[employer_filtered["company_clean"] != ""]
        .groupby("company_clean")
        .agg(
            vacancies=("id", "count"),
            median_salary=("salary_avg_analytics", "median"),
            avg_skills=("skills_count", "mean"),
            open_roles=("title_display", lambda x: ", ".join(pd.Series(x).dropna().astype(str).unique()[:4])),
        )
        .sort_values("vacancies", ascending=False)
        .head(20)
        .reset_index()
    )
    if company_summary.empty:
        st.plotly_chart(empty_figure("No company summary is available for the current filters."), use_container_width=True)
    else:
        st.plotly_chart(
            horizontal_bar(
                company_summary.sort_values("vacancies"),
                x="vacancies",
                y="company_clean",
                color="median_salary",
                title="Top employers by number of vacancies",
            ),
            use_container_width=True,
        )

    scatter_data = company_summary[company_summary["vacancies"] >= 2].copy()
    if scatter_data.empty:
        st.plotly_chart(empty_figure("Need at least a few repeated-company rows for the salary benchmark scatter."), use_container_width=True)
    else:
        fig = px.scatter(
            scatter_data,
            x="vacancies",
            y="median_salary",
            size="avg_skills",
            text="company_clean",
            hover_data=["open_roles"],
            color="vacancies",
            color_continuous_scale="Viridis",
        )
        fig.update_traces(textposition="top center")
        st.plotly_chart(
            apply_figure_style(fig, title="Company salary benchmark: volume × pay × skill density", height=480),
            use_container_width=True,
        )

    top_companies = company_summary["company_clean"].head(12).tolist()
    category_heatmap = (
        employer_filtered[employer_filtered["company_clean"].isin(top_companies)]
        .groupby(["company_clean", "category_filled"])["id"]
        .count()
        .unstack(fill_value=0)
    )
    st.plotly_chart(
        heatmap_chart(category_heatmap, title="Hiring category mix by company", colorbar_title="Vacancies"),
        use_container_width=True,
    )

    work_format_company = (
        employer_filtered[employer_filtered["company_clean"].isin(top_companies)]
        .groupby(["company_clean", "work_format_norm"])["id"]
        .count()
        .reset_index(name="vacancies")
    )
    if work_format_company.empty:
        st.plotly_chart(empty_figure("No work-format split is available."), use_container_width=True)
    else:
        fig = px.bar(
            work_format_company,
            x="vacancies",
            y="company_clean",
            color="work_format_norm",
            orientation="h",
            barmode="stack",
        )
        st.plotly_chart(
            apply_figure_style(fig, title="Work format mix by top employer", legend_title="Work format"),
            use_container_width=True,
        )

    st.subheader("Employer detail table")
    st.dataframe(
        company_summary.rename(
            columns={
                "company_clean": "company",
                "vacancies": "vacancies",
                "median_salary": "median_salary_kzt",
                "avg_skills": "avg_skills_count",
                "open_roles": "sample_open_roles",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
