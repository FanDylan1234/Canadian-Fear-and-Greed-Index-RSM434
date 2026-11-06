"""Consistent, accessible Plotly figures for the local dashboard."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from .model import regime

BANDS = [(0, 25, "Extreme fear", "#dd7965"), (25, 45, "Fear", "#ecc898"),
         (45, 55, "Neutral", "#dedede"), (55, 75, "Greed", "#acd3be"), (75, 100, "Extreme greed", "#5cae90")]


def color(value):
    return next((shade for _, _, label, shade in BANDS if label == regime(value)), "#999999")


def style(fig, height=360):
    fig.update_layout(template="plotly_white", height=height, font=dict(family="Arial, sans-serif", color="#202124", size=12),
                      margin=dict(l=42, r=24, t=25, b=35), paper_bgcolor="white", plot_bgcolor="white",
                      hovermode="x unified", legend=dict(orientation="h", y=1.14, x=0),
                      uirevision="stable", modebar_remove=["lasso2d", "select2d"])
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#eeeeee", zeroline=False)
    return fig


def gauge(value):
    fig = go.Figure()
    for lo, hi, label, shade in BANDS:
        angles = np.linspace(np.pi*(1-lo/100), np.pi*(1-hi/100), 90)
        fig.add_trace(go.Scatter(x=np.cos(angles), y=np.sin(angles), mode="lines", line=dict(color=shade, width=40),
                                 hoverinfo="skip", showlegend=False))
        mid = np.pi*(1-(lo+hi)/200)
        fig.add_annotation(x=1.27*np.cos(mid), y=1.27*np.sin(mid), text=label.replace(" ", "<br>"),
                           showarrow=False, font=dict(size=11, color="#555"))
    for v in (0, 25, 50, 75, 100):
        angle = np.pi*(1-v/100)
        fig.add_annotation(x=.78*np.cos(angle), y=.78*np.sin(angle), text=str(v), showarrow=False, font=dict(size=12, color="#666"))
    if pd.notna(value):
        angle = np.pi*(1-value/100)
        fig.add_trace(go.Scatter(x=[0, .69*np.cos(angle)], y=[0, .69*np.sin(angle)], mode="lines", line=dict(color="#202124", width=5), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", marker=dict(size=15, color="#202124"), hoverinfo="skip", showlegend=False))
    fig.add_annotation(x=0, y=-.27, text=f"<b>{value:.0f}</b>" if pd.notna(value) else "—", showarrow=False, font=dict(size=54))
    fig.add_annotation(x=0, y=-.55, text=regime(value).upper(), showarrow=False, font=dict(size=14))
    fig.update_layout(height=355, margin=dict(l=12, r=12, t=25, b=5), paper_bgcolor="white", plot_bgcolor="white",
                      xaxis=dict(range=[-1.5, 1.5], visible=False, fixedrange=True),
                      yaxis=dict(range=[-.68, 1.5], visible=False, scaleanchor="x", fixedrange=True), hovermode=False)
    return fig


def history_chart(history, start=None, end=None):
    frame = history.loc[start:end]
    fig = go.Figure()
    for lo, hi, _, shade in BANDS:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=shade, opacity=.13, line_width=0, layer="below")
    fig.add_trace(go.Scatter(x=frame.index, y=frame["index"], name="Fear & Greed", mode="lines", connectgaps=False,
                            line=dict(color="#202124", width=2), customdata=frame[["active_components", "volatility_source"]],
                            hovertemplate="%{y:.1f} / 100<br>%{customdata[0]} components<br>%{customdata[1]}<extra></extra>"))
    fig.update_yaxes(range=[0, 100], tickvals=[0, 25, 50, 75, 100])
    fig.update_xaxes(range=[frame.index.min(), frame.index.max()] if len(frame) else None)
    return style(fig, 390)


def signal_chart(result, component, days=252):
    fig = go.Figure()
    if component == "momentum":
        s = result.inputs.tsx_price
        fig.add_trace(go.Scatter(x=s.index[-days:], y=s.iloc[-days:], name="TSX Composite", line=dict(color="#202124", width=2)))
        avg = s.shift(1).rolling(125).mean()
        fig.add_trace(go.Scatter(x=avg.index[-days:], y=avg.iloc[-days:], name="Prior 125-session average", line=dict(color="#d2a24b", width=2)))
    else:
        s = result.signals[component].iloc[-days:]
        fig.add_trace(go.Scatter(x=s.index, y=s, name="Raw indicator", line=dict(color="#283b43", width=2), connectgaps=False))
        if component == "safe_haven":
            fig.update_yaxes(tickformat=".0%")
    return style(fig, 230)


def weights_chart(weights):
    from .model import COMPONENTS
    fig = go.Figure()
    colors = ["#293d46", "#547e88", "#84a8ad", "#d9ac63", "#b87565", "#729c79", "#b6bb83"]
    for (key, (label, _, _)), shade in zip(COMPONENTS.items(), colors):
        fig.add_trace(go.Scatter(x=weights.index, y=weights[key]*100, name=label, stackgroup="weights", mode="lines",
                                line=dict(width=0, color=shade), hovertemplate="%{y:.2f}%<extra>%{fullData.name}</extra>"))
    fig.update_yaxes(range=[0, 100], ticksuffix="%")
    return style(fig, 330)
