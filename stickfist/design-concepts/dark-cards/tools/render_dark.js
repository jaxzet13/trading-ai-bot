const { chromium } = require('playwright');
const path = require('path');
const DIR = __dirname, OUT = path.join(DIR, 'out');
const page = process.argv[2] || 'dark.html';
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1700, height: 1200 }, deviceScaleFactor: 2 });   // 1500 x 2100 = 600 dpi
  await p.goto('file://' + path.join(DIR, page));
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(700);
  for (const el of await p.$$('.card')) {
    const id = await el.getAttribute('id');
    await el.screenshot({ path: path.join(OUT, `card_${id}.png`) });
    console.log('card', id);
  }
  await b.close();
})();
