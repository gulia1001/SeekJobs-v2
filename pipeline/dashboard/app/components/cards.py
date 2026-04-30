from __future__ import annotations

from typing import Any, Iterable

import streamlit as st

from app.config import COLORS


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="page-header">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def render_metric_cards(metrics: Iterable[dict[str, Any]]) -> None:
    metrics = list(metrics)
    if not metrics:
        return
    columns = st.columns(len(metrics))
    for column, metric in zip(columns, metrics):
        color = COLORS.get(metric.get("color", ""), metric.get("color", COLORS["accent_blue"]))
        delta = metric.get("delta", "")
        help_text = metric.get("help", "")
        with column:
            st.markdown(
                f"""
                <div class="metric-card" title="{help_text}">
                    <div style="font-size:1.5rem;">{metric.get("icon", "•")}</div>
                    <div class="metric-label">{metric.get("label", "")}</div>
                    <div class="metric-value" style="color:{color};">{metric.get("value", "—")}</div>
                    <div class="metric-delta">{delta}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def insight_card(text: str) -> None:
    st.markdown(f'<div class="insight-card">{text}</div>', unsafe_allow_html=True)


def job_card(
    *,
    title: str,
    company: str,
    salary: str,
    meta: str,
    match_score: float | None = None,
    skills: list[str] | None = None,
    url: str = "",
) -> None:
    skill_markup = "".join(f'<span class="pill">{skill}</span>' for skill in (skills or [])[:8])
    match_text = f" • match {match_score:.0%}" if match_score is not None else ""
    link = f'<a href="{url}" target="_blank">Open source listing</a>' if url else ""
    st.markdown(
        f"""
        <div class="job-card">
            <div class="job-title">{title}</div>
            <div class="job-meta">{company} • {salary}{match_text}</div>
            <div class="job-meta">{meta}</div>
            <div>{skill_markup}</div>
            <div class="small-note" style="margin-top:0.5rem;">{link}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
