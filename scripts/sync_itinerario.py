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

Uso:
    NOTION_TOKEN=secret_xxx python3 scripts/sync_itinerario.py

Lo lancia ogni notte .github/workflows/sync-itinerario.yml.
"""
import json, os, re, sys, shutil, datetime, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

TOKEN = os.environ.get("NOTION_TOKEN")
DESTINATIONS_DB = "8ac2578e062983ccaa6901c6ea59b7eb"
ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "itinerario")
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
    """Raccoglie i database annidati nella pagina città e i testi Storia/Paesaggio/Monumenti."""
    pending = None
    for b in children(block_id):
        t = b["type"]
        if t == "child_database":
            found["dbs"].append(b["id"]); continue
        if t.startswith("heading_"):
            pending = INTRO.get(plain(b[t]["rich_text"]).lower())
        elif t == "paragraph" and pending:
            txt = plain(b[t]["rich_text"])
            if txt and pending not in found["intro"]:
                found["intro"][pending] = short(txt); pending = None
        if b.get("has_children") and t != "child_page":
            walk(b["id"], found)


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
    for pg in pages:
        name = prop(pg, "Name")
        x = EXTRA.get(name, {})
        slug = x.get("slug", name)
        tz = ZoneInfo(x.get("tz", "Europe/Rome"))
        found = {"dbs": [], "intro": {}}
        walk(pg["id"], found)

        # Coordinate già note (export precedente): servono se l'API non restituisce il campo Luogo.
        known = {}
        prev = os.path.join(OUT, slug, "citta.json")
        if os.path.exists(prev):
            for d in json.load(open(prev, encoding="utf-8")).get("days", []):
                for st in d.get("stops", []):
                    if st.get("lat") is not None:
                        known[st["name"].lower()] = (st["lat"], st["lng"])

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
                if place.get("lat") is None and act.lower() in known:
                    place = {"lat": known[act.lower()][0], "lng": known[act.lower()][1]}
                stops.append({
                    "date": local.date().isoformat(),
                    "time": prop(row, "Time") or (local.strftime("%H:%M") if "T" in start else ""),
                    "sort": local.isoformat(),
                    "name": act, "type": typ or "", "cat": CATEGORIE.get(typ, "luoghi"),
                    "notes": prop(row, "Notes") or "",
                    "lat": place.get("lat"), "lng": place.get("lng"),
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
        cities.append(city)

        page = {**city, "days": days}
        with open(os.path.join(folder, "citta.json"), "w", encoding="utf-8") as f:
            json.dump(page, f, ensure_ascii=False, indent=2)
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
            f.write(embed(template, page))

    cities.sort(key=lambda c: (c["start"] or "", c["name"]), reverse=True)  # più recente prima
    data = {"updated": datetime.date.today().isoformat(), "cities": cities}
    with open(os.path.join(OUT, "viaggi.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(embed(home, data))
    print(f"{len(cities)} città → {OUT}")


if __name__ == "__main__":
    main()
