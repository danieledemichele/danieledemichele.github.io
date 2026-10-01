# Portfolio — Daniele De Michele

Sito personale **minimalista** realizzato con **Bootstrap 5** e pubblicato su **GitHub Pages**.  
Layout a due colonne: **card profilo** a sinistra (cover, avatar, dropdown social) e **progetti** a destra (lista semantica e accessibile).

> Screenshot placeholder — salva un'immagine in `assets/screenshot.jpg` e aggiorna il link qui sotto se vuoi mostrarla.
![screenshot](assets/cover.jpg)

---

## ✨ Caratteristiche

- **UI pulita** con card “soft” (`.neo-card`) e spaziatura coerente.
- **A11y**: skip link, alt descrittivi, icone decorative `aria-hidden`, liste semantiche `<dl>`.
- **Dropdown Social “+”** ancorato in alto a destra, **stabile** (non si sposta all’apertura).
- **Progetti** in `<dl>` (termine+descrizione) con anchor e **smooth scroll**.
- **SEO base** + **Open Graph** (preview social).
- **CSP** (Content Security Policy) restrittiva per maggiore sicurezza.
- **Zero build**: HTML/CSS/JS vanilla + Bootstrap via CDN.

---

## 🗂 Struttura del progetto

```
.
├── index.html
├── assets/
│   ├── avatar.jpg
│   ├── cover.jpg
│   ├── screenshot.jpg            # opzionale
│   └── favicon.svg / favicon.ico / favicon-16.png / favicon-32.png / apple-touch-icon.png
├── ripetizioni/                  # vedi sezione "Prenota una ripetizione"
│   └── index.html
├── triennale/                    # vedi sezione "Ingegneria Civile — materie"
│   ├── index.html
│   ├── materie.json              # generato da Notion (non si modifica a mano)
│   └── materie-overrides.json    # eccezioni ai dati di Notion
├── tutorato/                     # vedi sezione "Tutorato — Scienza delle Costruzioni" (anteprima)
│   └── index.html
├── scripts/
│   └── sync_materie.py           # Notion → triennale/materie.json
├── .github/workflows/
│   └── sync-materie.yml          # GitHub Action che lancia lo script
├── libreria/                     # vedi sezione "La Mia Libreria" più sotto
│   ├── index.html
│   ├── statistiche.html
│   ├── data.json
│   ├── covers/
│   ├── favicon-libreria.svg / .ico / -16.png / -32.png / apple-touch-icon-libreria.png
│   └── favicon-statistiche.svg / .ico / -16.png / -32.png / apple-touch-icon-statistiche.png
├── .gitignore
├── CLAUDE.md                     # regole per l'assistente (es. aggiornare questo README)
├── CNAME
├── LICENSE
└── README.md
```

> Puoi aggiungere `styles.css` o `scripts.js` se preferisci estrarre lo stile/JS dall’HTML.

### 🔖 Favicon

Ogni pagina ha la propria favicon, per distinguerla subito tra le schede del browser:

| Pagina | Icona | File |
|---|---|---|
| `index.html` (portfolio) | monogramma "D" su cerchio scuro | `assets/favicon.*` |
| `libreria/index.html` | libro chiuso con segnalibro | `libreria/favicon-libreria.*` |
| `libreria/statistiche.html` | istogramma a barre | `libreria/favicon-statistiche.*` |
| `ripetizioni/index.html`, `triennale/index.html`, `tutorato/index.html` | stesso monogramma del portfolio | `assets/favicon.*` |

