/* Acquisto degli itinerari — usato dalla home di /itinerario, dalle pagine città e dalla pagina «grazie».
 *
 * Cosa si compra: la pagina completa della città (sul sito pubblico c'è solo l'anteprima
 * del primo giorno) e il volume in PDF con la storia di ogni luogo.
 *
 * Come funziona:
 *  - se ACQUISTO.api (Worker) e ACQUISTO.pk (chiave pubblicabile Stripe) sono impostati,
 *    «Acquista» apre un popup del sito con dentro il pagamento di Stripe (checkout incorporato);
 *  - altrimenti apre il link di pagamento di Stripe (ACQUISTO.link) in una nuova scheda;
 *  - in entrambi i casi, a pagamento finito, Stripe rimanda a /itinerario/grazie/ e il Worker
 *    consegna il PDF solo se la sessione risulta pagata;
 *  - la pagina «grazie» ricorda il codice d'acquisto in questo browser (localStorage): la pagina
 *    della città lo usa per chiedere al Worker l'itinerario completo e sbloccarsi.
 *
 * Per passare dalla prova alla vendita vera basta cambiare i valori qui sotto.
 */
window.ACQUISTO = {
  api: '',          // URL del Worker, es. 'https://itinerario-acquisto.<tuo-account>.workers.dev'
  pk: '',           // chiave pubblicabile Stripe: pk_test_… in prova, pk_live_… dal vivo
  link: {           // link di pagamento Stripe per itinerario (usato finché api e pk sono vuoti)
    Londra: 'https://buy.stripe.com/test_dRmeVe1KMfEV2ec6q52cg00',
  },
  prezzo: {         // prezzo mostrato sul sito (quello vero lo decide Stripe)
    Londra: '9 €',
  },
};

