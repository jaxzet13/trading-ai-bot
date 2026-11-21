/* ============================================================================
   4. STATE AND ECONOMY. Everything lives in this browser.
   ========================================================================== */
const KEY = "stixx-first-print-v1";
const fresh = () => ({ coins: START, vault: [], serials: {}, bought: {}, ageOK: false, s: { packs: 0, spent: 0, sold: 0, best: 0, realized: 0, bought: 0 } });
let state = fresh();
try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && typeof s.coins === "number") state = Object.assign(fresh(), s, { s: Object.assign(fresh().s, s.s || {}) }); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };

// what a copy is worth right now: the card's live market price, times its style multiple
const valueOf = c => Math.max(1, Math.round(MK.price(BY_NO[c.no]) * (c.fx ? STYLES[c.fx].x : 1)));
const sellOf = c => Math.floor(valueOf(c) * SELLBACK);                    // selling pays the price minus 10%
const BUY_SPREAD = 1.1, buyPrice = card => Math.round(MK.price(card) * BUY_SPREAD);   // buying costs the price plus 10%
const costOf = c => c.cost != null ? c.cost : valueOf(c);                 // what a copy cost you, or was worth the moment you pulled it
const gainOf = c => valueOf(c) / Math.max(1, costOf(c)) - 1;
function mint(card, phys, serial, paid) {
  const n = serial != null ? serial : (state.serials[card.no] = (state.serials[card.no] || 0) + 1);
  if (serial != null) state.serials[card.no] = Math.max(state.serials[card.no] || 0, serial);
  const code = cardCode(card, n);
  const copy = { uid: "c" + Date.now().toString(36) + Math.floor(rand() * 1e6).toString(36), no: card.no, serial: n, code, fx: card.styles ? styleOfCode(code) : "", t: Date.now(), phys: !!phys };
  copy.cost = paid != null ? paid : valueOf(copy); return copy;
}
function pullPack() { return PACK.slots.map(slot => mint(BY_ID[pick(slot)])); }

// the odds, worked out from the slot tables
function slotP(slot, id) { let t = 0, w = 0; for (const [i, x] of slot) { t += x; if (i === id) w = x; } return w / t; }
const packP = id => 1 - PACK.slots.reduce((a, s) => a * (1 - slotP(s, id)), 1);

// The exact distribution of what a whole pack sells back for: every slot's outcomes (including a Stitch's style roll) convolved together.
// `val` says what a card is worth: the live market price, or its base worth.
const sellFor = (card, mult, val) => Math.floor(Math.max(1, Math.round(val(card) * mult)) * SELLBACK);
function cardSells(card, val) {
  const m = new Map(), add = (k, p) => m.set(k, (m.get(k) || 0) + p);
  if (!card.styles) { add(sellFor(card, 1, val), 1); return m; }
  let rest = 1; for (const k in STYLES) { add(sellFor(card, STYLES[k].x, val), STYLES[k].p); rest -= STYLES[k].p; } add(sellFor(card, 1, val), rest); return m;
}
function packDist(val) {
  let dist = new Map([[0, 1]]);
  for (const slot of PACK.slots) {
    const t = slot.reduce((a, [, w]) => a + w, 0), sd = new Map();
    for (const [id, w] of slot) for (const [v, p] of cardSells(BY_ID[id], val)) sd.set(v, (sd.get(v) || 0) + w / t * p);
    const next = new Map(); for (const [a, pa] of dist) for (const [b, pb] of sd) next.set(a + b, (next.get(a + b) || 0) + pa * pb); dist = next;
  }
  return dist;
}
const evOf = dist => { let ev = 0; for (const [k, p] of dist) ev += k * p; return ev; };
let _base = 0; const baseEV = () => _base || (_base = evOf(packDist(c => c.val)));
// The pack's price follows the market: it moves with what the cards inside are worth now, so the pack always returns about the same share
// (88%) whatever the market does. Recomputed whenever the market moves.
let _ps = null;
function packStats() {
  const t = MK.tick(); if (_ps && _ps.t === t) return _ps;
  const dist = packDist(card => MK.price(card)), ev = evOf(dist), price = clamp(Math.round(PACK.price * ev / baseEV()), PACK.min, PACK.max);
  let hit = 0, acc = 0, median = 0; const keys = [...dist.keys()].sort((a, b) => a - b);
  for (const k of keys) if (k >= price) hit += dist.get(k);
  for (const k of keys) { acc += dist.get(k); if (acc >= .5) { median = k; break; } }
  return (_ps = { t, ev, hit, median, rtp: ev / price, price });
}
const packPrice = () => packStats().price;
