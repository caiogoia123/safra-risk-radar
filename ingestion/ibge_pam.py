"""IBGE PAM (SIDRA table 1612): municipal crop production.

Used to locate where each state's production actually sits, so weather is
sampled over the producing belt instead of the geographic centre of the state.

Extract and load only: every municipality of the target states comes through,
including zero-production ones. Selecting the producing hubs is a later step.
"""

from __future__ import annotations

import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb

from . import RAW_DIR, STAGING_DIR, http

# IBGE state codes for the states covered by the v1 scope.
TARGET_STATES = {
    29: "BA",
    31: "MG",
    41: "PR",
    43: "RS",
    50: "MS",
    51: "MT",
    52: "GO",
}

# Classification 81 (temporary crops).
CROPS = {2713: "SOJA", 2711: "MILHO"}

# PAM is annual and lags; 2024 is the latest closed year.
YEARS = "2020-2024"

VARIABLE_PRODUCTION = 214  # quantity produced, tonnes

RAW_FILE = RAW_DIR / "ibge" / "pam_municipal.json"
PARQUET_FILE = STAGING_DIR / "ibge_pam_municipal.parquet"

# Committed extract, beside the code rather than under the gitignored data/.
# See run() for why.
REFERENCE_PARQUET = Path(__file__).parent / "reference" / "pam_municipal.parquet"

TIMEOUT = 180
# SIDRA has no published rate limit; this keeps the loop polite.
SLEEP_BETWEEN_CALLS = 0.5
MAX_WORKERS = 5


def _fetch(state_code: int, crop_id: int) -> list[dict]:
    url = (
        f"https://apisidra.ibge.gov.br/values/t/1612"
        f"/n6/in%20n3%20{state_code}"
        f"/v/{VARIABLE_PRODUCTION}"
        f"/p/{YEARS}"
        f"/c81/{crop_id}"
    )
    response = http.fetch(url, timeout=TIMEOUT, label=f"sidra {state_code}/{crop_id}")
    payload = response.json()
    time.sleep(SLEEP_BETWEEN_CALLS)
    # First element is a header row describing the columns, not data.
    return payload[1:]


def download(force: bool = False) -> None:
    import json

    if RAW_FILE.exists() and not force:
        print(f"[pam] cached: {RAW_FILE.name}")
        return

    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    # Fourteen requests (7 states x 2 crops), concurrent for the same reason as
    # the other sources: each took ~20 s from the CI runner, and one at a time
    # that was five minutes of pure waiting.
    requested = [
        (state_code, state_uf, crop_id, crop_name)
        for state_code, state_uf in TARGET_STATES.items()
        for crop_id, crop_name in CROPS.items()
    ]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_fetch, state_code, crop_id): (state_uf, crop_name)
            for state_code, state_uf, crop_id, crop_name in requested
        }
        for future in as_completed(futures):
            state_uf, crop_name = futures[future]
            fetched = future.result()
            for row in fetched:
                rows.append(
                    {
                        "municipality_id": row["D1C"],
                        "municipality_name": row["D1N"],
                        "state_code": state_uf,
                        "crop_name": crop_name,
                        "year": row["D3N"],
                        # SIDRA uses '...' for unavailable and '-' for zero.
                        "production_t": row["V"] if row["V"] not in ("...", "-", "X") else None,
                    }
                )
            print(f"[pam] {state_uf} {crop_name}: {len(fetched):,} rows", flush=True)

    # Concurrency makes completion order arbitrary; sorting keeps the raw file
    # byte-identical between runs, so a re-run shows no spurious diff.
    rows.sort(key=lambda r: (r["state_code"], r["crop_name"], r["municipality_id"], r["year"]))

    RAW_FILE.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"[pam] saved {len(rows):,} rows")


def to_parquet() -> None:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    duckdb.sql(
        f"""
        COPY (
            SELECT
                CAST(municipality_id AS BIGINT)   AS municipality_id,
                municipality_name,
                state_code,
                crop_name,
                CAST(year AS INT)                 AS year,
                CAST(production_t AS DOUBLE)      AS production_t
            FROM read_json('{RAW_FILE.as_posix()}')
        ) TO '{PARQUET_FILE.as_posix()}' (FORMAT PARQUET)
        """
    )
    rows, munis = duckdb.sql(
        f"SELECT count(*), count(DISTINCT municipality_id) "
        f"FROM read_parquet('{PARQUET_FILE.as_posix()}')"
    ).fetchone()
    print(f"[pam] {rows:,} rows | {munis:,} municipalities")


def run(force: bool = False) -> None:
    """Use the committed extract unless explicitly refreshing.

    Same reasoning as the municipal centroids in geo.py, and the same trigger:
    IBGE refuses connections from datacenter IPs, and a scheduled run died with
    all 14 SIDRA requests timing out on every retry.

    Refusing is not even the main argument -- the data does not move. YEARS is
    pinned to 2020-2024, PAM is annual and those years are closed, so every run
    re-downloaded 3.9 MB of JSON to rebuild a byte-identical 100 KB table. What
    is committed is the parquet, not the raw JSON: same content, a fortieth of
    the size, and it is what the warehouse actually loads.

    Refresh deliberately, when YEARS changes or IBGE publishes a revision:

        py -c "from ingestion import ibge_pam; ibge_pam.run(force=True)"
    """
    if REFERENCE_PARQUET.exists() and not force:
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REFERENCE_PARQUET, PARQUET_FILE)
        rows, munis = duckdb.sql(
            f"SELECT count(*), count(DISTINCT municipality_id) "
            f"FROM read_parquet('{PARQUET_FILE.as_posix()}')"
        ).fetchone()
        print(f"[pam] {rows:,} rows | {munis:,} municipalities "
              f"from {REFERENCE_PARQUET.name}, no request needed", flush=True)
        return

    download(force=force)
    to_parquet()

    REFERENCE_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PARQUET_FILE, REFERENCE_PARQUET)
    print(f"[pam] {REFERENCE_PARQUET.name} updated, commit it", flush=True)


if __name__ == "__main__":
    run()
