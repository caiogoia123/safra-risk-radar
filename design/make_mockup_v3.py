"""Gera a v3 do mockup da pagina do Safra Risk Radar.

Diferencas para a v2 (que continua em make_mockup.py / app-redesign-v2.svg):
  - manchete em UMA linha, com a descricao logo abaixo;
  - a safra aberta 2025/26 vira um card estreito COM SCROLL, na mesma linha do
    grafico de severidade, em vez de uma faixa de largura inteira;
  - exposicao por estado em barras EM PE, ocupando a largura toda;
  - "Season by season" sem anotacao dentro do plot, com a legenda antes do grafico.

Todo numero vem dos CSVs que o app publica. Uso: `python design/make_mockup_v3.py`.
O SVG sai com hex inline em cada elemento, sem var() e sem bloco <style>: o Figma
nao resolve nenhum dos dois e importaria o arquivo invisivel.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = ROOT / "design" / "app-redesign-v3.svg"

# ------------------------------------------------------------------ paleta
# Identidade: violeta (slot 7) + laranja (slot 2) -- CVD dE 29,5, contra 9,1 do
# azul+laranja. Azul e vermelho seguem no projeto, mas so como PAR DIVERGENTE
# (seco/umido): ali a cor marca polaridade, nao identidade de serie.
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

# ------------------------------------------------------------------ medicao
# Largura de texto medida na fonte real, nao estimada por contagem de char: e
# o que garante que chip, legenda e rotulo de barra nao se sobreponham.
try:
    from PIL import ImageFont

    _FACES = {"400": "C:/Windows/Fonts/segoeui.ttf",
              "600": "C:/Windows/Fonts/seguisb.ttf",
              "700": "C:/Windows/Fonts/segoeuib.ttf"}
    _cache: dict[tuple[str, int], object] = {}

    def measure(s: str, size: float, weight: str = "400") -> float:
        key = (weight, round(size * 4))
        if key not in _cache:
            _cache[key] = ImageFont.truetype(_FACES.get(weight, _FACES["400"]), round(size * 4))
        return _cache[key].getlength(s) / 4
except Exception:                                   # sem PIL: estimativa grosseira
    def measure(s: str, size: float, weight: str = "400") -> float:
        return len(s) * size * 0.52


# A pagina pode ser aberta onde nao ha Segoe UI, e a fonte substituta e mais
# larga: o subtitulo da exposicao coube na medicao e vazou do card no navegador
# do Caio. Toda largura calculada aqui leva essa folga.
SAFETY = 1.12
RIGHT_EDGE = W - M - 28          # borda util: card menos o padding interno
_emitted: list[tuple[float, float, str, str, str]] = []


def wrap(s: str, max_w: float, size: float, weight: str = "400") -> list[str]:
    """Quebra o texto so quando a linha encosta na largura dada (com folga)."""
    max_w /= SAFETY
    lines_, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and measure(trial, size, weight) > max_w:
            lines_.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines_.append(cur)
    return lines_


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, fill=SOFT, weight="400", anchor="start",
         spacing=None, opacity=None):
    extra = ""
    if spacing is not None:
        extra += f' letter-spacing="{spacing}"'
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    _emitted.append((x, size, weight, anchor, s))
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


def line(x1, y1, x2, y2, stroke, sw=1, cap=None, opacity=None):
    extra = f' stroke-linecap="{cap}"' if cap else ""
    if opacity is not None:
        extra += f' opacity="{opacity}"'
    out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
               f'stroke="{stroke}" stroke-width="{sw}"{extra}/>')


def circle(cx, cy, r, fill, stroke=None, sw=2):
    extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"{extra}/>')


def card(x, y, w, h, fill=CARD, r=14):
    rect(x, y, w, h, fill, r=r, stroke=INK, sw=1, stroke_opacity=0.10)


def hbar(x0, y, value_px, h, fill, r=4, opacity=None):
    """Barra horizontal: canto arredondado so na ponta, quadrado na baseline."""
    if abs(value_px) < 0.6:
        return
    op = f' opacity="{opacity}"' if opacity is not None else ""
    w = abs(value_px)
    rr = min(r, w)
    if value_px >= 0:
        p = (f"M{x0:.1f},{y:.1f} H{x0 + w - rr:.1f} Q{x0 + w:.1f},{y:.1f} "
             f"{x0 + w:.1f},{y + rr:.1f} V{y + h - rr:.1f} "
             f"Q{x0 + w:.1f},{y + h:.1f} {x0 + w - rr:.1f},{y + h:.1f} H{x0:.1f} Z")
    else:
        p = (f"M{x0:.1f},{y:.1f} H{x0 - w + rr:.1f} Q{x0 - w:.1f},{y:.1f} "
             f"{x0 - w:.1f},{y + rr:.1f} V{y + h - rr:.1f} "
             f"Q{x0 - w:.1f},{y + h:.1f} {x0 - w + rr:.1f},{y + h:.1f} H{x0:.1f} Z")
    out.append(f'<path d="{p}" fill="{fill}"{op}/>')


def vbar(x, y_base, value_px, w, fill, r=4, opacity=None):
    """Barra vertical: ponta arredondada, base quadrada na linha de zero."""
    if abs(value_px) < 0.6:
        return
    op = f' opacity="{opacity}"' if opacity is not None else ""
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
    out.append(f'<path d="{p}" fill="{fill}"{op}/>')


def legend(x, y, items, size=12.5, gap=26):
    """Legenda horizontal. Cada item: (rotulo, cor, forma)."""
    for label_, col, kind in items:
        if kind == "line":
            line(x, y, x + 16, y, col, 2, cap="round")
            circle(x + 8, y, 4, col)
        elif kind == "ring":
            circle(x + 8, y, 7, "none", stroke=col, sw=2.5)
        else:
            rect(x + 2, y - 6, 12, 12, col, r=3)
        text(x + 24, y + 4, label_, size=size, fill=SOFT)
        x += 24 + measure(label_, size) + gap
    return x


# ------------------------------------------------------------------- dados
CROP_LABEL = {"SOJA": "Soybean", "MILHO 2A SAFRA": "Safrinha corn"}

# Limiares em um lugar so: o texto da pagina, o rotulo das faixas e o filtro
# que desenha os aneis saem daqui. Escritos duas vezes, divergem na primeira
# vez que alguem mexer em um deles.
FLAG_PCT = -10              # abaixo disso o modelo chama "quebra"
FAIL_PCT = -20              # abaixo disso a quebra e severa

bt = pd.read_csv(APP / "data/backtest.csv")
wide = bt.pivot_table(
    index=["crop_name", "state_code", "harvest_year", "actual_pct", "trend_kg_ha", "yield_kg_ha"],
    columns="role", values="predicted_pct").reset_index()
bins = [-1000, FAIL_PCT, FLAG_PCT, -FLAG_PCT, -FAIL_PCT, 1000]
labels = [f"Failure < {FAIL_PCT}%", f"{FAIL_PCT}% to {FLAG_PCT}%",
          f"Normal ±{abs(FLAG_PCT)}%", f"+{abs(FLAG_PCT)}% to +{abs(FAIL_PCT)}%",
          f"Good > +{abs(FAIL_PCT)}%"]
wide["severity"] = pd.cut(wide["actual_pct"], bins, labels=labels)

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

FOCUS_STATE = "RS"          # o estado que o explorador abre, igual ao app
rs = wide[(wide["crop_name"] == "SOJA")
          & (wide["state_code"] == FOCUS_STATE)].sort_values("harvest_year")

# --------------------------------------------------------------- metricas
# Regra do projeto: nada que a pagina afirma sobre o dado pode ser digitado a
# mao. Tudo abaixo e derivado; o que NAO da para derivar dos CSVs esta na
# secao "fixos" logo adiante, isolado e comentado.
STATE_NAME = {"BA": "Bahia", "GO": "Goiás", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul",
              "MT": "Mato Grosso", "PR": "Paraná", "RS": "Rio Grande do Sul"}

meta = json.loads((APP / "data/meta.json").read_text(encoding="utf-8"))
weather_through = date.fromisoformat(meta["weather_through"])
# "%-d" nao existe no Windows e "%d" preenche com zero: tirar o zero na mao.
weather_label = weather_through.strftime("%d %b %Y").lstrip("0")
weather_rows_label = f"{meta['weather_rows'] / 1e6:.1f}M"

n_states = sr["state_code"].nunique()
first_season, open_season = int(sr["harvest_year"].min()), int(sr["harvest_year"].max())
open_label = f"{open_season - 1}/{str(open_season)[2:]}"
first_scored, last_scored = int(wide["harvest_year"].min()), int(wide["harvest_year"].max())
n_seasons = wide["harvest_year"].nunique()

failures = wide[wide["actual_pct"] <= FLAG_PCT]
called = failures[failures["model"] <= FLAG_PCT]
recall_pct = len(called) / len(failures) * 100
n_flags = int((wide["model"] <= FLAG_PCT).sum())
false_alarm_pct = (1 - len(called) / n_flags) * 100

worst_soy = wide[(wide["crop_name"] == "SOJA") & (wide["severity"] == labels[0])]
soy_gain = (1 - rmse(worst_soy["model"] - worst_soy["actual_pct"])
            / rmse(worst_soy["baseline"] - worst_soy["actual_pct"])) * 100
ordinary_pct = (wide["severity"] == labels[2]).sum() / len(wide) * 100

n_scored, n_total = len(live), len(fc)
expo_lo, expo_hi = expo.index[0], expo.index[-1]
expo_ratio = expo.iloc[-1] / expo.iloc[0]
expo_first, expo_last = int(sub["harvest_year"].min()), int(sub["harvest_year"].max())

# --- fixos: nao existem nos CSVs que o app publica. Para sair daqui, teriam de
# entrar em app/data/meta.json (celulas) ou ser lidos do dbt (contagem de testes).
GRID_CELLS = 255            # celulas NASA POWER sobre os municipios produtores
DBT_TESTS = 78              # testes do projeto dbt

# ===================================================================== canvas
H = 2028
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}" font-family="{FONT}">')
# Fade no fim da lista rolavel -- gradiente com id o Figma resolve; var() nao.
out.append(f'<defs><linearGradient id="fadeOut" x1="0" y1="0" x2="0" y2="1">'
           f'<stop offset="0" stop-color="{CARD}" stop-opacity="0"/>'
           f'<stop offset="1" stop-color="{CARD}" stop-opacity="1"/></linearGradient></defs>')
rect(0, 0, W, H, PAGE)

# ---------------------------------------------------------------- 1. topbar
TB = 68
rect(0, 0, W, TB, DARK)
out.append(f'<g transform="translate({M},{TB / 2 - 11})">'
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
    text(right, TB / 2 + 4.5, lbl, size=13, fill=DARK_SOFT, anchor="end")
    right -= measure(lbl, 13) + 32
circle(right - 3, TB / 2, 4, "#0ca30c")
text(right - 14, TB / 2 + 4.5, f"Weather through {weather_label}", size=13,
     fill=DARK_SOFT, anchor="end")

# ------------------------------------------------------------------ 2. hero
# Manchete inteira em uma linha: a 38px ela mede 1258 dos 1312 disponiveis.
y = TB + 52
text(M, y, f"SOYBEAN & SAFRINHA CORN  \u00b7  {n_states} STATES  \u00b7  "
     f"{first_season}\u2013{open_season}", size=12, fill=MUTED, weight="600", spacing="1.4")

y += 52
head_a, head_b = "Weather does not predict the harvest. It predicts the harvests that ", "fail"
HEAD_SIZE = 34            # o maior corpo que cabe em uma linha com a folga
_emitted.append((M, HEAD_SIZE, "700", "start", head_a + head_b + "."))
out.append(f'<text x="{M}" y="{y}" font-family="{FONT}" font-size="{HEAD_SIZE}" '
           f'font-weight="700" fill="{INK}">{esc(head_a)}'
           f'<tspan fill="{RED}">{head_b}</tspan>.</text>')

y += 42
for ln in ["Averaged over every season this model ties with the trend baseline. Restricted to the "
           "seasons that actually broke, it removes",
           f"{soy_gain:.0f}% of the error \u2014 and flags {recall_pct:.0f}% of them in advance, "
           "against a baseline that by construction never flags one."]:
    text(M, y, ln, size=16, fill=SOFT)
    y += 27

# ------------------------------------------------------------- 3. stat tiles
SY = y + 34
gap = 20
tw = (CW - 3 * gap) / 4
th = 132

tiles = [
    ("CROP FAILURES FLAGGED", f"{recall_pct:.0f}%", "in advance \u00b7 baseline flags 0%"),
    ("ERROR REMOVED ON FAILURES", f"{soy_gain:.0f}%",
     f"soybean seasons >{abs(FAIL_PCT)}% below trend"),
    ("SEASONS BACKTESTED", f"{n_seasons}",
     f"{first_scored}\u2013{last_scored} \u00b7 walk-forward refit"),
    ("DAILY WEATHER ROWS", weather_rows_label,
     f"NASA POWER \u00b7 {GRID_CELLS} grid cells"),
]
for i, (lab, val, sub_) in enumerate(tiles):
    x = M + i * (tw + gap)
    card(x, SY, tw, th)
    text(x + 24, SY + 34, lab, size=11, fill=MUTED, weight="600", spacing="1.1")
    text(x + 24, SY + 82, val, size=44, fill=INK, weight="700")
    text(x + 24, SY + 108, sub_, size=12, fill=MUTED)

# ------------------------------------- 4. safra aberta (rolavel) + severidade
RY = SY + th + 40
RH = 424
FW = 500                      # card estreito: a lista rola, nao empurra a pagina
SW_ = CW - FW - 24

# --- 4a. a safra que a CONAB nao fechou
card(M, RY, FW, RH)
text(M + 26, RY + 40, f"{open_label} \u2014 the season CONAB has not closed", size=17,
     fill=INK, weight="600")
text(M + 26, RY + 63, "Forecast deviation from each state's own", size=13, fill=SOFT)
text(M + 26, RY + 82, f"yield trend. {n_scored} of {n_total} states scored.", size=13,
     fill=SOFT)

vis_rows = 8                                     # 8 de 11 visiveis; o resto rola
row_h = 32
list_top = RY + 104
list_h = vis_rows * row_h
zx_f = M + 26 + 300
text(zx_f, list_top - 8, "trend", size=10.5, fill=MUTED, anchor="middle")
line(zx_f, list_top, zx_f, list_top + list_h - 8, RULE, 1)

fscale = 190 / 23.0
for i, r in enumerate(live.head(vis_rows).itertuples()):
    yy = list_top + i * row_h
    text(M + 26, yy + 20, r.label, size=13, fill=SOFT)
    v = r.desvio_previsto_pct
    hbar(zx_f, yy + 11, v * fscale, 13, RED if v < -8 else "#ef8b8a")
    text(M + FW - 26, yy + 20, f"{v:.1f}%", size=13, fill=INK, weight="600", anchor="end")

# fade + trilha de scroll: a lista continua abaixo do corte
rect(M + 1, list_top + list_h - 34, FW - 2, 34, "url(#fadeOut)")
track_x = M + FW - 15
rect(track_x, list_top, 5, list_h - 8, GRID, r=2.5)
rect(track_x, list_top, 5, (list_h - 8) * vis_rows / len(live), MUTED, r=2.5)
text(M + 26, RY + RH - 24, f"scroll for {len(live) - vis_rows} more", size=11.5, fill=MUTED)

# --- 4b. onde o modelo ganha
SX = M + FW + 24
card(SX, RY, SW_, RH)
text(SX + 28, RY + 40, "The model earns its keep only in the tail", size=17, fill=INK, weight="600")
text(SX + 28, RY + 63, "Error removed versus the trend baseline, by how far the season really fell.",
     size=13, fill=SOFT)
text(SX + 28, RY + 82, f"Ordinary seasons are {ordinary_pct:.0f}% of the sample \u2014 which is"
     " why the average looks like a tie.", size=13, fill=SOFT)
legend(SX + 28, RY + 108, [("Soybean", VIOLET, "swatch"), ("Safrinha corn", ORANGE, "swatch")])

px0, px1 = SX + 150, SX + SW_ - 84
py0 = RY + 136
plot_h = RH - 136 - 56
# Faixa do eixo derivada do dado, com folga de 10%: um limite digitado corta a
# barra maior sem nenhum aviso.
vspan = max(abs(gains['gain'].min()), abs(gains['gain'].max())) * 1.10
vmin, vmax = -vspan, vspan * 0.62
sx = (px1 - px0) / (vmax - vmin)
zx = px0 + (0 - vmin) * sx

rect(px0, py0, zx - px0, plot_h, RED, opacity=0.045)
text(px0 + 10, py0 + plot_h + 42, "worse than baseline", size=11.5, fill=MUTED)
text(px1 - 4, py0 + plot_h + 42, "better than baseline", size=11.5, fill=MUTED, anchor="end")

for v in [-60, -40, -20, 20, 40]:
    gx = px0 + (v - vmin) * sx
    line(gx, py0, gx, py0 + plot_h, GRID, 1)
    text(gx, py0 + plot_h + 20, f"{v:+d}%", size=11.5, fill=MUTED, anchor="middle")
line(zx, py0, zx, py0 + plot_h, RULE, 1)
text(zx, py0 + plot_h + 20, "0", size=11.5, fill=MUTED, anchor="middle")

band = plot_h / len(labels)
for i, sev in enumerate(labels):
    cy = py0 + band * i
    text(px0 - 16, cy + band / 2 - 2, sev, size=12.5, fill=SOFT, anchor="end")
    n_tot = int(gains[gains.sev == sev]["n"].sum())
    text(px0 - 16, cy + band / 2 + 15, f"n = {n_tot}", size=11, fill=MUTED, anchor="end")
    for j, (crop, col) in enumerate([("Soybean", VIOLET), ("Safrinha corn", ORANGE)]):
        v = float(gains[(gains.crop == crop) & (gains.sev == sev)]["gain"].iloc[0])
        by = cy + band / 2 - 21 + j * 21          # 2px de respiro entre as barras
        hbar(zx, by, v * sx, 19, col)
        tip = zx + v * sx
        # Barra longa a esquerda nao tem espaco fora da ponta sem bater no
        # rotulo da categoria: o valor entra na barra, em branco.
        if v < 0 and (tip - px0) < 60 and abs(v * sx) > 40:
            text(tip + 10, by + 14, f"{v:+.0f}%", size=12, fill="#ffffff", weight="600")
        else:
            text(tip + (10 if v >= 0 else -10), by + 14, f"{v:+.0f}%", size=12,
                 fill=INK if abs(v) > 25 else SOFT, weight="600",
                 anchor="start" if v >= 0 else "end")

# ------------------------------------------- 5. exposicao, barras em pe
# Subtitulo em cima do grafico, na largura inteira do card: quebra so quando
# encosta na borda, medido na fonte real.
EY = RY + RH + 40
sub_lines = wrap(
    f"Correlation between rainfall anomaly in the critical window and the yield residual, "
    f"soybean. {STATE_NAME[expo_hi]} is {expo_ratio:.0f} times as sensitive as "
    f"{STATE_NAME[expo_lo]} — a national average erases this entirely. "
    f"Pearson r, {expo_first}–{expo_last}.", CW - 56, 13)
EH = 300 + 19 * len(sub_lines)
card(M, EY, CW, EH)
text(M + 28, EY + 42, "Exposure is not national", size=17, fill=INK, weight="600")
for i, ln in enumerate(sub_lines):
    text(M + 28, EY + 68 + i * 19, ln, size=13, fill=SOFT)

ex0, ex1 = M + 76, M + CW - 32
ebase = EY + EH - 62                 # linha de base das colunas
etop = EY + 78 + 19 * len(sub_lines)
# O teto do eixo sai do dado, com folga: um teto digitado corta a barra maior e
# ainda renderiza, subestimando em silencio justo o estado que o grafico existe
# para apontar.
emax = max(0.6, float(expo.max()) * 1.15)
tick = 0.2
ticks, t = [], 0.0
while t <= emax:
    ticks.append(round(t, 1))
    t += tick
for tv in ticks:
    gy = ebase - tv / emax * (ebase - etop)
    line(ex0 - 24, gy, ex1, gy, GRID if tv else RULE, 1)
    text(ex0 - 34, gy + 4, f"{tv:.1f}", size=11.5, fill=MUTED, anchor="end")

eband = (ex1 - ex0) / len(expo)
for i, (st, v) in enumerate(expo.items()):
    cx = ex0 + eband * (i + 0.5)
    strongest = st == expo.index[-1]
    h = v / emax * (ebase - etop)
    vbar(cx, ebase, -h, 24, VIOLET, opacity=None if strongest else 0.42)
    text(cx, ebase - h - 12, f"{v:.2f}", size=13, fill=INK if strongest else MUTED,
         weight="600" if strongest else "400", anchor="middle")
    text(cx, ebase + 24, st, size=13, fill=INK if strongest else SOFT,
         weight="600" if strongest else "400", anchor="middle")

# ------------------------------------------------------------- 6. season chart
QY = EY + EH + 40
QH = 540
card(M, QY, CW, QH)
text(M + 28, QY + 42, "Season by season", size=17, fill=INK, weight="600")
text(M + 28, QY + 65, f"Circled seasons are the ones the model called {abs(FLAG_PCT)}% or more below"
     " trend, using only weather and seasons that preceded them.", size=13, fill=SOFT)
text(M + 28, QY + 84, f"About {false_alarm_pct:.0f}% of the calls are false alarms, and they are left in on purpose.",
     size=13, fill=SOFT)
legend(M + 28, QY + 116, [("Actual yield", VIOLET, "line"), ("Trend (baseline)", MUTED, "line"),
                         ("Model flagged a failure", ORANGE, "ring"),
                         ("Drier than normal", RED, "swatch"), ("Wetter", BLUE, "swatch")])

cx = M + CW - 28
for lbl, active in [(STATE_NAME[FOCUS_STATE], False), ("Soybean", True)]:
    w = 30 + measure(lbl, 13, "600" if active else "400")
    x = cx - w
    rect(x, QY + 26, w, 32, INK if active else "#ffffff", r=16,
         stroke=None if active else INK, sw=1, stroke_opacity=None if active else 0.12)
    text(x + w / 2, QY + 47, lbl, size=13, fill="#ffffff" if active else SOFT,
         weight="600" if active else "400", anchor="middle")
    cx = x - 10

sx0, sx1 = M + 88, M + CW - 56
sy0 = QY + 150
sh = 240
# Teto do eixo: acima do maior valor da serie, arredondado para o milhar.
ymax = (int(max(rs['yield_kg_ha'].max(), rs['trend_kg_ha'].max()) / 500) + 1) * 500.0
years = rs["harvest_year"].tolist()
xs = {yr: sx0 + (yr - years[0]) / (years[-1] - years[0]) * (sx1 - sx0) for yr in years}
ypx = lambda v: sy0 + sh - (v / ymax) * sh

for tick in range(0, int(ymax), 1000):
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
    if r.model <= FLAG_PCT:
        circle(px, py, 10, "none", stroke=ORANGE, sw=2.5)
    circle(px, py, 4.5, VIOLET, stroke=CARD, sw=2)

# faixa climatica: a variavel de entrada, no mesmo eixo de tempo. Nao e um
# segundo eixo y no mesmo plot -- e outro painel, com sua propria escala.
anom = (sr[(sr["crop_name"] == "SOJA") & (sr["state_code"] == "RS")
           & (sr["harvest_year"].between(years[0], years[-1]))]
        .set_index("harvest_year")["dry_days_anomaly_z"])
ay0 = sy0 + sh + 56
zline = ay0 + 42
text(sx0, ay0 - 14, "Dry-day anomaly in the critical window, in standard deviations — "
     "the input the model actually reads", size=12, fill=SOFT)
text(sx0 - 14, zline - 28, "drier", size=10.5, fill=MUTED, anchor="end")
text(sx0 - 14, zline + 34, "wetter", size=10.5, fill=MUTED, anchor="end")
line(sx0, zline, sx1, zline, RULE, 1)
zscale = 40 / (abs(anom).max() * 1.05)
for yr, v in anom.items():
    # z positivo = mais dias secos que o normal, e sobe: o eixo cresce para cima
    vbar(xs[yr], zline, -v * zscale, 14, RED if v > 0 else BLUE)

# ------------------------------------------------------------- 7. pipeline bar
PY = QY + QH + 40
PH = 132
rect(0, PY, W, PH, DARK)
text(M, PY + 42, "PIPELINE", size=11, fill="#8f8e88", weight="600", spacing="1.4")

steps = ["CONAB \u00b7 IBGE \u00b7 NASA POWER", "Python ingestion", "DuckDB (dev) \u00b7 BigQuery (prod)",
         f"dbt \u00b7 {DBT_TESTS} tests", "scikit-learn", "Streamlit"]
sx = M
for i, s in enumerate(steps):
    w = measure(s, 12.5) + 34
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

# Guard: com a folga aplicada, nenhum texto alinhado a esquerda pode passar da
# borda util. Falha ruidosamente em vez de gerar um SVG com texto vazando.
overflow = [(t, round(x + measure(t, size, wt) * SAFETY - RIGHT_EDGE))
            for x, size, wt, anchor, t in _emitted
            if anchor == "start" and x + measure(t, size, wt) * SAFETY > RIGHT_EDGE]
if overflow:
    for t, over in sorted(overflow, key=lambda r: -r[1]):
        print(f"  ESTOURA {over:>3}px: {t[:70]}")
    raise SystemExit(f"{len(overflow)} texto(s) passam da borda — quebre ou reduza")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(out), encoding="utf-8")
print("ok", OUT, "| altura usada:", PY + PH)
