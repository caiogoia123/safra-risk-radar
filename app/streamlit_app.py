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
# A marca do mockup, não o emoji 🌾: o emoji entra colorido pela fonte do sistema
# e destoa da barra escura -- este desenho usa o laranja da paleta.
WHEAT = (
    '<svg width="22" height="22" viewBox="0 0 22 22" fill="none">'
    '<path d="M11,22 V6" stroke="#eb6834" stroke-width="2" stroke-linecap="round"/>'
    '<path d="M11,10 C6,10 3,7 3,3 C8,3 11,6 11,10 Z" fill="#eb6834"/>'
    '<path d="M11,10 C16,10 19,7 19,3 C14,3 11,6 11,10 Z" fill="#eb6834" opacity=".72"/>'
    '<path d="M11,17 C6,17 3,14 3,10 C8,10 11,13 11,17 Z" fill="#eb6834" opacity=".52"/>'
    '<path d="M11,17 C16,17 19,14 19,10 C14,10 11,13 11,17 Z" fill="#eb6834" opacity=".34"/>'
    "</svg>"
)

st.markdown(
    f"""
    <style>
      /* Uma medida só para a margem da página: a barra escura e o rodapé sangram
         até a borda anulando exatamente este padding, e um valor solto em cada
         lugar desalinha os três na primeira vez que um deles muda. */
      :root {{ --srr-pad: 64px; }}
      .stMainBlockContainer {{ padding: 0 var(--srr-pad) 0; max-width: 1440px; }}
      /* O toolbar do Streamlit (Deploy, menu) flutua por cima da barra escura e é
         a primeira coisa que se vê no canto superior direito. Fora. */
      header[data-testid="stHeader"] {{ display: none; }}
      [data-testid="stToolbar"] {{ display: none; }}
      .srr-bleed {{ margin-left: calc(-1 * var(--srr-pad));
                    margin-right: calc(-1 * var(--srr-pad));
                    padding-left: var(--srr-pad); padding-right: var(--srr-pad);
                    background:#12120f; }}
      /* Sem `padding` de atalho aqui: o valor curto zera também o horizontal que
         a .srr-bleed usa para realinhar o conteúdo com o resto da página, e a
         barra sangra com o texto colado na borda da tela. */
      .srr-top {{
        color:#fff; margin-bottom:52px; height:68px;
        display:flex; align-items:center; gap:14px; flex-wrap:wrap;
      }}
      .srr-top .logo {{ display:flex; align-items:center; }}
      .srr-top .mark {{ font-weight:600; letter-spacing:.11em; font-size:.97rem;
                        margin-left:-4px; }}
      .srr-top .sub {{ color:#8f8e88; font-size:.81rem; margin-left:12px; }}
      .srr-top .right {{ margin-left:auto; display:flex; gap:32px; align-items:center;
                        color:#c3c2b7; font-size:.81rem; flex-wrap:wrap; }}
      .srr-top .dot {{ color:#0ca30c; font-size:1.1rem; line-height:0; }}
      .srr-top a {{ color:#c3c2b7; text-decoration:none; }}
      .srr-top a:hover {{ color:#fff; }}
      div.srr-eyebrow {{ color:#898781; font-size:.75rem; font-weight:600;
                      letter-spacing:.11em; margin-bottom:1.1rem; }}
      p.srr-head {{ font-size:2.12rem; font-weight:700; line-height:1.18;
                   color:#0b0b0b; margin:0 0 1rem 0; }}
      p.srr-head .fail {{ color:#e34948; }}
      /* Quebra na mesma largura da faixa de KPIs logo abaixo, não antes: o texto
         parando no meio da página abria uma coluna de branco à direita que não
         alinhava com nada. */
      p.srr-lede {{ color:#52514e; font-size:1rem; line-height:1.7;
                    max-width:100%; margin-bottom:.4rem; }}
      /* Os quatro KPIs num grid só, não em `st.columns`. Item de grid estica por
         padrão, então os quatro terminam na mesma linha seja qual for o número
         de linhas que o rótulo e a nota ocupem -- e é o que quebrava ao estreitar
         a janela: em colunas do Streamlit, a corrente de divs entre a coluna e o
         cartão para na altura natural, e esticá-la com `height:100%` tira o
         cartão mais alto da conta da linha, que encolhe para a do mais baixo.
         Aqui não há widget nenhum dentro dos cartões, então o grid é de graça. */
      .srr-kpis {{ display:grid; gap:20px; margin-bottom:8px;
                   grid-template-columns:repeat(4, minmax(0, 1fr)); }}
      @media (max-width: 900px) {{
        .srr-kpis {{ grid-template-columns:repeat(2, minmax(0, 1fr)); }}
      }}
      .srr-tile {{ border:1px solid rgba(11,11,11,.10); border-radius:14px;
                   padding:22px 24px 20px; background:#fcfcfb;
                   display:flex; flex-direction:column; }}
      div.srr-tile .k {{ color:#898781; font-size:.7rem; font-weight:600;
                      letter-spacing:.09em; text-transform:uppercase; }}
      /* O número nunca quebra: numa janela estreita "3.3M" virava "3.3" com o
         "M" na linha de baixo. Encolhe com a coluna em vez de partir. */
      div.srr-tile .v {{ color:#0b0b0b; font-weight:700; line-height:1.32;
                         white-space:nowrap;
                         font-size:clamp(1.9rem, 4.4vw, 2.75rem); }}
      /* A nota desce para o pé do cartão: com os quatro na mesma altura, ela é o
         que fecha a leitura -- solta logo abaixo do número, para em alturas
         diferentes assim que um rótulo quebra em duas linhas. Em tela larga, em
         que ninguém quebra, nada muda. */
      div.srr-tile .n {{ color:#898781; font-size:.78rem; margin-top:auto;
                         padding-top:6px; }}
      p.srr-card-title {{ font-size:1.1rem; font-weight:600; color:#0b0b0b; margin:0 0 .45rem; }}
      p.srr-card-sub {{ color:#52514e; font-size:.85rem; line-height:1.5; margin-bottom:.2rem; }}
      /* Cartões: a moldura padrão do Streamlit é cinza-azulada, quadrada e cola
         no conteúdo. A chave `key=` de cada container vira classe `st-key-*`, que
         é o único gancho estável -- as classes emotion mudam a cada versão. */
      div[class*="st-key-srr-card"] {{
        background:#fcfcfb; border:1px solid rgba(11,11,11,.10);
        border-radius:14px; padding:24px 26px 20px; margin-top:24px;
      }}
      div[class*="st-key-srr-scroll"] {{ padding:0; }}
      /* "Table view" como um link discreto, não como uma caixa da largura da
         página: é uma saída de emergência do gráfico, não um segundo cartão. */
      [data-testid="stExpander"] details {{ border:none; background:transparent; }}
      [data-testid="stExpander"] summary {{ padding-left:0; }}
      div[class*="st-key-srr-card"] [data-testid="stExpander"] summary p {{
        color:#898781; font-size:.78rem;
      }}
      .srr-pipe {{ padding-top:22px; padding-bottom:26px; color:#c3c2b7;
                   font-size:.81rem; margin-top:44px; }}
      .srr-pipe .k {{ color:#8f8e88; font-size:.68rem; font-weight:600;
                      letter-spacing:.12em; display:block; margin-bottom:14px; }}
      .srr-pipe .steps {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
      .srr-pipe .step {{ border:1px solid rgba(255,255,255,.10); background:#1e1e1a;
                         border-radius:18px; padding:7px 16px; }}
      .srr-pipe .arrow {{ color:#5a5954; }}
      .srr-pipe .by {{ margin-left:auto; color:#8f8e88; }}
      /* Cards lado a lado terminam na mesma linha. A coluna já recebe a altura
         da linha (o flex do Streamlit estica), mas o cartão dentro dela para na
         sua altura natural -- então a borda do mais curto fecha antes. Esticar a
         cadeia inteira resolve em qualquer largura, o que uma altura em px não
         faz: o cartão mais alto cresce quando o subtítulo quebra numa linha a
         mais. Só o cartão estica; a área rolável mantém a altura fixa que lhe dá
         o overflow -- deixá-la crescer com flex devolve `overflow: visible` e
         mata a rolagem.
         Vale só para esta linha, não para toda coluna da página: altura
         percentual tira o conteúdo mais alto da conta da linha, e nos KPIs isso
         encolhia a linha até a altura do cartão mais baixo. */
      div[class*="st-key-srr-row-cards"] [data-testid="stColumn"]
        > [data-testid="stVerticalBlock"],
      div[class*="st-key-srr-row-cards"] [data-testid="stColumn"]
        > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"],
      div[class*="st-key-srr-row-cards"] [data-testid="stColumn"]
        > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]
        > [data-testid="stVerticalBlock"] {{
        height: 100%;
      }}
    </style>
    <div class="srr-bleed srr-top">
      <span class="logo">{WHEAT}</span>
      <span class="mark">SAFRA RISK RADAR</span>
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
st.markdown(
    '<div class="srr-kpis">'
    + "".join(f'<div class="srr-tile"><div class="k">{label}</div>'
              f'<div class="v">{value}</div><div class="n">{note}</div></div>'
              for label, value, note in tiles)
    + "</div>",
    unsafe_allow_html=True,
)

# ---------------------------------------- the open season, and where model wins
cards_row = st.container(key="srr-row-cards")
left, right = cards_row.columns([2, 3], gap="medium")

with left:
    with st.container(border=True, key="srr-card-forecast"):
        st.markdown(
            f'<p class="srr-card-title">{open_season_label} — the season CONAB has not '
            "closed</p>"
            '<p class="srr-card-sub">Forecast deviation from each state\'s own yield trend. '
            f"{len(live)} of {len(forecast)} states scored.</p>",
            unsafe_allow_html=True,
        )
        # A lista cresce até o pé do cartão em vez de rolar dentro de uma altura
        # fixa: com 380px ela rolava por menos de uma linha e ainda deixava uma
        # faixa branca embaixo, porque o cartão é esticado pelo vizinho mais alto.
        # Esticar é seguro aqui porque o número de linhas é limitado -- são as 13
        # combinações cultura x estado que o pipeline pontua, não uma série
        # aberta. Se um dia passar disso, volta a altura fixa com rolagem.
        with st.container(height="stretch", border=False, key="srr-scroll-forecast"):
            st.plotly_chart(forecast_chart(live), width="stretch", height="stretch",
                            config={"displayModeBar": False})

with right:
    with st.container(border=True, key="srr-card-severity"):
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
with st.container(border=True, key="srr-card-exposure"):
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
with st.container(border=True, key="srr-card-seasons"):
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
    with st.expander("Table view"):
        st.dataframe(
            series[["harvest_year", "yield_kg_ha", "trend_kg_ha", "actual_pct", "model"]]
            .rename(columns={"harvest_year": "Season", "yield_kg_ha": "Actual kg/ha",
                             "trend_kg_ha": "Trend kg/ha", "actual_pct": "Actual vs trend %",
                             "model": "Predicted vs trend %"}).round(1),
            width="stretch", hide_index=True,
        )

# ------------------------------------------------------------------- the method
# O que ficou de fora da previsão é um detalhe do método, não a manchete: como
# `st.info` de largura inteira, era a caixa mais chamativa da página. O card da
# safra aberta já diz "11 of 13 states scored"; aqui está o porquê.
if suppressed.empty:
    withheld = ""
else:
    names = ", ".join(f"{CROP_LABEL[r.crop_name]} in {r.state_code}"
                      for r in suppressed.itertuples())
    withheld = (
        f"\n\n**Withheld from the {open_season_label} forecast: {names}.** Their critical "
        f"windows run into August and the weather series ends {long_date(weather_through)}, so "
        f"the window is only {suppressed['janela_coberta_pct'].min():.0f}–"
        f"{suppressed['janela_coberta_pct'].max():.0f}% covered. A truncated window reads "
        "to the model as an extreme drought — before this guard existed it forecast +99% "
        "for Paraná, about double any yield ever recorded there."
    )

with st.expander("Method, and what this model cannot do"):
    st.markdown(
        withheld
        + f"""
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
    f'<div class="srr-bleed srr-pipe"><span class="k">PIPELINE</span>'
    f'<div class="steps">{chain}'
    '<span class="by">Built by Caio Goia</span></div></div>',
    unsafe_allow_html=True,
)
