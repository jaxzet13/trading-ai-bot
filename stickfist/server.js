#!/usr/bin/env node
/* STIXX beta server. No dependencies: Node 18 or newer.

     node server.js                 serves the game on http://localhost:8080 and the API under /api

   It does two jobs the page cannot do for itself, because a page cannot be trusted to count its own rewards:
     1. invites: who invited whom, and how many free packs each person has earned
     2. provably fair packs: it holds a secret seed per player, shows its SHA-256 hash first, and answers each pack with HMAC-SHA256(seed, "clientSeed:nonce")

   What it stores about a player: a random id, an invite code, who invited them, counters, the days they visited, a hash of their network address (never the address), and the seed.
   No names, emails, addresses or card details are kept by this program. The one real-money feature, the Requiem checkout in pay.js (off unless you set it up), sends
   buyers to Stripe to pay and keeps only a Stripe session id, a pack number and an amount per order.

   Settings, all optional (environment variables):
     PORT=8080          DATA_FILE=./data/stixx.json     STATIC_DIR=.   (where index.html and cards/ are)
     TRUST_PROXY=1      read the visitor's address from X-Forwarded-For (set this behind a proxy or CDN)
     ADMIN_TOKEN=...    lets you read /api/stats?token=...
     BLOCKED_CODES=A,B  extra words that can't be used in a vanity invite code
     CORS_ORIGIN=*      who may call the API from another site (default: any)
*/
"use strict";
const http = require("http"), fs = require("fs"), path = require("path"), crypto = require("crypto"), zlib = require("zlib");

const PORT = +process.env.PORT || 8080, DATA_FILE = path.resolve(process.env.DATA_FILE || path.join(__dirname, "data", "stixx.json")), STATIC = path.resolve(process.env.STATIC_DIR || __dirname);
const TRUST_PROXY = process.env.TRUST_PROXY === "1", ADMIN_TOKEN = process.env.ADMIN_TOKEN || "", CORS = process.env.CORS_ORIGIN || "*";
const MAX_FRIENDS = 30, BONUS_AT = { 5: 2, 10: 3, 25: 5 }, SAME_NET_MAX = 2, HELLOS_PER_HOUR = 40, CALLS_PER_MIN = 240;
const ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const RESERVED = new Set(["STIXX", "ADMIN", "ROOT", "TEST", "NULL", "FREE", "SUPPORT", "MOD", "STAFF", "OFFICIAL", "TEAM", "HELP", "API", "NONE", "UNDEFINED"].concat((process.env.BLOCKED_CODES || "").toUpperCase().split(",").filter(Boolean)));
const OFFENSIVE = ["FUCK", "SHIT", "CUNT", "NAZI", "RAPE", "NIGGER", "NIGGA", "FAGGOT", "RETARD", "HITLER", "KKK"];

/* ---- the store: one JSON file, written a moment after every change, swapped in atomically ---- */
let db = { users: {}, codes: {}, salt: crypto.randomBytes(16).toString("hex"), day: {} };
try { db = Object.assign(db, JSON.parse(fs.readFileSync(DATA_FILE, "utf8"))); } catch (e) { /* first run */ }
let dirty = false, writing = false;
function flush() {
  if (writing || !dirty) return; dirty = false; writing = true;
  fs.mkdirSync(path.dirname(DATA_FILE), { recursive: true }); const tmp = DATA_FILE + "." + process.pid + ".tmp";
  fs.writeFile(tmp, JSON.stringify(db), err => { if (!err) fs.rename(tmp, DATA_FILE, () => { writing = false; if (dirty) setTimeout(flush, 50); }); else { writing = false; dirty = true; console.error("could not save:", err.message); } });
}
const touch = () => { dirty = true; setTimeout(flush, 250); };
// for things that must not be lost (a paid order): write now, not a moment from now
function saveNow() { try { fs.mkdirSync(path.dirname(DATA_FILE), { recursive: true }); const tmp = DATA_FILE + "." + process.pid + ".sync.tmp"; fs.writeFileSync(tmp, JSON.stringify(db)); fs.renameSync(tmp, DATA_FILE); dirty = false; } catch (e) { console.error("could not save:", e.message); dirty = true; } }
process.on("SIGTERM", () => { dirty = true; try { fs.mkdirSync(path.dirname(DATA_FILE), { recursive: true }); fs.writeFileSync(DATA_FILE, JSON.stringify(db)); } catch (e) {} process.exit(0); });
process.on("SIGINT", () => process.emit("SIGTERM"));

