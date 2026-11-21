/* ============================================================================
   4b. THE MARKET. Every card has a live price that moves on its own.
   The price is a fixed formula you can read right here, the same for everybody, and nothing in it looks at who owns what:
     - a slow "taste" level per card (how good it looks next to the other cards of its rarity)
     - random noise, bigger for cheap cards than for expensive ones
     - demand shocks (a card catches on, or falls out of favour), equally likely either way, the same size either way,
       fading over a few hours
   Nothing is tilted against holders: up moves and down moves are mirror images in log terms, and selling costs everybody the same 10%.
   Like a memecoin, any card can moon (ten times its price or more) or get rugged (a tenth of its price or less). Both are equally likely and the same size.
   History is continuous: the noise is keyed by the absolute clock tick, and the path is built from a few days before the window anyone can see.
   ========================================================================== */
const MK = (() => {
  const TICK = 20000, EPOCH = 14 * 864e5, PRE = 14 * 864e5, LEN = Math.ceil((EPOCH + PRE) / TICK) + 2, DT = TICK / 864e5;   // one tick = 20 seconds; the path is rebuilt every 14 days, starting 14 days earlier so nothing visible ever has a gap
  const KAPPA = 1.2, TAU = .25, TAU_MOON = 1;                                                // pull back toward the card's taste level (per day); shocks fade over ~6 hours, a moon or a rug over a day or two
  const VOL = { common: .62, uncommon: .52, rare: .36, epic: .28, legendary: .2, mythic: .15, secret: .12 };      // daily volatility of the log price
  const RATE = { common: 1.3, uncommon: 1.1, rare: .75, epic: .55, legendary: .35, mythic: .25, secret: .15 };    // demand shocks per day
  // The big moves, per card: [chance per day of a moon, and the same chance of a rug, biggest multiple]. The price stays between 1/multiple and multiple times the card's base value.
  const MOON = { stitch: [.10, 60], brick: [.10, 60], rook: [.10, 60], orbit: [.09, 50], phantom: [.06, 30], null: [.05, 20], shogun: [.035, 12], ronin: [.05, 20], grimm: [.03, 12], reaper: [.015, 5], umbra: [.01, 3.5] };
  const CAP = Object.fromEntries(CARDS.map(c => [c.id, MOON[c.id][1]]));
  const TASTE = { stitch: .04, brick: .14, rook: -.07, orbit: .08, phantom: -.03, null: .15, shogun: 0, ronin: .08, grimm: .05, reaper: -.04, umbra: .1 };   // log units
  const mix = h => { h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b); h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35); return h ^ (h >>> 16); };   // a well-mixed 32-bit hash, so different questions asked about the same tick are independent
  const h3 = (a, b, c) => (mix(Math.imul(a, 0x9e3779b1) + mix(Math.imul(b, 0x85ebca77) + mix(c + 0x27d4eb2f))) >>> 0) / 4294967296;
  const norm = (a, b, c) => Math.sqrt(-2 * Math.log(Math.max(h3(a, b, c), 1e-9))) * Math.cos(6.2832 * h3(a, b, c + 1));
  const idx = {}; CARDS.forEach((c, i) => { idx[c.no] = i; });
  let epoch = 0, t0 = 0, base = 0, cards = null;                                                // t0: where the built path starts; base: that moment as an absolute tick
  const nowTick = () => { if (!cards) advance(); return Math.floor((Date.now() - t0) / TICK); };
  function stepOne(S, c, i, t) {
    const vol = VOL[c.rar], hi = Math.log(CAP[c.id]), lo = -hi, sd = Math.sqrt(DT), mo = MOON[c.id];
    S.a += -.2 * (S.a - (TASTE[c.id] || 0)) * DT + .06 * sd * norm(i, t, 11);                     // taste wanders slowly
    S.u += -KAPPA * (S.u - S.a) * DT + vol * sd * norm(i, t, 3);          // noise, pulled back toward taste: a typical price sits at the taste level, up and down moves are mirror images in log terms
    if (h3(i, t, 5) < RATE[c.rar] * DT) {                                                         // a demand shock: up or down with equal odds
      const mega = h3(i, t, 6) < .08, size = (mega ? .9 + h3(i, t, 7) * 1 : .3 + .8 * h3(i, t, 7) * h3(i, t, 7)) * (h3(i, t, 8) < .5 ? 1 : -1);
      S.h += size;
    }
    S.h *= Math.exp(-DT / TAU);
    if (h3(i, t, 12) < 2 * mo[0] * DT) { const size = Math.log(mo[1]) * (.65 + .35 * h3(i, t, 14)); S.m += h3(i, t, 13) < .5 ? size : -size; }     // a moon or a rug: up or down with equal odds
    S.m *= Math.exp(-DT / TAU_MOON);
    let x = S.u + S.h + S.m; if (x > hi) { x = hi; S.u = hi - S.h - S.m; } else if (x < lo) { x = lo; S.u = lo - S.h - S.m; }
    return x;
  }
  function build() {
    epoch = Math.floor(Date.now() / EPOCH) * EPOCH; t0 = Math.floor((epoch - PRE) / TICK) * TICK; base = t0 / TICK; const t1 = Math.floor((Date.now() - t0) / TICK); cards = CARDS.map((c, i) => {
      const a = TASTE[c.id] || 0, vol = VOL[c.rar], S = { a, u: a + norm(i, -1, 1) * vol / Math.sqrt(2 * KAPPA), h: 0, m: 0 }, X = new Float32Array(LEN);
      X[0] = S.u; for (let t = 1; t <= t1; t++) X[t] = stepOne(S, c, i, base + t); return { c, S, X, n: t1 };
    });
  }
  function advance() {
    if (!cards || Math.floor(Date.now() / EPOCH) * EPOCH !== epoch) { build(); return true; }
    const t1 = Math.floor((Date.now() - t0) / TICK); let moved = false;
    for (const m of cards) while (m.n < t1) { m.n++; m.X[m.n] = stepOne(m.S, m.c, idx[m.c.no], base + m.n); moved = true; }
    return moved;
  }
  const M = card => { if (!cards) advance(); return cards[idx[card.no]]; };
  const logAt = (card, back) => { const m = M(card); return m.X[Math.max(0, m.n - back)]; };
  const price = (card, back) => Math.max(1, Math.round(card.val * Math.exp(logAt(card, back || 0))));
  const pct = (card, hours) => Math.exp(logAt(card, 0) - logAt(card, Math.round(hours * 180))) - 1;
  const series = (card, hours, pts) => { const m = M(card), span = Math.round(hours * 180), out = []; for (let k = 0; k < pts; k++) out.push(price(card, Math.round(span * (1 - k / (pts - 1))))); return out; };
  const buzz = card => { const m = M(card); return clamp(Math.round(2.5 + (m.S.h + m.S.m) * 2 + (m.X[m.n] - m.S.a) * 1.2), 0, 5); };   // 0 to 5: how much talk there is about the card right now
  /* Simulated traders. Each one pulled a card some hours ago and sold it at tick b; what they got and what they sold for come straight from the real
     price path, and the sale is net of the same 10% selling fee. Cards are chosen in proportion to how often packs actually hold them. */
  let cum = null; const pickCard = u => { if (!cum) { const w = CARDS.map(c => packP(c.id)), t = w.reduce((x, y) => x + y, 0); let acc = 0; cum = w.map(x => (acc += x / t)); } const i = cum.findIndex(x => u < x); return i < 0 ? CARDS.length - 1 : i; };
  function event(b) {
    const a = base + b, i = pickCard(h3(a, 31, 1)), hours = 1 + Math.floor(h3(a, 32, 2) * 23), c = CARDS[i], m = cards[i], from = b - hours * 180; if (from < 0) return null;
    const got = Math.max(1, Math.round(c.val * Math.exp(m.X[from]))), sold = Math.floor(Math.max(1, Math.round(c.val * Math.exp(m.X[b]))) * SELLBACK);
    return { name: "anon_" + (1000 + Math.floor(h3(a, 33, 3) * 9000)), card: c, hours, got, sold, gain: sold - got, pct: sold / got - 1, ago: Math.round((nowTick() - b) / 3) };   // ago: minutes
  }
  const feed = n => { const t = nowTick(), out = []; for (let k = 0; out.length < n && k < n * 3; k++) { const e = event(t - k * 9); if (e) out.push(e); } return out; };
  let fl = null;   // the last 7 days of simulated trades, one every three minutes: the best and the worst of them by dollars
  function flips() {
    const t = nowTick(); if (fl && fl.t === t) return fl; const all = []; for (let k = 0; k < 3360; k++) { const e = event(t - k * 9); if (e) all.push(e); }
    const byGain = all.slice().sort((x, y) => y.gain - x.gain); return (fl = { t, n: all.length, best: byGain.slice(0, 3), worst: byGain.slice(-3).reverse(), won: all.filter(e => e.gain > 0).length });
  }
  /* The biggest runs each card has made in the last week, in both directions. A run up is the price against its lowest in the 24 hours before it;
     a run down is the price against its highest in the 24 hours before it. Both are read straight off the real price path. */
  let rn = null;
  function runs() {
    const t = nowTick(); if (rn && rn.t === t) return rn; const H = 180, all = [];   // 180 ticks = one hour
    for (let i = 0; i < CARDS.length; i++) {
      const c = CARDS[i], m = cards[i], px = h => Math.max(1, Math.round(c.val * Math.exp(m.X[Math.max(0, t - h * H)]))); let up = { r: 1, h: 0 }, dn = { r: 1, h: 0 };
      for (let h = 0; h <= 7 * 24; h++) { const p = px(h); let lo = p, hi = p; for (let k = 1; k <= 24; k++) { const q = px(h + k); if (q < lo) lo = q; if (q > hi) hi = q; } if (p / lo > up.r) up = { r: p / lo, h }; if (p / hi < dn.r) dn = { r: p / hi, h }; }
      all.push({ c, up: up.r - 1, upAgo: up.h, upPrice: px(up.h), dn: dn.r - 1, dnAgo: dn.h, dnPrice: px(dn.h), now: px(0) });
    }
    return (rn = { t, up: all.filter(x => x.up >= 1).sort((a, b) => b.up - a.up), dn: all.filter(x => x.dn <= -.5).sort((a, b) => a.dn - b.dn), all });
  }
  return { advance, price, pct, series, buzz, feed, flips, runs, tick: nowTick, TICK, CAP, VOL, RATE };
})();
