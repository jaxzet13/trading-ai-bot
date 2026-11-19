const { chromium } = require('playwright');
const path = require('path');
const head = process.argv[2];
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 900, height: 1200 }, deviceScaleFactor: 2 });
  await p.goto('file://' + path.join(__dirname, 'blender.html') + '?head=' + head);
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(600);
  await (await p.$('#BL')).screenshot({ path: path.join(__dirname, 'out', 'card_BL.png') });
  await b.close(); console.log('ok');
})();
