"""NASA POWER daily weather for each producing grid cell.

One request per distinct grid cell, not per municipality: POWER serves a
~0.5 deg x 0.625 deg grid, so neighbouring hubs resolve to the same cell.
See geo.py for how the cells are derived.

Responses are cached gzipped on disk, one file per cell. Raw JSON is kept rather
than only the parsed output, so a parsing change never means re-fetching 255
cells.

The cache is keyed by cell and not by date, so a file fetched for an earlier
window is still a hit by name. Every run therefore reads the end date back out
of each file and re-fetches the ones that stop short -- see download().

That end date is today minus LAG_DAYS, so it moves every day: a cache filled
this morning is stale tomorrow, and the next local run re-fetches all 255 cells
(~3 min) for one more day of weather. Deliberate, but it does bound what the
cache is for -- it lets an interrupted run resume within the same day, not
across days. Silently loading last week's window is the failure this replaces,
and splitting the series would make the refresh cheap instead -- an immutable
history held in actions/cache, with only the current year fetched per run.
Working offline, or on parsing, is what --allow-stale is for.
"""

from __future__ import annotations

import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import duckdb
import pandas as pd

from . import RAW_DIR, STAGING_DIR, http

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

# 300 s was too forgiving: a stalled request could burn five minutes before
# anyone found out. A healthy response is ~3 s locally and ~14 s from a
# datacenter IP, so 120 s still leaves plenty of room for a slow-but-alive call.
TIMEOUT = 120
SLEEP_BETWEEN_CALLS = 0.5

# POWER throttles datacenter IPs hard: the same 255 cells that take ~13 min from
# a home connection did not finish in 59 min on a GitHub runner. Requests spend
# that time waiting, not computing, so a handful of concurrent ones recovers most
# of it. Kept deliberately low -- this is a free public API, and the point is to
# overlap waiting, not to hammer it.
MAX_WORKERS = 5


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


def _load_cached(path) -> dict | None:
    """Parsed cache file, or None when it is absent or unreadable.

    Unreadable counts as absent on purpose: a file truncated by an interrupted
    write is re-fetched here, instead of raising out of to_parquet minutes later.
    """
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, EOFError, ValueError):
        return None


def _payload_end_date(payload: dict) -> str | None:
    """Last date the payload carries, as YYYYMMDD, or None if it has no dates.

    POWER answers with exactly the window it was asked for and pads the days it
    has not published yet with the fill value -- verified against the live API on
    2026-08-07, where an end date one day back came back complete with -999 in
    the last entries. So this date is the end date the file was *requested* with,
    which is what makes comparing it to a new end date safe: a fresh fetch always
    satisfies the comparison, so the check cannot re-download every run waiting
    for data that POWER has not published.
    """
    try:
        series = payload["properties"]["parameter"]
        return max(max(dates) for dates in series.values() if dates)
    except (KeyError, TypeError, ValueError):
        return None


def fetch_cell(lat: float, lon: float, end_date: str) -> dict:
    path = _cache_path(lat, lon)
    cached = _load_cached(path)
    if cached is not None:
        # Existence alone used to be the whole check, which is how a cache built
        # for an earlier end date kept a local warehouse three days behind the
        # window the run had just printed -- silently, since every later step
        # reported the short range as if it were the requested one.
        cached_end = _payload_end_date(cached)
        if cached_end is not None and cached_end >= end_date:
            return cached

    params = {
        "parameters": PARAMETERS,
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": START_DATE,
        "end": end_date,
        "format": "JSON",
    }

    # Retry lives in http.fetch: a timeout or a 5xx here is almost always
    # transient throttling, and without a retry one blip fails the whole
    # scheduled run after the other 254 cells already succeeded.
    response = http.fetch(ENDPOINT, params=params, timeout=TIMEOUT,
                          label=f"power {lat},{lon}")
    payload = response.json()

    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh)

    time.sleep(SLEEP_BETWEEN_CALLS)
    return payload


