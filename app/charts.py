"""Figures and the transforms behind them, kept free of Streamlit.

Separated so the charts can be rendered and inspected on their own -- a chart is
read by people, and the only way to know it reads well is to look at it, which
is hard to do through a running app.

Colors come from the project's validated palette. Identity is violet + orange:
that pair separates by OKLab dE 29.5 under simulated protanopia and deuteranopia,
against 9.1 for the blue + orange it replaced (floor is 8). Blue and red survive
only as the DIVERGING pair -- drier against wetter, below trend against above --
where hue carries polarity, not the identity of a series. Chrome (grid, axes,
tick labels) stays recessive so the marks are what is seen.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

VIOLET, ORANGE, AQUA, RED, BLUE = "#4a3aa7", "#eb6834", "#1baf7a", "#e34948", "#2a78d6"
INK, INK_SOFT, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE_RULE, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

FONT = "system-ui, -apple-system, Segoe UI, sans-serif"

CROP_LABEL = {"SOJA": "Soybean", "MILHO 2A SAFRA": "Safrinha corn"}

# Both thresholds live here alone. The page states them in prose, the severity
# bands are cut on them and the failure rings are filtered by them; written down
# three times, they diverge the first time someone edits one of the three.
FLAG_PCT = -10          # at or below this the model is calling a crop failure
FAIL_PCT = -20          # at or below this the failure is a severe one

SEVERITY_BINS = [-1000, FAIL_PCT, FLAG_PCT, -FLAG_PCT, -FAIL_PCT, 1000]
SEVERITY_ORDER = [
    f"Failure < {FAIL_PCT}%",
    f"{FAIL_PCT}% to {FLAG_PCT}%",
    f"Normal ±{abs(FLAG_PCT)}%",
    f"+{abs(FLAG_PCT)}% to +{abs(FAIL_PCT)}%",
    f"Good > +{abs(FAIL_PCT)}%",
]

STATE_NAME = {"BA": "Bahia", "GO": "Goiás", "MG": "Minas Gerais",
              "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PR": "Paraná",
              "RS": "Rio Grande do Sul"}


# ------------------------------------------------------------------ transforms

def widen(backtest: pd.DataFrame) -> pd.DataFrame:
    """One row per crop x state x season, baseline and model side by side."""
    wide = backtest.pivot_table(
        index=["crop_name", "state_code", "harvest_year", "actual_pct",
               "trend_kg_ha", "yield_kg_ha"],
        columns="role",
        values="predicted_pct",
    ).reset_index()
    wide["severity"] = pd.cut(wide["actual_pct"], SEVERITY_BINS, labels=SEVERITY_ORDER)
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


def anomaly_series(season_risk: pd.DataFrame, crop: str, state: str) -> pd.Series:
    """Dry-day anomaly for one crop and state, indexed by season."""
    subset = season_risk[(season_risk["crop_name"] == crop)
                         & (season_risk["state_code"] == state)]
    return subset.set_index("harvest_year")["dry_days_anomaly_z"].sort_index()


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
    "Soybean = violet" while half the soybean bars were red, so hue was carrying
    identity and polarity at once and neither read cleanly. Sign is already in
    the geometry -- which side of zero the bar sits on -- so hue is free to do
    the one job a legend can explain. The wash to the left of zero says which
    side is which without asking anyone to read the axis.
    """
    fig = go.Figure()
    fig.add_vrect(x0=-100, x1=0, fillcolor=RED, opacity=0.05, line_width=0, layer="below")
    for crop, color, offset in [("Soybean", VIOLET, -0.19), ("Safrinha corn", ORANGE, 0.19)]:
        part = gains[gains["crop"] == crop].set_index("severity").reindex(SEVERITY_ORDER)
        fig.add_bar(
            y=[SEVERITY_ORDER.index(s) + offset for s in part.index],
            x=part["gain"], orientation="h", name=crop,
            marker=dict(color=color, line=dict(width=0), cornerradius=4),
            width=0.3,
            text=[f"{v:+.0f}%" for v in part["gain"]],
            textposition="outside",
            # Ink, not the series color: a value in violet on a violet bar reads
            # as decoration, and identity is already carried by the mark itself.
            textfont=dict(color=INK_SOFT, size=12),
            cliponaxis=False,
            customdata=list(zip(part.index, part["n"])),
            hovertemplate=f"<b>{crop}</b><br>%{{customdata[0]}}<br>"
                          "Error removed: %{x:.0f}%<br>n = %{customdata[1]}<extra></extra>",
        )
    fig.update_yaxes(tickmode="array", tickvals=list(range(len(SEVERITY_ORDER))),
                     ticktext=SEVERITY_ORDER, autorange="reversed")
    _value_axis(fig)
    # Range from the data with headroom. A typed limit clips the longest bar and
    # still renders -- quietly understating the very case the chart is about.
    span = max(gains["gain"].abs()) * 1.15
    fig.update_xaxes(range=[-span, span * 0.62])
    fig = _style(fig, height)
    fig.update_layout(showlegend=True, bargap=0.1)
    return fig


