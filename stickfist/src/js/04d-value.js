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
  const HOUR = 36e5;                                                          // the slow path is set hour by hour; the fast layer below moves it every half second
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
  /* ---- the fast layer: half a second at a time, like a coin that has just launched ----
     On top of the hourly path every copy has a price that never sits still. Three things move it:
       1. a random walk in the log of the price that starts hot (about 1.6% a second in its first minutes) and settles to
          about 0.12% a second for good;
       2. hot streaks: now and then buyers crowd one copy for two minutes and it shakes about 0.8% a second;
       3. pumps and rugs: once in a while a copy runs up (anything from +35% to more than four times, over ten to
          thirty-five seconds) or is dumped in a single tick. They come most often in a copy's first minutes.
     All three are fair. The walk has no pull back to where it was and its average is exactly flat (the log drifts down by half
     its variance); a pump is paid for by a slow bleed between pumps, sized so that the average stays flat at every moment,
     not just in the long run. That matters: with a wave you could wait for the top and beat the selling fee; here no way of
     timing a sale pays on average. A pump is shown as a climb, never ahead of itself, and a rug lands at once, so what is on
     the screen is never worth more than the fair price behind it. Most copies bleed and a few moon. Nothing here changes what a
     pack returns: a card still comes out at its set value.
     Everything is worked out from the copy and the clock alone (the walk is a bridge split in halves down to half a second),
     so any moment can be read without storing anything, and it is the same on every reload. */
  const VA = .0012 * .0012, VB = .016 * .016, VT = 200, LV = 26, SPAN = Math.pow(2, LV);     // variance a second for good, extra at launch, how fast the launch fades (s), and the walk's length in half-seconds (about a year)
  const tau = sec => VA * sec + VB * VT * Math.log(1 + sec / VT);                           // how much the walk has varied by `sec` seconds after the pull
  const walkC = new Map();
  function walk(seed, n) {
    if (n <= 0) return 0; if (n >= SPAN) n = SPAN - 1; const key = (seed & 0x7ffffff) * SPAN + n; let hit = walkC.get(key); if (hit !== undefined) return hit;
    const sd = seed ^ 0x5bd1e995; let lo = 0, hi = SPAN, tl = 0, th = tau(SPAN / 2), wl = 0, wh = gauss(sd, SPAN, 99) * Math.sqrt(th), out = 0, done = false;
    for (let lv = 0; lv < LV && !done; lv++) { const mid = (lo + hi) / 2, tm = tau(mid / 2), wm = wl + (tm - tl) / (th - tl) * (wh - wl) + Math.sqrt((tm - tl) * (th - tm) / (th - tl)) * gauss(sd, mid, lv);
      if (n === mid) { out = wm; done = true; } else if (n < mid) { hi = mid; wh = wm; th = tm; } else { lo = mid; wl = wm; tl = tm; } }
    if (!done) out = wl; if (walkC.size > 80000) walkC.clear(); walkC.set(key, out); return out;
  }
  // two-minute slots after the pull: each may hold a pump, a rug or a hot streak
  const BK = 120, CH = 16, HT = 128, HV = .008 * .008 * BK;
  const pP = k => .08 / ((1 + k / 2) * (1 + k / 2)) + .00004, pH = k => .006 + .06 / (1 + k / 30), DR = .5;   // the chance of a pump in slot k (a rug is half as likely), and of a hot streak
  const sizeP = m => .3 + 1.2 * m * m * m, sizeD = m => .15 + .5 * m;
  let EG = 0; { let a = 0, b = 0; const N = 4000; for (let i = 0; i < N; i++) { const m = (i + .5) / N; a += Math.exp(sizeP(m)); b += Math.exp(-sizeD(m)); } EG = (a / N + DR * b / N) / (1 + DR) - 1; }   // what a jump is worth on average, less one: the bleed that pays for it
  function slot(sd, k) {                                                                  // what happens in slot k: [jump, where in the slot (0..1), the slot's bleed, the climb in seconds, the hot streak's move]
    const p = pP(k), pj = p * (1 + DR), u = mix(sd, k, 31); let j = 0, U = 1, ramp = 0;
    if (u < pj) { const m = mix(sd, k, 32); U = mix(sd, k, 33); if (u < p) { j = sizeP(m); ramp = 10 + 25 * mix(sd, k, 36); } else j = -sizeD(m); }
    return { j, U, p: pj, drift: EG * Math.log(1 - pj * U), ramp, hot: mix(sd, k, 34) < pH(k) ? gauss(sd, k, 35) * Math.sqrt(HV) : null };
  }
  const slotEnd = e => e.j + e.drift + (e.hot == null ? 0 : e.hot - HV / 2);
  const cps = new Map(), slotC = new Map();
  function slotOf(sd, k) { const key = (sd & 0x7ffffff) * 4194304 + k; let e = slotC.get(key); if (!e) { if (slotC.size > 20000) slotC.clear(); e = slot(sd, k); slotC.set(key, e); } return e; }
  function before(sd, k) {                                                                // everything the slots before k added up to
    let cp = cps.get(sd); if (!cp) { cp = [0]; cps.set(sd, cp); } const i = Math.floor(k / CH);
    while (cp.length <= i) { let s = cp[cp.length - 1]; const from = (cp.length - 1) * CH; for (let q = from; q < from + CH; q++) s += slotEnd(slotOf(sd, q)); cp.push(s); }
    let s = cp[i]; for (let q = i * CH; q < k; q++) s += slotEnd(slotOf(sd, q)); return s;
  }
  function hotAt(sd, k, f, end) {                                                         // a hot streak, part of the way through: a bridge to where it ends
    const x = f * HT, n = Math.floor(x), fr = x - n, at = q => { if (q <= 0) return 0; if (q >= HT) return end; let lo = 0, hi = HT, wl = 0, wh = end;
      for (let lv = 0; lv < 7; lv++) { const mid = (lo + hi) / 2, wm = (wl + wh) / 2 + Math.sqrt((hi - lo) / 4 / HT * HV) * gauss(sd ^ 0x1b873593, k * HT + mid, lv); if (q === mid) return wm; if (q < mid) { hi = mid; wh = wm; } else { lo = mid; wl = wm; } } return wl; };
    const a = at(n); return (fr ? a + (at(n + 1) - a) * fr : a) - HV * f / 2;
  }
  const ease = x => x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x);
  function events(seed, sec) {
    const sd = seed ^ 0x2545f491, k = Math.floor(sec / BK), f = sec / BK - k, e = slotOf(sd, k); let v = before(sd, k);
    if (f >= e.U) { v += e.drift + e.j; if (e.ramp) v -= e.j * (1 - ease((f - e.U) * BK / e.ramp)); } else v += EG * Math.log(1 - e.p * f);
    if (e.hot != null) v += hotAt(sd, k, f, e.hot);
    if (k > 0) { const w = slotOf(sd, k - 1); if (w.ramp) { const since = (1 - w.U + f) * BK; if (since < w.ramp) v -= w.j * (1 - ease(since / w.ramp)); } }   // a climb that started late in the last slot is still going
    return v;
  }
  // is this copy running right now? { j: how far the run goes in all (log), q: how much of it is done }
  function surge(c, t) {
    t = t || Date.now(); const sec = Math.max(0, t - (c.t || t)) / 1000, sd = fnvCopy(c) ^ 0x2545f491, k = Math.floor(sec / BK), f = sec / BK - k;
    for (const [e, since] of [[slotOf(sd, k), (f - 0) * BK], k > 0 ? [slotOf(sd, k - 1), (1 + f) * BK] : null].filter(Boolean)) { const s = since - e.U * BK; if (e.ramp && s >= 0 && s < e.ramp) return { j: e.j, q: s / e.ramp }; }
    return null;
  }
  const CALM = 6;                                                                         // a copy holds its starting value for its first six seconds, so a card is seen at what it is worth before it starts to move
  function fast(seed, sec) { sec -= CALM; if (sec <= 0) return 0; const x = sec * 2, n = Math.floor(x), f = x - n, a = walk(seed, n); return (f ? a + (walk(seed, n + 1) - a) * f : a) - tau(sec) / 2 + events(seed, sec); }
  const startOf = c => BY_NO[c.no].val * (c.fx ? STYLES[c.fx].x : 1);                    // what it is worth the moment it comes out of the pack
  function logAt(c, t, rough) {
    const dt = Math.max(0, t - (c.t || t)), h = Math.floor(dt / HOUR), f = dt / HOUR - h, e = path(c, h);
    return Math.max(LO, Math.min(HI, e.x[h] + (e.x[h + 1] - e.x[h]) * f + fast(e.p.seed, dt / 1000)));
  }
  const at = (c, t) => Math.max(.5, startOf(c) * Math.exp(logAt(c, t)));
  // the last `n` candles of `step` seconds up to now: open, high, low, close (null before the copy existed)
  function candles(c, step, n, tNow) {
    const ms = step * 1000, end = Math.ceil(tNow / ms) * ms, t0 = c.t || tNow, k = Math.min(10, Math.max(2, step * 2)), out = [];
    for (let i = n - 1; i >= 0; i--) { const a0 = end - (i + 1) * ms, b = Math.min(a0 + ms, tNow); if (b <= t0) { out.push(null); continue; } const from = Math.max(a0, t0); let o = at(c, from), hi = o, lo = o, cl = o;
      for (let q = 1; q <= k; q++) { const v = at(c, from + (b - from) * q / k); if (v > hi) hi = v; if (v < lo) lo = v; cl = v; } out.push({ t: a0, o, h: hi, l: lo, c: cl }); }
    return out;
  }
  const now = c => at(c, Date.now());
  const pctSec = (c, sec) => { const t = Date.now(), from = Math.max(c.t || t, t - sec * 1000); return from >= t ? 0 : now(c) / at(c, from) - 1; };
  const pct = (c, hours) => { const t = Date.now(), from = Math.max(c.t || t, t - hours * HOUR); return from >= t ? 0 : now(c) / at(c, from) - 1; };
  function series(c, hours, n) { const t = Date.now(), from = Math.max(c.t || t, t - hours * HOUR), out = []; for (let i = 0; i < n; i++) { const ti = from + (t - from) * i / (n - 1); out.push(at(c, ti)); } return out; }
  // what buyers did with this copy lately: their rushes and dumps, newest first
  function moves(c, hours) { const t = Date.now(), dt = t - (c.t || t), h = Math.floor(dt / HOUR); const e = path(c, h); return e.ev.filter(([k]) => k <= h && (h - k) <= hours).map(([k, j]) => ({ ago: h - k, pct: Math.exp(j) - 1 })).reverse(); }
  // how many simulated buyers are watching it right now (flavour, from its interest and its last day)
  const watching = c => { const q = score(c), mo = pct(c, 24); return Math.max(0, Math.round(3 + 9 * Math.max(0, q) + 12 * Math.max(-.3, Math.min(1.5, mo)) + 3 * Math.sin(Date.now() / 9e5 + fnvCopy(c) % 7))); };
  return { now, at, pct, pctSec, surge, series, candles, moves, startOf, watching, traits, score, params, K };
})();
