"""Yield trend: the technology baseline the climate signal is measured against.

The target of the whole project is the *residual* against this trend, so the
trend is not a detail -- get its shape wrong and the residual carries trend
error rather than weather. That is exactly what happens to safrinha corn under a
straight line: the crop went from 1,796 to 5,198 kg/ha as it turned from
marginal to dominant, and a line cannot follow that.

The trend is also the project's baseline forecast ("next season equals trend"),
so picking its shape by out-of-sample error is the same as picking the strongest
baseline available -- it raises the bar the climate model has to clear, it does
not lower it.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import TheilSenRegressor

# Below this many seasons a trend is fitted on noise.
MIN_TRAIN_SEASONS = 10


def _poly(years_train, yields_train, years_predict, degree):
    coeffs = np.polyfit(years_train, yields_train, degree)
    return np.polyval(coeffs, years_predict)


def _linear(years_train, yields_train, years_predict):
    return _poly(years_train, yields_train, years_predict, 1)


def _quadratic(years_train, yields_train, years_predict):
    return _poly(years_train, yields_train, years_predict, 2)


def _log_linear(years_train, yields_train, years_predict):
    """Constant growth *rate* rather than constant kg/ha per year.

    The natural shape for a crop expanding into better land and management: the
    line is fitted in log space, so a season 3% above trend is 3% above whether
    the level is 2,000 or 5,000 kg/ha.
    """
    positive = yields_train > 0
    coeffs = np.polyfit(years_train[positive], np.log(yields_train[positive]), 1)
    return np.exp(np.polyval(coeffs, years_predict))


def _linear_recent(years_train, yields_train, years_predict, window=15):
    """A line, but only over the recent past -- a cheap way to bend the curve."""
    if len(years_train) <= window:
        return _linear(years_train, yields_train, years_predict)
    cut = np.sort(years_train)[-window]
    recent = years_train >= cut
    return _linear(years_train[recent], yields_train[recent], years_predict)


def _moving_average(years_train, yields_train, years_predict, window=5):
    """Last N seasons, flat. Carries no growth, which is the point of the test."""
    order = np.argsort(years_train)
    level = float(np.mean(yields_train[order][-window:]))
    return np.full(len(np.atleast_1d(years_predict)), level)


def _theil_sen(years_train, yields_train, years_predict):
    """Robust line: a drought year should not tilt the technology trend."""
    model = TheilSenRegressor(random_state=0)
    model.fit(years_train.reshape(-1, 1), yields_train)
    return model.predict(np.atleast_1d(years_predict).reshape(-1, 1))


def _damped_linear(years_train, yields_train, years_predict, damping=0.5):
    """Recent level plus a discounted slope.

    Standard forecasting result: a full-strength trend extrapolates too
    confidently, and halving the slope beyond the data usually beats it. Here it
    also has an agronomic reading -- yield growth decelerates as a crop matures,
    and safrinha is maturing.
    """
    coeffs = np.polyfit(years_train, yields_train, 1)
    slope, _ = coeffs
    anchor_year = years_train.max()
    anchor_level = np.polyval(coeffs, anchor_year)
    return anchor_level + damping * slope * (years_predict - anchor_year)


TRENDS = {
    "linear": _linear,
    "log_linear": _log_linear,
    "quadratic": _quadratic,
    "linear_recent_15": _linear_recent,
    "linear_recent_10": lambda y, v, p: _linear_recent(y, v, p, window=10),
    "linear_recent_8": lambda y, v, p: _linear_recent(y, v, p, window=8),
    "moving_avg_3": lambda y, v, p: _moving_average(y, v, p, window=3),
    "moving_avg_5": _moving_average,
    "moving_avg_7": lambda y, v, p: _moving_average(y, v, p, window=7),
    "theil_sen": _theil_sen,
    "damped_linear": _damped_linear,
    "damped_recent_10": lambda y, v, p: _damped_linear(
        *_recent(y, v, window=10), p
    ),
}


def _recent(years_train, yields_train, window):
    """Last `window` seasons, for shapes that compose with a shorter history."""
    if len(years_train) <= window:
        return years_train, yields_train
    cut = np.sort(years_train)[-window]
    keep = years_train >= cut
    return years_train[keep], yields_train[keep]


def predict_trend(kind, years_train, yields_train, years_predict):
    """Fit `kind` on the training seasons and predict the requested seasons."""
    years_train = np.asarray(years_train, dtype=float)
    yields_train = np.asarray(yields_train, dtype=float)
    years_predict = np.asarray(np.atleast_1d(years_predict), dtype=float)
    return np.asarray(TRENDS[kind](years_train, yields_train, years_predict), dtype=float)
