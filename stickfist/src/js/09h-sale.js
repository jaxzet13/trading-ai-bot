/* ============================================================================
   8h. THE SALE. The only thing in STIXX that costs real money is the physical Requiem pack, and only while the server (pay.js) says the sale is open.
   Everything else is play money. The page never handles a card: "Pay" sends the buyer to Stripe's own page (Apple Pay, Google Pay and cards are offered there),
   and Stripe sends them back here. Without a server (a file, a preview) there is no sale: this stays closed and the page shows the preview.
   ========================================================================== */
const Sale = (() => {
  let cfg = { open: false, soldOut: false, loaded: false }, polls = 0, timer = 0;
  const ret = (() => {                                                     // ?rq=paid&sid=… or ?rq=cancel, on the way back from Stripe; read once, then the address bar is tidied
    try {
      const p = new URLSearchParams(location.search), k = p.get("rq"); if (!k) return null;
      const sid = (p.get("sid") || "").replace(/[^\w]/g, "").slice(0, 120); p.delete("rq"); p.delete("sid");
      history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : "") + location.hash); return { kind: k === "paid" ? "paid" : "cancel", sid, order: null };
    } catch (e) { return null; }
  })();
  const open = () => !!cfg.open;
  async function load() {
    if (!API.on) return cfg; const r = await API.get("requiem/config"); if (!r || typeof r.open !== "boolean") return cfg;
    cfg = Object.assign({ loaded: true }, r); if (r.run) RQ.run = r.run; if (r.closes) RQ.closes = r.closes;
    Money.words(); if (view === "limited") renderLimited(); else if (view === "home") renderHome(); return cfg;
  }
  const total = () => { const q = $("rqQty"); return rmoney((cfg.price || RQ.price) * (q ? +q.value || 1 : 1)); };
  function qty() { const b = $("rqPay"); if (b && !b.dataset.busy) b.textContent = "Pay " + total(); }
  async function pay() {
    const age = $("rqAge") && $("rqAge").checked, b = $("rqPay"); if (!age || !b || b.dataset.busy) return;
    b.dataset.busy = 1; b.disabled = true; b.textContent = "Opening Stripe…";
    const r = await API.post("requiem/checkout", { qty: +($("rqQty") ? $("rqQty").value : 1) || 1, age: true });
    if (r && typeof r.url === "string" && /^https:\/\//.test(r.url)) { location.href = r.url; return; }
    delete b.dataset.busy; b.disabled = !($("rqAge") && $("rqAge").checked); qty(); toast((r && r.error) || "Couldn't reach the server. You have not been charged.");
  }
  // after paying: ask the server which packs are the buyer's, until the payment has been confirmed
  function poll() {
    if (!ret || ret.kind !== "paid" || !ret.sid || ret.order || timer) return;
    const tick = async () => {
      timer = 0; const r = await API.get("requiem/order?sid=" + encodeURIComponent(ret.sid)); polls++;
      if (r && r.ok) { ret.order = r; if (view === "limited") renderLimited(); return; }
      if (polls < 20) timer = setTimeout(tick, 2000); else if ($("rqPaidTxt")) $("rqPaidTxt").textContent = "Your payment is still being confirmed. Keep this page's link and check back in a few minutes.";
    };
    tick();
  }
  function banner() {
    if (!ret) return "";
    if (ret.kind === "cancel") return `<div class="rqnote" role="status"><b>No payment was taken.</b> You can try again whenever you like.</div>`;
    const o = ret.order, ps = o && o.packs ? o.packs.map(fmt) : [], nos = ps.length < 2 ? ps.join("") : ps.slice(0, -1).join(", ") + " and " + ps[ps.length - 1];
    const text = !o ? "Checking your order…" : o.short ? "Your payment went through, but the run sold out first. You will be refunded." : `Your payment went through. Your pack${o.packs.length > 1 ? "s are" : " is"} number ${nos} of ${fmt(o.run || 0)}. We ship to the address you gave Stripe.`;
    return `<div class="rqnote ok" role="status"><b>Thank you.</b> <span id="rqPaidTxt">${esc(text)}</span></div>`;
  }
  return { load, open, pay, qty, poll, banner, cfg: () => cfg, ret: () => ret, total };
})();

/* ============================================================================
   8i. DIGITAL PACKS. What real money buys in the game: pack openings, and nothing else. The cards stay game items with no cash value, every price in the game
   stays simulated, and nothing can be cashed out. The server (pay.js) decides whether this is on, takes the payment through Stripe, and keeps a running total of
   the packs each player has bought; the page adds the difference to the player's packs, so a purchase can never be added twice.
   ========================================================================== */
