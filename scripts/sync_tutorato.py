#!/usr/bin/env python3
"""
Sincronizza il tutorato da Notion a tutorato/incontri.json e tutorato/appunti/.

Legge il database Notion "Tutorato" (pagina "Tutorato – Scienza delle Costruzioni"):
  Titolo, Tipo (Incontro / Compito svolto), Corso, Argomenti, Anno accademico,
  Data, Allegato.
Gli allegati di Notion hanno link che scadono dopo circa un'ora, quindi i PDF vengono
scaricati nel repo (tutorato/appunti/) e la pagina /tutorato/ li apre da lì.

Solo libreria standard. Riusa le funzioni API di sync_materie.py.

Variabili d'ambiente:
  NOTION_TOKEN        token dell'integrazione interna (obbligatorio)
  NOTION_DB_TUTORATO  ID del database (default: database "Tutorato")
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_materie as sm  # noqa: E402  (api, righe_db, prop, testo, TOKEN)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tutorato" / "incontri.json"
APPUNTI = ROOT / "tutorato" / "appunti"
DB = os.environ.get("NOTION_DB_TUTORATO") or "3672578e062980428c0ddf2edca534d7"
ROMA = ZoneInfo("Europe/Rome")

CORSI = {
    "ingegneria civile": "civile",
    "civile": "civile",
    "architettura": "architettura",
    "ingegneria gestionale": "gestionale",
    "gestionale": "gestionale",
    "ingegneria ambientale": "ambientale",
    "ambientale": "ambientale",
}


def anno_accademico(d: date) -> str:
    """L'anno accademico parte a settembre: 2026-10-01 → 2026/27."""
    inizio = d.year if d.month >= 9 else d.year - 1
    return f"{inizio}/{str(inizio + 1)[-2:]}"


def data_ora(page):
    """(giorno ISO, ora inizio, ora fine) nel fuso di Roma."""
    p = page.get("properties", {}).get("Data") or {}
    v = p.get("date") or {}
    if not v.get("start"):
        return None, "", ""

    def conv(s):
        if not s:
            return None, ""
        if "T" not in s:
            return s, ""
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ROMA)
        dt = dt.astimezone(ROMA)
        return dt.date().isoformat(), dt.strftime("%H:%M")

    giorno, inizio = conv(v["start"])
    _, fine = conv(v.get("end"))
    return giorno, inizio, fine


def nome_file(nome: str) -> str:
    """Nome sicuro per il repo: niente spazi, niente suffissi "_(1)" dei duplicati."""
    nome = re.sub(r"[\s_]*\(\d+\)(?=\.[A-Za-z0-9]+$)", "", nome.strip())
    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", nome)
    nome = re.sub(r"_+(?=\.[A-Za-z0-9]+$)", "", nome)
    return nome or "allegato.pdf"


def allegati(page, usati):
    p = page.get("properties", {}).get("Allegato") or {}
    out = []
    for f in p.get("files") or []:
        url = (f.get(f.get("type")) or {}).get("url")
        if not url:
            continue
        nome = nome_file(f.get("name") or url.rsplit("/", 1)[-1].split("?")[0])
        base, ext = os.path.splitext(nome)
        k = 2
        while nome in usati:                       # due file con lo stesso nome in pagine diverse
            nome = f"{base}-{k}{ext}"
            k += 1
        usati.add(nome)
        dest = APPUNTI / nome
        if not dest.exists():                      # i file di Notion non cambiano: si scaricano una volta
            print(f"  ↓ {nome}")
            sicuro = urllib.parse.quote(url, safe=":/?&=%#+@,;~!$'()*[]")
            try:
                with urllib.request.urlopen(sicuro, timeout=120) as r:
                    dest.write_bytes(r.read())
            except (urllib.error.URLError, OSError) as e:
                raise RuntimeError(f"download di {nome} non riuscito: {e}") from None
        out.append({"nome": os.path.splitext(nome)[0], "file": nome})
    return out


def main():
    if not sm.TOKEN:
        raise RuntimeError("manca NOTION_TOKEN")
    APPUNTI.mkdir(parents=True, exist_ok=True)

    try:
        righe = sm.righe_db(DB)
    except sm.NonTrovato:
        raise RuntimeError(
            "database «Tutorato» non accessibile: su Notion apri la pagina "
            "«Tutorato – Scienza delle Costruzioni» → ••• → Connessioni e aggiungi l'integrazione "
            "usata per le materie."
        ) from None

    anni, usati = {}, set()
    for page in righe:
        if page.get("archived") or page.get("in_trash"):
            continue
        giorno, inizio, fine = data_ora(page)
        if not giorno:
            print(f"  ! «{sm.testo(page['properties'].get('Titolo', {}).get('title'))}» senza data: saltato")
            continue
        tipo = (sm.prop(page, "Tipo") or ["Incontro"])[0].lower()
        corsi = [CORSI[c.lower()] for c in sm.prop(page, "Corso") if c.lower() in CORSI]
        aa = (sm.prop(page, "Anno accademico") or [anno_accademico(date.fromisoformat(giorno))])[0]
        titolo = (sm.prop(page, "Titolo") or [""])[0]
        voce = {
            "data": giorno,
            "argomenti": sm.prop(page, "Argomenti"),
            "corsi": corsi,
            "allegati": allegati(page, usati),
        }
        gruppo = anni.setdefault(aa, {"incontri": [], "compiti": []})
        if tipo.startswith("compito"):
            # il titolo descrive la prova ("Appello di febbraio", …)
            voce["titolo"] = re.sub(r"^\s*compito\s*\d*\s*[–-]\s*", "", titolo, flags=re.I) or titolo
            gruppo["compiti"].append(voce)
        else:
            voce["inizio"], voce["fine"] = inizio or "00:00", fine or inizio or "00:00"
            gruppo["incontri"].append(voce)

    for g in anni.values():
        g["incontri"].sort(key=lambda x: x["data"])
        g["compiti"].sort(key=lambda x: x["data"])

    # L'anno accademico in corso c'è sempre, anche se ancora vuoto (scheda "non ancora iniziato")
    anni.setdefault(anno_accademico(date.today()), {"incontri": [], "compiti": []})

    # Elimina i PDF che non sono più collegati a nessuna pagina
    for f in APPUNTI.iterdir():
        if f.is_file() and f.name not in usati and f.name != ".gitkeep":
            print(f"  − {f.name} non più usato, rimosso")
            f.unlink()

    prima = json.loads(OUT.read_text()) if OUT.exists() else {}
    dati = {"anni": dict(sorted(anni.items(), reverse=True))}
    if prima.get("anni") == dati["anni"]:
        print("Nessuna modifica nei dati del tutorato.")
        return
    dati = {"aggiornato": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **dati}
    OUT.write_text(json.dumps(dati, ensure_ascii=False, indent=1) + "\n")
    n_i = sum(len(g["incontri"]) for g in anni.values())
    n_c = sum(len(g["compiti"]) for g in anni.values())
    print(f"incontri.json scritto: {n_i} incontri, {n_c} compiti svolti, {len(usati)} file.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"Errore: {e}")
