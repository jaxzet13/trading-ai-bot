/* ============================================================================
   4b. THE MARKET. Every card trades all day, and the traders are AI bots.
   Nobody types the prices in. Five kinds of simulated trading bots, each following a few simple rules about what they see on the screen,
   trade every card every 20 seconds, and the price is what their orders add up to:
     - degen bots: a crowd of small trades in both directions, the everyday wobble
     - market makers: lean against whatever the price is doing, and bid under a card that is falling too fast
     - FOMO bots: chase whatever has been going up, and run from whatever has been going down
     - sniper bots: pile into a sudden jump, and bail out of a sudden drop
     - whale bots: now and then one big order, mostly buying cards that look cheap and selling cards that look rich
   The bots never look at who owns what. They watch the price and the crowd, and nothing else.
   Together they make memecoin-style markets: a card can quietly drift for days and then run ten times its price when the bots feed on each other,
   then drift back down as the market makers fade it. Cards cannot be rugged: a price can fall, but never below 35% of the card's base worth,
   and never by more than half inside any 24 hours, because the market makers always have bids under it.
   Volume, market cap and liquidity are simulated and the bots are not real people. The noise is keyed by the absolute clock tick, so the market
   is the same for everyone, and the path is built from two weeks before the window anyone can see so history never has a gap.
   ========================================================================== */
