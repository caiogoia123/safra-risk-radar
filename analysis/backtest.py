"""Does critical-window weather beat the trend at forecasting yield?

Walk-forward: everything is refitted on seasons strictly before the test season
-- the yield trend, the climate normals the anomalies are measured against, and
the model itself. Nothing about season T is available when T is predicted.

The bar is the project's baseline: "next season equals trend". Beating it is the
whole claim; not beating it is a publishable result, and gets published.

    py -m analysis.backtest         (from the repo root)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

from analysis.dataset import WEATHER_COLUMNS, current_season, load_panel
from analysis.trend import MIN_TRAIN_SEASONS, predict_trend

# Both crops end up on a straight line, and for safrinha that is not what the
# trend comparison alone said.
#
# Judged as a forecast on its own, moving_avg_3 is the better safrinha trend
# (28.6% error against 31.8% for the line). But it makes a worse *target*: a
# moving average already absorbs recent weather, so the residual against it
# carries mean reversion instead of climate, and every climate model trained on
# it lands ~50% worse than its own baseline. On the line, the same models beat
# their baseline. End to end -- which is what counts -- line plus climate model
# (26.5% error) beats moving average alone (28.6%).
#
# Caveat, stated rather than hidden: this pairing was picked by looking at
# backtest results, so the numbers below are optimistic by an unknown margin.
# The honest test is the next unseen season.
TREND_BY_CROP = {
    "SOJA": "linear",
    "MILHO 2A SAFRA": "linear",
}

# The dry spell is deliberately absent: it correlates 0.73 with dry_days and its
# partial correlation with the residual is +0.05 -- the negative result the
# README writes up under "What did not work".
FEATURES = [c for c in WEATHER_COLUMNS if c != "max_dry_spell_days"]

FIRST_TEST_SEASON = 2003


def _standardise(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]):
    """Z-score each feature against its own state's normal, from training only.

    Rain of 100 mm is ordinary in Rio Grande do Sul and a drought in Mato
    Grosso, so features only compare across states once they are expressed as
    distance from that state's own normal.
    """
    train_z, test_z = train.copy(), test.copy()
    for (crop, state), group in train.groupby(["crop_name", "state_code"]):
        mask_train = (train["crop_name"] == crop) & (train["state_code"] == state)
        mask_test = (test["crop_name"] == crop) & (test["state_code"] == state)
        for column in columns:
            mean, sd = group[column].mean(), group[column].std()
            sd = sd if sd and sd > 0 else 1.0
            train_z.loc[mask_train, column] = (train.loc[mask_train, column] - mean) / sd
            test_z.loc[mask_test, column] = (test.loc[mask_test, column] - mean) / sd
    return train_z, test_z


def build_fold(
    panel: pd.DataFrame,
    crop: str,
    test_season: int,
    trend_kind: str,
    require_test_target: bool = True,
):
    """Training and test frames for one season, with the target detrended."""
    crop_panel = panel[panel["crop_name"] == crop]
    train = crop_panel[crop_panel["harvest_year"] < test_season].copy()
    test = crop_panel[crop_panel["harvest_year"] == test_season].copy()
    if test.empty:
        return None

    keep_states = []
    for state, group in train.groupby("state_code"):
        if len(group) >= MIN_TRAIN_SEASONS:
            keep_states.append(state)
    train = train[train["state_code"].isin(keep_states)]
    test = test[test["state_code"].isin(keep_states)]
    if train.empty or test.empty:
        return None

    # Trend fitted on training seasons only, then applied to both sides.
    for frame in (train, test):
        frame["trend_kg_ha"] = np.nan
    for state in keep_states:
        history = train[train["state_code"] == state].sort_values("harvest_year")
        years = history["harvest_year"].to_numpy(float)
        yields = history["yield_kg_ha"].to_numpy(float)

        train_mask = train["state_code"] == state
        train.loc[train_mask, "trend_kg_ha"] = predict_trend(
            trend_kind, years, yields, train.loc[train_mask, "harvest_year"].to_numpy(float)
        )
        test_mask = test["state_code"] == state
        if test_mask.any():
            test.loc[test_mask, "trend_kg_ha"] = predict_trend(
                trend_kind, years, yields, test.loc[test_mask, "harvest_year"].to_numpy(float)
            )

    for frame in (train, test):
        frame["target_pct"] = (
            (frame["yield_kg_ha"] - frame["trend_kg_ha"]) / frame["trend_kg_ha"] * 100
        )

    train = train.dropna(subset=["target_pct"] + FEATURES)
    # Forecasting the current season is the one case with no target to drop: the
    # weather is measured, the yield is what is being asked for.
    test = test.dropna(subset=(["target_pct"] if require_test_target else []) + FEATURES)
    if train.empty or test.empty:
        return None

    return _standardise(train, test, FEATURES)


def _design(frame: pd.DataFrame, states: list[str], interactions: bool):
    """Feature matrix; optionally one slope per state.

    Exposure is very uneven -- soybean residuals track rainfall at +0.50 in Rio
    Grande do Sul and +0.13 in Mato Grosso -- so a single pooled slope is an
    average of genuinely different states. Interactions let each state have its
    own, at the cost of many more parameters on a short panel.
    """
    base = frame[FEATURES].to_numpy(float)
    if not interactions:
        return base
    dummies = np.column_stack(
        [(frame["state_code"] == state).to_numpy(float) for state in states]
    )
    crossed = np.column_stack(
        [base * dummies[:, [i]] for i in range(dummies.shape[1])]
    )
    return np.column_stack([base, dummies, crossed])


def _fit_predict(name: str, train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    states = sorted(train["state_code"].unique())

    if name == "baseline_trend":
        # "The season equals the trend": residual zero, by definition.
        return np.zeros(len(test))

    if name == "ridge_pooled":
        model = Ridge(alpha=1.0)
        model.fit(_design(train, states, False), train["target_pct"])
        return model.predict(_design(test, states, False))

    if name == "ridge_by_state":
        model = Ridge(alpha=10.0)
        model.fit(_design(train, states, True), train["target_pct"])
        return model.predict(_design(test, states, True))

    if name == "ridge_per_state":
        predictions = np.zeros(len(test))
        for i, (_, row) in enumerate(test.iterrows()):
            history = train[train["state_code"] == row["state_code"]]
            model = Ridge(alpha=1.0)
            model.fit(history[FEATURES].to_numpy(float), history["target_pct"])
            predictions[i] = model.predict(row[FEATURES].to_numpy(float).reshape(1, -1))[0]
        return predictions

    if name == "random_forest":
        model = RandomForestRegressor(n_estimators=300, min_samples_leaf=3, random_state=0)
        model.fit(_design(train, states, False), train["target_pct"])
        return model.predict(_design(test, states, False))

    raise ValueError(name)


MODELS = [
    "baseline_trend",
    "ridge_pooled",
    "ridge_by_state",
    "ridge_per_state",
    "random_forest",
]


def run_backtest(panel: pd.DataFrame, trend_by_crop: dict | None = None) -> pd.DataFrame:
    rows = []
    # The newest season is CONAB's open survey, not a realised harvest, so it is
    # forecast rather than scored -- range() excluding the endpoint is the point.
    for crop, trend_kind in (trend_by_crop or TREND_BY_CROP).items():
        for season in range(FIRST_TEST_SEASON, current_season(panel)):
            fold = build_fold(panel, crop, season, trend_kind)
            if fold is None:
                continue
            train, test = fold
            for model_name in MODELS:
                predicted = _fit_predict(model_name, train, test)
                for i, (_, row) in enumerate(test.iterrows()):
                    rows.append(
                        {
                            "crop_name": crop,
                            "state_code": row["state_code"],
                            "harvest_year": season,
                            "model": model_name,
                            "predicted_pct": predicted[i],
                            "actual_pct": row["target_pct"],
                            "trend_kg_ha": row["trend_kg_ha"],
                            "yield_kg_ha": row["yield_kg_ha"],
                        }
                    )
    return pd.DataFrame(rows)


def score(results: pd.DataFrame, by=("crop_name", "model")) -> pd.DataFrame:
    """Error in the residual, plus what it means for the yield forecast itself."""
    out = []
    for keys, group in results.groupby(list(by)):
        error = group["predicted_pct"] - group["actual_pct"]
        predicted_yield = group["trend_kg_ha"] * (1 + group["predicted_pct"] / 100)
        yield_error_pct = (predicted_yield - group["yield_kg_ha"]) / group["yield_kg_ha"] * 100
        # Did it at least get the sign right -- above or below trend?
        called = np.sign(group["predicted_pct"]) == np.sign(group["actual_pct"])
        out.append(
            dict(
                zip(by, keys if isinstance(keys, tuple) else (keys,)),
                n=len(group),
                RMSE_resid=np.sqrt((error**2).mean()),
                MAE_resid=error.abs().mean(),
                RMSE_yield_pct=np.sqrt((yield_error_pct**2).mean()),
                acerto_direcao=called.mean() * 100,
            )
        )
    frame = pd.DataFrame(out)
    baseline = frame[frame["model"] == "baseline_trend"].set_index(list(by[:-1]))["RMSE_resid"]
    frame["skill_vs_baseline_pct"] = frame.apply(
        lambda r: (1 - r["RMSE_resid"] / baseline.loc[r[by[0]]]) * 100, axis=1
    )
    return frame.sort_values(list(by[:-1]) + ["RMSE_resid"])


SEVERITY_BINS = [-100, -20, -10, 10, 20, 100]
SEVERITY_LABELS = ["quebra <-20%", "-20 a -10%", "normal +-10%", "+10 a +20%", "boa >+20%"]


def score_by_severity(results: pd.DataFrame, model: str) -> pd.DataFrame:
    """Where does the model actually earn its keep?

    A single RMSE hides the answer, because two thirds of the seasons are
    ordinary ones where there is nothing to predict and the trend is already
    right. Splitting by how far the season really fell tells a different story
    from the average -- and it is the story the use case cares about.
    """
    wide = results.pivot_table(
        index=["crop_name", "state_code", "harvest_year", "actual_pct"],
        columns="model",
        values="predicted_pct",
    ).reset_index()
    wide["faixa"] = pd.cut(wide["actual_pct"], SEVERITY_BINS, labels=SEVERITY_LABELS)

    rows = []
    for (crop, faixa), group in wide.groupby(["crop_name", "faixa"], observed=True):
        baseline_error = group["baseline_trend"] - group["actual_pct"]
        model_error = group[model[crop]] - group["actual_pct"]
        rmse_baseline = np.sqrt((baseline_error**2).mean())
        rmse_model = np.sqrt((model_error**2).mean())
        rows.append(
            {
                "crop_name": crop,
                "faixa": faixa,
                "n": len(group),
                "RMSE_baseline": rmse_baseline,
                "RMSE_modelo": rmse_model,
                "ganho_pct": (1 - rmse_model / rmse_baseline) * 100,
            }
        )
    return pd.DataFrame(rows)


def detection_rate(results: pd.DataFrame, model: str, threshold: float = -10.0) -> pd.DataFrame:
    """Of the seasons that really broke, how many did the model call in advance?

    The trend baseline scores zero here by construction -- it never predicts a
    break at all -- which is exactly why RMSE alone undersells the model.
    """
    wide = results.pivot_table(
        index=["crop_name", "state_code", "harvest_year", "actual_pct"],
        columns="model",
        values="predicted_pct",
    ).reset_index()

    rows = []
    for crop, group in wide.groupby("crop_name"):
        broke = group["actual_pct"] <= threshold
        called = group[model[crop]] <= threshold
        rows.append(
            {
                "crop_name": crop,
                "quebras_reais": int(broke.sum()),
                "quebras_previstas": int(called.sum()),
                "acertos": int((broke & called).sum()),
                "recall_pct": (broke & called).sum() / max(broke.sum(), 1) * 100,
                "precisao_pct": (broke & called).sum() / max(called.sum(), 1) * 100,
                "falsos_alarmes": int((~broke & called).sum()),
            }
        )
    return pd.DataFrame(rows)


# One model per crop, and the reason is structural rather than a leaderboard
# pick: soybean spans seven states whose exposure genuinely differs (residuals
# track rainfall at +0.50 in RS against +0.13 in MT), so per-state slopes earn
# their parameters; safrinha has fewer seasons per state, where pooling is the
# steadier choice. The gap between the two on either crop is small.
BEST_MODEL_BY_CROP = {
    "SOJA": "ridge_by_state",
    "MILHO 2A SAFRA": "ridge_pooled",
}


def forecast_season(panel: pd.DataFrame, season: int | None = None) -> pd.DataFrame:
    """Train on everything realised, then forecast a season CONAB has not closed.

    This is the actual use case: the weather already happened and is measured,
    the official yield has not been published. The CONAB column alongside is
    their current survey estimate -- a reference point, not ground truth.
    """
    season = current_season(panel) if season is None else season

    # How much of each critical window the weather series actually covers. Below
    # this, the window is truncated rather than dry, and the model reads the
    # missing month as a drought: forecasting safrinha 2026 for Parana with 119
    # of 153 days produced +99%, roughly double any yield ever recorded there.
    MIN_WINDOW_COVERAGE = 0.95
    normal_window = (
        panel[panel["harvest_year"].between(season - 11, season - 1)]
        .groupby(["crop_name", "state_code"])["days_in_window"]
        .median()
    )

    rows = []
    for crop, trend_kind in TREND_BY_CROP.items():
        fold = build_fold(panel, crop, season, trend_kind, require_test_target=False)
        if fold is None:
            continue
        train, test = fold
        predicted = _fit_predict(BEST_MODEL_BY_CROP[crop], train, test)
        for i, (_, row) in enumerate(test.iterrows()):
            coverage = row["days_in_window"] / normal_window.loc[(crop, row["state_code"])]
            complete = coverage >= MIN_WINDOW_COVERAGE
            rows.append(
                {
                    "crop_name": crop,
                    "state_code": row["state_code"],
                    "janela_coberta_pct": coverage * 100,
                    "tendencia_kg_ha": row["trend_kg_ha"],
                    "desvio_previsto_pct": predicted[i] if complete else np.nan,
                    "previsao_kg_ha": (
                        row["trend_kg_ha"] * (1 + predicted[i] / 100) if complete else np.nan
                    ),
                    "estimativa_conab_kg_ha": row["yield_kg_ha"],
                }
            )
    frame = pd.DataFrame(rows)
    frame["dif_vs_conab_pct"] = (
        (frame["previsao_kg_ha"] - frame["estimativa_conab_kg_ha"])
        / frame["estimativa_conab_kg_ha"]
        * 100
    )
    return frame.sort_values(["crop_name", "desvio_previsto_pct"])


def main() -> None:
    pd.set_option("display.width", 140)
    pd.set_option("display.float_format", lambda v: f"{v:8.2f}")

    panel = load_panel()
    results = run_backtest(panel)
    last_scored = current_season(panel) - 1

    print(f"Backtest walk-forward {FIRST_TEST_SEASON}-{last_scored} "
          "(tendencia, normais e modelo so com treino)")
    print("skill positivo = melhor que o baseline; acerto_direcao = acima/abaixo da tendencia\n")
    print(score(results).to_string(index=False))

    print("\n\nOnde o modelo ganha, por severidade da safra\n")
    print(score_by_severity(results, BEST_MODEL_BY_CROP).to_string(index=False))

    print("\n\nDeteccao de quebra (safra 10%% ou mais abaixo da tendencia)")
    print("o baseline detecta ZERO por construcao -- ele nunca preve quebra\n")
    print(detection_rate(results, BEST_MODEL_BY_CROP).to_string(index=False))

    print("\n\nPor UF (soja): RMSE do residuo por modelo\n")
    soja = results[results["crop_name"] == "SOJA"]
    print(
        score(soja, by=("state_code", "model"))
        .pivot(index="state_code", columns="model", values="RMSE_resid")
        .to_string()
    )

    print(f"\n\nAplicacao: safra {current_season(panel)}, que a CONAB ainda nao fechou\n")
    print(forecast_season(panel).to_string(index=False))


if __name__ == "__main__":
    main()
