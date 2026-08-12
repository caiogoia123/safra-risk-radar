"""Asserts that every number the READMEs quote about the data still matches the data.

The app already refuses to state a fact it did not read from the exported CSVs.
The README was never held to that rule and drifted from it silently: it published
the share of ordinary seasons as 55% when the data said 48%, Bahia's dry-day
correlation as -0.52 when it was -0.51, and the dry-spell correlation as -0.25
when it was -0.26. Nothing caught any of them, because prose has no tests.

Generating the READMEs from the data would fix the numbers and break the argument.
The sentences around them assert what the numbers *mean*: a generator would
happily rewrite "removes 40% of the error" while leaving "the model earns its keep
only when the harvest breaks" standing above a number that no longer supports it.
So this asserts instead. The aggregates here are all over closed seasons, so they
do not move on the weekly refresh -- they move once, when a season closes and
enters the backtest. That is the moment nobody is watching, and the moment this
turns CI red so a human decides what the finding now is.

Both translations are checked, from one set of computations. A second language is
a second surface that can drift, and the Portuguese one would rot unwatched
otherwise -- it writes decimals with a comma, which is the only difference the
comparison has to absorb.

Covered: everything derivable from app/data. Deliberately not covered, and still
typed by hand -- the twelve-way detrend comparison and the per-model-family skill
spread (both need the warehouse), the one-variable rule comparison (needs the
walk-forward z-scores, which are not exported), the hub and grid-cell counts
(fixed by versioned reference data), and the dbt test count.

    py scripts/check_readme_numbers.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app"))

import charts as c  # noqa: E402

DATA_DIR = REPO_ROOT / "app" / "data"

# Positions, not retyped labels: the bands are built from FLAG_PCT/FAIL_PCT, so a
# threshold change has to reach this file through charts.py rather than silently
# comparing against a string that no longer exists.
FAILURE, MID, NORMAL, GOOD_MID, GOOD = c.SEVERITY_ORDER

# State names are spelled the same in both languages, so this table is shared.
STATE_ROWS = {name: code for code, name in c.STATE_NAME.items()}

# The bootstrap interval is published rounded, and its bounds move a couple of
# points between seeds. Asserting an exact bound would be asserting the seed, so
# the check allows the slack the estimate actually has.
CI_TOLERANCE_PP = 3


@dataclass(frozen=True)
class Doc:
    """One README and the phrasing its claims are anchored to."""

    path: str
    severity_header: str
    severity_rows: dict[str, str]
    change_suffix: str
    detector_header: str
    crop_rows: dict[str, str]
    crop_corr_header: str
    state_header: str
    weather_rows: str
    scale: str
    correlation: str
    skill: str
    soy_sample: str
    base_rate_lift: str
    recall_ci: str
    baseline_zero: str
    ratio: str
    ratio_words: dict[int, str]
    dry_spell: str
    worst_soy: str
    pr_season: str
    backtest_window: str
    corr_window: str
    decimal_comma: bool = field(default=False)


DOCS = [
    Doc(
        path="README.md",
        severity_header="Baseline error",
        severity_rows={"Severe shortfall: below -20%": FAILURE,
                       "Moderate shortfall: -20% to -10%": MID,
                       "Normal season: ±10%": NORMAL,
                       "Good season: +10% to +20%": GOOD_MID,
                       "Very good season: above +20%": GOOD},
        change_suffix="% error",
        detector_header="Alarms raised",
        crop_rows={"Soybean": "SOJA", "Second-crop corn": "MILHO 2A SAFRA"},
        crop_corr_header="Dry-day anomaly",
        state_header="| State | Rainfall |",
        weather_rows=r"([\d.]+) million daily weather rows",
        scale=r"(\d+) crop × state pairs, (\d+) seasons scored",
        correlation=r"\*\*\+([\d.]+)\*\* on soybean and \*\*\+([\d.]+)\*\* on second-crop corn",
        skill=r"gain over the baseline: ([\d.]+)% on soybean and ([\d.]+)% on second-crop corn",
        soy_sample=r"(\d+) of the (\d+), and most of the sample",
        base_rate_lift=r"shortfalls are (\d+)% of soybean seasons and (\d+)% of safrinha seasons, "
                       r"so (\d+)% and (\d+)% are gains of ([\d.]+)× and ([\d.]+)× over chance",
        recall_ci=r"soybean recall runs from roughly (\d+)% to (\d+)%",
        baseline_zero=r"baseline raises \*\*(\w+)\*\* alarms",
        ratio=r"roughly (\w+ ?\w*) as rainfall-sensitive",
        ratio_words={2: "twice", 3: "three times", 4: "four times", 5: "five times"},
        dry_spell=r"\((-[\d.]+) against (-[\d.]+) on soybean\)",
        worst_soy=r"worst soybean season in the record is ([\w ]+?) in (\d{4}), "
                  r"at \*\*(-\d+)% against trend\*\* with (\d+) extra dry days",
        pr_season=r"corn in (\d{4}) came in at \*\*(-\d+)%\*\* "
                  r"with rainfall at \*\*(-[\d.]+) standard",
        backtest_window=r"\((\d+) states × (\d{4})–(\d{4})\)",
        corr_window=r"normal, over (\d{4})–(\d{4})",
    ),
    Doc(
        path="README.pt-BR.md",
        severity_header="Erro do baseline",
        severity_rows={"Quebra forte: abaixo de -20%": FAILURE,
                       "Quebra moderada: -20% a -10%": MID,
                       "Safra normal: ±10%": NORMAL,
                       "Safra boa: +10% a +20%": GOOD_MID,
                       "Safra muito boa: acima de +20%": GOOD},
        change_suffix="% de erro",
        detector_header="Alarmes disparados",
        crop_rows={"Soja": "SOJA", "Milho segunda safra": "MILHO 2A SAFRA"},
        crop_corr_header="Anomalia de dias secos",
        state_header="| Estado | Chuva |",
        weather_rows=r"([\d,]+) milhões de linhas de clima diário",
        scale=r"(\d+) pares cultura × estado, (\d+) safras avaliadas",
        correlation=r"\*\*\+([\d,]+)\*\* na soja e \*\*\+([\d,]+)\*\* no milho segunda safra",
        skill=r"sobre o baseline: ([\d,]+)% na soja e ([\d,]+)% no milho segunda safra",
        soy_sample=r"(\d+) das (\d+), e a maior parte da amostra",
        base_rate_lift=r"quebras são (\d+)% das safras de soja e (\d+)% das\s*de safrinha, então "
                       r"(\d+)% e (\d+)% representam ganho de ([\d,]+)× e ([\d,]+)× sobre o acaso",
        recall_ci=r"recall da soja vai de aproximadamente (\d+)% a (\d+)%",
        baseline_zero=r"baseline dispara\s*\*\*(\w+)\*\* alarmes",
        ratio=r"cerca de (\w+) vezes mais sensível",
        ratio_words={2: "duas", 3: "três", 4: "quatro", 5: "cinco"},
        dry_spell=r"\((-[\d,]+) contra (-[\d,]+) na soja\)",
        worst_soy=r"pior safra de soja da série é o ([\w ]+?) em (\d{4}), "
                  r"com \*\*(-\d+)% ante a tendência\*\* e (\d+) dias secos a mais",
        pr_season=r"milho segunda safra do Paraná em (\d{4}) fechou em \*\*(-\d+)%\*\* "
                  r"com chuva a \*\*(-[\d,]+) desvios",
        backtest_window=r"\((\d+) estados × (\d{4})–(\d{4})\)",
        corr_window=r"ao longo de (\d{4})–(\d{4})",
        decimal_comma=True,
    ),
]


class Report:
    """Collects every mismatch instead of dying on the first one.

    A season closing moves most of these at once, in both languages. Stopping at
    the first failure would mean one CI run per number, and the point is to see
    the whole shift.
    """

    def __init__(self) -> None:
        self.failures: list[str] = []

    @staticmethod
    def _norm(value: str) -> str:
        # The Portuguese README writes 3,4 where the English one writes 3.4, and
        # a decimal separator is not a claim about the data.
        return value.strip().replace(",", ".")

    def check(self, label: str, published: str, computed: str) -> None:
        if self._norm(published) == self._norm(computed):
            print(f"ok   {label}: {computed}")
        else:
            self.failures.append(f"{label}: says {published!r}, data says {computed!r}")
            print(f"FAIL {label}: says {published!r}, data says {computed!r}")

    def check_close(self, label: str, published: str, computed: float, tol: float) -> None:
        """For the bootstrap bounds, which are an estimate rather than a count."""
        said = float(self._norm(published))
        if abs(said - computed) <= tol:
            print(f"ok   {label}: says {said:.0f}, data says {computed:.0f} (within {tol:.0f})")
        else:
            self.failures.append(
                f"{label}: says {said:.0f}, data says {computed:.0f} (tolerance {tol:.0f})")
            print(f"FAIL {label}: says {said:.0f}, data says {computed:.0f}")


def table_rows(text: str, header_fragment: str) -> dict[str, list[str]]:
    """Rows of the first markdown table whose header contains `header_fragment`.

    Keyed by first cell, so a row that gets moved still lines up with its data
    and a row that gets renamed fails loudly instead of comparing to nothing.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.startswith("|") and header_fragment in line), None)
    if start is None:
        raise LookupError(f"no table whose header contains {header_fragment!r}")
    rows = {}
    for line in lines[start + 2:]:  # +2 skips the |---|---| separator
        if not line.startswith("|"):
            break
        cells = [cell.strip().strip("*").strip() for cell in line.strip("|").split("|")]
        rows[cells[0]] = cells[1:]
    return rows


