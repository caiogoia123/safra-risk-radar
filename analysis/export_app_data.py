"""Freezes what the dashboard needs into small CSVs the app can ship with.

Streamlit Community Cloud serves straight from the GitHub repo, and `data/` is
gitignored -- the DuckDB file is 171 MB and regenerable. The marts are not big:
the whole fact table is 455 rows. Exporting them as CSV keeps the published app
free of credentials, warehouse quota and cold starts, and keeps the diffs
readable. The scheduled CI in week 5 refreshes these the same way.

    py -m analysis.export_app_data      (from the repo root, after `dbt build`)
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from analysis.backtest import BEST_MODEL_BY_CROP, forecast_season, run_backtest
from analysis.dataset import DB_PATH, REPO_ROOT, load_panel

OUTPUT_DIR = REPO_ROOT / "app" / "data"


def export_season_risk() -> pd.DataFrame:
    # Explicit ordering: a bare `select *` returns whatever order the engine
    # happens to produce, and reloading the warehouse was enough to shuffle it.
    # That alone rewrote 63 lines of an otherwise unchanged file.
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.sql(
            """
            select * from main_marts.fct_season_risk
            order by crop_name, state_code, harvest_year
            """
        ).df()


def export_meta() -> dict[str, str]:
    """Facts about the data that the dashboard states in prose.

    The weather cutoff used to be typed into the app text. It went stale the
    first time the scheduled refresh ran: the series moved to a later date and
    the sentence did not, so the published app misreported its own coverage.
    Anything the copy asserts about the data has to be read from the data.
    """
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        cutoff = con.sql(
            "select max(weather_date) from main_staging.stg_weather_daily"
        ).fetchone()[0]
    return {"weather_through": cutoff.isoformat()}


# Sort keys per export, so the committed files depend on the data and nothing
# else -- not engine order, not the order concurrent fetches happened to finish.
SORT_KEYS = {
    "season_risk": ["crop_name", "state_code", "harvest_year"],
    "backtest": ["crop_name", "model", "state_code", "harvest_year"],
    "forecast": ["crop_name", "state_code"],
}


# Enough precision for a dashboard by a wide margin, and it makes the export
# reproducible. Floating-point addition is not associative, so once the sources
# are fetched concurrently the same data can be summed in a different order and
# land a few units off in the 12th decimal. Unrounded, that noise alone rewrote
# 758 lines of CSV on a run where nothing had actually changed -- which would
# have the scheduled job committing pure churn every week and burying the diffs
# that matter.
DECIMALS = 6


def _stabilise(frame: pd.DataFrame) -> pd.DataFrame:
    floats = frame.select_dtypes("float")
    if not floats.empty:
        frame[floats.columns] = floats.round(DECIMALS)
    return frame


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    season_risk = export_season_risk()
    panel = load_panel()
    backtest = run_backtest(panel)
    forecast = forecast_season(panel)

    # The app plots the chosen model against the baseline, not the whole
    # leaderboard, so only those two survive the export.
    keep = backtest["model"] == "baseline_trend"
    for crop, model in BEST_MODEL_BY_CROP.items():
        keep |= (backtest["crop_name"] == crop) & (backtest["model"] == model)
    backtest = backtest[keep].copy()
    backtest["role"] = backtest["model"].apply(
        lambda m: "baseline" if m == "baseline_trend" else "model"
    )

    for name, frame in [
        ("season_risk", season_risk),
        ("backtest", backtest),
        ("forecast", forecast),
    ]:
        path = OUTPUT_DIR / f"{name}.csv"
        frame = frame.sort_values(SORT_KEYS[name], kind="stable").reset_index(drop=True)
        _stabilise(frame).to_csv(path, index=False)
        print(f"{path.relative_to(REPO_ROOT)}: {len(frame)} linhas, {path.stat().st_size/1024:.0f} KB")

    # Sorted keys and a trailing newline for the same reason the CSVs are
    # rounded and ordered: this file is committed, so it may only change when
    # the data does.
    meta = export_meta()
    meta_path = OUTPUT_DIR / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{meta_path.relative_to(REPO_ROOT)}: {meta}")


if __name__ == "__main__":
    main()
