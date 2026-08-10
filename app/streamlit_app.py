"""Safra Risk Radar -- the published face of the project.

Reads the CSVs exported by `analysis/export_app_data.py`, so the deployed app
needs no warehouse, no credentials and no scikit-learn: pandas and plotly only.

Leads with what the backtest actually showed. The model does not beat the trend
on average, and saying so up front is the point -- a dashboard that opened with
"93% accurate" would be describing a different, dishonest project.

Every quantity this page states is computed here, never typed. The one time a
date was written into the copy it went stale on the first scheduled refresh, and
the published app spent a week misreporting its own coverage. The same rule
caught a second case: the sample share of ordinary seasons was published as 55%
and the data said 48%.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from charts import (
    CROP_LABEL,
    FAIL_PCT,
    FLAG_PCT,
    SEVERITY_ORDER,
    STATE_NAME,
    anomaly_series,
    exposure_chart,
    forecast_chart,
    rmse,
    season_chart,
    severity_chart,
    severity_gains,
    state_exposure,
    widen,
)

DATA_DIR = Path(__file__).parent / "data"

# Not in any published CSV. `season_risk.grid_cells` is per state and summing it
# double-counts the cells shared between them, so this cannot be derived from
# what the app ships. To stop being typed it has to go into meta.json.
GRID_CELLS = 255

st.set_page_config(page_title="Safra Risk Radar", page_icon="🌾", layout="wide")


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{name}.csv")


@st.cache_data
def load_meta() -> dict[str, str]:
    return json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))


def long_date(value: date) -> str:
    # "%-d" is not portable to Windows and "%d" pads to "05 August"; strip the
    # zero instead of asking the platform for a format it may not have.
    return value.strftime("%d %B %Y").lstrip("0")


def short_date(value: date) -> str:
    return value.strftime("%d %b %Y").lstrip("0")


season_risk = load("season_risk")
backtest = widen(load("backtest"))
forecast = load("forecast")
meta = load_meta()
weather_through = date.fromisoformat(meta["weather_through"])

# ------------------------------------------------------------------- figures
first_season = int(season_risk["harvest_year"].min())
open_season = int(season_risk["harvest_year"].max())   # CONAB's survey, not a harvest
n_states = season_risk["state_code"].nunique()
first_scored = int(backtest["harvest_year"].min())
last_scored = int(backtest["harvest_year"].max())
n_seasons = backtest["harvest_year"].nunique()
# Harvest year 2026 is the 2025/26 season, the way CONAB labels it.
open_season_label = f"{open_season - 1}/{str(open_season)[2:]}"

failures = backtest[backtest["actual_pct"] <= FLAG_PCT]
called = failures[failures["model"] <= FLAG_PCT]
recall_pct = len(called) / len(failures) * 100
n_flags = int((backtest["model"] <= FLAG_PCT).sum())
false_alarm_pct = (1 - len(called) / n_flags) * 100

worst_soy = backtest[(backtest["crop_name"] == "SOJA")
                     & (backtest["severity"] == SEVERITY_ORDER[0])]
soy_gain = (1 - rmse(worst_soy["model"] - worst_soy["actual_pct"])
            / rmse(worst_soy["baseline"] - worst_soy["actual_pct"])) * 100
ordinary_pct = (backtest["severity"] == SEVERITY_ORDER[2]).sum() / len(backtest) * 100

skill = {}
for crop, label in CROP_LABEL.items():
    part = backtest[backtest["crop_name"] == crop]
    skill[label] = (1 - rmse(part["model"] - part["actual_pct"])
                    / rmse(part["baseline"] - part["actual_pct"])) * 100

exposure = state_exposure(season_risk)
expo_ratio = exposure.iloc[-1] / exposure.iloc[0]
expo_first = int(season_risk[season_risk["harvest_year"] < open_season]["harvest_year"].min())
expo_last = int(season_risk[season_risk["harvest_year"] < open_season]["harvest_year"].max())

live = forecast.dropna(subset=["desvio_previsto_pct"]).copy()
live["label"] = live["crop_name"].map(CROP_LABEL) + " · " + live["state_code"]
live = live.sort_values("desvio_previsto_pct", ascending=False)
suppressed = forecast[forecast["desvio_previsto_pct"].isna()]

# ---------------------------------------------------------------------- chrome
st.markdown(
    f"""
    <style>
      .block-container {{ padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1440px; }}
      header[data-testid="stHeader"] {{ background: transparent; }}
      .srr-top {{
        background:#12120f; color:#fff; border-radius:12px;
        padding:14px 22px; margin-bottom:34px;
        display:flex; align-items:center; gap:14px; flex-wrap:wrap;
      }}
      .srr-top .mark {{ font-weight:600; letter-spacing:.12em; font-size:.95rem; }}
      .srr-top .sub {{ color:#8f8e88; font-size:.82rem; }}
      .srr-top .right {{ margin-left:auto; display:flex; gap:26px; align-items:center;
                        color:#c3c2b7; font-size:.82rem; flex-wrap:wrap; }}
      .srr-top .dot {{ color:#0ca30c; font-size:1.1rem; line-height:0; }}
      .srr-top a {{ color:#c3c2b7; text-decoration:none; }}
      .srr-top a:hover {{ color:#fff; }}
      div.srr-eyebrow {{ color:#898781; font-size:.75rem; font-weight:600;
                      letter-spacing:.11em; margin-bottom:.5rem; }}
      p.srr-head {{ font-size:2.1rem; font-weight:700; line-height:1.18;
                   color:#0b0b0b; margin:0 0 .9rem 0; }}
      p.srr-head .fail {{ color:#e34948; }}
      p.srr-lede {{ color:#52514e; font-size:1.02rem; max-width:74rem; margin-bottom:.4rem; }}
      .srr-tile {{ border:1px solid rgba(11,11,11,.10); border-radius:14px;
                   padding:18px 20px 16px; background:#fcfcfb; height:100%; }}
      div.srr-tile .k {{ color:#898781; font-size:.68rem; font-weight:600;
                      letter-spacing:.09em; text-transform:uppercase; }}
      div.srr-tile .v {{ color:#0b0b0b; font-size:2.4rem; font-weight:700; line-height:1.25; }}
      div.srr-tile .n {{ color:#898781; font-size:.78rem; }}
      p.srr-card-title {{ font-size:1.18rem; font-weight:600; color:#0b0b0b; margin:0 0 .3rem; }}
      p.srr-card-sub {{ color:#52514e; font-size:.87rem; margin-bottom:.2rem; }}
      p.srr-note {{ color:#898781; font-size:.76rem; }}
      .srr-pipe {{ background:#12120f; border-radius:12px; padding:18px 22px;
                   margin-top:34px; color:#c3c2b7; font-size:.82rem; }}
      .srr-pipe .k {{ color:#8f8e88; font-size:.68rem; font-weight:600;
                      letter-spacing:.12em; display:block; margin-bottom:12px; }}
      .srr-pipe .steps {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
      .srr-pipe .step {{ border:1px solid rgba(255,255,255,.10); background:#1e1e1a;
                         border-radius:18px; padding:7px 16px; }}
      .srr-pipe .arrow {{ color:#5a5954; }}
      .srr-pipe .by {{ margin-left:auto; color:#8f8e88; }}
      div[data-testid="stVerticalBlockBorderWrapper"]:has(> div .srr-card-title) {{
        border-radius:14px;
      }}
    </style>
    <div class="srr-top">
      <span class="mark">🌾 SAFRA RISK RADAR</span>
      <span class="sub">Brazil · soybean &amp; safrinha corn</span>
      <span class="right">
        <span>Weather through {short_date(weather_through)} <span class="dot">●</span></span>
        <span>dbt · BigQuery</span>
        <a href="https://github.com/caiogoia123/safra-risk-radar">GitHub</a>
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------- hero
st.markdown(
    f"""
    <div class="srr-eyebrow">SOYBEAN &amp; SAFRINHA CORN · {n_states} STATES ·
      {first_season}–{open_season}</div>
    <p class="srr-head">Weather does not predict the harvest.
      It predicts the harvests that <span class="fail">fail</span>.</p>
    <p class="srr-lede">Averaged over every season this model ties with the trend baseline.
      Restricted to the seasons that actually broke, it removes {soy_gain:.0f}% of the error
      — and flags {recall_pct:.0f}% of them in advance, against a baseline that by
      construction never flags one.</p>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ stat tiles
tiles = [
    ("Crop failures flagged", f"{recall_pct:.0f}%", "in advance · baseline flags 0%"),
    ("Error removed on failures", f"{soy_gain:.0f}%",
     f"soybean seasons >{abs(FAIL_PCT)}% below trend"),
    ("Seasons backtested", f"{n_seasons}",
     f"{first_scored}–{last_scored} · walk-forward refit"),
    ("Daily weather rows", f"{meta['weather_rows'] / 1e6:.1f}M",
     f"NASA POWER · {GRID_CELLS} grid cells"),
]
for col, (label, value, note) in zip(st.columns(4, gap="medium"), tiles):
    col.markdown(
        f'<div class="srr-tile"><div class="k">{label}</div>'
        f'<div class="v">{value}</div><div class="n">{note}</div></div>',
        unsafe_allow_html=True,
    )

st.write("")

# ---------------------------------------- the open season, and where model wins
left, right = st.columns([2, 3], gap="medium")

with left:
    with st.container(border=True):
        st.markdown(
            f'<p class="srr-card-title">{open_season_label} — the season CONAB has not '
            "closed</p>"
            '<p class="srr-card-sub">Forecast deviation from each state\'s own yield trend. '
            f"{len(live)} of {len(forecast)} states scored.</p>",
            unsafe_allow_html=True,
        )
        # Fixed height: the list scrolls instead of pushing the rest of the page
        # down, and the chart keeps a readable row height however long it gets.
        with st.container(height=300):
            st.plotly_chart(forecast_chart(live), width="stretch",
                            config={"displayModeBar": False})
        st.markdown('<p class="srr-note">Scroll for the full list.</p>',
                    unsafe_allow_html=True)

with right:
    with st.container(border=True):
        st.markdown(
            '<p class="srr-card-title">The model earns its keep only in the tail</p>'
            '<p class="srr-card-sub">Error removed versus the trend baseline, by how far the '
            f"season really fell. Ordinary seasons are {ordinary_pct:.0f}% of the sample — "
            "which is why the average looks like a tie.</p>",
            unsafe_allow_html=True,
        )
        gains = severity_gains(backtest)
        st.plotly_chart(severity_chart(gains), width="stretch",
                        config={"displayModeBar": False})
        with st.expander("Table view"):
            st.dataframe(
                gains.pivot(index="severity", columns="crop", values="gain")
                .reindex(SEVERITY_ORDER).round(1),
                width="stretch",
            )

# -------------------------------------------------------------------- exposure
with st.container(border=True):
    st.markdown(
        '<p class="srr-card-title">Exposure is not national</p>'
        '<p class="srr-card-sub">Correlation between rainfall anomaly in the critical window '
        f"and the yield residual, soybean. {STATE_NAME[exposure.index[-1]]} is "
        f"{expo_ratio:.0f} times as sensitive as {STATE_NAME[exposure.index[0]]} — a national "
        f"average erases this entirely. Pearson r, {expo_first}–{expo_last}.</p>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(exposure_chart(exposure), width="stretch",
                    config={"displayModeBar": False})
    with st.expander("Table view"):
        st.dataframe(exposure.round(2).rename("correlation"), width="stretch")

# ------------------------------------------------------------------- explorer
with st.container(border=True):
    head, pick_crop, pick_state = st.columns([5, 1.3, 1.3], gap="medium")
    head.markdown(
        '<p class="srr-card-title">Season by season</p>'
        f'<p class="srr-card-sub">Circled seasons are the ones the model called '
        f"{abs(FLAG_PCT)}% or more below trend, using only weather and seasons that preceded "
        f"them. About {false_alarm_pct:.0f}% of the calls are false alarms, and they are left "
        "in on purpose.</p>",
        unsafe_allow_html=True,
    )
    crop_choice = pick_crop.selectbox("Crop", list(CROP_LABEL.values()),
                                      label_visibility="collapsed")
    crop_code = {v: k for k, v in CROP_LABEL.items()}[crop_choice]
    states = sorted(backtest[backtest["crop_name"] == crop_code]["state_code"].unique())
    state_choice = pick_state.selectbox(
        "State", states, index=states.index("RS") if "RS" in states else 0,
        format_func=lambda s: STATE_NAME.get(s, s), label_visibility="collapsed",
    )

    series = backtest[(backtest["crop_name"] == crop_code)
                      & (backtest["state_code"] == state_choice)].sort_values("harvest_year")
    st.plotly_chart(
        season_chart(series, anomaly_series(season_risk, crop_code, state_choice)),
        width="stretch", config={"displayModeBar": False},
    )
    st.markdown(
        '<p class="srr-note">Lower panel: dry-day anomaly in the critical window, in standard '
        "deviations — the input the model actually reads. Its own scale, not a second axis on "
        "the yield plot.</p>",
        unsafe_allow_html=True,
    )
    with st.expander("Table view"):
        st.dataframe(
            series[["harvest_year", "yield_kg_ha", "trend_kg_ha", "actual_pct", "model"]]
            .rename(columns={"harvest_year": "Season", "yield_kg_ha": "Actual kg/ha",
                             "trend_kg_ha": "Trend kg/ha", "actual_pct": "Actual vs trend %",
                             "model": "Predicted vs trend %"}).round(1),
            width="stretch", hide_index=True,
        )

# ------------------------------------------------------- withheld + the method
if not suppressed.empty:
    names = ", ".join(f"{CROP_LABEL[r.crop_name]} in {r.state_code}"
                      for r in suppressed.itertuples())
    st.info(
        f"**Withheld from the {open_season_label} forecast: {names}.** Their critical windows "
        f"run into August and the weather series ends {long_date(weather_through)}, so the "
        f"window is only {suppressed['janela_coberta_pct'].min():.0f}–"
        f"{suppressed['janela_coberta_pct'].max():.0f}% covered. A truncated window reads "
        "to the model as an extreme drought — before this guard existed it forecast +99% "
        "for Paraná, about double any yield ever recorded there.",
        icon="⚠️",
    )

with st.expander("Method, and what this model cannot do"):
    st.markdown(
        f"""
**Weather is the input, never the output.** Nothing here forecasts the weather. Measured
weather from a crop's critical window goes in; the yield CONAB has not yet published comes
out. The target is the deviation from each state's own yield trend, not the yield level —
a model trained on the level mostly rediscovers sixty years of genetics and reports a
flattering error with no predictive value.

**Walk-forward validation.** For every test season, the yield trend, the climate normals the
anomalies are measured against, and the model itself are refitted on earlier seasons only.
Nothing about a season is available when that season is predicted.

**The baseline is honest and hard to beat.** "Next season equals trend" is what the model must
clear. On average it does not — soybean skill is {skill['Soybean']:+.1f}%, safrinha
{skill['Safrinha corn']:+.1f}%. Published as found.

**Known limits**

- Useful in the tail, harmful in the middle: on ordinary seasons the model is *worse* than
  simply assuming trend. It is a failure detector, not a yield forecaster.
- Precision on flagged failures is {100 - false_alarm_pct:.0f}% — roughly one false alarm per
  true call.
- The trend-shape and model pairing was chosen by looking at backtest results, so the numbers
  here are optimistic by an unknown margin. The real test is the next unseen season.
- State-level grain, following CONAB. Municipal yield precision is not claimed.
- Rio Grande do Sul has no meaningful safrinha crop and is excluded from that half.

**Pipeline** — CONAB grain series, IBGE PAM and municipal boundaries, NASA POWER daily
weather → Python ingestion → DuckDB (dev) and BigQuery (prod) → dbt staging / intermediate /
marts → scikit-learn → this app.
        """
    )

# ------------------------------------------------------------------- pipeline
steps = ["CONAB · IBGE · NASA POWER", "Python ingestion", "DuckDB (dev) · BigQuery (prod)",
         "dbt", "scikit-learn", "Streamlit"]
chain = '<span class="arrow">→</span>'.join(f'<span class="step">{s}</span>' for s in steps)
st.markdown(
    f'<div class="srr-pipe"><span class="k">PIPELINE</span>'
    f'<div class="steps">{chain}'
    '<span class="by">Built by Caio Goia</span></div></div>',
    unsafe_allow_html=True,
)
