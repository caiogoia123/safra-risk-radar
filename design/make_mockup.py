"""Gera o mockup SVG do redesenho da pagina do Safra Risk Radar.

Todo numero vem dos CSVs que o app publica -- o mockup nao inventa dado sobre o
proprio projeto, e reroda junto com os dados. Uso: `python design/make_mockup.py`.

O SVG sai com hex inline em cada elemento, sem var() e sem bloco <style>: o
Figma nao resolve nenhum dos dois e importaria o arquivo invisivel.
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = ROOT / "design" / "app-redesign-v2.svg"

# ------------------------------------------------------------------ paleta
# Identidade: violeta (slot 7) + laranja (slot 2). O par bate CVD dE 29,5 contra
# 9,1 do azul+laranja que estava aqui -- e nao e azul, que o Caio dispensou.
# Azul e vermelho continuam, mas so como PAR DIVERGENTE (seco/umido, abaixo/acima
# da tendencia): ali a cor marca polaridade, nao identidade de serie.
VIOLET, ORANGE, RED, BLUE = "#4a3aa7", "#eb6834", "#e34948", "#2a78d6"
INK, SOFT, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, RULE = "#e1e0d9", "#c3c2b7"
PAGE, CARD = "#f9f9f7", "#fcfcfb"
DARK, DARK_INK, DARK_SOFT = "#12120f", "#ffffff", "#c3c2b7"
FONT = "Segoe UI, system-ui, -apple-system, Helvetica, sans-serif"

W = 1440
M = 64          # margem lateral
CW = W - 2 * M  # 1312

out: list[str] = []


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, fill=SOFT, weight="400", anchor="start",
         spacing=None, opacity=None):
    extra = ""
    if spacing is not None:
        extra += f' letter-spacing="{spacing}"'
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    out.append(
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{extra}>{esc(s)}</text>'
    )


def rect(x, y, w, h, fill, r=0, stroke=None, sw=1, stroke_opacity=None, opacity=None):
    extra = ""
    if stroke:
        extra += f' stroke="{stroke}" stroke-width="{sw}"'
        if stroke_opacity is not None:
            extra += f' stroke-opacity="{stroke_opacity}"'
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
               f'rx="{r}" fill="{fill}"{extra}/>')


def line(x1, y1, x2, y2, stroke, sw=1, dash=None, cap=None, opacity=None):
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    if cap:
        extra += f' stroke-linecap="{cap}"'
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
               f'stroke="{stroke}" stroke-width="{sw}"{extra}/>')


def circle(cx, cy, r, fill, stroke=None, sw=2):
    extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"{extra}/>')


def vbar(x, y_base, value_px, w, fill, r=4):
    """Barra vertical divergente: ponta arredondada, base quadrada no zero."""
    if abs(value_px) < 0.6:
        return
    h = abs(value_px)
    rr = min(r, w / 2)
    x0, x1 = x - w / 2, x + w / 2
    if value_px < 0:                     # cresce para cima
        top = y_base - h
        p = (f"M{x0:.1f},{y_base:.1f} V{top + rr:.1f} Q{x0:.1f},{top:.1f} "
             f"{x0 + rr:.1f},{top:.1f} H{x1 - rr:.1f} Q{x1:.1f},{top:.1f} "
             f"{x1:.1f},{top + rr:.1f} V{y_base:.1f} Z")
    else:                                # cresce para baixo
        bot = y_base + h
        p = (f"M{x0:.1f},{y_base:.1f} V{bot - rr:.1f} Q{x0:.1f},{bot:.1f} "
             f"{x0 + rr:.1f},{bot:.1f} H{x1 - rr:.1f} Q{x1:.1f},{bot:.1f} "
             f"{x1:.1f},{bot - rr:.1f} V{y_base:.1f} Z")
    out.append(f'<path d="{p}" fill="{fill}"/>')


def card(x, y, w, h, fill=CARD, r=14):
    rect(x, y, w, h, fill, r=r, stroke=INK, sw=1, stroke_opacity=0.10)


def hbar(x0, y, value_px, h, fill, r=4, opacity=None):
    """Barra horizontal: canto arredondado so na ponta, quadrado na baseline."""
    if abs(value_px) < 0.6:
        return
    op = f' opacity="{opacity}"' if opacity is not None else ""
    d = 1 if value_px >= 0 else -1
    w = abs(value_px)
    rr = min(r, w)
    if d > 0:
        p = (f"M{x0:.1f},{y:.1f} H{x0 + w - rr:.1f} Q{x0 + w:.1f},{y:.1f} "
             f"{x0 + w:.1f},{y + rr:.1f} V{y + h - rr:.1f} "
             f"Q{x0 + w:.1f},{y + h:.1f} {x0 + w - rr:.1f},{y + h:.1f} H{x0:.1f} Z")
    else:
        p = (f"M{x0:.1f},{y:.1f} H{x0 - w + rr:.1f} Q{x0 - w:.1f},{y:.1f} "
             f"{x0 - w:.1f},{y + rr:.1f} V{y + h - rr:.1f} "
             f"Q{x0 - w:.1f},{y + h:.1f} {x0 - w + rr:.1f},{y + h:.1f} H{x0:.1f} Z")
    out.append(f'<path d="{p}" fill="{fill}"{op}/>')


# ------------------------------------------------------------------- dados
CROP_LABEL = {"SOJA": "Soybean", "MILHO 2A SAFRA": "Safrinha corn"}

bt = pd.read_csv(APP / "data/backtest.csv")
wide = bt.pivot_table(
    index=["crop_name", "state_code", "harvest_year", "actual_pct", "trend_kg_ha", "yield_kg_ha"],
    columns="role", values="predicted_pct").reset_index()
labels = ["Failure < -20%", "-20% to -10%", "Normal \u00b110%", "+10% to +20%", "Good > +20%"]
wide["severity"] = pd.cut(wide["actual_pct"], [-1000, -20, -10, 10, 20, 1000], labels=labels)

rmse = lambda e: float((e ** 2).mean() ** 0.5)
gains = []
for (crop, sev), g in wide.groupby(["crop_name", "severity"], observed=True):
    gains.append({"crop": CROP_LABEL[crop], "sev": str(sev), "n": len(g),
                  "gain": (1 - rmse(g["model"] - g["actual_pct"])
                           / rmse(g["baseline"] - g["actual_pct"])) * 100})
gains = pd.DataFrame(gains)

sr = pd.read_csv(APP / "data/season_risk.csv")
latest = sr["harvest_year"].max()
sub = sr[(sr["crop_name"] == "SOJA") & (sr["harvest_year"] < latest)]
expo = (sub.groupby("state_code")
        .apply(lambda g: g["precipitation_anomaly_z"].corr(g["yield_residual_pct"]),
               include_groups=False).sort_values())

fc = pd.read_csv(APP / "data/forecast.csv")
live = fc.dropna(subset=["desvio_previsto_pct"]).copy()
live["label"] = live["crop_name"].map(CROP_LABEL) + " \u00b7 " + live["state_code"]
live = live.sort_values("desvio_previsto_pct")

rs = wide[(wide["crop_name"] == "SOJA") & (wide["state_code"] == "RS")].sort_values("harvest_year")

# ===================================================================== canvas
H = 2150
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" font-family="{FONT}">')
rect(0, 0, W, H, PAGE)

# ---------------------------------------------------------------- 1. topbar
TB = 68
rect(0, 0, W, TB, DARK)
# marca: espiga estilizada
out.append(f'<g transform="translate({M},{TB/2 - 11})">'
           f'<path d="M11,22 V6" stroke="{ORANGE}" stroke-width="2" stroke-linecap="round"/>'
           f'<path d="M11,10 C6,10 3,7 3,3 C8,3 11,6 11,10 Z" fill="{ORANGE}"/>'
           f'<path d="M11,10 C16,10 19,7 19,3 C14,3 11,6 11,10 Z" fill="{ORANGE}" opacity="0.72"/>'
           f'<path d="M11,17 C6,17 3,14 3,10 C8,10 11,13 11,17 Z" fill="{ORANGE}" opacity="0.52"/>'
           f'<path d="M11,17 C16,17 19,14 19,10 C14,10 11,13 11,17 Z" fill="{ORANGE}" opacity="0.34"/>'
           f'</g>')
text(M + 34, TB / 2 + 5.5, "SAFRA RISK RADAR", size=15.5, fill=DARK_INK, weight="600", spacing="1.6")
text(M + 232, TB / 2 + 5, "Brazil \u00b7 soybean & safrinha corn", size=13, fill="#8f8e88")

right = W - M
for lbl in ["GitHub", "Method", "dbt \u00b7 BigQuery"]:
    w = len(lbl) * 7.0 + 10
    text(right, TB / 2 + 4.5, lbl, size=13, fill=DARK_SOFT, anchor="end")
    right -= w + 26
circle(right - 3, TB / 2, 4, "#0ca30c")
text(right - 14, TB / 2 + 4.5, "Weather through 3 Aug 2026", size=13, fill=DARK_SOFT, anchor="end")

# ------------------------------------------------------------------ 2. hero
y = TB + 52
text(M, y, "SOYBEAN & SAFRINHA CORN  \u00b7  7 STATES  \u00b7  1992\u20132026", size=12,
     fill=MUTED, weight="600", spacing="1.4")
y += 46
text(M, y, "Weather does not predict", size=42, fill=INK, weight="700")
y += 50
text(M, y, "the harvest. It predicts", size=42, fill=INK, weight="700")
y += 50
out.append(f'<text x="{M}" y="{y}" font-family="{FONT}" font-size="42" font-weight="700" '
           f'fill="{INK}">the harvests that <tspan fill="{RED}">fail</tspan>.</text>')

# O paragrafo sobe para a direita da manchete: sem o card ao lado, o hero
# ocupava meia pagina e deixava a outra metade vazia.
py = TB + 118
for ln in ["Averaged over every season this model ties with",
           "the trend baseline. Restricted to the seasons that",
           "actually broke, it removes 40% of the error \u2014 and",
           "flags about half of them in advance, against a",
           "baseline that by construction never flags one."]:
    text(816, py, ln, size=16, fill=SOFT)
    py += 27

# ------------------------------------------------------------- 3. stat tiles
SY = TB + 302
gap = 20
tw = (CW - 3 * gap) / 4
th = 132

tiles = [
    ("CROP FAILURES FLAGGED", "48%", "in advance \u00b7 baseline flags 0%"),
    ("ERROR REMOVED ON FAILURES", "40%", "soybean seasons >20% below trend"),
    ("SEASONS BACKTESTED", "23", "2003\u20132025 \u00b7 walk-forward refit"),
    ("DAILY WEATHER ROWS", "3.3M", "NASA POWER \u00b7 255 grid cells"),
]
for i, (lab, val, sub_) in enumerate(tiles):
    x = M + i * (tw + gap)
    card(x, SY, tw, th)
    text(x + 24, SY + 34, lab, size=11, fill=MUTED, weight="600", spacing="1.1")
    text(x + 24, SY + 82, val, size=44, fill=INK, weight="700")
    text(x + 24, SY + 108, sub_, size=12, fill=MUTED)

# --------------------------------------------------------- 4. safra em aberto
# Card de largura inteira sob os KPIs. Cabem as 11 previsoes em duas colunas,
# entao some o "+5 more states" que o card estreito precisava esconder.
FY = SY + th + 40
FH = 336
card(M, FY, CW, FH)
text(M + 28, FY + 42, "2025/26 \u2014 the season CONAB has not closed", size=19, fill=INK,
     weight="600")
text(M + 28, FY + 65, "Forecast deviation from each state's own yield trend. The weather in "
     "the critical window already happened and is measured; the official yield is still a survey.",
     size=13, fill=SOFT)

rows_per_col = 6
col_w = 600
fscale = 220 / 25.0                      # px por ponto percentual, igual nas duas colunas
for i, r in enumerate(live.itertuples()):
    col, row = divmod(i, rows_per_col)
    cx0 = M + 28 + col * (col_w + 56)
    zx_f = cx0 + 400
    yy = FY + 104 + row * 27
    if row == 0:
        line(zx_f, yy - 12, zx_f, yy + 12 + 27 * (rows_per_col - 1), RULE, 1)
        text(zx_f + 6, yy - 18, "trend", size=10.5, fill=MUTED)
    text(cx0, yy + 4, r.label, size=13, fill=SOFT)
    v = r.desvio_previsto_pct
    hbar(zx_f, yy - 5, v * fscale, 13, RED if v < -8 else "#ef8b8a")
    text(cx0 + col_w - 130, yy + 4, f"{v:.1f}%", size=13, fill=INK, weight="600", anchor="end")

fy = FY + FH - 44
line(M + 28, fy - 16, M + CW - 28, fy - 16, GRID, 1)
circle(M + 34, fy + 4, 4.5, "#fab219")
text(M + 48, fy + 8, "PR and MS withheld \u2014 their critical windows run into August and the "
     "weather series ends 3 Aug 2026, so the window is only 82\u201385% covered. A truncated "
     "window reads to the model as an extreme drought.", size=12.5, fill=SOFT)

# ------------------------------------------------- 5. severity + exposure row
RY = FY + FH + 40
RH = 442
LW = 800
card(M, RY, LW, RH)
text(M + 28, RY + 40, "The model earns its keep only in the tail", size=19, fill=INK, weight="600")
text(M + 28, RY + 63, "Error removed versus the trend baseline, by how far the season really fell.",
     size=13, fill=SOFT)
text(M + 28, RY + 82, "Ordinary seasons are 55% of the sample \u2014 which is why the average looks like a tie.",
     size=13, fill=SOFT)

# legenda
lx = M + 28
for name, col in [("Soybean", VIOLET), ("Safrinha corn", ORANGE)]:
    circle(lx + 5, RY + 108, 5, col)
    text(lx + 17, RY + 112, name, size=12.5, fill=SOFT)
    lx += 17 + len(name) * 6.9 + 26

# plot
px0, px1 = M + 204, M + LW - 96
py0 = RY + 132
plot_h = RH - 132 - 44
vmin, vmax = -72.0, 44.0
sx = (px1 - px0) / (vmax - vmin)
zx = px0 + (0 - vmin) * sx

# zona "pior que a baseline"
rect(px0, py0, zx - px0, plot_h, RED, r=0, opacity=0.045)
text(px0 + 12, py0 + plot_h + 42, "worse than baseline", size=11.5, fill=MUTED)
text(px1 - 6, py0 + plot_h + 42, "better than baseline", size=11.5, fill=MUTED, anchor="end")

for v in [-60, -40, -20, 20, 40]:
    gx = px0 + (v - vmin) * sx
    line(gx, py0, gx, py0 + plot_h, GRID, 1)
    text(gx, py0 + plot_h + 20, f"{v:+d}%", size=11.5, fill=MUTED, anchor="middle")
line(zx, py0, zx, py0 + plot_h, RULE, 1)
text(zx, py0 + plot_h + 20, "0", size=11.5, fill=MUTED, anchor="middle")

band = plot_h / len(labels)
for i, sev in enumerate(labels):
    cy = py0 + band * i
    text(px0 - 18, cy + band / 2 - 2, sev, size=12.5, fill=SOFT, anchor="end")
    n_soy = int(gains[(gains.crop == "Soybean") & (gains.sev == sev)]["n"].iloc[0])
    n_cor = int(gains[(gains.crop == "Safrinha corn") & (gains.sev == sev)]["n"].iloc[0])
    text(px0 - 18, cy + band / 2 + 15, f"n = {n_soy + n_cor}", size=11, fill=MUTED, anchor="end")
    for j, (crop, col) in enumerate([("Soybean", VIOLET), ("Safrinha corn", ORANGE)]):
        v = float(gains[(gains.crop == crop) & (gains.sev == sev)]["gain"].iloc[0])
        by = cy + band / 2 - 22 + j * 22          # 2px de respiro entre as barras
        hbar(zx, by, v * sx, 20, col)
        tip = zx + v * sx
        # Barra longa a esquerda nao tem espaco fora da ponta sem bater no rotulo
        # da categoria: o valor entra na barra, em branco.
        inside = v < 0 and (tip - px0) < 60 and abs(v * sx) > 40
        if inside:
            text(tip + 10, by + 14, f"{v:+.0f}%", size=12, fill="#ffffff", weight="600")
        else:
            text(tip + (10 if v >= 0 else -10), by + 14, f"{v:+.0f}%", size=12,
                 fill=INK if abs(v) > 25 else SOFT, weight="600",
                 anchor="start" if v >= 0 else "end")

# --- exposure
EX = M + LW + 24
EW = CW - LW - 24
card(EX, RY, EW, RH)
text(EX + 28, RY + 40, "Exposure is not national", size=19, fill=INK, weight="600")
text(EX + 28, RY + 63, "Correlation between rainfall anomaly in the critical", size=13, fill=SOFT)
text(EX + 28, RY + 82, "window and the yield residual, soybean. Rio Grande", size=13, fill=SOFT)
text(EX + 28, RY + 101, "do Sul is four times as sensitive as Mato Grosso —", size=13, fill=SOFT)
text(EX + 28, RY + 120, "a national average erases this entirely.", size=13, fill=SOFT)

ex0, ex1 = EX + 78, EX + EW - 78
ey0 = RY + 158
eh = RH - 158 - 56
emax = 0.56
esx = (ex1 - ex0) / emax
for v in [0.2, 0.4]:
    gx = ex0 + v * esx
    line(gx, ey0, gx, ey0 + eh, GRID, 1)
    text(gx, ey0 + eh + 20, f"{v:.1f}", size=11.5, fill=MUTED, anchor="middle")
line(ex0, ey0, ex0, ey0 + eh, RULE, 1)
text(ex0, ey0 + eh + 20, "0", size=11.5, fill=MUTED, anchor="middle")

eband = eh / len(expo)
for i, (st, v) in enumerate(expo.items()):
    cy = ey0 + eband * i + eband / 2 - 9
    strongest = st == expo.index[-1]
    text(EX + 60, cy + 13, st, size=13, fill=INK if strongest else SOFT,
         weight="600" if strongest else "400", anchor="end")
    # Uma serie so: mesma cor em todas, e o RS ganha enfase por opacidade cheia
    # em vez de um hex novo -- o comprimento ja e quem carrega a magnitude.
    hbar(ex0, cy, v * esx, 18, VIOLET, opacity=None if strongest else 0.42)
    text(ex0 + v * esx + 10, cy + 13, f"{v:.2f}", size=12,
         fill=INK if strongest else MUTED, weight="600" if strongest else "400")

text(EX + 28, ey0 + eh + 48, "Pearson r, soybean yield residual × rainfall anomaly (z), "
     "1992–2025.", size=11.5, fill=MUTED)

# ------------------------------------------------------------- 5. season chart
QY = RY + RH + 40
QH = 578
card(M, QY, CW, QH)
text(M + 28, QY + 42, "Season by season", size=19, fill=INK, weight="600")
text(M + 28, QY + 65, "Circled seasons are the ones the model called 10% or more below trend, "
     "using only weather and seasons that preceded them.", size=13, fill=SOFT)

cx = M + CW - 28
for lbl, active in [("Rio Grande do Sul", False), ("Soybean", True)]:
    w = 28 + len(lbl) * 7.0
    x = cx - w
    rect(x, QY + 26, w, 32, INK if active else "#ffffff", r=16,
         stroke=None if active else INK, sw=1, stroke_opacity=None if active else 0.12)
    text(x + w / 2, QY + 47, lbl, size=13, fill="#ffffff" if active else SOFT,
         weight="600" if active else "400", anchor="middle")
    cx = x - 10

sx0, sx1 = M + 88, M + CW - 56
sy0 = QY + 104
sh = 262
ymax = 3600.0
years = rs["harvest_year"].tolist()
xs = {yr: sx0 + (yr - years[0]) / (years[-1] - years[0]) * (sx1 - sx0) for yr in years}
ypx = lambda v: sy0 + sh - (v / ymax) * sh

for tick in [0, 1000, 2000, 3000]:
    gy = ypx(tick)
    line(sx0, gy, sx1, gy, GRID, 1)
    text(sx0 - 14, gy + 4, f"{tick:,}", size=11.5, fill=MUTED, anchor="end")
text(sx0 - 14, ypx(3600) - 6, "kg/ha", size=11, fill=MUTED, anchor="end")
line(sx0, sy0 + sh, sx1, sy0 + sh, RULE, 1)
for yr in years:
    if yr % 5 == 0:
        text(xs[yr], sy0 + sh + 22, str(yr), size=11.5, fill=MUTED, anchor="middle")

trend_pts = " ".join(f"{xs[r.harvest_year]:.1f},{ypx(r.trend_kg_ha):.1f}" for r in rs.itertuples())
out.append(f'<polyline points="{trend_pts}" fill="none" stroke="{MUTED}" stroke-width="2" '
           f'stroke-linejoin="round" stroke-linecap="round"/>')
act_pts = " ".join(f"{xs[r.harvest_year]:.1f},{ypx(r.yield_kg_ha):.1f}" for r in rs.itertuples())
out.append(f'<polyline points="{act_pts}" fill="none" stroke="{VIOLET}" stroke-width="2" '
           f'stroke-linejoin="round" stroke-linecap="round"/>')

for r in rs.itertuples():
    px, py = xs[r.harvest_year], ypx(r.yield_kg_ha)
    if r.model <= -10:
        circle(px, py, 10, "none", stroke=ORANGE, sw=2.5)
    circle(px, py, 4.5, VIOLET, stroke=CARD, sw=2)

# Anotacoes: um acerto grande e um falso alarme. As duas caem no vazio sob a
# serie -- a direita do ponto o texto sairia do card.
ax, ay = xs[2020], ypx(1939)
line(ax - 6, ay + 16, ax - 14, ay + 50, RULE, 1)
text(ax - 20, ay + 60, "2020 \u00b7 driest window in the record", size=12, fill=INK,
     weight="600", anchor="end")
text(ax - 20, ay + 77, "called 42% low, came in 35% low", size=12, fill=MUTED, anchor="end")

bx, by = xs[2007], ypx(2550)
line(bx, by - 14, bx, by - 44, RULE, 1)
text(bx - 6, by - 50, "2007 \u00b7 false alarm", size=12, fill=INK, weight="600", anchor="middle")
text(bx - 6, by - 33, "flagged, came in 56% above trend", size=12, fill=MUTED, anchor="middle")

# --- faixa climatica: a variavel de entrada, no mesmo eixo de tempo.
# Nao e um segundo eixo y no mesmo plot: e outro painel, com sua propria escala.
anom = (sr[(sr["crop_name"] == "SOJA") & (sr["state_code"] == "RS")
           & (sr["harvest_year"].between(years[0], years[-1]))]
        .set_index("harvest_year")["dry_days_anomaly_z"])
ay0 = sy0 + sh + 60
zline = ay0 + 42
text(sx0, ay0 - 16, "Dry-day anomaly in the critical window, in standard deviations — "
     "the input the model actually reads", size=12, fill=SOFT)
text(sx0 - 14, zline - 28, "drier", size=10.5, fill=MUTED, anchor="end")
text(sx0 - 14, zline + 34, "wetter", size=10.5, fill=MUTED, anchor="end")
line(sx0, zline, sx1, zline, RULE, 1)
zscale = 40 / 2.3
for yr, v in anom.items():
    # z positivo = mais dias secos que o normal, e sobe: o eixo cresce para cima
    vbar(xs[yr], zline, -v * zscale, 14, RED if v > 0 else BLUE)

# legenda do season chart
ly = QY + QH - 30
lx = sx0
for name, col, kind in [("Actual yield", VIOLET, "line"), ("Trend (baseline)", MUTED, "line"),
                        ("Model flagged a failure", ORANGE, "ring"),
                        ("Drier than normal", RED, "swatch"), ("Wetter", BLUE, "swatch")]:
    if kind == "line":
        line(lx, ly, lx + 16, ly, col, 2, cap="round")
        circle(lx + 8, ly, 4, col)
    elif kind == "ring":
        circle(lx + 8, ly, 7, "none", stroke=col, sw=2.5)
    else:
        rect(lx + 2, ly - 6, 12, 12, col, r=3)
    text(lx + 24, ly + 4, name, size=12.5, fill=SOFT)
    lx += 24 + len(name) * 6.9 + 26

# ------------------------------------------------------------- 6. pipeline bar
PY = QY + QH + 40
PH = 132
rect(0, PY, W, PH, DARK)
text(M, PY + 42, "PIPELINE", size=11, fill="#8f8e88", weight="600", spacing="1.4")

steps = ["CONAB \u00b7 IBGE \u00b7 NASA POWER", "Python ingestion", "DuckDB (dev) \u00b7 BigQuery (prod)",
         "dbt \u00b7 78 tests", "scikit-learn", "Streamlit"]
sx = M
for i, s in enumerate(steps):
    w = len(s) * 7.1 + 34
    rect(sx, PY + 60, w, 36, "#1e1e1a", r=18, stroke="#ffffff", sw=1, stroke_opacity=0.10)
    text(sx + w / 2, PY + 83, s, size=12.5, fill=DARK_SOFT, anchor="middle")
    sx += w
    if i < len(steps) - 1:
        line(sx + 8, PY + 78, sx + 22, PY + 78, "#5a5954", 1.5, cap="round")
        out.append(f'<path d="M{sx + 18:.1f},{PY + 74:.1f} L{sx + 23:.1f},{PY + 78:.1f} '
                   f'L{sx + 18:.1f},{PY + 82:.1f}" fill="none" stroke="#5a5954" '
                   f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>')
        sx += 30

text(W - M, PY + 83, "Built by Caio Goia", size=12.5, fill="#8f8e88", anchor="end")

out.append("</svg>")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(out), encoding="utf-8")
print("ok", OUT, len("\n".join(out)), "bytes", "| altura usada:", PY + PH)
