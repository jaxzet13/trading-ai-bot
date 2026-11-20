// Lay out base-style cards: name, copy ID with rarity cuts, and the physical corner cuts (one per "/")
const { chromium } = require('playwright'); const path = require('path'); const fs = require('fs');
const OUT = process.argv[2];
const LIST = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));      // [{no, serial, art, tier, label?}]
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1700, height: 1300 }, deviceScaleFactor: 2 });
  await p.addInitScript(() => { localStorage.setItem('stickfist-rips-v3', JSON.stringify({ ageOK: true, coins: 900, tokens: 0, vault: [], history: [{ t: 1, text: 'x', delta: 0 }], serial: 1, netlog: [], s: {} })); });
  await p.goto('file:///home/user/trading-ai-bot/stickfist/_test.html'); await p.waitForTimeout(900);
  const data = await p.evaluate((list) => { const P = window.STIXX_PRINT; return list.map(x => { const c = P.CARD_BY_NO[x.no]; const f = P.BY_ID[c.id];
    return { ...x, name: x.name || f.name, code: P.cardCode(c, x.serial), mark: x.mark != null ? x.mark : P.rarMark(c.rar).length, rname: P.crOf(c).name }; }); }, LIST);
  const cut = (n) => { const c = 70, w = 750, h = 1050; const pts = [[0, 0], [w, 0], [w, h], [0, h]];
    // corners in order: TR, BL, TL
    const order = ['tr', 'bl', 'tl'].slice(0, n); const has = k => order.includes(k);
    const poly = [];
    poly.push(has('tl') ? [0, c] : [0, 0]); if (has('tl')) poly.push([c, 0]);
    poly.push(has('tr') ? [w - c, 0] : [w, 0]); if (has('tr')) poly.push([w, c]);
    poly.push(has('br') ? [w, h - c] : [w, h]); if (has('br')) poly.push([w - c, h]);
    poly.push(has('bl') ? [c, h] : [0, h]); if (has('bl')) poly.push([0, h - c]);
    return 'polygon(' + poly.map(q => q[0] + 'px ' + q[1] + 'px').join(',') + ')'; };
  const cards = data.map((d, i) => { const inv = ['R', 'H', 'RR'].includes(d.tier);
    const nameCol = d.tier === 'H' ? 'linear-gradient(180deg,#fafbfd,#a7abb5 45%,#f1f2f6)' : d.tier === 'RR' ? 'linear-gradient(180deg,#fff0c4,#c9983f 48%,#ffe3a0)' : inv ? '#ece6d9' : '#0b0b0c';
    const grad = d.tier === 'H' || d.tier === 'RR';
    return `<div class="wrap"><div class="card t${d.tier}" style="clip-path:${cut(d.mark)}"><img class="art" src="${d.art}">
      <div class="nm" style="${grad ? `background:${nameCol};-webkit-background-clip:text;background-clip:text;color:transparent;` : `color:${nameCol};`}">${d.name}</div>
      <div class="id">${d.code}${d.mark ? `<i>${'/'.repeat(d.mark)}</i>` : ''}</div></div>${d.label ? `<div class="lab">${d.label}</div>` : ''}</div>`; }).join('');
  const html = `<!doctype html><html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet"><style>
*{box-sizing:border-box;margin:0;padding:0}body{background:#1b1b1d;padding:24px;display:flex;flex-wrap:wrap;gap:24px;width:max-content}
.wrap{position:relative;flex:none}.card{width:750px;height:1050px;position:relative;overflow:hidden;background:#000}
.art{position:absolute;inset:0;width:100%;height:100%}
.nm{position:absolute;left:44px;top:34px;font-family:Archivo;font-weight:900;font-stretch:62%;font-variation-settings:'wdth' 62;line-height:.8;text-transform:uppercase;white-space:nowrap}
.tC .nm,.tU .nm{text-shadow:0 0 18px rgba(236,230,214,.95),0 0 6px rgba(236,230,214,.9)}.tR .nm{text-shadow:0 0 18px rgba(10,10,12,.9)}
.id{position:absolute;left:0;right:0;bottom:30px;text-align:center;font-family:'IBM Plex Mono';font-weight:600;font-size:14px;letter-spacing:.36em;white-space:nowrap}
.tC .id,.tU .id{color:#1c1b1a;text-shadow:0 0 10px rgba(236,230,214,.95)}.tR .id{color:#cfc9bc}.tH .id{color:#c3c6ce}.tRR .id{color:#e2c07a}
.id i{font-style:normal;font-weight:700;color:#d11a24;margin-left:.5em;letter-spacing:.04em}
.lab{position:absolute;left:0;right:0;bottom:-22px;text-align:center;font:600 13px 'IBM Plex Mono';letter-spacing:.2em;color:#8a867c}
</style></head><body>${cards}</body></html>`;
  await p.setContent(html); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(900);
  await p.evaluate(() => { for (const h of document.querySelectorAll('.nm')) { let fs = 200; h.style.fontSize = fs + 'px'; const r = document.createRange(); r.selectNodeContents(h); while (r.getBoundingClientRect().width > 560 && fs > 60) { fs -= 2; h.style.fontSize = fs + 'px'; } } });
  await p.waitForTimeout(300);
  const els = await p.$$('.card');
  for (let i = 0; i < els.length; i++) await els[i].screenshot({ path: path.join(OUT, `card_${i}.png`), omitBackground: true });
  fs.writeFileSync(path.join(OUT, 'data.json'), JSON.stringify(data)); console.log('cards', els.length); await b.close();
})();
