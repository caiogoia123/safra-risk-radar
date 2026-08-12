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
typed by hand -- the twelve-way detrend comparison (needs the warehouse), the hub
and grid-cell counts (fixed by versioned reference data), and the dbt test count.

    py scripts/check_readme_numbers.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app"))

import charts as c  # noqa: E402

DATA_DIR = REPO_ROOT / "app" / "data"

# Positions, not retyped labels: the bands are built from FLAG_PCT/FAIL_PCT, so a
# threshold change has to reach this file through charts.py rather than silently
# comparing against a string that no longer exists.
FAILURE, MID, NORMAL, _, GOOD = c.SEVERITY_ORDER

# State names are spelled the same in both languages, so this table is shared.
STATE_ROWS = {name: code for code, name in c.STATE_NAME.items()}


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
    skill: str
    normal_share: str
    corn_bands: str
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
        severity_header="Actual deviation",
        severity_rows={"Shortfall < -20%": FAILURE, "-20% to -10%": MID,
                       "Normal ±10%": NORMAL, "Good > +20%": GOOD},
        change_suffix="% error",
        detector_header="Real events",
        crop_rows={"Soybean": "SOJA", "Second-crop corn": "MILHO 2A SAFRA"},
        crop_corr_header="Dry-day anomaly",
        state_header="| State | Rainfall |",
        skill=r"([\d.]+)% better on soybean, ([\d.]+)% on second-crop corn",
        normal_share=r"normal years are (\d+)% of the sample",
        corn_bands=r"([-+]\d+)% error on shortfalls, ([-+]\d+)% in normal years",
        ratio=r"roughly (\w+ ?\w*) as rainfall-sensitive",
        ratio_words={2: "twice", 3: "three times", 4: "four times", 5: "five times"},
        dry_spell=r"\((-[\d.]+) against (-[\d.]+) on soybean\)",
        worst_soy=r"worst soybean season in the record is ([\w ]+?) in (\d{4}), "
                  r"at \*\*(-\d+)% against trend\*\* with (\d+) extra dry days",
        pr_season=r"corn in (\d{4}) came in at \*\*(-\d+)%\*\* "
                  r"with rainfall at \*\*(-[\d.]+) standard",
        backtest_window=r"walk-forward (\d{4})–(\d{4})",
        corr_window=r"normal, over (\d{4})–(\d{4})",
    ),
    Doc(
        path="README.pt-BR.md",
        severity_header="Desvio real",
        severity_rows={"Quebra < -20%": FAILURE, "-20% a -10%": MID,
                       "Normal ±10%": NORMAL, "Boa > +20%": GOOD},
        change_suffix="% de erro",
        detector_header="Eventos reais",
        crop_rows={"Soja": "SOJA", "Milho segunda safra": "MILHO 2A SAFRA"},
        crop_corr_header="Anomalia de dias secos",
        state_header="| Estado | Chuva |",
        skill=r"([\d,]+)% melhor na soja, ([\d,]+)% no milho segunda safra",
        normal_share=r"anos normais são (\d+)% da amostra",
        corn_bands=r"([-+]\d+)% de erro nas quebras, ([-+]\d+)% em anos normais",
        ratio=r"cerca de (\w+) vezes mais sensível",
        ratio_words={2: "duas", 3: "três", 4: "quatro", 5: "cinco"},
        dry_spell=r"\((-[\d,]+) contra (-[\d,]+) na soja\)",
        worst_soy=r"pior safra de soja da série é o ([\w ]+?) em (\d{4}), "
                  r"com \*\*(-\d+)% ante a tendência\*\* e (\d+) dias secos a mais",
        pr_season=r"milho segunda safra do Paraná em (\d{4}) fechou em \*\*(-\d+)%\*\* "
                  r"com chuva a \*\*(-[\d,]+) desvios",
        backtest_window=r"walk-forward (\d{4})–(\d{4})",
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

    def check(self, label: str, published: str, computed: str) -> None:
        # The Portuguese README writes 3,4 where the English one writes 3.4, and
        # a decimal separator is not a claim about the data.
        if published.strip().replace(",", ".") == computed.strip().replace(",", "."):
            print(f"ok   {label}: {computed}")
        else:
            self.failures.append(f"{label}: says {published!r}, data says {computed!r}")
            print(f"FAIL {label}: says {published!r}, data says {computed!r}")


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


def check_doc(doc: Doc, season: pd.DataFrame, wide: pd.DataFrame, rep: Report) -> None:
    text = (REPO_ROOT / doc.path).read_text(encoding="utf-8")
    # Tables need the line structure; prose does not, and matching it line by line
    # would fail every time a paragraph is rewrapped. Sentences are matched flat.
    flat = re.sub(r"\s+", " ", text)
    tag = doc.path

    soy = wide[wide["crop_name"] == "SOJA"]
    corn = wide[wide["crop_name"] == "MILHO 2A SAFRA"]

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

    soy_base, soy_model = errors(soy)
    corn_base, corn_model = errors(corn)
    said = prose(flat, doc.skill)
    rep.check(f"{tag} soybean global skill", said[0],
              f"{(soy_base - soy_model) / soy_base * 100:.1f}")
    rep.check(f"{tag} corn global skill", said[1],
              f"{(corn_base - corn_model) / corn_base * 100:.1f}")

    # The share that dilutes the global metric -- the sentence exists to explain
    # why the average looks like a tie, so a wrong value there is not cosmetic.
    counts = wide["severity"].value_counts()
    rep.check(f"{tag} ordinary-season share", prose(flat, doc.normal_share)[0],
              f"{counts[NORMAL] / counts.sum() * 100:.0f}")

    said = prose(flat, doc.corn_bands)
    base, model = errors(corn[corn["severity"] == FAILURE])
    rep.check(f"{tag} corn shortfall change", said[0], f"{(model - base) / base * 100:+.0f}")
    base, model = errors(corn[corn["severity"] == NORMAL])
    rep.check(f"{tag} corn normal-year change", said[1], f"{(model - base) / base * 100:+.0f}")

    published = table_rows(text, doc.detector_header)
    for label, crop in doc.crop_rows.items():
        sub = wide[wide["crop_name"] == crop]
        real, flagged = sub["actual_pct"] <= c.FLAG_PCT, sub["model"] <= c.FLAG_PCT
        hit = int((real & flagged).sum())
        cells = published[label]
        rep.check(f"{tag} {label} real events", cells[0], f"{int(real.sum())}")
        rep.check(f"{tag} {label} flagged", cells[1], f"{int(flagged.sum())}")
        rep.check(f"{tag} {label} correct", cells[2], f"{hit}")
        rep.check(f"{tag} {label} recall", cells[3], f"{hit / real.sum() * 100:.0f}%")
        rep.check(f"{tag} {label} precision", cells[4], f"{hit / flagged.sum() * 100:.0f}%")
        rep.check(f"{tag} {label} baseline flags", cells[5],
                  f"{int((sub['baseline'] <= c.FLAG_PCT).sum())}")

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

    rep.check(f"{tag} backtest window", "–".join(prose(flat, doc.backtest_window)),
              f"{wide['harvest_year'].min()}–{wide['harvest_year'].max()}")
    rep.check(f"{tag} correlation window", "–".join(prose(flat, doc.corr_window)),
              f"{closed['harvest_year'].min()}–{closed['harvest_year'].max()}")


def main() -> int:
    season = pd.read_csv(DATA_DIR / "season_risk.csv")
    wide = c.widen(pd.read_csv(DATA_DIR / "backtest.csv"))
    rep = Report()

    for doc in DOCS:
        print(f"--- {doc.path} ---")
        check_doc(doc, season, wide, rep)
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
