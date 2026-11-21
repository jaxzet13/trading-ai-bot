/* ============================================================================
   4. STATE. Everything lives in this browser.
   ========================================================================== */
const KEY = "stixx-first-print-v1";
const fresh = () => ({ coins: START, vault: [], serials: {}, ageOK: false, s: { packs: 0, spent: 0, sold: 0, best: 0 } });
let state = fresh();
try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s && typeof s.coins === "number") state = Object.assign(fresh(), s, { s: Object.assign(fresh().s, s.s || {}) }); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const valueOf = c => Math.max(1, Math.round(BY_NO[c.no].val * (c.fx ? STYLES[c.fx].x : 1)));
const sellOf = c => Math.floor(valueOf(c) * SELLBACK);
function mint(card, phys, serial) {
  const n = serial != null ? serial : (state.serials[card.no] = (state.serials[card.no] || 0) + 1);
  if (serial != null) state.serials[card.no] = Math.max(state.serials[card.no] || 0, serial);
  const code = cardCode(card, n);
  return { uid: "c" + Date.now().toString(36) + Math.floor(rand() * 1e6).toString(36), no: card.no, serial: n, code, fx: card.styles ? styleOfCode(code) : "", t: Date.now(), phys: !!phys };
}
function pullPack() { return PACK.slots.map(slot => mint(BY_ID[pick(slot)])); }
// the odds, worked out from the slot tables
function slotP(slot, id) { let t = 0, w = 0; for (const [i, x] of slot) { t += x; if (i === id) w = x; } return w / t; }
const packP = id => 1 - PACK.slots.reduce((a, s) => a * (1 - slotP(s, id)), 1);
// The exact distribution of what a whole pack sells back for: every slot's outcomes (including a Stitch's style roll) convolved together.
const sellFor = (card, mult) => Math.floor(Math.max(1, Math.round(card.val * mult)) * SELLBACK);
function cardSells(card) {
  const m = new Map(), add = (k, p) => m.set(k, (m.get(k) || 0) + p);
  if (!card.styles) { add(sellFor(card, 1), 1); return m; }
  let rest = 1; for (const k in STYLES) { add(sellFor(card, STYLES[k].x), STYLES[k].p); rest -= STYLES[k].p; } add(sellFor(card, 1), rest); return m;
}
let _ps = null;
function packStats() {
  if (_ps) return _ps;
  let dist = new Map([[0, 1]]);
  for (const slot of PACK.slots) {
    const t = slot.reduce((a, [, w]) => a + w, 0), sd = new Map();
    for (const [id, w] of slot) for (const [v, p] of cardSells(BY_ID[id])) sd.set(v, (sd.get(v) || 0) + w / t * p);
    const next = new Map(); for (const [a, pa] of dist) for (const [b, pb] of sd) next.set(a + b, (next.get(a + b) || 0) + pa * pb); dist = next;
  }
  let ev = 0, hit = 0, acc = 0, median = 0; const keys = [...dist.keys()].sort((a, b) => a - b);
  for (const k of keys) { const p = dist.get(k); ev += k * p; if (k >= PACK.price) hit += p; }
  for (const k of keys) { acc += dist.get(k); if (acc >= .5) { median = k; break; } }
  return (_ps = { ev, hit, median, rtp: ev / PACK.price });
}
