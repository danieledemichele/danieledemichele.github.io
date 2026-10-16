#!/usr/bin/env python3
"""
Volume di viaggio in LaTeX: impagina l'itinerario completo di una città in un
piccolo libro e lo compila in PDF con XeLaTeX.

    python scripts/volume_latex.py Londra                  → _pdf/Londra-taccuino.pdf
    python scripts/volume_latex.py Londra --stile atlante  → _pdf/Londra-atlante.pdf
    python scripts/volume_latex.py Londra --solo-tex       → solo il sorgente .tex

Due impaginazioni:
  taccuino  A5, una colonna: da tenere in tasca e leggere davanti ai luoghi.
            Apertura di ogni giorno con foto a tutta larghezza, percorso e orari,
            poi una scheda per luogo con storia e "Da cercare".
  atlante   A4 a due colonne, più da sfogliare: copertina con l'illustrazione a
            pagina piena, linea del tempo orizzontale, aperture dei giorni con
            foto grande e striscia di foto in fondo al giorno.

Dati: _privato/<Città>/citta.json, scritto da sync_itinerario.py (sul sito c'è
solo l'anteprima): tappe con le colonne Storia, Da cercare e Anno storico e la
sottopagina "Volume" di Notion. Le foto arrivano dal repo danieledemichele/Viaggio:
vengono scaricate in _pdf/foto/, raddrizzate secondo l'orientamento EXIF e
ritagliate in proporzione esatta prima di entrare nel PDF, così nessuna esce
deformata o tagliata male. Una foto che non si scarica viene saltata.

Requisiti: XeLaTeX con fontspec, tcolorbox, tikz, lettrine, needspace (TeX Live),
il font Inter installato nel sistema (pacchetto fonts-inter), Pillow.
Playfair Display è in scripts/volume/fonts/ (licenza OFL).
"""
import argparse
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "scripts", "volume", "fonts")
CACHE = os.path.join(ROOT, "_pdf", "foto")
DAY = ["B2434A", "7A4FB5", "B7801A", "2A7BC0", "3B8C55", "57534E", "9A3412"]
CAT = {"locali": "Locale", "luoghi": "Luogo", "musei": "Museo", "parchi": "Parco",
       "negozi": "Shopping", "esperienze": "Esperienza", "spostamenti": "Spostamento"}
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


# ---------------------------------------------------------------- aiuti

def tex(s):
    """Testo → LaTeX sicuro."""
    s = str(s or "")
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
           "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(rep.get(c, c) for c in s).replace("\n\n", "\\par ")


def url(u):
    return u.replace("%", r"\%").replace("#", r"\#")


def long_date(iso):
    d = date.fromisoformat(iso)
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"


def maps(s):
    return f"https://www.google.com/maps/search/?api=1&query={s['lat']},{s['lng']}" if s.get("lat") is not None else ""


def photo(src, aspect, width_px=1600):
    """Scarica (o legge) una foto, la raddrizza, la ritaglia al rapporto `aspect`
    (larghezza/altezza) centrata e la salva in JPEG. Restituisce il percorso o None."""
    from PIL import Image, ImageOps
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1(f"{src}|{aspect:.4f}|{width_px}".encode()).hexdigest()[:16]
    out = os.path.join(CACHE, key + ".jpg")
    if os.path.exists(out):
        return out
    try:
        if src.startswith("http"):
            raw = urllib.request.urlopen(src, timeout=40).read()
        else:
            raw = open(src, "rb").read()
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        w, h = im.size
        if w / h > aspect:                       # troppo larga: taglio i lati
            nw = int(h * aspect); x = (w - nw) // 2
            im = im.crop((x, 0, x + nw, h))
        else:                                    # troppo alta: taglio sopra e sotto (un po' più sotto)
            nh = int(w / aspect); y = int((h - nh) * 0.4)
            im = im.crop((0, y, w, y + nh))
        if im.width > width_px:
            im = im.resize((width_px, int(width_px / aspect)), Image.LANCZOS)
        im.save(out, "JPEG", quality=84, optimize=True, progressive=True)
        Image.open(out).verify()                 # il file scritto deve essere leggibile
        return out
    except Exception as e:
        print(f"  foto saltata ({src}): {e}", file=sys.stderr)
        if os.path.exists(out):
            os.remove(out)
        return None


def first_photos(srcs, n, aspect, width_px=1600, skip=0):
    """Le prime n foto valide della lista (dopo `skip`)."""
    out = []
    for s in srcs[skip:]:
        p = photo(s, aspect, width_px)
        if p:
            out.append(p)
        if len(out) == n:
            break
    return out