def exposure_chart(exposure: pd.Series, height: int = 320) -> go.Figure:
    """Columns, one per state, ordered by how exposed the state is.

    One series, one color -- bar length already encodes the magnitude, so the
    strongest state is emphasised by opacity rather than by a second hue.

    The axis keeps zero as a floor, because these bars are read against zero,
    but the ceiling stretches to fit the data instead of stopping at a number
    typed once. A fixed ceiling clips a bar that outgrows it, and the chart
    still renders -- it just quietly understates the very state it is meant to
    single out.
    """
    strongest = exposure.index[-1]
    fig = go.Figure(go.Bar(
        x=list(exposure.index), y=exposure.values,
        marker=dict(color=VIOLET, line=dict(width=0), cornerradius=4,
                    opacity=[1.0 if s == strongest else 0.42 for s in exposure.index]),
        # Thin: a column is capped, never filling its slot -- the leftover band
        # is air, and at 7 states a 0.32 width gave 90px slabs.
        width=0.16,
        text=[f"{v:.2f}" for v in exposure.values],
        textposition="outside",
        textfont=dict(color=MUTED, size=13),
        hovertemplate="<b>%{x}</b><br>Correlation: %{y:.2f}<extra></extra>",
    ))
    high = max(0.6, float(exposure.max()) * 1.22)
    fig.update_yaxes(range=[0, high], dtick=0.2)
    fig.update_xaxes(tickfont=dict(color=INK_SOFT, size=13))
    return _style(fig, height)


def season_chart(series: pd.DataFrame, anomaly: pd.Series | None = None,
                 height: int = 470) -> go.Figure:
    """Actual yield against its own trend, with the model's failure calls ringed.

    The trend is reference, not a competing series, so it wears muted ink while
    the actual yield takes the identity hue.

    When the dry-day anomaly is supplied it goes in a second panel below, on the
    same time axis: the input the model reads and the outcome it is judged on,
    read together. Two panels, each with its own scale -- deliberately not a
    second y-axis on one plot, which invites a comparison the units do not
    support and hides which line the reader is meant to believe.
    """
    rows = 2 if anomaly is not None else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        row_heights=[0.72, 0.28] if rows == 2 else [1.0],
                        vertical_spacing=0.14)

    fig.add_scatter(
        x=series["harvest_year"], y=series["trend_kg_ha"], name="Trend (baseline)",
        mode="lines", line=dict(color=MUTED, width=2),
        hovertemplate="%{x}<br>Trend: %{y:,.0f} kg/ha<extra></extra>",
        row=1, col=1,
    )
    fig.add_scatter(
        x=series["harvest_year"], y=series["yield_kg_ha"], name="Actual yield",
        mode="lines+markers", line=dict(color=VIOLET, width=2),
        marker=dict(size=8, line=dict(color=SURFACE, width=2)),
        hovertemplate="%{x}<br>Actual: %{y:,.0f} kg/ha<extra></extra>",
        row=1, col=1,
    )
    flagged = series[series["model"] <= FLAG_PCT]
    if not flagged.empty:
        fig.add_scatter(
            x=flagged["harvest_year"], y=flagged["yield_kg_ha"],
            name="Model flagged a failure", mode="markers",
            marker=dict(size=16, color="rgba(0,0,0,0)",
                        line=dict(color=ORANGE, width=2.5)),
            customdata=flagged["model"],
            hovertemplate="%{x}<br>Flagged: %{customdata:.0f}% below trend<extra></extra>",
            row=1, col=1,
        )

    if anomaly is not None:
        window = anomaly.reindex(series["harvest_year"]).dropna()
        fig.add_bar(
            x=window.index, y=window.values, name="Dry-day anomaly",
            marker=dict(color=[RED if v > 0 else BLUE for v in window.values],
                        line=dict(width=0), cornerradius=3),
            width=0.55, showlegend=False,
            hovertemplate="%{x}<br>Dry-day anomaly: %{y:+.1f} sd<extra></extra>",
            row=2, col=1,
        )
        fig.update_yaxes(title_text="drier →", title_font=dict(size=11, color=MUTED),
                         zeroline=True, zerolinecolor=BASELINE_RULE, zerolinewidth=1,
                         row=2, col=1)

    fig.update_xaxes(dtick=5)
    fig.update_yaxes(ticksuffix="", separatethousands=True, title_text="kg/ha",
                     title_font=dict(size=11, color=MUTED), row=1, col=1)
    fig = _style(fig, height)
    fig.update_layout(showlegend=True, hovermode="x unified", bargap=0.35,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                                  title=None))
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=BASELINE_RULE,
                     tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, linecolor=BASELINE_RULE,
                     tickfont=dict(color=MUTED))
    return fig


def forecast_chart(live: pd.DataFrame, height: int | None = None) -> go.Figure:
    """Diverging again, and here the poles mean loss and gain against trend.

    Height grows with the number of rows instead of squeezing them: the page
    puts this in a fixed-height scrolling container, so a long list scrolls
    rather than flattening into unreadable slivers.
    """
    height = height or max(220, 34 * len(live) + 60)
    fig = go.Figure(go.Bar(
        x=live["desvio_previsto_pct"], y=live["label"], orientation="h",
        marker=dict(color=[RED if v < FLAG_PCT / 2 else "#ef8b8a"
                           for v in live["desvio_previsto_pct"]],
                    line=dict(width=0), cornerradius=4),
        width=0.5,
        text=[f"{v:.1f}%" for v in live["desvio_previsto_pct"]],
        textposition="outside",
        textfont=dict(color=INK, size=13),
        customdata=list(zip(live["previsao_kg_ha"], live["estimativa_conab_kg_ha"])),
        hovertemplate="<b>%{y}</b><br>Forecast: %{x:.1f}% vs trend<br>"
                      "%{customdata[0]:,.0f} kg/ha "
                      "(CONAB estimate %{customdata[1]:,.0f})<extra></extra>",
    ))
    _value_axis(fig)
    span = float(live["desvio_previsto_pct"].abs().max()) * 1.35
    fig.update_xaxes(range=[-span, span * 0.18])
    return _style(fig, height)
