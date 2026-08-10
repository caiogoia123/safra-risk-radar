"""Loads the season panel out of the warehouse.

Everything the model needs comes from `fct_season_risk`, but deliberately in raw
form: the anomalies published there are measured against a fixed 1992-2020
normal, which for a backtest of, say, 2005 would quietly feed the model fifteen
years of weather that had not happened yet. Normals and trends are refitted on
training years only, inside the backtest loop.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

# The DuckDB path in profiles.yml is relative to the dbt working directory; this
# one is anchored to the repo instead, so the script runs from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "dev.duckdb"

WEATHER_COLUMNS = [
    "precipitation_mm",
    "dry_days",
    "temp_mean_c",
    "growing_degree_days",
    "max_dry_spell_days",
]


def current_season(panel: pd.DataFrame) -> int:
    """The newest season CONAB carries, which is always its open survey estimate.

    Read from the data rather than written down. A constant here would have gone
    stale the moment CONAB opened the next survey, and nothing would have said
    so: the weekly refresh would keep forecasting a season that had meanwhile
    been realised, and the dashboard would keep calling it "not closed yet".
    Same failure the hardcoded weather cutoff already caused once.
    """
    return int(panel["harvest_year"].max())


def load_panel(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    """One row per crop x state x season, weather raw and yield attached."""
    columns = ", ".join(WEATHER_COLUMNS)
    with duckdb.connect(str(db_path), read_only=True) as con:
        panel = con.sql(
            f"""
            select
                crop_name,
                state_code,
                harvest_year,
                days_in_window,
                {columns},
                yield_kg_ha
            from main_marts.fct_season_risk
            order by crop_name, state_code, harvest_year
            """
        ).df()

    # A state with no yield for a season cannot train or score. Weather alone is
    # still useful for forecasting the current season, so drop only where the
    # target is missing and the season is historical.
    historical = panel["harvest_year"] < current_season(panel)
    panel = panel[~(historical & panel["yield_kg_ha"].isna())].reset_index(drop=True)
    return panel


def series_key(panel: pd.DataFrame) -> pd.Series:
    """Crop x state identifies one yield series with its own trend and normals."""
    return panel["crop_name"] + " | " + panel["state_code"]
