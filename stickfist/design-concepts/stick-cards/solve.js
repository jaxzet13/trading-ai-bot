// solves each pack's odds for the roster: the rare slot's weights are set so that the pack returns just under 95%
const fs = require('fs'), path = require('path'), src = fs.readFileSync(path.join(__dirname, '../../src/js/01-data.js'), 'utf8');
let i = src.indexOf('const STYLES = {'), d = 0, j = i + 15; for (; j < src.length; j++) { const c = src[j]; if (c === '{') d++; if (c === '}') { d--; if (!d) break; } } const STYLES = eval('(' + src.slice(i + 15, j + 1) + ')');
const roster = JSON.parse(fs.readFileSync(path.join(__dirname, 'roster.json'), 'utf8')), PRICE = { fp: 1, ms: 3, ec: 8, td: 20, sg: 50 }, Q = { fp: .08, ms: .14, ec: .20, td: .28, sg: .38 }, SB = .9, U = 500;
const out = {};
for (const P of roster) {
  const price = PRICE[P.pack] * U, V = {}, styled = {}; for (const c of P.fill.concat(P.rare)) { V[c.id] = c.val; styled[c.id] = !!c.existing; }
  const sellFor = (val, m) => Math.floor(Math.max(1, Math.round(val * m)) * SB);
  const cardSells = id => { const m = new Map(), add = (k, p) => m.set(k, (m.get(k) || 0) + p); let rest = 1; if (styled[id]) for (const k in STYLES) { add(sellFor(V[id], STYLES[k].x), STYLES[k].p); rest -= STYLES[k].p; } add(sellFor(V[id], 1), rest); return m; };
  const slotSells = slot => { const t = slot.reduce((a, [, w]) => a + w, 0), sd = new Map(); for (const [id, w] of slot) for (const [v, p] of cardSells(id)) sd.set(v, (sd.get(v) || 0) + w / t * p); return sd; };
  const ev = slots => slots.reduce((a, s) => { let e = 0; for (const [v, p] of slotSells(s)) e += v * p; return a + e; }, 0);
  function dist(slots, cap) { let dd = new Float64Array(cap + 1); dd[0] = 1; for (const slot of slots) { const nx = new Float64Array(cap + 1); let all = 0; for (let k = 0; k <= cap; k++) all += dd[k]; for (const [v, p] of slotSells(slot)) { if (v >= cap) { nx[cap] += p * all; continue; } let over = 0; for (let k = 0; k <= cap; k++) { const q = dd[k]; if (!q) continue; if (k + v >= cap) over += q; else nx[k + v] += p * q; } nx[cap] += p * over; } dd = nx; } return dd; }
  const commons = P.fill.filter(c => c.kind === 'common'), uncs = P.fill.filter(c => c.kind === 'uncommon');
  const fillRaw = commons.map(c => [c.id, 1]).concat(uncs.map(c => [c.id, .5])), ft = fillRaw.reduce((a, b) => a + b[1], 0), fill = fillRaw.map(([id, w]) => [id, w / ft * 100]);
  const rarePool = P.rare.slice().sort((a, b) => a.val - b.val).map(c => c.id), low = rarePool.slice(0, 4), q = Q[P.pack];
  const bonus = fill.map(([id, w]) => [id, w * (1 - q)]).concat(low.map(id => [id, q * 100 / low.length]));
  const build = r => { const w = rarePool.map((id, k) => [id, Math.pow(r, k)]), t = w.reduce((a, b) => a + b[1], 0), rare = w.map(([id, x]) => [id, x / t * 100]); return { rare, slots: [fill, fill, fill, fill, rare, bonus, bonus] }; };
  const e1 = ev(build(1).slots) / price, e0 = ev(build(.02).slots) / price; if (e1 < .947 || e0 > .947) { console.log(P.pack, 'no fit', e0.toFixed(2), e1.toFixed(2)); continue; }
  let lo = .02, hi = 1; for (let k = 0; k < 40; k++) { const mid = (lo + hi) / 2; if (ev(build(mid).slots) / price < .947) lo = mid; else hi = mid; }
  const { rare, slots } = build((lo + hi) / 2), dd = dist(slots, price * 4); let hit = 0, x2 = 0, acc = 0, med = 0; for (let k = price; k <= price * 4; k++) hit += dd[k]; for (let k = price * 2; k <= price * 4; k++) x2 += dd[k]; for (let k = 0; k <= price * 4; k++) { acc += dd[k]; if (acc >= .5) { med = k; break; } }
  console.log(P.pack.padEnd(3), '$' + PRICE[P.pack], '| return', (ev(slots) / price * 100).toFixed(1) + '% | sells back the price or more', (hit * 100).toFixed(1) + '% | 2x+', (x2 * 100).toFixed(1) + '% | median $' + (med / U).toFixed(2), '| top card', (Math.max(...P.rare.map(c => c.val)) / U), 'at 1 in', Math.round(100 / rare[rare.length - 1][1]));
  out[P.pack] = slots.map(s => s.map(([id, w]) => [id, +w.toFixed(4)]));
}
fs.writeFileSync(path.join(__dirname, 'slots.json'), JSON.stringify(out));
