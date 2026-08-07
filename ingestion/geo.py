"""Pick the producing hubs of each state and resolve a weather sampling point.

Sampling weather at a state centroid is wrong: Mato Grosso's centroid sits in
forest, Bahia's in unirrigated scrubland. This module ranks municipalities by
grain production and keeps the ones that carry the bulk of it.

Two facts make this cheap:
  * NASA POWER serves a ~0.5 deg x 0.625 deg grid (roughly 55 km), which is
    larger than a typical municipality (~40 km across). So the exact centroid
    inside the municipality does not matter - the bounding box centre lands in
    the same grid cell as any fancier centroid would.
  * For the same reason neighbouring municipalities collapse onto one grid
    cell, so the number of weather requests is far below the number of hubs.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb
import pandas as pd

from . import STAGING_DIR, http

PAM_PARQUET = STAGING_DIR / "ibge_pam_municipal.parquet"
PARQUET_FILE = STAGING_DIR / "producer_hubs.parquet"

# Versioned input, not a throwaway cache -- it lives beside the code rather than
# under the gitignored data/.
#
# Municipal boundaries are redrawn every few years, so re-deriving these from the
# IBGE mesh API on every run fetched 510 outlines to compute 16 KB of numbers
# that had not moved. On a CI runner it was also the least reliable thing in the
# pipeline: IBGE throttles datacenter IPs progressively -- the fetch rate decayed
# 124 -> 75 -> 53 -> under 5 per minute across one run, and it eventually stopped
# accepting connections altogether, failing the job after every retry.
#
# Same treatment as the CONAB planting calendar: derived once from the official
# source, committed, and regenerated deliberately.
#
#     py -c "from ingestion import geo; geo.run(force=True)"
#
# Run that when IBGE publishes a new mesh edition, or when the hub ranking picks
# up municipalities this file does not cover, and commit the result.
CENTROID_CACHE = Path(__file__).parent / "reference" / "centroids.json"

# Keep adding municipalities, biggest first, until this share of the state's
# production is covered.
PRODUCTION_COVERAGE = 0.80

# Safeguard against a pathological state, not a selection criterion. It has to
# sit above the real requirement: production is concentrated in Bahia (6
# municipalities reach 80%) and pulverised in Parana (165 for the same 80%).
# A tighter cap silently under-samples the South, where climate varies most.
MAX_HUBS_PER_STATE = 250

# NASA POWER native grid (MERRA-2).
GRID_LAT = 0.5
GRID_LON = 0.625

TIMEOUT = 90
SLEEP_BETWEEN_CALLS = 0.3

# Same reasoning as ingestion/nasa_power.py: the requests are fast (~0.4 s here)
# but there are 510 of them, and a CI runner is throttled enough that doing them
# one at a time dominated the whole workflow.
MAX_WORKERS = 5


def rank_hubs() -> list[dict]:
    """Rank municipalities by mean annual grain production within each state.

    Soybean and corn are summed: the safrinha corn is planted on the same land
    right after the soybean, so both share a producing belt.
    """
    return duckdb.sql(
        f"""
        with by_municipality as (
            select
                municipality_id,
                any_value(municipality_name) as municipality_name,
                state_code,
                sum(coalesce(production_t, 0)) / count(distinct year) as mean_production_t
            from read_parquet('{PAM_PARQUET.as_posix()}')
            group by municipality_id, state_code
            having sum(coalesce(production_t, 0)) > 0
        ),

        ranked as (
            select
                *,
                row_number() over (
                    partition by state_code order by mean_production_t desc
                ) as rank_in_state,
                sum(mean_production_t) over (
                    partition by state_code
                    order by mean_production_t desc
                    rows between unbounded preceding and current row
                ) as running_production_t,
                sum(mean_production_t) over (partition by state_code) as state_production_t
            from by_municipality
        ),

        shares as (
            select
                *,
                running_production_t / state_production_t as cumulative_share,
                -- Share reached *before* this row, so the municipality that
                -- crosses the threshold is kept rather than dropped.
                (running_production_t - mean_production_t) / state_production_t
                    as share_before
            from ranked
        )

        select municipality_id, municipality_name, state_code,
               mean_production_t, rank_in_state, cumulative_share
        from shares
        where share_before < {PRODUCTION_COVERAGE}
          and rank_in_state <= {MAX_HUBS_PER_STATE}
        order by state_code, rank_in_state
        """
    ).df().to_dict("records")


def _load_cache() -> dict[str, list[float]]:
    if CENTROID_CACHE.exists():
        return json.loads(CENTROID_CACHE.read_text(encoding="utf-8"))
    return {}


def fetch_centroid(municipality_id: int) -> tuple[float, float]:
    """Bounding-box centre of the municipality outline, in (lat, lon).

    Pure fetch: the caller owns the cache. That keeps the dict writes on one
    thread while the 510 requests overlap.
    """
    url = (
        f"https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{municipality_id}"
        "?formato=application/vnd.geo+json"
    )
    # A bad parameter returns a 400 with a JSON body that has no 'features',
    # which is exactly how this broke the first time around -- so http.fetch
    # raises 4xx immediately instead of retrying it into a slower failure.
    response = http.fetch(url, timeout=TIMEOUT, label=f"malha {municipality_id}")
    payload = response.json()
    if "features" not in payload:
        raise ValueError(f"unexpected payload for {municipality_id}: {list(payload)}")

    points: list[list[float]] = []

    def flatten(node) -> None:
        if isinstance(node, list) and node and isinstance(node[0], (int, float)):
            points.append(node)
        elif isinstance(node, list):
            for child in node:
                flatten(child)

    flatten(payload["features"][0]["geometry"]["coordinates"])

    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    centroid = (
        round((min(lats) + max(lats)) / 2, 4),
        round((min(lons) + max(lons)) / 2, 4),
    )
    time.sleep(SLEEP_BETWEEN_CALLS)
    return centroid


def run(force: bool = False) -> None:
    hubs = rank_hubs()
    print(f"[geo] {len(hubs)} producing hubs selected", flush=True)

    cache = {} if force else _load_cache()
    cached_at_start = len(cache)

    missing = [
        int(hub["municipality_id"])
        for hub in hubs
        if str(hub["municipality_id"]) not in cache
    ]
    if not missing:
        print(f"[geo] {len(hubs)} centroids from {CENTROID_CACHE.name}, no request needed",
              flush=True)
    if missing:
        # Reaching here in CI means the hub ranking moved and the committed file
        # no longer covers it. Say so plainly: the fix is to regenerate and
        # commit, not to hope IBGE answers from a datacenter IP.
        print(f"[geo] {len(hubs) - len(missing)} from {CENTROID_CACHE.name}, "
              f"{len(missing)} missing -- fetching from IBGE", flush=True)
        if not force:
            print("[geo] if this is CI, commit the regenerated centroids instead: "
                  "py -c \"from ingestion import geo; geo.run(force=True)\"", flush=True)
        started = time.monotonic()
        completed = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(fetch_centroid, mid): mid for mid in missing}
            for future in as_completed(futures):
                # Only this thread touches the cache.
                cache[str(futures[future])] = list(future.result())
                completed += 1
                if completed % 50 == 0 or completed == len(missing):
                    rate = completed / (time.monotonic() - started) * 60
                    print(f"[geo] {completed}/{len(missing)} fetched | {rate:.0f}/min",
                          flush=True)

    for hub in hubs:
        lat, lon = cache[str(hub["municipality_id"])]
        hub["latitude"] = lat
        hub["longitude"] = lon
        # Snap to the POWER grid so neighbouring hubs share one weather request.
        hub["grid_latitude"] = round(round(lat / GRID_LAT) * GRID_LAT, 4)
        hub["grid_longitude"] = round(round(lon / GRID_LON) * GRID_LON, 4)

    # Only rewrite when something was actually fetched, and write it sorted:
    # this file is committed, so an unnecessary rewrite is a spurious diff, and
    # concurrent completion order would otherwise shuffle the keys every run.
    if len(cache) != cached_at_start or force:
        CENTROID_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CENTROID_CACHE.write_text(
            json.dumps(dict(sorted(cache.items())), indent=0, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[geo] centroids: {cached_at_start} known, "
              f"{len(cache) - cached_at_start} fetched -- {CENTROID_CACHE.name} updated, "
              "commit it", flush=True)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # DuckDB resolves `hubs_df` from the enclosing Python scope.
    hubs_df = pd.DataFrame(hubs)  # noqa: F841 - referenced inside the SQL below
    duckdb.sql(f"COPY (SELECT * FROM hubs_df) TO '{PARQUET_FILE.as_posix()}' (FORMAT PARQUET)")

    cells = duckdb.sql(
        f"SELECT count(DISTINCT (grid_latitude, grid_longitude)) "
        f"FROM read_parquet('{PARQUET_FILE.as_posix()}')"
    ).fetchone()[0]
    print(f"[geo] {len(hubs)} hubs collapse into {cells} POWER grid cells")


if __name__ == "__main__":
    run()
