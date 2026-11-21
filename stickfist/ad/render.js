// Renders ad.html frame by frame.
//   node render.js shots <t1,t2,...> <outdir> [handle]     PNG stills at those moments, for checking the film
//   node render.js video <outdir> [handle] [workers]       every frame as JPEG in <outdir>/frames, plus <outdir>/timeline.json for audio.py
// Needs playwright with chromium and JetBrains Mono installed. It serves the stickfist folder itself.
const { chromium } = require("playwright"); const fs = require("fs"); const path = require("path"); const http = require("http");
const ROOT = path.resolve(__dirname, ".."); const MIME = { ".html": "text/html", ".jpg": "image/jpeg", ".png": "image/png", ".js": "text/javascript" };
const server = http.createServer((q, r) => { const f = path.join(ROOT, decodeURIComponent(q.url.split("?")[0])); if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { r.statusCode = 404; return r.end(); } r.setHeader("content-type", MIME[path.extname(f)] || "application/octet-stream"); fs.createReadStream(f).pipe(r); });
const [mode, a1, a2, a3, a4] = process.argv.slice(2);
(async () => {
  await new Promise(r => server.listen(0, "127.0.0.1", r)); const port = server.address().port, b = await chromium.launch();
  const open = async handle => { const p = await b.newPage({ viewport: { width: 1080, height: 1920 } }); p.on("pageerror", e => console.log("PAGEERR", e.message)); p.on("console", m => { if (m.type() === "error") console.log("CON", m.text()); }); await p.goto(`http://127.0.0.1:${port}/ad/${process.env.AD_FILE || "ad.html"}${handle ? "?handle=" + encodeURIComponent(handle) : ""}`); await p.evaluate(() => window.READY); return p; };
  if (mode === "shots") {
    const ts = a1.split(",").map(Number), dir = a2; fs.mkdirSync(dir, { recursive: true }); const p = await open(a3 || "");
    for (const t of ts) { await p.evaluate(t => window.renderAt(t), t); const data = await p.evaluate(() => document.getElementById("o").toDataURL("image/png")); fs.writeFileSync(path.join(dir, `t${t.toFixed(2).padStart(6, "0")}.png`), Buffer.from(data.split(",")[1], "base64")); }
    console.log("shots", ts.length);
  } else if (mode === "video") {
    const dir = a1, handle = a2 && a2 !== "-" ? a2 : "", workers = +a3 || 3; fs.mkdirSync(path.join(dir, "frames"), { recursive: true });
    const p0 = await open(handle), TL = await p0.evaluate(() => window.TL); fs.writeFileSync(path.join(dir, "timeline.json"), JSON.stringify(TL, null, 1));
    const N = Math.round(TL.dur * TL.fps); let next = 0, done = 0; const t0 = Date.now();
    const work = async p => { for (;;) { const f = next++; if (f >= N) return; const data = await p.evaluate(t => window.frameJpeg(t, .94), f / TL.fps); fs.writeFileSync(path.join(dir, "frames", `f${String(f).padStart(5, "0")}.jpg`), Buffer.from(data.split(",")[1], "base64")); if (++done % 60 === 0) console.log(`${done}/${N}  ${((Date.now() - t0) / 1000).toFixed(0)}s`); } };
    const pages = [p0]; for (let i = 1; i < workers; i++) pages.push(await open(handle)); await Promise.all(pages.map(work));
    console.log("frames", N, "in", ((Date.now() - t0) / 1000).toFixed(0) + "s");
  }
  await b.close(); server.close();
})();
