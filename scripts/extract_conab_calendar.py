"""Extract CONAB's planting/harvest calendar from the official PDF into a dbt seed.

CONAB publishes the calendar as a PDF where the months are *coloured bars*, not
text: the page text only holds state codes and month headers. So the bars are
read geometrically -- a bar's colour gives the phase, and the month columns its
horizontal span covers give the months.

Run this only when CONAB publishes a new edition:
    python scripts/extract_conab_calendar.py

Source: Calendario de Plantio e Colheita de Graos no Brasil (CONAB, 2022)
https://www.gov.br/conab/pt-br/acesso-a-informacao/institucional/publicacoes/arquivos-de-paginas/calendariozplantiozezcolheitazjunz2022.pdf
"""

from __future__ import annotations

import csv
from pathlib import Path

import pdfplumber
import requests

PDF_URL = (
    "https://www.gov.br/conab/pt-br/acesso-a-informacao/institucional/publicacoes/"
    "arquivos-de-paginas/calendariozplantiozezcolheitazjunz2022.pdf"
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = PROJECT_ROOT / "data" / "raw" / "conab" / "calendario_plantio_colheita_2022.pdf"
SEED_PATH = PROJECT_ROOT / "dbt" / "seeds" / "crop_calendar.csv"

# Page ranges per crop, from the PDF's table of contents (page 5).
CROP_PAGES = {
    "SOJA": range(52, 56),
    "MILHO 2A SAFRA": range(46, 50),
}

STATES_IN_SCOPE = {"BA", "GO", "MG", "MS", "MT", "PR", "RS"}

# The calendar runs October to September, so Oct-Dec belong to the calendar year
# before the harvest year. Season 2023/24 -> harvest_year 2024, and its October
# is October 2023.
MONTH_ORDER = ["Out", "Nov", "Dez", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set"]
MONTH_NUMBER = {
    "Jan": 1, "Fev": 2, "Mar": 3, "Abr": 4, "Mai": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Set": 9, "Out": 10, "Nov": 11, "Dez": 12,
}

# Legend colours, identical across every page.
PHASE_BY_COLOUR = {
    (1.0, 0.612, 0.086): ("planting",),
    (0.137, 0.114, 0.741): ("harvest",),
    (0.137, 0.596, 0.306): ("planting", "harvest"),  # "Plantio/Colheita"
}

ALL_STATES = {
    "RO", "AC", "AM", "RR", "PA", "AP", "TO", "MA", "PI", "CE", "RN", "PB", "PE",
    "AL", "SE", "BA", "MG", "ES", "RJ", "SP", "PR", "SC", "RS", "MS", "MT", "GO", "DF",
}

# Legend swatches are ~12pt wide; real bars span at least one month column.
MIN_BAR_WIDTH = 20


def download_pdf() -> None:
    if PDF_PATH.exists():
        print(f"[calendar] cached: {PDF_PATH.name}")
        return
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"[calendar] downloading {PDF_URL}")
    response = requests.get(PDF_URL, timeout=300)
    response.raise_for_status()
    PDF_PATH.write_bytes(response.content)


def read_page(page) -> list[tuple[str, str, str]]:
    """Return (state, phase, month_name) for every coloured cell on the page."""
    words = page.extract_words()

    # Each table on the page has its own row of 12 month headers.
    header_rows: dict[float, list] = {}
    for word in words:
        if word["text"] in MONTH_ORDER:
            header_rows.setdefault(round(word["top"] / 5) * 5, []).append(word)
    tables = {top: hdr for top, hdr in header_rows.items() if len(hdr) == 12}

    states = [w for w in words if w["text"] in ALL_STATES and w["x0"] < 80]

    bars = [
        rect for rect in page.rects
        if tuple(rect.get("non_stroking_color") or ()) in PHASE_BY_COLOUR
        and (rect["x1"] - rect["x0"]) > MIN_BAR_WIDTH
    ]

    found = []
    for table_top, headers in sorted(tables.items()):
        month_centres = {w["text"]: (w["x0"] + w["x1"]) / 2 for w in headers}

        following = [t for t in sorted(tables) if t > table_top]
        table_bottom = min(following) if following else float("inf")
        table_states = [s for s in states if table_top < s["top"] < table_bottom]

        for state in table_states:
            state_centre_y = (state["top"] + state["bottom"]) / 2
            for bar in bars:
                if not bar["top"] <= state_centre_y <= bar["bottom"]:
                    continue
                phases = PHASE_BY_COLOUR[tuple(bar["non_stroking_color"])]
                for month, centre_x in month_centres.items():
                    if bar["x0"] <= centre_x <= bar["x1"]:
                        for phase in phases:
                            found.append((state["text"], phase, month))
    return found


def year_offset(month: str, months_in_phase: set[str]) -> int:
    """Which calendar year a month belongs to, relative to the harvest year.

    Oct-Dec are plainly the year before. The catch is the calendar's circularity:
    it is drawn Oct->Sep, so when planting starts in September the bar lands in
    the *last* column while meaning the September *before* October. Left as
    offset 0 that window would sit eleven months out of place.

    A month at the tail is folded back to the previous year only when it runs
    contiguously into October within the same phase. That keeps soybean planting
    in Mato Grosso (Sep-Dec) correct without touching safrinha corn harvest in
    Mato Grosso do Sul (Jun-Sep), where September genuinely is the harvest year.
    """
    if month in ("Out", "Nov", "Dez"):
        return -1
    if "Out" not in months_in_phase:
        return 0

    # Walk backwards from September while the phase stays unbroken.
    for position in range(len(MONTH_ORDER) - 1, 2, -1):
        candidate = MONTH_ORDER[position]
        if candidate not in months_in_phase:
            break
        if candidate == month:
            return -1
    return 0


def main() -> None:
    download_pdf()

    rows = set()
    with pdfplumber.open(PDF_PATH) as pdf:
        for crop, pages in CROP_PAGES.items():
            for page_number in pages:
                for state, phase, month in read_page(pdf.pages[page_number - 1]):
                    if state in STATES_IN_SCOPE:
                        rows.add((crop, state, phase, month))

    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SEED_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["crop_name", "state_code", "phase", "month_number", "year_offset"])
        for crop, state, phase, month in sorted(
            rows, key=lambda r: (r[0], r[1], r[2], MONTH_ORDER.index(r[3]))
        ):
            months_in_phase = {m for c, s, p, m in rows if (c, s, p) == (crop, state, phase)}
            offset = year_offset(month, months_in_phase)
            writer.writerow([crop, state, phase, MONTH_NUMBER[month], offset])

    print(f"[calendar] wrote {len(rows)} rows to {SEED_PATH.relative_to(PROJECT_ROOT)}")

    for crop in CROP_PAGES:
        states = sorted({r[1] for r in rows if r[0] == crop})
        print(f"[calendar] {crop}: {', '.join(states)}")


if __name__ == "__main__":
    main()
