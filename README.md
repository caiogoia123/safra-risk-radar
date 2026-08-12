# Safra Risk Radar

**English** · [Português](README.pt-BR.md)

**[→ Live dashboard](https://safra-risk-radar.streamlit.app)** · rebuilt weekly by CI, from
CONAB, IBGE and NASA POWER through dbt into BigQuery.

<sub>Hosted on Streamlit's free tier, which sleeps an app after a stretch of no visitors. If you
land on a "Zzzz" screen, the button on it wakes the app in about half a minute.</sub>

## What this is

A data pipeline that measures **how much of the year-to-year swing in Brazilian soybean and
second-crop corn yield is explained by weather in each crop's critical window**, and tests whether
a shortfall can be called before the official survey closes.

Brazil supplies roughly half of the world's soybean exports, and the official yield figure lands
months after the weather that caused it. That gap is where trading, crop insurance and rural credit
have to decide. Weather is the **input** here, already measured — nothing about future climate is
being predicted.

Scale: 3.3 million daily weather rows, 510 producer municipalities collapsed into 255 grid cells,
13 crop × state pairs, 293 seasons scored in a walk-forward backtest (2003–2025).

## Key results

Two conventions for reading the tables: the **baseline** is the simplest possible guess ("the
harvest comes in wherever the state's trend says"), and **error** is the distance between a
prediction and the real harvest in percentage points of yield — lower is better.

**1. Critical-window weather carries real but moderate signal.** Correlation between the model's
prediction and the observed residual: **+0.47** on soybean and **+0.29** on second-crop corn.

**2. On average, the model ties the trend.** RMSE gain over the baseline: 3.4% on soybean and 1.2%
on second-crop corn. That 3.4% is the **best result among the four model families tested** — other
configurations land below the baseline, and the choice was made looking at this same backtest. It
is not a general, settled improvement; it is noise the size of a tie.

**3. The gain is concentrated in the shortfalls.** The 161 soybean seasons scored (7 states ×
2003–2025), split by how good or bad the harvest actually turned out:

| How the season ended (vs. trend) | Seasons | Baseline error | Model error | Change |
|---|---|---|---|---|
| Severe shortfall: below -20% | 14 | 34.4 | 20.6 | **-40% error** |
| Moderate shortfall: -20% to -10% | 15 | 15.7 | 10.8 | **-31% error** |
| Normal season: ±10% | 89 | 5.9 | 9.6 | +61% error |
| Good season: +10% to +20% | 31 | 14.8 | 18.3 | +24% error |
| Very good season: above +20% | 12 | 33.5 | 34.8 | +4% error |

In normal seasons — 89 of the 161, and most of the sample — the trend alone is already the right
answer and the model only gets in the way. That is what dilutes the average gain in point 2.

An honest caveat: this shape is **not specific to this model**. Any predictor with positive
correlation and a narrower spread than the real data beats the baseline in the tails and loses in
the middle, by construction. The table shows where the signal is usable, not a special property of
the model.

**4. As a shortfall detector, it beats chance.** Counting as a shortfall any season finishing 10%
or more below trend:

| Crop | Real shortfalls | Alarms raised | Alarms right | Recall | Precision |
|---|---|---|---|---|---|
| Soybean | 29 | 28 | 13 | 45% | 46% |
| Second-crop corn | 38 | 34 | 19 | 50% | 56% |

Precision only means something against the base rate: shortfalls are 18% of soybean seasons and 29%
of safrinha seasons, so 46% and 56% are gains of 2.6× and 1.9× over chance. The baseline raises
**zero** alarms by construction — a trend line never predicts a bad year. With 29 and 38 events,
though, these rates are imprecise: the 95% interval for soybean recall runs from roughly 25% to 70%
(block bootstrap by year).

**5. But the model barely beats a one-variable rule.** Ranking seasons by the z-score of a single
weather variable, with the same number of alarms the model raises:

| Crop | Alarms | Model | Rule: dry days | Rule: rainfall |
|---|---|---|---|---|
| Soybean | 28 | 13 right | 13 right | 11 right |
| Second-crop corn | 34 | 19 right | 19 right | **21 right** |

The model's only clear edge is on **severe soybean shortfalls** (≤ -20%), where it catches 10 of 14
against 8 for the dry-day rule and 6 for the rainfall rule. On safrinha it has no edge at all:
rainfall alone detects more shortfalls than the whole model.

**Bottom line.** This is not an accurate yield forecaster and should not be presented as one. It is
a **risk detector** with real climate signal, useful in the tail of severe soybean shortfalls,
whose advantage over a simple rule is small or absent everywhere else.

## What was analysed

**The target is the residual against trend, not yield.** Yield rises over decades because seeds,
machinery and practice improve; a model trained on the level mostly rediscovers that trend, reports
a flattering error and forecasts nothing. Twelve detrending methods were compared on out-of-sample
error, and two results survived:

- **A non-linear trend does not fix second-crop corn**, even though the crop grew from 1,796 to
  5,198 kg/ha. `log_linear` is the *worst* of the twelve (RMSE 39.4 against 31.5 for a straight
  line): in log space the early expansion extrapolates into nonsense.
- **A 3-year moving average is the better forecast (RMSE 28.3) and the worse target.** It has
  already absorbed recent weather, so a residual against it carries mean reversion instead of
  climate, and every model trained on that target came out ~50% worse than its own baseline.
  Picking the trend by the best baseline is not the same as picking it by the best end-to-end
  system.

**The *veranico* is not the strong variable it was expected to be.** The dry spell inside the
critical window — longest run of consecutive dry days, computed by gaps-and-islands over the daily
series — correlates *worse* with the yield residual than a plain count of dry days (-0.26 against
-0.39 on soybean). Thresholds of 1, 2 and 5 mm were tested; the definition is not the problem. It
was demoted from a model feature to a descriptive column. Measuring the *whole* spell that merely
touches the window was tried and rejected too: in Bahia the window closes in April, right as the
dry season begins, so the metric picked up the dry season rather than a drought event.

**Weather tracks yield in the direction agronomy predicts.** Against each state's own 1992–2020
normal, over 1992–2025:

| Crop | Dry-day anomaly | Rainfall anomaly | Temperature anomaly |
|---|---|---|---|
| Soybean | **-0.39** | +0.29 | -0.29 |
| Second-crop corn | -0.26 | +0.21 | -0.18 |

**Climate exposure is wildly uneven between states**, and this is the project's most useful finding
— correlation of the soybean yield residual against weather anomaly:

| State | Rainfall | Dry days |
|---|---|---|
| Rio Grande do Sul | **+0.50** | **-0.56** |
| Mato Grosso do Sul | +0.39 | -0.51 |
| Minas Gerais | +0.35 | -0.25 |
| Paraná | +0.24 | -0.31 |
| Bahia | +0.22 | -0.51 |
| Goiás | +0.15 | -0.24 |
| Mato Grosso | +0.13 | -0.40 |

Rio Grande do Sul is roughly four times as rainfall-sensitive as Mato Grosso. A national average
hides this: the drought that barely dents Mato Grosso is what breaks a harvest in the South.

As a sanity check, two shortfalls the pipeline surfaced unaided are recognisable events. The worst
soybean season in the record is Rio Grande do Sul in 2005, at **-67% against trend** with 17 extra
dry days (the 2004/05 drought); Paraná second-crop corn in 2021 came in at **-51%** with rainfall
at **-2.06 standard deviations**.

## Architecture and tooling

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

| Stage | Where it runs | Tool and role |
|---|---|---|
| Extract & load | local **or** GitHub Actions | Python + `requests`; raw files kept verbatim |
| Transform | local **or** GitHub Actions | dbt Core: staging → intermediate → marts, 78 tests |
| Dev warehouse | **local** (single file) | DuckDB — no server, no credentials |
| Prod warehouse | **cloud** | BigQuery (sandbox) |
| Backtest & export | local **or** GitHub Actions | pandas + scikit-learn |
| Dashboard | **cloud** | Streamlit Community Cloud |
| Automation | **cloud** | GitHub Actions |

The same dbt project targets both warehouses, so the SQL stays close to ANSI. That portability is
enforced by actually running it on both: `dbt compile` resolves Jinja, but only execution rejects a
type or a function one engine has and the other does not.

**Why municipal data when the fact table is by state:** a state centroid is not where the crop is —
Mato Grosso's sits in forest, Bahia's in unirrigated scrubland. Municipal production from PAM
locates the real producing belt (the municipalities making up 80% of each state's output, 510 of
them), and weather is sampled and weighted there. Those 510 hubs collapse to 255 distinct NASA
POWER cells, and the ratio varies sharply by state: 3.3 hubs per cell in Paraná against 1.0 in
Bahia. Summing rainfall after that join would triple Paraná's total and leave Bahia's untouched — a
silent, region-biased error. Every weather aggregate deduplicates by cell before summing.

**Weekly automation.** Every Monday at 06:00 UTC, GitHub Actions re-runs ingestion, runs
`dbt build` against both targets, re-exports the dashboard CSVs and commits if the data moved. Two
goals in one job: keep the dashboard current (CONAB revises its survey monthly) and keep the
BigQuery sandbox tables alive, since they expire after 60 days and every build resets the clock. A
separate, lighter CI runs on every push: `dbt parse`, a render of every dashboard figure, and a
check of this README's numbers against the exported CSVs.

## Model and validation

**Ridge** regression over four named agronomic features — dry days in the window, rainfall, mean
temperature and growing degree days — each measured as distance from that state's own normal. Not
200 anonymous columns. On soybean the model uses per-state interactions (one slope per state,
α=10), justified by the uneven exposure in the table above; on safrinha, with fewer seasons per
state, the pooled version (α=1) is steadier.

Details that hold the result up:

1. **Phenological windows, not calendar years.** Planting and harvest months come from CONAB's
   official calendar, parsed out of the PDF's coloured bars rather than typed by hand. The critical
   window runs from the last planting month to one month before harvest ends.
2. **Anomalies against each state's own normal.** 100 mm of rain in May is ordinary in Rio Grande
   do Sul and a drought signal in Mato Grosso.
3. **Walk-forward validation.** Trend, climate normals and model are all refit each season using
   only prior years; nothing from season *T* exists when *T* is predicted. The anomalies already
   published in the mart are deliberately ignored here: they use a fixed 1992–2020 normal, which in
   a 2005 backtest would feed the model fifteen years of weather that had not happened yet.
4. **The baseline is reported alongside** and would have been published had it won.

## Dashboard

The published app has three pages: the yield series per crop and state with the model's alarms
marked, the critical-window weather anomaly panel, and the open season's forecast. It reads the
exported CSVs rather than querying the warehouse, so it costs nothing to serve and does not break
if the BigQuery sandbox tables expire. Those exports are byte-reproducible — rebuilding the
warehouse from scratch on another machine and re-exporting produces identical files, which is what
lets the weekly commit touch only rows that really moved.

## Reproducing

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python -m ingestion              # download sources, load into DuckDB
cd dbt
dbt build                        # DuckDB target by default
```

No credentials needed: the default target is local DuckDB, a roughly 170 MB file in `data/`, which
is gitignored and rebuilt by ingestion. The CONAB calendar, municipal PAM table and hub centroids
are versioned instead of re-downloaded — they are derived once from the official source and
regenerated on purpose, which also keeps the two IBGE APIs (which refuse datacenter IPs) off the CI
critical path.

To run against BigQuery, set `GCP_KEYFILE` and `GCP_PROJECT` (see `.env.example`), then
`python -m ingestion --target prod` and `dbt build --target prod`. dbt commands run from inside
`dbt/`, since the DuckDB path is relative to the working directory.

To redo the analysis: `python -m analysis.backtest` runs the full walk-forward and
`python -m analysis.export_app_data` regenerates the dashboard CSVs.

## Limitations

- **Model and trend were chosen on the same backtest that reports the result**, with no final
  hold-out. The numbers above are optimistic by an unknown margin.
- **The sample is small for the rates published** — 29 and 38 shortfall events. Confidence
  intervals are wide and the percentages should not be read as precise.
- **The model is only useful on shortfalls.** In a normal year it is worse than assuming the trend.
  It should be read as an alarm, not as a yield number.
- **Predictions are shrunk** — predicted spread is about half the real one on soybean and a third
  on safrinha, so the model rarely nails the magnitude of a large shortfall.
- **Rio Grande do Sul is excluded from second-crop corn**: CONAB publishes no safrinha calendar for
  the state because it does not grow a meaningful second crop. A deliberate cut.
- **The current season is a survey estimate, not a realized harvest**, and is kept out of training
  truth. A season still in progress is not predicted: partial windows are refused rather than
  extrapolated, because measuring incomplete weather against a full-window normal produces a fake
  anomaly — which once turned a Paraná forecast into +99%.
- **State-level yield hides intra-state variation.** Production-weighted weather sampling reduces
  this but does not remove it.

## License

MIT
