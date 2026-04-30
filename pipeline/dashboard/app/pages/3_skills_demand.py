from __future__ import annotations

from collections import Counter
from itertools import combinations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.components.cards import page_header, render_metric_cards
from app.components.charts import apply_figure_style, bubble_cloud, empty_figure, heatmap_chart, horizontal_bar
from app.components.filters import apply_filters, render_sidebar_filters
from app.config import COLORS
from app.data.loader import explode_skills


def _skill_family(skill: str) -> str:
    token = skill.casefold()
    if any(word in token for word in ["python", "java", "go", "scala", "c#", "php", "sql", "javascript", "typescript"]):
        return "language"
    if any(word in token for word in ["react", "vue", "angular", "django", "flask", "spring", "fastapi", "laravel"]):
        return "framework"
    if any(word in token for word in ["docker", "kubernetes", "aws", "azure", "gcp", "terraform", "airflow", "jenkins"]):
        return "cloud_devops"
    if any(word in token for word in ["power bi", "tableau", "looker", "superset", "excel", "etl", "dbt"]):
        return "analytics_bi"
    return "other"


def _co_occurrence_matrix(rows: pd.Series, top_skills: list[str]) -> pd.DataFrame:
    matrix = pd.DataFrame(0, index=top_skills, columns=top_skills)
    top_set = set(top_skills)
    for skills in rows:
        tokens = sorted({skill for skill in skills if skill in top_set})
        for left, right in combinations(tokens, 2):
            matrix.loc[left, right] += 1
            matrix.loc[right, left] += 1
        for token in tokens:
            matrix.loc[token, token] += 1
    return matrix