def prose(text: str, pattern: str) -> tuple[str, ...]:
    match = re.search(pattern, text)
    if match is None:
        raise LookupError(f"no sentence matching {pattern!r}")
    return match.groups()


def errors(group: pd.DataFrame) -> tuple[float, float]:
    return (c.rmse(group["baseline"] - group["actual_pct"]),
            c.rmse(group["model"] - group["actual_pct"]))


def recall_interval(group: pd.DataFrame, draws: int = 4000, seed: int = 0) -> tuple[float, float]:
    """95% interval for recall, resampling whole seasons rather than rows.

    A drought hits several states in the same year, so the crop x state rows are
    not independent draws. Resampling years keeps those clusters intact;
    resampling rows would report an interval narrower than the data supports.
    """
    rng = np.random.default_rng(seed)
    years = group["harvest_year"].unique()
    by_year = {year: group[group["harvest_year"] == year] for year in years}
    rates = []
    for _ in range(draws):
        sample = pd.concat([by_year[y] for y in rng.choice(years, len(years), replace=True)])
        real, flagged = sample["actual_pct"] <= c.FLAG_PCT, sample["model"] <= c.FLAG_PCT
        if real.sum():
            rates.append((real & flagged).sum() / real.sum() * 100)
    return float(np.percentile(rates, 2.5)), float(np.percentile(rates, 97.5))