def route_tikz(stops, color, w, h):
    """Schema del percorso in TikZ (cm): tappe numerate, linea tratteggiata, scala e nord.
    Proiezione equirettangolare locale, fedele alla scala di un quartiere."""
    pts, n = [], 0
    for s in stops:
        if s["cat"] != "spostamenti":
            n += 1
            if s.get("lat") is not None:
                pts.append((n, s))
    if len(pts) < 2:
        return ""
    lat0 = sum(s["lat"] for _, s in pts) / len(pts)
    kx, ky = math.cos(math.radians(lat0)) * 111_320, 110_540
    xs = [s["lng"] * kx for _, s in pts]
    ys = [s["lat"] * ky for _, s in pts]
    pad = 0.9
    span = max(max(xs) - min(xs), (max(ys) - min(ys)) * (w - 2 * pad) / (h - 2 * pad), 200)
    sc = (w - 2 * pad) / span                     # cm per metro
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    P = [(w / 2 + (x - cx) * sc, h / 2 + (y - cy) * sc) for x, y in zip(xs, ys)]
    for a in range(len(P)):                        # separa i punti sovrapposti
        for b in range(a):
            if math.dist(P[a], P[b]) < 0.42:
                ang = 0.9 * (a + 1)
                P[a] = (P[a][0] + 0.4 * math.cos(ang), P[a][1] + 0.4 * math.sin(ang))
    target = (w / 4) / sc
    nice = min([50, 100, 200, 250, 500, 1000, 2000, 5000], key=lambda v: abs(v - target))
    lab = f"{nice // 1000} km" if nice >= 1000 else f"{nice} m"
    path = " -- ".join(f"({x:.2f},{y:.2f})" for x, y in P)
    dots = "\n".join(
        f"\\node[circle,fill=c{color},draw=white,line width=0.9pt,inner sep=0pt,minimum size=4.6mm,"
        f"text=white,font=\\sffamily\\bfseries\\fontsize{{6.5}}{{7}}\\selectfont] at ({x:.2f},{y:.2f}) {{{k}}};"
        for (k, _), (x, y) in zip(pts, P))
    return f"""\\begin{{tikzpicture}}
\\fill[panel,rounded corners=3mm] (0,0) rectangle ({w},{h});
\\draw[c{color},line width=1.1pt,dash pattern=on 3pt off 2.4pt,opacity=.8,line cap=round] {path};
{dots}
\\fill[ink2] (0.5,0.45) rectangle ({0.5 + nice * sc:.2f},0.55);
\\node[anchor=south west,font=\\sffamily\\fontsize{{6.5}}{{7}}\\selectfont,text=ink2,inner sep=1pt] at (0.48,0.6) {{{lab}}};
\\fill[ink2] ({w - 0.55},{h - 0.35}) -- ({w - 0.75},{h - 0.85}) -- ({w - 0.55},{h - 0.72}) -- ({w - 0.35},{h - 0.85}) -- cycle;
\\node[font=\\sffamily\\bfseries\\fontsize{{6.5}}{{7}}\\selectfont,text=ink2] at ({w - 0.55},{h - 1.1}) {{N}};
\\end{{tikzpicture}}"""


def numbered_stops(d):
    """(numero, tappa) con il numero delle sole tappe che non sono spostamenti."""
    out, n = [], 0
    for s in d["stops"]:
        if s["cat"] != "spostamenti":
            n += 1
            out.append((n, s))
        else:
            out.append((None, s))
    return out


def schedule(d, color, width=r"\linewidth"):
    """Orari del giorno: ora, numero della tappa, nome (con link a Maps) e nota.
    Ogni riga è una sequenza di box allineati sulla prima linea di testo."""
    rows = []
    for n, s in numbered_stops(d):
        badge = (f"\\tikz[baseline=(n.base)]\\node(n)[circle,fill=c{color},inner sep=0pt,minimum size=4.2mm,text=white,"
                 f"font=\\sffamily\\bfseries\\fontsize{{6.5}}{{7}}\\selectfont]{{{n}}};") if n else \
                "\\tikz[baseline=-0.7ex]\\draw[sub,dash pattern=on 1pt off 1pt] (0,0) circle (2.1mm);"
        link = maps(s)
        name = f"\\href{{{url(link)}}}{{{tex(s['name'])}}}" if link else tex(s["name"])
        notes = f"\\\\{{\\color{{sub}}\\fontsize{{7.5}}{{9}}\\selectfont {tex(s['notes'])}}}" if s.get("notes") else ""
        weight = "\\bfseries" if n else "\\color{ink2}"
        rows.append(f"\\noindent\\makebox[11mm][l]{{\\color{{sub}}\\fontsize{{8}}{{10}}\\selectfont {tex(s.get('time'))}}}"
                    f"\\makebox[7mm][l]{{{badge}}}"
                    f"\\parbox[t]{{\\dimexpr {width}-18mm\\relax}}{{\\raggedright{{{weight} {name}}}{notes}}}\\par\\vspace{{1.6mm}}")
    return "{\\sffamily\\fontsize{8.5}{10.5}\\selectfont\\setlength{\\parskip}{0pt}\n" + "\n".join(rows) + "\n}"


