"""CONAB grain series: planted area, production and yield by state and crop season.

Source: https://portaldeinformacoes.conab.gov.br (semicolon-separated, latin-1,
fixed-width padding inside the text fields). Series starts at 1976/77.

This module only extracts and loads. No filtering or business logic here -- that
belongs in dbt, so the raw grain of the source stays auditable.
"""

from __future__ import annotations

import duckdb

from . import RAW_DIR, STAGING_DIR, http

SOURCE_URL = "https://portaldeinformacoes.conab.gov.br/downloads/arquivos/SerieHistoricaGraos.txt"
RAW_FILE = RAW_DIR / "conab" / "serie_historica_graos.txt"
PARQUET_FILE = STAGING_DIR / "conab_grain_series.parquet"

TIMEOUT = 120


def download(force: bool = False) -> None:
    """Fetch the raw file verbatim. Skips if already present unless force=True."""
    if RAW_FILE.exists() and not force:
        print(f"[conab] cached: {RAW_FILE.relative_to(RAW_DIR.parent.parent)}")
        return

    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    print(f"[conab] downloading {SOURCE_URL}", flush=True)
    response = http.fetch(SOURCE_URL, timeout=TIMEOUT, label="conab series")
    RAW_FILE.write_bytes(response.content)
    print(f"[conab] saved {len(response.content):,} bytes")


def to_parquet() -> None:
    """Convert the raw text into typed Parquet, trimming the padded text fields."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # DuckDB reads the latin-1 CSV and writes Parquet without needing pyarrow.
    duckdb.sql(
        f"""
        COPY (
            SELECT
                trim(ano_agricola)                  AS crop_year,
                trim(dsc_safra_previsao)            AS season_label,
                trim(uf)                            AS state_code,
                trim(produto)                       AS crop_name,
                id_produto                          AS crop_id,
                area_plantada_mil_ha                AS planted_area_kha,
                producao_mil_t                      AS production_kt,
                produtividade_mil_ha_mil_t          AS yield_source_t_ha
            FROM read_csv(
                '{RAW_FILE.as_posix()}',
                delim = ';',
                header = true,
                encoding = 'latin-1',
                types = {{
                    'area_plantada_mil_ha': 'DOUBLE',
                    'producao_mil_t': 'DOUBLE',
                    'produtividade_mil_ha_mil_t': 'DOUBLE'
                }}
            )
        ) TO '{PARQUET_FILE.as_posix()}' (FORMAT PARQUET)
        """
    )

    rows, crops, seasons, first, last = duckdb.sql(
        f"""
        SELECT count(*), count(DISTINCT crop_name), count(DISTINCT season_label),
               min(crop_year), max(crop_year)
        FROM read_parquet('{PARQUET_FILE.as_posix()}')
        """
    ).fetchone()
    print(
        f"[conab] {rows:,} rows | {crops} crops | {seasons} season labels | "
        f"{first} -> {last}"
    )


def run(force: bool = False) -> None:
    download(force=force)
    to_parquet()


if __name__ == "__main__":
    run()
