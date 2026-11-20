const { chromium } = require('playwright'); const path = require('path');
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1700, height: 2300 }, deviceScaleFactor: 2 });
  await p.goto('file://' + path.join(__dirname, 'four.html')); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(900);
  for (const id of ['A', 'B', 'C', 'D']) await (await p.$('#' + id)).screenshot({ path: path.join(__dirname, 'out', 'four_' + id + '.png') });
  await b.close(); console.log('ok'); })();
