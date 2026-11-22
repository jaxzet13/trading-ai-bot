/* STIXX checkout: the physical Requiem pack, and digital packs. No dependencies: Node 18 or newer. Loaded by server.js.

   It sells the physical Requiem pack through Stripe Checkout (hosted by Stripe: Apple Pay, Google Pay and cards appear on their own, and a card number never touches this server).
   Nothing here is on until every setting below is present; with any of them missing the page shows the preview and /api/requiem/checkout refuses.

   Settings (environment variables):
     REQUIEM_OPEN=1               the sale switch
     STRIPE_SECRET_KEY=sk_test_…  your Stripe secret key, or a restricted rk_ key allowed to write Checkout Sessions only (use a test key until you have tried everything)
     STRIPE_WEBHOOK_SECRET=whsec_…  the signing secret of the webhook endpoint  https://YOUR-SITE/api/stripe/webhook
     PUBLIC_URL=https://…         where the page lives (https for a live key); Stripe sends buyers back here
     REQUIEM_TERMS_URL=https://…  your terms, shipping and returns page. The sale will not open without one.
     REQUIEM_RUN_FILE=…           the assembled run (design-concepts/requiem/requiem_run.py); default data/requiem-run.json
     REQUIEM_PRICE_CENTS=6500     the price of one pack, shipping included (US only)
     REQUIEM_MAX_PER_ORDER=3      packs per order
     REQUIEM_CLOSES=2027-02-14    orders close at the end of that day (UTC-5). Optional.
     STRIPE_TAX=1                 let Stripe Tax work out sales tax (set Stripe Tax up in the dashboard first). Optional.
     REQUIEM_UNIT_COST_CENTS=1200 what one Requiem pack costs you to print, pack and ship, in cents. Required: the sale won't open without it.
     REQUIEM_MIN_MARGIN_PCT=20    the least you must keep of each pack's price after Stripe's fee and your cost (default 20). The sale won't open below it.
     SHOP_MIN_NET_PCT=60          the least of each digital pack's price that must be left after Stripe's fee (default 60). A pack cheaper than that is not offered.
     STRIPE_FEE_PCT=2.9, STRIPE_FEE_FIXED_CENTS=30   Stripe's card fee, used for these checks (these are the usual US card rates: check yours)
     STRIPE_API_BASE=…            for tests only

   DIGITAL PACKS (what real money buys in the game: pack openings, nothing else; cards stay play-money game items with no cash value and nothing can be cashed out):
     SHOP_OPEN=1                  the switch for selling digital packs (needs the same STRIPE_*, PUBLIC_URL and REQUIEM_TERMS_URL settings: the terms page is your terms and refund policy)
     SHOP_PRICES={"fp":100,"ms":300}  the real price of each pack in cents: First Print $1.00, Moonshot $3.00. One flat price per pack: no bundles or discounts. Stripe's minimum is 50 cents.
     SHOP_MAX_PER_ORDER=10        packs per order
     SHOP_DAILY_CAP_CENTS=2500    the most one player can spend in a day (UTC), counting payments still open. A spending limit for the player's own protection.
   A paid pack is credited to the player's id when Stripe confirms the payment (a running total for each pack, so the page can never add the same pack twice); the page then adds it to their packs.

   What is kept: for each paid order, the Stripe session id, how many packs, which packs of the run (by number) and the amount. Names, emails, phone numbers and
   addresses stay at Stripe: read them there to ship an order. A pack is assigned when Stripe says the payment is complete, in the order payments arrive, from a
   list that was shuffled and fingerprinted (SHA-256) before the sale. That is what makes the published counts the real counts: the packs are finite, and every pack
   is spoken for exactly once. While someone is paying, their packs are held so two buyers can't be sold the same last pack.
*/
"use strict";
const http = require("http"), https = require("https"), crypto = require("crypto"), fs = require("fs"), path = require("path");

