#!/usr/bin/env python3
"""
Notion → /itinerario: esporta i viaggi dal Travel Planner per le pagine del sito.

  itinerario/index.html           → home (danieledemichele.it/itinerario/), da _home.html
  itinerario/<Città>/index.html   → pagina città (…/itinerario/Londra/), da _citta.html
  itinerario/viaggi.json, itinerario/<Città>/citta.json → gli stessi dati in JSON

I dati vengono incorporati dentro ogni pagina: così le pagine si aprono anche
direttamente dal disco, dove il browser blocca fetch().

Fonti:
  - Notion, Destinations: le città con Status = Visited e le loro proprietà.
  - Notion, Itinerary annidato in ogni città: le tappe con Status = Fatto
    (data e ora, Type, Notes, Luogo con coordinate).
  - scripts/itinerario_extra.json: ciò che Notion non ha (slug dell'URL, paese,
    coordinate della città, titoli e km dei giorni, cartelle delle foto).
  - Itinerari in vendita ("sale": true): le colonne Storia, Da cercare e Anno
    storico dell'Itinerary e la sottopagina "Volume" della città (Londra in breve,
    linea del tempo, introduzioni dei giorni) sono i testi del volume PDF.

Itinerari in vendita: la pagina pubblica contiene solo l'anteprima (i primi
"anteprima_giorni" giorni, 1 se non indicato). L'itinerario completo, con i testi
del volume, va in _privato/<Città>/citta.json, fuori dal sito e fuori da git: il
workflow lo carica nel bucket R2 del Worker di acquisto, che lo consegna solo a
chi ha pagato. Le coordinate delle tappe restano in scripts/coordinate.json
(chiave = hash del nome), perché l'API di Notion non restituisce il campo Luogo.

Uso:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_itinerario.py

Lo lancia ogni notte .github/workflows/sync-itinerario.yml.
"""
import json, os, re, sys, shutil, datetime, hashlib, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

TOKEN = os.environ.get("NOTION_TOKEN")
DESTINATIONS_DB = "8ac2578e062983ccaa6901c6ea59b7eb"
ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "itinerario")
PRIVATO = os.path.join(ROOT, "_privato")
COORD = os.path.join(os.path.dirname(__file__), "coordinate.json")
EXTRA = json.load(open(os.path.join(os.path.dirname(__file__), "itinerario_extra.json"), encoding="utf-8"))

# Type dell'Itinerary → categoria sulle pagine. Gli spostamenti restano nella
# timeline della città ma non contano come "posti visitati".
CATEGORIE = {
    "🍽️ Food": "locali",
    "📸 Sightseeing": "luoghi",
    "🏛️ Museum": "musei",
    "🌳 Park": "parchi",
    "🛍️ Shopping": "negozi",
    "🎟️ Activity": "esperienze",
    "✈️ Travel": "spostamenti",
    "🚕 Transport": "spostamenti",
    "🏨 Check-in": "spostamenti",
    "😴 Rest": "spostamenti",
}
POSTI = {"locali", "luoghi", "musei", "parchi", "negozi", "esperienze"}
INTRO = {"storia": "storia", "paesaggio e territorio": "paesaggio", "monumenti": "monumenti"}


