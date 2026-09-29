#!/usr/bin/env python3
"""
Sincronizza le materie di Ingegneria Civile da Notion a triennale/materie.json.

Legge i due database Notion (triennale e magistrale), le pagine delle materie
(per i link al materiale, es. cartelle MEGA) e le relazioni con "Books University",
applica le eccezioni di triennale/materie-overrides.json e scrive un JSON che la
pagina /triennale/ carica all'avvio.

Solo libreria standard: nessuna dipendenza da installare.

Variabili d'ambiente:
  NOTION_TOKEN          token dell'integrazione interna (obbligatorio)
  NOTION_DB_TRIENNALE   ID database triennale  (default: "Laurea Ingegneria")
  NOTION_DB_MAGISTRALE  ID database magistrale (default: "Laurea Magistrale")
  NOTION_API_BASE       solo per i test (default: https://api.notion.com/v1)
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "triennale" / "materie.json"
OVERRIDES = ROOT / "triennale" / "materie-overrides.json"
LIBRERIA = ROOT / "libreria" / "data.json"

API = os.environ.get("NOTION_API_BASE", "https://api.notion.com/v1").rstrip("/")
TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
VERSION = "2022-06-28"
VERSION_DS = "2025-09-03"   # API con le "origini dati" (data sources), usata se serve

CORSI = {
    "triennale": {
        "db": os.environ.get("NOTION_DB_TRIENNALE") or "27e2578e062980d9b36ac848eecfe341",
        "titolo_db": "Laurea Ingegneria",
        "laurea": "Triennale",
    },
    "magistrale": {
        "db": os.environ.get("NOTION_DB_MAGISTRALE") or "2d22578e0629808fb367d8c050f7ead0",
        "titolo_db": "Laurea Magistrale",
        "laurea": "Magistrale",
    },
}

PREFISSO_CI = re.compile(r"^\s*corso\s+integrato\s*:?\s*", re.I)
ORDINE_PROVE = ["Scritto", "Orale", "Pratico"]


# --------------------------------------------------------------------------- API

class NonTrovato(RuntimeError):
    pass


def api(method, path, body=None, tentativi=5, version=VERSION):
    url = f"{API}/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Notion-Version": version,
        "Content-Type": "application/json",
    })
    for i in range(tentativi):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tentativi - 1:
                attesa = float(e.headers.get("Retry-After") or 2 ** i)
                print(f"  … {e.code} su {path}, riprovo tra {attesa:.0f}s")
                time.sleep(attesa)
                continue
            if e.code == 401:
                raise RuntimeError("token Notion non valido o scaduto: controlla il segreto NOTION_TOKEN su GitHub") from None
            if e.code == 404:
                raise NonTrovato(f"{path}: l'integrazione non vede questa risorsa (non collegata o ID errato)") from None
            dettaglio = e.read().decode(errors="replace")[:400]
            raise RuntimeError(f"Notion {e.code} su {method} {path}: {dettaglio}") from None
        except urllib.error.URLError as e:
            if i < tentativi - 1:
                time.sleep(2 ** i)
                continue
            raise RuntimeError(f"Rete non raggiungibile ({path}): {e}") from None


def paginate(method, path, body=None, version=VERSION):
    cursor = None
    while True:
        if method == "POST":
            b = dict(body or {})
            if cursor:
                b["start_cursor"] = cursor
            res = api("POST", path, b, version=version)
        else:
            sep = "&" if "?" in path else "?"
            res = api("GET", f"{path}{sep}page_size=100" + (f"&start_cursor={cursor}" if cursor else ""), version=version)
        yield from res.get("results", [])
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")


def trova_db(corso):
    """Usa l'ID configurato; se Notion non lo trova, cerca il database per titolo."""
    cfg = CORSI[corso]
    try:
        api("GET", f"databases/{cfg['db']}")
        return cfg["db"]
    except RuntimeError as e:
        print(f"  ! database {corso}: {e}. Cerco «{cfg['titolo_db']}» tra quelli condivisi…")
    trovati = []
    for version, tipo in ((VERSION, "database"), (VERSION_DS, "data_source")):
        try:
            res = api("POST", "search", {"query": cfg["titolo_db"], "filter": {"property": "object", "value": tipo}}, version=version)
        except RuntimeError:
            continue
        for db in res.get("results", []):
            titolo = "".join(t.get("plain_text", "") for t in db.get("title", []))
            trovati.append(titolo)
            if titolo.strip().lower() == cfg["titolo_db"].lower():
                # per una data source serve l'ID del database che la contiene
                parent = db.get("parent") or {}
                return parent.get("database_id") or db["id"]
    visti = ", ".join(sorted(set(t for t in trovati if t))) or "nessuno"
    raise RuntimeError(
        f"database «{cfg['titolo_db']}» ({corso}) non accessibile. Database visti dall'integrazione: {visti}. "
        f"Apri la pagina del corso su Notion → ••• → Connessioni e aggiungi l'integrazione."
    )