def download(force: bool = False, allow_stale: bool = False) -> None:
    cells = grid_cells()
    end_date = (date.today() - timedelta(days=LAG_DAYS)).strftime("%Y%m%d")
    print(f"[power] {len(cells)} grid cells | {START_DATE} -> {end_date}", flush=True)

    if force:
        for path in CACHE_DIR.glob("*.json.gz"):
            path.unlink()

    # Opening all 255 files costs 8-14 s (warm/cold) against a download step
    # measured in minutes, and it is the only honest check available: the end
    # date lives inside the payload, so mtime or size would be guessing at it.
    started = time.monotonic()
    missing: list[tuple[float, float]] = []
    stale: list[tuple[tuple[float, float], str]] = []
    for lat, lon in cells:
        cached = _load_cached(_cache_path(lat, lon))
        cached_end = _payload_end_date(cached) if cached is not None else None
        if cached_end is None:
            missing.append((lat, lon))
        elif cached_end < end_date:
            stale.append(((lat, lon), cached_end))

    print(f"[power] cache read in {time.monotonic() - started:.0f}s | "
          f"{len(cells) - len(missing) - len(stale)} reach {end_date}, "
          f"{len(stale)} stale, {len(missing)} missing", flush=True)

    pending = missing + [cell for cell, _ in stale]
    if stale:
        oldest = min(cached_end for _, cached_end in stale)
        behind = (datetime.strptime(end_date, "%Y%m%d")
                  - datetime.strptime(oldest, "%Y%m%d")).days
        # Loud, because the failure it replaces was silent: the run printed the
        # window it wanted and then loaded whatever the cache happened to hold.
        print(f"[power] !! {len(stale)}/{len(cells)} cached cells end before "
              f"{end_date} -- oldest {oldest}, {behind} days behind the window",
              flush=True)
        if allow_stale:
            pending = missing
            # Deliberately says nothing about where the table ends: `oldest` is
            # the minimum over the lagging cells, which equals the table's end
            # only when every cell lags by the same amount. Pinning the table to
            # it would be the same global-versus-cell mix-up that kept the
            # original bug invisible -- the point here is that the overall range
            # cannot express this at all.
            print(f"[power] !! --allow-stale: keeping them. The table's overall "
                  f"range follows its newest cell, so this lag does not show up "
                  f"there -- and exporting from the warehouse can move app/data "
                  f"backwards against what the weekly refresh committed.",
                  flush=True)

    print(f"[power] {len(cells) - len(pending)} cached, {len(pending)} to download",
          flush=True)
    if not pending:
        return

    # Progress is printed with an elapsed rate on purpose: on a clean runner this
    # step is the long pole, and a silent hour is indistinguishable from a hang.
    started = time.monotonic()
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(fetch_cell, lat, lon, end_date): (lat, lon)
            for lat, lon in pending
        }
        for future in as_completed(futures):
            future.result()  # re-raises, so a persistent failure stops the run
            completed += 1
            if completed % 10 == 0 or completed == len(pending):
                elapsed = time.monotonic() - started
                rate = completed / elapsed * 60
                remaining = (len(pending) - completed) / rate if rate else 0
                print(f"[power] {completed}/{len(pending)} downloaded | "
                      f"{rate:.1f}/min | ~{remaining:.0f} min left", flush=True)


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

    # One range for the whole table hides a subset of cells ending early, which
    # is exactly the shape a stale cache leaves behind. download() re-fetches
    # those, but this step also runs on its own, so it says so itself.
    cell_end = daily.groupby(["grid_latitude", "grid_longitude"])["date"].max()
    behind = cell_end[cell_end < cell_end.max()]

    print(
        f"[power] {len(daily):,} rows | {len(cell_end)} cells | "
        f"{daily['date'].min():%Y-%m-%d} -> {daily['date'].max():%Y-%m-%d}"
    )
    print(f"[power] fill values (-999) replaced with null: {missing_before:,}")
    if not behind.empty:
        print(f"[power] !! {len(behind)}/{len(cell_end)} cells end before "
              f"{cell_end.max():%Y-%m-%d} -- oldest {behind.min():%Y-%m-%d}")


def run(force: bool = False, allow_stale: bool = False) -> None:
    download(force=force, allow_stale=allow_stale)
    to_parquet()


if __name__ == "__main__":
    run()
