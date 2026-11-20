// Final layer for grain-print cards: the grain image fills the card; the copy ID (crisp, small) and the
// physical corner cuts go on top. The NAME is already inside the grain image (printed through it).
// usage: node grain_cards.js OUTDIR LIST.json   (list: [{no, serial, art, tint, idpos}])
const { chromium } = require('playwright'); const path = require('path'); const fs = require('fs');
const OUT = process.argv[2]; const LIST = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const TINT = { bw: '#ece7dc', blue: '#eeeadb', red: '#efe4d8', olive: '#e1e6c0', brass: '#f4dca0' };
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1700, height: 1300 }, deviceScaleFactor: 2 });
  await p.addInitScript(() => { localStorage.setItem('stickfist-rips-v3', JSON.stringify({ ageOK: true, coins: 900, tokens: 0, vault: [], history: [{ t: 1, text: 'x', delta: 0 }], serial: 1, netlog: [], s: {} })); });
  await p.goto('file:///home/user/trading-ai-bot/stickfist/_test.html'); await p.waitForTimeout(900);
  const data = await p.evaluate(list => { const P = window.STIXX_PRINT; return list.map(x => { const c = P.CARD_BY_NO[x.no]; return { ...x, code: P.cardCode(c, x.serial), mark: P.rarMark(c.rar).length }; }); }, LIST);
  const cut = (n) => { const c = 70, w = 750, h = 1050; const order = ['tr', 'bl', 'tl'].slice(0, n), has = k => order.includes(k), poly = [];
    poly.push(has('tl') ? [0, c] : [0, 0]); if (has('tl')) poly.push([c, 0]);
    poly.push(has('tr') ? [w - c, 0] : [w, 0]); if (has('tr')) poly.push([w, c]);
    poly.push([w, h]); poly.push(has('bl') ? [c, h] : [0, h]); if (has('bl')) poly.push([0, h - c]);
    return 'polygon(' + poly.map(q => q[0] + 'px ' + q[1] + 'px').join(',') + ')'; };
  const cards = data.map(d => `<div class="card" style="clip-path:${cut(d.mark)}"><img src="${d.art}">
    <div class="id ${d.idpos === 'top' ? 'top' : ''}" style="color:${TINT[d.tint] || TINT.bw}">${d.code}${d.mark ? `<i>${'/'.repeat(d.mark)}</i>` : ''}</div></div>`).join('');
  await p.setContent(`<!doctype html><html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet"><style>
    *{margin:0;padding:0;box-sizing:border-box}body{background:#161617;padding:24px;display:flex;gap:24px;width:max-content}
    .card{width:750px;height:1050px;position:relative;overflow:hidden;background:#000;flex:none}.card img{position:absolute;inset:0;width:100%;height:100%}
    .card::after{content:'';position:absolute;left:0;right:0;bottom:0;height:70px;background:linear-gradient(0deg,rgba(0,0,0,.92),rgba(0,0,0,.6) 55%,rgba(0,0,0,0));pointer-events:none}
    .id{z-index:2;position:absolute;left:0;right:0;bottom:16px;text-align:center;font:600 13px 'IBM Plex Mono';letter-spacing:.38em;white-space:nowrap;text-shadow:0 0 6px #000,0 0 12px #000;opacity:.9}
    .id.top{bottom:auto;top:26px}.id i{font-style:normal;font-weight:700;color:#e0202c;margin-left:.5em;letter-spacing:.04em}
  </style></head><body>${cards}</body></html>`);
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(800);
  const els = await p.$$('.card');
  for (let i = 0; i < els.length; i++) await els[i].screenshot({ path: path.join(OUT, `card_${i}.png`), omitBackground: true });
  await b.close(); console.log('cards', els.length);
})();
