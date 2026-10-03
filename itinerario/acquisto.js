/* Acquisto degli itinerari in PDF — usato dalla home di /itinerario, dalle pagine città e dalla pagina «grazie».
 *
 * Come funziona:
 *  - se ACQUISTO.api (Worker) e ACQUISTO.pk (chiave pubblicabile Stripe) sono impostati,
 *    «Acquista» apre un popup del sito con dentro il pagamento di Stripe (checkout incorporato);
 *  - altrimenti apre il link di pagamento di Stripe (ACQUISTO.link) in una nuova scheda;
 *  - in entrambi i casi, a pagamento finito, Stripe rimanda a /itinerario/grazie/ e il Worker
 *    consegna il PDF solo se la sessione risulta pagata.
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
  `;

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

  async function open(info){
    ensureModal();
    const body = modal.querySelector('#acq-body');
    body.innerHTML = `
      <div class="acq-head">${info.cover ? `<img src="${esc(info.cover)}" alt="">` : ''}
        <div><div class="eyebrow">Itinerario in PDF${A.prezzo[info.slug] ? ` · ${esc(A.prezzo[info.slug])}` : ''}</div>
        <h3 id="acq-title">${esc(info.title || info.slug)}</h3>
        <p>Lo scarichi subito dopo il pagamento.</p></div></div>
      <div class="acq-pay" id="acq-pay"><div class="acq-wait">Carico il pagamento sicuro…</div></div>
      <div class="acq-foot">Pagamento gestito da Stripe: i dati della carta non passano dal sito.</div>`;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    modal.querySelector('.acq-x').focus();
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

  /* API usata dalle pagine */
  window.Acquisto = {
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
