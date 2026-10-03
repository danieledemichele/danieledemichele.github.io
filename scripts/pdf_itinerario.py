#!/usr/bin/env python3
"""
Impagina l'itinerario di una città in un PDF da vendere.

    python scripts/pdf_itinerario.py Londra            → _pdf/Londra.pdf
    python scripts/pdf_itinerario.py Londra --fonts DIR

Legge itinerario/<Città>/citta.json (lo stesso export che alimenta il sito),
costruisce una pagina HTML pensata per la stampa e la trasforma in PDF con
Chromium (Playwright). Il PDF finisce in _pdf/, che è fuori dal sito e fuori
da git: va caricato a mano nel bucket R2 letto dal Worker di acquisto.

Requisiti: pip install playwright pillow  (e un Chromium per Playwright).
I caratteri arrivano da Google Fonts; con --fonts si possono usare file
locali .woff2 (Playfair Display e Inter, come quelli di @fontsource).
"""
import argparse
import base64
import html
import io
import json
import math
import os
import sys
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY_COLORS = ["#B2434A", "#7A4FB5", "#B7801A", "#2A7BC0", "#3B8C55", "#57534e", "#9a3412"]
CAT = {
    "locali": "Locale", "luoghi": "Luogo", "musei": "Museo", "parchi": "Parco",
    "negozi": "Shopping", "esperienze": "Esperienza", "spostamenti": "Spostamento",
}
CAT_PLURAL = {
    "luoghi": "Luoghi e monumenti", "musei": "Musei", "parchi": "Parchi",
    "locali": "Locali", "negozi": "Negozi e mercati", "esperienze": "Esperienze",
}
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

esc = lambda s: html.escape(str(s or ""), quote=True)


def data_uri(raw, mime):
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def image_uri(src, width=1400):
    """Immagine (file locale o URL) ridotta e ricompressa in JPEG, come data: URI."""
    try:
        from PIL import Image
        if src.startswith("http"):
            raw = urllib.request.urlopen(src, timeout=30).read()
        else:
            raw = open(src, "rb").read()
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((width, width))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=80, optimize=True)
        return data_uri(out.getvalue(), "image/jpeg")
    except Exception as e:  # una foto che non arriva non deve fermare il PDF
        print(f"  foto saltata ({src}): {e}", file=sys.stderr)
        return None


def font_css(font_dir):
    if not font_dir:
        return ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
                'family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap">')
    wanted = {("Playfair Display", w): f"playfair-display-latin-{w}-normal.woff2" for w in (600, 700)}
    wanted.update({("Inter", w): f"inter-latin-{w}-normal.woff2" for w in (400, 500, 600, 700)})
    found = {}
    for base, _, files in os.walk(font_dir):
        for f in files:
            found.setdefault(f, os.path.join(base, f))
    css = []
    for (family, weight), name in wanted.items():
        if name in found:
            uri = data_uri(open(found[name], "rb").read(), "font/woff2")
            css.append(f"@font-face{{font-family:'{family}';font-weight:{weight};src:url({uri}) format('woff2')}}")
    return f"<style>{''.join(css)}</style>"


def long_date(iso):
    d = date.fromisoformat(iso)
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"


def maps_link(s):
    if s.get("lat") is None:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={s['lat']},{s['lng']}"


