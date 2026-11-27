// solves every style of every pack: the rare slot's bins keep Triumph's percentages, and the split of the top bin between its two cards is set so the pack returns 94.7%
const fs = require('fs'), path = require('path'), src = fs.readFileSync(path.join(__dirname, '../../src/js/01-data.js'), 'utf8');
let i = src.indexOf('const STYLES = {'), d = 0, j = i + 15; for (; j < src.length; j++) { const c = src[j]; if (c === '{') d++; if (c === '}') { d--; if (!d) break; } } const STYLES = eval('(' + src.slice(i + 15, j + 1) + ')');
const roster = JSON.parse(fs.readFileSync(path.join(__dirname, 'roster.json'), 'utf8')), Q = { fp: .0, ms: .0, ec: .0, td: .0, sg: .0 }, SB = .9, U = 500, out = {};
for (const P of roster) {
  const price = P.price * U, V = {}, styled = {}; for (const c of P.fill.concat(P.rare)) { V[c.id] = c.val; styled[c.id] = !!c.existing; }
  const sellFor = (val, m) => Math.floor(Math.max(1, Math.round(val * m)) * SB);
  const cardEV = id => { let e = 0, rest = 1; if (styled[id]) for (const k in STYLES) { e += sellFor(V[id], STYLES[k].x) * STYLES[k].p; rest -= STYLES[k].p; } return e + sellFor(V[id], 1) * rest; };
  const slotEV = slot => { const t = slot.reduce((a, [, w]) => a + w, 0); return slot.reduce((a, [id, w]) => a + cardEV(id) * w / t, 0); };
  const commons = P.fill.filter(c => c.kind === 'common'), uncs = P.fill.filter(c => c.kind === 'uncommon'), fillRaw = commons.map(c => [c.id, 1]).concat(uncs.map(c => [c.id, .5])), ft = fillRaw.reduce((a, b) => a + b[1], 0), fill = fillRaw.map(([id, w]) => [id, w / ft * 100]);
  const rare = P.rare, A = rare.find(c => c.bin === 5 && !c.top), B = rare.find(c => c.top), low = rare.filter(c => c.bin < 5).sort((a, b) => a.val - b.val).slice(0, 4).map(c => c.id), q = Q[P.pack];
  const bonus = fill.map(([id, w]) => [id, w * (1 - q)]).concat(low.map(id => [id, q * 100 / low.length]));
  out[P.pack] = {};
  for (const st of ['normal', 'high', 'max']) {
    const pct = P.pct[st], build = al => { const rs = rare.map(c => [c.id, c.bin < 5 ? pct[c.bin] : c.top ? pct[5] * al : pct[5] * (1 - al)]).map(([id, w]) => [id, w * 100]); return { rs, slots: [fill, fill, fill, fill, rs, bonus, bonus] }; };
    const ev = al => build(al).slots.reduce((a, s) => a + slotEV(s), 0) / price, e0 = ev(0), e1 = ev(1);
    if (e0 > .947 || e1 < .947) { console.log(P.pack, st, 'NO FIT', e0.toFixed(3), e1.toFixed(3)); out[P.pack][st] = build(e0 > .947 ? 0 : 1).slots; continue; }
    let lo = 0, hi = 1; for (let k = 0; k < 50; k++) { const m = (lo + hi) / 2; if (ev(m) < .947) lo = m; else hi = m; }
    const al = (lo + hi) / 2, { rs, slots } = build(al); out[P.pack][st] = slots.map(s => s.map(([id, w]) => [id, +w.toFixed(5)]));
    console.log(P.pack.padEnd(3), st.padEnd(6), '$' + P.price, '| return', (ev(al) * 100).toFixed(1) + '% | top card at 1 in', Math.round(100 / (pct[5] * al * 100)), '| A:B', ((1 - al) * 100).toFixed(0) + '/' + (al * 100).toFixed(0));
  }
}
fs.writeFileSync(path.join(__dirname, 'slots.json'), JSON.stringify(out));
