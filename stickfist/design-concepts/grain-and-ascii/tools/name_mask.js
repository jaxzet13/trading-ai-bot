// Render the card name as a white-on-black mask (1500x2100) so it can be printed through the grain pass.
// usage: node name_mask.js JOBS.json   (jobs: [{out, text, font, weight, size, tracking, y, align, x, maxw, italic}])
const { chromium } = require('playwright'); const fs = require('fs');
const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1500, height: 2100 }, deviceScaleFactor: 1 });
  const fams = [...new Set(jobs.map(j => j.font))].map(f => 'family=' + f.replace(/ /g, '+') + ':wght@400;500;600;700;800;900').join('&');
  for (const j of jobs) {
    const html = `<!doctype html><html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?${fams}&display=swap" rel="stylesheet"><style>
      *{margin:0;padding:0}body{background:#000;width:1500px;height:2100px;position:relative;overflow:hidden}
      #t{position:absolute;white-space:nowrap;color:#fff;font-family:'${j.font}';font-weight:${j.weight || 700};font-size:${j.size || 220}px;letter-spacing:${j.tracking || 0}em;line-height:1;text-transform:${j.upper === false ? 'none' : 'uppercase'};${j.italic ? 'font-style:italic;' : ''}}
    </style></head><body><div id="t">${j.text}</div></body></html>`;
    await p.setContent(html); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(500);
    await p.evaluate(({ maxw, align, x, y, bottom }) => {
      const t = document.getElementById('t'); let fs = parseFloat(getComputedStyle(t).fontSize);
      while (t.getBoundingClientRect().width > maxw && fs > 40) { fs -= 2; t.style.fontSize = fs + 'px'; }
      const w = t.getBoundingClientRect().width;
      t.style.left = (align === 'left' ? x : align === 'right' ? 1500 - x - w : (1500 - w) / 2) + 'px'; t.style.top = (bottom ? bottom - t.getBoundingClientRect().height : y) + 'px';
    }, { maxw: j.maxw || 1180, align: j.align || 'center', x: j.x || 110, y: j.y || 1650, bottom: j.bottom || 0 });
    await p.screenshot({ path: j.out });
  }
  await b.close(); console.log('masks', jobs.length);
})();
