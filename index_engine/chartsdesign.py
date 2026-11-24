"""Consistent, accessible Plotly figures for the local dashboard."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .buildindicatorsfromdata import regime

BANDS = [
    (0, 25, "Extreme fear", "#f07e83"),
    (25, 45, "Fear", "#eab187"),
    (45, 55, "Neutral", "#d6ccc5"),
    (55, 75, "Greed", "#a5b8d0"),
    (75, 100, "Extreme greed", "#7990b5"),
]
CHART_FONT = "Inter, Segoe UI, Arial, sans-serif"
DATA_LINE = "#000000"
DARK_PANEL = "#661c2d"


def color(value):
    return next(
        (shade for _, _, label, shade in BANDS if label == regime(value)), "#999999"
    )


def style(fig, height=360):
    fig.update_layout(
        template="plotly_white",
        height=height,
        font=dict(family=CHART_FONT, color="#594c50", size=12),
        margin=dict(l=54, r=20, t=26, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.14, x=0),
        uirevision="stable",
        hoverlabel=dict(bgcolor="#581c2c", font=dict(family=CHART_FONT, color="white")),
        modebar_remove=["lasso2d", "select2d"],
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#ebe3e1", zeroline=False, automargin=True)
    return fig


def gauge(value):
    """Draw a true semicircle with proportional bands and a single needle."""
    fig = go.Figure()
    for lo, hi, label, shade in BANDS:
        angles = np.linspace(np.pi * (1 - lo / 100), np.pi * (1 - hi / 100), 80)
        x = np.r_[np.cos(angles), 0.80 * np.cos(angles[::-1])]
        y = np.r_[np.sin(angles), 0.80 * np.sin(angles[::-1])]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                fill="toself",
                fillcolor=shade,
                line=dict(color=DARK_PANEL, width=2),
                name=label,
                hoveron="fills",
                hovertemplate=f"{label}<extra></extra>",
                showlegend=False,
            )
        )
    for tick in (0, 25, 50, 75, 100):
        angle = np.pi * (1 - tick / 100)
        fig.add_annotation(
            x=0.68 * np.cos(angle),
            y=0.68 * np.sin(angle),
            text=str(tick),
            showarrow=False,
            font=dict(size=11, color="#efd6d5"),
        )
    if pd.notna(value):
        angle = np.pi * (1 - np.clip(value, 0, 100) / 100)
        tip = np.array([0.73 * np.cos(angle), 0.73 * np.sin(angle)])
        side = np.array([-0.024 * np.sin(angle), 0.024 * np.cos(angle)])
        fig.add_trace(
            go.Scatter(
                x=[side[0], tip[0], -side[0]],
                y=[side[1], tip[1], -side[1]],
                mode="lines",
                fill="toself",
                fillcolor="#fff6ed",
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[0],
                y=[0],
                mode="markers",
                marker=dict(size=10, color="#fff6ed"),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    if pd.isna(value):
        fig.add_annotation(x=0, y=0, text="—", showarrow=False)
    for x, label in [(-0.89, "Fear"), (0.89, "Greed")]:
        fig.add_annotation(x=x, y=-0.18, text=label, showarrow=False,
                           font=dict(size=12, color="#f4ded9"))
    fig.update_layout(
        height=168,
        margin=dict(l=4, r=4, t=4, b=2),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=CHART_FONT, color="white"),
        xaxis=dict(range=[-1.14, 1.14], visible=False, fixedrange=True),
        yaxis=dict(
            range=[-0.31, 1.06],
            visible=False,
            scaleanchor="x",
            scaleratio=1,
            fixedrange=True,
        ),
        hovermode=False,
    )
    return fig


def recent_trend(history):
    end = history.index[-1]
    dates = history.loc[end - pd.DateOffset(months=3):end, "index"]
    fig = go.Figure(go.Scatter(x=dates.index, y=dates, mode="lines",
                               line=dict(color=DATA_LINE, width=2), fill="tozeroy",
                               fillcolor="rgba(255,181,173,0.14)", connectgaps=False,
                               hovertemplate="%{x|%b %d, %Y} · %{y:.1f} / 100<extra></extra>"))
    fig.update_layout(height=46, margin=dict(l=2, r=4, t=4, b=2),
                      xaxis=dict(visible=False, fixedrange=True),
                      yaxis=dict(visible=False, fixedrange=True, range=[0, 100]),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      showlegend=False, hovermode="x")
    return fig


def history_chart(history, start=None, end=None):
    frame = history.loc[start:end]
    fig = go.Figure()
    for lo, hi, _, shade in BANDS:
        fig.add_hrect(
            y0=lo, y1=hi, fillcolor=shade, opacity=0.13, line_width=0, layer="below"
        )
    fig.add_trace(
        go.Scatter(
            x=frame.index,
            y=frame["index"],
            name="Fear & Greed",
            mode="lines",
            connectgaps=False,
            line=dict(color=DATA_LINE, width=2.3),
            customdata=frame[["active_components", "volatility_source"]],
            hovertemplate="%{y:.1f} / 100<br>%{customdata[0]} components<br>%{customdata[1]}<extra></extra>",
        )
    )
    fig.update_yaxes(range=[0, 100], tickvals=[0, 25, 50, 75, 100])
    fig.update_xaxes(
        range=[frame.index.min(), frame.index.max()] if len(frame) else None
    )
    return style(fig, 390)


def signal_chart(result, component, days=252):
    fig = go.Figure()
    if component == "momentum":
        s = result.inputs.tsx_price
        fig.add_trace(
            go.Scatter(
                x=s.index[-days:],
                y=s.iloc[-days:],
                name="TSX Composite",
                line=dict(color=DATA_LINE, width=2),
            )
        )
        avg = s.shift(1).rolling(125).mean()
        fig.add_trace(
            go.Scatter(
                x=avg.index[-days:],
                y=avg.iloc[-days:],
                name="Prior 125-session average",
                line=dict(color=DATA_LINE, width=1.6, dash="dash"),
            )
        )
    else:
        s = result.signals[component].iloc[-days:]
        fig.add_trace(
            go.Scatter(
                x=s.index,
                y=s,
                name="Raw indicator",
                line=dict(color=DATA_LINE, width=2),
                connectgaps=False,
            )
        )
        if component == "breadth":
            fig.update_yaxes(tickformat=".2%")
            fig.update_traces(hovertemplate="%{y:.2%}<extra>Market breadth</extra>")
        if component == "safe_haven":
            fig.update_yaxes(tickformat=".0%")
    return style(fig, 230)


def weights_chart(weights):
    from .buildindicatorsfromdata import COMPONENTS

    fig = go.Figure()
    colors = [
        "#76283d",
        "#c56068",
        "#647998",
        "#d0a26d",
        "#a06986",
        "#586173",
        "#db9985",
    ]
    for (key, (label, _, _)), shade in zip(COMPONENTS.items(), colors):
        fig.add_trace(
            go.Scatter(
                x=weights.index,
                y=weights[key] * 100,
                name=label,
                stackgroup="weights",
                mode="lines",
                line=dict(width=0, color=shade),
                hovertemplate="%{y:.2f}%<extra>%{fullData.name}</extra>",
            )
        )
    fig.update_yaxes(range=[0, 100], ticksuffix="%")
    return style(fig, 330)