/* ---- helpers ---- */
const sha = s => crypto.createHash("sha256").update(s).digest("hex");
const validUid = u => typeof u === "string" && /^[a-f0-9]{16,64}$/.test(u);
const normCode = c => String(c || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16);
const newCode = () => { for (;;) { let c = ""; for (let i = 0; i < 6; i++) c += ALPHA[crypto.randomInt(ALPHA.length)]; if (!db.codes[c] && !RESERVED.has(c)) return c; } };
const ipOf = req => { let ip = req.socket.remoteAddress || ""; if (TRUST_PROXY) { const f = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim(); if (f) ip = f; } return sha(ip + db.salt).slice(0, 16); };
const dayKey = () => new Date().toISOString().slice(0, 10);
const hits = new Map();                                                                    // address hash -> [timestamps] for simple rate limits
function limited(key, max, ms) { const t = Date.now(), a = (hits.get(key) || []).filter(x => t - x < ms); a.push(t); hits.set(key, a); return a.length > max; }
setInterval(() => { const t = Date.now(); for (const [k, a] of hits) { const f = a.filter(x => t - x < 3.6e6); f.length ? hits.set(k, f) : hits.delete(k); } }, 600000).unref();
const publicInfo = u => ({ paid: u.paidTotal || 0, code: u.code, joined: u.joined || 0, invited: u.invited || 0, earned: u.earned || 0, credits: u.credits || 0, activated: !!u.active, by: u.by || "", cap: MAX_FRIENDS, fair: { commit: sha(u.seed), nonce: u.nonce, epoch: u.epoch } });

function getUser(uid, ip, create, ref) {
  let u = db.users[uid]; if (u || !create) return u;
  u = db.users[uid] = { code: newCode(), at: Date.now(), net: ip, by: "", active: 0, credits: 0, welcome: 0, joined: 0, invited: 0, earned: 0, credited: 0, vanityAt: 0, seed: crypto.randomBytes(32).toString("hex"), nonce: 0, epoch: 1 };
  db.codes[u.code] = uid; const d = db.day[dayKey()] = db.day[dayKey()] || { new: 0, ref: 0, active: 0, refActive: 0 }; d.new++;
  const r = ref && db.codes[normCode(ref)] ? db.users[db.codes[normCode(ref)]] : null;
  if (r && db.codes[normCode(ref)] !== uid && (r.joined || 0) < 500) { u.by = r.code; u.welcome = 1; u.credits += 1; r.joined = (r.joined || 0) + 1; d.ref++; }       // the friend's welcome pack
  return u;
}

