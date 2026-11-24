/* ============================================================================
   4d. WHAT YOUR COPY IS WORTH. There is no shared market: every copy has a value of its own.
   A card always comes out of the pack at its set value (times its style). From the moment you pull it, simulated AI buyers trade that one copy, and its value
   follows them: drifting, rushing up when buyers pile in, dropping when they dump it. Nobody else's copy moves with yours.
   Buyers aren't random about it. Small details of a copy make them keener or cooler: its serial, the letters in its code, its style, and how good the
   picture is. None of that is spelled out anywhere, so learning what buyers like is the skill, and even then a copy can fall.
   Everything is worked out from the copy itself and the clock, so it is the same on every reload and needs no server.
   On average a copy drifts a little down while you hold it, so holding everything is never free money; picking the right ones is.
   ========================================================================== */
const Val = (() => {
  const HOUR = 36e5, FINE = 180;                                                          // the path is set hour by hour, with 20-second wiggles inside each hour
  const LO = Math.log(.04), HI = Math.log(80);                                             // a copy can lose most of its value or go up many times, never to zero or forever
  // how good each picture looks to buyers (hidden): the best-looking art draws more interest
  const LOOK = { stitch: .3, brick: .2, rook: .35, mop: .15, pan: .25, cone: .4, orbit: .55, tempest: .65, phantom: .5, surge: .6, kraken: .9, shogun: .6, null: .45, ronin: .7, grimm: .8, reaper: .85, umbra: 1,
    fuse: .35, spark: .2, flare: .45, bubble: .3, ignition: .5, countdown: .3, gantry: .4, liftoff: .65, booster: .5, apogee: .75, luna: .95 };
  // buyers pull each copy toward what they think it is worth (its goal, set by its details), at about a 3½-day half-life; rushes and dumps knock it off and fade
  const K = { g0: .52, g1: 1, th: .008, sig: .055, u0: .0025, u1: .006, d0: .008, j0: .5, j1: .4, lc: .85, lw: .4 };
  const mix = (a, b, c) => { let h = Math.imul(a ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(b + 0x6a09e667, 0xc2b2ae35) ^ Math.imul(c + 0x3c6ef372, 0x27d4eb2f); h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d); h ^= h >>> 12; h = Math.imul(h, 0x297a2d39); h ^= h >>> 15; return (h >>> 0) / 4294967296; };
  const gauss = (s, a, b) => (mix(s, a, b) + mix(s, a, b + 7919) + mix(s, a, b + 15887) + mix(s, a, b + 23873) - 2) * 1.732;
  // what buyers notice about a copy, and how much each thing is worth to them
  function traits(c) {
    const card = BY_NO[c.no], s = c.serial || 0, ss = String(s), tail = String(c.code || "").slice(-4), out = [];
    if (s === 1) out.push(["first", .55]); else if (s <= 10) out.push(["low", .2]);
    if (ss.length >= 2 && /^(\d)\1+$/.test(ss)) out.push(["repeat", .4]); else if (ss.length >= 3 && ss === [...ss].reverse().join("")) out.push(["mirror", .25]);
    if (/(.)\1/.test(tail)) out.push(["twin", .3]); if (/7/.test(tail)) out.push(["seven", .2]); if (/^[A-Z]{4}$/.test(tail)) out.push(["letters", .1]);
    if (c.fx) out.push(["style", .2 + Math.log10(STYLES[c.fx].x) * .35]);
    out.push(["look", ((LOOK[card.id] != null ? LOOK[card.id] : .45) - K.lc) * K.lw]);
    return out;
  }
  const score = c => traits(c).reduce((a, t) => a + t[1], 0);
  const tierOf = c => RAR[BY_NO[c.no].rar].tier;
  // per hour: the drift, how much it shakes, and how often buyers rush in or dump it
  function params(c) {
    const tier = tierOf(c), q = score(c) - .08 * tier;                                     // rarer cards look better and more often have a style: measured against their own rarity, so no rarity is a sure thing
    const qq = Math.max(-.3, Math.min(2, q));
    return { goal: Math.log(Math.max(.3, K.g0 + K.g1 * qq)), th: K.th, sig: K.sig - tier * .004, pUp: K.u0 + K.u1 * Math.max(0, qq), pDn: K.d0, up: K.j0 + K.j1 * Math.max(0, qq), seed: fnvCopy(c) };
  }
  const fnvCopy = c => fnv("v1:" + (c.code || "") + ":" + (c.uid || ""));
  const cache = new Map();                                                                // per copy: its parameters and the hourly path worked out so far
  function path(c, h) {
    let e = cache.get(c.uid); if (!e) { e = { p: params(c), x: [0], ev: [] }; cache.set(c.uid, e); }
    const { p, x } = e;
    while (x.length <= h + 1) {
      const k = x.length - 1, last = x[k], s = p.seed; let dx = p.th * (p.goal - last) + p.sig * gauss(s, k, 1); const u = mix(s, k, 2), m = mix(s, k, 3);
      if (u < p.pUp) { const j = p.up * (.4 + 3 * m * m * m * m); dx += j; e.ev.push([k + 1, j]); } else if (u < p.pUp + p.pDn) { const j = -(.1 + .35 * m); dx += j; e.ev.push([k + 1, j]); }
      if (last + dx > HI) dx -= (last + dx - HI) * .6; if (last + dx < LO) dx += (LO - last - dx) * .6;
      x.push(last + dx);
    }
    return e;
  }
  // the wiggle inside an hour: a bridge of 20-second steps that starts and ends at zero, so the hourly path is kept exactly
  const fineC = new Map();
  function fine(c, e, h, f) {
    const key = c.uid + ":" + h; let cum = fineC.get(key);
    if (!cum) { if (fineC.size > 600) fineC.clear(); cum = new Float32Array(FINE + 1); for (let i = 0; i < FINE; i++) cum[i + 1] = cum[i] + gauss(e.p.seed, h * 1000 + i, 5); fineC.set(key, cum); }
    const k = Math.min(FINE, Math.floor(f * FINE)); return (cum[k] - k / FINE * cum[FINE]) * e.p.sig * .7 / Math.sqrt(FINE);
  }
  const startOf = c => BY_NO[c.no].val * (c.fx ? STYLES[c.fx].x : 1);                    // what it is worth the moment it comes out of the pack
  function logAt(c, t, rough) {
    const dt = Math.max(0, t - (c.t || t)), h = Math.floor(dt / HOUR), f = dt / HOUR - h, e = path(c, h);
    return e.x[h] + (e.x[h + 1] - e.x[h]) * f + (rough ? 0 : fine(c, e, h, f));
  }
  const at = (c, t, rough) => Math.max(.5, startOf(c) * Math.exp(logAt(c, t, rough)));
  const now = c => at(c, Date.now());
  const pct = (c, hours) => { const t = Date.now(), from = Math.max(c.t || t, t - hours * HOUR); return from >= t ? 0 : now(c) / at(c, from) - 1; };
  function series(c, hours, n) { const t = Date.now(), from = Math.max(c.t || t, t - hours * HOUR), out = []; for (let i = 0; i < n; i++) { const ti = from + (t - from) * i / (n - 1); out.push(at(c, ti, i < n - 1 && hours > 6)); } return out; }
  // what buyers did with this copy lately: their rushes and dumps, newest first
  function moves(c, hours) { const t = Date.now(), dt = t - (c.t || t), h = Math.floor(dt / HOUR); const e = path(c, h); return e.ev.filter(([k]) => k <= h && (h - k) <= hours).map(([k, j]) => ({ ago: h - k, pct: Math.exp(j) - 1 })).reverse(); }
  // how many simulated buyers are watching it right now (flavour, from its interest and its last day)
  const watching = c => { const q = score(c), mo = pct(c, 24); return Math.max(0, Math.round(3 + 9 * Math.max(0, q) + 12 * Math.max(-.3, Math.min(1.5, mo)) + 3 * Math.sin(Date.now() / 9e5 + fnvCopy(c) % 7))); };
  return { now, at, pct, series, moves, startOf, watching, traits, score, params, K };
})();
