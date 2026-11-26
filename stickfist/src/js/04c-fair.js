/* ============================================================================
   4c. PROVABLY FAIR PACKS, and the one door to the beta server.
   A pack is drawn from a number you can check afterwards. Before the draw the server commits to a secret seed by showing its SHA-256 hash. You pick a
   client seed of your own. Pack number n is then HMAC-SHA256(server seed, "client seed:n"), and the cards come from 32-bit slices of that, one per slot,
   through the odds on the odds page. When you rotate the seed the server reveals the old one and the page re-does every draw it made with it: the hash must
   match the commitment, the HMAC must match what you were given, and the cards must match what you got. The server cannot change a draw after seeing
   your client seed, and you cannot steer one, because you never see a result before it is committed.
   Without a server (a file, a preview) the page keeps the seed on this device instead. That still shows the odds are applied as published, but it cannot
   show that nobody else could have chosen the seed, and the page says so. The style of a copy is fixed by its copy id (a public formula), not by the draw.
   ========================================================================== */
const API = (() => {
  const m = document.querySelector('meta[name="stixx-api"]'), on = !!m && !!m.content, base = on ? m.content.replace(/\/$/, "") : "";
  async function call(path, body) {
    if (!on) return null; const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 7000);
    try { const r = await fetch(base + "/api/" + path, body === undefined ? { signal: ctl.signal } : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal: ctl.signal }); if (!r.ok) return null; return await r.json(); } catch (e) { return null; } finally { clearTimeout(t); }
  }
  // the same call, but the caller gets the status too (0 = the server could not be reached), for the calls where "no" has more than one meaning
  async function raw(path, body, keep) {
    if (!on) return { status: 0, data: null }; const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 12000);
    try { const r = await fetch(base + "/api/" + path, body === undefined ? { signal: ctl.signal } : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal: ctl.signal, keepalive: !!keep }); let data = null; try { data = await r.json(); } catch (e) {} return { status: r.status, data }; } catch (e) { return { status: 0, data: null }; } finally { clearTimeout(t); }
  }
  return { on, post: (p, b) => call(p, b || {}), get: p => call(p), raw };
})();

