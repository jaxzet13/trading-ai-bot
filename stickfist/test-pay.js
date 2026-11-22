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
const seen = []; let n = 0, failNext = false;
const stripe = http.createServer((req, res) => {
  let b = ""; req.on("data", c => b += c); req.on("end", () => {
    if (failNext) { failNext = false; res.writeHead(500, { "content-type": "application/json" }); return res.end(JSON.stringify({ error: { message: "boom" } })); }
    const id = "cs_test_" + (++n); seen.push({ path: req.url, headers: req.headers, form: Object.fromEntries(new URLSearchParams(b)) });
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
  const open = { REQUIEM_OPEN: "1", STRIPE_SECRET_KEY: KEY, STRIPE_WEBHOOK_SECRET: WH, PUBLIC_URL: "https://example.test", REQUIEM_TERMS_URL: "https://example.test/terms", STRIPE_API_BASE: "http://127.0.0.1:" + SP };

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

  // the run assembler: the counts it makes are the odds in the data file
  const big = path.join(tmp, "big"); execFileSync("python3", [path.join(__dirname, "design-concepts", "requiem", "requiem_run.py"), "--packs", "2500", "--out", big, "--seed", "t"], { stdio: "ignore" });
  const pub = JSON.parse(fs.readFileSync(path.join(big, "requiem-run.public.json"), "utf8")), bigRun = JSON.parse(fs.readFileSync(path.join(big, "requiem-run.json"), "utf8"));
  ok(bigRun.packs.length === 2500 && pub.counts.seraph === 1 && pub.counts.orrery === 16 && pub.counts.halation === 605 && Math.abs(pub.counts.witness - 132.5) <= 1 && pub.counts.pallbearer + pub.counts.vigil + pub.counts.halation + pub.counts.witness + pub.counts.orrery + pub.counts.seraph === 7500, "a 2,500-pack run has 1 Seraph, 16 Orrery, 605 Halation, 132 or 133 Witness and 7,500 cards in all");
  ok(bigRun.packs.every(p => ["pallbearer", "vigil"].includes(p[0]) && ["pallbearer", "vigil", "halation", "witness"].includes(p[1])), "every pack follows the slot rules (card 1 is Pallbearer or Vigil; card 2 is never Orrery or Seraph)");
  ok(pub.commit === crypto.createHash("sha256").update(fs.readFileSync(path.join(big, "requiem-run.json"))).digest("hex"), "the published fingerprint matches the file");

  stripe.close(); fs.rmSync(tmp, { recursive: true, force: true });
  console.log(fails ? `${fails} FAILED` : "all passed"); process.exit(fails ? 1 : 0);
})().catch(e => { console.error("CRASH", e); process.exit(1); });