def api(method, path, body=None):
    req = urllib.request.Request(
        "https://api.notion.com/v1" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def query_all(db_id, flt=None):
    rows, cursor = [], None
    while True:
        body = {"page_size": 100}
        if flt: body["filter"] = flt
        if cursor: body["start_cursor"] = cursor
        res = api("POST", f"/databases/{db_id}/query", body)
        rows += res["results"]
        if not res.get("has_more"): return rows
        cursor = res["next_cursor"]


def children(block_id):
    out, cursor = [], None
    while True:
        q = "?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        res = api("GET", f"/blocks/{block_id}/children{q}")
        out += res["results"]
        if not res.get("has_more"): return out
        cursor = res["next_cursor"]


def plain(rich):
    return "".join(t.get("plain_text", "") for t in rich or []).strip()


def prop(page, name):
    p = page["properties"].get(name)
    if not p: return None
    k, v = p["type"], p[p["type"]]
    if k in ("title", "rich_text"): return plain(v)
    if k == "multi_select": return [o["name"] for o in v]
    if k in ("select", "status"): return v["name"] if v else None
    if k in ("number", "checkbox"): return v
    if k == "date": return v["start"] if v else None
    if k == "place" and v:
        lat = v.get("lat", v.get("latitude")); lng = v.get("lon", v.get("lng", v.get("longitude")))
        return {"name": v.get("name"), "lat": lat, "lng": lng}
    return None


def short(text, limit=240):
    text = re.sub(r"\s+", " ", text).strip(); out = ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if len(out) + len(s) > limit and out: break
        out = (out + " " + s).strip()
    return out


def walk(block_id, found):
    """Raccoglie i database annidati nella pagina città, i testi Storia/Paesaggio/Monumenti
    e la sottopagina "Volume" con i testi del PDF."""
    pending = None
    for b in children(block_id):
        t = b["type"]
        if t == "child_database":
            found["dbs"].append(b["id"]); continue
        if t == "child_page":
            if b["child_page"].get("title", "").strip().lower() == "volume":
                found["volume"] = b["id"]
            continue
        if t.startswith("heading_"):
            pending = INTRO.get(plain(b[t]["rich_text"]).lower())
        elif t == "paragraph" and pending:
            txt = plain(b[t]["rich_text"])
            if txt and pending not in found["intro"]:
                found["intro"][pending] = short(txt); pending = None
        if b.get("has_children") and t != "child_page":
            walk(b["id"], found)


def volume(page_id):
    """Testi del volume dalla sottopagina "Volume": un titolo di sezione (H2) con i suoi
    paragrafi diventa l'introduzione; "Linea del tempo" è un elenco «anno · testo»;
    sotto "Giorni" ogni H3 è il titolo di un giorno seguito dalla sua introduzione."""
    out = {"intro": [], "intro_titolo": "", "timeline": [], "giorni": {}}
    sez, giorno = None, None
    for b in children(page_id):
        t = b["type"]
        txt = plain(b[t].get("rich_text")) if isinstance(b.get(t), dict) else ""
        if t == "heading_2" or t == "heading_1":
            sez, giorno = txt.lower(), None
            if sez not in ("linea del tempo", "giorni") and not out["intro_titolo"]:
                out["intro_titolo"] = txt
        elif t == "heading_3" and sez == "giorni":
            giorno = txt; out["giorni"][giorno] = ""
        elif t == "paragraph" and txt:
            if sez == "giorni" and giorno:
                out["giorni"][giorno] = (out["giorni"][giorno] + "\n\n" + txt).strip()
            elif sez and sez not in ("linea del tempo", "giorni"):
                out["intro"].append(txt)
        elif t in ("bulleted_list_item", "numbered_list_item") and sez == "linea del tempo" and txt:
            anno, _, testo = txt.partition("·")
            out["timeline"].append({"anno": anno.strip(), "testo": testo.strip()})
    return out


def coord_key(name):
    return hashlib.sha1(name.strip().lower().encode()).hexdigest()[:12]


STORIA = ("storia", "cercare", "anno")


def anteprima(page, ngiorni):
    """Versione pubblica di un itinerario in vendita: i primi giorni completi, degli
    altri solo titolo, introduzione breve e numeri. Niente testi del volume."""
    days = []
    for i, d in enumerate(page["days"]):
        nposti = sum(1 for s in d["stops"] if s["cat"] in POSTI)
        base = {k: d[k] for k in ("date", "title", "lede", "km", "steps", "temp")}
        if i < ngiorni:
            stops = [{k: v for k, v in s.items() if k not in STORIA} for s in d["stops"]]
            days.append({**base, "photos": d["photos"], "stops": stops, "nposti": nposti})
        else:
            days.append({**base, "photos": [], "stops": [], "locked": True,
                         "nposti": nposti, "nfoto": len(d["photos"])})
    aperti = {s["name"] for d in days for s in d["stops"]}
    places = [p if p["name"] in aperti else {"name": None, "category": p["category"]} for p in page["places"]]
    pub = {k: v for k, v in page.items() if k not in ("days", "places", "volume")}
    return {**pub, "days": days, "places": places, "locked": True, "anteprima_giorni": ngiorni,
            "tot": {"tappe": len(page["places"]), "foto": sum(len(d["photos"]) for d in page["days"])}}


def embed(template, data):
    """Inserisce i dati nella pagina al posto di {{PAGE_DATA}}."""
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("{{PAGE_DATA}}", blob)


def save_cover(page, folder):
    """Salva la copertina della pagina Notion nella cartella della città.
    I file caricati su Notion hanno link che scadono dopo pochi minuti, quindi
    vanno scaricati; le copertine esterne (es. Unsplash) si usano così come sono.
    Restituisce il percorso relativo a itinerario/ oppure l'URL esterno."""
    cov = page.get("cover") or {}
    if cov.get("type") == "external":
        return cov["external"]["url"]
    if cov.get("type") != "file":
        return ""
    url = cov["file"]["url"]
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    existing = [f for f in os.listdir(folder) if f.startswith("cover.")]
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
    except Exception as e:
        print(f"  copertina non scaricata ({e}); tengo quella già salvata")
        return f"{os.path.basename(folder)}/{existing[0]}" if existing else ""
    for old in existing:
        os.remove(os.path.join(folder, old))
    with open(os.path.join(folder, "cover" + ext), "wb") as f:
        f.write(data)
    return f"{os.path.basename(folder)}/cover{ext}"


def photo_urls(base, spec):
    if not spec or not base: return []
    folder, a, b = spec
    return [f"{base}/{folder}/{n}.jpg" for n in range(a, b + 1)]


def main():
    if not TOKEN: sys.exit("Manca NOTION_TOKEN")
    template = open(os.path.join(OUT, "_citta.html"), encoding="utf-8").read()
    home = open(os.path.join(OUT, "_home.html"), encoding="utf-8").read()
    pages = query_all(DESTINATIONS_DB, {"property": "Status", "status": {"equals": "Visited"}})
    cities = []
    coords = json.load(open(COORD, encoding="utf-8")) if os.path.exists(COORD) else {}
    for pg in pages:
        name = prop(pg, "Name")
        x = EXTRA.get(name, {})
        slug = x.get("slug", name)
        tz = ZoneInfo(x.get("tz", "Europe/Rome"))
        found = {"dbs": [], "intro": {}, "volume": None}
        walk(pg["id"], found)

        # Coordinate già note (scripts/coordinate.json ed export precedenti): servono
        # perché l'API di Notion non restituisce il campo Luogo.
        known = {}
        for prev in (os.path.join(OUT, slug, "citta.json"), os.path.join(PRIVATO, slug, "citta.json")):
            if os.path.exists(prev):
                for d in json.load(open(prev, encoding="utf-8")).get("days", []):
                    for st in d.get("stops", []):
                        if st.get("lat") is not None:
                            coords[coord_key(st["name"])] = [st["lat"], st["lng"]]

        stops, seen = [], set()
        for db in found["dbs"]:
            for row in query_all(db):
                act, typ, start = prop(row, "Activity"), prop(row, "Type"), prop(row, "Date")
                if not act or prop(row, "Status") != "Fatto" or not start: continue
                key = (act.lower(), start)
                if key in seen: continue
                seen.add(key)
                dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                local = dt.astimezone(tz) if dt.tzinfo else dt
                place = prop(row, "Luogo") or {}
                if place.get("lat") is None and coord_key(act) in coords:
                    place = {"lat": coords[coord_key(act)][0], "lng": coords[coord_key(act)][1]}
                elif place.get("lat") is not None:
                    coords[coord_key(act)] = [place["lat"], place["lng"]]
                extra = {k: v for k, v in (("storia", prop(row, "Storia")), ("cercare", prop(row, "Da cercare")),
                                            ("anno", prop(row, "Anno storico"))) if v}
                stops.append({
                    "date": local.date().isoformat(),
                    "time": prop(row, "Time") or (local.strftime("%H:%M") if "T" in start else ""),
                    "sort": local.isoformat(),
                    "name": act, "type": typ or "", "cat": CATEGORIE.get(typ, "luoghi"),
                    "notes": prop(row, "Notes") or "",
                    "lat": place.get("lat"), "lng": place.get("lng"), **extra,
                })
        stops.sort(key=lambda s: s["sort"])

        dmeta = x.get("days", {})
        days = []
        for d in sorted({s["date"] for s in stops} | set(dmeta)):
            m = dmeta.get(d, {})
            days.append({
                "date": d, "title": m.get("title", ""), "lede": m.get("lede", ""),
                "km": m.get("km"), "steps": m.get("steps"), "temp": m.get("temp"),
                "photos": photo_urls(x.get("photoBase"), m.get("photos")),
                "stops": [{k: v for k, v in s.items() if k not in ("date", "sort")} for s in stops if s["date"] == d],
            })

        places = [{"name": s["name"], "category": s["cat"]} for s in stops if s["cat"] in POSTI]
        date = prop(pg, "Date (Planned)")
        folder = os.path.join(OUT, slug)
        os.makedirs(folder, exist_ok=True)
        # Copertina: quella della pagina su Notion; se manca, la foto indicata in itinerario_extra.json
        cover = save_cover(pg, folder)
        if not cover and x.get("cover") and x.get("photoBase"):
            cover = f'{x["photoBase"]}/{x["cover"]}'
        city = {
            "name": name, "slug": slug, "label": x.get("label", name),
            "country": x.get("country", ""), "flag": x.get("flag", ""), "iso": x.get("iso"),
            "lat": x.get("lat"), "lng": x.get("lng"),
            "year": int(days[0]["date"][:4]) if days else (int(date[:4]) if date else None),
            "start": days[0]["date"] if days else (date or ""),
            "dates": x.get("dates", ""), "title": x.get("title", name), "lede": x.get("lede", ""),
            "cover": cover, "sale": bool(x.get("sale")),
            "poster": f"{slug}/{x['poster']}" if x.get("poster") and os.path.exists(os.path.join(folder, x["poster"])) else "",
            "ndays": len(days),
            "km": round(sum(d["km"] or 0 for d in days), 1) or None,
            "nights": prop(pg, "Nights"),
            "duration": prop(pg, "Duration") or [], "type": prop(pg, "Type") or [],
            "season": prop(pg, "Time to Travel") or [], "budget": prop(pg, "Budget") or [],
            "transport": prop(pg, "Transportation") or [], "favorite": bool(prop(pg, "Favorite")),
            # Città in cui vivo (casella "Based" in Destinations, o "based": true in itinerario_extra.json)
            "based": bool(prop(pg, "Based")) or bool(x.get("based")),
            "intro": found["intro"], "places": places,
        }
        page = {**city, "days": days}
        if city["sale"]:
            # completo (con i testi del volume) fuori dal sito; sul sito solo l'anteprima
            if found["volume"]:
                page["volume"] = volume(found["volume"])
            os.makedirs(os.path.join(PRIVATO, slug), exist_ok=True)
            with open(os.path.join(PRIVATO, slug, "citta.json"), "w", encoding="utf-8") as f:
                json.dump(page, f, ensure_ascii=False, indent=2)
            page = anteprima(page, int(x.get("anteprima_giorni", 1)))
        else:
            for d in page["days"]:
                d["stops"] = [{k: v for k, v in s.items() if k not in STORIA} for s in d["stops"]]
        cities.append({**city, "places": page["places"], **({"locked": True, "tot": page["tot"]} if page.get("locked") else {})})
        with open(os.path.join(folder, "citta.json"), "w", encoding="utf-8") as f:
            json.dump(page, f, ensure_ascii=False, indent=2)
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
            f.write(embed(template, page))

    cities.sort(key=lambda c: (c["start"] or "", c["name"]), reverse=True)  # più recente prima

    # Prossimi viaggi: le città In Planning o Want to go (senza pagina città, solo scheda e globo)
    STATI = {"In Planning": "In pianificazione", "Want to go": "Da visitare"}
    upcoming = []
    for pg in query_all(DESTINATIONS_DB, {"or": [{"property": "Status", "status": {"equals": s}} for s in STATI]}):
        name = prop(pg, "Name")
        x = EXTRA.get(name, {})
        slug = x.get("slug", name)
        folder = os.path.join(OUT, "prossimi", slug)
        os.makedirs(folder, exist_ok=True)
        cover = save_cover(pg, folder)
        if cover and not cover.startswith("http"):
            cover = "prossimi/" + cover
        upcoming.append({
            "name": name, "slug": slug, "label": x.get("label", name),
            "country": x.get("country", ""), "flag": x.get("flag", ""), "iso": x.get("iso"),
            "lat": x.get("lat"), "lng": x.get("lng"),
            "status": STATI.get(prop(pg, "Status"), ""),
            "planned": prop(pg, "Date (Planned)") or "", "nights": prop(pg, "Nights"),
            "duration": prop(pg, "Duration") or [], "type": prop(pg, "Type") or [],
            "season": prop(pg, "Time to Travel") or [], "budget": prop(pg, "Budget") or [],
            "transport": prop(pg, "Transportation") or [], "cover": cover,
        })
    # prima quelli in pianificazione, poi per data prevista
    upcoming.sort(key=lambda u: (u["status"] != "In pianificazione", u["planned"] or "9999", u["label"]))
    with open(COORD, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(coords.items())), f, indent=0)
    data = {"updated": datetime.date.today().isoformat(), "cities": cities, "upcoming": upcoming}
    with open(os.path.join(OUT, "viaggi.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(embed(home, data))
    print(f"{len(cities)} città → {OUT}")


if __name__ == "__main__":
    main()
