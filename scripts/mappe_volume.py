#!/usr/bin/env python3
"""
Mappe del volume: scarica da OpenStreetMap (Overpass API) strade, acqua, parchi e
ferrovie delle zone visitate ogni giorno e le salva semplificate in
scripts/volume/mappe/<Città>-<giorno>.json. volume_latex.py le usa come sfondo
del percorso del giorno.

    python scripts/mappe_volume.py            → tutte le aree di scripts/volume/mappe/aree.json
    python scripts/mappe_volume.py --forza    → riscarica anche le mappe già presenti

Le aree (sud, ovest, nord, est) sono in aree.json: contengono solo il riquadro del
quartiere, non le tappe. Lo lancia .github/workflows/mappe-volume.yml, perché
Overpass non è raggiungibile da ovunque; le mappe si scaricano una volta sola.
Dati © OpenStreetMap contributors, licenza ODbL.

Requisiti: pip install shapely
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from shapely.geometry import LineString, Polygon, box, mapping
from shapely.ops import polygonize, unary_union

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "volume", "mappe")
SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
MAIN = "motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"
MINOR = "residential|unclassified|pedestrian|living_street|service"


def query(s, w, n, e, minor):
    bb = f"{s},{w},{n},{e}"
    return f"""[out:json][timeout:180];
(
  way["highway"~"^({MAIN})$"]({bb});
  {f'way["highway"~"^({MINOR})$"]({bb});' if minor else ''}
  way["railway"="rail"]({bb});
  way["natural"="water"]({bb});
  relation["natural"="water"]({bb});
  way["waterway"="riverbank"]({bb});
  way["leisure"~"^(park|garden|common)$"]({bb});
  relation["leisure"~"^(park|garden)$"]({bb});
  way["landuse"~"^(grass|recreation_ground|cemetery|forest|meadow)$"]({bb});
);
out geom;"""


def overpass(q):
    data = urllib.parse.urlencode({"data": q}).encode()
    for tentativo in range(4):
        for srv in SERVERS:
            try:
                req = urllib.request.Request(srv, data=data, headers={"User-Agent": "danieledemichele.it volume di viaggio"})
                with urllib.request.urlopen(req, timeout=240) as r:
                    return json.load(r)
            except Exception as ex:
                print(f"  {srv}: {ex}", file=sys.stderr)
        time.sleep(20 * (tentativo + 1))
    sys.exit("Overpass non risponde")


def coords(geom):
    return [(p["lon"], p["lat"]) for p in geom]


def rnd(lst):
    return [[round(x, 5), round(y, 5)] for x, y in lst]


def build(area, res):
    s, w, n, e = area
    frame = box(w, s, e, n)
    tol = max(e - w, n - s) / 2500           # semplificazione proporzionale alla zona
    roads = {"main": [], "minor": []}
    rail, water_parts, green_parts = [], [], []
    for el in res.get("elements", []):
        t = el.get("tags", {})
        if el["type"] == "way" and "geometry" in el:
            pts = coords(el["geometry"])
            if len(pts) < 2:
                continue
            hw = t.get("highway")
            if hw:
                (roads["main"] if hw.split("_")[0] in MAIN.split("|") or hw.endswith("_link") else roads["minor"]).append(LineString(pts))
            elif t.get("railway") == "rail":
                rail.append(LineString(pts))
            elif len(pts) >= 4 and pts[0] == pts[-1]:
                poly = Polygon(pts).buffer(0)
                (water_parts if t.get("natural") == "water" or t.get("waterway") == "riverbank" else green_parts).append(poly)
        elif el["type"] == "relation":
            outer = [LineString(coords(m["geometry"])) for m in el.get("members", [])
                     if m.get("role") == "outer" and m.get("geometry") and len(m["geometry"]) > 1]
            inner = [LineString(coords(m["geometry"])) for m in el.get("members", [])
                     if m.get("role") == "inner" and m.get("geometry") and len(m["geometry"]) > 1]
            polys = list(polygonize(unary_union(outer))) if outer else []
            if not polys:
                continue
            g = unary_union(polys)
            holes = list(polygonize(unary_union(inner))) if inner else []
            if holes:
                g = g.difference(unary_union(holes))
            (water_parts if t.get("natural") == "water" else green_parts).append(g)

    def lines(lst):
        out = []
        for g in lst:
            c = g.intersection(frame).simplify(tol)
            for part in getattr(c, "geoms", [c]):
                if part.geom_type == "LineString" and len(part.coords) > 1:
                    out.append(rnd(part.coords))
        return out

    def polys(lst):
        if not lst:
            return []
        g = unary_union([p for p in lst if p.is_valid and not p.is_empty]).intersection(frame).simplify(tol)
        out = []
        for part in getattr(g, "geoms", [g]):
            if part.geom_type == "Polygon" and part.area > 0:
                out.append({"esterno": rnd(part.exterior.coords), "buchi": [rnd(r.coords) for r in part.interiors]})
        return out

    return {"area": area, "fonte": "© OpenStreetMap contributors (ODbL)",
            "strade": {"principali": lines(roads["main"]), "secondarie": lines(roads["minor"])},
            "ferrovie": lines(rail), "acqua": polys(water_parts), "verde": polys(green_parts)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forza", action="store_true")
    a = ap.parse_args()
    aree = json.load(open(os.path.join(DIR, "aree.json"), encoding="utf-8"))
    for slug, giorni in aree.items():
        for i, area in giorni.items():
            out = os.path.join(DIR, f"{slug}-{i}.json")
            if os.path.exists(out) and not a.forza:
                continue
            s, w, n, e = area
            # nelle zone grandi (oltre ~4 km) solo le strade principali, così la mappa resta leggibile
            minor = (e - w) * 69 < 4 and (n - s) * 111 < 4
            print(f"{slug} giorno {i}: {area} ({'tutte le strade' if minor else 'strade principali'})")
            data = build(area, overpass(query(s, w, n, e, minor)))
            json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"))
            print(f"  {os.path.getsize(out) // 1024} KB · {len(data['strade']['principali'])} + {len(data['strade']['secondarie'])} strade, "
                  f"{len(data['acqua'])} acqua, {len(data['verde'])} verde")
            time.sleep(5)


if __name__ == "__main__":
    main()
