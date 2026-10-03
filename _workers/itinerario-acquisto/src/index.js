/**
 * Worker "itinerario-acquisto": vendita dei PDF degli itinerari con Stripe.
 *
 *   POST /checkout   {"itinerario":"Londra"} → {clientSecret}
 *                    crea una sessione di Checkout incorporata nel sito (popup)
 *   GET  /session?session_id=cs_…            → stato del pagamento per la pagina «grazie»
 *   GET  /download?session_id=cs_…           → il PDF, solo se la sessione risulta pagata
 *
 * Il PDF non è mai pubblico: sta nel bucket R2 (binding ITINERARI) e il Worker
 * lo consegna solo dopo aver chiesto a Stripe se quella sessione è stata pagata.
 * Funziona sia con il checkout incorporato sia con il link di pagamento, perché
 * entrambi rimandano a /itinerario/grazie/?session_id={CHECKOUT_SESSION_ID}.
 *
 * Variabili (wrangler.toml): SITE_URL, ALLOWED_ORIGINS, PRODOTTI (JSON)
 * Segreto:                   STRIPE_SECRET_KEY  (wrangler secret put STRIPE_SECRET_KEY)
 */

const SESSION_RE = /^cs_(test|live)_[A-Za-z0-9]{10,200}$/;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(request, env);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    try {
      if (url.pathname === '/checkout' && request.method === 'POST') return await checkout(request, env, cors);
      if (url.pathname === '/session' && request.method === 'GET') return await session(url, env, cors);
      if (url.pathname === '/download' && request.method === 'GET') return await download(url, env);
      if (url.pathname === '/') return json({ ok: true, servizio: 'itinerario-acquisto' }, 200, cors);
      return json({ error: 'Pagina non trovata.' }, 404, cors);
    } catch (e) {
      console.error(e);
      return json({ error: 'Qualcosa non ha funzionato. Riprova tra poco.' }, 500, cors);
    }
  },
};

/* ---------- endpoint ---------- */

async function checkout(request, env, cors) {
  const body = await request.json().catch(() => ({}));
  const slug = String(body.itinerario || '');
  const p = prodotti(env)[slug];
  if (!p) return json({ error: 'Itinerario non in vendita.' }, 400, cors);

  const params = {
    mode: 'payment',
    ui_mode: 'embedded_page',
    line_items: [{ price: p.price, quantity: 1 }],
    return_url: `${env.SITE_URL}/itinerario/grazie/?session_id={CHECKOUT_SESSION_ID}`,
    metadata: { itinerario: slug },
    payment_intent_data: { description: p.nome, metadata: { itinerario: slug } },
    allow_promotion_codes: true,
    locale: 'it',
    // stessi colori del sito; se l'account non li accetta vengono tolti (vedi stripe())
    branding_settings: { button_color: '#9a3412', background_color: '#ffffff', border_style: 'rounded', font_family: 'inter' },
  };
  const s = await stripe(env, 'POST', '/v1/checkout/sessions', params, { fallbackUiMode: 'embedded' });
  if (s.error) return json({ error: 'Non riesco ad avviare il pagamento. Riprova tra poco.' }, 502, cors);
  return json({ clientSecret: s.client_secret }, 200, cors);
}

async function session(url, env, cors) {
  const r = await verify(url.searchParams.get('session_id'), env);
  if (r.error) return json({ error: r.error }, r.status, cors);
  const { s, slug, p } = r;
  return json({
    stato: s.status,                          // open | complete | expired
    pagato: s.payment_status === 'paid',
    email: s.customer_details?.email || null,
    itinerario: slug,
    nome: p?.nome || null,
    totale: s.amount_total,
    valuta: s.currency,
    download: s.payment_status === 'paid' && p
      ? `${new URL(url).origin}/download?session_id=${encodeURIComponent(s.id)}` : null,
  }, 200, cors);
}

