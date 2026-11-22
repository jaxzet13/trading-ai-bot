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
const Shop = (() => {
  let cfg = { open: false, prices: {} };
  const ret = (() => {                                                     // ?pk=paid&sid=… or ?pk=cancel, on the way back from Stripe
    try {
      const p = new URLSearchParams(location.search), k = p.get("pk"); if (!k) return null;
      const sid = (p.get("sid") || "").replace(/[^\w]/g, "").slice(0, 120); p.delete("pk"); p.delete("sid");
      history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : "") + location.hash); return { kind: k === "paid" ? "paid" : "cancel", sid };
    } catch (e) { return null; }
  })();
  const open = () => !!cfg.open && PACKS.some(p => cfg.prices && cfg.prices[p.id]), has = id => !!cfg.open && !!(cfg.prices && cfg.prices[id]), price = id => (cfg.prices && cfg.prices[id]) || 0;
  async function load() {
    if (!API.on) return; const r = await API.get("shop/config?uid=" + encodeURIComponent(state.uid)); if (!r || typeof r.open !== "boolean") return;
    cfg = r; Money.words(); if (view === "home") renderHome();
  }
  const chosen = () => { const s = $("shopPack"); return s ? s.value : curPack().id; }, count = () => { const q = $("shopQty"); return q ? +q.value || 1 : 1; };
  const total = () => rmoney(price(chosen()) * count());
  function qty() { const b = $("shopPay"); if (b && !b.dataset.busy) b.textContent = "Pay " + total(); const e = $("shopEach"); if (e) e.textContent = rmoney(price(chosen())) + " per pack"; }
  function modal() {
    const ids = PACKS.filter(p => has(p.id)).map(p => p.id); if (!ids.length) return; const cur = ids.includes(curPack().id) ? curPack().id : ids[0];
    openModal(`<div class="minfo"><div><span class="label">real money</span><h2>Buy packs</h2></div>
      <p class="dim">Real money buys packs, and nothing else. Each pack holds random digital cards: you can't choose them, and the odds are on the <a href="#/odds" data-close>odds page</a>. The cards are game items with <b>no cash value</b>. Nothing in STIXX can be cashed out, and the prices you see in the game are simulated.</p>
      <div class="rqbuyh"><label class="rqqty" style="justify-items:start"><span class="small">Pack</span><select id="shopPack" aria-label="Which pack">${ids.map(id => `<option value="${id}"${id === cur ? " selected" : ""}>${esc(PACK_BY[id].name)} · ${rmoney(price(id))}</option>`).join("")}</select></label>
        <label class="rqqty"><span class="small">How many</span><select id="shopQty" aria-label="How many packs">${Array.from({ length: cfg.maxQty || 1 }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("")}</select></label></div>
      <p class="small" style="margin:-6px 0 0"><b id="shopEach">${rmoney(price(cur))} per pack</b> · one flat price: no bundles, no discounts</p>
      <label class="rqage"><input type="checkbox" id="shopAge"><span>I'm 18 or older, I understand the packs are random, and I'm spending real money.</span></label>
      <button class="btn solid big" id="shopPay" disabled>Pay ${rmoney(price(cur))}</button>
      <p class="small">Apple Pay, Google Pay or card, on Stripe's secure page. STIXX never sees your card. You are only charged after you confirm there. There is a limit of ${rmoney(cfg.cap || 0)} a day${cfg.spentToday > 0 ? ` (you have used ${rmoney(cfg.spentToday)} today)` : ""}. <a href="${esc(cfg.terms || "#")}" target="_blank" rel="noopener">Terms and refunds</a>.</p>
      <div class="row"><button class="btn ghost" data-close>not now</button></div></div>`, true);
  }
  async function pay() {
    const age = $("shopAge") && $("shopAge").checked, b = $("shopPay"); if (!age || !b || b.dataset.busy) return;
    b.dataset.busy = 1; b.disabled = true; b.textContent = "Opening Stripe…";
    const r = await API.post("shop/checkout", { uid: state.uid, pack: chosen(), qty: count(), age: true });
    if (r && typeof r.url === "string" && /^https:\/\//.test(r.url)) { location.href = r.url; return; }
    delete b.dataset.busy; b.disabled = !($("shopAge") && $("shopAge").checked); qty(); toast((r && r.error) || "Couldn't reach the server. You have not been charged.");
  }
  const done = (title, text, button) => openModal(`<div class="minfo"><div><span class="label">real money</span><h2>${esc(title)}</h2></div><p class="dim" id="shopDoneTxt">${esc(text)}</p><div class="row">${button ? `<button class="btn solid" id="shopOpen">open a pack</button>` : ""}<button class="btn ${button ? "ghost" : "solid"}" data-close>${button ? "later" : "ok"}</button></div></div>`, true);
  // back from Stripe: wait until the server has confirmed the payment, then collect the packs
  async function back() {
    if (!ret) return; if (ret.kind === "cancel") { toast("No payment was taken."); return; }
    done("Thank you", "Checking your payment…", false);
    for (let i = 0; i < 20 && ret.sid; i++) {
      const r = await API.get("shop/order?sid=" + encodeURIComponent(ret.sid));
      if (r && r.ok) {
        if (r.short) { done("Thank you", "Your payment went through, but we couldn't add the packs to your game. You will be refunded.", false); return; }
        await Ref.sync(); const n = r.qty || 1, pn = PACK_BY[r.pack] ? PACK_BY[r.pack].name + " " : ""; if (PACK_BY[r.pack] && state.pack !== r.pack) { state.pack = r.pack; persist(); }
        done("Your packs are ready", `Your payment went through. ${n} ${pn}pack${n > 1 ? "s are" : " is"} ready to open. You'll find ${n > 1 ? "them" : "it"} on the pack page.`, true); if (view === "home") renderHome(); return;
      }
      await sleep(2000);
    }
    if ($("shopDoneTxt")) $("shopDoneTxt").textContent = "Your payment is still being confirmed. Your packs will appear on the pack page within a few minutes.";
  }
  return { load, open, has, price, modal, pay, qty, back, cfg: () => cfg };
})();

