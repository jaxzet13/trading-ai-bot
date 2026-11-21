/* ============================================================================
   8b. THE RESULT CARD. What a card did between the pack and the sale, drawn as an ASCII line chart that draws itself,
   with a headline number that rises and falls with the line. The animation is a canvas, so what you watch is what you save.
   ========================================================================== */
// everything the picture needs, worked out from the card's own price path while it was yours
function receiptOf(c, sold) {
  const card = BY_NO[c.no], now = Date.now(), held = Math.max(0, now - (c.t || now)), span = Math.max(held, 3 * 36e5), n = 120;
  const ago0 = Math.min(MK.tick(), Math.round(span / MK.TICK)), agoPull = Math.min(ago0, Math.round(held / MK.TICK)), vals = [];
  for (let i = 0; i < n; i++) vals.push(valueAgo(c, Math.round(ago0 * (1 - i / (n - 1)))));
  const cost = costOf(c), got = sellOf(c), pi = ago0 ? Math.round((1 - agoPull / ago0) * (n - 1)) : 0; let pk = pi;
  for (let i = pi; i < n; i++) if (vals[i] > vals[pk]) pk = i;
  return { card, fx: c.fx || "", code: c.code, sold, cost, got, held, vals, pi, pk, gain: got - cost, pct: got / Math.max(1, cost) - 1, peakPct: vals[pk] * SELLBACK / Math.max(1, cost) - 1, at: now };
}

