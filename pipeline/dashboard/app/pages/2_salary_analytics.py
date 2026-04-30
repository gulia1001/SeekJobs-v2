from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.components.cards import page_header, render_metric_cards
from app.components.charts import apply_figure_style, empty_figure, heatmap_chart
from app.components.filters import apply_filters, render_sidebar_filters
from app.config import COLORS, LEVEL_ORDER
from app.data.loader import compute_salary_coverage


def render(bundle: dict[str, object]) -> None:
    df_base = bundle["base"]
    df_base_structured = bundle["base_structured"]
    df_salary = bundle["salary"]

    page_header(
        "💰 Salary Analytics",
        "Salary benchmarking across categories, levels, cities, English demand, and remote-work policies. This page uses structured salary sources only: `hh_kz`, `kaspi_jobs`, and `kolesa_jobs`.",
    )

    filters = render_sidebar_filters(
        df_base_structured,
        prefix="salary",
        include=["city", "category", "level", "work_format", "source", "quality_tier", "english_required"],
        title="Salary filters",
    )
    base_filtered = apply_filters(df_base_structured, filters)
    salary_filtered = apply_filters(df_salary, filters)

    coverage = compute_salary_coverage(len(base_filtered), len(salary_filtered))
    if base_filtered.empty:
        st.warning("No vacancies match the current filters.")
        return

    if len(salary_filtered) < 30:
        st.warning(
            f"Salary sample is small ({len(salary_filtered)} rows). Treat medians and premiums as directional rather than definitive."
        )

    salary_categories = sorted(
        salary_filtered["category_filled"].replace("", pd.NA).dropna().unique().tolist()
    )
    selected_category = st.selectbox(
        "Focus category for level distribution",
        options=salary_categories or ["No category available"],
        index=0,
    )

    market_median = salary_filtered["salary_avg_clean"].median()
    render_metric_cards(
        [
            {"icon": "📦", "label": "Salary rows", "value": f"{len(salary_filtered):,}", "delta": f"{coverage:.1f}% of filtered market", "color": "accent_blue"},
            {"icon": "💵", "label": "Median salary", "value": f"{market_median:,.0f} ₸" if pd.notna(market_median) else "n/a", "delta": "Filtered market median", "color": "accent_green"},
            {"icon": "🌍", "label": "Currencies", "value": f"{salary_filtered['currency_clean'].replace('', pd.NA).dropna().nunique():,}", "delta": "Currency variants in slice", "color": "accent_violet"},
            {"icon": "🧪", "label": "Salary coverage", "value": f"{coverage:.1f}%", "delta": "Always shown for context", "color": "accent_orange"},
        ]
    )

    if selected_category != "No category available":
        category_slice = salary_filtered[salary_filtered["category_filled"] == selected_category]
        if category_slice.empty:
            st.plotly_chart(empty_figure("No salary rows for the selected category."), use_container_width=True)
        else:
            fig = px.box(
                category_slice,
                x="level_filled",
                y="salary_avg_clean",
                color="city_norm",
                points="all",
                category_orders={"level_filled": LEVEL_ORDER},
                color_discrete_sequence=COLORS["gradient_main"],
            )
            st.plotly_chart(
                apply_figure_style(fig, title=f"Salary distribution inside {selected_category}", legend_title="City"),
                use_container_width=True,
            )

    violin_data = salary_filtered[salary_filtered["city_norm"].isin(["almaty", "astana"])]
    if violin_data.empty:
        st.plotly_chart(empty_figure("No Almaty vs Astana salary comparison is available."), use_container_width=True)
    else:
        fig = px.violin(
            violin_data,
            x="city_norm",
            y="salary_avg_clean",
            color="city_norm",
            box=True,
            points="all",
            color_discrete_sequence=[COLORS["accent_blue"], COLORS["accent_violet"]],
        )
        st.plotly_chart(apply_figure_style(fig, title="Almaty vs Astana salary distribution"), use_container_width=True)

    category_stats = (
        salary_filtered[salary_filtered["category_filled"] != ""]
        .groupby("category_filled")["salary_avg_clean"]
        .agg(median="median", q25=lambda x: x.quantile(0.25), q75=lambda x: x.quantile(0.75), vacancies="count")
        .dropna()
        .sort_values("median", ascending=True)
    )
    if category_stats.empty:
        st.plotly_chart(empty_figure("Not enough category salary data."), use_container_width=True)
    else:
        category_stats = category_stats.assign(
            diff_vs_market=category_stats["median"] - market_median,
            error_plus=category_stats["q75"] - category_stats["median"],
            error_minus=category_stats["median"] - category_stats["q25"],
        )
        bar_colors = [COLORS["accent_green"] if value >= 0 else COLORS["accent_red"] for value in category_stats["diff_vs_market"]]
        fig = go.Figure(
            go.Bar(
                x=category_stats["median"],
                y=category_stats.index,
                orientation="h",
                marker_color=bar_colors,
                error_x=dict(array=category_stats["error_plus"], arrayminus=category_stats["error_minus"]),
                customdata=category_stats[["vacancies"]],
                hovertemplate="%{y}<br>Median: %{x:,.0f} ₸<br>Vacancies: %{customdata[0]}<extra></extra>",
            )
        )
        st.plotly_chart(apply_figure_style(fig, title="Median salary by category with IQR"), use_container_width=True)

    level_category = (
        salary_filtered[salary_filtered["category_filled"] != ""]
        .groupby(["level_filled", "category_filled"])["salary_avg_clean"]
        .median()
        .unstack()
    )
    st.plotly_chart(
        heatmap_chart(
            level_category.fillna(0) if not level_category.empty else level_category,
            title="Salary heatmap: level × category",
            colorbar_title="Median ₸",
        ),
        use_container_width=True,
    )

    def _premium_frame(flag_column: str, positive_label: str, negative_label: str) -> pd.DataFrame:
        if salary_filtered.empty:
            return pd.DataFrame(columns=["category_filled", "premium_pct"])
        yes = salary_filtered[salary_filtered[flag_column]].groupby("category_filled")["salary_avg_clean"].median()
        no = salary_filtered[~salary_filtered[flag_column]].groupby("category_filled")["salary_avg_clean"].median()
        joined = pd.concat([yes.rename(positive_label), no.rename(negative_label)], axis=1).dropna()
        joined = joined[joined[negative_label] > 0]
        joined["premium_pct"] = ((joined[positive_label] - joined[negative_label]) / joined[negative_label] * 100).round(1)
        return joined.reset_index().sort_values("premium_pct")

    english_premium = _premium_frame("english_required", "with_english", "without_english")
    if english_premium.empty:
        st.plotly_chart(empty_figure("Not enough data for English premium analysis."), use_container_width=True)
    else:
        fig = px.bar(
            english_premium,
            x="premium_pct",
            y="category_filled",
            orientation="h",
            color="premium_pct",
            color_continuous_scale="Viridis",
            text="premium_pct",
        )
        fig.update_traces(texttemplate="%{text:.1f}%")
        st.plotly_chart(apply_figure_style(fig, title="English premium by category"), use_container_width=True)

    remote_office = salary_filtered[salary_filtered["work_format_norm"].astype(str).isin(["remote", "office"])].copy()
    remote_yes = remote_office[remote_office["work_format_norm"].astype(str) == "remote"].groupby("category_filled")["salary_avg_clean"].median()
    office_no = remote_office[remote_office["work_format_norm"].astype(str) == "office"].groupby("category_filled")["salary_avg_clean"].median()
    remote_premium = pd.concat([remote_yes.rename("remote"), office_no.rename("office")], axis=1).dropna()
    remote_premium = remote_premium[remote_premium["office"] > 0]
    if remote_premium.empty:
        st.plotly_chart(empty_figure("Not enough data for remote premium analysis."), use_container_width=True)
    else:
        remote_premium["premium_pct"] = ((remote_premium["remote"] - remote_premium["office"]) / remote_premium["office"] * 100).round(1)
        remote_premium = remote_premium.reset_index().sort_values("premium_pct")
        fig = px.bar(
            remote_premium,
            x="premium_pct",
            y="category_filled",
            orientation="h",
            color="premium_pct",
            color_continuous_scale="RdBu",
            text="premium_pct",
        )
        fig.update_traces(texttemplate="%{text:.1f}%")
        st.plotly_chart(apply_figure_style(fig, title="Remote premium vs office by category"), use_container_width=True)

    benchmark = (
        salary_filtered.groupby(["category_filled", "level_filled"])["salary_avg_clean"]
        .agg(vacancies="count", median_salary="median", q25=lambda x: x.quantile(0.25), q75=lambda x: x.quantile(0.75))
        .reset_index()
        .sort_values(["category_filled", "median_salary"], ascending=[True, False])
    )
    benchmark["salary_coverage_pct"] = coverage
    st.subheader("Salary benchmark table")
    st.dataframe(
        benchmark.rename(
            columns={
                "category_filled": "category",
                "level_filled": "level",
                "vacancies": "vacancies",
                "median_salary": "median_salary_kzt",
                "q25": "iqr_25",
                "q75": "iqr_75",
                "salary_coverage_pct": "salary_coverage_pct",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