def righe_db(db):
    """Pagine del database. Se il database usa le "origini dati", passa all'API nuova."""
    try:
        return list(paginate("POST", f"databases/{db}/query", {"page_size": 100}))
    except RuntimeError as e:
        print(f"  … query classica non riuscita ({e}); provo con le origini dati")
    info = api("GET", f"databases/{db}", version=VERSION_DS)
    righe = []
    for ds in info.get("data_sources", []):
        righe += paginate("POST", f"data_sources/{ds['id']}/query", {"page_size": 100}, version=VERSION_DS)
    return righe


# ------------------------------------------------------------------ proprietà

def testo(rich):
    return "".join(t.get("plain_text", "") for t in rich or []).strip()


def valori(prop):
    """Restituisce sempre una lista di stringhe (o ID per le relazioni)."""
    if not prop:
        return []
    t = prop.get("type")
    v = prop.get(t)
    if t in ("title", "rich_text"):
        s = testo(v)
        return [x.strip() for x in s.split(",") if x.strip()] if t == "rich_text" else ([s] if s else [])
    if t == "number":
        return [] if v is None else [str(v)]
    if t in ("select", "status"):
        return [v["name"]] if v else []
    if t == "multi_select":
        return [x["name"] for x in v or []]
    if t == "relation":
        return [x["id"] for x in v or []]
    if t == "people":
        return [x.get("name", "") for x in v or [] if x.get("name")]
    if t == "formula":
        f = v or {}
        x = f.get(f.get("type"))
        return [] if x in (None, "") else [str(x)]
    if t == "rollup":
        r = v or {}
        if r.get("type") == "array":
            out = []
            for el in r.get("array", []):
                out += valori(el)
            return out
        x = r.get(r.get("type"))
        return [] if x is None else [str(x)]
    return []


def prop(page, *nomi):
    props = page.get("properties", {})
    low = {k.lower(): k for k in props}
    for n in nomi:
        k = low.get(n.lower())
        if k:
            return valori(props[k])
    return []


def titolo_pagina(page):
    for p in page.get("properties", {}).values():
        if p.get("type") == "title":
            return testo(p["title"])
    return ""


def numero(lista):
    for x in lista:
        m = re.search(r"\d+(?:[.,]\d+)?", x)
        if m:
            n = float(m.group().replace(",", "."))
            return int(n) if n.is_integer() else n
    return None


def semestre(lista):
    s = " ".join(lista).lower()
    uno, due = bool(re.search(r"\b1\b", s)), bool(re.search(r"\b2\b", s))
    if uno and due:
        return "1-2"
    return "1" if uno else "2" if due else ""


def prove(lista):
    trovate = {x.strip().capitalize() for x in lista}
    return [p for p in ORDINE_PROVE if p in trovate] + sorted(trovate - set(ORDINE_PROVE))


# ------------------------------------------------------------ link nei blocchi

