/* ============================================================================
   4. STATE AND ECONOMY. Everything lives in this browser.
   ========================================================================== */
const KEY = "stixx-first-print-v1";
const fresh = () => ({ coins: START, vault: [], serials: {}, hist: [], alertAt: {}, seen: {}, seenIntro: false, ageOK: false, pack: "fp", openN: 1, freePacks: 1, paid: {}, paidSeen: {}, uid: rid(16), ref: { code: "", by: "", n: 0, act: 0 }, fair: null, rescueAt: 0, streak: { n: 0, last: "", freezes: 0, best: 0 }, lastSeen: 0, tg: {}, mute: false, lim: { packs: 0, breakUntil: 0 }, packLog: [], found: {}, foundFx: {}, rank: 0, s: { packs: 0, spent: 0, sold: 0, best: 0, realized: 0, added: 0, free: 0, bought: 0 } });
let state = fresh();
try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && typeof s.coins === "number") state = Object.assign(fresh(), s, { s: Object.assign(fresh().s, s.s || {}) }); } catch (e) {}
const persist = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const save = () => { logWorth(true); persist(); };
// a fresh start keeps who you are (age check, sound, your invite code) and nothing else
// packs you paid for survive a fresh start, along with who you are
const boughtOf = id => (state.paid && state.paid[id]) || 0, boughtAll = () => Object.values(state.paid || {}).reduce((a, n) => a + n, 0);       // packs you paid for, per pack and in all
function startOver() { const keep = { ageOK: state.ageOK, seenIntro: state.seenIntro, uid: state.uid, ref: state.ref, mute: state.mute, fair: state.fair, paid: state.paid, paidSeen: state.paidSeen }; state = Object.assign(fresh(), keep); save(); }

// what a copy is worth right now: the card's live market price, times its style multiple
const valueOf = c => Math.max(.5, MK.price(BY_NO[c.no]) * (c.fx ? STYLES[c.fx].x : 1));   // in cents, live, not rounded
const sellOf = c => Math.floor(valueOf(c) * SELLBACK);                    // selling pays the price minus 10%
const costOf = c => c.cost != null ? c.cost : valueOf(c);                 // what a copy cost you, or was worth the moment you pulled it
const gainOf = c => valueOf(c) / Math.max(1, costOf(c)) - 1;

/* ---- your net worth over time ----
   A point is kept each time the market moves while the app is open, and after every change you make: [time, net worth, money you have added].
   While the app is closed nothing in your wallet can change, so the gap is filled in from the market's own price path. Nothing on the profile is made up. */
const holdingsValue = () => state.vault.reduce((a, c) => a + valueOf(c), 0);
const netWorth = () => state.coins + holdingsValue();
const valueAgo = (c, ticks) => Math.max(.5, MK.price(BY_NO[c.no], ticks) * (c.fx ? STYLES[c.fx].x : 1));
function logWorth(force) {
  const h = state.hist, t = Date.now(), last = h[h.length - 1]; if (last && !force && t - last[0] < 15000) return;
  if (last && t - last[0] > 12 * 60000 && state.vault.length) for (let ts = Math.max(last[0] + 6e5, t - 7 * 864e5); ts < t - 3e5; ts += 6e5) { const ago = Math.round((t - ts) / MK.TICK); h.push([ts, state.coins + state.vault.reduce((a, c) => a + valueAgo(c, ago), 0), state.s.added]); }
  const net = netWorth(); if (!last || last[1] !== net || last[2] !== state.s.added || t - last[0] > 15000) h.push([t, net, state.s.added]);
  if (h.length > 1500) h.splice(0, 750, ...h.slice(0, 750).filter((_, i) => i % 2 === 0));    // keep recent points dense, thin out the old ones
}
const profitAll = () => netWorth() - START - state.s.added;                                    // everything you have made or lost, deposits left out
function profitSince(ms) { const h = state.hist, t = Date.now() - ms; let p = h[0]; for (const x of h) { if (x[0] <= t) p = x; else break; } return p ? (netWorth() - state.s.added) - (p[1] - p[2]) : 0; }
function mint(card, phys, serial, paid) {
  const n = serial != null ? serial : (state.serials[card.no] = (state.serials[card.no] || 0) + 1);
  if (serial != null) state.serials[card.no] = Math.max(state.serials[card.no] || 0, serial);
  const code = cardCode(card, n);
  const copy = { uid: "c" + Date.now().toString(36) + Math.floor(rand() * 1e6).toString(36), no: card.no, serial: n, code, fx: card.styles ? styleOfCode(code) : "", t: Date.now(), phys: !!phys };
  copy.cost = paid != null ? paid : valueOf(copy); return copy;
}
const curPack = () => PACK_BY[state.pack] || PACKS[0];
function pullPack(pk, us) { return (pk || curPack()).slots.map((slot, i) => mint(BY_ID[us ? pickU(slot, us[i]) : pick(slot)])); }        // `us` holds one number in [0,1) per slot when the draw is the provably fair one

