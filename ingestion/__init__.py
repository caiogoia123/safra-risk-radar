"""Extract-load layer for Safra Risk Radar.

Each module downloads a raw file, keeps it verbatim under data/raw/ for
reproducibility, and converts it to Parquet under data/staging/ for dbt to read.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"

__all__ = ["PROJECT_ROOT", "DATA_DIR", "RAW_DIR", "STAGING_DIR"]
