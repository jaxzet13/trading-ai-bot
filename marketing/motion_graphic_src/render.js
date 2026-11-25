const { chromium } = require('playwright');
(async () => {
  const dir = process.argv[2], fps = 30;
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.goto('file://' + dir + '/index.html'); await p.waitForFunction('window.READY===true', null, { timeout: 30000 }); await p.waitForTimeout(500);
  const only = process.argv[3] ? process.argv[3].split(',').map(Number) : null;
  const N = 20 * fps, cv = p.locator('#c');
  for (let i = 0; i < N; i++) { if (only && !only.includes(i)) continue;
    await p.evaluate((t) => window.draw(t), i / fps);
    await cv.screenshot({ path: `${dir}/frames/f_${String(i).padStart(4, '0')}.jpg`, type: 'jpeg', quality: 92 }); }
  console.log('errors', errs); await b.close();
})();
