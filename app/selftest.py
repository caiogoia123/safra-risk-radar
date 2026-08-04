"""Builds every figure the dashboard shows, without Streamlit or a warehouse.

Runs in CI on each push. It catches the failure this app is actually exposed to:
the exported CSVs and the chart code drifting apart -- a renamed column breaks
the published dashboard for everyone, and nothing else in the repo would notice.

    py app/selftest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import charts as c  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"

EXPECTED_COLUMNS = {
    "season_risk": {"crop_name", "state_code", "harvest_year", "precipitation_anomaly_z",
                    "yield_residual_pct", "max_dry_spell_days"},
    "backtest": {"crop_name", "state_code", "harvest_year", "role", "predicted_pct",
                 "actual_pct", "trend_kg_ha", "yield_kg_ha"},
    "forecast": {"crop_name", "state_code", "janela_coberta_pct", "tendencia_kg_ha",
                 "desvio_previsto_pct", "previsao_kg_ha", "estimativa_conab_kg_ha"},
}


def main() -> int:
    frames = {}
    for name, required in EXPECTED_COLUMNS.items():
        path = DATA_DIR / f"{name}.csv"
        if not path.exists():
            print(f"FAIL: {path} missing -- run `py -m analysis.export_app_data`")
            return 1
        frame = pd.read_csv(path)
        missing = required - set(frame.columns)
        if missing:
            print(f"FAIL: {name}.csv is missing columns: {sorted(missing)}")
            return 1
        if frame.empty:
            print(f"FAIL: {name}.csv has no rows")
            return 1
        frames[name] = frame
        print(f"ok   {name}.csv: {len(frame)} rows")

    wide = c.widen(frames["backtest"])
    for role in ("baseline", "model"):
        if role not in wide.columns:
            print(f"FAIL: pivoting backtest lost the '{role}' column")
            return 1

    # Every crop x state pair the selectors can reach must produce a figure.
    for crop in wide["crop_name"].unique():
        for state in wide[wide["crop_name"] == crop]["state_code"].unique():
            series = wide[(wide["crop_name"] == crop) & (wide["state_code"] == state)]
            c.season_chart(series).to_dict()
    print(f"ok   season chart renders for all {wide.groupby('crop_name')['state_code'].nunique().sum()} crop/state pairs")

    c.severity_chart(c.severity_gains(wide)).to_dict()
    c.exposure_chart(c.state_exposure(frames["season_risk"])).to_dict()

    live = frames["forecast"].dropna(subset=["desvio_previsto_pct"]).copy()
    live["label"] = live["crop_name"].map(c.CROP_LABEL) + " · " + live["state_code"]
    c.forecast_chart(live).to_dict()
    print("ok   severity, exposure and forecast charts render")

    unknown = set(frames["backtest"]["crop_name"]) - set(c.CROP_LABEL)
    if unknown:
        print(f"FAIL: crops with no display label: {sorted(unknown)}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