def link_pagina(page_id, profondita=0):
    """URL esterni trovati nel corpo della pagina, nell'ordine in cui compaiono."""
    out = []
    for b in paginate("GET", f"blocks/{page_id}/children"):
        t = b.get("type")
        v = b.get(t, {}) or {}
        if t in ("bookmark", "embed", "link_preview") and v.get("url"):
            out.append({"url": v["url"], "caption": testo(v.get("caption"))})
        for rt in v.get("rich_text", []) or []:
            href = rt.get("href") or ((rt.get("text") or {}).get("link") or {}).get("url")
            if href and href.startswith("http") and "notion." not in href:
                out.append({"url": href, "caption": ""})
        if b.get("has_children") and t not in ("child_page", "child_database") and profondita < 3:
            out += link_pagina(b["id"], profondita + 1)
    visti, unici = set(), []
    for l in out:
        if l["url"] not in visti:
            visti.add(l["url"])
            unici.append(l)
    return unici


# ------------------------------------------------------------------ costruzione

def carica_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def main():
    if not TOKEN:
        sys.exit("NOTION_TOKEN mancante: aggiungilo in Settings → Secrets and variables → Actions.")

    overrides = {k.lower(): v for k, v in carica_json(OVERRIDES, {}).items() if not k.startswith("_")}
    precedente = carica_json(OUT, {})
    # Note già scritte (es. "364 MB · 51 file") conservate per URL: l'API non le fornisce.
    note = {}
    for lista in (precedente.get("corsi") or {}).values():
        for m in lista:
            for l in m.get("link", []) + [x for mod in m.get("moduli", []) for x in mod.get("link", [])]:
                if l.get("nota"):
                    note[l["url"]] = l["nota"]
    libri_noti = {x["id"]: x.get("title", "") for x in carica_json(LIBRERIA, {}).get("items", [])}

    def titolo_libro(i):
        if i in libri_noti:
            return libri_noti[i]
        try:
            libri_noti[i] = titolo_pagina(api("GET", f"pages/{i}"))
        except RuntimeError:
            libri_noti[i] = ""
        return libri_noti[i]

    def fai_link(raw, titolo):
        return [{"titolo": l["caption"] or titolo, "url": l["url"], "nota": note.get(l["url"], "")} for l in raw]

    risultato, usati = {}, set()
    for corso, cfg in CORSI.items():
        db = trova_db(corso)
        pagine = [p for p in righe_db(db) if not p.get("archived") and not p.get("in_trash")]
        print(f"[{corso}] {len(pagine)} pagine nel database")

        voci = {}
        for p in pagine:
            nome_notion = titolo_pagina(p)
            if not nome_notion:
                continue
            laurea = prop(p, "Laurea")
            if laurea and cfg["laurea"].lower() not in " ".join(laurea).lower():
                continue
            voci[p["id"]] = {
                "_page": p["id"],
                "_notion": nome_notion,
                "_parent": (prop(p, "Parent item", "Elemento principale", "Parent") or [None])[0],
                "anno": numero(prop(p, "Anno")),
                "nome": PREFISSO_CI.sub("", nome_notion).strip(),
                "integrato": bool(PREFISSO_CI.match(nome_notion)),
                "docenti": prop(p, "Docente", "Docenti"),
                "cfu": numero(prop(p, "CFU")) or 0,
                "sem": semestre(prop(p, "Semestre")),
                "prove": prove(prop(p, "Tipologia esame", "Tipologia Esame", "Esame")),
                "libri": prop(p, "Books University", "Libri"),
            }

        materie = [v for v in voci.values() if not v["_parent"] or v["_parent"] not in voci]
        figli = {}
        for v in voci.values():
            if v["_parent"] in voci:
                figli.setdefault(v["_parent"], []).append(v)

        out = []
        for m in materie:
            raw = link_pagina(m["_page"])
            mods = figli.get(m["_page"], [])
            titolo_m = PREFISSO_CI.sub("", m["_notion"]).lower()

            def pos(mod):
                base = re.sub(r"\s*\d+$", "", mod["nome"]).lower()
                i = titolo_m.find(base)
                return (i if i >= 0 else 10_000, mod["nome"].lower())

            mods.sort(key=pos)
            moduli = []
            for mod in mods:
                moduli.append({
                    "nome": mod["nome"], "docenti": mod["docenti"], "cfu": mod["cfu"],
                    "sem": mod["sem"], "prove": mod["prove"],
                    "link": fai_link(link_pagina(mod["_page"]), "Materiale del modulo"),
                })

            # Più cartelle nella pagina del corso integrato e moduli senza link propri:
            # la 1ª cartella va al 1° modulo, la 2ª al 2°, …
            if len(moduli) > 1 and len(raw) == len(moduli) and not any(x["link"] for x in moduli):
                for mod, l in zip(moduli, raw):
                    mod["link"] = fai_link([l], "Materiale del modulo")
                link = []
            else:
                link = fai_link(raw, "Materiale del corso")

            voce = {
                "anno": m["anno"], "nome": m["nome"],
                **({"integrato": True} if m["integrato"] else {}),
                "docenti": m["docenti"], "cfu": m["cfu"], "sem": m["sem"], "prove": m["prove"],
                "link": link,
                "libri": [{"id": i, "titolo": titolo_libro(i)} for i in dict.fromkeys(m["libri"])],
            }
            if moduli:
                voce["moduli"] = moduli
            # Corso integrato senza modalità d'esame: unione di quelle dei moduli
            if not voce["prove"] and moduli:
                voce["prove"] = prove([p for x in moduli for p in x["prove"]])

            ov = overrides.get(m["_notion"].lower()) or overrides.get(m["nome"].lower())
            if ov:
                usati.add(m["_notion"].lower() if m["_notion"].lower() in overrides else m["nome"].lower())
                voce.update({k: v for k, v in ov.items() if not k.startswith("_")})
            if voce["anno"] is None:
                print(f"  ! «{m['_notion']}» senza Anno su Notion: la salto")
                continue
            voce["_ordine"] = m["_notion"].lower()
            out.append(voce)

        out.sort(key=lambda v: (v["anno"], v.pop("_ordine")))
        n_link = sum(len(v["link"]) + sum(len(x["link"]) for x in v.get("moduli", [])) for v in out)
        print(f"[{corso}] {len(out)} materie, {n_link} link al materiale")
        if not out:
            sys.exit(f"Nessuna materia trovata per {corso}: non sovrascrivo materie.json.")
        risultato[corso] = out

    for k in overrides:
        if k not in usati:
            print(f"  ! eccezione non usata in materie-overrides.json: «{k}» (materia rinominata su Notion?)")

    nuovo = {"corsi": risultato}
    if (precedente.get("corsi") or {}) == risultato:
        print("Nessuna modifica rispetto a materie.json.")
        return
    riepilogo(precedente.get("corsi") or {}, risultato)
    nuovo = {"aggiornato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **nuovo}
    OUT.write_text(json.dumps(nuovo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Scritto {OUT.relative_to(ROOT)}")


def riepilogo(prima, dopo):
    for corso in dopo:
        a = {m["nome"]: m for m in prima.get(corso, [])}
        b = {m["nome"]: m for m in dopo[corso]}
        for n in sorted(b.keys() - a.keys()):
            print(f"  + [{corso}] nuova materia: {n}")
        for n in sorted(a.keys() - b.keys()):
            print(f"  - [{corso}] materia rimossa: {n}")
        for n in sorted(a.keys() & b.keys()):
            if a[n] != b[n]:
                campi = sorted(k for k in set(a[n]) | set(b[n]) if a[n].get(k) != b[n].get(k))
                print(f"  ~ [{corso}] {n}: {', '.join(campi)}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"Errore: {e}")
