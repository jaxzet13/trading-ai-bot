/* ============================================================================
   8b. THE TRADE REPLAY. Your card's whole trade as a picture: first a position card with a pile of ASCII coins, then a replay where an ASCII line chart
   redraws itself from the moment you got the card, an ASCII face rides the line, and the profit or loss changes live. It is a canvas, so it can be
   saved as a picture or recorded as a video.
   ========================================================================== */
// everything the picture needs, worked out from the card's own price path while it was yours
function receiptOf(c, sold) {
  const card = BY_NO[c.no], now = Date.now(), held = Math.max(0, now - (c.t || now)), span = Math.max(held, 2 * 36e5), n = 240;
  const ago0 = Math.min(MK.tick(), Math.round(span / MK.TICK)), agoPull = Math.min(ago0, Math.round(held / MK.TICK)), vals = [];
  for (let i = 0; i < n; i++) vals.push(valueAgo(c, Math.round(ago0 * (1 - i / (n - 1)))));
  const cost = costOf(c), got = sellOf(c), pi = ago0 ? Math.round((1 - agoPull / ago0) * (n - 1)) : 0; let pk = pi;
  for (let i = pi; i < n; i++) if (vals[i] > vals[pk]) pk = i;
  return { card, fx: c.fx || "", code: c.code, sold, cost, got, held, vals, pi, pk, startMs: now - ago0 * MK.TICK, endMs: now, gain: got - cost, pct: got / Math.max(1, cost) - 1, peakPct: vals[pk] * SELLBACK / Math.max(1, cost) - 1, at: now };
}

async function saveBlob(blob, name) {
  try { const dl = window.claude && claude.use ? await claude.use("downloads") : null; if (dl) { await dl.save({ filename: name, data: blob }); toast("Saved"); return; } } catch (e) { if (e && e.code === "declined") return; }
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); toast("Saved");
}