Ogni set include un `.svg` (usato dai browser moderni), un `.ico` multi-risoluzione (fallback), due `.png` (16×16 e 32×32) e un `apple-touch-icon.png` (180×180, per l'aggiunta alla home screen su iOS). Per cambiare un'icona basta rigenerare il set e sovrascrivere i file: gli `<link rel="icon">` nell'`<head>` di ciascuna pagina restano invariati.

---

## 📅 Prenota una ripetizione (`/ripetizioni`)

Pagina per prenotare le ripetizioni private, collegata dalla voce "Prenota un appuntamento!" della home.

- **Live**: <https://www.danieledemichele.it/ripetizioni/>
- Istruzioni passo passo + **calendario Calendly incorporato** (lezioni da 1 ora, conferma via email, link per spostare o cancellare).
- Stile coerente con la libreria (Tailwind CDN, palette terracotta / oceano / salvia). Dopo la prenotazione compare un riquadro di conferma (evento `calendly.event_scheduled`).
- L'altezza visibile del calendario si regola con le variabili CSS `--cal-crop` e `--cal-visible` in cima al file.

---

## 🎓 Ingegneria Civile — materie (`/triennale`)

Pagina per gli studenti con tutte le materie di **Ingegneria Civile**, collegata dalla voce "Percorso di laurea triennale/magistrale" della home. Sostituisce le vecchie pagine Notion pubbliche.

- **Live**: <https://www.danieledemichele.it/triennale/> · magistrale: <https://www.danieledemichele.it/triennale/#magistrale>
- **Schede** "Laurea Triennale" e "Magistrale · Strutture"; materie divise per anno con CFU, docenti, semestre e modalità d'esame. Filtri per anno e semestre e ricerca per materia, docente o libro.
- **Popup della materia** (clic sulla card): dati, moduli dei corsi integrati, link al materiale (cartelle MEGA) e **testi di riferimento** collegati alla libreria (copertina, autori, editore; il clic apre il libro in `/libreria/#libro=<id>`).
- **Colonna destra**: sede della facoltà con mappa e modulo **Tally** "Richiesta di supporto". Il pulsante "Chiedi" apre il modulo con la materia già indicata (parametro `?materia=`).
- **Link diretti**: `#triennale/<materia>` o `#magistrale/<materia>` aprono subito il popup (es. `#magistrale/ponti`).

### Da dove arrivano i dati

La fonte è **Notion** (database "Laurea Ingegneria" e "Laurea Magistrale", con le relazioni a "Books University"). Il flusso è automatico:

1. Il GitHub Action **"Aggiorna materie da Notion"** (`.github/workflows/sync-materie.yml`) gira ogni notte alle 02:17 UTC, oppure a mano da **Actions → Run workflow**.
2. Lancia `scripts/sync_materie.py` (solo libreria standard Python), che legge i database, i link presenti nel corpo di ogni pagina (anche nei moduli) e gli ID dei libri, e scrive `triennale/materie.json`.
3. Se qualcosa è cambiato fa commit su `main` e GitHub Pages ripubblica; altrimenti non fa nulla. La pagina mostra in fondo "Aggiornato il …".

Serve il segreto **`NOTION_TOKEN`** (Settings → Secrets and variables → Actions) e l'integrazione Notion collegata alle due pagine dei corsi (••• → Connessioni).

Regole applicate dallo script:
- nei **corsi integrati** con più cartelle e moduli senza link propri, la 1ª cartella va al 1° modulo, la 2ª al 2°, …;
- un corso integrato senza modalità d'esame prende l'**unione** di quelle dei moduli;
- le **note** dei link (es. "364 MB · 51 file") già presenti in `materie.json` vengono conservate, perché l'API di Notion non le fornisce.

**Eccezioni** — `triennale/materie-overrides.json` corregge i dati letti da Notion (chiave = titolo della pagina su Notion). Oggi contiene i due laboratori di **tipologia G** da 3 CFU (Strutture al 1° anno, Riqualificazione Strutturale al 2°) e la correzione del nome "Aeroporti". Se correggi il dato su Notion puoi eliminare la riga.

**Aggiungere materiale** (es. una materia della magistrale): inserisci il link MEGA nel corpo della pagina della materia su Notion; compare sul sito dopo la sincronizzazione notturna o subito con "Run workflow".

Gli elenchi `TRIENNALE` / `MAGISTRALE` dentro `triennale/index.html` sono solo **dati di riserva**, usati se `materie.json` non si carica.

---

## 🧑‍🏫 Tutorato — Scienza delle Costruzioni (`/tutorato`) · anteprima

Pagina per gli studenti del tutorato universitario di **Scienza delle Costruzioni** (Ingegneria Civile e Architettura, Gestionale, Ambientale). Sostituirà la pagina Notion "Tutoraggio – Principi di progettazione meccanica", ancora collegata dalla home.

- **Schede** per anno accademico; filtro per **corso di laurea** (un colore per corso), per argomento e ricerca.
- Incontri raggruppati per mese, con numero progressivo per corso, orario e durata. Scegliendo un corso compaiono il nome dell'insegnamento e gli obiettivi formativi (richiudibili).
- Il popup dell'incontro apre gli **appunti PDF in un visualizzatore interno** (da `tutorato/appunti/`), con Scarica, Nuova scheda e "Segnala questo file".
- **Chiedi o segnala**: modulo Tally `LZRvby` incorporato, precompilato con i campi nascosti `incontro` e `corso` (da creare nel modulo).
- **Link diretti**: `#gestionale` (o `#civile`, `#ambientale`) filtra per corso; `#AAAA-MM-GG` apre l'incontro di quel giorno.
- **Dati**: per ora dentro `tutorato/index.html` (A.A. 2025/26, Gestionale). Previsto: `tutorato/incontri.json` generato da Notion con un GitHub Action, che scarica anche gli allegati in `tutorato/appunti/` (i link ai file di Notion scadono dopo circa un'ora).

---

## 📚 La Mia Libreria (`/libreria`)

Sezione self-hosted, separata dal resto del portfolio, che sostituisce la vecchia pagina Notion pubblica. È una vetrina e archivio personale delle letture (libri, articoli, riviste in abbonamento, testi universitari), con una pagina di statistiche dedicata.

- **Live**: <https://www.danieledemichele.it/libreria/> · statistiche: <https://www.danieledemichele.it/libreria/statistiche.html>
- **`libreria/index.html`** — vetrina + archivio, filtri (categoria, anno, autore, tipologia, ricerca, scorciatoie rapide) e viste per Articoli / Libri / Università / Archivio Completo. Pagina singola, self-contained (Tailwind CDN + JS vanilla), nessuna build.
- **Link diretti**: `/libreria/#libro=<id Notion>` apre la scheda di un singolo libro (usato dai "Testi di riferimento" di `/triennale/`), `/libreria/#universita` apre la vista Università.
- **`libreria/statistiche.html`** — report con grafici Chart.js (andamento nel tempo, distribuzione per tipo, categorie e autori più letti, riviste in abbonamento, stato dei libri).
- **`libreria/data.json`** — i dati mostrati dalle due pagine sopra. **Non si modifica a mano**: viene rigenerato dallo script `export_libreria.py` (vedi sotto) e va semplicemente committato quando cambia.
- **`libreria/covers/`** — copertine dei singoli elementi, scaricate in locale durante l'export: è la via di fuga se il link "fresco" (vedi sotto) non risponde.
- **`libreria/export_cache.json`** — stato incrementale dell'export (vedi sotto): da committare insieme a `data.json`.

### Da dove arrivano i dati

`export_libreria.py` (script esterno, **non versionato in questo repo**) legge tre database Notion — Books List, Books University, Articles List — e genera `libreria/data.json`. Per aggiornare la libreria online:

1. Posizionati dentro `libreria/` (o passa un `--output` che punti lì) e lancia lo script con il tuo `NOTION_TOKEN` (e, se configurato, `--worker-base-url` per il proxy cover — vedi sotto): `cd libreria/ && python3 export_libreria.py --output data.json`. In un solo comando genera `data.json`, scarica le cover nuove/mancanti in `covers/` e aggiorna `export_cache.json` — nessun passaggio separato.
2. Commit + push su `main` di `data.json`, `covers/` ed `export_cache.json`: GitHub Pages ripubblica automaticamente.

**Log dell'aggiornamento**: ogni esecuzione dello script scrive due file nella cartella `logs/` accanto al `data.json` generato (percorso configurabile con `--log-dir`, di norma **fuori da questo repo**, dove lo script viene lanciato):
- `export.log` — attività della run (pagine trovate per database, cover scaricate, esito finale).
- `export_errors.log` — solo warning/errori (retry Notion, cover non scaricate, singole pagine Notion malformate saltate, eccezioni impreviste con traceback completo). Comodo per capire subito cosa è andato storto senza scorrere il log generale, ed evitare di ripetere lo stesso errore al giro successivo.

### Cache incrementale (`export_cache.json`)

Man mano che la libreria cresce, rileggere da capo il corpo di ogni singola pagina Notion (blocchi, autori collegati) ad ogni esecuzione diventerebbe sempre più lento. Lo script tiene quindi una cache accanto a `data.json` — **`export_cache.json`** — che associa ad ogni pagina la sua ultima modifica su Notion (`last_edited_time`, tracciato automaticamente da Notion stesso, senza bisogno di compilare a mano una data) e il relativo elemento già pronto.

Ad ogni run: le pagine con `last_edited_time` invariato vengono riusate così come sono (niente richiami API per i blocchi o per gli autori); solo le pagine nuove o modificate da davvero vengono rielaborate; le pagine cancellate da Notion spariscono da sole sia da `data.json` sia dalla cache. Il file va **committato insieme a `data.json`**, altrimenti la prossima esecuzione (es. da un'altra macchina) riparte da zero una volta sola — non è un errore, solo una run più lenta del solito.

- `--no-cache` — ignora la cache e rielabora tutte le pagine da zero (es. per un controllo completo).
- `--force-covers` — ririscarica anche le cover già presenti in locale; disattiva automaticamente anche la cache per quella run.
- `--cache-file` — percorso della cache, se non va bene il default (`export_cache.json` accanto al file di output).

### Copertine sempre aggiornate

Gli URL dei file caricati su Notion scadono circa un'ora dopo essere stati restituiti dall'API, quindi un `data.json` statico che li contenga direttamente smetterebbe presto di mostrare le immagini. Ogni elemento ha perciò due campi immagine, con doppia via di fuga:
1. **`image`** — se è configurato un Cloudflare Worker (`libreria-covers-worker/`, anch'esso esterno a questo repo), è la sua rotta `/cover/<page_id>`, che ad ogni richiesta va a riprendere un link fresco da Notion.
2. **`imageFallback`** — la copia locale in `libreria/covers/`, usata dalla pagina se il worker (o Notion) non rispondono.
3. Se anche questa manca, la pagina mostra un'icona segnaposto generica in base al tipo di contenuto.

---

## ▶️ Avvio locale

Non serve alcun build tool.  
Apri semplicemente il file `index.html` nel browser:

- doppio click su `index.html`, **oppure**
- avvia un piccolo server statico (consigliato per test CSP):
  ```bash
  # Python 3
  python -m http.server 8000
  # poi visita http://localhost:8000
  ```

---

## 🚀 Pubblicazione su GitHub Pages

1. Crea un repository e carica i file (`index.html`, `assets/...`).
2. Vai su **Settings → Pages**.
3. **Source**: seleziona `Deploy from a branch`.
4. **Branch**: scegli `main` e la cartella `/root`.
5. Salva. L’URL sarà:  
   `https://<username>.github.io/<nome-repo>/`

### Dominio personalizzato (opzionale)
- Aggiungi un file `CNAME` nella root con il tuo dominio:
  ```
  danieledemichele.it
  ```
- In DNS crea un record **CNAME** verso `<username>.github.io`.  
- Su **Settings → Pages → Custom domain** inserisci lo stesso dominio e abilita **Enforce HTTPS**.

---

## 🔧 Personalizzazione rapida

Apri `index.html` e modifica:

### Dati personali
- **Titolo/SEO**: `<title>`, `<meta name="description">`, `<meta name="keywords">`.
- **Open Graph**: `og:title`, `og:description`, `og:image`, `og:url`, `og:site_name`.

### Avatar & Cover
- Sostituisci i file in `assets/` e assicurati del peso ottimizzato (usa **WebP/JPEG** compressi).

### Social nel dropdown
Cerca il blocco `<!-- Dropdown Social -->` e aggiorna gli `href`:
```html
<a class="dropdown-item" href="https://github.com/username" target="_blank" rel="noopener">...</a>
```

### Progetti
Modifica la lista `<dl>` nella card destra:
```html
<dt> <i class="bi ..."></i> <a href="#progetto-notion"> Titolo progetto </a></dt>
<dd class="small muted"> Breve descrizione… </dd>
```
Le sezioni con gli `id` (`#progetto-notion`, ecc.) sono già predisposte più in basso.

### Testo footer
Cerca:
```html
Designed by Daniele De Michele © <span id="year"></span>
```
e personalizza se serve.

### Colori & spacing (Design System)
In cima al `<style>`:
```css
:root{
  --card-bg:#ffffff;
  --card-r:24px;
  --shadow-soft: 0 10px 30px rgba(0,0,0,.08);
  --border-soft: 1px solid rgba(0,0,0,.06);
  --text-soft:#4b5563;
  --content-pad:1.5rem;
}
```
Modifica qui per cambiare velocemente look & feel.

---

## ♿ Accessibilità (checklist)

- [x] `lang="it"` e testo **non** tutto in maiuscolo.
- [x] **Skip link** prima del `<main>`.
- [x] `alt` significativo sull’**avatar** (es: “Ritratto di Daniele”).
- [x] Icone decorative con `aria-hidden="true"`.
- [x] Struttura **semantica**: header in card profilo, `<dl>` per progetti.
- [x] Focus visibile e navigazione **tastiera** per il dropdown.

> Suggerimento: esegui Lighthouse o WAVE per verificare contrasto e ruoli ARIA.

---

## 🔐 Sicurezza

**CSP** impostata nel `<head>`:
```html
<meta http-equiv="Content-Security-Policy"
  content="default-src 'self';
           img-src 'self' data:;
           style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline';
           script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline';
           font-src https://cdn.jsdelivr.net 'self';
           connect-src 'self';
           frame-ancestors 'self';">
```
Se sposti CSS/JS in file esterni nel repo, puoi rimuovere `'unsafe-inline'` (da `style-src` e `script-src`) e rendere la policy più rigida.
La CSP vale solo per la home: `libreria/`, `ripetizioni/`, `triennale/` e `tutorato/` caricano anche Tailwind, Google Fonts, Calendly, Tally e Google Maps.

---

## 📈 SEO & Performance (consigli)

- Usa immagini **WebP** e dimensioni adatte; aggiungi `loading="lazy"`.
- Facoltativo: `srcset`/`sizes` per cover e avatar.
- Aggiungi `sitemap.xml` e `robots.txt` (per Pages possono essere file statici).
- Precarica Bootstrap (`<link rel="preload" as="style">`) se serve ottimizzare il LCP.

---

## 🧪 Verifiche

- **Validazione HTML**: <https://validator.w3.org/>
- **Lighthouse** (Chrome DevTools): mira a 90+ su Performance/A11y/Best Practices/SEO.

---

## 🗺 Roadmap (idee)

- [ ] **Dark mode** (`prefers-color-scheme` + toggle).
- [ ] Progetti da `projects.json` + template dinamici.
- [ ] Sezione **Blog/Note** (Jekyll su Pages).
- [ ] **Analytics** privacy-first (Plausible/Umami) senza cookie banner.
- [x] GitHub **Actions**: sincronizzazione notturna delle materie da Notion.
- [ ] GitHub **Actions**: sincronizzazione del tutorato da Notion (`tutorato/incontri.json` + appunti PDF).
- [ ] GitHub **Actions**: link-checker + report Lighthouse ad ogni push.
- [ ] Automatizzare anche l'export di `libreria/data.json` con un Action (oggi lo script è esterno e il file si carica a mano).

---

## 🤝 Licenza

Se non specifichi altro, suggerisco **MIT**.  
Crea un file `LICENSE` con:

```
MIT License

Copyright (c) 2025 Daniele De Michele

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
...
```
(incolla il testo MIT completo)
---

## 🙌 Credits

- **Bootstrap 5.3** e **Bootstrap Icons** via CDN.  
- Design e sviluppo: **Daniele De Michele**.  
- Assistenza tecnica e A11y review: ChatGPT.

---

## 📬 Contatti

- LinkedIn: https://www.linkedin.com/in/danieledemichele  
- GitHub: https://github.com/danieledemichele  
- Email: daniele@danieledemichele.it

---
