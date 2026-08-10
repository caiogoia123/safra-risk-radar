"""Safra Risk Radar -- the published face of the project.

Reads the CSVs exported by `analysis/export_app_data.py`, so the deployed app
needs no warehouse, no credentials and no scikit-learn: pandas and plotly only.

Leads with what the backtest actually showed. The model does not beat the trend
on average, and saying so up front is the point -- a dashboard that opened with
"93% accurate" would be describing a different, dishonest project.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from charts import (
    CROP_LABEL,
    INK_SOFT,
    SEVERITY_ORDER,
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


season_risk = load("season_risk")
backtest = widen(load("backtest"))
forecast = load("forecast")
meta = load_meta()
weather_through = date.fromisoformat(meta["weather_through"])

# Every year this page states is derived, never typed. The one time a date was
# written into the copy it went stale on the first scheduled refresh, and the
# published app spent a week misreporting its own coverage.
first_season = int(season_risk["harvest_year"].min())
open_season = int(season_risk["harvest_year"].max())   # CONAB's survey, not a harvest
n_states = season_risk["state_code"].nunique()
first_scored = int(backtest["harvest_year"].min())
last_scored = int(backtest["harvest_year"].max())
# Harvest year 2026 is the 2025/26 season, the way CONAB labels it.
open_season_label = f"{open_season - 1}/{str(open_season)[2:]}"

# ----------------------------------------------------------------------- header

st.title("Safra Risk Radar")
st.markdown(
    "#### Climate stress in the critical window, measured against what Brazilian "
    f"soybean and safrinha corn actually yielded — {first_season} to {open_season}, "
    f"{n_states} states."
)
st.markdown(
    f"<p style='color:{INK_SOFT};font-size:1.05rem;max-width:62rem'>"
    "The honest headline is not that weather predicts the harvest. It is that "
    "<b>weather predicts the bad harvests</b>. Averaged over every season this model "
    "ties with the trend; restricted to the seasons that actually broke, it removes "
    "40% of the error — and it flags about half of them in advance, against a "
    "baseline that by construction never raises a flag at all.</p>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------- stat row

failures = backtest[backtest["actual_pct"] <= -10]
called = failures[failures["model"] <= -10]
worst_soy = backtest[(backtest["crop_name"] == "SOJA")
                     & (backtest["severity"] == SEVERITY_ORDER[0])]
soy_gain = (1 - rmse(worst_soy["model"] - worst_soy["actual_pct"])
            / rmse(worst_soy["baseline"] - worst_soy["actual_pct"])) * 100

a, b, c, d = st.columns(4)
a.metric("Crop failures flagged in advance", f"{len(called) / len(failures) * 100:.0f}%",
         help="Seasons that came in 10% or more below trend and were predicted as such. "
              "The trend baseline scores 0% here — it never predicts a failure.")
b.metric("Error removed on failed seasons", f"{soy_gain:.0f}%",
         help="Soybean seasons more than 20% below trend, RMSE against the baseline.")
c.metric("Seasons backtested", f"{backtest['harvest_year'].nunique()}",
         help=f"{first_scored}–{last_scored}, walk-forward: trend, climate normals and "
              "model refitted on past seasons only.")
d.metric("Daily weather rows", f"{meta['weather_rows'] / 1e6:.1f}M",
         help="NASA POWER, 255 grid cells over the producing municipalities, "
              f"{date.fromisoformat(meta['weather_from']).year} onward.")

st.divider()

# ------------------------------------------------------- 1. where the model wins

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("The model earns its keep only in the tail")
    st.caption(
        "Error removed versus the trend baseline, by how far the season really fell. "
        "Positive is better than the baseline. Ordinary seasons are 55% of the sample, "
        "which is why the average looks like a tie."
    )
    gains = severity_gains(backtest)
    st.plotly_chart(severity_chart(gains), use_container_width=True)
    with st.expander("Table view"):
        st.dataframe(
            gains.pivot(index="severity", columns="crop", values="gain")
            .reindex(SEVERITY_ORDER).round(1),
            use_container_width=True,
        )

with right:
    st.subheader("Exposure is not national")
    st.caption(
        "Correlation between rainfall anomaly in the critical window and the yield "
        "residual, soybean. Rio Grande do Sul is roughly four times as sensitive as "
        "Mato Grosso — a national average erases this entirely."
    )
    exposure = state_exposure(season_risk)
    st.plotly_chart(exposure_chart(exposure), use_container_width=True)
    with st.expander("Table view"):
        st.dataframe(exposure.round(2).rename("correlation"), use_container_width=True)

st.divider()

# ------------------------------------------------------------------ 2. explorer

st.subheader("Season by season")
filters = st.columns([1, 1, 4])
crop_choice = filters[0].selectbox("Crop", list(CROP_LABEL.values()))
crop_code = {v: k for k, v in CROP_LABEL.items()}[crop_choice]
states = sorted(backtest[backtest["crop_name"] == crop_code]["state_code"].unique())
state_choice = filters[1].selectbox(
    "State", states, index=states.index("RS") if "RS" in states else 0
)

series = backtest[(backtest["crop_name"] == crop_code)
                  & (backtest["state_code"] == state_choice)].sort_values("harvest_year")

st.plotly_chart(season_chart(series), use_container_width=True)
st.caption(
    "Circled seasons are the ones the model called 10% or more below trend, using only "
    "weather and seasons that preceded them. A circle sitting **above** the trend line is a "
    "false alarm, and they are left in on purpose — roughly half the calls are. "
    f"{crop_choice}, {state_choice}."
)
with st.expander("Table view"):
    st.dataframe(
        series[["harvest_year", "yield_kg_ha", "trend_kg_ha", "actual_pct", "model"]]
        .rename(columns={"harvest_year": "Season", "yield_kg_ha": "Actual kg/ha",
                         "trend_kg_ha": "Trend kg/ha", "actual_pct": "Actual vs trend %",
                         "model": "Predicted vs trend %"}).round(1),
        use_container_width=True, hide_index=True,
    )

st.divider()

# ------------------------------------------------------------------ 3. forecast

st.subheader(f"{open_season_label} — the season CONAB has not closed yet")
st.caption(
    "The weather in the critical window already happened and is measured; the official "
    "yield is still a survey estimate. This is the forecast the project is willing to be "
    "judged on."
)

live = forecast.dropna(subset=["desvio_previsto_pct"]).copy()
live["label"] = live["crop_name"].map(CROP_LABEL) + " · " + live["state_code"]
live = live.sort_values("desvio_previsto_pct")
st.plotly_chart(forecast_chart(live), use_container_width=True)

suppressed = forecast[forecast["desvio_previsto_pct"].isna()]
if not suppressed.empty:
    names = ", ".join(f"{CROP_LABEL[r.crop_name]} in {r.state_code}"
                      for r in suppressed.itertuples())
    st.info(
        f"**Withheld: {names}.** Their critical windows run into August and the weather "
        f"series ends {long_date(weather_through)}, so the window is only "
        f"{suppressed['janela_coberta_pct'].min():.0f}–"
        f"{suppressed['janela_coberta_pct'].max():.0f}% covered. A truncated window reads "
        "to the model as an extreme drought — before this guard existed it forecast +99% "
        "for Paraná, about double any yield ever recorded there.",
        icon="⚠️",
    )
with st.expander("Table view"):
    st.dataframe(
        forecast.rename(columns={
            "crop_name": "Crop", "state_code": "State",
            "janela_coberta_pct": "Window covered %", "tendencia_kg_ha": "Trend kg/ha",
            "desvio_previsto_pct": "Forecast vs trend %", "previsao_kg_ha": "Forecast kg/ha",
            "estimativa_conab_kg_ha": "CONAB estimate kg/ha", "dif_vs_conab_pct": "vs CONAB %",
        }).round(1), use_container_width=True, hide_index=True,
    )

st.divider()

# -------------------------------------------------------------------- 4. method

with st.expander("Method, and what this model cannot do"):
    st.markdown(
        """