async function download(url, env) {
  const r = await verify(url.searchParams.get('session_id'), env);
  if (r.error) return new Response(r.error, { status: r.status, headers: { 'content-type': 'text/plain; charset=utf-8' } });
  const { s, p } = r;
  if (s.payment_status !== 'paid' || !p) {
    return new Response('Il pagamento non risulta completato.', { status: 402, headers: { 'content-type': 'text/plain; charset=utf-8' } });
  }
  const obj = await env.ITINERARI.get(p.file);
  if (!obj) return new Response('File non disponibile, scrivimi e te lo mando.', { status: 404, headers: { 'content-type': 'text/plain; charset=utf-8' } });
  console.log(`download ${p.file} · ${s.id}`);
  return new Response(obj.body, {
    headers: {
      'content-type': 'application/pdf',
      'content-disposition': `attachment; filename="${p.download || p.file}"`,
      'cache-control': 'private, no-store',
    },
  });
}

/* ---------- aiuti ---------- */

/** Controlla l'id, legge la sessione da Stripe e capisce quale itinerario è stato comprato. */
async function verify(id, env) {
  if (!id || !SESSION_RE.test(id)) return { error: 'Codice di acquisto non valido.', status: 400 };
  const s = await stripe(env, 'GET', `/v1/checkout/sessions/${id}?expand[]=line_items`);
  if (s.error) return { error: 'Acquisto non trovato.', status: 404 };
  const all = prodotti(env);
  // 1) metadati messi dal checkout incorporato; 2) prezzo, per i link di pagamento
  let slug = s.metadata?.itinerario;
  if (!all[slug]) {
    const prices = (s.line_items?.data || []).map(li => li.price?.id);
    slug = Object.keys(all).find(k => prices.includes(all[k].price));
  }
  return { s, slug: slug || null, p: all[slug] || null };
}

function prodotti(env) {
  try { return JSON.parse(env.PRODOTTI || '{}'); } catch { return {}; }
}

/**
 * Chiamata all'API di Stripe. Se Stripe rifiuta un parametro che l'account non
 * conosce ancora (versione dell'API più vecchia), lo toglie e riprova.
 */
async function stripe(env, method, path, params, opts = {}) {
  let p = params ? structuredClone(params) : null;
  for (let tentativo = 0; tentativo < 4; tentativo++) {
    const res = await fetch(`https://api.stripe.com${path}`, {
      method,
      headers: {
        authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
        ...(p ? { 'content-type': 'application/x-www-form-urlencoded' } : {}),
      },
      body: p ? form(p) : undefined,
    });
    const data = await res.json();
    if (res.ok) return data;
    const err = data.error || {};
    console.warn('Stripe', res.status, err.code, err.param, err.message);
    if (!p || res.status !== 400 || !err.param) return { error: err };
    const top = err.param.split('[')[0];
    if (top === 'ui_mode' && opts.fallbackUiMode && p.ui_mode !== opts.fallbackUiMode) { p.ui_mode = opts.fallbackUiMode; continue; }
    if (['branding_settings', 'payment_intent_data', 'allow_promotion_codes', 'locale'].includes(top) && top in p) { delete p[top]; continue; }
    return { error: err };
  }
  return { error: { message: 'troppi tentativi' } };
}

/** Oggetto → application/x-www-form-urlencoded con la notazione a[b][0][c] di Stripe. */
function form(obj, prefix = '', out = new URLSearchParams()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}[${k}]` : k;
    if (v === undefined || v === null) continue;
    if (typeof v === 'object') form(v, key, out);
    else out.append(key, String(v));
  }
  return out;
}

function corsHeaders(request, env) {
  const origin = request.headers.get('origin') || '';
  const allowed = String(env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
  const ok = allowed.includes(origin) || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
  return ok ? {
    'access-control-allow-origin': origin,
    'access-control-allow-methods': 'GET, POST, OPTIONS',
    'access-control-allow-headers': 'content-type',
    'vary': 'origin',
  } : { 'vary': 'origin' };
}

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...headers } });
}