def check_doc(doc: Doc, season: pd.DataFrame, wide: pd.DataFrame, meta: dict,
              rep: Report) -> None:
    text = (REPO_ROOT / doc.path).read_text(encoding="utf-8")
    # Tables need the line structure; prose does not, and matching it line by line
    # would fail every time a paragraph is rewrapped. Sentences are matched flat.
    flat = re.sub(r"\s+", " ", text)
    tag = doc.path

    soy = wide[wide["crop_name"] == "SOJA"]
    corn = wide[wide["crop_name"] == "MILHO 2A SAFRA"]

    # --- scale claims in the opening paragraph
    rep.check(f"{tag} weather rows", prose(flat, doc.weather_rows)[0],
              f"{meta['weather_rows'] / 1e6:.1f}")
    said = prose(flat, doc.scale)
    rep.check(f"{tag} crop x state pairs", said[0],
              f"{wide.groupby('crop_name')['state_code'].nunique().sum()}")
    rep.check(f"{tag} seasons scored", said[1], f"{len(wide)}")

    # --- the headline: signal size, then the tie, then where the gain sits
    said = prose(flat, doc.correlation)
    rep.check(f"{tag} soybean correlation", said[0], f"{soy['model'].corr(soy['actual_pct']):.2f}")
    rep.check(f"{tag} corn correlation", said[1], f"{corn['model'].corr(corn['actual_pct']):.2f}")

    soy_base, soy_model = errors(soy)
    corn_base, corn_model = errors(corn)
    said = prose(flat, doc.skill)
    rep.check(f"{tag} soybean global skill", said[0],
              f"{(soy_base - soy_model) / soy_base * 100:.1f}")
    rep.check(f"{tag} corn global skill", said[1],
              f"{(corn_base - corn_model) / corn_base * 100:.1f}")

    published = table_rows(text, doc.severity_header)
    for label, band in doc.severity_rows.items():
        group = soy[soy["severity"] == band]
        base, model = errors(group)
        cells = published[label]
        rep.check(f"{tag} soybean {band} n", cells[0], f"{len(group)}")
        rep.check(f"{tag} soybean {band} baseline RMSE", cells[1], f"{base:.1f}")
        rep.check(f"{tag} soybean {band} model RMSE", cells[2], f"{model:.1f}")
        rep.check(f"{tag} soybean {band} change", cells[3],
                  f"{(model - base) / base * 100:+.0f}{doc.change_suffix}")

    said = prose(flat, doc.soy_sample)
    rep.check(f"{tag} soybean ordinary seasons", said[0],
              f"{int((soy['severity'] == NORMAL).sum())}")
    rep.check(f"{tag} soybean seasons", said[1], f"{len(soy)}")

    # --- the detector, and the base rate without which precision means nothing
    published = table_rows(text, doc.detector_header)
    rates = {}
    for label, crop in doc.crop_rows.items():
        sub = wide[wide["crop_name"] == crop]
        real, flagged = sub["actual_pct"] <= c.FLAG_PCT, sub["model"] <= c.FLAG_PCT
        hit = int((real & flagged).sum())
        cells = published[label]
        rep.check(f"{tag} {label} real shortfalls", cells[0], f"{int(real.sum())}")
        rep.check(f"{tag} {label} alarms", cells[1], f"{int(flagged.sum())}")
        rep.check(f"{tag} {label} right", cells[2], f"{hit}")
        rep.check(f"{tag} {label} recall", cells[3], f"{hit / real.sum() * 100:.0f}%")
        rep.check(f"{tag} {label} precision", cells[4], f"{hit / flagged.sum() * 100:.0f}%")
        rates[crop] = (real.mean() * 100, hit / flagged.sum() * 100)

    said = prose(flat, doc.base_rate_lift)
    for i, crop in enumerate(["SOJA", "MILHO 2A SAFRA"]):
        base_rate, precision = rates[crop]
        rep.check(f"{tag} {crop} base rate", said[i], f"{base_rate:.0f}")
        rep.check(f"{tag} {crop} precision (restated)", said[i + 2], f"{precision:.0f}")
        rep.check(f"{tag} {crop} lift", said[i + 4], f"{precision / base_rate:.1f}")

    # A trend line predicting a bad year would break the whole detector argument,
    # so the word "zero" is checked against the count rather than trusted.
    flags = int((wide["baseline"] <= c.FLAG_PCT).sum())
    rep.check(f"{tag} baseline alarms", prose(flat, doc.baseline_zero)[0],
              "zero" if flags == 0 else str(flags))

    low, high = recall_interval(soy)
    said = prose(flat, doc.recall_ci)
    rep.check_close(f"{tag} soybean recall CI low", said[0], low, CI_TOLERANCE_PP)
    rep.check_close(f"{tag} soybean recall CI high", said[1], high, CI_TOLERANCE_PP)

    # Same cutoff the app uses, and for the same reason: the newest season is
    # CONAB's open estimate, not a harvest. Read from the data, never typed.
    closed = season[season["harvest_year"] < season["harvest_year"].max()].dropna(
        subset=["yield_residual_pct"])
    published = table_rows(text, doc.crop_corr_header)
    for label, crop in doc.crop_rows.items():
        g = closed[closed["crop_name"] == crop]
        cells = published[label]
        for i, column in enumerate(["dry_days_anomaly_z", "precipitation_anomaly_z",
                                    "temp_anomaly_z"]):
            rep.check(f"{tag} {label} {column}", cells[i],
                      f"{g[column].corr(g['yield_residual_pct']):+.2f}")

    soy_closed = closed[closed["crop_name"] == "SOJA"]
    published = table_rows(text, doc.state_header)
    for label, uf in STATE_ROWS.items():
        g = soy_closed[soy_closed["state_code"] == uf]
        cells = published[label]
        rep.check(f"{tag} {label} rainfall corr", cells[0],
                  f"{g['precipitation_anomaly_z'].corr(g['yield_residual_pct']):+.2f}")
        rep.check(f"{tag} {label} dry-day corr", cells[1],
                  f"{g['dry_days_anomaly_z'].corr(g['yield_residual_pct']):+.2f}")

    def rain_corr(uf: str) -> float:
        g = soy_closed[soy_closed["state_code"] == uf]
        return g["precipitation_anomaly_z"].corr(g["yield_residual_pct"])

    ratio = rain_corr("RS") / rain_corr("MT")
    rep.check(f"{tag} RS vs MT sensitivity", prose(flat, doc.ratio)[0],
              doc.ratio_words.get(round(ratio), f"{ratio:.1f}x"))

    # The dry-spell result is the project's published negative finding, so the
    # number that demotes it has to survive every rebuild.
    said = prose(flat, doc.dry_spell)
    rep.check(f"{tag} dry-spell corr", said[0],
              f"{soy_closed['dry_spell_anomaly_days'].corr(soy_closed['yield_residual_pct']):.2f}")
    rep.check(f"{tag} dry-day corr", said[1],
              f"{soy_closed['dry_days_anomaly_z'].corr(soy_closed['yield_residual_pct']):.2f}")

    def season_row(crop: str, uf: str, year: int) -> pd.Series:
        row = season[(season["crop_name"] == crop) & (season["state_code"] == uf)
                     & (season["harvest_year"] == year)]
        if row.empty:
            raise LookupError(f"{crop} {uf} {year} is no longer in season_risk.csv")
        return row.iloc[0]

    # This paragraph once claimed these were "the two worst seasons in the series".
    # They are not -- the Paraná one is fifth -- and nothing noticed, because a
    # ranking is a claim about the whole table that reads like a caption. So the
    # superlative is now checked against the table it describes.
    said = prose(flat, doc.worst_soy)
    worst = season[season["crop_name"] == "SOJA"].nsmallest(1, "yield_residual_pct").iloc[0]
    rep.check(f"{tag} worst soybean season", f"{said[0]} {said[1]}",
              f"{c.STATE_NAME[worst['state_code']]} {int(worst['harvest_year'])}")
    row = season_row("SOJA", "RS", int(said[1]))
    rep.check(f"{tag} RS 2005 residual", said[2], f"{row['yield_residual_pct'] * 100:.0f}")
    rep.check(f"{tag} RS 2005 extra dry days", said[3], f"{row['dry_days_anomaly']:.0f}")

    said = prose(flat, doc.pr_season)
    row = season_row("MILHO 2A SAFRA", "PR", int(said[0]))
    rep.check(f"{tag} PR 2021 residual", said[1], f"{row['yield_residual_pct'] * 100:.0f}")
    rep.check(f"{tag} PR 2021 rainfall z", said[2], f"{row['precipitation_anomaly_z']:.2f}")

    said = prose(flat, doc.backtest_window)
    rep.check(f"{tag} soybean states", said[0], f"{soy['state_code'].nunique()}")
    rep.check(f"{tag} backtest window", "–".join(said[1:]),
              f"{wide['harvest_year'].min()}–{wide['harvest_year'].max()}")
    rep.check(f"{tag} correlation window", "–".join(prose(flat, doc.corr_window)),
              f"{closed['harvest_year'].min()}–{closed['harvest_year'].max()}")


def main() -> int:
    import json

    season = pd.read_csv(DATA_DIR / "season_risk.csv")
    wide = c.widen(pd.read_csv(DATA_DIR / "backtest.csv"))
    meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
    rep = Report()

    for doc in DOCS:
        print(f"--- {doc.path} ---")
        check_doc(doc, season, wide, meta, rep)
        print()

    if rep.failures:
        print(f"{len(rep.failures)} claim(s) no longer match app/data:")
        for failure in rep.failures:
            print(f"  - {failure}")
        print("\nFix the README, or decide the finding changed and rewrite the argument.")
        return 1
    print(f"All README numbers match the exported data, in {len(DOCS)} languages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
