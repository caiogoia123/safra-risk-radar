"""Asserts that every number README.md quotes about the data still matches the data.

The app already refuses to state a fact it did not read from the exported CSVs.
The README was never held to that rule and drifted from it silently: it published
the share of ordinary seasons as 55% when the data said 48%, Bahia's dry-day
correlation as -0.52 when it was -0.51, and the dry-spell correlation as -0.25
when it was -0.26. Nothing caught any of them, because prose has no tests.

Generating the README from the data would fix the numbers and break the argument.
The sentences around them assert what the numbers *mean*: a generator would
happily rewrite "removes 40% of the error" while leaving "the model earns its keep
only when the harvest breaks" standing above a number that no longer supports it.
So this asserts instead. The aggregates here are all over closed seasons, so they
do not move on the weekly refresh -- they move once, when a season closes and
enters the backtest. That is the moment nobody is watching, and the moment this
turns CI red so a human decides what the finding now is.

Covered: everything derivable from app/data. Deliberately not covered, and still
typed by hand -- the twelve-way detrend comparison (needs the warehouse), the hub
and grid-cell counts (fixed by versioned reference data), and the dbt test count.

    py scripts/check_readme_numbers.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app"))

import charts as c  # noqa: E402

DATA_DIR = REPO_ROOT / "app" / "data"
README_PATH = REPO_ROOT / "README.md"

# README row label -> the band charts.py actually cuts. Kept as a mapping rather
# than matched by position: reordering the table in prose should not silently
# start comparing the wrong band.
SEVERITY_ROWS = {
    "Shortfall < -20%": "Failure < -20%",
    "-20% to -10%": "-20% to -10%",
    "Normal ±10%": "Normal ±10%",
    "Good > +20%": "Good > +20%",
}
CROP_ROWS = {"Soybean": "SOJA", "Second-crop corn": "MILHO 2A SAFRA"}
# Borrowed from the app rather than retyped, so the README, the dashboard and this
# check can never disagree about what to call a state.
STATE_NAMES = c.STATE_NAME
STATE_ROWS = {name: code for code, name in STATE_NAMES.items()}
RATIO_WORDS = {2: "twice", 3: "three times", 4: "four times", 5: "five times"}


class Report:
    """Collects every mismatch instead of dying on the first one.

    A season closing moves most of these at once. Stopping at the first failure
    would mean one CI run per number, and the point is to see the whole shift.
    """

    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, label: str, published: str, computed: str) -> None:
        if published.strip() == computed.strip():
            print(f"ok   {label}: {computed}")
        else:
            self.failures.append(f"{label}: README says {published!r}, data says {computed!r}")
            print(f"FAIL {label}: README says {published!r}, data says {computed!r}")


def table_rows(text: str, header_fragment: str) -> dict[str, list[str]]:
    """Rows of the first markdown table whose header contains `header_fragment`.

    Keyed by first cell, so a row that gets moved still lines up with its data
    and a row that gets renamed fails loudly instead of comparing to nothing.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.startswith("|") and header_fragment in line), None)
    if start is None:
        raise LookupError(f"no README table whose header contains {header_fragment!r}")
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
        raise LookupError(f"README no longer contains the sentence matching {pattern!r}")
    return match.groups()


