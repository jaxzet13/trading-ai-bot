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
  // the one sentence that keeps every "play money" line honest while a sale is on
  const note = () => open() ? " The one exception is the physical Requiem pack, a separate real-money purchase on its own page." : "";
  function words() {
    const f = $("footMoney"), g = $("gateMoney");
    if (f) f.textContent = open() ? "the game is play money, nothing in it is charged or paid out · the physical Requiem pack is the only real-money purchase" : "play money only, nothing is ever charged or paid out";
    if (g) g.textContent = open() ? "The game is play money: nothing in it is ever charged, and nothing can be cashed out. The one exception is the physical Requiem pack, a separate real-money purchase on its own page." : "Everything here is play money: nothing is ever charged, and nothing can be cashed out.";
  }
  async function load() {
    if (!API.on) return cfg; const r = await API.get("requiem/config"); if (!r || typeof r.open !== "boolean") return cfg;
    cfg = Object.assign({ loaded: true }, r); if (r.run) RQ.run = r.run; if (r.closes) RQ.closes = r.closes;
    words(); if (view === "limited") renderLimited(); else if (view === "home") renderHome(); return cfg;
  }
  const total = () => { const q = $("rqQty"); return money((cfg.price || RQ.price) * (q ? +q.value || 1 : 1)); };
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
  return { load, open, note, words, pay, qty, poll, banner, cfg: () => cfg, ret: () => ret, total };
})();