**Weather is the input, never the output.** Nothing here forecasts the weather. Measured
weather from a crop's critical window goes in; the yield CONAB has not yet published comes
out. The target is the deviation from each state's own yield trend, not the yield level —
a model trained on the level mostly rediscovers sixty years of genetics and reports a
flattering error with no predictive value.

**Walk-forward validation.** For every test season, the yield trend, the climate normals the
anomalies are measured against, and the model itself are refitted on earlier seasons only.
Nothing about a season is available when that season is predicted.

**The baseline is honest and hard to beat.** "Next season equals trend" is what the model must
clear. On average it does not — soybean skill is +3.4%, safrinha +1.2%. Published as found.

**Known limits**

- Useful in the tail, harmful in the middle: on ordinary seasons the model is *worse* than
  simply assuming trend. It is a failure detector, not a yield forecaster.
- Precision on flagged failures is around 50% — roughly one false alarm per true call.
- The trend-shape and model pairing was chosen by looking at backtest results, so the numbers
  here are optimistic by an unknown margin. The real test is the next unseen season.
- State-level grain, following CONAB. Municipal yield precision is not claimed.
- Rio Grande do Sul has no meaningful safrinha crop and is excluded from that half.

**Pipeline** — CONAB grain series, IBGE PAM and municipal boundaries, NASA POWER daily
weather → Python ingestion → DuckDB (dev) and BigQuery (prod) → dbt staging / intermediate /
marts → scikit-learn → this app.
        """
    )

st.caption("Built by Caio Goia · github.com/caiogoia123/safra-risk-radar")
