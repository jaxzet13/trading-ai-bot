// STIXX print run generator.
// Makes print files for MakePlayingCards (63.5 x 88.9 mm game cards, 600 dpi, 1/8" bleed):
//   fronts/  one front per physical copy, with that copy's serial in the ID strip
//   backs/   one back per copy, with a QR that opens the app and adds exactly that copy
//   packcodes/ code cards for store packs (front with QR, back is the plain STIXX back)
//   manifest.csv  every code in the run
// Codes come from the app itself (window.STIXX_PRINT), so the app always accepts what this prints.
//
// usage: node print-templates/make_run.js --sets BM,FB,VN --copies 1 --start 1 --packs 2 --out exports/print-run-001 [--base https://your.domain/app]
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > 0 ? process.argv[i + 1] : d; };
const SETS = arg("sets", "BM,FB,VN").split(","), COPIES = +arg("copies", "1"), START = +arg("start", "1"), PACKS = +arg("packs", "2");
const ROOT = path.resolve(__dirname, ".."), OUT = path.resolve(ROOT, arg("out", "exports/print-run-001"));
for (const d of ["fronts", "backs", "packcodes", "_raw"]) fs.mkdirSync(path.join(OUT, d), { recursive: true });

const BACK = (qrSvg, code) => `<div class="c">
  <svg class="mk" viewBox="0 0 40 40"><circle cx="20" cy="9.5" r="1.6" fill="#fff"/><path d="M11 15 L29 33 M29 15 L11 33" stroke="#fff" stroke-width="1.4" stroke-linecap="round" fill="none"/></svg>
  <div class="nm">STIXX</div>${qrSvg ? `<div class="qr">${qrSvg}</div><div class="code">${code}</div>` : ""}</div>`;
const CODECARD = (qrSvg, code, pack) => `<div class="c cc" style="--a:${pack.acc}">
  <div class="k">DIGITAL PACK CODE</div><div class="pn">${pack.name.toUpperCase()}</div>
  <div class="qr big">${qrSvg}</div><div class="code">${code}</div>
  <div class="how">Scan to open this pack's digital rip in STIXX.<br>One use. Scan the back of each card to add the cards.</div>
  <svg class="mk sm" viewBox="0 0 40 40"><circle cx="20" cy="9.5" r="1.6" fill="#fff"/><path d="M11 15 L29 33 M29 15 L11 33" stroke="#fff" stroke-width="1.4" stroke-linecap="round" fill="none"/></svg></div>`;
const CSS = `html,body{margin:0;background:#000}
.c{position:relative;width:1650px;height:2250px;background:#000;color:#f2f2f0;font-family:Manrope,Arial,sans-serif;overflow:hidden}
.mk{position:absolute;left:50%;top:33%;width:230px;transform:translate(-50%,-50%);filter:drop-shadow(0 0 22px rgba(255,255,255,.35))}
.nm{position:absolute;left:0;right:0;top:47.5%;text-align:center;font-size:54px;font-weight:600;letter-spacing:.9em;text-indent:.9em;color:#e6e6e3}
.qr{position:absolute;left:50%;top:60%;width:430px;height:430px;transform:translateX(-50%);background:#fff;border-radius:28px;padding:34px;box-sizing:border-box}
.qr svg{width:100%;height:100%;display:block}
.code{position:absolute;left:0;right:0;top:82.5%;text-align:center;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:46px;letter-spacing:.08em;color:#e6e6e3}
.cc .k{position:absolute;left:0;right:0;top:12%;text-align:center;font-family:"IBM Plex Mono",monospace;font-size:44px;letter-spacing:.3em;text-indent:.3em;color:var(--a)}
.cc .pn{position:absolute;left:0;right:0;top:17.5%;text-align:center;font-weight:800;font-size:150px;letter-spacing:.02em;color:#fff}
.cc .qr.big{top:33%;width:640px;height:640px;padding:46px}
.cc .code{top:64%}
.cc .how{position:absolute;left:12%;right:12%;top:71%;text-align:center;font-size:40px;line-height:1.5;color:#a6abb5}
.cc .mk.sm{top:86%;width:120px}
.cc::after{content:"";position:absolute;left:150px;right:150px;top:150px;bottom:150px;border:3px solid var(--a);border-radius:40px;opacity:.6}`;

