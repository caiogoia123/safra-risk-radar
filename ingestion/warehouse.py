"""Load the staged Parquet files into the warehouse.

dbt then reads tables, never files, so the exact same models run on DuckDB and
on BigQuery. Reading Parquet straight from dbt would mean `read_parquet`, which
only exists in DuckDB and would break the prod target.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from . import DATA_DIR, STAGING_DIR

DUCKDB_PATH = DATA_DIR / "dev.duckdb"
DUCKDB_SCHEMA = "raw"
BIGQUERY_DATASET = "safra_raw"
BIGQUERY_LOCATION = "southamerica-east1"


def staged_tables() -> dict[str, Path]:
    """Every Parquet in data/staging becomes a raw table of the same name."""
    return {p.stem: p for p in sorted(STAGING_DIR.glob("*.parquet"))}


def load_duckdb(tables: dict[str, Path]) -> None:
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))
    try:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {DUCKDB_SCHEMA}")
        for name, path in tables.items():
            con.execute(
                f"CREATE OR REPLACE TABLE {DUCKDB_SCHEMA}.{name} AS "
                f"SELECT * FROM read_parquet('{path.as_posix()}')"
            )
            (rows,) = con.execute(f"SELECT count(*) FROM {DUCKDB_SCHEMA}.{name}").fetchone()
            print(f"[duckdb] {DUCKDB_SCHEMA}.{name}: {rows:,} rows")
    finally:
        con.close()


def load_bigquery(tables: dict[str, Path]) -> None:
    """Upload straight from the local file - no GCS bucket, which the sandbox lacks."""
    from google.cloud import bigquery

    keyfile = os.environ.get("GCP_KEYFILE")
    project = os.environ.get("GCP_PROJECT")
    if not keyfile or not project:
        raise SystemExit("Set GCP_KEYFILE and GCP_PROJECT to load into BigQuery.")

    client = bigquery.Client.from_service_account_json(keyfile, project=project)

    dataset = bigquery.Dataset(f"{project}.{BIGQUERY_DATASET}")
    dataset.location = BIGQUERY_LOCATION
    client.create_dataset(dataset, exists_ok=True)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    for name, path in tables.items():
        table_id = f"{project}.{BIGQUERY_DATASET}.{name}"
        with path.open("rb") as fh:
            client.load_table_from_file(fh, table_id, job_config=job_config).result()
        print(f"[bigquery] {BIGQUERY_DATASET}.{name}: {client.get_table(table_id).num_rows:,} rows")


def run(target: str = "dev") -> None:
    tables = staged_tables()
    if not tables:
        raise SystemExit("Nothing in data/staging. Run the ingestion modules first.")

    if target == "dev":
        load_duckdb(tables)
    elif target == "prod":
        load_bigquery(tables)
    else:
        raise SystemExit(f"Unknown target: {target!r} (expected 'dev' or 'prod')")