// the odds, worked out from the slot tables
function slotP(slot, id) { let t = 0, w = 0; for (const [i, x] of slot) { t += x; if (i === id) w = x; } return w / t; }
const packP = id => 1 - packOf(BY_ID[id]).slots.reduce((a, s) => a * (1 - slotP(s, id)), 1);        // the chance a pack of the card's own set holds it

// The exact distribution of what a whole pack sells back for: every slot's outcomes (including each card's style roll) convolved together.
// `val` says what a card is worth: the live market price, or its base worth.
const sellFor = (card, mult, val) => Math.floor(Math.max(1, Math.round(val(card) * mult)) * SELLBACK);
function cardSells(card, val) {
  const m = new Map(), add = (k, p) => m.set(k, (m.get(k) || 0) + p);
  if (!card.styles) { add(sellFor(card, 1, val), 1); return m; }
  let rest = 1; for (const k in STYLES) { add(sellFor(card, STYLES[k].x, val), STYLES[k].p); rest -= STYLES[k].p; } add(sellFor(card, 1, val), rest); return m;
}
// The pack's average return is worked out exactly (it is linear), and so is the chance of selling back at least what you paid; every total at or above `cap`
// is merged into one bin, because past that point nothing about the number matters, which keeps this fast enough to redo every time the market moves.
function slotSells(slot, val) { const t = slot.reduce((a, [, w]) => a + w, 0), sd = new Map(); for (const [id, w] of slot) for (const [v, p] of cardSells(BY_ID[id], val)) sd.set(v, (sd.get(v) || 0) + w / t * p); return sd; }
const evOf = (val, pk) => pk.slots.reduce((a, slot) => { let e = 0; for (const [v, p] of slotSells(slot, val)) e += v * p; return a + e; }, 0);
function packDist(val, cap, pk) {
  let dist = new Float64Array(cap + 1); dist[0] = 1;
  for (const slot of pk.slots) {
    const next = new Float64Array(cap + 1); let all = 0; for (let i = 0; i <= cap; i++) all += dist[i];
    for (const [v, p] of slotSells(slot, val)) { if (v >= cap) { next[cap] += p * all; continue; } let over = 0; for (let i = 0; i <= cap; i++) { const q = dist[i]; if (!q) continue; if (i + v >= cap) over += q; else next[i + v] += p * q; } next[cap] += p * over; }
    dist = next;
  }
  return dist;
}
const _base = {}; const baseEV = pk => _base[pk.id] || (_base[pk.id] = evOf(c => c.val, pk));
// The pack's price follows the market: it moves with what the cards inside are worth now, so the pack always returns about the same share
// (about 90%) whatever the market does. Recomputed whenever the market moves.
const RTP_CEIL = .95;                                                                                   // a pack is never allowed to return more than 95% on average, whatever the cards are doing
const _ps = {};
function packStats(pk) {
  pk = pk || curPack(); const t = MK.tick(); if (_ps[pk.id] && _ps[pk.id].t === t) return _ps[pk.id];
  const val = card => MK.tickPrice(card), ev = evOf(val, pk), price = Math.max(clamp(Math.round(pk.price * ev / baseEV(pk)), pk.min, pk.max), Math.ceil(ev / RTP_CEIL)), cap = price * 3, dist = packDist(val, cap, pk);
  let hit = 0, acc = 0, median = cap; for (let i = price; i <= cap; i++) hit += dist[i]; for (let i = 0; i <= cap; i++) { acc += dist[i]; if (acc >= .5) { median = i; break; } }
  return (_ps[pk.id] = { t, ev, hit, median, rtp: ev / price, price, pk });
}
const packPrice = pk => packStats(pk).price;
