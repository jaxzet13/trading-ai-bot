#!/usr/bin/env node
/* Tests for the Requiem checkout (pay.js) against a pretend Stripe. No dependencies, no network:  node test-pay.js
   It starts server.js twice (sale off, sale on) and a stand-in for Stripe's API, then checks the rules that matter when money is involved. */
"use strict";
const assert = require("assert"), http = require("http"), crypto = require("crypto"), fs = require("fs"), os = require("os"), path = require("path"), { spawn, execFileSync } = require("child_process");
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log("FAIL", m); } else console.log("ok  ", m); };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "stixx-pay-")), RUN = path.join(tmp, "requiem-run.json");
execFileSync("python3", [path.join(__dirname, "design-concepts", "requiem", "requiem_run.py"), "--packs", "6", "--out", tmp, "--seed", "t"], { stdio: "ignore" });
const run = JSON.parse(fs.readFileSync(RUN, "utf8"));
const WH = "whsec_testsecret", KEY = "sk_test_abc";

/* ---- a stand-in for Stripe's API ---- */
const seen = [], reads = [], sessions = {}; let n = 0, failNext = false;
const stripe = http.createServer((req, res) => {
  let b = ""; req.on("data", c => b += c); req.on("end", () => {
    if (req.method === "GET") {                                  // Stripe answering "what is the state of this session": retrieve one, or list the recent ones
      reads.push(req.url); const u = new URL(req.url, "http://x"); res.writeHead(200, { "content-type": "application/json" });
      if (u.pathname === "/v1/checkout/sessions") return res.end(JSON.stringify({ data: Object.values(sessions) }));
      const s = sessions[u.pathname.split("/").pop()]; if (!s) { res.writeHead(404); return res.end(JSON.stringify({ error: { message: "no such session" } })); } return res.end(JSON.stringify(s));
    }
    if (failNext) { failNext = false; res.writeHead(500, { "content-type": "application/json" }); return res.end(JSON.stringify({ error: { message: "boom" } })); }
    const id = "cs_test_" + (++n), form = Object.fromEntries(new URLSearchParams(b)); seen.push({ path: req.url, headers: req.headers, form });
    sessions[id] = { id, payment_status: "unpaid", amount_total: (+form["line_items[0][price_data][unit_amount]"] || 0) * (+form["line_items[0][quantity]"] || 1), metadata: { kind: form["metadata[kind]"], uid: form["metadata[uid]"], pack: form["metadata[pack]"], qty: form["metadata[qty]"] } };
    res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify({ id, url: "https://checkout.stripe.test/pay/" + id }));
  });
});

const call = (port, method, p, body, headers) => new Promise((resolve, reject) => {
  const data = body === undefined ? "" : typeof body === "string" ? body : JSON.stringify(body);
  const r = http.request({ port, method, path: p, headers: Object.assign({ "content-length": Buffer.byteLength(data) }, method === "POST" && !headers ? { "content-type": "application/json" } : {}, headers || {}) }, res => { let d = ""; res.on("data", c => d += c); res.on("end", () => { let j = null; try { j = JSON.parse(d); } catch (e) {} resolve({ status: res.statusCode, json: j, text: d }); }); });
  r.on("error", reject); r.end(data);
});
const sign = (raw, secret, t) => { t = t || Math.floor(Date.now() / 1000); return `t=${t},v1=${crypto.createHmac("sha256", secret || WH).update(`${t}.${raw}`).digest("hex")}`; };
const hook = (port, ev, opts) => { const raw = JSON.stringify(ev); opts = opts || {}; return call(port, "POST", "/api/stripe/webhook", raw, { "stripe-signature": opts.sig || sign(raw, opts.secret, opts.t), "content-type": "application/json" }); };
const done = (sid, qty, extra) => Object.assign({ id: "evt_" + sid, type: "checkout.session.completed", data: { object: Object.assign({ id: sid, payment_status: "paid", amount_total: 6500 * qty, metadata: { kind: "requiem", qty: String(qty) } }, extra || {}) } });

