"""Which trend shape forecasts next season's yield best, out of sample?

Answers the open question left in PROJETO.md ("linear detrend does not work for
safrinha"), by measurement rather than by argument: every shape is refitted on
seasons before T and scored on T, walking forward one season at a time.

    py -m analysis.compare_detrend        (from the repo root)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.dataset import CURRENT_SEASON, load_panel, series_key
from analysis.trend import MIN_TRAIN_SEASONS, TRENDS, predict_trend


def walk_forward_trend_errors(panel: pd.DataFrame) -> pd.DataFrame:
    """Percent error of each trend shape, one row per series x season x shape."""
    rows = []
    panel = panel[panel["harvest_year"] < CURRENT_SEASON]

    for (crop, state), series in panel.groupby(["crop_name", "state_code"]):
        series = series.sort_values("harvest_year")
        years = series["harvest_year"].to_numpy(float)
        yields = series["yield_kg_ha"].to_numpy(float)

        for i in range(MIN_TRAIN_SEASONS, len(series)):
            train_years, train_yields = years[:i], yields[:i]
            actual = yields[i]
            if actual <= 0:
                continue
            for kind in TRENDS:
                predicted = predict_trend(kind, train_years, train_yields, years[i])[0]
                rows.append(
                    {
                        "crop_name": crop,
                        "state_code": state,
                        "harvest_year": int(years[i]),
                        "trend": kind,
                        "error_pct": (predicted - actual) / actual * 100,
                    }
                )

    return pd.DataFrame(rows)


def summarise(errors: pd.DataFrame, by=("crop_name", "trend")) -> pd.DataFrame:
    grouped = errors.groupby(list(by))["error_pct"]
    summary = pd.DataFrame(
        {
            "n": grouped.size(),
            "MAE_pct": grouped.apply(lambda e: e.abs().mean()),
            "RMSE_pct": grouped.apply(lambda e: np.sqrt((e**2).mean())),
            "vies_pct": grouped.mean(),
        }
    )
    return summary.sort_values(list(by[:-1]) + ["RMSE_pct"])


def main() -> None:
    panel = load_panel()
    errors = walk_forward_trend_errors(panel)

    pd.set_option("display.width", 120)
    pd.set_option("display.float_format", lambda v: f"{v:8.2f}")

    print("Erro out-of-sample da tendencia (previsao = tendencia), por cultura")
    print("MAE/RMSE em % da produtividade real; vies negativo = subestima a safra\n")
    print(summarise(errors).to_string())

    print("\n\nSo 2010 em diante (a safrinha mudou de regime antes disso)\n")
    print(summarise(errors[errors["harvest_year"] >= 2010]).to_string())

    print("\n\nSafrinha por UF, as tres formas principais\n")
    safrinha = errors[
        (errors["crop_name"] == "MILHO 2A SAFRA")
        & (errors["trend"].isin(["linear", "log_linear", "linear_recent_15"]))
    ]
    print(summarise(safrinha, by=("state_code", "trend")).to_string())


if __name__ == "__main__":
    main()