const Share = (() => {
  const W = 1080, H = 1350, FONT = "'JetBrains Mono', 'DejaVu Sans Mono', ui-monospace, Menlo, Consolas, monospace";
  const GREEN = "#9fd8a6", RED = "#e8786d", INK = "#ece7dc", DIM = "#8d897f", FAINT = "#4a4a52", BG = "#050506";
  const CH0 = .9, CH1 = 3.7, ROWS = 24, LH = 19, CF = 16, X0 = 60, Y0 = 668;               // when the chart starts and stops drawing, and where it sits
  let cv, ctx, rec = null, img = null, plot = null, t0 = 0, raf = 0, last = 0, parts = [], burst = false, rain = null, recording = false;
  const ease = x => 1 - Math.pow(1 - x, 3), lerp = (a, b, k) => a + (b - a) * k, clampK = x => x < 0 ? 0 : x > 1 ? 1 : x;
  const scramble = (str, k) => { const n = Math.floor(str.length * k); let o = ""; for (let i = 0; i < str.length; i++) o += i < n || str[i] === " " ? str[i] : "#%&*+=<>/"[Math.floor(Math.random() * 9)]; return o; };
  const dateStr = ms => { const d = new Date(ms), p = x => String(x).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`; };

  function T(str, x, y, size, color, weight, align, alpha) {
    ctx.font = `${weight || 500} ${size}px ${FONT}`; ctx.textAlign = align || "left"; ctx.fillStyle = color; ctx.globalAlpha = alpha == null ? 1 : alpha; ctx.fillText(str, x, y); ctx.globalAlpha = 1; ctx.textAlign = "left";
  }
  function pix(str, x, y, px, color, alpha) {   // the pixel lettering, drawn as squares
    const rows = blockText(str).split("\n"); ctx.fillStyle = color; ctx.globalAlpha = alpha == null ? 1 : alpha;
    rows.forEach((row, r) => { for (let i = 0; i < row.length; i++) if (row[i] === "█") ctx.fillRect(x + i * px, y + r * px, px - 1, px - 1); }); ctx.globalAlpha = 1; return rows[0].length * px;
  }
  function rainLayer(t, col) {
    if (!rain) rain = Array.from({ length: 44 }, (_, i) => ({ x: 20 + i * 24.2, y: Math.random() * H, v: 24 + Math.random() * 70, s: Math.random() }));
    ctx.font = `500 16px ${FONT}`; ctx.fillStyle = col;
    for (const r of rain) { const y0 = (r.y + t * r.v) % (H + 300) - 150; for (let k = 0; k < 7; k++) { ctx.globalAlpha = .075 * (1 - k / 7); ctx.fillText("01+-$.:%"[(Math.floor(t * 6 + r.s * 40) + k * 3) % 8], r.x, y0 - k * 18); } }
    ctx.globalAlpha = 1;
  }

  function draw(t, live) {
    const r = rec, up = r.pct >= 0, col = up ? GREEN : RED, c = ctx;
    c.save(); c.globalAlpha = 1; c.fillStyle = BG; c.fillRect(0, 0, W, H); c.textBaseline = "top";
    if (live) rainLayer(t, col);
    c.strokeStyle = FAINT; c.lineWidth = 2; c.globalAlpha = .7; c.strokeRect(24, 24, W - 48, H - 48); c.globalAlpha = 1;

    // top bar
    T("[ STIXX ]", 60, 54, 30, INK, 700); T(dateStr(r.at), W - 60, 60, 20, DIM, 500, "right");

    // the card picture, decoding from the top
    const ik = ease(clampK(t / .9)), ix = 60, iy = 140, iw = 360, ih = 437;
    c.fillStyle = "#040405"; c.fillRect(ix, iy, iw, ih);
    if (img) { c.save(); c.beginPath(); c.rect(ix, iy, iw, ih * ik); c.clip(); c.drawImage(img, ix, iy, iw, ih); c.restore(); }
    if (ik < 1 && live) { c.font = `500 14px ${FONT}`; c.fillStyle = col; const ey = iy + ih * ik; for (let i = 0; i < 26; i++) { c.globalAlpha = .5; c.fillText("01+-$.:%#"[Math.floor(Math.random() * 9)], ix + i * 14, ey - 6); } c.globalAlpha = 1; }
    c.strokeStyle = FAINT; c.lineWidth = 2; c.strokeRect(ix - 1, iy - 1, iw + 2, ih + 2);

    // the right column: status, name, the headline number
    const nameFull = r.card.name.toUpperCase() + (r.fx ? " · " + STYLES[r.fx].name.toUpperCase() : "");
    T(r.sold ? "[ SOLD ]" : "[ STILL HOLDING ]", 470, 142, 28, col, 700);
    T(t < .6 ? scramble(nameFull, t / .6) : nameFull, 470, 192, nameFull.length > 18 ? 34 : 44, INK, 700);
    T(`${RAR[r.card.rar].name} · ${fmt(r.card.chars)} characters`, 470, 250, 22, DIM, 500);

    // chart geometry and the character grid
    c.font = `500 ${CF}px ${FONT}`; const cw = c.measureText("M").width, cols = Math.floor(960 / cw);
    if (!plot || plot.cols !== cols) plot = Object.assign({ cols }, plotGrid(r.vals, cols, ROWS));
    const p = ease(clampK((t - CH0) / (CH1 - CH0))), hc = p * (cols - 1), hi = Math.floor(hc), pullCol = Math.round(r.pi / (r.vals.length - 1) * (cols - 1)), peakCol = Math.round(r.pk / (r.vals.length - 1) * (cols - 1));
    const vAt = x => { const i = Math.floor(x), j = Math.min(cols - 1, i + 1); return plot.v[i] + (plot.v[j] - plot.v[i]) * (x - i); };
    const vHead = vAt(hc), pctHead = p >= 1 ? r.pct : hc < pullCol ? 0 : vHead * SELLBACK / Math.max(1, r.cost) - 1;

    // the headline: it moves with the line
    const txt = pctShort(pctHead).replace("−", "-"), full = pctShort(r.pct).replace("−", "-"), colsN = blockText(full).split("\n")[0].length, px = Math.min(16, Math.floor(560 / colsN));
    const hcol = pctHead >= 0 ? GREEN : RED; pix(txt, 470, 292, px, hcol, 1);
    const by = 292 + 5 * px + 26;
    T(`${money(r.cost)}  →  ${money(p >= 1 ? r.got : Math.round(vHead * SELLBACK))}`, 470, by, 38, INK, 700);
    T(`${r.gain >= 0 ? "+" : "−"}${money(Math.abs(r.gain))} ${r.sold ? (r.gain >= 0 ? "made" : "lost") : "if you sold now"}`, 470, by + 56, 26, col, 600, "left", p >= 1 ? 1 : .35);
    T(`held ${heldText(r.held)} · after the 10% fee`, 470, by + 96, 21, DIM, 500);

    // the ASCII line chart
    T(`HIGH ${money(Math.max(...r.vals))}   LOW ${money(Math.min(...r.vals))}`, X0, Y0 - 40, 19, DIM, 500);
    T(r.pi > 0 ? "the dim part is before you got it" : "", W - 60, Y0 - 40, 19, FAINT, 500, "right");
    c.font = `500 ${CF}px ${FONT}`;
    for (let x = 0; x <= hi; x++) {
      const before = x < pullCol, age = hc - x, ly = ROWS - 1 - plot.Y[x];
      for (let y = 0; y < ROWS; y++) { const ch = plot.grid[y][x]; if (ch === " ") continue; c.globalAlpha = before ? .5 : 1; c.fillStyle = before ? FAINT : age < 2.5 ? "#ffffff" : age < 7 ? INK : col; c.fillText(ch, X0 + x * cw, Y0 + y * LH); }
      for (let y = ly + 1; y < ROWS && y - ly < 9; y++) { c.globalAlpha = (before ? .1 : .3) * (1 - (y - ly) / 9.5); c.fillStyle = before ? FAINT : col; c.fillText(y - ly === 1 ? ":" : ".", X0 + x * cw, Y0 + y * LH); }
    }
    c.globalAlpha = 1;
    // pulled and peak markers
    if (hi >= pullCol && r.pi > 0) { c.fillStyle = DIM; c.font = `500 ${CF}px ${FONT}`; for (let y = ROWS - 1 - plot.Y[pullCol] + 1; y < ROWS; y++) { c.globalAlpha = .35; c.fillText("┆", X0 + pullCol * cw, Y0 + y * LH); } c.globalAlpha = 1; }
    const baseY = Y0 + ROWS * LH + 14, pullX = Math.min(X0 + pullCol * cw, W - 60 - 230);
    if (hi >= pullCol) T(`▲ pulled ${money(r.cost)}`, Math.max(X0, pullX), baseY, 22, DIM, 600);
    if (hi >= peakCol && r.peakPct > r.pct + .08 && r.pk > r.pi) { const pyy = Y0 + (ROWS - 1 - plot.Y[peakCol]) * LH - 36, ptx = `PEAK ${pctShort(r.peakPct)}`; T(ptx, Math.min(Math.max(X0 + peakCol * cw - 40, X0), W - 60 - 220), Math.max(pyy, Y0 - 12), 22, INK, 700, "left", .95); }
    // the head
    if (p < 1 || live) {
      const hx = X0 + hc * cw, hy = Y0 + (ROWS - 1 - plot.Y[Math.min(cols - 1, Math.round(hc))]) * LH;
      c.fillStyle = col; c.globalAlpha = .16 + .06 * Math.sin(t * 9); c.beginPath(); c.arc(hx + cw / 2, hy + LH / 2, 13, 0, 6.3); c.fill(); c.globalAlpha = 1;
      c.font = `700 22px ${FONT}`; c.fillStyle = "#ffffff"; c.fillText("●", hx - 1, hy - 2);
      if (p < 1) { const lx = hx > X0 + 760 ? hx - 120 : hx + 24; T(money(Math.round(vHead)), lx, hy - 36, 24, "#ffffff", 700); }
    }
    if (p >= 1) T(`${r.sold ? "sold" : "now"} ${money(r.got)} ▶`, W - 60, baseY, 22, col, 700, "right");

    // footer
    c.strokeStyle = FAINT; c.lineWidth = 1; c.beginPath(); c.moveTo(60, 1168); c.lineTo(W - 60, 1168); c.stroke();
    T("Demo money. Prices follow a fixed public formula and the other traders are simulated.", 60, 1190, 19, DIM, 500);
    T("Nothing here is real and nothing was charged.", 60, 1218, 19, DIM, 500);
    pix("STIXX", 60, 1262, 7, INK, .95); T(`first print · ${r.code}`, W - 60, 1284, 19, DIM, 500, "right");

    // after the line has run: profit throws characters up, a loss glitches
    if (live && p >= 1 && !burst) { burst = true; for (let i = 0; i < (up ? 90 : 60); i++) parts.push({ x: 470 + Math.random() * 520, y: 310, vx: (Math.random() - .5) * 420, vy: up ? -140 - Math.random() * 360 : 40 + Math.random() * 120, ch: up ? "$+*·"[i % 4] : "-x/\\"[i % 4], life: 1.4 + Math.random() * 1.2, age: 0 }); }
    if (live && parts.length) { const dt = Math.min(.05, (performance.now() - last) / 1000 || .016); c.font = `700 24px ${FONT}`; c.fillStyle = col; for (const q of parts) { q.age += dt; q.x += q.vx * dt; q.y += q.vy * dt; q.vy += (up ? 380 : 220) * dt; c.globalAlpha = Math.max(0, 1 - q.age / q.life); c.fillText(q.ch, q.x, q.y); } c.globalAlpha = 1; parts = parts.filter(q => q.age < q.life); }
    if (live && !up && t > CH1 && t < CH1 + .7) { for (let i = 0; i < 7; i++) { const by2 = 140 + Math.random() * 1000, bh = 8 + Math.random() * 40, dx = (Math.random() - .5) * 46; c.drawImage(cv, 0, by2, W, bh, dx, by2, W, bh); } }
    c.restore(); last = performance.now();
  }

  function loop(now) { draw((now - t0) / 1000, true); raf = requestAnimationFrame(loop); }
  function play() { cancelAnimationFrame(raf); parts = []; burst = false; t0 = performance.now(); last = t0; if (reduced) draw(99, false); else raf = requestAnimationFrame(loop); }
  const fontReady = () => Promise.race([document.fonts && document.fonts.load ? document.fonts.load("700 22px 'JetBrains Mono'").catch(() => 0) : 0, new Promise(r => setTimeout(r, 1200))]);

  async function open(r) {
    rec = r; plot = null; rain = null; $("share").hidden = false; document.body.style.overflow = "hidden"; cv = $("shCv"); ctx = cv.getContext("2d");
    $("shVideo").hidden = !(window.MediaRecorder && cv.captureStream);
    draw(0, false); await fontReady(); img = await loadImg(imgOf(r.card, r.fx)); if ($("share").hidden) return; play();
  }
  function close() { cancelAnimationFrame(raf); $("share").hidden = true; document.body.style.overflow = ""; rec = null; }

  // a still picture of the finished chart
  function still() { return new Promise(res => { cancelAnimationFrame(raf); draw(99, false); cv.toBlob(b => { res(b); if (!$("share").hidden && !reduced) { t0 = performance.now() - 20000; raf = requestAnimationFrame(loop); } }, "image/png"); }); }
  async function saveBlob(blob, name) {
    try { const dl = window.claude && claude.use ? await claude.use("downloads") : null; if (dl) { await dl.save({ filename: name, data: blob }); toast("Saved"); return; } } catch (e) { if (e && e.code === "declined") return; }
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); toast("Saved");
  }
  const fileName = ext => `stixx-${rec.card.id}-${rec.pct >= 0 ? "up" : "down"}-${Math.abs(Math.round(rec.pct * 100))}pct.${ext}`;
  const caption = () => `${rec.sold ? "Sold" : "Holding"} ${rec.card.name} on STIXX: ${pctShort(rec.pct)} (${money(rec.cost)} to ${money(rec.got)}). Demo money.`;
  async function save() { const b = await still(); if (b) saveBlob(b, fileName("png")); }
  async function share() {
    const b = await still(); if (!b) return; const f = new File([b], fileName("png"), { type: "image/png" });
    try { if (navigator.canShare && navigator.canShare({ files: [f] })) { await navigator.share({ files: [f], title: "STIXX", text: caption() }); return; } } catch (e) { if (e && e.name === "AbortError") return; }
    saveBlob(b, fileName("png"));
  }
  // record the animation itself as a short video
  async function video() {
    if (recording) return; const mime = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"].find(m => MediaRecorder.isTypeSupported(m)); if (!mime) { toast("This browser can't record video. Save the image instead."); return; }
    recording = true; const btn = $("shVideo"), label = btn.textContent; btn.textContent = "recording…"; const chunks = [], mr = new MediaRecorder(cv.captureStream(30), { mimeType: mime, videoBitsPerSecond: 5e6 });
    mr.ondataavailable = e => { if (e.data.size) chunks.push(e.data); }; mr.onstop = () => { recording = false; btn.textContent = label; saveBlob(new Blob(chunks, { type: mime }), fileName(mime.startsWith("video/mp4") ? "mp4" : "webm")); };
    play(); mr.start(); setTimeout(() => mr.stop(), (CH1 + 2.2) * 1000);
  }
  return { open, close, play, save, share, video };
})();