def place_index(c):
    items = []
    for i, d in enumerate(c["days"]):
        for n, s in numbered_stops(d):
            if n and s.get("storia"):
                items.append((s["name"], f"luogo-{i}-{n}"))
    items.sort(key=lambda x: x[0].lower().lstrip("'"))
    return items


# ---------------------------------------------------------------- preambolo comune

def preamble(paper, margins, size):
    return rf"""\documentclass[{size}]{{article}}
\usepackage[{paper},{margins}]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{polyglossia}}\setdefaultlanguage{{italian}}
\usepackage{{microtype,xcolor,graphicx,tikz,tabularx,multicol,needspace,lettrine,fancyhdr,ragged2e,enumitem}}
\usepackage[most]{{tcolorbox}}
\usepackage[hidelinks]{{hyperref}}
\usetikzlibrary{{calc,fadings}}
\setmainfont{{TeX Gyre Pagella}}[Numbers=OldStyle]
\setsansfont{{Inter}}[Numbers=Lining]
\newfontfamily\display{{PlayfairDisplay}}[Path={FONTS}/, Extension=.ttf, UprightFont=*-Regular, BoldFont=*-Bold, ItalicFont=*-Italic, BoldItalicFont=*-BoldItalic, Numbers=Lining]
\newfontfamily\displayblack{{PlayfairDisplay-Black}}[Path={FONTS}/, Extension=.ttf, Numbers=Lining]
\definecolor{{accent}}{{HTML}}{{9A3412}}
\definecolor{{ink}}{{HTML}}{{2C2825}}
\definecolor{{ink2}}{{HTML}}{{44403C}}
\definecolor{{sub}}{{HTML}}{{78716C}}
\definecolor{{line}}{{HTML}}{{E7E0D5}}
\definecolor{{panel}}{{HTML}}{{F3EEE6}}
\definecolor{{paper}}{{HTML}}{{FBF8F3}}
{"".join(f"\\definecolor{{c{h}}}{{HTML}}{{{h}}}\n" for h in DAY)}
\color{{ink}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.55em}}
\setlength{{\JustifyingParindent}}{{0pt}}
\tolerance=2000\emergencystretch=2.5em\hbadness=10000
\newcommand\eyebrow[2][accent]{{{{\sffamily\bfseries\fontsize{{7}}{{9}}\selectfont\addfontfeature{{LetterSpace=12}}\color{{#1}}\MakeUppercase{{#2}}}}}}
\newcommand\meta[1]{{{{\sffamily\fontsize{{7.5}}{{9.5}}\selectfont\color{{sub}}#1}}}}
\newtcolorbox{{cercare}}[1]{{enhanced,breakable=false,colback=panel,colframe=panel,boxrule=0pt,arc=2mm,
  left=3mm,right=3mm,top=1.6mm,bottom=1.6mm,borderline west={{1.4pt}}{{0pt}}{{#1}},fontupper=\sffamily\fontsize{{8}}{{10.5}}\selectfont\color{{ink2}},
  before upper={{{{\bfseries\fontsize{{6.5}}{{8}}\selectfont\addfontfeature{{LetterSpace=10}}\color{{#1}}DA CERCARE}}\enspace}}}}
\renewcommand*{{\LettrineFontHook}}{{\display\color{{accent}}}}
\setlength{{\DefaultNindent}}{{0.3em}}
"""


# ---------------------------------------------------------------- impaginazione "taccuino" (A5)

