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

## Findings

*To be filled in at week 3, with the analysis. No claims before the data supports them.*

## Reproducing

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
python -m ingestion          # downloads sources into data/
cd dbt && dbt build          # DuckDB target by default
```

`data/` is gitignored — the ingestion step rebuilds it from the public sources.

## Known limitations

- The most recent season in CONAB is a **survey estimate, not a realized harvest**, and the file
  carries no survey date. It is treated as a forecast target and excluded from training truth.
- Yield in the source is rounded to one decimal in t/ha. It is recomputed from production and
  area, which preserves the precision the residual analysis needs.
- State-level yield hides intra-state variation. A weighted weather sample reduces, but does not
  eliminate, this.

## License

MIT