/* ---- the API ---- */
const routes = {
  "GET /api/health": () => ({ ok: true, v: 1 }),
  // who am I: creates the player on first contact, and applies the invite code they arrived with
  "POST /api/hello": (b, ip) => {
    if (!validUid(b.uid)) return [400, { error: "bad id" }];
    if (!db.users[b.uid] && limited("hello:" + ip, HELLOS_PER_HOUR, 3.6e6)) return [429, { error: "slow down" }];
    const u = getUser(b.uid, ip, true, b.ref), k = dayKey();
    if (u.last !== k) { u.last = k; (u.days = u.days || []).push(k); if (u.days.length > 60) u.days.shift(); const d = db.day[k] = db.day[k] || { new: 0, ref: 0, active: 0, refActive: 0 }; d.dau = (d.dau || 0) + 1; touch(); }
    return publicInfo(u);
  },
  // anonymous counters: how often a clip is made, saved or shared, and an invite link copied or shared. A name and a count, nothing about the player.
  "POST /api/event": (b, ip) => {
    const u = getUser(b.uid, ip, false); if (!u) return [404, { error: "unknown" }]; const name = String(b.name || ""); if (!/^(clip|clipSave|clipShare|inviteCopy|inviteShare)$/.test(name)) return [400, { error: "unknown event" }];
    const d = db.day[dayKey()] = db.day[dayKey()] || { new: 0, ref: 0, active: 0, refActive: 0 }; d.ev = d.ev || {}; d.ev[name] = (d.ev[name] || 0) + 1; touch(); return { ok: true };
  },
  // the player opened their first pack: the friend who invited them earns a pack
  "POST /api/active": (b, ip) => {
    const u = getUser(b.uid, ip, false); if (!u) return [404, { error: "unknown" }];
    if (!u.active) {
      u.active = Date.now(); const d = db.day[dayKey()] = db.day[dayKey()] || { new: 0, ref: 0, active: 0, refActive: 0 }; d.active++;
      const r = u.by && db.users[db.codes[u.by]];
      if (r && !u.credited && (r.invited || 0) < MAX_FRIENDS) {
        const sameNet = Object.values(db.users).filter(x => x.by === r.code && x.credited && x.net === u.net).length;           // one household can't mint endless rewards
        if (u.net !== r.net || sameNet < SAME_NET_MAX) {
          u.credited = 1; r.invited = (r.invited || 0) + 1; let g = 1 + (BONUS_AT[r.invited] || 0); r.credits += g; r.earned = (r.earned || 0) + g; r.pending = (r.pending || 0) + 1; d.refActive++;
        }
      }
      touch();
    }
    return { ok: true };
  },
  // collect free packs that are waiting; the server's count is the one that matters
  "POST /api/claim": (b, ip) => {
    const u = getUser(b.uid, ip, false); if (!u) return [404, { error: "unknown" }];
    const packs = u.credits || 0, welcome = u.welcome ? 1 : 0, friends = u.pending || 0; u.credits = 0; u.welcome = 0; u.pending = 0; if (packs) touch();
    return { packs, welcome, friends: Math.max(0, Math.min(friends, packs - welcome)) };
  },
  // a creator picks their own code
  "POST /api/vanity": (b, ip) => {
    const u = getUser(b.uid, ip, false); if (!u) return [404, { error: "unknown" }]; const c = normCode(b.code);
    if (!u.active) return { error: "Open your first pack, then pick a code." };
    if (c.length < 3 || c.length > 16) return { error: "Use 3 to 16 letters or numbers." };
    if (c === u.code) return { ok: true, code: c, info: publicInfo(u) };
    if (Date.now() - (u.vanityAt || 0) < 864e5) return { error: "You can change your code once a day." };
    if (RESERVED.has(c) || OFFENSIVE.some(w => c.includes(w))) return { error: "That one isn't available." };
    if (db.codes[c]) return { error: "Someone already has that one." };
    delete db.codes[u.code]; db.codes[c] = b.uid; for (const x of Object.values(db.users)) if (x.by === u.code) x.by = c; u.code = c; u.vanityAt = Date.now(); touch();
    return { ok: true, code: c, info: publicInfo(u) };
  },
  "GET /api/ref": (_b, _ip, q) => ({ valid: !!db.codes[normCode(q.get("code"))] }),
  // provably fair draws
  "POST /api/fair/draw": (b, ip) => {
    const u = getUser(b.uid, ip, false); if (!u) return [404, { error: "unknown" }]; const cs = String(b.cs || "").replace(/[^\w.-]/g, "").slice(0, 24); if (!cs) return [400, { error: "no client seed" }];
    const n = u.nonce++, digest = crypto.createHmac("sha256", u.seed).update(`${cs}:${n}`).digest("hex"); touch();
    return { nonce: n, digest, commit: sha(u.seed), epoch: u.epoch };
  },
  "POST /api/fair/rotate": (b, ip) => {
    const u = getUser(b.uid, ip, false); if (!u) return [404, { error: "unknown" }];
    const old = u.seed, epoch = u.epoch; u.seed = crypto.randomBytes(32).toString("hex"); u.nonce = 0; u.epoch++; touch();
    return { seed: old, epoch, next: u.epoch, commit: sha(u.seed) };
  },
  "GET /api/stats": (_b, _ip, q) => {
    if (!ADMIN_TOKEN || q.get("token") !== ADMIN_TOKEN) return [403, { error: "no" }];
    const us = Object.values(db.users), days = Object.keys(db.day).sort().slice(-30).map(k => Object.assign({ day: k }, db.day[k]));
    const joined = us.length, active = us.filter(u => u.active).length, referred = us.filter(u => u.by).length, refActive = us.filter(u => u.by && u.active).length;
    const addDays = (k, n) => new Date(Date.parse(k + "T00:00:00Z") + n * 864e5).toISOString().slice(0, 10), today = dayKey(), ret = n => { const el = us.filter(u => u.days && u.days.length && addDays(u.days[0], n) <= addDays(today, -1)); return el.length ? +(el.filter(u => u.days.includes(addDays(u.days[0], n))).length / el.length).toFixed(3) : null; };
    const events = {}; for (const k of Object.keys(db.day)) for (const [n, c] of Object.entries(db.day[k].ev || {})) events[n] = (events[n] || 0) + c;
    // k-factor: new players who opened a pack through an invite, per player who opened a pack. Above 1 means invites alone make the game grow.
    return { joined, active, referred, refActive, kFactor: active ? +(refActive / active).toFixed(3) : 0, activation: joined ? +(active / joined).toFixed(3) : 0, retention: { d1: ret(1), d7: ret(7) }, events, shareRate: active ? +(((events.clipShare || 0) + (events.inviteShare || 0) + (events.inviteCopy || 0)) / active).toFixed(3) : 0, days };
  },
};

