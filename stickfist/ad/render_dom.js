// Renders a film that is a web page (ad3.html), one screenshot per frame.
//   node render_dom.js shots <t1,t2,...> <outdir>      stills at those moments
//   node render_dom.js video <outdir> [workers]        every frame as JPEG in <outdir>/frames, plus <outdir>/timeline.json for the audio script
// The page is 540x960 CSS pixels at 2x, so frames are 1080x1920. AD_FILE picks the page (default ad3.html). Needs playwright with chromium.
const { chromium } = require("playwright"); const fs = require("fs"); const path = require("path"); const http = require("http");
const ROOT = path.resolve(__dirname, ".."); const MIME = { ".html": "text/html", ".jpg": "image/jpeg", ".png": "image/png", ".js": "text/javascript", ".css": "text/css" };
const server = http.createServer((q, r) => { const f = path.join(ROOT, decodeURIComponent(q.url.split("?")[0])); if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { r.statusCode = 404; return r.end(); } r.setHeader("content-type", MIME[path.extname(f)] || "application/octet-stream"); fs.createReadStream(f).pipe(r); });
const [mode, a1, a2] = process.argv.slice(2);
(async () => {
  await new Promise(r => server.listen(0, "127.0.0.1", r)); const port = server.address().port, b = await chromium.launch();
  const open = async () => { const ctx = await b.newContext({ viewport: { width: 540, height: 960 }, deviceScaleFactor: 2 }); const p = await ctx.newPage(); p.on("pageerror", e => console.log("PAGEERR", e.message)); p.on("console", m => { if (m.type() === "error" && !/fonts\.g|Failed to load resource/.test(m.text())) console.log("CON", m.text()); }); await p.goto(`http://127.0.0.1:${port}/ad/${process.env.AD_FILE || "ad3.html"}`); await p.evaluate(() => window.READY); return p; };
  const shot = async (p, t, file, q) => { await p.evaluate(t => window.renderAt(t), t); await p.screenshot({ path: file, type: "jpeg", quality: q || 92 }); };
  if (mode === "shots") { const ts = a1.split(",").map(Number), dir = a2; fs.mkdirSync(dir, { recursive: true }); const p = await open(); for (const t of ts) await shot(p, t, path.join(dir, `t${t.toFixed(2).padStart(6, "0")}.jpg`)); console.log("shots", ts.length); console.log(JSON.stringify(await p.evaluate(() => ({ within: window.TL.within, start: window.TL.start, end: window.TL.end, basis: window.TL.basis })))); }
  else if (mode === "video") {
    const dir = a1, workers = +a2 || 4; fs.mkdirSync(path.join(dir, "frames"), { recursive: true }); const p0 = await open(), TL = await p0.evaluate(() => window.TL); fs.writeFileSync(path.join(dir, "timeline.json"), JSON.stringify(TL));
    const N = Math.round(TL.dur * TL.fps); let next = 0, done = 0; const t0 = Date.now();
    const work = async p => { for (;;) { const f = next++; if (f >= N) return; await shot(p, f / TL.fps, path.join(dir, "frames", `f${String(f).padStart(5, "0")}.jpg`), 93); if (++done % 60 === 0) console.log(done + "/" + N, ((Date.now() - t0) / 1000).toFixed(0) + "s"); } };
    const pages = [p0]; for (let i = 1; i < workers; i++) pages.push(await open()); await Promise.all(pages.map(work)); console.log("frames", N, "in", ((Date.now() - t0) / 1000).toFixed(0) + "s");
  }
  await b.close(); server.close();
})();
