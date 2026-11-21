/* ============================================================================
   4b. THE MARKET. Every card has a live price that moves on its own.
   The price is a fixed formula you can read right here, the same for everybody, and nothing in it looks at who owns what:
     - a slow "taste" level per card (how good it looks next to the other cards of its rarity)
     - random noise, bigger for cheap cards than for expensive ones
     - demand shocks (a card catches on, or falls out of favour), equally likely either way, the same size either way,
       fading over a few hours
   Nothing is tilted against holders: up moves and down moves are mirror images in log terms, and buying costs the same spread as selling.
   ========================================================================== */
const MK = (() => {
  const TICK = 20000, EPOCH = 14 * 864e5, N = Math.round(EPOCH / TICK), DT = TICK / 864e5;   // one tick = 20 seconds; the path restarts every 14 days
  const KAPPA = 1.2, TAU = .25;                                                             // pull back toward the card's taste level (per day); shocks fade over ~6 hours
  const VOL = { common: .62, uncommon: .52, rare: .36, epic: .28, legendary: .2, mythic: .15, secret: .12 };      // daily volatility of the log price
  const RATE = { common: 1.3, uncommon: 1.1, rare: .75, epic: .55, legendary: .35, mythic: .25, secret: .15 };    // demand shocks per day
  const CAP = { common: 8, uncommon: 6, rare: 4, epic: 3, legendary: 2.5, mythic: 2, secret: 2 }, FLOOR = .25;      // the price stays between FLOOR x and CAP x of the card's base value
  const TASTE = { stitch: .04, brick: .14, rook: -.07, orbit: .08, phantom: -.03, null: .15, shogun: 0, ronin: .08, grimm: .05, reaper: -.04, umbra: .1 };   // log units
  const LIST = { epic: .55, legendary: .2, mythic: .1, secret: .04 }, DEPTH = { common: 40, uncommon: 12, rare: 4, epic: 2, legendary: 1, mythic: 1, secret: 1 };
  const h3 = (a, b, c) => { let h = (a * 374761393 + b * 668265263 + c * 2147483647) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16; return (h >>> 0) / 4294967296; };
  const norm = (a, b, c) => Math.sqrt(-2 * Math.log(Math.max(h3(a, b, c), 1e-9))) * Math.cos(6.2832 * h3(a, b, c + 1));
  const idx = {}; CARDS.forEach((c, i) => { idx[c.no] = i; });
  let epoch = 0, cards = null;
  const nowTick = () => { if (!cards) advance(); return Math.floor((Date.now() - epoch) / TICK); };
  function stepOne(S, c, i, t) {
    const vol = VOL[c.rar], hi = Math.log(CAP[c.rar]), lo = Math.log(FLOOR), sd = Math.sqrt(DT);
    S.a += -.2 * (S.a - (TASTE[c.id] || 0)) * DT + .06 * sd * norm(i, t, 11);                     // taste wanders slowly
    S.u += -KAPPA * (S.u - S.a) * DT + vol * sd * norm(i, t, 3);          // noise, pulled back toward taste: a typical price sits at the taste level, up and down moves are mirror images in log terms
    if (h3(i, t, 5) < RATE[c.rar] * DT) {                                                         // a demand shock: up or down with equal odds
      const mega = h3(i, t, 6) < .08, size = (mega ? .9 + h3(i, t, 7) * 1 : .3 + .8 * h3(i, t, 7) * h3(i, t, 7)) * (h3(i, t, 8) < .5 ? 1 : -1);
      S.h += size;
    }
    S.h *= Math.exp(-DT / TAU);
    let x = S.u + S.h; if (x > hi) { x = hi; S.u = hi - S.h; } else if (x < lo) { x = lo; S.u = lo - S.h; }
    return x;
  }
  function build() {
    epoch = Math.floor(Date.now() / EPOCH) * EPOCH; const t1 = Math.floor((Date.now() - epoch) / TICK); cards = CARDS.map((c, i) => {
      const a = TASTE[c.id] || 0, vol = VOL[c.rar], S = { a, u: a + norm(i, -1, 1) * vol / Math.sqrt(2 * KAPPA), h: 0 }, X = new Float32Array(N + 2);
      X[0] = S.u; for (let t = 1; t <= t1; t++) X[t] = stepOne(S, c, i, t); return { c, S, X, n: t1 };
    });
  }
  function advance() {
    if (!cards || Math.floor(Date.now() / EPOCH) * EPOCH !== epoch) { build(); return true; }
    const t1 = Math.floor((Date.now() - epoch) / TICK); let moved = false;
    for (const m of cards) while (m.n < t1) { m.n++; m.X[m.n] = stepOne(m.S, m.c, idx[m.c.no], m.n); moved = true; }
    return moved;
  }
  const M = card => { if (!cards) advance(); return cards[idx[card.no]]; };
  const logAt = (card, back) => { const m = M(card); return m.X[Math.max(0, m.n - back)]; };
  const price = (card, back) => Math.max(1, Math.round(card.val * Math.exp(logAt(card, back || 0))));
  const pct = (card, hours) => Math.exp(logAt(card, 0) - logAt(card, Math.round(hours * 180))) - 1;
  const series = (card, hours, pts) => { const m = M(card), span = Math.round(hours * 180), out = []; for (let k = 0; k < pts; k++) out.push(price(card, Math.round(span * (1 - k / (pts - 1))))); return out; };
  const buzz = card => { const m = M(card); return clamp(Math.round(2.5 + m.S.h * 3 + (m.X[m.n] - m.S.a) * 2.2), 0, 5); };   // 0 to 5: how much talk there is about the card right now
  const stock = card => { const w = Math.floor(nowTick() / 180), i = idx[card.no];
    if (LIST[card.rar] == null) return DEPTH[card.rar] ? Math.max(1, Math.floor(DEPTH[card.rar] * (.3 + .7 * h3(i, w, 21)))) : 0;
    return h3(i, w, 22) < LIST[card.rar] ? 1 + Math.floor(h3(i, w, 23) * DEPTH[card.rar]) : 0; };
  const hourId = () => Math.floor(nowTick() / 180);
  // what simulated traders did lately, worked out from the real price path and net of the same 10% spread everyone pays
  function trades(n) {
    const t = nowTick(), out = [];
    for (let k = 0; k < n; k++) { const b = t - k * 9, i = Math.floor(h3(b, 31, 1) * CARDS.length), hours = 1 + Math.floor(h3(b, 32, 2) * 23), c = CARDS[i], m = cards[i];
      if (b - hours * 180 < 0) continue; const buy = Math.max(1, Math.round(c.val * Math.exp(m.X[b - hours * 180]))), sell = Math.max(1, Math.round(c.val * Math.exp(m.X[b])));
      out.push({ name: "anon_" + (1000 + Math.floor(h3(b, 33, 3) * 9000)), card: c, hours, buy: Math.round(buy * 1.1), sell: Math.floor(sell * .9), min: k * 3 }); }
    return out;
  }
  return { advance, price, pct, series, buzz, stock, hourId, trades, tick: nowTick, TICK, FLOOR, CAP, VOL, RATE };
})();