/* ---- the Requiem checkout (Stripe), off unless configured: see pay.js ---- */
const pay = require("./pay.js")({ db: () => db, touch, saveNow, limited, adminToken: ADMIN_TOKEN, dataDir: path.dirname(DATA_FILE) });
Object.assign(routes, pay.routes);

/* ---- web server ---- */
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".mp4": "video/mp4", ".webp": "image/webp", ".webmanifest": "application/manifest+json", ".txt": "text/plain; charset=utf-8" };
const gz = new Map();
function send(res, code, body, type, extra) { const h = Object.assign({ "content-type": type, "x-content-type-options": "nosniff" }, extra || {}); res.writeHead(code, h); res.end(body); }
function json(res, code, obj) { send(res, code, JSON.stringify(obj), "application/json", { "cache-control": "no-store", "access-control-allow-origin": CORS }); }
function serveStatic(req, res, url) {
  let p = decodeURIComponent(url.pathname); if (p === "/" || p === "") p = "/index.html"; const file = path.join(STATIC, path.normalize(p));
  if (!file.startsWith(STATIC + path.sep) || /(^|[\\/])(server\.js|pay\.js|data|\.git|src|node_modules)([\\/]|$)/.test(path.relative(STATIC, file)) || /\.(py|md|sh|json)$/.test(file) && !/manifest\.json$/.test(file)) return send(res, 404, "Not found", "text/plain");
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) return send(res, 404, "Not found", "text/plain");
    const ext = path.extname(file).toLowerCase(), type = MIME[ext] || "application/octet-stream", cache = ext === ".html" ? "no-cache" : "public, max-age=86400";
    const wantsGz = /\bgzip\b/.test(req.headers["accept-encoding"] || "") && /^(\.html|\.js|\.css|\.svg|\.json)$/.test(ext);
    if (wantsGz) { const k = file + st.mtimeMs; if (!gz.has(k)) gz.set(k, zlib.gzipSync(fs.readFileSync(file))); return send(res, 200, gz.get(k), type, { "content-encoding": "gzip", "cache-control": cache, vary: "accept-encoding" }); }
    res.writeHead(200, { "content-type": type, "content-length": st.size, "cache-control": cache, "x-content-type-options": "nosniff" }); if (req.method === "HEAD") return res.end(); fs.createReadStream(file).pipe(res);
  });
}
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x"), key = req.method + " " + url.pathname;
  if (key === "POST /api/stripe/webhook") return pay.webhook(req, res, send);            // Stripe's calls: the raw body is needed to check the signature
  if (!url.pathname.startsWith("/api/")) { if (req.method !== "GET" && req.method !== "HEAD") return send(res, 405, "No", "text/plain"); return serveStatic(req, res, url); }
  if (req.method === "OPTIONS") { res.writeHead(204, { "access-control-allow-origin": CORS, "access-control-allow-methods": "GET, POST, OPTIONS", "access-control-allow-headers": "content-type", "access-control-max-age": "86400" }); return res.end(); }
  const fn = routes[key]; if (!fn) return json(res, 404, { error: "not found" });
  const ip = ipOf(req); if (limited("all:" + ip, CALLS_PER_MIN, 60000)) return json(res, 429, { error: "slow down" });
  let raw = ""; req.on("data", c => { raw += c; if (raw.length > 4096) { req.destroy(); } });
  req.on("end", () => {
    let body = {}; if (req.method === "POST") { try { body = JSON.parse(raw || "{}"); } catch (e) { return json(res, 400, { error: "bad json" }); } if (!body || typeof body !== "object") return json(res, 400, { error: "bad json" }); }
    Promise.resolve().then(() => fn(body, ip, url.searchParams)).then(out => { if (Array.isArray(out)) json(res, out[0], out[1]); else { json(res, 200, out); if (/hello/.test(key)) touch(); } }).catch(e => { console.error(e); json(res, 500, { error: "server error" }); });
  });
});
if (require.main === module) server.listen(PORT, () => console.log(`STIXX beta on http://localhost:${PORT}  (data: ${DATA_FILE}, files: ${STATIC})`));
module.exports = { server, db: () => db };
