"""Figures and the transforms behind them, kept free of Streamlit.

Separated so the charts can be rendered and inspected on their own -- a chart is
read by people, and the only way to know it reads well is to look at it, which
is hard to do through a running app.

Colors come from the project's validated palette: categorical slots carry
identity, blue<->red is the diverging pair for gain against loss, and chrome
(grid, axes, tick labels) stays recessive so the marks are what is seen.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
INK, INK_SOFT, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE_RULE, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

FONT = "system-ui, -apple-system, Segoe UI, sans-serif"

CROP_LABEL = {"SOJA": "Soybean", "MILHO 2A SAFRA": "Safrinha corn"}
SEVERITY_ORDER = [
    "Failure < -20%",
    "-20% to -10%",
    "Normal ±10%",
    "+10% to +20%",
    "Good > +20%",
]


# ------------------------------------------------------------------ transforms

def widen(backtest: pd.DataFrame) -> pd.DataFrame:
    """One row per crop x state x season, baseline and model side by side."""
    wide = backtest.pivot_table(
        index=["crop_name", "state_code", "harvest_year", "actual_pct",
               "trend_kg_ha", "yield_kg_ha"],
        columns="role",
        values="predicted_pct",
    ).reset_index()
    wide["severity"] = pd.cut(
        wide["actual_pct"], [-1000, -20, -10, 10, 20, 1000], labels=SEVERITY_ORDER
    )
    return wide


def rmse(errors: pd.Series) -> float:
    return float((errors**2).mean() ** 0.5)


def severity_gains(wide: pd.DataFrame) -> pd.DataFrame:
    """Error removed against the baseline, split by how far the season fell."""
    rows = []
    for (crop, severity), group in wide.groupby(["crop_name", "severity"], observed=True):
        base = rmse(group["baseline"] - group["actual_pct"])
        model = rmse(group["model"] - group["actual_pct"])
        rows.append({"crop": CROP_LABEL[crop], "severity": severity,
                     "n": len(group), "gain": (1 - model / base) * 100})
    return pd.DataFrame(rows)


def state_exposure(season_risk: pd.DataFrame, crop: str = "SOJA") -> pd.Series:
    """How tightly each state's yield residual tracks its rainfall anomaly.

    The newest season is excluded because its yield is CONAB's open survey
    estimate, not a realised harvest, and it has no business inside a
    correlation over the record. The cutoff is read from the data: written down,
    it would silently freeze this chart at whatever year was current the day it
    was typed, and never take in a season once that season closed.
    """
    latest = season_risk["harvest_year"].max()
    subset = season_risk[(season_risk["crop_name"] == crop)
                         & (season_risk["harvest_year"] < latest)]
    return (
        subset.groupby("state_code")
        .apply(lambda g: g["precipitation_anomaly_z"].corr(g["yield_residual_pct"]),
               include_groups=False)
        .sort_values()
    )


# --------------------------------------------------------------------- styling

def _style(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=16, t=8, b=8),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, color=INK_SOFT, size=13),
        hoverlabel=dict(font_size=13, bgcolor=SURFACE, bordercolor=GRID),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=BASELINE_RULE,
                     tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, zeroline=False, linecolor=BASELINE_RULE,
                     tickfont=dict(color=MUTED))
    return fig


def _value_axis(fig: go.Figure, suffix: str = "%") -> None:
    """Horizontal bars: the value axis carries the grid, the category axis none."""
    fig.update_xaxes(showgrid=True, gridcolor=GRID, ticksuffix=suffix,
                     zeroline=True, zerolinecolor=BASELINE_RULE, zerolinewidth=1)
    fig.update_yaxes(showgrid=False)


# --------------------------------------------------------------------- figures

def severity_chart(gains: pd.DataFrame, height: int = 360) -> go.Figure:
    """Two crops, two categorical hues -- and no diverging scale on top of them.

    Coloring these bars by sign was tried and dropped: the legend then claimed
    "Soybean = blue" while half the soybean bars were red, so hue was carrying
    identity and polarity at once and neither read cleanly. Sign is already in
    the geometry -- which side of zero the bar sits on -- so hue is free to do
    the one job a legend can explain.
    """
    fig = go.Figure()
    for crop, color, offset in [("Soybean", BLUE, -0.19), ("Safrinha corn", ORANGE, 0.19)]:
        part = gains[gains["crop"] == crop].set_index("severity").reindex(SEVERITY_ORDER)
        fig.add_bar(
            y=[SEVERITY_ORDER.index(s) + offset for s in part.index],
            x=part["gain"], orientation="h", name=crop,
            marker=dict(color=color, line=dict(width=0), cornerradius=4),
            width=0.3,
            customdata=list(zip(part.index, part["n"])),
            hovertemplate=f"<b>{crop}</b><br>%{{customdata[0]}}<br>"
                          "Error removed: %{x:.0f}%<br>n = %{customdata[1]}<extra></extra>",
        )
    fig.update_yaxes(tickmode="array", tickvals=list(range(len(SEVERITY_ORDER))),
                     ticktext=SEVERITY_ORDER, autorange="reversed")
    _value_axis(fig)
    fig = _style(fig, height)
    fig.update_layout(showlegend=True, bargap=0.1)
    return fig


def exposure_chart(exposure: pd.Series, height: int = 360) -> go.Figure:
    """One series, one color -- bar length already encodes the magnitude.

    The axis keeps zero as an edge, because these bars are read against zero,
    but it stretches to fit the data instead of stopping at a number typed once.
    A fixed ceiling clips a bar that outgrows it, and the chart still renders --
    it just quietly understates the very state it is meant to single out. The
    floor drops below zero only if a correlation ever turns negative, which
    would otherwise be a bar of length zero and invisible.
    """
    low = min(0.0, float(exposure.min()) * 1.15)
    high = max(0.6, float(exposure.max()) * 1.15)
    fig = go.Figure(go.Bar(
        x=exposure.values, y=exposure.index, orientation="h",
        marker=dict(color=BLUE, line=dict(width=0), cornerradius=4), width=0.45,
        hovertemplate="<b>%{y}</b><br>Correlation: %{x:.2f}<extra></extra>",
    ))
    fig.update_xaxes(showgrid=True, gridcolor=GRID, range=[low, high], ticksuffix="")
    fig.update_yaxes(showgrid=False)
    return _style(fig, height)


def season_chart(series: pd.DataFrame, height: int = 380) -> go.Figure:
    """Actual yield against its own trend, with the model's failure calls ringed.

    The trend is reference, not a competing series, so it wears muted ink while
    the actual yield takes categorical slot 1.
    """
    fig = go.Figure()
    fig.add_scatter(
        x=series["harvest_year"], y=series["trend_kg_ha"], name="Trend (baseline)",
        mode="lines", line=dict(color=MUTED, width=2),
        hovertemplate="%{x}<br>Trend: %{y:,.0f} kg/ha<extra></extra>",
    )
    fig.add_scatter(
        x=series["harvest_year"], y=series["yield_kg_ha"], name="Actual yield",
        mode="lines+markers", line=dict(color=BLUE, width=2),
        marker=dict(size=8, line=dict(color=SURFACE, width=2)),
        hovertemplate="%{x}<br>Actual: %{y:,.0f} kg/ha<extra></extra>",
    )
    flagged = series[series["model"] <= -10]
    if not flagged.empty:
        fig.add_scatter(
            x=flagged["harvest_year"], y=flagged["yield_kg_ha"],
            name="Model flagged a failure", mode="markers",
            marker=dict(size=16, color="rgba(0,0,0,0)",
                        line=dict(color=ORANGE, width=2.5)),
            customdata=flagged["model"],
            hovertemplate="%{x}<br>Flagged: %{customdata:.0f}% below trend<extra></extra>",
        )
    fig.update_xaxes(dtick=5)
    fig.update_yaxes(ticksuffix="", separatethousands=True)
    fig = _style(fig, height)
    fig.update_layout(showlegend=True, hovermode="x unified")
    return fig


def forecast_chart(live: pd.DataFrame, height: int = 300) -> go.Figure:
    """Diverging again, and here the poles mean loss and gain against trend."""
    fig = go.Figure(go.Bar(
        x=live["desvio_previsto_pct"], y=live["label"], orientation="h",
        marker=dict(color=[RED if v < 0 else BLUE for v in live["desvio_previsto_pct"]],
                    line=dict(width=0), cornerradius=4),
        width=0.5,
        customdata=list(zip(live["previsao_kg_ha"], live["estimativa_conab_kg_ha"])),
        hovertemplate="<b>%{y}</b><br>Forecast: %{x:.1f}% vs trend<br>"
                      "%{customdata[0]:,.0f} kg/ha "
                      "(CONAB estimate %{customdata[1]:,.0f})<extra></extra>",
    ))
    _value_axis(fig)
    return _style(fig, height)