/* ---- the one place that says what is and isn't real money, so no line in the game is ever wrong about it ---- */
const Money = (() => {
  const packs = () => Shop.open(), req = () => Sale.open();
  const footer = () => packs() ? "the game's money is play money and can't be cashed out · real money only buys packs, whose cards have no cash value" + (req() ? " · the physical Requiem pack is a separate purchase" : "") : req() ? "the game is play money, nothing in it is charged or paid out · the physical Requiem pack is the only real-money purchase" : "play money only, nothing is ever charged or paid out";
  const gate = () => packs() ? "The game's money is play money, and nothing can be cashed out. Real money can only be used to buy packs, whose cards have no cash value." + (req() ? " The physical Requiem pack is a separate real-money purchase, on its own page." : "") : req() ? "The game is play money: nothing in it is ever charged, and nothing can be cashed out. The one exception is the physical Requiem pack, a separate real-money purchase on its own page." : "Everything here is play money: nothing is ever charged, and nothing can be cashed out.";
  const note = lead => (packs() ? (lead ? " " : " ") + "Real money only buys packs, and their cards have no cash value." : "") + (req() ? " The physical Requiem pack is a separate real-money purchase on its own page." : "");
  const about = () => packs() ? `<b>Real money buys packs, nothing else.</b> Cards, balances and every price in the game are play items with no cash value, and nothing can be cashed out.${req() ? " The physical Requiem pack is a separate real-money purchase on its own page." : ""}` : `<b>Play money only.</b> Nothing in the beta costs real money and nothing can be cashed out. Cards have no cash value. Cashing out, and buying cards with real money through Stripe, are planned for the public release and are not part of this beta.${note()}`;
  function words() { const f = $("footMoney"), g = $("gateMoney"); if (f) f.textContent = footer(); if (g) g.textContent = gate(); }
  return { words, note, about, footer, gate };
})();