def taccuino(c):
    vol = c.get("volume") or {}
    days = c["days"]
    n_luoghi = sum(1 for d in days for n, s in numbered_stops(d) if n)
    poster = os.path.join(ROOT, "itinerario", c["poster"]) if c.get("poster") else None
    cover = photo(poster, 0.78, 1100) if poster and os.path.exists(poster) else None
    T = [preamble("a5paper", "inner=17mm,outer=14mm,top=17mm,bottom=19mm,headsep=5mm,footskip=9mm", "9.5pt" if False else "10pt")]
    T.append(rf"""
\pagestyle{{fancy}}\fancyhf{{}}
\renewcommand{{\headrulewidth}}{{0pt}}
\fancyhead[L]{{\meta{{{tex(c['title'])}}}}}
\fancyhead[R]{{\meta{{\leftmark}}}}
\fancyfoot[C]{{\meta{{\thepage}}}}
\newcommand\giorno[1]{{\markboth{{#1}}{{#1}}}}
\begin{{document}}
\thispagestyle{{empty}}
\pagecolor{{paper}}
\begin{{tikzpicture}}[remember picture,overlay]
\fill[paper] (current page.south west) rectangle (current page.north east);
{f"\\node[anchor=north,inner sep=0pt] (cv) at ($(current page.north)+(0,-14mm)$) {{\\includegraphics[width=104mm]{{{cover}}}}};" if cover else ""}
\end{{tikzpicture}}\par
\vspace*{{{'124mm' if cover else '40mm'}}}
\begin{{center}}
\eyebrow{{Volume di viaggio · {tex(c['country'])}}}\par\vspace{{2mm}}
{{\display\bfseries\fontsize{{25}}{{28}}\selectfont {tex(c['title'])}\par}}
\vspace{{1mm}}{{\sffamily\fontsize{{9}}{{11}}\selectfont\color{{accent}} {tex(c['dates'])}\par}}
\vspace{{3mm}}\meta{{{len(days)} giorni · {n_luoghi} tappe · {str(c.get('km') or '').replace('.', ',')} km a piedi}}
\end{{center}}
\vfill
\begin{{center}}\meta{{di Daniele De Michele · danieledemichele.it}}\end{{center}}
\newpage\nopagecolor
""")
    # come usare + indice
    rows = "\n".join(
        rf"\tikz[baseline=-0.6ex]\fill[c{DAY[i % 7]}] (0,0) circle (1.2mm); & {{\sffamily\fontsize{{7.5}}{{9}}\selectfont\color{{sub}}Giorno {i + 1} · {tex(long_date(d['date']))}}}\newline{{\display\bfseries\fontsize{{12}}{{14}}\selectfont {tex(d['title'])}}} & \meta{{p.~\pageref{{giorno-{i}}}}}\\[2.5mm]"
        for i, d in enumerate(days))
    T.append(rf"""
\giorno{{Il viaggio in breve}}
\eyebrow{{Come usare questo volume}}\par
{{\display\bfseries\fontsize{{20}}{{23}}\selectfont Il viaggio in breve\par}}
{tex(c.get('lede'))}

Ogni giorno si apre con una foto e la storia del quartiere; segue il percorso con gli orari in cui ho fatto ogni tappa. Poi ci sono le schede dei luoghi: quando sei sul posto, leggi la storia e cerca il dettaglio indicato nel riquadro. Il nome di ogni posto è un collegamento a Google Maps. Gli orari sono quelli del mio viaggio: usali come ritmo, non come tabella di marcia.

\vspace{{3mm}}
\begin{{tabularx}}{{\linewidth}}{{@{{}}p{{4mm}}X r@{{}}}}
{rows}
\end{{tabularx}}
\newpage
""")
    # la città in breve
    if vol.get("intro"):
        paras = vol["intro"]
        first = paras[0]
        w0, rest = first.split(" ", 1)
        body = f"\\lettrine[lines=3,loversize=0.08]{{{tex(w0[0])}}}{{{tex(w0[1:])}}} {tex(rest)}\n\n" + "\n\n".join(tex(p) for p in paras[1:])
        tl = "\n".join(rf"{{\display\bfseries\color{{accent}}{tex(t['anno'])}}} & {tex(t['testo'])}\\[0.8mm]" for t in vol.get("timeline", []))
        T.append(rf"""
\giorno{{{tex(vol.get('intro_titolo') or c['label'] + ' in breve')}}}
\eyebrow{{Prima di partire}}\par
{{\display\bfseries\fontsize{{20}}{{23}}\selectfont {tex(vol.get('intro_titolo') or c['label'] + ' in breve')}\par}}
\vspace{{1mm}}
\justifying
{body}
\newpage
\eyebrow{{Linea del tempo}}\par
{{\display\bfseries\fontsize{{20}}{{23}}\selectfont Duemila anni in dodici date\par}}
\vspace{{2mm}}
{{\fontsize{{9.5}}{{12.5}}\selectfont
\begin{{tabularx}}{{\linewidth}}{{@{{}}>{{\raggedleft\arraybackslash}}p{{14mm}}!{{\color{{line}}\vrule width 1pt}}@{{\hspace{{3mm}}}}X@{{}}}}
{tl}
\end{{tabularx}}}}
\newpage
""")
    # giorni
    for i, d in enumerate(days):
        col = DAY[i % 7]
        pics = first_photos(d.get("photos") or [], 1, 148 / 80)
        meta = " · ".join(x for x in [
            f"{str(d['km']).replace('.', ',')} km" if d.get("km") else "",
            f"{d['steps']:,} passi".replace(",", ".") if d.get("steps") else "",
            f"{d['temp']} °C" if d.get("temp") is not None else ""] if x)
        hist = (vol.get("giorni") or {}).get(d["title"], "")
        has_cards = any(n and s.get("storia") for n, s in numbered_stops(d))
        T.append(rf"""
\giorno{{{tex(d['title'])}}}
\label{{giorno-{i}}}
\thispagestyle{{empty}}
{f"\\begin{{tikzpicture}}[remember picture,overlay]\\node[anchor=north,inner sep=0pt] at (current page.north) {{\\includegraphics[width=\\paperwidth,height=80mm]{{{pics[0]}}}}};\\fill[c{col}] ($(current page.north west)+(0,-80mm)$) rectangle ($(current page.north east)+(0,-81.6mm)$);\\end{{tikzpicture}}\\par\\vspace*{{63mm}}" if pics else ""}
\eyebrow[c{col}]{{Giorno {i + 1} · {tex(long_date(d['date']))}}}\par
{{\display\bfseries\fontsize{{24}}{{27}}\selectfont {tex(d['title'])}\par}}
{f"{{\\itshape\\color{{ink2}} {tex(d.get('lede'))}\\par}}" if d.get('lede') else ''}
{f"\\meta{{{meta}}}\\par" if meta else ''}
{f"\\vspace{{1mm}}{{\\fontsize{{9.5}}{{12.5}}\\selectfont\\justifying {tex(hist)}\\par}}" if hist else ''}
{"\\newpage" if (pics or has_cards) else "\\vspace{6mm}"}
""")
        rt = route_tikz(d["stops"], col, 11.7, 7.2)
        T.append(rf"""
\eyebrow[c{col}]{{{"Il percorso" if rt else "Orari"}}}\par
{rt}
\par\vspace{{2mm}}
{schedule(d, col)}
\newpage
""")
        cards = []
        for n, s in numbered_stops(d):
            if not (n and s.get("storia")):
                continue
            link = maps(s)
            name = f"\\href{{{url(link)}}}{{{tex(s['name'])}}}" if link else tex(s["name"])
            m = " · ".join(x for x in [s.get("time") and f"ore {s['time']}", CAT.get(s["cat"], ""), s.get("anno")] if x)
            cards.append(rf"""
\needspace{{14\baselineskip}}
\label{{luogo-{i}-{n}}}
\noindent\begin{{tabularx}}{{\linewidth}}{{@{{}}p{{7mm}}X@{{}}}}
\tikz[baseline=-0.8ex]\node[circle,fill=c{col},inner sep=0pt,minimum size=5.6mm,text=white,font=\sffamily\bfseries\fontsize{{8}}{{9}}\selectfont]{{{n}}}; &
{{\display\bfseries\fontsize{{14}}{{16}}\selectfont {name}}}\newline\meta{{{tex(m)}}}
\end{{tabularx}}\par\vspace{{-1mm}}
{{\fontsize{{9.5}}{{12.5}}\selectfont\justifying {tex(s['storia'])}\par}}
{f"\\begin{{cercare}}{{c{col}}}{tex(s['cercare'])}\\end{{cercare}}" if s.get('cercare') else ''}
\vspace{{3mm}}""")
        if cards:
            T.append(rf"""
\eyebrow[c{col}]{{{tex(d['title'])}}}\par
{{\display\bfseries\fontsize{{20}}{{23}}\selectfont I luoghi\par}}\vspace{{1mm}}
{"".join(cards)}
\newpage
""")
    # indice
    idx = "\n".join(rf"{tex(nm)}\dotfill\pageref{{{lab}}}\par" for nm, lab in place_index(c))
    T.append(rf"""
\giorno{{Indice dei luoghi}}
\eyebrow{{Indice}}\par
{{\display\bfseries\fontsize{{20}}{{23}}\selectfont I luoghi, in ordine\par}}
\vspace{{1mm}}
{{\sffamily\fontsize{{8.5}}{{11}}\selectfont\setlength{{\parskip}}{{1.1mm}}
{idx}}}
\vfill
\meta{{Le note storiche sono state scritte e verificate su fonti pubbliche (siti ufficiali dei luoghi, enti di tutela, enciclopedie) nell'ottobre 2026: orari, aperture e opere esposte possono cambiare. Questo volume è per uso personale: grazie per non condividerlo.}}
\end{{document}}
""")
    return "".join(T)


