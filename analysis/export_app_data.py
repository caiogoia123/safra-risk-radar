"""Freezes what the dashboard needs into small CSVs the app can ship with.

Streamlit Community Cloud serves straight from the GitHub repo, and `data/` is
gitignored -- the DuckDB file is 171 MB and regenerable. The marts are not big:
the whole fact table is 455 rows. Exporting them as CSV keeps the published app
free of credentials, warehouse quota and cold starts, and keeps the diffs
readable. The scheduled CI in week 5 refreshes these the same way.

    py -m analysis.export_app_data      (from the repo root, after `dbt build`)
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from analysis.backtest import BEST_MODEL_BY_CROP, forecast_season, run_backtest
from analysis.dataset import DB_PATH, REPO_ROOT, load_panel

OUTPUT_DIR = REPO_ROOT / "app" / "data"


def export_season_risk() -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.sql("select * from main_marts.fct_season_risk").df()


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
        frame.to_csv(path, index=False)
        print(f"{path.relative_to(REPO_ROOT)}: {len(frame)} linhas, {path.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
