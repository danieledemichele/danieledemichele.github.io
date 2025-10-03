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
│   └── screenshot.jpg            # opzionale
└── README.md
```

> Puoi aggiungere `styles.css` o `scripts.js` se preferisci estrarre lo stile/JS dall’HTML.

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
           script-src 'self' https://cdn.jsdelivr.net;
           font-src https://cdn.jsdelivr.net 'self';
           connect-src 'self';
           frame-ancestors 'self';">
```
Se sposti CSS/JS in file esterni nel repo, puoi rimuovere `'unsafe-inline'` e rendere la policy più rigida.

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
- [ ] GitHub **Actions**: link-checker + report Lighthouse ad ogni push.

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

- LinkedIn: https://www.linkedin.com/in/username  
- GitHub: https://github.com/username  
- Email: daniele@danieledemichele.it

---
