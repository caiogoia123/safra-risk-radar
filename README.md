# Safra Risk Radar

**[→ Live dashboard](https://safra-risk-radar.streamlit.app)** · rebuilt weekly by CI, from
CONAB, IBGE and NASA POWER through dbt into BigQuery.

<sub>Hosted on Streamlit's free tier, which sleeps an app after a stretch of no visitors. If you
land on a "Zzzz" screen, the button on it wakes the app in about half a minute.</sub>

**How much of the year-to-year swing in Brazilian soybean and second-crop corn yield is
explained by weather in each crop's critical window — and can a shortfall be called before the
official survey closes?**

Brazil supplies roughly half of the world's soybean exports. A bad *safrinha* (second-crop corn)
in Mato Grosso moves global feed prices. Yet the official yield figure lands months after the
weather that caused it, and that gap is where trading, crop insurance and rural credit have to
decide. Weather is the **input** here, already measured — nothing about the future climate is
being predicted.

---

## The finding: this is not a yield forecaster

Averaged over every season, the model essentially ties the naive baseline of "yield equals
trend" — 3.4% better on soybean, 1.2% on second-crop corn. Published on that number alone, the
honest conclusion would be "does not beat the trend."

**The average hides the result.** Split by how bad the season actually was (soybean,
walk-forward 2003–2025, RMSE of the yield residual in percentage points):

| Actual deviation | n | Baseline | Model | Change |
|---|---|---|---|---|
| Shortfall < -20% | 14 | 34.4 | 20.6 | **-40% error** |
| -20% to -10% | 15 | 15.7 | 10.8 | **-31% error** |
| Normal ±10% | 89 | 5.9 | 9.6 | +61% error |
| Good > +20% | 12 | 33.5 | 34.8 | +4% error |

The model earns its keep only when the harvest breaks, and actively hurts in a normal year —
and normal years are 55% of the sample, which is exactly what dilutes the global metric.
Second-crop corn repeats the pattern, weaker: -27% error on shortfalls, +68% in normal years.

Read as a detector instead of a forecaster, on seasons finishing 10% or more below trend:

| Crop | Real events | Flagged | Correct | Recall | Precision | Baseline flags |
|---|---|---|---|---|---|---|
| Soybean | 29 | 28 | 13 | 45% | 46% | **0** |
| Second-crop corn | 38 | 34 | 19 | 50% | 56% | **0** |

The baseline detects zero shortfalls by construction — a trend line never predicts a bad year.
So the honest framing is: **a shortfall detector that catches about half of them with about
half false alarms, against a baseline that never warns at all.** For a trader or a credit desk,
half the shortfalls called early is worth more than 3% of RMSE.

## Why the target is a residual, not a yield

Yield rises over decades because seeds, machinery and practice improve. A model trained on the
level mostly rediscovers that trend, reports a flattering error and forecasts nothing. The
target here is the **residual against each state's own yield trend** — the part of the harvest
technology does not explain.

Choosing that trend was itself a result. Twelve detrending methods were compared on
out-of-sample error:

- **A non-linear trend does not fix second-crop corn**, even though the crop grew from 1,796 to
  5,198 kg/ha as it went from marginal to dominant. `log_linear` is the *worst* of the twelve
  (RMSE 39.4 against 31.5 for a straight line): in log space the early expansion extrapolates
  into nonsense. Quadratic and Theil-Sen also lose to the line.
- **What wins is not extrapolating at all** — a 3-year moving average, RMSE 28.3.
- **And the straight line stayed anyway.** The moving average is the better *forecast* and the
  worse *target*: it has already absorbed recent weather, so a residual against it carries mean
  reversion instead of climate, and every model trained on that target came out ~50% worse than
  its own baseline. Picking the trend by the best baseline is not the same as picking it by the
  best end-to-end system, and only the second one matters.

## What did not work

- **The *veranico* is not the strong variable it was expected to be.** The dry spell inside the
  critical window — longest run of consecutive dry days, computed by gaps-and-islands over the
  daily series — correlates *worse* with the yield residual than a plain count of dry days
  (-0.25 against -0.39 on soybean). Thresholds of 1, 2 and 5 mm were tested; the definition is
  not the problem. It was demoted from a model feature to a descriptive column.
- Measuring the *whole* spell that merely touches the window was tried and rejected: in Bahia
  the window closes in April, right as the five-month dry season begins, so the metric picked up
  the dry season rather than a drought event.

## What the data shows

Weather in the critical window tracks yield in the direction agronomy predicts. Against each
state's own 1992–2020 normal, over 1992–2025:

| Crop | Dry-day anomaly | Rainfall anomaly | Temperature anomaly |
|---|---|---|---|
| Soybean | **-0.39** | +0.29 | -0.29 |
| Second-crop corn | -0.26 | +0.21 | -0.18 |

**Climate exposure is wildly uneven between states** — correlation of soybean yield residual
against weather anomaly:

| State | Rainfall | Dry days |
|---|---|---|
| Rio Grande do Sul | **+0.50** | **-0.56** |
| Mato Grosso do Sul | +0.39 | -0.51 |
| Minas Gerais | +0.35 | -0.25 |
| Paraná | +0.24 | -0.31 |
| Bahia | +0.22 | -0.52 |
| Goiás | +0.15 | -0.24 |
| Mato Grosso | +0.13 | -0.40 |

Rio Grande do Sul is roughly four times as rainfall-sensitive as Mato Grosso. A national average
hides this completely: the drought that barely dents Mato Grosso is what breaks a harvest in the
South. Anyone pricing crop risk off a country-level number is mispricing both states.

The two worst seasons in the series are real events the pipeline found unaided — Rio Grande do
Sul soybean in 2005 at **-67% against trend** with 17 extra dry days (the 2004/05 drought), and
Paraná second-crop corn in 2021 at **-51%** with rainfall at **-2.06 standard deviations** (the
2021 safrinha failure).

## Architecture

```
CONAB grain series ─┐
IBGE municipal PAM ─┼─→ ingestion (Python) ─→ Parquet ─→ dbt ─→ marts
NASA POWER daily   ─┘                                     │
                                                          │
                                        ┌─────────────────┴────────────────┐
                                        ▼                                  ▼
                                 yield model                        Streamlit app
                                 (walk-forward backtest)            (public dashboard)
```

| Layer | Tech | Why |
|---|---|---|
| Extract & load | Python, `requests`, DuckDB | raw files kept verbatim for reproducibility |
| Transform | dbt Core | staging → intermediate → marts, 78 tests on both targets |
| Warehouse | DuckDB (dev) / BigQuery (prod) | same dbt project, two targets |
| Orchestration | GitHub Actions | weekly refresh, both targets, plus CI on every push |
| App | Streamlit | published dashboard, no Node toolchain required |

The same dbt project targets both warehouses, so the SQL stays close to ANSI. That portability
is enforced by actually running it: `dbt compile` resolves Jinja, but only execution rejects a
type, a function or a clause one engine has and the other does not.

The published app reads exported CSVs rather than querying the warehouse, so the dashboard costs
nothing to serve and does not break if the BigQuery sandbox tables expire. Those exports are
byte-reproducible — rebuilding the warehouse from scratch on another machine and re-exporting
produces identical files, which is what lets the weekly commit touch only rows that really moved.

## Data sources

| Source | Grain | Coverage |
|---|---|---|
| [CONAB](https://portaldeinformacoes.conab.gov.br) grain series | state × crop × season | 1976/77 → 2025/26 |
| [IBGE SIDRA 1612](https://sidra.ibge.gov.br/tabela/1612) (PAM) | municipality × crop × year | 1974 → 2024 |
| [NASA POWER](https://power.larc.nasa.gov) daily | 0.5° grid point | 1981 → present, ingested from 1991 |

**Why municipal data when the fact table is by state:** a state centroid is not where the crop
is. Mato Grosso's centroid sits in forest, Bahia's in unirrigated scrubland. Municipal production
from PAM locates the real producing belt — the municipalities making up 80% of each state's grain
output, 510 of them — and weather is sampled and weighted there.

Those 510 hubs collapse to 255 distinct NASA POWER cells, and the many-to-one ratio varies sharply
by state: 3.3 hubs per cell in Paraná against 1.0 in Bahia. Summing rainfall after that join would
triple Paraná's total and leave Bahia's untouched — a silent, region-biased error. Every weather
aggregate deduplicates by cell before summing.

## Method

1. **Detrend** yield per state and crop, so the target is the residual, not the level.
2. **Phenological windows, not calendar years.** Planting and harvest months come from CONAB's
   official calendar, parsed out of the PDF's coloured bars rather than typed by hand. The
   critical window is derived from it: last planting month through one month before harvest ends.
3. **Anomalies against each state's own normal.** 100 mm of rain in May is ordinary in Rio Grande
   do Sul and a drought signal in Mato Grosso.
4. **Named agronomic features** — dry days in the window, rainfall, temperature, growing degree
   days, each measured against that state's normal. Not 200 anonymous columns.
5. **Walk-forward validation.** Trend, climate normals and model are all refit each season using
   only prior years; nothing from season *T* exists when *T* is predicted. The baseline
   ("yield = trend") is reported alongside, and would have been published had it won.

## Scope and limitations

- **Rio Grande do Sul is excluded from second-crop corn** — CONAB publishes no safrinha calendar
  for the state because it does not grow a meaningful second crop. A deliberate cut, not a gap.
- **The current season is a survey estimate, not a realized harvest**, and CONAB's file carries no
  survey date. It is treated as a forecast target and kept out of training truth.
- **The model is only useful on shortfalls.** In a normal year it is worse than assuming the
  trend. It should be read as an alarm, not as a yield number.
- **State-level yield hides intra-state variation.** Production-weighted weather sampling reduces
  this but does not remove it.
- **A season still in progress is not predicted.** Partial windows are refused rather than
  extrapolated: measuring incomplete weather against a full-window normal produces a fake anomaly,
  which once turned a Paraná forecast into +99%.
- Yield in the source is rounded to one decimal in t/ha, and is recomputed from production and
  area to preserve the precision residual analysis needs.

## Reproducing

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python -m ingestion              # download sources, load into DuckDB
cd dbt
dbt build                        # DuckDB target by default
```

`data/` is gitignored — the ingestion step rebuilds it from the public sources. The CONAB
calendar, municipal PAM table and hub centroids are versioned instead of re-downloaded: they are
derived once from the official source and regenerated on purpose, which also keeps the two IBGE
APIs (which refuse datacenter IPs) off the CI critical path.

To run against BigQuery, set `GCP_KEYFILE` and `GCP_PROJECT` (see `.env.example`), then
`python -m ingestion --target prod` and `dbt build --target prod`. dbt commands run from inside
`dbt/`, since the DuckDB path is relative to the working directory.

## License

MIT