def render(bundle: dict[str, object]) -> None:
    df_skills = bundle["skills"]

    page_header(
        "🛠️ Skills Demand",
        "Demand, salary correlation, co-occurrence, and level patterns for hard skills, soft skills, and technology stacks.",
    )

    filters = render_sidebar_filters(
        df_skills,
        prefix="skills",
        include=["category", "city", "level", "source", "quality_tier", "min_vacancies", "skill_type"],
        title="Skills filters",
    )
    filtered = apply_filters(df_skills, filters)
    if filtered.empty:
        st.warning("No rows remain after filtering. Try widening the category or level scope.")
        return

    skill_type = filters.get("skill_type", "all")
    list_column = {
        "all": "skills_all_clean_list",
        "hard": "hard_skills_clean_list",
        "soft": "soft_skills_clean_list",
        "tech_stack": "tech_stack_clean_list",
    }[skill_type]
    exploded = explode_skills(filtered, list_column=list_column)
    min_vacancies = filters.get("min_vacancies", 10)

    if exploded.empty:
        st.warning("The selected slice does not contain usable skill arrays.")
        return

    skill_stats = (
        exploded.groupby("skill")
        .agg(
            demand=("id", "count"),
            vacancy_count=("id", "nunique"),
            median_salary=("salary_avg_analytics", "median"),
        )
        .reset_index()
    )
    skill_stats["skill_family"] = skill_stats["skill"].apply(_skill_family)
    bubble_data = skill_stats[skill_stats["demand"] >= min_vacancies].copy()

    top_skill = skill_stats.sort_values("demand", ascending=False).head(1)
    render_metric_cards(
        [
            {"icon": "📚", "label": "Skill vacancies", "value": f"{len(filtered):,}", "delta": "Rows marked usable for skill analytics", "color": "accent_blue"},
            {"icon": "🧠", "label": "Unique skills", "value": f"{skill_stats['skill'].nunique():,}", "delta": f"{skill_type} skill space", "color": "accent_cyan"},
            {"icon": "💡", "label": "Bubble chart skills", "value": f"{len(bubble_data):,}", "delta": f"Demand threshold ≥ {min_vacancies}", "color": "accent_green"},
            {"icon": "🔥", "label": "Top skill", "value": top_skill['skill'].iloc[0] if not top_skill.empty else "n/a", "delta": f"{int(top_skill['demand'].iloc[0]) if not top_skill.empty else 0} mentions", "color": "accent_orange"},
        ]
    )

    if bubble_data.empty:
        st.plotly_chart(empty_figure("No skills meet the current minimum vacancy threshold."), use_container_width=True)
    else:
        fig = px.scatter(
            bubble_data,
            x="demand",
            y="median_salary",
            size="vacancy_count",
            color="skill_family",
            text=bubble_data["skill"].where(bubble_data["demand"].rank(method="first", ascending=False) <= 20, ""),
            hover_name="skill",
            color_discrete_sequence=COLORS["gradient_main"],
        )
        fig.update_traces(textposition="top center")
        st.plotly_chart(
            apply_figure_style(fig, title="Skill ROI map: demand × salary × vacancy count", height=520, legend_title="Skill family"),
            use_container_width=True,
        )

    top_30 = skill_stats.sort_values("demand").tail(30)
    st.plotly_chart(
        horizontal_bar(
            top_30,
            x="demand",
            y="skill",
            color="skill_family",
            title="Top 30 skills by demand",
            color_scale=COLORS["gradient_main"],
        ),
        use_container_width=True,
    )

    top_15_skills = skill_stats.sort_values("demand", ascending=False).head(15)["skill"].tolist()
    co_matrix = _co_occurrence_matrix(filtered[list_column], top_15_skills)
    st.plotly_chart(
        heatmap_chart(co_matrix, title="Skill co-occurrence heatmap", colorbar_title="Co-mentions"),
        use_container_width=True,
    )

    selectable_skills = skill_stats.sort_values("demand", ascending=False)["skill"].tolist()
    selected_skill = st.selectbox("Inspect level requirements for a skill", options=selectable_skills[:150], index=0)
    skill_level = exploded[exploded["skill"] == selected_skill].groupby("level_filled")["id"].nunique().reset_index(name="vacancies")
    if skill_level.empty:
        st.plotly_chart(empty_figure("No level split is available for this skill."), use_container_width=True)
    else:
        fig = px.bar(
            skill_level,
            x="level_filled",
            y="vacancies",
            color="vacancies",
            color_continuous_scale="Viridis",
            text="vacancies",
        )
        st.plotly_chart(apply_figure_style(fig, title=f"Level requirements for {selected_skill}"), use_container_width=True)

    soft_exploded = explode_skills(filtered, list_column="soft_skills_clean_list")
    soft_freq = soft_exploded["skill"].value_counts().head(24)
    st.plotly_chart(
        bubble_cloud(soft_freq, title="Soft skills emphasis cloud", color=COLORS["accent_violet"]),
        use_container_width=True,
    )

    category_options = sorted(filtered["category_filled"].replace("", pd.NA).dropna().unique().tolist())
    selected_category = st.selectbox("Tech stack by category", options=category_options or ["No category"], index=0)
    tech_slice = filtered[filtered["category_filled"] == selected_category] if selected_category != "No category" else filtered.iloc[0:0]
    tech_exploded = explode_skills(tech_slice, list_column="tech_stack_clean_list")
    if tech_exploded.empty:
        st.plotly_chart(empty_figure("No tech-stack rows are available for the selected category."), use_container_width=True)
    else:
        tech_level = (
            tech_exploded.groupby(["skill", "level_filled"])["id"]
            .nunique()
            .reset_index(name="vacancies")
        )
        top_stack = tech_level.groupby("skill")["vacancies"].sum().nlargest(12).index.tolist()
        tech_level = tech_level[tech_level["skill"].isin(top_stack)]
        fig = px.bar(
            tech_level,
            x="vacancies",
            y="skill",
            color="level_filled",
            orientation="h",
            barmode="stack",
            color_discrete_sequence=COLORS["gradient_cool"],
        )
        st.plotly_chart(
            apply_figure_style(fig, title=f"Tech stack demand by level: {selected_category}", legend_title="Level"),
            use_container_width=True,
        )
