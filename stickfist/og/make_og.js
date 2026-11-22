// node make_og.js  ->  ../og.png (1200x630), the picture shown when an invite link is shared
const { chromium } = require('playwright'); const path = require('path');
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
  await p.goto('file://' + path.join(__dirname, 'og.html')); await p.waitForTimeout(800); await p.screenshot({ path: path.join(__dirname, '..', 'og.png') }); await b.close(); console.log('og.png written'); })();