// Nothing to open and nothing to open it with: no free pack, no bought pack, and not enough play money for the cheapest pack. Only while buying is on.
const isBroke = () => Shop.open() && !state.freePacks && PACKS.every(p => !boughtOf(p.id) && state.coins < packPrice(p));
function renderBroke() { document.body.classList.toggle("broke", isBroke()); }
// what the server says you have paid for, as running totals: add only the difference, so the same purchase can never be added twice. Returns what was added.
function applyPaid(paid, quiet) {
  let add = 0, dollars = 0; state.paid = state.paid || {}; state.paidSeen = state.paidSeen || {};
  for (const id of Object.keys(paid || {})) { const d = (paid[id] || 0) - (state.paidSeen[id] || 0); if (d <= 0) continue;
    if (id === "cash") { dollars += d; state.paidSeen.cash = paid.cash; state.coins += d * UNIT; state.s.added += d * UNIT; }      // play money bought with real money: counted as money handed to you, never as profit
    else if (PACK_BY[id]) { add += d; state.paidSeen[id] = paid[id]; state.paid[id] = (state.paid[id] || 0) + d; } }
  if (dollars || add) { persist(); renderBal(true); renderChips(); renderBroke(); if (view === "home") renderHome(); if (!quiet) toast(dollars ? `${money(dollars * UNIT)} added to your balance` : `${add} pack${add > 1 ? "s" : ""} ready to open`); }
  return { dollars, add };
}
const Shop = (() => {
  let cfg = { open: false, prices: {} };
  const ret = (() => {                                                     // ?pk=paid&sid=… or ?pk=cancel, on the way back from Stripe
    try {
      const p = new URLSearchParams(location.search), k = p.get("pk"); if (!k) return null;
      const sid = (p.get("sid") || "").replace(/[^\w]/g, "").slice(0, 120); p.delete("pk"); p.delete("sid");
      history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : "") + location.hash); return { kind: k === "paid" ? "paid" : "cancel", sid };
    } catch (e) { return null; }
  })();
  const cash = () => !!cfg.open && !!(cfg.prices && cfg.prices.cash), open = () => cash() || !!cfg.open && PACKS.some(p => cfg.prices && cfg.prices[p.id]), has = id => cash() || !!cfg.open && !!(cfg.prices && cfg.prices[id]), price = id => (cfg.prices && cfg.prices[id]) || 0;
  async function load() {
    if (!API.on) return; const r = await API.get("shop/config?uid=" + encodeURIComponent(state.uid)); if (!r || typeof r.open !== "boolean") return;
    cfg = r; Money.words(); const tb = $("topBuy"); if (tb) { tb.hidden = !open(); tb.innerHTML = cash() ? '+ Add<span class="xs"> money</span>' : '+ Buy<span class="xs"> packs</span>'; } renderBroke(); if (view === "home") renderHome();
  }
  const chosen = () => { const s = $("shopPack"); return s ? s.value : cash() ? "cash" : curPack().id; }, count = () => { const q = $("shopQty"); return q ? +q.value || 1 : 1; };
  const total = () => rmoney(price(chosen()) * count());
  function qty() { const b = $("shopPay"); if (b && !b.dataset.busy) b.textContent = cash() ? `Add ${total()} · open ${packsFor(count())} pack${packsFor(count()) === 1 ? "" : "s"}` : "Pay " + total(); const e = $("shopEach"); if (e) e.textContent = rmoney(price(chosen())) + " per pack"; }
  // pick an amount: update the hidden value, the chips and the button
  function setAmt(n) { const q = $("shopQty"); if (!q) return; q.value = n; document.querySelectorAll("#shopAmts .amtchip").forEach(c => { const on = +c.dataset.addamt === n; c.classList.toggle("on", on); c.setAttribute("aria-pressed", on); }); qty(); buzz(8); }
  const AMOUNTS = [1, 2, 3, 5, 10, 15, 25];
  // how many packs an amount of play money buys, at the pack in front of you — the honest, tangible reason to add more
  const packsFor = n => Math.max(1, Math.floor(n * (price("cash") || 100) / 100 * UNIT / Math.max(1, packPrice(curPack()))));
  function cashModal(w) {
    want = w || want;                                               // real money adds play money to the balance, $1.00 for each dollar: no bonuses, no bundles
    const room = Math.max(0, Math.floor(((cfg.cap || 0) - (cfg.spentToday || 0)) / (price("cash") || 100))), opts = AMOUNTS.filter(n => n <= Math.min(cfg.maxQty || 25, room));
    if (!opts.length) { openModal(`<div class="minfo"><div><span class="label">real money</span><h2>Daily limit reached</h2></div><p class="dim">You've added the most you can today (${rmoney(cfg.cap || 0)}). It resets tomorrow (UTC).</p><div class="row"><button class="btn" data-close>ok</button></div></div>`, true); return; }
    // what to pre-select: enough for the pack you came to open, or a sensible middle amount — never the biggest
    const need = want && PACK_BY[want] ? Math.max(1, Math.ceil((packPrice(PACK_BY[want]) - state.coins) / UNIT)) : 0;
    const pick = need ? (opts.find(n => n >= need) || opts[opts.length - 1]) : (opts.includes(5) ? 5 : opts[Math.min(opts.length - 1, Math.max(0, Math.ceil(opts.length / 2) - 1))]);
    openModal(`<div class="minfo buym"><div><span class="label">add play money</span><h2>Add money</h2></div>
      <p class="buyline">Open more packs. <b>$1 adds $1</b> of play money — no cash value, nothing is cashed out.</p>
      <div class="amtgrid" id="shopAmts">${opts.map(n => `<button type="button" class="amtchip${n === pick ? " on" : ""}" data-addamt="${n}" aria-pressed="${n === pick}"><b>${rmoney(n * 100)}</b><small>${packsFor(n)} pack${packsFor(n) === 1 ? "" : "s"}</small></button>`).join("")}</div>
      <input type="hidden" id="shopQty" value="${pick}">
      <button class="btn solid big" id="shopPay">Add ${rmoney(pick * 100)} · open ${packsFor(pick)} pack${packsFor(pick) === 1 ? "" : "s"}</button>
      <div class="trust"><svg class="lock" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg><span>Secure checkout by <b>Stripe</b></span><span class="pays">Apple Pay · Google Pay · Card</span></div>
      <p class="finep">18+ · Stripe's secure page, STIXX never sees your card · ${rmoney(cfg.cap || 0)}/day limit${cfg.spentToday > 0 ? ` (${rmoney(cfg.spentToday)} used)` : ""} · <a href="${esc(cfg.terms || "#")}" target="_blank" rel="noopener">Terms</a></p>
      <button class="btn ghost" data-close>not now</button></div>`, true);
  }
  function modal(w) {
    if (cash()) { cashModal(w); return; } want = w || null;
    const ids = PACKS.filter(p => has(p.id)).map(p => p.id); if (!ids.length) return; const pref = w || curPack().id, cur = ids.includes(pref) ? pref : ids[0];
    openModal(`<div class="minfo"><div><span class="label">real money</span><h2>Buy packs</h2></div>
      <p class="dim">Real money buys packs, and nothing else. Each pack holds random digital cards: you can't choose them, and the odds are on the <a href="#/odds" data-close>odds page</a>. The cards are game items with <b>no cash value</b>. Nothing in STIXX can be cashed out, and the prices you see in the game are simulated.</p>
      <div class="rqbuyh"><label class="rqqty" style="justify-items:start"><span class="small">Pack</span><select id="shopPack" aria-label="Which pack">${ids.map(id => `<option value="${id}"${id === cur ? " selected" : ""}>${esc(PACK_BY[id].name)} · ${rmoney(price(id))}</option>`).join("")}</select></label>
        <label class="rqqty"><span class="small">How many</span><select id="shopQty" aria-label="How many packs">${Array.from({ length: cfg.maxQty || 1 }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("")}</select></label></div>
      <p class="small" style="margin:-6px 0 0"><b id="shopEach">${rmoney(price(cur))} per pack</b> · one flat price: no bundles, no discounts</p>
      <button class="btn solid big" id="shopPay">Pay ${rmoney(price(cur))}</button>
      <p class="small">Apple Pay, Google Pay or card, on Stripe's secure page. STIXX never sees your card. You are only charged after you confirm there. There is a limit of ${rmoney(cfg.cap || 0)} a day${cfg.spentToday > 0 ? ` (you have used ${rmoney(cfg.spentToday)} today)` : ""}. <a href="${esc(cfg.terms || "#")}" target="_blank" rel="noopener">Terms and refunds</a>.</p>
      <div class="row"><button class="btn ghost" data-close>not now</button></div></div>`, true);
  }
  /* ---- paying: Stripe's own checkout opens inside the app (no leaving, no coming back), and the money or packs land the moment it says paid.
          Without Stripe's script (blocked, offline, no publishable key) it falls back to Stripe's page and back. ---- */
  let stripeJs = null, ec = null, want = null, pendingT = 0;
  const loadStripe = () => stripeJs || (stripeJs = new Promise(res => { if (window.Stripe) return res(window.Stripe); const sc = document.createElement("script"); sc.src = "https://js.stripe.com/v3/"; sc.async = true;
    const to = setTimeout(() => res(null), 7000); sc.onload = () => { clearTimeout(to); res(window.Stripe || null); }; sc.onerror = () => { clearTimeout(to); stripeJs = null; res(null); }; document.head.appendChild(sc); }));
  const PEND = "stixx-pending-pay", setPending = sid => { try { localStorage.setItem(PEND, JSON.stringify({ sid, t: Date.now(), want })); } catch (e) {} }, getPending = () => { try { const p = JSON.parse(localStorage.getItem(PEND) || "null"); return p && Date.now() - p.t < 36e5 ? p : null; } catch (e) { return null; } }, clearPending = () => { try { localStorage.removeItem(PEND); } catch (e) {} };
  function drop() { if (ec) { try { ec.destroy(); } catch (e) {} ec = null; } }
  async function pay() {
    const b = $("shopPay"); if (!state.ageOK || !b || b.dataset.busy) return;      // 18+ was confirmed at the age gate when the app opened; no second checkbox
    b.dataset.busy = 1; b.disabled = true; b.textContent = "Opening checkout…";
    const S = cfg.pk ? loadStripe() : Promise.resolve(null);                                              // fetch Stripe's script while the session is made
    const r = await API.post("shop/checkout", { uid: state.uid, pack: chosen(), qty: count(), age: true, embedded: !!cfg.pk });
    if (r && r.secret && r.sid) {
      const Stripe = await S; if (Stripe) { try { await mountEmbedded(Stripe, r); return; } catch (e) { console.error(e); } }
      const r2 = await API.post("shop/checkout", { uid: state.uid, pack: chosen(), qty: count(), age: true });      // the script didn't load: use Stripe's page instead
      if (r2 && r2.url) { setPending(r2.sid); location.href = r2.url; return; }
    } else if (r && typeof r.url === "string" && /^https:\/\//.test(r.url)) { setPending(r.sid); location.href = r.url; return; }
    delete b.dataset.busy; b.disabled = false; qty(); toast((r && r.error) || "Couldn't reach the server. You have not been charged.");
  }
  async function mountEmbedded(Stripe, r) {
    drop(); const st = Stripe(cfg.pk); setPending(r.sid);
    openModal(`<div class="ecwrap"><div class="echead"><span class="label">secure checkout</span><span class="small dim"><svg class="lock" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg> Stripe</span></div><div id="ecMount" class="ecmount"><p class="dim small">Loading…</p></div></div>`, false);
    $("mbox").classList.add("ec");
    ec = await st.initEmbeddedCheckout({ fetchClientSecret: async () => r.secret, onComplete: () => finish(r.sid) });
    const m = $("ecMount"); if (!m) { drop(); return; } m.innerHTML = ""; ec.mount("#ecMount");
  }
  // paid: ask the server (which asks Stripe directly), quickly and often, then credit and get out of the way
  async function finish(sid, fromReturn) {
    if (!sid) return; drop(); clearTimeout(pendingT);
    openModal(`<div class="minfo paydone"><div class="spinner" aria-hidden="true"></div><h2>Payment received</h2><p class="dim" id="shopDoneTxt">Adding it to your balance…</p></div>`, true);
    for (let i = 0; i < 40; i++) {
      const r = await API.get("shop/order?sid=" + encodeURIComponent(sid));
      if (r && r.ok) {
        clearPending();
        if (r.short) { openModal(`<div class="minfo"><h2>Thank you</h2><p class="dim">Your payment went through, but we couldn't add it to your game. You will be refunded automatically.</p><div class="row"><button class="btn solid" data-close>ok</button></div></div>`, true); return; }
        let paid = r.paid; if (!paid) { const h = await API.post("hello", { uid: state.uid, ref: state.ref.by }); paid = (h && h.paid) || {}; }      // an older server: ask for the totals
        const got = applyPaid(paid, true); if (r.pack && PACK_BY[r.pack] && state.pack !== r.pack) { state.pack = r.pack; persist(); }
        closeModal(); const wpk = (want && PACK_BY[want]) || curPack(); want = null;
        toast(got.dollars ? `${money(got.dollars * UNIT)} added` : got.add ? `${got.add} pack${got.add > 1 ? "s" : ""} added` : "Payment received");
        if (view !== "home") location.hash = "#/";
        if (got.add || state.coins >= packPrice(wpk)) { if (state.pack !== wpk.id) { state.pack = wpk.id; persist(); } setTimeout(() => openPack(), 250); }      // straight into the pack you came to open
        return;
      }
      await sleep(i < 15 ? 350 : 1500);
    }
    const t = $("shopDoneTxt"); if (t) t.textContent = "Stripe is still confirming your payment. It will be added within a few minutes, even if you close the app.";
  }
  // a payment started before the app was closed or sent to Stripe's page: when you come back to the app, finish it
  function resume() { const p = getPending(); if (!p || !p.sid || ec) return; if (p.want) want = p.want; pendingT = setTimeout(() => API.get("shop/order?sid=" + encodeURIComponent(p.sid)).then(r => { if (r && r.ok) finish(p.sid, true); }), 150); }
  addEventListener("pageshow", e => { if (e.persisted) { const b = $("shopPay"); if (b) { delete b.dataset.busy; b.disabled = false; qty(); } } resume(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) resume(); });
  const done = (title, text, button) => openModal(`<div class="minfo"><div><span class="label">real money</span><h2>${esc(title)}</h2></div><p class="dim" id="shopDoneTxt">${esc(text)}</p><div class="row">${button ? `<button class="btn solid" id="shopOpen">open a pack</button>` : ""}<button class="btn ${button ? "ghost" : "solid"}" data-close>${button ? "later" : "ok"}</button></div></div>`, true);
  // back from Stripe: wait until the server has confirmed the payment, then collect the packs
  async function back() {
    if (!ret) { resume(); return; } if (ret.kind === "cancel") { clearPending(); toast("No payment was taken."); return; }
    const p = getPending(); if (p && p.want) want = p.want; finish(ret.sid || (p && p.sid), true);
  }

  return { load, open, has, cash, price, modal, pay, qty, setAmt, back, drop, cfg: () => cfg };
})();