def route_svg(stops, color, w=420, h=270):
    """Schema del percorso del giorno: tappe numerate, linea, scala in metri, nord.
    Proiezione equirettangolare locale: alla scala di un quartiere è fedele."""
    pts = [(i, s) for i, s in enumerate(stops) if s.get("lat") is not None and s["cat"] != "spostamenti"]
    if len(pts) < 2:
        return ""
    lat0 = sum(s["lat"] for _, s in pts) / len(pts)
    kx = math.cos(math.radians(lat0)) * 111_320  # metri per grado di longitudine
    ky = 110_540                                 # metri per grado di latitudine
    xs = [s["lng"] * kx for _, s in pts]
    ys = [s["lat"] * ky for _, s in pts]
    pad = 34
    span = max(max(xs) - min(xs), (max(ys) - min(ys)) * (w - 2 * pad) / (h - 2 * pad), 200)
    scale = (w - 2 * pad) / span                 # pixel per metro
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    P = [(w / 2 + (x - cx) * scale, h / 2 - (y - cy) * scale) for x, y in zip(xs, ys)]
    # sposta un po' i punti sovrapposti, così i numeri restano leggibili
    for a in range(len(P)):
        for b in range(a):
            if math.dist(P[a], P[b]) < 16:
                ang = 0.9 * (a + 1)
                P[a] = (P[a][0] + 15 * math.cos(ang), P[a][1] + 15 * math.sin(ang))
    # scala grafica: una lunghezza "tonda" vicina a un quarto della larghezza
    target = (w / 4) / scale
    nice = min([50, 100, 200, 250, 500, 1000, 2000, 5000], key=lambda v: abs(v - target))
    bar = nice * scale
    lab = f"{nice // 1000} km" if nice >= 1000 else f"{nice} m"
    path = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(P))
    dots = "".join(
        f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="10.5" fill="{color}" stroke="#fff" stroke-width="2"/>'
        f'<text x="{x:.1f}" y="{y + 3.6:.1f}" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">{i + 1}</text></g>'
        for (i, _), (x, y) in zip(pts, P))
    return f'''<svg viewBox="0 0 {w} {h}" class="route" role="img" aria-label="Schema del percorso">
  <rect width="{w}" height="{h}" rx="14" fill="#f3eee6"/>
  <path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" stroke-dasharray="6 5" stroke-linecap="round" opacity=".75"/>
  {dots}
  <g transform="translate(18,{h - 18})"><rect x="0" y="-4" width="{bar:.1f}" height="4" fill="#44403c"/>
  <text x="0" y="-10" font-size="10" fill="#44403c">{lab}</text></g>
  <g transform="translate({w - 26},26)"><path d="M0,-12 L6,6 L0,2 L-6,6 Z" fill="#44403c"/><text y="20" text-anchor="middle" font-size="10" font-weight="700" fill="#44403c">N</text></g>
</svg>'''