module.exports = function payments(ctx) {
  const { db, touch, saveNow, limited, adminToken, dataDir } = ctx;
  const sha = b => crypto.createHash("sha256").update(b).digest("hex");

  const settings = () => {
    const E = process.env;
    return {
      openFlag: E.REQUIEM_OPEN === "1", key: E.STRIPE_SECRET_KEY || "", whsec: E.STRIPE_WEBHOOK_SECRET || "", apiBase: (E.STRIPE_API_BASE || "https://api.stripe.com").replace(/\/$/, ""),
      site: (E.PUBLIC_URL || "").replace(/\/$/, ""), terms: E.REQUIEM_TERMS_URL || "", price: Math.round(+E.REQUIEM_PRICE_CENTS) || 6500, maxQty: Math.max(1, Math.min(10, Math.round(+E.REQUIEM_MAX_PER_ORDER) || 3)),
      feePct: Number.isFinite(+E.STRIPE_FEE_PCT) && E.STRIPE_FEE_PCT ? +E.STRIPE_FEE_PCT : 2.9, feeFixed: /^\d+$/.test(E.STRIPE_FEE_FIXED_CENTS || "") ? +E.STRIPE_FEE_FIXED_CENTS : 30,
      unitCost: /^\d+$/.test(E.REQUIEM_UNIT_COST_CENTS || "") ? +E.REQUIEM_UNIT_COST_CENTS : null, minMargin: Number.isFinite(+E.REQUIEM_MIN_MARGIN_PCT) && E.REQUIEM_MIN_MARGIN_PCT ? +E.REQUIEM_MIN_MARGIN_PCT : 20,
      closes: /^\d{4}-\d{2}-\d{2}$/.test(E.REQUIEM_CLOSES || "") ? E.REQUIEM_CLOSES : "", tax: E.STRIPE_TAX === "1", runFile: path.resolve(E.REQUIEM_RUN_FILE || path.join(dataDir, "requiem-run.json"))
    };
  };

  /* ---- the run: a list of sealed packs, shuffled before the sale. Read from disk, never served. ---- */
  let cache = { file: "", mtime: 0, run: null, commit: "" };
  function loadRun(file) {
    try {
      const st = fs.statSync(file); if (cache.file === file && cache.mtime === st.mtimeMs && cache.run) return cache;
      const raw = fs.readFileSync(file), run = JSON.parse(raw.toString("utf8"));
      if (!run || !Array.isArray(run.packs) || !run.packs.length || !run.packs.every(p => Array.isArray(p) && p.length === 3 && p.every(c => typeof c === "string"))) return null;
      return (cache = { file, mtime: st.mtimeMs, run, commit: sha(raw) });
    } catch (e) { return null; }
  }
  const counts = run => { const o = {}; for (const p of run.packs) for (const c of p) o[c] = (o[c] || 0) + 1; return o; };

  /* ---- what has been sold and what is being paid for right now ---- */
  const S = () => { const d = db(); return d.rq = d.rq || { sold: 0, orders: {}, hold: {}, commit: "" }; };
  const prune = () => { const s = S(), t = Date.now(); for (const [k, h] of Object.entries(s.hold)) if (h.exp < t) delete s.hold[k]; };
  const held = () => Object.values(S().hold).reduce((a, h) => a + h.qty, 0);
  // what Stripe takes from one charge, and what is left: the checks below never let a product be sold at a loss
  const feeOf = (cents, c) => Math.round(cents * c.feePct / 100 + c.feeFixed);
  const closesAt = c => c.closes ? Date.parse(c.closes + "T23:59:59-05:00") : 0;

  function requiemEcon(c) {
    const fee = feeOf(c.price, c), out = { price: c.price, fee, unitCost: c.unitCost, net: null, marginPct: null, why: "" };
    if (c.unitCost === null) { out.why = "REQUIEM_UNIT_COST_CENTS is not set: say what one pack costs you to print, pack and ship, so the server can check you make a profit"; return out; }
    out.net = c.price - fee - c.unitCost; out.marginPct = +(out.net / c.price * 100).toFixed(1);
    if (out.net <= 0 || out.marginPct < c.minMargin) out.why = `at ${(c.price / 100).toFixed(2)} a pack you would keep only ${(out.net / 100).toFixed(2)} (${out.marginPct}%) after Stripe's fee and your cost, under your minimum of ${c.minMargin}%`;
    return out;
  }
  function status() {
    const c = settings(), why = [], rc = loadRun(c.runFile), s = S(); prune();
    if (!c.openFlag) why.push("REQUIEM_OPEN is not 1");
    if (!/^(sk|rk)_(test|live)_\S+$/.test(c.key)) why.push("STRIPE_SECRET_KEY is missing or is not a secret key");
    if (!/^whsec_\S+$/.test(c.whsec)) why.push("STRIPE_WEBHOOK_SECRET is missing");
    if (!/^https?:\/\/\S+$/.test(c.site)) why.push("PUBLIC_URL is missing"); else if (/^(sk|rk)_live_/.test(c.key) && !/^https:/.test(c.site)) why.push("PUBLIC_URL must be https with a live key");
    if (!/^https?:\/\/\S+$/.test(c.terms)) why.push("REQUIEM_TERMS_URL is missing: publish your terms, shipping and returns first");
    if (!rc) why.push("the run file is missing or invalid (run requiem_run.py)");
    else if (s.commit && s.commit !== rc.commit) why.push("the run file changed after sales began, which must never happen");
    if (c.closes && Date.now() > closesAt(c)) why.push("orders are closed");
    const econ = requiemEcon(c); if (econ.why) why.push(econ.why);
    const left = rc ? rc.run.packs.length - s.sold - held() : 0;
    return { c, rc, why, left, econ, soldOut: !!rc && rc.run.packs.length - s.sold <= 0, open: !why.length && left > 0 };
  }


  /* ---- digital packs ---- */
  const PACK_NAMES = { fp: "First Print", ms: "Moonshot" };
  const shopPrices = () => { let p = { fp: 100, ms: 300 }; try { const e = JSON.parse(process.env.SHOP_PRICES || "null"); if (e && typeof e === "object" && !Array.isArray(e)) p = e; } catch (x) {} const o = {}; for (const [k, v] of Object.entries(p)) if (/^[a-z]{1,12}$/.test(k) && Number.isInteger(v) && v >= 50 && v <= 100000) o[k] = v; return o; };
  const shopSettings = () => { const E = process.env; return { open: E.SHOP_OPEN === "1", prices: shopPrices(), minNet: Number.isFinite(+E.SHOP_MIN_NET_PCT) && E.SHOP_MIN_NET_PCT ? +E.SHOP_MIN_NET_PCT : 60, maxQty: Math.max(1, Math.min(50, Math.round(+E.SHOP_MAX_PER_ORDER) || 10)), cap: Math.round(+E.SHOP_DAILY_CAP_CENTS) || 2500 }; };
  const SH = () => { const d = db(); return d.shop = d.shop || { orders: {}, hold: {}, spent: {} }; };
  const today = () => new Date().toISOString().slice(0, 10), validUid = u => typeof u === "string" && /^[a-f0-9]{16,64}$/.test(u);
  const shopPrune = () => { const h = SH().hold, t = Date.now(); for (const k of Object.keys(h)) if (h[k].exp < t) delete h[k]; };
  const shopSpent = uid => { shopPrune(); const sh = SH(); return (sh.spent[uid + ":" + today()] || 0) + Object.values(sh.hold).filter(h => h.uid === uid).reduce((a, h) => a + h.cents, 0); };
  function shopStatus() {
    const c = settings(), sc = shopSettings(), why = [];
    if (!sc.open) why.push("SHOP_OPEN is not 1");
    if (!/^(sk|rk)_(test|live)_\S+$/.test(c.key)) why.push("STRIPE_SECRET_KEY is missing or is not a secret key");
    if (!/^whsec_\S+$/.test(c.whsec)) why.push("STRIPE_WEBHOOK_SECRET is missing");
    if (!/^https?:\/\/\S+$/.test(c.site)) why.push("PUBLIC_URL is missing"); else if (/^(sk|rk)_live_/.test(c.key) && !/^https:/.test(c.site)) why.push("PUBLIC_URL must be https with a live key");
    if (!/^https?:\/\/\S+$/.test(c.terms)) why.push("REQUIEM_TERMS_URL is missing: publish your terms and refund policy first");
    const econ = {}; for (const [id, price] of Object.entries(sc.prices)) { const fee = feeOf(price, c), net = price - fee, netPct = +(net / price * 100).toFixed(1); econ[id] = { price, fee, net, netPct, offered: netPct >= sc.minNet }; if (netPct < sc.minNet) delete sc.prices[id]; }
    if (!Object.keys(sc.prices).length) why.push("no pack is offered: SHOP_PRICES is empty, or each price leaves less than " + sc.minNet + "% after Stripe's fee");
    return { c, sc, why, econ, open: !why.length };
  }
  function credit(o) {                                                     // a payment for digital packs is complete: add the packs to the player's running total
    const sh = SH(), md = o.metadata || {}; if (sh.orders[o.id]) return;   // already recorded: Stripe may deliver an event more than once
    const qty = Math.max(1, Math.min(50, Math.round(+md.qty) || 1)), pack = String(md.pack || ""), u = db().users[md.uid], cents = o.amount_total || 0, known = /^[a-z]{1,12}$/.test(pack); delete sh.hold[o.id];
    if (u && known) { u.paidTotals = u.paidTotals || {}; u.paidTotals[pack] = (u.paidTotals[pack] || 0) + qty; const k = md.uid + ":" + today(); sh.spent[k] = (sh.spent[k] || 0) + cents; }
    sh.orders[o.id] = { uid: md.uid, pack, qty, cents, at: Date.now(), short: u && known ? 0 : qty };       // short > 0: the player could not be found, so refund it in Stripe
    saveNow();
  }

  /* ---- Stripe ---- */
  const enc = (o, prefix, out) => { out = out || []; for (const [k, v] of Object.entries(o)) { const key = prefix ? `${prefix}[${k}]` : k; if (v && typeof v === "object") enc(v, key, out); else out.push(encodeURIComponent(key) + "=" + encodeURIComponent(String(v))); } return out; };
  function stripe(method, pathname, params) {
    const c = settings(), u = new URL(c.apiBase + pathname), lib = u.protocol === "http:" ? http : https, body = method === "POST" ? enc(params || {}).join("&") : "";
    return new Promise((resolve, reject) => {
      const req = lib.request({ method, hostname: u.hostname, port: u.port || (u.protocol === "http:" ? 80 : 443), path: u.pathname + u.search,
        headers: { authorization: "Bearer " + c.key, "content-type": "application/x-www-form-urlencoded", "content-length": Buffer.byteLength(body), "idempotency-key": crypto.randomBytes(16).toString("hex") } }, res => {
        let d = ""; res.on("data", x => d += x); res.on("end", () => { try { const j = JSON.parse(d); if (res.statusCode >= 200 && res.statusCode < 300) resolve(j); else reject(Object.assign(new Error((j.error && j.error.message) || "stripe error"), { status: res.statusCode })); } catch (e) { reject(e); } });
      });
      req.setTimeout(10000, () => req.destroy(new Error("stripe timed out"))); req.on("error", reject); req.end(body);
    });
  }

  function verify(raw, header, secret) {                                   // https://docs.stripe.com/webhooks/signature : HMAC-SHA256 of "t.rawbody", compared in constant time, within 5 minutes
    if (!secret || !header) return false;
    let t = "", v1 = []; for (const kv of String(header).split(",")) { const i = kv.indexOf("="); if (i < 0) continue; const k = kv.slice(0, i).trim(), v = kv.slice(i + 1).trim(); if (k === "t") t = v; else if (k === "v1") v1.push(v); }
    if (!/^\d+$/.test(t) || !v1.length || Math.abs(Date.now() / 1000 - +t) > 300) return false;
    const mac = crypto.createHmac("sha256", secret).update(t + ".").update(raw).digest("hex");
    return v1.some(s => s.length === mac.length && crypto.timingSafeEqual(Buffer.from(s), Buffer.from(mac)));
  }

  function record(o) {                                                      // a payment is complete: give the buyer the next packs of the run
    const s = S(), rc = loadRun(settings().runFile); if (!rc || s.orders[o.id]) return;       // already recorded: Stripe may deliver an event more than once
    const qty = Math.max(1, Math.min(10, Math.round(+(o.metadata || {}).qty) || 1)), idx = [];
    delete s.hold[o.id]; s.commit = s.commit || rc.commit;
    for (let i = 0; i < qty && s.sold < rc.run.packs.length; i++) idx.push(s.sold++);
    s.orders[o.id] = { qty, packs: idx, short: qty - idx.length, amount: o.amount_total || 0, at: Date.now() };    // short > 0 means the run ran out: refund it in Stripe
    saveNow();
  }
  function handle(ev) {
    const o = (ev && ev.data && ev.data.object) || {};
    if (ev.type === "checkout.session.completed" || ev.type === "checkout.session.async_payment_succeeded") {
      if (o.metadata && o.payment_status === "paid") { if (o.metadata.kind === "requiem") record(o); else if (o.metadata.kind === "packs") credit(o); }
      return;
    }
    if (ev.type === "checkout.session.expired" || ev.type === "checkout.session.async_payment_failed") { let c = false; if (S().hold[o.id]) { delete S().hold[o.id]; c = true; } if (SH().hold[o.id]) { delete SH().hold[o.id]; c = true; } if (c) touch(); }
  }
  /* ---- ask Stripe directly. The buyer can come back before the webhook does, and a webhook can fail or never be set up right, so a paid session is also found by
     asking Stripe itself (the answer comes from Stripe over https, so nobody can fake it). credit() and record() ignore a session they have already recorded. ---- */
  const consider = s => { try { if (!s || s.payment_status !== "paid" || !s.metadata) return; if (s.metadata.kind === "packs") credit(s); else if (s.metadata.kind === "requiem") record(s); } catch (e) { console.error("consider:", e.message); } };
  async function pull(sid) { try { consider(await stripe("GET", "/v1/checkout/sessions/" + encodeURIComponent(sid))); } catch (e) { console.error("pull:", e.message); } }
  let sweeping = false;
  async function sweep(days) {
    if (sweeping || !settings().key) return; sweeping = true;
    try { const r = await stripe("GET", "/v1/checkout/sessions?limit=100&created[gte]=" + (Math.floor(Date.now() / 1000) - days * 86400)); for (const s of (r && r.data) || []) consider(s); }
    catch (e) { console.error("sweep:", e.message); } finally { sweeping = false; }
  }
  setTimeout(() => sweep(7), 4000).unref(); setInterval(() => sweep(2), 300000).unref();      // once after starting (a payment made while the server was down or the webhook was broken), then every five minutes
  const SID = /^cs_(test|live)_\w{1,120}$/;

  function webhook(req, res, send) {
    const chunks = []; let size = 0;
    req.on("data", d => { size += d.length; if (size > 1e6) req.destroy(); else chunks.push(d); });
    req.on("end", () => {
      const raw = Buffer.concat(chunks); if (!verify(raw, req.headers["stripe-signature"], settings().whsec)) return send(res, 400, "bad signature", "text/plain");
      let ev; try { ev = JSON.parse(raw.toString("utf8")); } catch (e) { return send(res, 400, "bad json", "text/plain"); }
      try { handle(ev); } catch (e) { console.error("webhook:", e.message); return send(res, 500, "error", "text/plain"); }
      send(res, 200, "ok", "text/plain");
    });
  }

  /* ---- the API ---- */
  const routes = {
    // what the page needs to know: is it on sale, for how much, how big is the run. Nothing secret, and no count of how many are left.
    "GET /api/requiem/config": () => {
      const st = status(), c = st.c; return { open: st.open, soldOut: c.openFlag && st.soldOut, price: c.price, maxQty: c.maxQty, closes: c.closes, terms: c.terms, run: st.rc ? st.rc.run.packs.length : null, commit: st.rc ? st.rc.commit : "", counts: st.rc ? counts(st.rc.run) : null };
    },
    "POST /api/requiem/checkout": async (b, ip) => {
      const st = status(), c = st.c; if (!st.open) return { error: st.soldOut ? "Requiem is sold out." : "Requiem isn't on sale right now." };
      if (b.age !== true) return { error: "Please confirm you are 18 or older." };
      const qty = b.qty === undefined ? 1 : Number(b.qty); if (!Number.isInteger(qty) || qty < 1 || qty > c.maxQty) return { error: `You can buy 1 to ${c.maxQty} packs at a time.` };
      if (st.left < qty) return { error: st.left > 0 ? `Only ${st.left} pack${st.left > 1 ? "s are" : " is"} available right now.` : "Requiem is sold out right now." };
      if (limited("rqco:" + ip, 8, 600000)) return [429, { error: "slow down" }];                       // only real attempts (the ones that reach Stripe) count
      const expires = Math.floor(Date.now() / 1000) + 31 * 60, p = {
        mode: "payment", "line_items": { 0: { quantity: qty, price_data: { currency: "usd", unit_amount: c.price, product_data: { name: "STIXX Requiem: sealed pack of 3 cards", description: "A limited physical pack of 3 cards. Contents are fixed before the sale; the odds are published and never change." } } } },
        shipping_address_collection: { allowed_countries: { 0: "US" } }, phone_number_collection: { enabled: "true" },
        success_url: `${c.site}/?rq=paid&sid={CHECKOUT_SESSION_ID}#/limited`, cancel_url: `${c.site}/?rq=cancel#/limited`, expires_at: expires,
        metadata: { kind: "requiem", qty, age: "18+" }, custom_text: { submit: { message: "Random cards, 18+ only. The odds are published on the Requiem page and never change." } }
      };
      if (c.tax) p.automatic_tax = { enabled: "true" };
      let s; try { s = await stripe("POST", "/v1/checkout/sessions", p); } catch (e) { console.error("checkout:", e.message); return { error: "Payment isn't available right now. You have not been charged." }; }
      if (!s || !s.id || !s.url) return { error: "Payment isn't available right now. You have not been charged." };
      const state = S(); state.commit = state.commit || st.rc.commit; state.hold[s.id] = { qty, exp: Date.now() + 32 * 60000 }; touch();
      return { url: s.url };
    },
    // after paying, the page asks which packs are the buyer's (the session id in the link is the key). Pack numbers only: the contents stay sealed.
    "GET /api/requiem/order": async (_b, ip, q) => {
      const sid = String(q.get("sid") || ""); let o = S().orders[sid]; if (!o && SID.test(sid) && !limited("pull:" + ip, 60, 60000)) { await pull(sid); o = S().orders[sid]; } if (!o) return { pending: true }; const rc = loadRun(settings().runFile);
      return { ok: true, qty: o.qty, packs: o.packs.map(i => i + 1), run: rc ? rc.run.packs.length : null, short: !!o.short };
    },

    /* ---- digital packs ---- */
    "GET /api/shop/config": (_b, _ip, q) => {
      const st = shopStatus(), uid = q.get("uid"); return { open: st.open, prices: st.sc.prices, maxQty: st.sc.maxQty, cap: st.sc.cap, terms: st.c.terms, spentToday: validUid(uid) ? shopSpent(uid) : 0 };
    },
    "POST /api/shop/checkout": async (b, ip) => {
      const st = shopStatus(), c = st.c, sc = st.sc; if (!st.open) return { error: "Buying packs isn't available right now." };
      if (!validUid(b.uid) || !db().users[b.uid]) return { error: "Open the game once and try again." };
      if (b.age !== true) return { error: "Please confirm you are 18 or older." };
      const pack = String(b.pack || ""), unit = sc.prices[pack]; if (!unit) return { error: "Choose a pack to buy." };
      const qty = b.qty === undefined ? 1 : Number(b.qty); if (!Number.isInteger(qty) || qty < 1 || qty > sc.maxQty) return { error: `You can buy 1 to ${sc.maxQty} packs at a time.` };
      const cents = qty * unit, spent = shopSpent(b.uid), money = n => "$" + (n / 100).toFixed(2);
      if (spent + cents > sc.cap) return { error: spent >= sc.cap ? `You've reached today's limit of ${money(sc.cap)}. It resets tomorrow (UTC).` : `That would go over today's limit of ${money(sc.cap)}. You can spend up to ${money(sc.cap - spent)} more today.` };
      if (limited("shco:" + ip, 8, 600000)) return [429, { error: "slow down" }];
      const p = {
        mode: "payment", line_items: { 0: { quantity: qty, price_data: { currency: "usd", unit_amount: unit, product_data: { name: "STIXX digital pack: " + (PACK_NAMES[pack] || pack), description: "A pack of random digital cards for the STIXX game. The cards have no cash value and can't be cashed out." } } } },
        success_url: `${c.site}/?pk=paid&sid={CHECKOUT_SESSION_ID}`, cancel_url: `${c.site}/?pk=cancel`, expires_at: Math.floor(Date.now() / 1000) + 31 * 60, client_reference_id: b.uid,
        metadata: { kind: "packs", uid: b.uid, pack, qty, age: "18+" }, custom_text: { submit: { message: "Random digital cards, 18+ only. The cards have no cash value and can't be cashed out." } }
      };
      if (c.tax) p.automatic_tax = { enabled: "true" };
      let s; try { s = await stripe("POST", "/v1/checkout/sessions", p); } catch (e) { console.error("shop checkout:", e.message); return { error: "Payment isn't available right now. You have not been charged." }; }
      if (!s || !s.id || !s.url) return { error: "Payment isn't available right now. You have not been charged." };
      SH().hold[s.id] = { uid: b.uid, cents, exp: Date.now() + 32 * 60000 }; touch(); return { url: s.url };
    },
    // after paying: has the payment been confirmed and credited yet?
    "GET /api/shop/order": async (_b, ip, q) => { const sid = String(q.get("sid") || ""); let o = SH().orders[sid]; if (!o && SID.test(sid) && !limited("pull:" + ip, 60, 60000)) { await pull(sid); o = SH().orders[sid]; } return o ? { ok: true, pack: o.pack, qty: o.qty, short: !!o.short } : { pending: true }; },
    "GET /api/shop/orders": (_b, _ip, q) => {
      if (!adminToken || q.get("token") !== adminToken) return [403, { error: "no" }]; const st = shopStatus(), sh = SH(), os = Object.entries(sh.orders);
      return { open: st.open, why: st.why, economics: st.econ, orders: os.map(([sid, o]) => ({ sid, player: String(o.uid || "").slice(0, 8), pack: o.pack, qty: o.qty, cents: o.cents, at: new Date(o.at).toISOString(), short: o.short })), packs: os.reduce((a, [, o]) => a + (o.short ? 0 : o.qty), 0), cents: os.reduce((a, [, o]) => a + o.cents, 0) };
    },
    // for you: every paid order and what is inside the packs to send. Needs ADMIN_TOKEN. Addresses are in the Stripe dashboard, not here.
    "GET /api/requiem/orders": (_b, _ip, q) => {
      if (!adminToken || q.get("token") !== adminToken) return [403, { error: "no" }]; const st = status(), s = S(), rc = st.rc;
      return { open: st.open, why: st.why, economics: st.econ, run: rc ? rc.run.packs.length : 0, sold: s.sold, held: held(), commit: rc ? rc.commit : "", orders: Object.entries(s.orders).map(([sid, o]) => ({ sid, at: new Date(o.at).toISOString(), amount: o.amount, short: o.short, packs: o.packs.map(i => ({ no: i + 1, cards: rc ? rc.run.packs[i] : null })) })) };
    }
  };
  return { routes, webhook, status };
};
