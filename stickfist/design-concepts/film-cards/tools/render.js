const { chromium } = require('playwright');
const path = require('path');
const DIR = __dirname, OUT = path.join(DIR, 'out');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 2500, height: 1200 }, deviceScaleFactor: 1.6 });
  await p.goto('file://' + path.join(DIR, 'cards.html'));
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(800);
  console.log('fonts', await p.evaluate(() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family).filter((v, i, a) => a.indexOf(v) === i).join(',')));
  for (const id of ['A', 'B']) await (await p.$('#' + id)).screenshot({ path: path.join(OUT, `card_${id}.png`) });
  // booking sheet: three copies, each set by its own serial
  const copies = [[1, 19, -11, 300, 150], [4072, 4072, -6, 290, 172], [88314, 88314, -15, 312, 140]];
  for (const c of copies) {
    await p.evaluate(c => window.setCopy(...c), c);
    await p.waitForTimeout(250);
    await (await p.$('#C')).screenshot({ path: path.join(OUT, `card_C_${c[0]}.png`) });
  }
  await b.close();
})();
