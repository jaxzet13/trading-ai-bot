// Draws each glyph scene as a still (900 x 1092) so it can become the card's text picture:  node stills.js <outdir>
const { chromium } = require('playwright'); const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '../../src/js/06c-glyph.js'), 'utf8').split('/* ---- the player')[0];
(async () => { const out = process.argv[2] || path.join(__dirname, '../paint/sources'); fs.mkdirSync(out, { recursive: true }); const b = await chromium.launch(); const p = await b.newPage();
  await p.setContent('<canvas id="c" width="900" height="1092"></canvas>'); await p.addScriptTag({ content: src + ';window.GS = GlyphScenes;' });
  for (const id of ['morpho', 'heartword', 'bouquet', 'candle', 'phoenix']) {
    const data = await p.evaluate(id => { const c = document.getElementById('c'), g = c.getContext('2d'); g.setTransform(1, 0, 0, 1, 0, 0); g.fillStyle = '#030304'; g.fillRect(0, 0, 900, 1092); g.setTransform(9, 0, 0, 9, 0, 0); GS[id](g, GS.STILL[id] + 1.2, 100, 121.33); return c.toDataURL('image/png'); }, id);
    fs.writeFileSync(path.join(out, id + '.png'), Buffer.from(data.split(',')[1], 'base64')); console.log(id);
  } await b.close(); })();
