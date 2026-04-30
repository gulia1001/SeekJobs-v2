from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components.cards import insight_card, page_header, render_metric_cards
from app.components.charts import apply_figure_style, donut_chart, empty_figure, heatmap_chart, horizontal_bar
from app.components.filters import apply_filters, render_sidebar_filters
from app.config import COLORS
from app.data.loader import compute_salary_coverage


def _safe_percent(series: pd.Series, value: str) -> float:
    valid = series.dropna().astype(str)
    if valid.empty:
        return 0.0
    return round((valid == value).mean() * 100, 1)


def render(bundle: dict[str, object]) -> None:
    df_base = bundle["base"]
    df_base_structured = bundle["base_structured"]
    df_category = bundle["category"]
    df_salary = bundle["salary"]

    page_header(
        "🏠 Market Overview",
        "Conference-style snapshot of the Kazakhstan IT job market with robust fallbacks for sparse salary, city, and skill fields.",
    )

    filters = render_sidebar_filters(
        df_base,
        prefix="market",
        include=["city", "category", "level", "work_format", "source", "quality_tier", "salary_range", "english_required"],
        title="Market filters",
    )
    base_filtered = apply_filters(df_base, filters)
    base_structured_filtered = apply_filters(df_base_structured, filters)
    category_filtered = apply_filters(df_category, filters)
    salary_filtered = apply_filters(df_salary, filters)

    if base_filtered.empty:
        st.warning("No vacancies match the current filters. Try widening city, category, or quality constraints.")
        return

    unique_hard_skills = (
        pd.Series([skill for skills in base_filtered["hard_skills_clean_list"] for skill in skills]).nunique()
        if "hard_skills_clean_list" in base_filtered
        else 0
    )
    salary_coverage = compute_salary_coverage(len(base_structured_filtered), len(salary_filtered))
    remote_pct = _safe_percent(base_filtered["work_format_norm"], "remote")
    median_salary = salary_filtered["salary_avg_clean"].median()

    render_metric_cards(
        [
            {"icon": "💼", "label": "Total vacancies", "value": f"{len(base_filtered):,}", "delta": "Base deduped market", "color": "accent_blue"},
            {"icon": "💰", "label": "Median salary", "value": f"{median_salary:,.0f} ₸" if pd.notna(median_salary) else "Not enough salary data", "delta": f"Structured-source coverage {salary_coverage:.1f}%", "color": "accent_green"},
            {"icon": "🏢", "label": "Companies", "value": f"{base_filtered['company_clean'].replace('', pd.NA).dropna().nunique():,}", "delta": "Distinct employers", "color": "accent_violet"},
            {"icon": "🛠️", "label": "Unique hard skills", "value": f"{unique_hard_skills:,}", "delta": "Canonicalized skills", "color": "accent_cyan"},
            {"icon": "🌐", "label": "Remote share", "value": f"{remote_pct:.1f}%", "delta": "From filtered market", "color": "accent_orange"},
        ]
    )

    left, right = st.columns((1.15, 0.85))

    with left:
        treemap_data = (
            category_filtered[category_filtered["category_filled"] != ""]
            .assign(
                level_treemap=lambda frame: frame["level_filled"]
                .astype(object)
                .where(frame["level_filled"].notna(), "level_unresolved")
                .astype(str)
                .replace({"": "level_unresolved", "nan": "level_unresolved"})
            )
            .groupby(["category_filled", "level_treemap"], dropna=False)
            .agg(count=("id", "count"))
            .reset_index()
        )
        salary_treemap = (
            salary_filtered[salary_filtered["category_filled"] != ""]
            .assign(
                level_treemap=lambda frame: frame["level_filled"]
                .astype(object)
                .where(frame["level_filled"].notna(), "level_unresolved")
                .astype(str)
                .replace({"": "level_unresolved", "nan": "level_unresolved"})
            )
            .groupby(["category_filled", "level_treemap"], dropna=False)
            .agg(median_salary=("salary_avg_clean", "median"))
            .reset_index()
        )
        treemap_data = treemap_data.merge(
            salary_treemap,
            on=["category_filled", "level_treemap"],
            how="left",
        )
        if treemap_data.empty:
            st.plotly_chart(empty_figure("Not enough category data for the market map."), use_container_width=True)
        else:
            fig = px.treemap(
                treemap_data,
                path=["category_filled", "level_treemap"],
                values="count",
                color="median_salary",
                color_continuous_scale="Viridis",
            )
            st.plotly_chart(
                apply_figure_style(
                    fig,
                    title="IT market map: box size = demand, color = median salary",
                    height=500,
                ),
                use_container_width=True,
            )

    with right:
        city_data = base_filtered.assign(
            city_group=lambda frame: frame["city_bucket"].astype(str).replace({"remote": "other"})
        )["city_group"].value_counts().rename_axis("city_group").reset_index(name="vacancies")
        st.plotly_chart(
            donut_chart(
                city_data,
                names="city_group",
                values="vacancies",
                title="City distribution",
                colors=[COLORS["accent_blue"], COLORS["accent_violet"], COLORS["text_muted"]],
            ),
            use_container_width=True,
        )

    category_work_format = (
        category_filtered[category_filtered["category_filled"] != ""]
        .groupby(["category_filled", "work_format_norm"], dropna=False)
        .size()
        .reset_index(name="vacancies")
    )
    top_categories = (
        category_work_format.groupby("category_filled")["vacancies"].sum().nlargest(15).index.tolist()
    )
    category_work_format = category_work_format[category_work_format["category_filled"].isin(top_categories)]
    st.plotly_chart(
        horizontal_bar(
            category_work_format.sort_values("vacancies"),
            x="vacancies",
            y="category_filled",
            color="work_format_norm",
            title="Top categories by demand and work format",
            color_scale=[COLORS["accent_blue"], COLORS["accent_violet"], COLORS["accent_cyan"]],
        ),
        use_container_width=True,
    )

    level_city = (
        base_filtered.assign(city_group=lambda frame: frame["city_bucket"].astype(str).replace({"remote": "other"}))
        .groupby(["level_filled", "city_group"], dropna=False)
        .size()
        .reset_index(name="vacancies")
    )
    if level_city.empty:
        st.plotly_chart(empty_figure("Not enough level data for the city comparison."), use_container_width=True)
    else:
        fig = px.bar(
            level_city,
            x="level_filled",
            y="vacancies",
            color="city_group",
            barmode="group",
            color_discrete_sequence=[COLORS["accent_blue"], COLORS["accent_violet"], COLORS["accent_cyan"]],
        )
        st.plotly_chart(apply_figure_style(fig, title="Level distribution by city"), use_container_width=True)

    salary_scatter = salary_filtered[
        salary_filtered["salary_avg_clean"].notna() & salary_filtered["experience_min"].notna()
    ].copy()
    if salary_scatter.empty:
        st.plotly_chart(empty_figure("Not enough salary and experience pairs for the scatter plot."), use_container_width=True)
    else:
        fig = px.scatter(
            salary_scatter,
            x="experience_min",
            y="salary_avg_clean",
            color="category_filled",
            size="skills_count",
            hover_name="title_display",
            hover_data=["company_display", "city_norm", "work_format_norm"],
            color_discrete_sequence=COLORS["gradient_main"],
        )
        st.plotly_chart(
            apply_figure_style(fig, title="Salary vs experience", height=450, legend_title="Category"),
            use_container_width=True,
        )

    heatmap_source = (
        category_filtered[category_filtered["category_filled"] != ""]
        .groupby(["category_filled", "work_format_norm"])
        .size()
        .unstack(fill_value=0)
    )
    if heatmap_source.empty:
        st.plotly_chart(empty_figure("Not enough data for the remote-work heatmap."), use_container_width=True)
    else:
        heatmap_pct = heatmap_source.div(heatmap_source.sum(axis=1), axis=0).mul(100).round(1)
        st.plotly_chart(
            heatmap_chart(
                heatmap_pct,
                title="Remote / hybrid / office mix by category",
                colorbar_title="% of category",
                zmin=0,
                zmax=100,
            ),
            use_container_width=True,
        )

    st.subheader("Featured Insights")
    top_category = base_filtered["category_filled"].replace("", pd.NA).dropna().value_counts()
    top_category_name = top_category.index[0] if not top_category.empty else "n/a"
    top_category_count = int(top_category.iloc[0]) if not top_category.empty else 0

    top_salary_category = (
        salary_filtered.groupby("category_filled")["salary_avg_clean"].median().dropna().sort_values(ascending=False)
    )
    premium_text = "Not enough data"
    if not salary_filtered.empty:
        eng_yes = salary_filtered[salary_filtered["english_required"]].groupby("category_filled")["salary_avg_clean"].median()
        eng_no = salary_filtered[~salary_filtered["english_required"]].groupby("category_filled")["salary_avg_clean"].median()
        eng_premium = ((eng_yes - eng_no) / eng_no.replace(0, pd.NA) * 100).dropna().sort_values(ascending=False)
        if not eng_premium.empty:
            premium_text = f"English premium peaks in **{eng_premium.index[0]}** at **{eng_premium.iloc[0]:.1f}%**."

    insight_card(f"🔥 Most demanded category right now: **{top_category_name}** with **{top_category_count:,}** vacancies.")
    insight_card(f"🌐 Remote-friendly roles account for **{remote_pct:.1f}%** of the filtered market.")
    if not top_salary_category.empty:
        insight_card(
            f"💸 Highest paid category in the structured-source salary slice: **{top_salary_category.index[0]}** with median salary **{top_salary_category.iloc[0]:,.0f} ₸**."
        )
    insight_card(f"📊 Structured-source salary data is available for **{salary_coverage:.1f}%** of the filtered structured vacancies.")
    insight_card(f"🗣️ {premium_text}")