/* ---- the one place that says what is and isn't real money, so no line in the game is ever wrong about it ---- */
const Money = (() => {
  const packs = () => Shop.open(), req = () => Sale.open();
  const cashy = () => Shop.cash();
  const footer = () => (cashy() || packs() || req() ? "Secure payments by Stripe · play money and cards have no cash value and can't be cashed out" : "Play money only. Nothing is charged or paid out.") + (req() ? " · the physical Requiem pack is a separate purchase" : "");
  const gate = () => cashy() ? "The game's money is play money, and nothing can be cashed out. Real money can only be used to add play money, which has no cash value." + (req() ? " The physical Requiem pack is a separate real-money purchase, on its own page." : "") : packs() ? "The game's money is play money, and nothing can be cashed out. Real money can only be used to buy packs, whose cards have no cash value." + (req() ? " The physical Requiem pack is a separate real-money purchase, on its own page." : "") : req() ? "The game is play money: nothing in it is ever charged, and nothing can be cashed out. The one exception is the physical Requiem pack, a separate real-money purchase on its own page." : "Everything here is play money: nothing is ever charged, and nothing can be cashed out.";
  const note = lead => (cashy() ? " Real money only adds play money, which has no cash value." : packs() ? (lead ? " " : " ") + "Real money only buys packs, and their cards have no cash value." : "") + (req() ? " The physical Requiem pack is a separate real-money purchase on its own page." : "");
  const about = () => cashy() ? `<b>Real money adds play money, nothing else.</b> Play money, cards and every price in the game have no cash value, and nothing can be cashed out.${req() ? " The physical Requiem pack is a separate real-money purchase on its own page." : ""}` : packs() ? `<b>Real money buys packs, nothing else.</b> Cards, balances and every price in the game are play items with no cash value, and nothing can be cashed out.${req() ? " The physical Requiem pack is a separate real-money purchase on its own page." : ""}` : `<b>Play money only.</b> Nothing in the beta costs real money and nothing can be cashed out. Cards have no cash value. Cashing out, and buying cards with real money through Stripe, are planned for the public release and are not part of this beta.${note()}`;
  function words() { const f = $("footMoney"), g = $("gateMoney"); if (f) f.textContent = footer(); if (g) g.textContent = gate(); }
  return { words, note, about, footer, gate };
})();
