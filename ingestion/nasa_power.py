"""NASA POWER daily weather for each producing grid cell.

One request per distinct grid cell, not per municipality: POWER serves a
~0.5 deg x 0.625 deg grid, so neighbouring hubs resolve to the same cell.
See geo.py for how the cells are derived.

Responses are cached gzipped on disk, one file per cell, so an interrupted run
resumes instead of re-downloading. Raw JSON is kept rather than only the parsed
output, so a parsing change never means re-fetching 255 cells.
"""

from __future__ import annotations

import gzip
import json
import time
from datetime import date, timedelta

import duckdb
import pandas as pd
import requests

from . import RAW_DIR, STAGING_DIR

HUBS_PARQUET = STAGING_DIR / "producer_hubs.parquet"
CACHE_DIR = RAW_DIR / "nasa_power"
PARQUET_FILE = STAGING_DIR / "nasa_power_daily.parquet"

ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"

# T2M/T2M_MAX/T2M_MIN feed growing degree days and hot nights, PRECTOTCORR the
# dry-spell and water-deficit features, ALLSKY_SFC_SW_DWN the radiation ones.
PARAMETERS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,ALLSKY_SFC_SW_DWN"

# 1991 so the 1991-2020 climate normal is fully covered.
START_DATE = "19910101"

# POWER publishes with a few days of lag; asking for the last week returns fill
# values at best, so the window stops short of today.
LAG_DAYS = 7

FILL_VALUE = -999.0

TIMEOUT = 300
SLEEP_BETWEEN_CALLS = 0.5


def _cache_path(lat: float, lon: float):
    return CACHE_DIR / f"{lat:+08.3f}_{lon:+09.3f}.json.gz".replace("+", "p").replace("-", "m")


def grid_cells() -> list[tuple[float, float]]:
    rows = duckdb.sql(
        f"""
        SELECT DISTINCT grid_latitude, grid_longitude
        FROM read_parquet('{HUBS_PARQUET.as_posix()}')
        ORDER BY grid_latitude, grid_longitude
        """
    ).fetchall()
    return [(float(lat), float(lon)) for lat, lon in rows]


def fetch_cell(lat: float, lon: float, end_date: str) -> dict:
    path = _cache_path(lat, lon)
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)

    response = requests.get(
        ENDPOINT,
        params={
            "parameters": PARAMETERS,
            "community": "AG",
            "latitude": lat,
            "longitude": lon,
            "start": START_DATE,
            "end": end_date,
            "format": "JSON",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh)

    time.sleep(SLEEP_BETWEEN_CALLS)
    return payload


def download(force: bool = False) -> None:
    cells = grid_cells()
    end_date = (date.today() - timedelta(days=LAG_DAYS)).strftime("%Y%m%d")
    print(f"[power] {len(cells)} grid cells | {START_DATE} -> {end_date}")

    if force:
        for path in CACHE_DIR.glob("*.json.gz"):
            path.unlink()

    fetched = 0
    for index, (lat, lon) in enumerate(cells, start=1):
        was_cached = _cache_path(lat, lon).exists()
        fetch_cell(lat, lon, end_date)
        fetched += 0 if was_cached else 1
        if index % 25 == 0 or index == len(cells):
            print(f"[power] {index}/{len(cells)} cells ({fetched} downloaded)")


def to_parquet() -> None:
    """Flatten the per-cell JSON into one long table of cell x date x measure."""
    frames = []
    for path in sorted(CACHE_DIR.glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            payload = json.load(fh)

        lon, lat, *_ = payload["geometry"]["coordinates"]
        measures = payload["properties"]["parameter"]

        frame = pd.DataFrame(measures)
        frame.index.name = "date_key"
        frame = frame.reset_index()
        frame.insert(0, "grid_latitude", lat)
        frame.insert(1, "grid_longitude", lon)
        frames.append(frame)

    if not frames:
        raise SystemExit("No cached POWER responses. Run download() first.")

    daily = pd.concat(frames, ignore_index=True)
    daily = daily.rename(
        columns={
            "T2M": "temp_mean_c",
            "T2M_MAX": "temp_max_c",
            "T2M_MIN": "temp_min_c",
            "PRECTOTCORR": "precipitation_mm",
            "ALLSKY_SFC_SW_DWN": "radiation_mj_m2",
        }
    )
    daily["date"] = pd.to_datetime(daily["date_key"], format="%Y%m%d")

    measure_columns = [
        "temp_mean_c",
        "temp_max_c",
        "temp_min_c",
        "precipitation_mm",
        "radiation_mj_m2",
    ]
    # POWER marks missing readings with -999, which would silently poison any
    # average it touches.
    missing_before = int((daily[measure_columns] == FILL_VALUE).sum().sum())
    daily[measure_columns] = daily[measure_columns].replace(FILL_VALUE, pd.NA)

    daily = daily[["grid_latitude", "grid_longitude", "date"] + measure_columns]

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    duckdb.sql(f"COPY (SELECT * FROM daily) TO '{PARQUET_FILE.as_posix()}' (FORMAT PARQUET)")

    cells = daily[["grid_latitude", "grid_longitude"]].drop_duplicates().shape[0]
    print(
        f"[power] {len(daily):,} rows | {cells} cells | "
        f"{daily['date'].min():%Y-%m-%d} -> {daily['date'].max():%Y-%m-%d}"
    )
    print(f"[power] fill values (-999) replaced with null: {missing_before:,}")


def run(force: bool = False) -> None:
    download(force=force)
    to_parquet()


if __name__ == "__main__":
    run()