(async () => {
  const b = await chromium.launch();
  const app = await b.newPage({ viewport: { width: 900, height: 1100 }, deviceScaleFactor: 1.875 });
  await app.addInitScript(() => localStorage.setItem("stickfist-rips-v3", JSON.stringify({ ageOK: true, coins: 0, tokens: 0, vault: [], history: [{ t: 1, text: "x", delta: 0 }], serial: 1, netlog: [], s: {} })));
  await app.goto("file://" + path.join(ROOT, "index.html")); await app.waitForTimeout(1500);
  await app.addScriptTag({ url: "https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js" });
  const BASE = arg("base", await app.evaluate(() => window.STIXX_PRINT.APP_URL));
  await app.addStyleTag({ content: ".tcard, .tcard *, .tcard::before, .tcard::after { animation: none !important; transition: none !important; } .tcard .glare { display: none !important; } #probe { position: fixed; inset: 0; z-index: 9999; background: #000; display: grid; place-items: center; } #probe .tcard { width: 800px; border-radius: 0 !important; box-shadow: none !important; } #probe .tcard .tc-face { border-radius: 0 !important; }" });
  await app.evaluate(() => { const d = document.createElement("div"); d.id = "probe"; document.body.appendChild(d); });
  const qr = (text) => app.evaluate(t => { const q = qrcode(0, "M"); q.addData(t); q.make(); return q.createSvgTag({ cellSize: 4, margin: 0, scalable: true }); }, text);
  const sheet = await b.newPage({ viewport: { width: 1650, height: 2250 } });
  const renderSheet = async (html, file) => { await sheet.setContent(`<!doctype html><html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=Manrope:wght@600;800&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet"><style>${CSS}</style></head><body>${html}</body></html>`); await sheet.waitForTimeout(700); await sheet.screenshot({ path: file }); };
  const rows = [["type", "set", "card", "name", "rarity", "serial", "code", "url", "front", "back"]];
  for (const set of SETS) {
    const cards = await app.evaluate(s => window.STIXX_PRINT.CARDS.filter(c => c.set === s).map(c => c.no), set);
    for (const no of cards) for (let k = 0; k < COPIES; k++) {
      const serial = START + k;
      const info = await app.evaluate(({ no, serial }) => { const P = window.STIXX_PRINT, c = P.CARD_BY_NO[no]; document.getElementById("probe").innerHTML = P.cardHTML({ uid: "print", id: c.id, cno: no, rar: c.rar, serial, ed: "foil" }); return { code: P.cardCode(c, serial), id: c.id, rar: c.rar }; }, { no, serial });
      await app.waitForTimeout(500);
      const tag = `${no}_${String(serial).padStart(6, "0")}`, raw = path.join(OUT, "_raw", tag + ".png");
      await (await app.$("#probe .tcard")).screenshot({ path: raw });
      const url = `${BASE}#c-${info.code}`;
      await renderSheet(BACK(await qr(url), info.code), path.join(OUT, "backs", `${tag}_back.png`));
      rows.push(["card", set, no, info.id, info.rar, serial, info.code, url, `fronts/${tag}_front.png`, `backs/${tag}_back.png`]);
      console.log("card", tag, info.code);
    }
    for (let k = 0; k < PACKS; k++) {
      const serial = START + k, key = set;
      const pk = await app.evaluate(({ key, serial }) => { const P = window.STIXX_PRINT, p = P.PACK_BY_ID[P.RETAIL_KEY[key]]; return p ? { code: P.packCode(key, serial), name: p.name, acc: p.acc } : null; }, { key, serial });
      if (!pk) continue;
      const url = `${BASE}#p-${pk.code}`, tag = `PK-${key}_${String(serial).padStart(6, "0")}`;
      await renderSheet(CODECARD(await qr(url), pk.code, pk), path.join(OUT, "packcodes", `${tag}_front.png`));
      rows.push(["pack", set, "", pk.name, "", serial, pk.code, url, `packcodes/${tag}_front.png`, "plain STIXX back"]);
      console.log("pack", tag, pk.code);
    }
  }
  await renderSheet(BACK(null, ""), path.join(OUT, "packcodes", "STIXX_plain_back.png"));
  fs.writeFileSync(path.join(OUT, "manifest.csv"), rows.map(r => r.map(v => /[",]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v).join(",")).join("\n") + "\n");
  await b.close();
  // fronts: shrink the design inside MPC's safe zone and extend its outer edge into the bleed (same as the earlier set exports)
  execFileSync("python3", ["-c", `
import glob, os, numpy as np
from PIL import Image
out = ${JSON.stringify(OUT)}
for f in sorted(glob.glob(os.path.join(out, "_raw", "*.png"))):
    im = Image.open(f).convert("RGB").resize((1500, 2100), Image.LANCZOS)
    k = 0.93; w, h = round(1500 * k), round(2100 * k)
    a = np.asarray(im.resize((w, h), Image.LANCZOS)); px = (1650 - w) // 2; py = (2250 - h) // 2
    o = np.pad(a, ((py, 2250 - h - py), (px, 1650 - w - px), (0, 0)), mode="edge")
    Image.fromarray(o).save(os.path.join(out, "fronts", os.path.basename(f)[:-4] + "_front.png"), dpi=(600, 600))
    os.remove(f)
os.rmdir(os.path.join(out, "_raw"))
for d in ("backs", "packcodes"):
    for f in glob.glob(os.path.join(out, d, "*.png")):
        Image.open(f).convert("RGB").save(f, dpi=(600, 600))
`]);
  console.log("done", OUT, rows.length - 1, "codes");
})();
