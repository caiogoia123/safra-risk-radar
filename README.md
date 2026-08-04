# Safra Risk Radar

**How much of the year-to-year swing in Brazilian soybean and second-crop corn yield is
explained by weather anomalies during each crop's critical window — and can a shortfall be
called before the official survey closes?**

Brazil supplies roughly half of the world's soybean exports. A bad *safrinha* (second-crop
corn) in Mato Grosso moves global feed prices. Yet the official yield figure for a season
lands months after the weather that caused it. This project quantifies the gap.

> **Status: work in progress (week 1 of 6).** Data ingestion is running; the analysis and
> dashboard are not built yet. Findings below will be filled in with real results — nothing
> here is a placeholder claim.

---

## The question behind the question

Yield goes up over time because seeds, machinery and practices improve. Any model trained on
raw yield mostly rediscovers that trend and reports a flattering error metric with no
predictive value. So the target here is **the residual against each state's yield trend** —
the part of the harvest that technology does *not* explain.

## Architecture

```
CONAB grain series ─┐
IBGE municipal PAM ─┼─→ ingestion (Python) ─→ Parquet ─→ dbt ─→ marts
NASA POWER daily   ─┘                                     │
                                                          │
                                        ┌─────────────────┴────────────────┐
                                        ▼                                  ▼
                                 yield model                        Streamlit app
                                 (temporal backtest)                (public dashboard)
```

| Layer | Tech | Why |
|---|---|---|
| Extract & load | Python, `requests`, DuckDB | raw files kept verbatim for reproducibility |
| Transform | dbt Core | staging → intermediate → marts, with tests and docs |
| Warehouse | DuckDB (dev) / BigQuery (prod) | same dbt project, two targets |
| Orchestration | GitHub Actions | scheduled refresh + `dbt test` in CI |
| App | Streamlit | published dashboard, no Node toolchain required |

## Data sources

| Source | Grain | Coverage |
|---|---|---|
| [CONAB](https://portaldeinformacoes.conab.gov.br) grain series | state × crop × season | 1976/77 → 2025/26 |
| [IBGE SIDRA 1612](https://sidra.ibge.gov.br/tabela/1612) (PAM) | municipality × crop × year | 1974 → 2024 |
| [NASA POWER](https://power.larc.nasa.gov) daily | 0.5° grid point | 1981 → present |

**Why municipal data when the fact table is by state:** a state centroid is not where the crop
is. Mato Grosso's centroid sits in forest; Bahia's in unirrigated scrubland. Municipal
production from PAM locates the real producing belt, and weather is sampled and weighted there.

## Method

1. **Detrend** yield per state and crop, so the target is the residual, not the level.
2. **Phenological windows, not calendar years** — soybean ~Oct→Feb, second-crop corn ~Feb→Jun,
   shifted per state.
3. **Anomalies against the 1991–2020 normal** for that grid point and day of year. 100 mm of
   rain in May is ordinary in Rio Grande do Sul and a drought signal in Mato Grosso.
4. **Agronomically meaningful features** — consecutive dry days in the critical window, growing
   degree days, hot nights, accumulated water deficit. Not 200 unnamed features.
5. **Temporal validation** — train through season *t*, test on *t+1*, never shuffled. The
   baseline (forecast = trend) is reported alongside. If the model does not beat the trend,
   that result gets published too.

## Findings so far

These are correlations from the built marts, not the output of a validated model.
The forecasting work comes next, and its results will be reported separately.

**Weather in the critical window tracks yield, in the direction agronomy predicts.**
Against each state's own 1992-2020 normal, over 1992-2025:

| Crop | Dry-day anomaly | Rainfall anomaly | Temperature anomaly |
|---|---|---|---|
| Soybean | **-0.39** | +0.29 | -0.29 |
| Second-crop corn | -0.26 | +0.21 | -0.18 |

**Climate exposure is wildly uneven between states** — the single most useful result
so far. Correlation of soybean yield residual against weather anomaly:

| State | Rainfall | Dry days |
|---|---|---|
| Rio Grande do Sul | **+0.50** | **-0.56** |
| Mato Grosso do Sul | +0.39 | -0.51 |
| Minas Gerais | +0.35 | -0.25 |
| Paraná | +0.24 | -0.31 |
| Bahia | +0.22 | -0.52 |
| Goiás | +0.15 | -0.24 |
| Mato Grosso | +0.13 | -0.40 |

Rio Grande do Sul is roughly four times as rainfall-sensitive as Mato Grosso. A
national average hides this completely: the same drought that barely dents Mato
Grosso is what breaks a harvest in the South. Anyone pricing crop risk on a
country-level number is mispricing both states.

**The two worst seasons in the series are real events the data found unaided:**

- **Rio Grande do Sul soybean, 2005: -67% against trend**, with 17 extra dry days.
  The 2004/05 drought.
- **Paraná second-crop corn, 2021: -51%**, with rainfall at **-2.06 standard
  deviations**. The safrinha failure of 2021.

## Known limitations

- **The linear detrend does not fit second-crop corn.** Its yield went from 1,796 to
  5,198 kg/ha as the crop moved from marginal to dominant — growth a straight line
  cannot follow, so early-season residuals carry trend error rather than weather
  signal. Evidence: restricting the series to 2010+ lifts the dry-day correlation
  from -0.26 to -0.48, while soybean holds steady at ~-0.38 either way. The
  forecasting model needs a non-linear trend, a later start date, or both.
- **Rio Grande do Sul is excluded from the corn analysis** — CONAB publishes no
  safrinha calendar for the state, because it does not grow a meaningful second crop.
- Correlation here is in-sample and uses a trend fitted over the whole series. It
  describes the record; it does not forecast.

## Reproducing

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python -m ingestion              # download sources, load into DuckDB
cd dbt
dbt build                        # DuckDB target by default
```

`data/` is gitignored — the ingestion step rebuilds it from the public sources.

To run against BigQuery instead, set `GCP_KEYFILE` and `GCP_PROJECT` (see `.env.example`),
then `python -m ingestion --target prod` and `dbt build --target prod`. dbt commands run from
inside `dbt/`, since the DuckDB path is relative to the working directory.

## Known limitations

- The most recent season in CONAB is a **survey estimate, not a realized harvest**, and the file
  carries no survey date. It is treated as a forecast target and excluded from training truth.
- Yield in the source is rounded to one decimal in t/ha. It is recomputed from production and
  area, which preserves the precision the residual analysis needs.
- State-level yield hides intra-state variation. A weighted weather sample reduces, but does not
  eliminate, this.

## License

MIT