def main() -> int:
    readme = README_PATH.read_text(encoding="utf-8")
    # Tables need the line structure; prose does not, and matching it line by line
    # would fail every time a paragraph is rewrapped. Sentences are matched flat.
    flat = re.sub(r"\s+", " ", readme)
    season = pd.read_csv(DATA_DIR / "season_risk.csv")
    wide = c.widen(pd.read_csv(DATA_DIR / "backtest.csv"))
    rep = Report()

    def errors(group: pd.DataFrame) -> tuple[float, float]:
        return (c.rmse(group["baseline"] - group["actual_pct"]),
                c.rmse(group["model"] - group["actual_pct"]))

    # ---------------------------------------------------------- severity table
    soy = wide[wide["crop_name"] == "SOJA"]
    published = table_rows(readme, "Actual deviation")
    for label, band in SEVERITY_ROWS.items():
        group = soy[soy["severity"] == band]
        base, model = errors(group)
        cells = published[label]
        rep.check(f"soybean {band} n", cells[0], f"{len(group)}")
        rep.check(f"soybean {band} baseline RMSE", cells[1], f"{base:.1f}")
        rep.check(f"soybean {band} model RMSE", cells[2], f"{model:.1f}")
        rep.check(f"soybean {band} change", cells[3],
                  f"{(model - base) / base * 100:+.0f}% error")

    # ------------------------------------------------------------ global skill
    soy_base, soy_model = errors(soy)
    corn = wide[wide["crop_name"] == "MILHO 2A SAFRA"]
    corn_base, corn_model = errors(corn)
    said = prose(flat,r"([\d.]+)% better on soybean, ([\d.]+)% on second-crop corn")
    rep.check("soybean global skill", said[0], f"{(soy_base - soy_model) / soy_base * 100:.1f}")
    rep.check("corn global skill", said[1], f"{(corn_base - corn_model) / corn_base * 100:.1f}")

    # The share that dilutes the global metric -- the sentence exists to explain
    # why the average looks like a tie, so a wrong value there is not cosmetic.
    counts = wide["severity"].value_counts()
    share = counts[f"Normal ±{abs(c.FLAG_PCT)}%"] / counts.sum() * 100
    rep.check("ordinary-season share",
              prose(flat,r"normal years are (\d+)% of the sample")[0], f"{share:.0f}")

    said = prose(flat,r"([-+]\d+)% error on shortfalls, ([-+]\d+)% in normal years")
    base, model = errors(corn[corn["severity"] == "Failure < -20%"])
    rep.check("corn shortfall change", said[0], f"{(model - base) / base * 100:+.0f}")
    base, model = errors(corn[corn["severity"] == f"Normal ±{abs(c.FLAG_PCT)}%"])
    rep.check("corn normal-year change", said[1], f"{(model - base) / base * 100:+.0f}")

    # ---------------------------------------------------------- detector table
    published = table_rows(readme, "Real events")
    for label, crop in CROP_ROWS.items():
        sub = wide[wide["crop_name"] == crop]
        real, flagged = sub["actual_pct"] <= c.FLAG_PCT, sub["model"] <= c.FLAG_PCT
        hit = int((real & flagged).sum())
        cells = published[label]
        rep.check(f"{label} real events", cells[0], f"{int(real.sum())}")
        rep.check(f"{label} flagged", cells[1], f"{int(flagged.sum())}")
        rep.check(f"{label} correct", cells[2], f"{hit}")
        rep.check(f"{label} recall", cells[3], f"{hit / real.sum() * 100:.0f}%")
        rep.check(f"{label} precision", cells[4], f"{hit / flagged.sum() * 100:.0f}%")
        rep.check(f"{label} baseline flags", cells[5],
                  f"{int((sub['baseline'] <= c.FLAG_PCT).sum())}")

    # ------------------------------------------------------------ correlations
    # Same cutoff the app uses, and for the same reason: the newest season is
    # CONAB's open estimate, not a harvest. Read from the data, never typed.
    closed = season[season["harvest_year"] < season["harvest_year"].max()].dropna(
        subset=["yield_residual_pct"])
    published = table_rows(readme, "Dry-day anomaly")
    for label, crop in CROP_ROWS.items():
        g = closed[closed["crop_name"] == crop]
        cells = published[label]
        for i, column in enumerate(["dry_days_anomaly_z", "precipitation_anomaly_z",
                                    "temp_anomaly_z"]):
            rep.check(f"{label} {column}", cells[i],
                      f"{g[column].corr(g['yield_residual_pct']):+.2f}")

    soy_closed = closed[closed["crop_name"] == "SOJA"]
    published = table_rows(readme, "| State | Rainfall |")
    for label, uf in STATE_ROWS.items():
        g = soy_closed[soy_closed["state_code"] == uf]
        cells = published[label]
        rep.check(f"{label} rainfall corr", cells[0],
                  f"{g['precipitation_anomaly_z'].corr(g['yield_residual_pct']):+.2f}")
        rep.check(f"{label} dry-day corr", cells[1],
                  f"{g['dry_days_anomaly_z'].corr(g['yield_residual_pct']):+.2f}")

    def rain_corr(uf: str) -> float:
        g = soy_closed[soy_closed["state_code"] == uf]
        return g["precipitation_anomaly_z"].corr(g["yield_residual_pct"])

    ratio = rain_corr("RS") / rain_corr("MT")
    rep.check("RS vs MT sensitivity",
              prose(flat,r"roughly (\w+ ?\w*) as rainfall-sensitive")[0],
              RATIO_WORDS.get(round(ratio), f"{ratio:.1f}x"))

    # The dry-spell result is the project's published negative finding, so the
    # number that demotes it has to survive every rebuild.
    said = prose(flat,r"\((-[\d.]+) against (-[\d.]+) on soybean\)")
    rep.check("dry-spell corr", said[0],
              f"{soy_closed['dry_spell_anomaly_days'].corr(soy_closed['yield_residual_pct']):.2f}")
    rep.check("dry-day corr", said[1],
              f"{soy_closed['dry_days_anomaly_z'].corr(soy_closed['yield_residual_pct']):.2f}")

    # ----------------------------------------------------------- named seasons
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
    said = prose(flat, r"worst soybean season in the record is ([\w ]+?) in (\d{4}), "
                       r"at \*\*(-\d+)% against trend\*\* with (\d+) extra dry days")
    worst = season[season["crop_name"] == "SOJA"].nsmallest(1, "yield_residual_pct").iloc[0]
    rep.check("worst soybean season", f"{said[0]} {said[1]}",
              f"{STATE_NAMES[worst['state_code']]} {int(worst['harvest_year'])}")
    row = season_row("SOJA", "RS", int(said[1]))
    rep.check("RS 2005 residual", said[2], f"{row['yield_residual_pct'] * 100:.0f}")
    rep.check("RS 2005 extra dry days", said[3], f"{row['dry_days_anomaly']:.0f}")

    said = prose(flat, r"corn in (\d{4}) came in at \*\*(-\d+)%\*\* "
                       r"with rainfall at \*\*(-[\d.]+) standard")
    row = season_row("MILHO 2A SAFRA", "PR", int(said[0]))
    rep.check("PR 2021 residual", said[1], f"{row['yield_residual_pct'] * 100:.0f}")
    rep.check("PR 2021 rainfall z", said[2], f"{row['precipitation_anomaly_z']:.2f}")

    # ------------------------------------------------------------------ ranges
    rep.check("backtest window",
              "–".join(prose(flat,r"walk-forward (\d{4})–(\d{4})")),
              f"{wide['harvest_year'].min()}–{wide['harvest_year'].max()}")
    rep.check("correlation window",
              "–".join(prose(flat,r"normal, over (\d{4})–(\d{4})")),
              f"{closed['harvest_year'].min()}–{closed['harvest_year'].max()}")

    print()
    if rep.failures:
        print(f"{len(rep.failures)} claim(s) in README.md no longer match app/data:")
        for failure in rep.failures:
            print(f"  - {failure}")
        print("\nFix the README, or decide the finding changed and rewrite the argument.")
        return 1
    print("All README numbers match the exported data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