const MK = (() => {
  const TICK = 20000, EPOCH = 14 * 864e5, PRE = 14 * 864e5, LEN = Math.ceil((EPOCH + PRE) / TICK) + 2, DT = TICK / 864e5, SD = Math.sqrt(DT);   // one tick = 20 seconds; the path is rebuilt every 14 days, starting 14 days earlier
  const FLOOR = Math.log(.35), DROP = Math.log(.5), AF = DT / (20 / 1440), AS = DT / .333;                       // the lowest a card can go, the most it can fall in a day (half), the fast and slow moving averages the bots watch
  // How each kind of card is traded: [degen wobble per day, maker pull when above fair value, maker pull when below, FOMO chase, sniper size, sniper trigger, whales per day, whale size, how fast attention builds]
  const BOT = {
    common:    { vol: .40, kdn: 1.4, kup: 3, gf: 1.15, ss: .10, thr: .10, lw: .55, ws: .55, hg: 4 },
    uncommon:  { vol: .35, kdn: 1.4, kup: 3, gf: 1.25, ss: .09, thr: .09, lw: .45, ws: .50, hg: 4 },
    rare:      { vol: .26, kdn: 1.3, kup: 3, gf: 1.3,  ss: .06, thr: .07, lw: .30, ws: .40, hg: 3 },
    epic:      { vol: .20, kdn: 1.3, kup: 3, gf: 1.35, ss: .05, thr: .06, lw: .25, ws: .32, hg: 3 },
    legendary: { vol: .17, kdn: 1.2, kup: 3, gf: 1.35, ss: .04, thr: .05, lw: .18, ws: .26, hg: 3 },
    mythic:    { vol: .13, kdn: 1.2, kup: 3, gf: .95,  ss: .03, thr: .04, lw: .12, ws: .20, hg: 3 },
    secret:    { vol: .10, kdn: 1.2, kup: 3, gf: .85,  ss: .02, thr: .03, lw: .08, ws: .14, hg: 3 },
  };
  const CAP = { stitch: 40, brick: 40, rook: 40, orbit: 35, phantom: 25, null: 16, shogun: 12, ronin: 16, grimm: 10, reaper: 5, umbra: 3.5 };   // the most a card can multiply its base worth by
  const TASTE = { stitch: .04, brick: .14, rook: -.07, orbit: .08, phantom: -.03, null: .15, shogun: 0, ronin: .08, grimm: .05, reaper: -.04, umbra: .1 };   // how good each card looks next to its rarity, in log units
  const SHIFT = { common: .27, uncommon: .2, rare: .12, epic: .05, legendary: .03, mythic: -.1, secret: 0 };   // keeps a typical price near the card's base worth
  // simulated size of each card's market: market cap at base worth in dollars, and how many times a day the whole cap changes hands
  const MCAP = { stitch: 420e3, brick: 420e3, rook: 420e3, orbit: 650e3, phantom: 2.2e6, null: 9e6, shogun: 15e6, ronin: 26e6, grimm: 70e6, reaper: 180e6, umbra: 420e6 };
  const TURN = { common: 3, uncommon: 2, rare: 1.2, epic: .8, legendary: .5, mythic: .3, secret: .2 };
  const KIND = ["DegenBot", "MakerBot", "FomoBot", "SniperBot", "WhaleBot"];
  const mix = h => { h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b); h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35); return h ^ (h >>> 16); };   // a well-mixed 32-bit hash, so different questions asked about the same tick are independent
  const h3 = (a, b, c) => (mix(Math.imul(a, 0x9e3779b1) + mix(Math.imul(b, 0x85ebca77) + mix(c + 0x27d4eb2f))) >>> 0) / 4294967296;
  const norm = (a, b, c) => Math.sqrt(-2 * Math.log(Math.max(h3(a, b, c), 1e-9))) * Math.cos(6.2832 * h3(a, b, c + 1));
  const idx = {}; CARDS.forEach((c, i) => { idx[c.no] = i; });
  let epoch = 0, t0 = 0, base = 0, cards = null;                                                // t0: where the built path starts; base: that moment as an absolute tick
  const nowTick = () => { if (!cards) advance(); return Math.floor((Date.now() - t0) / TICK); };
  const out = { abs: 0, kind: 0, z: 0 };
  // one 20-second round of trading for one card: every bot reads the screen and places its order, and the price moves by what they add up to
  function stepOne(S, c, i, T) {
    const P = BOT[c.rar], hi = Math.log(CAP[c.id]), fair = S.a;
    S.a += -.2 * (S.a - (TASTE[c.id] - SHIFT[c.rar])) * DT + .06 * SD * norm(i, T, 11);                // what the card is "worth" to the crowd drifts slowly
    const x = S.x, un = P.vol * SD * norm(i, T, 3);                                                // degens
    const d = x - fair, umm = -(d > 0 ? P.kup : P.kdn) * d * DT;                                   // market makers fade the move
    const m = S.f - S.s, uf = (m < 0 && x < FLOOR + .35) ? 0 : P.gf * S.h * m * DT;                // FOMO bots chase momentum, but nobody dumps a card that is already near its floor
    const r = x - S.xl[T % 10]; let us = 0;                                                         // snipers react to the last three minutes
    if (r > P.thr && h3(i, T, 21) < .15) us = P.ss * (.5 + h3(i, T, 22)); else if (r < -P.thr && h3(i, T, 23) < .15) us = -P.ss * (.5 + h3(i, T, 22));
    let uw = 0; if (h3(i, T, 24) < P.lw * DT) {                                                     // a whale shows up: buys cards that look cheap, sells cards that look rich
      let size = P.ws * (.4 + 1.6 * h3(i, T, 25)); const pb = Math.min(.9, Math.max(.1, .5 + (fair - x) * .7)), dir = h3(i, T, 26) < pb ? 1 : -1;
      if (dir < 0) size = Math.min(size, .35 * Math.max(0, x - fair)); uw = dir * size; S.h += .5;
    }
    const hb = Math.floor(T / 180); if (hb !== S.hb) { S.bk[S.hb % 24] = S.cur; S.cur = x; S.old = -9; for (let k = 0; k < 24; k++) if (k !== hb % 24) S.old = Math.max(S.old, S.bk[k]); S.hb = hb; }
    const peak = Math.max(S.old, S.cur, x), support = Math.max(FLOOR, peak + DROP);              // the market makers' bids: never under 35% of base, never more than 60% under the last day's high
    let xn = x + un + umm + uf + us + uw; if (xn < support) xn = support; if (xn > hi) xn = hi;
    S.h += -(S.h - 1) * 1.2 * DT + Math.abs(xn - x) * P.hg; S.h = S.h < .3 ? .3 : S.h > 6 ? 6 : S.h;   // attention builds with every move and fades when things go quiet
    S.xl[T % 10] = xn; S.f += (xn - S.f) * AF; S.s += (xn - S.s) * AS; if (xn > S.cur) S.cur = xn; S.x = xn;
    const a1 = Math.abs(un), a2 = Math.abs(umm), a3 = Math.abs(uf); out.abs = (a1 + a2 + a3 + Math.abs(us) + Math.abs(uw)) * (.5 + Math.min(20, 8 * Math.abs(S.f - S.s)));   // trading volume swells when the price is running, up or down
    if (uw) { out.kind = 4; out.z = uw; } else if (us) { out.kind = 3; out.z = us; } else if (a3 > .004) { out.kind = 2; out.z = uf; } else if (a2 > a1) { out.kind = 1; out.z = umm; } else { out.kind = 0; out.z = un; }
    return xn;
  }
  function build() {
    epoch = Math.floor(Date.now() / EPOCH) * EPOCH; t0 = Math.floor((epoch - PRE) / TICK) * TICK; base = t0 / TICK; const t1 = Math.floor((Date.now() - t0) / TICK); cards = CARDS.map((c, i) => {
      const a = TASTE[c.id] - SHIFT[c.rar], x0 = a + norm(i, -1, 1) * .3, S = { a, x: x0, f: x0, s: x0, h: 1, xl: new Float32Array(10).fill(x0), bk: new Float32Array(24).fill(x0), cur: x0, old: x0, hb: Math.floor(base / 180) }, X = new Float32Array(LEN), V = new Float32Array(LEN), K = new Uint8Array(LEN), Z = new Float32Array(LEN);
      X[0] = x0; for (let t = 1; t <= t1; t++) { X[t] = stepOne(S, c, i, base + t); V[t] = out.abs; K[t] = out.kind; Z[t] = out.z; } return { c, S, X, V, K, Z, n: t1 };
    });
  }
  function advance() {
    if (!cards || Math.floor(Date.now() / EPOCH) * EPOCH !== epoch) { build(); return true; }
    const t1 = Math.floor((Date.now() - t0) / TICK); let moved = false;
    for (const m of cards) while (m.n < t1) { m.n++; const i = idx[m.c.no]; m.X[m.n] = stepOne(m.S, m.c, i, base + m.n); m.V[m.n] = out.abs; m.K[m.n] = out.kind; m.Z[m.n] = out.z; moved = true; }
    return moved;
  }
  const M = card => { if (!cards) advance(); return cards[idx[card.no]]; };
  const logAt = (card, back) => { const m = M(card); return m.X[Math.max(0, m.n - back)]; };
  const price = (card, back) => Math.max(1, Math.round(card.val * Math.exp(logAt(card, back || 0))));
  const pct = (card, hours) => Math.exp(logAt(card, 0) - logAt(card, Math.round(hours * 180))) - 1;
  const series = (card, hours, pts) => { const m = M(card), span = Math.round(hours * 180), out = []; for (let k = 0; k < pts; k++) out.push(price(card, Math.round(span * (1 - k / (pts - 1))))); return out; };
  const buzz = card => { const m = M(card), S = m.S; return clamp(Math.round(Math.abs(S.f - S.s) * 3 + Math.max(0, S.x - S.a) * .5 + .4), 0, 5); };   // 0 to 5: how much attention the bots are giving the card right now: it is running, or it is far above where the market makers think it belongs
  // ---- the numbers a trading screen shows, all simulated: market cap, liquidity, volume, buys against sells
  const VOLDAY = {"stitch":59.36,"brick":57.88,"rook":52.63,"orbit":55.27,"phantom":60.5,"null":47.92,"shogun":44.04,"ronin":46.24,"grimm":35.78,"reaper":15.38,"umbra":8.76};   // measured: the average amount of trading a card sees in a day, in the units the bots trade in
  const KV = {}; CARDS.forEach(c => { KV[c.id] = TURN[c.rar] / (VOLDAY[c.id] || 25); });          // volume units to the fraction of the market cap that changes hands (calibrated so a typical day turns over TURN times the cap)
  const mcapAt = (c, m, t) => MCAP[c.id] * Math.exp(m.X[Math.max(0, t)]);                           // market cap in dollars at tick t (index into the path)
  function stats(card) {
    const m = M(card), t = m.n, w = Math.min(4320, t); let vol = 0; for (let k = 0; k < w; k++) { const tt = t - k; vol += m.V[tt] * KV[card.id] * mcapAt(card, m, tt); }
    const net = m.X[t] - m.X[t - w], buyShare = .5 + .4 * Math.tanh(net * .8), mc = mcapAt(card, m, t);   // more buying than selling when the price has been rising
    return { mcap: mc, liq: mc * .06, vol, turn: vol / mc, buyShare, hype: m.S.h };
  }
  const total24 = () => CARDS.reduce((a, c) => a + stats(c).vol, 0);
  // the biggest recent orders from the bots, newest first
  function botFeed(n) {
    const now = nowTick(); let ev = [];
    for (const win of [360, 1080, 4320]) { ev = []; CARDS.forEach((c, i) => { const m = cards[i]; for (let k = 0; k < win; k++) { const t = now - k; if (t < 1) break; ev.push({ t, c, kind: m.K[t], z: m.Z[t], mc: mcapAt(c, m, t) }); } }); if (ev.length >= n) break; }
    return ev.sort((a, b) => Math.abs(b.z * b.mc) - Math.abs(a.z * a.mc)).slice(0, n).sort((a, b) => b.t - a.t).map(e => ({ name: KIND[e.kind] + "-" + (1 + Math.floor(h3(base + e.t, 41, 7) * 99)), card: e.c, buy: e.z > 0, usd: Math.abs(e.z) * e.mc * .06, price: Math.max(1, Math.round(e.c.val * Math.exp(cards[idx[e.c.no]].X[e.t]))), ago: Math.round((now - e.t) / 3), kind: e.kind }));
  }

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
  return { advance, price, pct, series, buzz, feed, flips, runs, stats, total24, botFeed, tick: nowTick, TICK, CAP, BOT, KIND };
})();