# ---------------------------------------------------------------- impaginazione "atlante" (A4, due colonne)

def atlante(c):
    vol = c.get("volume") or {}
    days = c["days"]
    n_luoghi = sum(1 for d in days for n, s in numbered_stops(d) if n)
    poster = os.path.join(ROOT, "itinerario", c["poster"]) if c.get("poster") else None
    cover = photo(poster, 210 / 297, 1400) if poster and os.path.exists(poster) else None
    T = [preamble("a4paper", "inner=20mm,outer=18mm,top=20mm,bottom=22mm,headsep=6mm,footskip=11mm", "10pt")]
    T.append(rf"""
\setlength{{\columnsep}}{{8mm}}
\pagestyle{{fancy}}\fancyhf{{}}
\renewcommand{{\headrulewidth}}{{0pt}}
\fancyhead[L]{{\eyebrow[sub]{{{tex(c['title'])}}}}}
\fancyhead[R]{{\eyebrow[sub]{{\leftmark}}}}
\fancyfoot[R]{{\display\bfseries\fontsize{{11}}{{12}}\selectfont\color{{accent}}\thepage}}
\newcommand\giorno[1]{{\markboth{{#1}}{{#1}}}}
\begin{{document}}
\thispagestyle{{empty}}
\begin{{tikzpicture}}[remember picture,overlay]
{f"\\node[inner sep=0pt] at (current page.center) {{\\includegraphics[width=\\paperwidth,height=\\paperheight]{{{cover}}}}};" if cover else "\\fill[accent] (current page.south west) rectangle (current page.north east);"}
\fill[black,opacity=.55,path fading=north] (current page.south west) rectangle ($(current page.south east)+(0,110mm)$);
\node[anchor=south west,text=white,inner sep=0pt] at ($(current page.south west)+(20mm,24mm)$) {{\begin{{minipage}}{{170mm}}\raggedright%
  {{\sffamily\bfseries\fontsize{{8}}{{10}}\selectfont\addfontfeature{{LetterSpace=14}}VOLUME DI VIAGGIO · {tex(c['country']).upper()}\par}}\vspace{{3mm}}
  {{\raggedright\display\bfseries\fontsize{{36}}{{40}}\selectfont {tex(c['title'])}\par}}\vspace{{3mm}}
  {{\sffamily\fontsize{{10}}{{13}}\selectfont {tex(c['dates'])} · {len(days)} giorni · {n_luoghi} tappe · {str(c.get('km') or '').replace('.', ',')} km a piedi\par}}\vspace{{5mm}}
  {{\sffamily\fontsize{{8}}{{10}}\selectfont di Daniele De Michele · danieledemichele.it\par}}\end{{minipage}}}};
\end{{tikzpicture}}
\newpage
""")
    # la città in breve + linea del tempo orizzontale
    if vol.get("intro"):
        paras = vol["intro"]
        w0, rest = paras[0].split(" ", 1)
        body = f"\\lettrine[lines=3]{{{tex(w0[0])}}}{{{tex(w0[1:])}}} {tex(rest)}\n\n" + "\n\n".join(tex(p) for p in paras[1:])
        tl = vol.get("timeline", [])
        k = len(tl)
        W = 170.0
        nodes = []
        for j, t in enumerate(tl):
            x = 3 + j * (W - 6) / max(1, k - 1)
            up = j % 2 == 0
            nodes.append(rf"\fill[accent] ({x:.1f}mm,0) circle (1.3mm);\draw[line,line width=.6pt] ({x:.1f}mm,{'1.6' if up else '-1.6'}mm) -- ({x:.1f}mm,{'9' if up else '-9'}mm);"
                         rf"\node[anchor={'south' if up else 'north'},inner sep=1pt] at ({x:.1f}mm,{'9.5' if up else '-9.5'}mm) {{\begin{{minipage}}{{27mm}}\centering{{\display\bfseries\fontsize{{11}}{{12}}\selectfont\color{{accent}}{tex(t['anno'])}}}\\{{\sffamily\fontsize{{6.8}}{{8.4}}\selectfont\color{{ink2}}{tex(t['testo'])}}}\end{{minipage}}}};")
        T.append(rf"""
\giorno{{{tex(vol.get('intro_titolo') or c['label'] + ' in breve')}}}
\eyebrow{{Prima di partire}}\par
{{\display\bfseries\fontsize{{30}}{{33}}\selectfont {tex(vol.get('intro_titolo') or c['label'] + ' in breve')}\par}}
\vspace{{2mm}}
{{\itshape\fontsize{{12}}{{15}}\selectfont\color{{ink2}} {tex(c.get('lede'))}\par}}
\vspace{{3mm}}
\begin{{multicols}}{{2}}\justifying
{body}
\end{{multicols}}
\vfill
\eyebrow{{Linea del tempo}}\par\vspace{{24mm}}
\noindent\begin{{tikzpicture}}
\draw[line,line width=1.4pt] (0,0) -- ({W}mm,0);
{chr(10).join(nodes)}
\end{{tikzpicture}}
\vspace{{22mm}}
\newpage
""")
    for i, d in enumerate(days):
        col = DAY[i % 7]
        srcs = d.get("photos") or []
        hero = first_photos(srcs, 1, 210 / 120, 1800)
        strip = first_photos(srcs, 3, 4 / 3, 900, skip=1)
        hist = (vol.get("giorni") or {}).get(d["title"], "")
        meta = " · ".join(x for x in [
            f"{str(d['km']).replace('.', ',')} km" if d.get("km") else "",
            f"{d['steps']:,} passi".replace(",", ".") if d.get("steps") else "",
            f"{d['temp']} °C" if d.get("temp") is not None else ""] if x)
        T.append(rf"""
\clearpage
\giorno{{{tex(d['title'])}}}
\thispagestyle{{empty}}
{f"\\begin{{tikzpicture}}[remember picture,overlay]\\node[anchor=north,inner sep=0pt] at (current page.north) {{\\includegraphics[width=\\paperwidth,height=120mm]{{{hero[0]}}}}};\\fill[black,opacity=.5,path fading=north] ($(current page.north west)+(0,-120mm)$) rectangle ($(current page.north east)+(0,-70mm)$);\\node[anchor=south west,text=white,inner sep=0pt] at ($(current page.north west)+(20mm,-114mm)$) {{\\begin{{minipage}}{{170mm}}{{\\sffamily\\bfseries\\fontsize{{8}}{{10}}\\selectfont\\addfontfeature{{LetterSpace=14}}GIORNO {i + 1} · {tex(long_date(d['date'])).upper()}\\par}}\\vspace{{1mm}}{{\\display\\bfseries\\fontsize{{34}}{{36}}\\selectfont {tex(d['title'])}\\par}}\\end{{minipage}}}};\\fill[c{col}] ($(current page.north west)+(0,-120mm)$) rectangle ($(current page.north east)+(0,-122mm)$);\\end{{tikzpicture}}\\par\\vspace*{{108mm}}" if hero else f"\\eyebrow[c{col}]{{Giorno {i + 1} · {tex(long_date(d['date']))}}}\\par{{\\display\\bfseries\\fontsize{{34}}{{36}}\\selectfont {tex(d['title'])}\\par}}"}
{f"{{\\itshape\\fontsize{{12}}{{15}}\\selectfont\\color{{ink2}} {tex(d.get('lede'))}\\par}}" if d.get('lede') else ''}
{f"\\meta{{{meta}}}\\par" if meta else ''}
\vspace{{1mm}}
\begin{{minipage}}[t]{{0.47\linewidth}}
{f"\\eyebrow[c{col}]{{Un po' di storia}}\\par{{\\fontsize{{9.5}}{{12.6}}\\selectfont\\justifying {tex(hist)}\\par}}" if hist else ''}
\end{{minipage}}\hfill
\begin{{minipage}}[t]{{0.47\linewidth}}
{(f"\\eyebrow[c{col}]{{Il percorso}}\\par" + chr(10) + route_tikz(d['stops'], col, 8.1, 6.4)) if route_tikz(d['stops'], col, 8.1, 6.4) else ''}
\end{{minipage}}
{"\\newpage" if (hero or any(n and x.get("storia") for n, x in numbered_stops(d))) else "\\par\\vspace{6mm}"}
\eyebrow[c{col}]{{Orari del giorno}}\par\vspace{{1mm}}
\begin{{multicols}}{{2}}
{schedule(d, col)}
\end{{multicols}}
""")
        if len(strip) == 3:
            imgs = "\\hfill".join(f"\\includegraphics[width=0.322\\linewidth]{{{p}}}" for p in strip)
            T.append(rf"""
\vspace{{1mm}}\noindent{imgs}\par
\meta{{Foto del viaggio · {tex(d['title'])}}}
""")
        cards = []
        for n, s in numbered_stops(d):
            if not (n and s.get("storia")):
                continue
            link = maps(s)
            name = f"\\href{{{url(link)}}}{{{tex(s['name'])}}}" if link else tex(s["name"])
            m = " · ".join(x for x in [s.get("time") and f"ore {s['time']}", CAT.get(s["cat"], "")] if x)
            cards.append(rf"""
\begin{{tcolorbox}}[enhanced,breakable=false,colback=white,colframe=line,boxrule=0.5pt,arc=2.5mm,left=3.5mm,right=3.5mm,top=2.5mm,bottom=2.5mm]
\label{{luogo-{i}-{n}}}
{{\sffamily\bfseries\fontsize{{7}}{{9}}\selectfont\color{{c{col}}}{n}\quad\MakeUppercase{{{tex(m)}}}\hfill{{\display\bfseries\fontsize{{13}}{{13}}\selectfont {tex(s.get('anno'))}}}\par}}\vspace{{0.6mm}}
{{\display\bfseries\fontsize{{13.5}}{{15.5}}\selectfont {name}\par}}\vspace{{0.8mm}}
{{\fontsize{{9}}{{11.8}}\selectfont\justifying {tex(s['storia'])}\par}}
{f"\\begin{{cercare}}{{c{col}}}{tex(s['cercare'])}\\end{{cercare}}" if s.get('cercare') else ''}
\end{{tcolorbox}}""")
        if cards:
            T.append(rf"""
\vspace{{4mm}}
\eyebrow[c{col}]{{{tex(d['title'])}}}\par
{{\display\bfseries\fontsize{{24}}{{27}}\selectfont I luoghi\par}}
\vspace{{1mm}}
\begin{{multicols}}{{2}}
{"".join(cards)}
\end{{multicols}}
""")
    idx = "\n".join(rf"{tex(nm)}\dotfill\pageref{{{lab}}}\par" for nm, lab in place_index(c))
    T.append(rf"""
\clearpage
\giorno{{Indice dei luoghi}}
\eyebrow{{Indice}}\par
{{\display\bfseries\fontsize{{30}}{{33}}\selectfont I luoghi, in ordine\par}}
\vspace{{3mm}}
{{\sffamily\fontsize{{9}}{{12}}\selectfont\setlength{{\parskip}}{{1.4mm}}
\begin{{multicols}}{{3}}
{idx}
\end{{multicols}}}}
\vfill
\meta{{Le note storiche sono state scritte e verificate su fonti pubbliche (siti ufficiali dei luoghi, enti di tutela, enciclopedie) nell'ottobre 2026: orari, aperture e opere esposte possono cambiare. Questo volume è per uso personale: grazie per non condividerlo.}}
\end{{document}}
""")
    return "".join(T)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="cartella della città, es. Londra")
    ap.add_argument("--stile", choices=["taccuino", "atlante"], default="taccuino")
    ap.add_argument("--out", help="percorso del PDF (predefinito _pdf/<Città>-<stile>.pdf)")
    ap.add_argument("--solo-tex", action="store_true", help="scrive solo il sorgente .tex")
    a = ap.parse_args()

    src = os.path.join(ROOT, "_privato", a.slug, "citta.json")
    if not os.path.exists(src):
        sys.exit(f"Manca {src}: lancia prima scripts/sync_itinerario.py")
    c = json.load(open(src, encoding="utf-8"))
    out = a.out or os.path.join(ROOT, "_pdf", f"{a.slug}-{a.stile}.pdf")
    work = os.path.join(ROOT, "_pdf", "tex")
    os.makedirs(work, exist_ok=True)
    name = f"{a.slug}-{a.stile}"
    texfile = os.path.join(work, name + ".tex")
    open(texfile, "w", encoding="utf-8").write((taccuino if a.stile == "taccuino" else atlante)(c))
    print(f"Sorgente: {texfile}")
    if a.solo_tex:
        return
    for _ in range(2):  # due passate: rimandi di pagina dell'indice
        r = subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", name + ".tex"],
                           cwd=work, capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-3000:], file=sys.stderr)
            sys.exit("XeLaTeX non è riuscito a compilare il volume")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    shutil.copy(os.path.join(work, name + ".pdf"), out)
    print(f"PDF pronto: {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