(function(){
  const A = window.ACQUISTO;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const incorporato = () => Boolean(A.api && A.pk);

  /* stili del popup: usano i colori della pagina che lo ospita */
  const CSS = `
  .acq-modal{position:fixed;inset:0;z-index:5000;background:var(--overlay,rgba(28,25,23,.55));backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);display:flex;align-items:flex-start;justify-content:center;overflow-y:auto;padding:max(24px,env(safe-area-inset-top,0px)) 16px 24px}
  .acq-sheet{position:relative;background:var(--paper,#fff);color:var(--ink,#1c1917);border:1px solid var(--line2,#d6d3d1);border-radius:24px;width:100%;max-width:560px;padding:22px;box-shadow:0 30px 80px rgba(28,25,23,.25);display:flex;flex-direction:column;gap:16px}
  .acq-head{display:flex;gap:14px;align-items:center;padding-right:40px}
  .acq-head img{width:64px;height:64px;border-radius:14px;object-fit:cover;flex-shrink:0;border:1px solid var(--line2,#d6d3d1)}
  .acq-head h3{font-family:var(--serif,Georgia,serif);font-size:20px;margin:2px 0 0}
  .acq-head p{margin:2px 0 0;font-size:12.5px;color:var(--sub,#78716c)}
  .acq-x{position:absolute;top:14px;right:14px;width:36px;height:36px;border-radius:50%;border:1px solid var(--line2,#d6d3d1);background:var(--paper,#fff);color:var(--ink,#1c1917);font-size:20px;line-height:1;cursor:pointer}
  .acq-x:focus-visible{outline:2px solid var(--accent,#9a3412);outline-offset:2px}
  .acq-pay{min-height:420px;border-radius:16px;overflow:hidden;background:#fff}
  .acq-wait{display:grid;place-items:center;min-height:420px;color:var(--sub,#78716c);font-size:13.5px;text-align:center;padding:20px}
  .acq-foot{font-size:11.5px;color:var(--sub,#78716c);display:flex;gap:6px;align-items:center}
  .acq-sheet .eyebrow{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--accent,#9a3412)}
  #acq-body{display:flex;flex-direction:column;gap:16px}
  .acq-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
  .acq-list li{display:grid;grid-template-columns:22px 1fr;gap:10px;font-size:14px;line-height:1.45;color:var(--ink2,#44403c)}
  .acq-list li b{color:var(--ink,#1c1917);font-weight:600}
  .acq-list svg{margin-top:1px;color:var(--accent,#9a3412)}
  .acq-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
  .acq-btn{font:inherit;font-size:14px;font-weight:600;padding:12px 18px;border-radius:12px;border:1px solid transparent;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;gap:8px}
  .acq-btn.go{background:var(--accent,#9a3412);color:#fff;flex:1 1 220px}
  .acq-btn.go:hover{background:var(--accent-h,#802a0e)}
  .acq-btn.later{background:transparent;color:var(--ink2,#44403c);border-color:var(--line2,#d6d3d1)}
  .acq-btn:focus-visible{outline:2px solid var(--accent,#9a3412);outline-offset:2px}
  .acq-note{margin:0;font-size:12px;color:var(--sub,#78716c)}
  `;
  const CHECK = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';

  let modal, current;
  function ensureModal(){
    if(modal) return modal;
    const st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st);
    modal = document.createElement('div');
    modal.className = 'acq-modal'; modal.hidden = true;
    modal.setAttribute('role', 'dialog'); modal.setAttribute('aria-modal', 'true'); modal.setAttribute('aria-labelledby', 'acq-title');
    modal.innerHTML = '<div class="acq-sheet"><button type="button" class="acq-x" aria-label="Chiudi">×</button><div id="acq-body"></div></div>';
    document.body.appendChild(modal);
    modal.querySelector('.acq-x').addEventListener('click', close);
    modal.addEventListener('click', e => { if(e.target === modal) close(); });
    document.addEventListener('keydown', e => { if(e.key === 'Escape' && !modal.hidden) close(); });
    return modal;
  }

  function loadStripe(){
    if(window.Stripe) return Promise.resolve(window.Stripe);
    return new Promise((ok, ko) => {
      const s = document.createElement('script');
      s.src = 'https://js.stripe.com/v3/';
      s.onload = () => ok(window.Stripe); s.onerror = () => ko(new Error('Stripe.js non caricato'));
      document.head.appendChild(s);
    });
  }

  function head(info, sub){
    return `<div class="acq-head">${info.cover ? `<img src="${esc(info.cover)}" alt="">` : ''}
        <div><div class="eyebrow">Itinerario completo${A.prezzo[info.slug] ? ` · ${esc(A.prezzo[info.slug])}` : ''}</div>
        <h3 id="acq-title">${esc(info.title || info.slug)}</h3>
        <p>${esc(sub)}</p></div></div>`;
  }
  function show(){
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    modal.querySelector('.acq-x').focus();
  }

  /* Popup del paywall: cosa si sblocca, prezzo e pulsante per pagare */
  function paywall(info){
    ensureModal();
    const body = modal.querySelector('#acq-body');
    const g = info.giorni ? `${info.giorni} giornate` : 'Tutte le giornate';
    const link = A.link[info.slug];
    body.innerHTML = head(info, info.sub || 'Hai visto l\'anteprima del primo giorno.') + `
      <ul class="acq-list">
        <li>${CHECK}<span><b>${esc(g)}${info.tappe ? `, ${info.tappe} tappe` : ''}</b> con orari, note, mappa e foto, su questa pagina.</span></li>
        <li>${CHECK}<span><b>Il volume in PDF</b> da portare in viaggio: la storia di ogni luogo, cosa cercare sul posto e le mappe dei giorni.</span></li>
        <li>${CHECK}<span><b>Subito dopo il pagamento</b>, senza account: la pagina si sblocca su questo dispositivo.</span></li>
      </ul>
      <div class="acq-actions">
        ${incorporato() || !link ? `<button type="button" class="acq-btn go" id="acq-go">Sblocca l'itinerario${A.prezzo[info.slug] ? ` · ${esc(A.prezzo[info.slug])}` : ''}</button>`
          : `<a class="acq-btn go" id="acq-go" href="${esc(link)}" target="_blank" rel="noopener">Sblocca l'itinerario${A.prezzo[info.slug] ? ` · ${esc(A.prezzo[info.slug])}` : ''} →</a>`}
        <button type="button" class="acq-btn later" id="acq-later">Continua con l'anteprima</button>
      </div>
      <p class="acq-note">Pagamento sicuro gestito da Stripe. Hai già acquistato? Riapri il link della pagina di conferma su questo dispositivo.</p>`;
    show();
    body.querySelector('#acq-later').addEventListener('click', close);
    const go = body.querySelector('#acq-go');
    if(go.tagName === 'BUTTON') go.addEventListener('click', () => open(info));
  }

  async function open(info){
    ensureModal();
    const body = modal.querySelector('#acq-body');
    body.innerHTML = head(info, 'Pagina completa e volume in PDF, subito dopo il pagamento.') + `
      <div class="acq-pay" id="acq-pay"><div class="acq-wait">Carico il pagamento sicuro…</div></div>
      <div class="acq-foot">Pagamento gestito da Stripe: i dati della carta non passano dal sito.</div>`;
    show();
    try{
      const Stripe = await loadStripe();
      const stripe = Stripe(A.pk);
      const fetchClientSecret = async () => {
        const r = await fetch(`${A.api}/checkout`, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({itinerario: info.slug})});
        const j = await r.json();
        if(!r.ok || !j.clientSecret) throw new Error(j.error || 'Pagamento non disponibile');
        return j.clientSecret;
      };
      const pay = document.getElementById('acq-pay');
      pay.innerHTML = '';
      current = await stripe.initEmbeddedCheckout({fetchClientSecret});
      if(modal.hidden){ current.destroy(); current = null; return; }
      current.mount(pay);
    }catch(e){
      console.error(e);
      const link = A.link[info.slug];
      document.getElementById('acq-pay').innerHTML = `<div class="acq-wait"><p style="margin:0 0 12px">Il pagamento qui non si è caricato.</p>${link ? `<a class="btn btn-primary" href="${esc(link)}" target="_blank" rel="noopener">Paga sulla pagina di Stripe →</a>` : 'Riprova tra poco.'}</div>`;
    }
  }

  function close(){
    if(!modal || modal.hidden) return;
    if(current){ try{ current.destroy(); }catch(e){} current = null; }
    modal.hidden = true;
    document.body.style.overflow = '';
  }

  /* codice d'acquisto ricordato in questo browser */
  const KEY = slug => `acquisto:${slug}`;
  const leggi = slug => { try{ return localStorage.getItem(KEY(slug)) || ''; }catch(e){ return ''; } };

  /* API usata dalle pagine */
  window.Acquisto = {
    paywall,
    /** salva il codice della sessione pagata (lo chiama la pagina «grazie») */
    ricorda(slug, sid){ try{ localStorage.setItem(KEY(slug), sid); }catch(e){} },
    /** link per scaricare di nuovo il volume, se in questo browser c'è un acquisto */
    download: slug => (A.api && leggi(slug)) ? `${A.api}/download?session_id=${encodeURIComponent(leggi(slug))}` : '',
    /** itinerario completo dal Worker se in questo browser c'è un acquisto valido, altrimenti null */
    async sblocca(slug){
      const sid = leggi(slug);
      if(!sid || !A.api) return null;
      try{
        const r = await fetch(`${A.api}/itinerario?session_id=${encodeURIComponent(sid)}`);
        if(r.status === 400 || r.status === 402){ try{ localStorage.removeItem(KEY(slug)); }catch(e){} return null; }
        return r.ok ? await r.json() : null;
      }catch(e){ return null; }
    },
    /** true se per questo itinerario c'è un modo di pagare */
    disponibile: slug => incorporato() || Boolean(A.link[slug]),
    prezzo: slug => A.prezzo[slug] || '',
    /** collega i pulsanti con data-acquista="<slug>" (titolo e copertina da data-title e data-cover) */
    collega(root = document){
      root.querySelectorAll('[data-acquista]').forEach(el => {
        if(el.dataset.acqBound) return; el.dataset.acqBound = '1';
        const info = {slug: el.dataset.acquista, title: el.dataset.title, cover: el.dataset.cover};
        if(!incorporato()){
          const link = A.link[info.slug];
          if(link && el.tagName === 'A'){ el.href = link; el.target = '_blank'; el.rel = 'noopener'; }
          return;
        }
        el.addEventListener('click', e => { e.preventDefault(); open(info); });
      });
    },
  };
})();