const Share = (() => {
  const W = 1080, H = 1350, FONT = "'JetBrains Mono', 'DejaVu Sans Mono', ui-monospace, Menlo, Consolas, monospace";
  const GREEN = "#9fd8a6", RED = "#e8786d", INK = "#ece7dc", DIM = "#8d897f", FAINT = "#4a4a52", BG = "#050507", PANEL = "#0b0b10";
  const DUR = 14, CF = 16, LH = 19, PX0 = 60, PY0 = 214, PW = 876, ROWS = 27;      // seconds a replay lasts, and where the chart sits
  let cv, ctx, rec = null, img = null, raf = 0, last = 0, mode = "position", intro = 0, rt = 0, paused = false, speed = 1, auto = true, parts = [], burst = false, rain = null, recording = false, lastUi = "";
  let clock = 0, dtLast = .016, endAge = 0;
  const ease = x => 1 - Math.pow(1 - x, 3), clampK = x => x < 0 ? 0 : x > 1 ? 1 : x;
  const dateStr = ms => new Date(ms).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const timeStr = (ms, span) => span > 40 * 36e5 ? new Date(ms).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const sgn = x => (x >= 0 ? "+" : "−") + money(Math.abs(x));

  function T(str, x, y, size, color, weight, align, alpha) { ctx.font = `${weight || 500} ${size}px ${FONT}`; ctx.textAlign = align || "left"; ctx.fillStyle = color; ctx.globalAlpha = alpha == null ? 1 : alpha; ctx.fillText(str, x, y); ctx.globalAlpha = 1; ctx.textAlign = "left"; }
  function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function pix(str, x, y, px, color, alpha) { const rows = blockText(str).split("\n"); ctx.fillStyle = color; ctx.globalAlpha = alpha == null ? 1 : alpha; rows.forEach((row, r) => { for (let i = 0; i < row.length; i++) if (row[i] === "█") ctx.fillRect(x + i * px, y + r * px, px - 1, px - 1); }); ctx.globalAlpha = 1; return rows[0].length * px; }
  function rainLayer(t, col) {
    if (!rain) rain = Array.from({ length: 44 }, (_, i) => ({ x: 20 + i * 24.2, y: Math.random() * H, v: 24 + Math.random() * 70, s: Math.random() }));
    ctx.font = `500 16px ${FONT}`; ctx.fillStyle = col;
    for (const r of rain) { const y0 = (r.y + t * r.v) % (H + 300) - 150; for (let k = 0; k < 7; k++) { ctx.globalAlpha = .06 * (1 - k / 7); ctx.fillText("01+-$.:%"[(Math.floor(t * 6 + r.s * 40) + k * 3) % 8], r.x, y0 - k * 18); } }
    ctx.globalAlpha = 1;
  }

  // ---- the chart for the part of the trade replayed so far: it is redrawn to fit what has happened, like a live chart
  function chartAt(k) {
    const n = rec.vals.length, kf = k * (n - 1), ki = Math.floor(kf), shown = rec.vals.slice(0, ki + 1), vh = rec.vals[ki] + (rec.vals[Math.min(n - 1, ki + 1)] - rec.vals[ki]) * (kf - ki);
    shown.push(vh); if (shown.length < 3) shown.unshift(shown[0]);
    ctx.font = `500 ${CF}px ${FONT}`; const cw = ctx.measureText("M").width, cols = Math.floor(PW / cw), entry = rec.vals[rec.pi];
    return { pl: plotGrid(shown, cols, ROWS, [entry]), cw, cols, vh, kf, len: shown.length, entry };
  }

  function drawFace(x, y, up, size) {
    ctx.font = `700 ${size}px ${FONT}`; const f = up ? "(^_^)" : "(;_;)", w = ctx.measureText(f).width + 20; rr(x - w / 2, y - size * .9, w, size * 1.8, size * .9); ctx.fillStyle = "#0b0b10"; ctx.fill();
    ctx.strokeStyle = up ? GREEN : RED; ctx.lineWidth = 2; ctx.stroke(); ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(f, x, y + 1); ctx.textAlign = "left"; ctx.textBaseline = "top";
  }
  function coin(x, y, ch, col, a) { ctx.globalAlpha = a; ctx.font = `700 22px ${FONT}`; const s = "(" + ch + ")", w = ctx.measureText(s).width; ctx.fillStyle = col === RED ? "#1a0907" : "#07140b"; ctx.fillRect(x - 3, y - 2, w + 6, 26); ctx.fillStyle = col; ctx.fillText(s, x, y); ctx.globalAlpha = 1; }

  function draw(live) {
    const r = rec, c = ctx, t = clock; c.save(); c.globalAlpha = 1; c.fillStyle = BG; c.fillRect(0, 0, W, H); c.textBaseline = "top";
    const rep = mode === "replay"; let ch = null, pnl = r.gain, pct = r.pct, price = r.got, before = false;
    if (rep) { ch = chartAt(rt); before = ch.kf < r.pi; price = Math.round(ch.vh * SELLBACK); pnl = before ? 0 : price - r.cost; pct = before ? 0 : price / Math.max(1, r.cost) - 1; if (rt >= 1) { pnl = r.gain; pct = r.pct; price = r.got; } }
    else { const k = ease(clampK(intro / 1.2)); pnl = Math.round(r.gain * k); pct = r.pct * k; }
    const up = pnl >= 0, col = up ? GREEN : RED, finalUp = r.pct >= 0;
    if (live) rainLayer(t, finalUp ? GREEN : RED);

    // the card, and its header: the card's picture as an avatar, a handle, a tag, the date
    rr(30, 30, W - 60, H - 60, 34); c.fillStyle = "#07070b"; c.fill(); c.strokeStyle = finalUp ? "#3d6b46" : "#7a3a35"; c.lineWidth = 4; c.stroke();
    const ax = 104, ay = 112; c.save(); c.beginPath(); c.arc(ax, ay, 40, 0, 6.3); c.clip(); c.fillStyle = "#0e0e14"; c.fillRect(ax - 40, ay - 40, 80, 80); if (img) { const s = 80 / img.width; c.drawImage(img, ax - 40, ay - 40, 80, img.height * s); } c.restore();
    c.strokeStyle = col; c.lineWidth = 3; c.beginPath(); c.arc(ax, ay, 41, 0, 6.3); c.stroke();
    T("you", 166, 76, 34, INK, 700); const tag = r.sold ? (finalUp ? "Profit" : "Loss") : "Holding"; c.font = `700 20px ${FONT}`; const tw = c.measureText(tag).width + 24;
    rr(166, 124, tw, 32, 8); c.fillStyle = finalUp ? "#10261a" : "#2a1210"; c.fill(); T(tag, 178, 130, 20, finalUp ? GREEN : RED, 700);
    T(dateStr(r.at), W - 62, 80, 22, DIM, 500, "right"); T("[ STIXX ]", W - 62, 118, 22, INK, 700, "right");

    if (!rep) drawPile(finalUp); else drawChart(ch, col);

    // the profit and loss panel
    rr(60, 800, W - 120, 262, 26); c.fillStyle = PANEL; c.fill(); c.strokeStyle = "#1b1b24"; c.lineWidth = 2; c.stroke();
    const name = r.card.name.toUpperCase() + (r.fx ? " · " + STYLES[r.fx].name.toUpperCase() : ""); T("◆ " + name, W / 2, 824, 30, INK, 700, "center");
    const big = rep && before ? "–" : sgn(pnl), pc = rep && before ? "" : (pct >= 0 ? "▲ " : "▼ ") + (Math.abs(pct) >= 1 ? Math.round(Math.abs(pct) * 100).toLocaleString("en-US") : (Math.abs(pct) * 100).toFixed(1)) + "%";
    c.font = `700 84px ${FONT}`; const bw = c.measureText(big).width; c.font = `700 42px ${FONT}`; const pw = c.measureText(pc).width, x0 = W / 2 - (bw + 26 + pw) / 2;
    T(big, x0, 868, 84, col, 700); T(pc, x0 + bw + 26, 902, 42, col, 700);
    const sx = [W / 2 - 300, W / 2, W / 2 + 300]; T("Pulled at", sx[0], 986, 20, DIM, 500, "center"); T(r.sold && (!rep || rt >= 1) ? "Sold for" : "Worth now", sx[1], 986, 20, DIM, 500, "center"); T("Held", sx[2], 986, 20, DIM, 500, "center");
    T(money(r.cost), sx[0], 1014, 28, INK, 700, "center"); T(money(rep ? price : r.got), sx[1], 1014, 28, INK, 700, "center"); T(heldText(r.held), sx[2], 1014, 28, INK, 700, "center");

    // the footer band
    c.save(); rr(30, 1090, W - 60, H - 1090 - 30, 34); c.clip(); c.fillStyle = "#0e0e18"; c.fillRect(30, 1090, W - 60, 240); c.restore();
    pix("STIXX", 66, 1140, 10, INK, .95); T("play money · simulated", W - 66, 1142, 24, INK, 600, "right"); T("nothing here is real or charged", W - 66, 1180, 20, DIM, 500, "right");
    T(`${RAR[r.card.rar].name} · ${fmt(r.card.chars)} characters`, 66, 1240, 19, DIM, 500); T(r.code, 66, 1270, 19, DIM, 500); T(r.sold ? "after the 10% selling fee" : "if you sold now, after the 10% fee", W - 66, 1270, 19, DIM, 500, "right");

    // when the replay ends: profit throws characters up, a loss glitches
    if (live && rep && rt >= 1 && !burst) { burst = true; for (let i = 0; i < (finalUp ? 90 : 60); i++) parts.push({ x: 540 + (Math.random() - .5) * 600, y: 860, vx: (Math.random() - .5) * 460, vy: finalUp ? -160 - Math.random() * 380 : 40 + Math.random() * 120, ch: finalUp ? "$+*·"[i % 4] : "-x/\\"[i % 4], life: 1.4 + Math.random() * 1.2, age: 0 }); }
    if (live && parts.length) { c.font = `700 26px ${FONT}`; c.fillStyle = finalUp ? GREEN : RED; for (const q of parts) { q.age += dtLast; q.x += q.vx * dtLast; q.y += q.vy * dtLast; q.vy += (finalUp ? 380 : 220) * dtLast; c.globalAlpha = Math.max(0, 1 - q.age / q.life); c.fillText(q.ch, q.x, q.y); } c.globalAlpha = 1; parts = parts.filter(q => q.age < q.life); }
    if (live && !finalUp && rep && rt >= 1 && endAge < .7) for (let i = 0; i < 7; i++) { const by = 120 + Math.random() * 1000, bh = 8 + Math.random() * 40, dx = (Math.random() - .5) * 46; c.drawImage(cv, 0, by, W, bh, dx, by, W, bh); }
    c.restore();
  }

  // ---- the position card: a pile of ASCII coins, green for what you bought and red for what you sold
  function drawPile(finalUp) {
    const c = ctx, r = rec, base = 690, big = clampK(Math.log10(1 + Math.abs(r.pct)) / 2.6), heights = [3, 5, 8, 6, 4].map(h => Math.max(2, Math.round(h * (.7 + big * .9)))), xs = [230, 350, 470, 590, 710];
    c.font = `500 15px ${FONT}`; c.fillStyle = FAINT; c.globalAlpha = .45; for (let y = PY0 + 20; y < base + 30; y += 38) c.fillText("┄".repeat(98), 60, y); c.globalAlpha = 1;
    let idx = 0; heights.forEach((n, ci) => { const sell = r.sold && ci >= 3, ch = sell ? "S" : "P", col = sell ? RED : GREEN;
      for (let i = 0; i < n; i++, idx++) { const k = clampK((intro - idx * .045) / .35); if (k <= 0) continue; coin(xs[ci], base - i * 27 - (1 - ease(k)) * 160 - ((i + ci) % 2) * 5, ch, col, Math.min(1, k * 2)); } });
    T(r.sold ? "green: what you pulled · red: what you sold" : "what you pulled, still in your hands", 540, 736, 22, DIM, 500, "center");
  }

  // ---- the replay: an ASCII line chart that redraws itself, the entry line, a coin where you got it, an ASCII face on the head and a price tag
  function drawChart(ch, col) {
    const c = ctx, r = rec, { pl, cw, cols, vh, entry } = ch, pullCol = Math.round(r.pi / (ch.len - 1) * (cols - 1)), hasPull = ch.kf >= r.pi;
    const ey = PY0 + (ROWS - 1 - Math.round((Math.log(entry) - pl.mn) / pl.sp * (ROWS - 1))) * LH;
    c.font = `500 ${CF}px ${FONT}`;
    for (let i = 0; i < 3; i++) { const row = Math.round(i * (ROWS - 1) / 2), p = Math.exp(pl.mn + pl.sp * (ROWS - 1 - row) / (ROWS - 1)); T(money(Math.round(p)), PX0 + PW + 14, PY0 + row * LH - 8, 18, FAINT, 500); }
    const full = r.endMs - r.startMs, span = full * ch.kf / (r.vals.length - 1);
    [0, .5, 1].forEach(f => T(timeStr(r.startMs + span * f, full), PX0 + f * (PW - 70), PY0 + ROWS * LH + 12, 18, FAINT, 500));
    if (ey >= PY0 - 4 && ey < PY0 + ROWS * LH) { c.font = `500 ${CF}px ${FONT}`; c.fillStyle = DIM; c.globalAlpha = .5; c.fillText("┄".repeat(cols), PX0, ey); c.globalAlpha = 1; T("you got it here", PX0 + PW - 4, ey + 4, 17, DIM, 500, "right", .8); }
    c.font = `500 ${CF}px ${FONT}`;
    for (let x = 0; x < cols; x++) {   // green above the entry line, red below it, grey before you had the card
      const before = x < pullCol, above = pl.v[x] >= entry, lc = before ? FAINT : above ? GREEN : RED, ly = ROWS - 1 - pl.Y[x], age = cols - 1 - x;
      for (let y = 0; y < ROWS; y++) { const chr = pl.grid[y][x]; if (chr === " ") continue; c.globalAlpha = before ? .55 : 1; c.fillStyle = before ? FAINT : age < 3 ? "#ffffff" : lc; c.fillText(chr, PX0 + x * cw, PY0 + y * LH); }
      for (let y = ly + 1; y < ROWS && y - ly < 12; y++) { c.globalAlpha = (before ? .08 : .26) * (1 - (y - ly) / 12.5); c.fillStyle = lc; c.fillText(y - ly === 1 ? ":" : ".", PX0 + x * cw, PY0 + y * LH); }
    }
    c.globalAlpha = 1;
    if (hasPull && pullCol >= 0 && pullCol < cols) coin(PX0 + pullCol * cw - 14, PY0 + (ROWS - 1 - pl.Y[pullCol]) * LH - 32, "P", GREEN, 1);
    const hy = PY0 + (ROWS - 1 - pl.Y[cols - 1]) * LH + LH / 2, hx = PX0 + (cols - 1) * cw;
    if (ch.kf >= r.pk && r.peakPct > r.pct + .08 && r.pk > r.pi) { const pc = Math.round(r.pk / (ch.len - 1) * (cols - 1)), py = PY0 + (ROWS - 1 - pl.Y[pc]) * LH - 36; T("PEAK " + pctShort(r.peakPct), Math.min(Math.max(PX0 + pc * cw - 40, PX0), PX0 + PW - 200), Math.max(py, PY0 - 14), 20, INK, 700, "left", .9); }
    if (rt >= 1 && r.sold) { coin(hx - 70, hy - 56, "S", RED, 1); T(sgn(r.gain), hx - 80, hy - 90, 22, r.gain >= 0 ? GREEN : RED, 700, "right"); }
    drawFace(hx - 40, hy - 2, vh >= entry, 17);
    const tag = money(Math.round(vh)), tx = PX0 + PW + 8, ty = Math.min(Math.max(hy - 16, PY0 - 6), PY0 + ROWS * LH - 28); rr(tx, ty, 108, 32, 8); c.fillStyle = vh >= entry ? "#6fbf7c" : "#e0584c"; c.fill(); T(tag, tx + 54, ty + 6, 20, "#07070b", 700, "center");
  }

  // ---- the loop and the controls
  function loop(now) {
    dtLast = Math.min(.05, (now - last) / 1000 || .016); last = now; clock += dtLast;
    if (mode === "position") { intro += dtLast; if (auto && intro > 2.4 && !reduced) replay(); }
    else if (!paused && rt < 1) { rt = Math.min(1, rt + dtLast * speed / DUR); if (rt >= 1) endAge = 0; } else if (rt >= 1) endAge += dtLast;
    draw(true); ui(); raf = requestAnimationFrame(loop);
  }
  function ui() {
    const left = mode === "replay" ? Math.ceil((1 - rt) * DUR / speed) : Math.ceil(DUR / speed), key = [mode, paused, speed, Math.round(rt * 400), left].join("|"); if (key === lastUi) return; lastUi = key;
    $("shFill").style.width = (mode === "replay" ? rt * 100 : 0) + "%"; $("shLeft").textContent = "-0:" + String(left).padStart(2, "0"); $("shSpeed").textContent = speed + "x";
    $("shPlay").textContent = mode === "position" ? "▶ Replay trade" : rt >= 1 ? "▶ Replay" : paused ? "▶ Play" : "❚❚ Pause";
  }
  function start() { cancelAnimationFrame(raf); clock = 0; last = performance.now(); parts = []; burst = false; lastUi = ""; if (reduced) { mode = "position"; intro = 9; draw(false); ui(); return; } raf = requestAnimationFrame(loop); }
  function replay() { mode = "replay"; rt = 0; paused = false; burst = false; parts = []; endAge = 0; auto = false; }
  function summary() { mode = "position"; intro = 9; auto = false; paused = false; }
  function toggle() { if (mode === "position" || rt >= 1) { replay(); return; } paused = !paused; }
  function seek(e) { const b = $("shTrack").getBoundingClientRect(); if (mode !== "replay") replay(); rt = clampK((e.clientX - b.left) / b.width); burst = rt >= 1; }
  function cycle() { speed = speed === 1 ? 2 : speed === 2 ? 4 : 1; lastUi = ""; }
  const fontReady = () => Promise.race([document.fonts && document.fonts.load ? document.fonts.load("700 22px 'JetBrains Mono'").catch(() => 0) : 0, new Promise(r => setTimeout(r, 1200))]);

  async function open(r) {
    rec = r; rain = null; mode = "position"; intro = 0; rt = 0; speed = 1; auto = true; paused = false; $("share").hidden = false; document.body.style.overflow = "hidden"; cv = $("shCv"); ctx = cv.getContext("2d");
    $("shVideo").hidden = !(window.MediaRecorder && cv.captureStream); img = null; clock = 0; draw(false);
    await fontReady(); img = await loadImg(imgOf(r.card, r.fx)); if ($("share").hidden) return; start();
  }
  function close() { cancelAnimationFrame(raf); raf = 0; $("share").hidden = true; document.body.style.overflow = ""; rec = null; }

  // a still picture of the position card
  function still() { return new Promise(res => { cancelAnimationFrame(raf); const m = mode, i = intro; mode = "position"; intro = 9; draw(false); cv.toBlob(b => { res(b); mode = m; intro = i; if (!$("share").hidden && !reduced) { last = performance.now(); raf = requestAnimationFrame(loop); } }, "image/png"); }); }
  const fileName = ext => `stixx-${rec.card.id}-${rec.pct >= 0 ? "up" : "down"}-${Math.abs(Math.round(rec.pct * 100))}pct.${ext}`;
  const caption = () => `${rec.sold ? "Sold" : "Holding"} ${rec.card.name} on STIXX: ${pctShort(rec.pct)} (${money(rec.cost)} to ${money(rec.got)}). Play money.`;
  async function save() { const b = await still(); if (b) saveBlob(b, fileName("png")); }
  async function share() {
    const b = await still(); if (!b) return; const f = new File([b], fileName("png"), { type: "image/png" });
    try { if (navigator.canShare && navigator.canShare({ files: [f] })) { await navigator.share({ files: [f], title: "STIXX", text: caption() }); return; } } catch (e) { if (e && e.name === "AbortError") return; }
    saveBlob(b, fileName("png"));
  }
  // record the replay itself as a short video
  async function video() {
    if (recording) return; const mime = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"].find(m => MediaRecorder.isTypeSupported(m)); if (!mime) { toast("This browser can't record video. Save the image instead."); return; }
    recording = true; const btn = $("shVideo"), label = btn.textContent; btn.textContent = "recording…"; const chunks = [], mr = new MediaRecorder(cv.captureStream(30), { mimeType: mime, videoBitsPerSecond: 6e6 });
    mr.ondataavailable = e => { if (e.data.size) chunks.push(e.data); }; mr.onstop = () => { recording = false; btn.textContent = label; saveBlob(new Blob(chunks, { type: mime }), fileName(mime.startsWith("video/mp4") ? "mp4" : "webm")); };
    speed = 1; if (!raf) start(); replay(); mr.start(); setTimeout(() => mr.stop(), (DUR + 2) * 1000);
  }
  return { open, close, replay, summary, toggle, seek, cycle, save, share, video };
})();
