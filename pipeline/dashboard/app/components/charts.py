from __future__ import annotations

from math import ceil, sqrt
from typing import Iterable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from app.config import COLORS


def apply_figure_style(
    fig: go.Figure,
    *,
    title: str = "",
    height: int = 420,
    legend_title: str | None = None,
) -> go.Figure:
    fig.update_layout(
        title=title,
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": COLORS["text_primary"], "family": "Inter, sans-serif"},
        title_font={"size": 18, "color": COLORS["text_primary"]},
        legend=dict(
            bgcolor="rgba(17,24,39,0.6)",
            bordercolor="rgba(255,255,255,0.05)",
            borderwidth=1,
            title=legend_title,
        ),
        margin=dict(l=20, r=20, t=60, b=20),
        hoverlabel=dict(
            bgcolor=COLORS["bg_card"],
            bordercolor="rgba(59,130,246,0.35)",
            font_color=COLORS["text_primary"],
        ),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)", zeroline=False)
    return fig


def empty_figure(message: str, *, height: int = 340) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 16, "color": COLORS["text_secondary"]},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return apply_figure_style(fig, height=height)


def donut_chart(
    frame: pd.DataFrame,
    *,
    names: str,
    values: str,
    title: str,
    colors: Iterable[str] | None = None,
) -> go.Figure:
    if frame.empty:
        return empty_figure("Not enough data for this chart.")
    fig = px.pie(frame, names=names, values=values, hole=0.62, color_discrete_sequence=list(colors or COLORS["gradient_main"]))
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return apply_figure_style(fig, title=title, height=400)


def horizontal_bar(
    frame: pd.DataFrame,
    *,
    x: str,
    y: str,
    title: str,
    color: str | None = None,
    barmode: str = "relative",
    text: str | None = None,
    color_scale: list[str] | None = None,
) -> go.Figure:
    if frame.empty:
        return empty_figure("Not enough data for this chart.")
    fig = px.bar(
        frame,
        x=x,
        y=y,
        orientation="h",
        color=color,
        text=text,
        barmode=barmode,
        color_discrete_sequence=color_scale or COLORS["gradient_main"],
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    return apply_figure_style(fig, title=title)


def heatmap_chart(
    frame: pd.DataFrame,
    *,
    title: str,
    colorbar_title: str,
    zmin: float | None = None,
    zmax: float | None = None,
) -> go.Figure:
    if frame.empty:
        return empty_figure("Not enough data for this heatmap.")
    fig = go.Figure(
        data=go.Heatmap(
            z=frame.values,
            x=list(frame.columns),
            y=list(frame.index),
            colorscale="Viridis",
            zmin=zmin,
            zmax=zmax,
            colorbar=dict(title=colorbar_title),
            hoverongaps=False,
        )
    )
    return apply_figure_style(fig, title=title)


def gauge_chart(value: float, *, title: str, delta_reference: float = 70) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=value,
            delta={"reference": delta_reference, "increasing": {"color": COLORS["accent_green"]}},
            title={"text": title},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": COLORS["accent_blue"]},
                "steps": [
                    {"range": [0, 40], "color": "#1F2937"},
                    {"range": [40, 70], "color": "#374151"},
                    {"range": [70, 100], "color": "#1E3A5F"},
                ],
                "threshold": {"line": {"color": COLORS["accent_green"], "width": 4}, "value": delta_reference},
            },
        )
    )
    return apply_figure_style(fig, height=320)


def bubble_cloud(series: pd.Series, *, title: str, color: str = COLORS["accent_cyan"]) -> go.Figure:
    if series.empty:
        return empty_figure("Not enough data for this chart.")
    values = series.sort_values(ascending=False).head(24)
    points = len(values)
    cols = max(4, ceil(sqrt(points)))
    xs = [idx % cols for idx in range(points)]
    ys = [-(idx // cols) for idx in range(points)]
    sizes = values.values
    fig = go.Figure(
        data=go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=[f"{skill}<br>{count}" for skill, count in values.items()],
            textposition="middle center",
            marker=dict(
                size=[max(24, min(72, count * 2.2)) for count in sizes],
                color=color,
                opacity=0.78,
                line=dict(color="rgba(255,255,255,0.12)", width=1),
            ),
            hovertemplate="%{text}<extra></extra>",
        )
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return apply_figure_style(fig, title=title, height=420)