function start(env, dataName) {
  const port = 21000 + Math.floor(Math.random() * 3000), child = spawn(process.execPath, [path.join(__dirname, "server.js")], { env: Object.assign({}, process.env, { PORT: String(port), DATA_FILE: path.join(tmp, dataName), ADMIN_TOKEN: "tok", REQUIEM_RUN_FILE: RUN }, env), stdio: ["ignore", "ignore", "inherit"] });
  return new Promise(async (resolve, reject) => { for (let i = 0; i < 60; i++) { try { const r = await call(port, "GET", "/api/health"); if (r.status === 200) return resolve({ port, kill: () => new Promise(res => { child.once("exit", res); child.kill("SIGTERM"); }) }); } catch (e) {} await new Promise(r => setTimeout(r, 100)); } reject(new Error("server did not start")); });
}

(async () => {
  await new Promise(r => stripe.listen(0, "127.0.0.1", r)); const SP = stripe.address().port;
  const open = { REQUIEM_OPEN: "1", STRIPE_SECRET_KEY: KEY, STRIPE_WEBHOOK_SECRET: WH, PUBLIC_URL: "https://example.test", REQUIEM_TERMS_URL: "https://example.test/terms", REQUIEM_UNIT_COST_CENTS: "1200", STRIPE_API_BASE: "http://127.0.0.1:" + SP };

  // ---- the sale is off unless every setting is there
  let s = await start({}, "off.json");
  let r = await call(s.port, "GET", "/api/requiem/config"); ok(r.status === 200 && r.json.open === false && r.json.price === 6500, "with nothing set, the sale is closed (config says open: false)");
  r = await call(s.port, "POST", "/api/requiem/checkout", { qty: 1, age: true }); ok(r.json && r.json.error && !r.json.url, "and checkout refuses");
  r = await hook(s.port, done("cs_x", 1), { sig: "t=1,v1=00" }); ok(r.status === 400, "a webhook with a bad signature is refused");
  r = await call(s.port, "GET", "/api/requiem/orders"); ok(r.status === 403, "the order list needs the admin token");
  r = await call(s.port, "GET", "/api/requiem/orders?token=tok"); ok(r.json.open === false && r.json.why.some(w => /REQUIEM_OPEN/.test(w)) && r.json.why.some(w => /STRIPE_SECRET_KEY/.test(w)) && r.json.why.some(w => /TERMS/.test(w)), "the admin view says what is missing (" + r.json.why.length + " reasons)");
  for (const miss of ["REQUIEM_TERMS_URL", "STRIPE_WEBHOOK_SECRET", "PUBLIC_URL"]) {
    const e = Object.assign({}, open); delete e[miss]; const t = await start(e, "miss-" + miss + ".json"); const c = (await call(t.port, "GET", "/api/requiem/config")).json; ok(c.open === false, "closed without " + miss); await t.kill();
  }
  await s.kill();

  // ---- the sale is on
  s = await start(open, "on.json"); const P = s.port;
  r = await call(P, "GET", "/api/requiem/config"); const cfg = r.json;
  ok(cfg.open === true && cfg.price === 6500 && cfg.run === 6 && cfg.terms === "https://example.test/terms" && /^[0-9a-f]{64}$/.test(cfg.commit) && !("left" in cfg), "with everything set it is open; it shows the price, run size, terms and fingerprint, and not how many are left");
  ok(Object.values(cfg.counts).reduce((a, b) => a + b, 0) === 18 && Object.keys(cfg.counts).length === 6, "the page is told the real counts of the run (18 cards, all six cards present)");
  ok(cfg.commit === crypto.createHash("sha256").update(fs.readFileSync(RUN)).digest("hex"), "the fingerprint is the SHA-256 of the run file");
  r = await call(P, "GET", "/pay.js"); ok(r.status === 404, "the payment code is not served"); r = await call(P, "GET", "/server.js"); ok(r.status === 404, "nor is the server");

  r = await call(P, "POST", "/api/requiem/checkout", { qty: 1 }); ok(r.json.error && /18/.test(r.json.error) && seen.length === 0, "checkout needs the 18+ confirmation, and nothing is sent to Stripe without it");
  r = await call(P, "POST", "/api/requiem/checkout", { qty: 0, age: true }); ok(r.json.error && seen.length === 0, "a quantity of 0 is refused");
  r = await call(P, "POST", "/api/requiem/checkout", { qty: 4, age: true }); ok(r.json.error && /1 to 3/.test(r.json.error) && seen.length === 0, "more than 3 packs in one order is refused");
  r = await call(P, "POST", "/api/requiem/checkout", { qty: 2, age: true }); ok(r.json.url === "https://checkout.stripe.test/pay/cs_test_1", "a valid checkout returns Stripe's page to go to");
  const f = seen[0].form, h = seen[0].headers;
  ok(seen[0].path === "/v1/checkout/sessions" && f.mode === "payment" && f["line_items[0][quantity]"] === "2" && f["line_items[0][price_data][unit_amount]"] === "6500" && f["line_items[0][price_data][currency]"] === "usd", "it asks Stripe for a $65.00 x 2 one-time payment");
  ok(!Object.keys(f).some(k => /payment_method_types/.test(k)), "it does not restrict payment methods, so Apple Pay and Google Pay can show on Stripe's page");
  ok(f["shipping_address_collection[allowed_countries][0]"] === "US" && f["phone_number_collection[enabled]"] === "true", "Stripe collects a US shipping address and a phone number");
  ok(f.success_url === "https://example.test/?rq=paid&sid={CHECKOUT_SESSION_ID}#/limited" && f.cancel_url === "https://example.test/?rq=cancel#/limited", "buyers come back to the Requiem page");
  ok(f["metadata[kind]"] === "requiem" && f["metadata[qty]"] === "2" && +f.expires_at > Date.now() / 1000 + 1700 && +f.expires_at < Date.now() / 1000 + 3700, "the session carries what the webhook needs and expires in about 30 minutes");
  ok(h.authorization === "Bearer " + KEY && h["idempotency-key"] && /form/.test(h["content-type"]), "it authenticates with the secret key and sends an idempotency key");

  // holds: the last packs can't be sold twice
  r = await call(P, "POST", "/api/requiem/checkout", { qty: 3, age: true }); ok(r.json.url && r.json.url.endsWith("cs_test_2"), "a second buyer can hold 3 more (5 of 6 are now spoken for)");
  r = await call(P, "POST", "/api/requiem/checkout", { qty: 2, age: true }); ok(r.json.error && /Only 1 pack/.test(r.json.error) && seen.length === 2, "a third buyer can't hold 2: only 1 is available, and Stripe isn't called");
  failNext = true; r = await call(P, "POST", "/api/requiem/checkout", { qty: 1, age: true }); ok(r.json.error && /not been charged/.test(r.json.error) && !r.json.url, "if Stripe is down the buyer is told they have not been charged");
  r = await call(P, "POST", "/api/requiem/checkout", { qty: 1, age: true }); ok(r.json.url, "and the failed attempt didn't use up a pack (the last one can still be held)"); // cs_test_3, holds 6 of 6

  // webhooks: signature first
  r = await hook(P, done("cs_test_1", 2), { secret: "whsec_wrong" }); ok(r.status === 400, "a webhook signed with the wrong secret is refused");
  r = await hook(P, done("cs_test_1", 2), { t: Math.floor(Date.now() / 1000) - 3600 }); ok(r.status === 400, "an old signed webhook (an hour old) is refused");
  r = await call(P, "GET", "/api/requiem/order?sid=cs_test_1"); ok(r.json.pending === true, "nothing is assigned before a verified payment");
  r = await hook(P, done("cs_test_1", 2, { payment_status: "unpaid" })); ok(r.status === 200, "an unpaid session is acknowledged"); r = await call(P, "GET", "/api/requiem/order?sid=cs_test_1"); ok(r.json.pending === true, "and gives no packs");
  r = await hook(P, done("cs_other", 1, { metadata: { kind: "something else", qty: "1" } })); r = await call(P, "GET", "/api/requiem/order?sid=cs_other"); ok(r.json.pending === true, "a payment that isn't for Requiem is ignored");
  r = await hook(P, done("cs_test_1", 2)); ok(r.status === 200, "a verified payment is accepted");
  r = await call(P, "GET", "/api/requiem/order?sid=cs_test_1"); ok(r.json.ok && r.json.packs.join() === "1,2" && r.json.run === 6 && !r.json.cards && !JSON.stringify(r.json).includes("pallbearer"), "the buyer gets pack numbers 1 and 2 of 6, and the contents stay sealed");
  r = await hook(P, done("cs_test_1", 2)); r = await call(P, "GET", "/api/requiem/order?sid=cs_test_1"); ok(r.json.packs.join() === "1,2", "Stripe sending the same event again changes nothing");
  r = await hook(P, { id: "evt_e", type: "checkout.session.expired", data: { object: { id: "cs_test_2" } } }); r = await call(P, "POST", "/api/requiem/checkout", { qty: 3, age: true });
  ok(r.json.url && !r.json.error, "an expired session gives its held packs back");   // cs_test_4: holds cs_test_3's 1 + this 3 = 4, sold 2

  // selling out
  r = await hook(P, done("cs_test_4", 3)); r = await call(P, "GET", "/api/requiem/order?sid=cs_test_4"); ok(r.json.packs.join() === "3,4,5", "the next buyer gets the next packs, in the order payments arrive (3, 4, 5)");
  r = await hook(P, done("cs_test_3", 1)); r = await call(P, "GET", "/api/requiem/order?sid=cs_test_3"); ok(r.json.packs.join() === "6", "and the last buyer gets pack 6");
  r = await call(P, "GET", "/api/requiem/config"); ok(r.json.soldOut === true && r.json.open === false, "now it is sold out");
  r = await call(P, "POST", "/api/requiem/checkout", { qty: 1, age: true }); ok(r.json.error && /sold out/i.test(r.json.error), "and checkout refuses");
  r = await hook(P, done("cs_late", 2)); r = await call(P, "GET", "/api/requiem/order?sid=cs_late"); ok(r.json.ok && r.json.packs.length === 0 && r.json.short === true, "a payment that somehow arrives after the last pack is recorded as short, to refund in Stripe, and gets no pack");

  // the admin view
  r = await call(P, "GET", "/api/requiem/orders?token=tok"); const o = r.json;
  ok(o.sold === 6 && o.run === 6 && o.orders.length === 4, "the admin list has the orders (6 of 6 packs sold)");
  const byS = Object.fromEntries(o.orders.map(x => [x.sid, x]));
  ok(byS.cs_test_1.packs.map(p => p.no).join() === "1,2" && JSON.stringify(byS.cs_test_1.packs[0].cards) === JSON.stringify(run.packs[0]) && JSON.stringify(byS.cs_test_4.packs[2].cards) === JSON.stringify(run.packs[4]), "it lists exactly which cards are in each buyer's packs, as in the run file");
  ok(!/address|email|phone|name"/i.test(JSON.stringify(o.orders)) && byS.cs_test_1.amount === 13000, "it holds no names, addresses or contact details, only the amount");

  // the run file can't change once selling has begun
  const orig = fs.readFileSync(RUN); fs.writeFileSync(RUN, orig.toString() + " "); r = await call(P, "GET", "/api/requiem/orders?token=tok"); ok(r.json.why.some(w => /changed after sales began/.test(w)), "if the run file is altered after sales begin, the sale shuts and says why"); fs.writeFileSync(RUN, orig);
  // orders survive a restart
  await s.kill(); s = await start(open, "on.json"); r = await call(s.port, "GET", "/api/requiem/order?sid=cs_test_4"); ok(r.json.packs && r.json.packs.join() === "3,4,5", "orders are still there after the server restarts");
  await s.kill();

  // ---- you always keep more than it costs: nothing is sold at a loss, and nothing in the code can pay a player
  {
    const econ = async (env, name) => { const t = await start(Object.assign({}, open, env), name); const a = (await call(t.port, "GET", "/api/requiem/orders?token=tok")).json, c = (await call(t.port, "GET", "/api/requiem/config")).json; await t.kill(); return { a, c }; };
    let e = await econ({}, "e1.json"); ok(e.c.open === true && e.a.economics.fee === 219 && e.a.economics.net === 6500 - 219 - 1200 && e.a.economics.marginPct === 78.2, "with a cost of $12.00 a pack you keep $50.81 of $65.00 (78.2%) after Stripe's $2.19; the admin view shows it");
    e = await econ({ REQUIEM_UNIT_COST_CENTS: "" }, "e2.json"); ok(e.c.open === false && e.a.why.some(w => /REQUIEM_UNIT_COST_CENTS is not set/.test(w)), "the Requiem sale won't open until you say what a pack costs you");
    e = await econ({ REQUIEM_UNIT_COST_CENTS: "6000" }, "e3.json"); ok(e.c.open === false && e.a.why.some(w => /under your minimum of 20%/.test(w)), "at a cost of $60.00 a pack the sale stays closed (you'd keep under 5%)");
    e = await econ({ REQUIEM_UNIT_COST_CENTS: "5000" }, "e4.json"); ok(e.c.open === false && e.a.economics.marginPct < 20, "just under the 20% margin it is closed (19.7%)");
    e = await econ({ REQUIEM_UNIT_COST_CENTS: "4900" }, "e5.json"); ok(e.c.open === true && e.a.economics.marginPct > 20, "just over it, open (21.2%)");
    e = await econ({ REQUIEM_UNIT_COST_CENTS: "9000" }, "e6.json"); ok(e.c.open === false && e.a.economics.net < 0, "a cost above the price (a loss on every pack) is closed");
    e = await econ({ REQUIEM_MIN_MARGIN_PCT: "90" }, "e7.json"); ok(e.c.open === false, "and you can raise the minimum margin (at 90% this one is closed)");
    const shopEcon = async (env, name) => { const t = await start(Object.assign({}, open, { REQUIEM_OPEN: "0", SHOP_OPEN: "1" }, env), name); const a = (await call(t.port, "GET", "/api/shop/orders?token=tok")).json, c = (await call(t.port, "GET", "/api/shop/config")).json; await t.kill(); return { a, c }; };
    let h = await shopEcon({}, "h1.json"); ok(h.a.economics.fp.fee === 33 && h.a.economics.fp.netPct === 67 && h.a.economics.ms.fee === 39 && h.a.economics.ms.netPct === 87 && h.c.prices.fp === 100, "a $1.00 pack keeps 67 cents after Stripe's 33 cent fee, a $3.00 pack keeps $2.61 (87%)");
    h = await shopEcon({ SHOP_PRICES: '{"fp":100,"ms":300,"xx":50}' }, "h2.json"); ok(!h.c.prices.xx && h.c.prices.fp === 100 && h.a.economics.xx.offered === false, "a 50 cent pack (Stripe would keep 62%) is not offered, and the others still are");
    h = await shopEcon({ SHOP_MIN_NET_PCT: "70" }, "h3.json"); ok(h.c.prices.fp === undefined && h.c.prices.ms === 300, "with a 70% minimum the $1.00 pack (67%) is dropped and the $3.00 pack stays");
    h = await shopEcon({ SHOP_MIN_NET_PCT: "95" }, "h4.json"); ok(h.c.open === false && h.a.why.some(w => /no pack is offered/.test(w)), "and if no price clears the minimum the shop is closed");
    const src = fs.readFileSync(path.join(__dirname, "pay.js"), "utf8") + fs.readFileSync(path.join(__dirname, "server.js"), "utf8");
    const calls = [...src.matchAll(/stripe\("(GET|POST)", "([^"]+)"/g)].map(m => m[2]);
    ok(calls.length >= 2 && calls.every(p => /^\/v1\/checkout\/sessions/.test(p)), "the server's only calls to Stripe are about Checkout sessions: start one, or ask whether one was paid (" + calls.length + " places, all /v1/checkout/sessions)");
    ok(!/\/v1\/(payouts|transfers|refunds|topups|treasury|issuing|payment_intents|charges|customers|subscriptions|balance)/.test(src), "nothing in the code can send money to anyone: no payouts, transfers, refunds or cash-out of any kind");
  }

  // ---- digital packs (the sale of the physical Requiem pack is off in this server: the two are independent)
  const SHOP = Object.assign({}, open, { REQUIEM_OPEN: "0", SHOP_OPEN: "1" });
  s = await start(Object.assign({}, open, { }), "noshop.json"); r = await call(s.port, "GET", "/api/shop/config"); ok(r.json.open === false, "digital packs are closed unless SHOP_OPEN=1"); await s.kill();
  s = await start(SHOP, "shop.json"); const Q = s.port, uid = crypto.randomBytes(8).toString("hex"), uid2 = crypto.randomBytes(8).toString("hex"); seen.length = 0;
  r = await call(Q, "GET", "/api/shop/config"); ok(r.json.open === true && r.json.prices.fp === 100 && r.json.prices.ms === 300 && r.json.maxQty === 10 && r.json.cap === 2500 && r.json.terms === "https://example.test/terms", "with SHOP_OPEN=1 digital packs are on: First Print $1.00, Moonshot $3.00, up to 10 at a time, a $25.00 daily limit");
  r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "fp", qty: 1, age: true }); ok(r.json.error && /Open the game/.test(r.json.error) && seen.length === 0, "a player the server has never met can't buy (open the game first)");
  await call(Q, "POST", "/api/hello", { uid }); await call(Q, "POST", "/api/hello", { uid: uid2 });
  r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "fp", qty: 1 }); ok(r.json.error && /18/.test(r.json.error) && seen.length === 0, "the 18+ confirmation is required, and Stripe isn't called without it");
  r = await call(Q, "POST", "/api/shop/checkout", { uid, qty: 1, age: true }); ok(r.json.error && /Choose a pack/.test(r.json.error) && seen.length === 0, "a pack must be chosen"); r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "zz", qty: 1, age: true }); ok(r.json.error && seen.length === 0, "an unknown pack is refused");
  r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "fp", qty: 0, age: true }); ok(r.json.error && seen.length === 0, "0 packs is refused"); r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "fp", qty: 11, age: true }); ok(r.json.error && /1 to 10/.test(r.json.error) && seen.length === 0, "11 packs is refused");
  r = await call(Q, "POST", "/api/shop/checkout", { uid: "nothex!", pack: "fp", qty: 1, age: true }); ok(r.json.error && seen.length === 0, "a malformed player id is refused");
  r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "fp", qty: 3, age: true }); const sid1 = r.json.url && r.json.url.split("/").pop(); ok(/cs_test_/.test(sid1 || ""), "a valid purchase returns Stripe's page");
  let g = seen[0].form; ok(g.mode === "payment" && g["line_items[0][quantity]"] === "3" && g["line_items[0][price_data][unit_amount]"] === "100" && g["line_items[0][price_data][currency]"] === "usd" && /First Print/.test(g["line_items[0][price_data][product_data][name]"]), "3 First Print packs: 3 x $1.00");
  ok(g["metadata[kind]"] === "packs" && g["metadata[uid]"] === uid && g["metadata[pack]"] === "fp" && g["metadata[qty]"] === "3" && g.client_reference_id === uid, "the session carries the player, pack and quantity for the webhook");
  ok(!Object.keys(g).some(k => /shipping_address|phone_number|payment_method_types/.test(k)) && g.success_url === "https://example.test/?pk=paid&sid={CHECKOUT_SESSION_ID}" && g.cancel_url === "https://example.test/?pk=cancel", "digital: no address or phone is collected, no payment method is excluded, and buyers return to the game");
  // the daily limit counts payments still open: 3 First Print = $3.00 held
  r = await call(Q, "GET", "/api/shop/config?uid=" + uid); ok(r.json.spentToday === 300, "money still being paid counts toward today's limit ($3.00)");
  r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "ms", qty: 10, age: true }); ok(r.json.error && /over today's limit of \$25\.00/.test(r.json.error) && /\$22\.00 more/.test(r.json.error), "10 Moonshot ($30.00) is over the limit, and it says how much is left ($22.00)");
  r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "ms", qty: 7, age: true }); const sid2 = r.json.url && r.json.url.split("/").pop(); g = seen[1].form; ok(/cs_test_/.test(sid2 || "") && g["line_items[0][price_data][unit_amount]"] === "300" && /Moonshot/.test(g["line_items[0][price_data][product_data][name]"]) && g["metadata[pack]"] === "ms", "7 Moonshot at $3.00 ($21.00, $24.00 of $25.00 today) is allowed");
  r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "fp", qty: 2, age: true }); ok(r.json.error && /limit/.test(r.json.error), "and 2 more First Print is not");
  r = await call(Q, "POST", "/api/shop/checkout", { uid: uid2, pack: "ms", qty: 8, age: true }); const sid3 = r.json.url && r.json.url.split("/").pop(); ok(/cs_test_/.test(sid3 || ""), "another player has their own limit");
  r = await hook(Q, { id: "evt_x", type: "checkout.session.expired", data: { object: { id: sid2 } } }); r = await call(Q, "POST", "/api/shop/checkout", { uid, pack: "fp", qty: 2, age: true }); ok(r.json.url, "an expired payment page gives its part of the limit back");
  // crediting
  r = await call(Q, "POST", "/api/hello", { uid }); ok(JSON.stringify(r.json.paid) === "{}", "nothing is credited before a verified payment");
  const ev = (sid, u, pack, qty, cents, extra) => done(sid, qty, Object.assign({ amount_total: cents, metadata: { kind: "packs", uid: u, pack, qty: String(qty) } }, extra || {}));
  r = await hook(Q, ev(sid1, uid, "fp", 3, 300), { secret: "whsec_wrong" }); ok(r.status === 400, "a payment signed with the wrong secret credits nothing");
  r = await hook(Q, ev(sid1, uid, "fp", 3, 300, { payment_status: "unpaid" })); r = await call(Q, "POST", "/api/hello", { uid }); ok(JSON.stringify(r.json.paid) === "{}", "an unpaid session credits nothing");
  r = await hook(Q, ev(sid1, uid, "fp", 3, 300)); ok(r.status === 200, "a verified payment is accepted");
  r = await call(Q, "POST", "/api/hello", { uid }); ok(r.json.paid.fp === 3 && !r.json.paid.ms, "the player's running total of bought First Print packs is now 3");
  r = await hook(Q, ev(sid1, uid, "fp", 3, 300)); r = await call(Q, "POST", "/api/hello", { uid }); ok(r.json.paid.fp === 3, "the same event again changes nothing");
  r = await call(Q, "GET", "/api/shop/order?sid=" + sid1); ok(r.json.ok && r.json.qty === 3 && r.json.pack === "fp" && !r.json.short, "the page can ask whether the payment has been credited");
  r = await call(Q, "GET", "/api/shop/order?sid=cs_nope"); ok(r.json.pending === true, "and gets 'pending' for one that hasn't");
  r = await call(Q, "POST", "/api/hello", { uid: uid2 }); ok(JSON.stringify(r.json.paid) === "{}", "another player's totals are untouched");
  r = await hook(Q, ev(sid3, uid2, "ms", 8, 2400)); r = await call(Q, "POST", "/api/hello", { uid: uid2 }); ok(r.json.paid.ms === 8 && !r.json.paid.fp, "Moonshot packs are counted on their own (8)");
  r = await call(Q, "GET", "/api/shop/config?uid=" + uid); ok(r.json.spentToday === 300 + 200, "paid money counts toward the limit too ($3.00 paid + $2.00 still open)");
  const ghost = crypto.randomBytes(8).toString("hex"); r = await hook(Q, ev("cs_ghost", ghost, "fp", 2, 200)); r = await call(Q, "GET", "/api/shop/order?sid=cs_ghost"); ok(r.json.ok && r.json.short === true, "a payment for a player that can't be found is marked short, to refund in Stripe");
  r = await hook(Q, ev("cs_oddpack", uid, "zz!", 1, 100)); r = await call(Q, "GET", "/api/shop/order?sid=cs_oddpack"); const r2 = await call(Q, "POST", "/api/hello", { uid }); ok(r.json.short === true && r2.json.paid.fp === 3 && !r2.json.paid["zz!"], "a payment naming a pack that doesn't exist credits nothing and is marked short");
  r = await call(Q, "GET", "/api/shop/orders"); ok(r.status === 403, "the order list needs the admin token"); r = await call(Q, "GET", "/api/shop/orders?token=tok"); ok(r.json.packs === 11 && r.json.cents === 300 + 2400 + 200 + 100 && r.json.orders.length === 4 && r.json.orders.every(o => o.player.length === 8) && !/address|email|phone/i.test(JSON.stringify(r.json)), "the admin list has the orders and the packs credited (3 First Print + 8 Moonshot), with no personal details");
  r = await call(Q, "GET", "/api/requiem/config"); ok(r.json.open === false, "selling digital packs doesn't open the Requiem sale");
  // a payment the webhook never reported: the server asks Stripe itself
  const uid3 = crypto.randomBytes(8).toString("hex"); await call(Q, "POST", "/api/hello", { uid: uid3 });
  r = await call(Q, "POST", "/api/shop/checkout", { uid: uid3, pack: "fp", qty: 2, age: true }); const sid4 = r.json.url.split("/").pop();
  r = await call(Q, "GET", "/api/shop/order?sid=" + sid4); ok(r.json.pending === true, "a session Stripe says is not paid is not credited (still pending)");
  sessions[sid4].payment_status = "paid"; reads.length = 0;
  r = await call(Q, "GET", "/api/shop/order?sid=" + sid4); ok(r.json.ok && r.json.qty === 2 && reads.some(p => p === "/v1/checkout/sessions/" + sid4), "once Stripe says it is paid, the page's check credits it with no webhook at all (the server asked Stripe)");
  r = await call(Q, "POST", "/api/hello", { uid: uid3 }); ok(r.json.paid.fp === 2, "and the packs are in the player's total (2)");
  r = await call(Q, "GET", "/api/shop/order?sid=" + sid4); r = await call(Q, "POST", "/api/hello", { uid: uid3 }); ok(r.json.paid.fp === 2, "asking again never credits twice");
  r = await call(Q, "POST", "/api/shop/checkout", { uid: uid3, pack: "ms", qty: 1, age: true }); const sid5 = r.json.url.split("/").pop(); sessions[sid5].payment_status = "paid";
  await s.kill(); s = await start(SHOP, "shop.json"); await new Promise(r => setTimeout(r, 6000));
  r = await call(s.port, "POST", "/api/hello", { uid: uid3 }); ok(r.json.paid.ms === 1 && r.json.paid.fp === 2, "a payment made while the webhook was broken or the server was down is found when the server starts (sweep of recent sessions)");
  await s.kill(); s = await start(SHOP, "shop.json"); r = await call(s.port, "POST", "/api/hello", { uid }); ok(r.json.paid.fp === 3, "credited packs survive a restart");
  await s.kill(); s = await start(Object.assign({}, SHOP, { SHOP_PRICES: '{"fp":150}' }), "shop2.json"); r = await call(s.port, "GET", "/api/shop/config"); ok(r.json.prices.fp === 150 && !r.json.prices.ms, "SHOP_PRICES sets the prices (here only First Print, $1.50)");
  await s.kill(); s = await start(Object.assign({}, SHOP, { SHOP_PRICES: '{"fp":10}' }), "shop3.json"); r = await call(s.port, "GET", "/api/shop/config"); ok(r.json.open === false, "a price below Stripe's 50 cent minimum is not accepted, so the shop stays closed"); await s.kill();

  // the run assembler: the counts it makes are the odds in the data file
  const big = path.join(tmp, "big"); execFileSync("python3", [path.join(__dirname, "design-concepts", "requiem", "requiem_run.py"), "--packs", "2500", "--out", big, "--seed", "t"], { stdio: "ignore" });
  const pub = JSON.parse(fs.readFileSync(path.join(big, "requiem-run.public.json"), "utf8")), bigRun = JSON.parse(fs.readFileSync(path.join(big, "requiem-run.json"), "utf8"));
  ok(bigRun.packs.length === 2500 && pub.counts.seraph === 1 && pub.counts.orrery === 16 && pub.counts.halation === 605 && Math.abs(pub.counts.witness - 132.5) <= 1 && pub.counts.pallbearer + pub.counts.vigil + pub.counts.halation + pub.counts.witness + pub.counts.orrery + pub.counts.seraph === 7500, "a 2,500-pack run has 1 Seraph, 16 Orrery, 605 Halation, 132 or 133 Witness and 7,500 cards in all");
  ok(bigRun.packs.every(p => ["pallbearer", "vigil"].includes(p[0]) && ["pallbearer", "vigil", "halation", "witness"].includes(p[1])), "every pack follows the slot rules (card 1 is Pallbearer or Vigil; card 2 is never Orrery or Seraph)");
  ok(pub.commit === crypto.createHash("sha256").update(fs.readFileSync(path.join(big, "requiem-run.json"))).digest("hex"), "the published fingerprint matches the file");

  const outTxt = execFileSync("python3", [path.join(__dirname, "design-concepts", "requiem", "requiem_run.py"), "--packs", "2500", "--unit-cost", "1200", "--out", path.join(tmp, "eco"), "--seed", "t"]).toString();
  ok(/you keep \$50\.81 \(78\.2%\)/.test(outTxt) && /you keep \$127,025\.00/.test(outTxt) && /98\.6%/.test(outTxt), "the run assembler prints what you keep ($50.81 a pack, $127,025 over 2,500 packs) and how the planned worth compares with what buyers pay (98.6%)");
  stripe.close(); fs.rmSync(tmp, { recursive: true, force: true });
  console.log(fails ? `${fails} FAILED` : "all passed"); process.exit(fails ? 1 : 0);
})().catch(e => { console.error("CRASH", e); process.exit(1); });