const sha256 = (() => {
  const primes = []; for (let n = 2; primes.length < 64; n++) if (primes.every(p => n % p)) primes.push(n);
  const f32 = x => Math.floor((x - Math.floor(x)) * 4294967296), K = primes.map(p => f32(Math.cbrt(p))), H0 = primes.slice(0, 8).map(p => f32(Math.sqrt(p))), w = new Int32Array(64);
  return function (msg) {                                                    // Uint8Array in, Uint8Array(32) out
    const l = msg.length, buf = new Uint8Array(((l + 9 + 63) >> 6) << 6), dv = new DataView(buf.buffer), H = Int32Array.from(H0); buf.set(msg); buf[l] = 128;
    dv.setUint32(buf.length - 8, Math.floor(l * 8 / 4294967296)); dv.setUint32(buf.length - 4, (l * 8) >>> 0);
    for (let o = 0; o < buf.length; o += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(o + i * 4);
      for (let i = 16; i < 64; i++) { const a = w[i - 15], b = w[i - 2]; w[i] = (w[i - 16] + (((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3)) + w[i - 7] + (((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10))) | 0; }
      let a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7))) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0, t2 = ((((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10))) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    const out = new Uint8Array(32), ov = new DataView(out.buffer); for (let i = 0; i < 8; i++) ov.setUint32(i * 4, H[i] >>> 0); return out;
  };
})();
const utf8 = s => new TextEncoder().encode(s), toHex = b => Array.from(b, x => x.toString(16).padStart(2, "0")).join("");
const sha256hex = s => toHex(sha256(utf8(s)));
function hmacHex(key, msg) {                                                 // HMAC-SHA256, key and message as text (the key is the seed's hex text), digest as hex
  let k = utf8(key); const m = utf8(msg); if (k.length > 64) k = sha256(k); const kp = new Uint8Array(64); kp.set(k);
  const cat = (a, b) => { const o = new Uint8Array(a.length + b.length); o.set(a); o.set(b, a.length); return o; };
  return toHex(sha256(cat(kp.map(x => x ^ 92), sha256(cat(kp.map(x => x ^ 54), m)))));
}
const digestU = (hex, n) => Array.from({ length: n }, (_, i) => parseInt(hex.slice(i * 8, i * 8 + 8), 16) / 4294967296);   // one number in [0,1) per slot

const Fair = (() => {
  const LOG = 60;
  const mk = () => { const seed = rid(16); return { seed, commit: sha256hex(seed), nonce: 0, epoch: 1 }; };
  const F = () => state.fair || (state.fair = { cs: rid(5).toUpperCase(), local: mk(), srv: null, log: [], past: [] });
  const cardsOf = (pk, hex, st) => { const sl = pk.slotsBy[st] || pk.slotsBy.normal; return digestU(hex, sl.length).map((u, i) => BY_ID[pickU(sl[i], u)]); };
  // draw the cards for one pack
  async function next(pk, pick) {
    const f = F(); let hex = "", nonce = 0, epoch = "", mode = "local", commit = "";
    if (API.on) {
      const r = await API.post("fair/draw", { uid: state.uid, cs: f.cs });
      if (r && /^[0-9a-f]{64}$/.test(r.digest || "")) { const seen = f.srv && f.srv.epoch === r.epoch ? f.srv.commit : r.commit; hex = r.digest; nonce = r.nonce; epoch = "S" + r.epoch; mode = "server"; commit = seen; f.srv = { commit: seen, nonce: r.nonce + 1, epoch: r.epoch }; }     // the commitment you were shown before the draw is the one that gets checked
    }
    if (!hex) { const L = f.local; nonce = L.nonce++; epoch = "L" + L.epoch; commit = L.commit; hex = hmacHex(L.seed, `${f.cs}:${nonce}`); }
    return pick ? ticket(pk, f, hex, nonce, epoch, mode, commit, pick) : settle(pk, f, hex, nonce, epoch, mode, commit);
  }
  // One pack as a choice of `k` face-down cards. The single draw is read as k numbers, one per card, each picked from the pack's table in the
  // same way, so every one of them has exactly the published odds. Nothing is made until you choose: take(i) gives you card i, and the log
  // keeps which one you took (k, of), so the draw can be checked against the seed like any other.
  // a legendary or better goes on the live feed: the server is told which draw it was, re-draws it itself, and lists it only if it checks out
  const tell = (mode, pk, n, items) => { if (mode === "server" && items.some(c => RAR[BY_NO[c.no].rar].tier >= 4)) API.post("fair/hit", { uid: state.uid, n, pack: pk.id, style: (state.styles && state.styles[pk.id]) || "normal" }).then(() => { if (typeof Live !== "undefined") Live.pull(true); }); };
  const cardAt = (pk, hex, of, i) => BY_ID[pickU(pk.slots[0], digestU(hex, of)[i])];
  function ticket(pk, f, hex, nonce, epoch, mode, commit, of) {
    let done = false;
    // warm(): fetch the pictures the five could be, in no order that says which is where, so the one you pick is ready the moment you pick it
    return { of, get done() { return done; }, warm() { [...new Set(Array.from({ length: of }, (_, i) => cardAt(pk, hex, of, i).id))].sort().forEach(id => loadImg(imgOf(BY_ID[id]))); }, take(i) { if (done) return null; done = true; i = Math.max(0, Math.min(of - 1, i | 0)); const card = mint(cardAt(pk, hex, of, i));
      f.log.push({ mode, e: epoch, n: nonce, cs: f.cs, c: commit, pack: pk.id, d: hex, picks: [BY_NO[card.no].id], k: i, of, t: Date.now() }); if (f.log.length > LOG) f.log.shift(); return card; } };
  }
  function settle(pk, f, hex, nonce, epoch, mode, commit) {
    const items = pullPack(pk, digestU(hex, pk.slots.length));
    f.log.push({ mode, e: epoch, n: nonce, cs: f.cs, c: commit, pack: pk.id, st: (state.styles && state.styles[pk.id]) || "normal", d: hex, picks: items.map(c => BY_NO[c.no].id), t: Date.now() }); if (f.log.length > LOG) f.log.shift(); tell(mode, pk, nonce, items);
    return items;
  }
  // the cards for n packs with one request to the server (the same draws, in order, as n single requests would give)
  async function nextMany(pk, n) {
    const f = F(); let r = null;
    if (API.on && n > 1) { r = await API.post("fair/draws", { uid: state.uid, cs: f.cs, n }); if (!(r && Array.isArray(r.draws) && r.draws.length === n && r.draws.every(d => /^[0-9a-f]{64}$/.test(d.digest || "")))) r = null; }
    const out = [];
    for (let i = 0; i < n; i++) {
      if (r) { const d = r.draws[i], seen = f.srv && f.srv.epoch === r.epoch ? f.srv.commit : r.commit; f.srv = { commit: seen, nonce: d.nonce + 1, epoch: r.epoch }; out.push(settle(pk, f, d.digest, d.nonce, "S" + r.epoch, "server", seen)); }
      else if (API.on && n === 1) out.push(await next(pk));
      else { const L = f.local, nonce = L.nonce++; out.push(settle(pk, f, hmacHex(L.seed, `${f.cs}:${nonce}`), nonce, "L" + L.epoch, "local", L.commit)); }
    }
    return out;
  }
  // check one logged draw against a revealed seed
  function check(entry, seed) {
    if (!seed) return null; const pk = PACK_BY[entry.pack]; if (!pk) return false;
    const hex = hmacHex(seed, `${entry.cs}:${entry.n}`), cs = entry.of ? [cardAt(pk, hex, entry.of, entry.k).id] : cardsOf(pk, hex, entry.st).map(c => c.id);
    return sha256hex(seed) === entry.c && hex === entry.d && cs.length === entry.picks.length && cs.every((id, i) => id === entry.picks[i]);
  }
  const seedFor = (f, entry) => { if (entry.mode === "local") { const p = f.past.find(x => x.e === entry.e); return p ? p.seed : entry.e === "L" + f.local.epoch ? f.local.seed : ""; } const p = f.past.find(x => x.e === entry.e); return p ? p.seed : ""; };
  const status = (f, entry) => check(entry, seedFor(f, entry));
  // reveal the seed in use and start a new one
  async function rotate() {
    const f = F(); let done = false;
    if (API.on && f.srv) { const r = await API.post("fair/rotate", { uid: state.uid }); if (r && r.seed) { f.past.push({ e: "S" + r.epoch, seed: r.seed, commit: sha256hex(r.seed) }); f.srv = { commit: r.commit, nonce: 0, epoch: r.next }; done = true; } }
    if (f.log.some(x => x.mode === "local" && x.e === "L" + f.local.epoch) || !done) { f.past.push({ e: "L" + f.local.epoch, seed: f.local.seed, commit: f.local.commit }); const n = mk(); n.epoch = f.local.epoch + 1; f.local = n; }
    while (f.past.length > 20) f.past.shift(); persist(); return true;
  }
  const adopt = fi => { const f = F(); if (fi && /^[0-9a-f]{64}$/.test(fi.commit || "") && (!f.srv || f.srv.epoch !== fi.epoch)) f.srv = { commit: fi.commit, nonce: fi.nonce, epoch: fi.epoch }; persist(); };      // the server's commitment, shown before any pack is drawn from it
  const setClientSeed = v => { const s = String(v).replace(/[^\w.-]/g, "").slice(0, 24); if (s) { F().cs = s; persist(); } return F().cs; };
  return { F, next, nextMany, check, status, rotate, setClientSeed, cardsOf, seedFor, adopt , offer: (pk, k) => next(pk, k) };
})();