def build_html(c, fonts):
    days = c["days"]
    n_stops = sum(1 for d in days for s in d["stops"] if s["cat"] != "spostamenti")
    cover = image_uri(os.path.join(ROOT, "itinerario", c["cover"]), 1600) if c.get("cover") and not c["cover"].startswith("http") else None
    steps = sum(d.get("steps") or 0 for d in days)

    # ---- copertina
    out = [f'''
<section class="page cover">
  {f'<img class="cv" src="{cover}" alt="">' if cover else ''}
  <div class="cv-body">
    <div class="eyebrow">Itinerario · {esc(c["country"])}</div>
    <h1>{esc(c["title"])}</h1>
    <p class="dates">{esc(c["dates"])}</p>
    <p class="lede">{esc(c.get("lede"))}</p>
    <div class="facts">
      <div><b>{len(days)}</b><span>giorni</span></div>
      <div><b>{n_stops}</b><span>tappe</span></div>
      <div><b>{str(c.get("km") or "").replace(".", ",")}</b><span>km a piedi</span></div>
      <div><b>{f"{steps:,}".replace(",", ".")}</b><span>passi</span></div>
    </div>
    <p class="by">di Daniele De Michele · danieledemichele.it</p>
  </div>
</section>''']

    # ---- indice dei giorni
    rows = "".join(f'''<li><span class="dot" style="background:{DAY_COLORS[i % 7]}"></span>
      <span class="ix-d">Giorno {i + 1} · {esc(long_date(d["date"]))}</span>
      <span class="ix-t">{esc(d["title"])}</span>
      <span class="ix-n">{sum(1 for s in d["stops"] if s["cat"] != "spostamenti")} tappe</span></li>''' for i, d in enumerate(days))
    out.append(f'''
<section class="page">
  <div class="eyebrow">Come usare questa guida</div>
  <h2>Il viaggio in breve</h2>
  <p class="body">Ogni giorno ha uno schema del percorso, gli orari in cui ho fatto ogni tappa e una nota pratica.
  Toccando il nome di un posto si apre su Google Maps, così puoi seguire l'itinerario direttamente dal telefono.
  Gli orari sono quelli del mio viaggio: usali come ritmo, non come tabella di marcia.</p>
  <ol class="index">{rows}</ol>
  <div class="legend">{"".join(f'<span class="chip c-{k}">{v}</span>' for k, v in CAT.items())}</div>
</section>''')

    # ---- un capitolo per giorno
    for i, d in enumerate(days):
        col = DAY_COLORS[i % 7]
        photos = [u for u in (image_uri(p, 900) for p in (d.get("photos") or [])[:2]) if u]
        meta = " · ".join(x for x in [
            f'{str(d["km"]).replace(".", ",")} km' if d.get("km") else "",
            f'{d["steps"]:,} passi'.replace(",", ".") if d.get("steps") else "",
            f'{d["temp"]} °C' if d.get("temp") is not None else ""] if x)
        n = 0
        items = []
        for s in d["stops"]:
            move = s["cat"] == "spostamenti"
            if not move:
                n += 1
            link = maps_link(s)
            name = f'<a href="{link}">{esc(s["name"])}</a>' if link else esc(s["name"])
            items.append(f'''<li class="{'move' if move else ''}">
        <span class="tm">{esc(s.get("time"))}</span>
        <span class="no" style="{'' if move else f'background:{col}'}">{'' if move else n}</span>
        <div><div class="nm">{name} <span class="chip c-{s["cat"]}">{CAT.get(s["cat"], s["cat"])}</span></div>
          {f'<div class="nt">{esc(s["notes"])}</div>' if s.get("notes") else ''}</div></li>''')
        out.append(f'''
<section class="page day" style="--dc:{col}">
  <div class="dayhead">
    <div class="eyebrow" style="color:{col}">Giorno {i + 1} · {esc(long_date(d["date"]))}</div>
    <h2>{esc(d["title"])}</h2>
    {f'<p class="body">{esc(d.get("lede"))}</p>' if d.get("lede") else ''}
    {f'<p class="meta">{meta}</p>' if meta else ''}
  </div>
  <div class="visual{' nophoto' if not photos else ''}">{route_svg(d["stops"], col)}
    {f'<div class="photos">{"".join(f"<img src={chr(34)}{p}{chr(34)} alt={chr(34)}{chr(34)}>" for p in photos)}</div>' if photos else ''}</div>
  <ol class="stops">{"".join(items)}</ol>
</section>''')

    # ---- tutti i posti per categoria
    groups = []
    for k, label in CAT_PLURAL.items():
        names = []
        for i, d in enumerate(days):
            for s in d["stops"]:
                if s["cat"] == k:
                    link = maps_link(s)
                    nm = f'<a href="{link}">{esc(s["name"])}</a>' if link else esc(s["name"])
                    names.append(f'<li>{nm}<span>giorno {i + 1}</span></li>')
        if names:
            groups.append(f'<div class="grp"><h3>{label} <small>{len(names)}</small></h3><ul>{"".join(names)}</ul></div>')
    out.append(f'''
<section class="page">
  <div class="eyebrow">Indice</div>
  <h2>Tutti i posti</h2>
  <div class="groups">{"".join(groups)}</div>
  <p class="fine">Questo itinerario è per uso personale: grazie per non condividerlo.<br>
  Domande o correzioni? Scrivimi da danieledemichele.it</p>
</section>''')

    return f'''<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>{esc(c["title"])}</title>{font_css(fonts)}
<style>
@page {{ size: A4; margin: 16mm 16mm 18mm; }}
:root {{ --ink:#1c1917; --ink2:#44403c; --sub:#78716c; --line:#e7e0d5; --panel:#f3eee6; --accent:#9a3412;
  --serif:"Playfair Display",Georgia,serif; --sans:Inter,"Helvetica Neue",Arial,sans-serif; }}
* {{ box-sizing:border-box }}
body {{ margin:0; font-family:var(--sans); font-size:10.5pt; line-height:1.5; color:var(--ink);
  -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
a {{ color:inherit; text-decoration:none; border-bottom:1px solid #d6cbbb }}
h1,h2,h3 {{ font-family:var(--serif); margin:0; line-height:1.12 }}
h1 {{ font-size:34pt }} h2 {{ font-size:22pt }} h3 {{ font-size:12.5pt }}
.page {{ break-after:page; display:flex; flex-direction:column; gap:12px }}
.page:last-child {{ break-after:auto }}
.eyebrow {{ font-size:8pt; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--accent) }}
.body {{ margin:0; color:var(--ink2); max-width:150mm }}
.cover .cv {{ width:100%; height:120mm; object-fit:cover; border-radius:14px }}
.cv-body {{ display:flex; flex-direction:column; gap:10px; padding-top:8mm }}
.dates {{ margin:0; font-weight:600; color:var(--accent) }}
.lede {{ margin:0; font-size:12pt; color:var(--ink2); max-width:150mm }}
.facts {{ display:flex; gap:10px; margin-top:6mm }}
.facts div {{ flex:1; border:1px solid var(--line); border-radius:12px; padding:10px 12px; display:flex; flex-direction:column }}
.facts b {{ font-family:var(--serif); font-size:20pt }} .facts span {{ font-size:8.5pt; color:var(--sub) }}
.by {{ margin-top:auto; padding-top:12mm; font-size:9pt; color:var(--sub) }}
.index {{ list-style:none; padding:0; margin:6mm 0 0; display:flex; flex-direction:column }}
.index li {{ display:grid; grid-template-columns:14px 52mm 1fr auto; gap:8px; align-items:center; padding:9px 0; border-bottom:1px solid var(--line) }}
.dot {{ width:10px; height:10px; border-radius:50% }}
.ix-d {{ font-size:9pt; color:var(--sub) }} .ix-t {{ font-family:var(--serif); font-size:13pt; font-weight:700 }} .ix-n {{ font-size:9pt; color:var(--sub) }}
.legend {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:4mm }}
.chip {{ display:inline-block; font-size:7.5pt; font-weight:600; padding:1px 7px; border-radius:999px; background:#f1ebe2; color:var(--ink2) }}
.c-locali {{ background:#fbeae4; color:#9a3412 }} .c-luoghi {{ background:#e6effa; color:#1f5f9a }}
.c-musei {{ background:#f0e9fa; color:#5b3a92 }} .c-parchi {{ background:#e6f2ea; color:#2e6b42 }}
.c-negozi {{ background:#fbf1dc; color:#8a5a0c }}
.dayhead {{ display:flex; flex-direction:column; gap:6px; border-left:4px solid var(--dc); padding-left:12px }}
.meta {{ margin:0; font-size:9pt; color:var(--sub); font-variant-numeric:tabular-nums }}
.route {{ width:100%; height:auto; font-family:var(--sans); break-inside:avoid }}
.stops {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column }}
.stops li {{ display:grid; grid-template-columns:13mm 22px 1fr; gap:8px; padding:5px 0; border-bottom:1px solid var(--line); break-inside:avoid }}
.tm {{ font-size:9pt; color:var(--sub); font-variant-numeric:tabular-nums; padding-top:2px }}
.no {{ width:20px; height:20px; border-radius:50%; color:#fff; font-size:8.5pt; font-weight:700; display:grid; place-items:center }}
.move .no {{ border:1.5px dashed #a8a29e }}
.nm {{ font-weight:600 }} .move .nm {{ color:var(--ink2); font-weight:500 }}
.nt {{ font-size:9pt; color:var(--ink2); margin-top:1px }}
.nm .chip {{ margin-left:4px; vertical-align:1px }}
.visual {{ display:grid; grid-template-columns:1.55fr 1fr; gap:8px; break-inside:avoid }}
.visual.nophoto {{ grid-template-columns:1fr }}
.photos {{ display:grid; grid-template-rows:1fr 1fr; gap:8px }}
.photos img {{ width:100%; height:33mm; object-fit:cover; border-radius:10px }}
.groups {{ columns:2; column-gap:10mm }}
.grp {{ margin-bottom:6mm }}
.grp h3 {{ break-after:avoid }}
.grp li {{ break-inside:avoid }}
.grp h3 small {{ font-family:var(--sans); font-size:8.5pt; color:var(--sub); font-weight:500 }}
.grp ul {{ list-style:none; margin:4px 0 0; padding:0 }}
.grp li {{ display:flex; justify-content:space-between; gap:8px; padding:3px 0; border-bottom:1px solid var(--line); font-size:9.5pt }}
.grp li span {{ color:var(--sub); font-size:8.5pt; white-space:nowrap }}
.fine {{ margin-top:auto; font-size:8.5pt; color:var(--sub) }}
</style></head><body>{"".join(out)}</body></html>'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="cartella della città, es. Londra")
    ap.add_argument("--fonts", help="cartella con i .woff2 di Playfair Display e Inter")
    ap.add_argument("--out", help="percorso del PDF (predefinito _pdf/<Città>.pdf)")
    ap.add_argument("--html", action="store_true", help="salva anche l'HTML intermedio")
    a = ap.parse_args()

    c = json.load(open(os.path.join(ROOT, "itinerario", a.slug, "citta.json"), encoding="utf-8"))
    out = a.out or os.path.join(ROOT, "_pdf", f"{a.slug}.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    page = build_html(c, a.fonts)
    if a.html:
        open(out[:-4] + ".html", "w", encoding="utf-8").write(page)

    from playwright.sync_api import sync_playwright
    footer = ('<div style="width:100%;font:7.5pt Inter,Arial,sans-serif;color:#a8a29e;padding:0 16mm;'
              f'display:flex;justify-content:space-between"><span>{esc(c["title"])} · danieledemichele.it</span>'
              '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(page, wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        pg.pdf(path=out, format="A4", print_background=True, display_header_footer=True,
               header_template="<span></span>", footer_template=footer,
               margin={"top": "16mm", "bottom": "18mm", "left": "16mm", "right": "16mm"})
        b.close()
    print(f"PDF pronto: {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
