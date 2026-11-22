/* ============================================================================
   8g. THE PULL CLIP. One tap turns a pack opening into a 9:16 video: the tear, the cards in rising order, then the best card read into its letters with a
   camera that dives until every character is on screen, and an end card with the total and your invite link. It is drawn on a canvas and recorded while it
   plays, so the file is ready the moment it ends. Every number in it is the real one from your pack. The letters in the zoom are the card's picture read
   into characters, the same way the card was made.
   ========================================================================== */
const Clip = (() => {
  const W = 1080, H = 1920, FONT = "'JetBrains Mono', 'DejaVu Sans Mono', ui-monospace, Menlo, Consolas, monospace";
  const INK = "#ece7dc", DIM = "#8d897f", BG = "#050507", GREEN = "#9fd8a6", ADV = .6;
  const RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$";
  const cl = x => x < 0 ? 0 : x > 1 ? 1 : x, sm = (a, b, t) => { const k = cl((t - a) / (b - a)); return k * k * (3 - 2 * k); }, ease = x => 1 - Math.pow(1 - cl(x), 3), ease2 = x => { x = cl(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  const hash = (i, j, s) => { let h = Math.imul(i * 374761393 + j * 668265263 + s * 982451653, 1274126177); h ^= h >>> 13; return (Math.imul(h, 1103515245) >>> 0) / 4294967296; };
  const DWELL = [.8, .9, 1.05, 1.5, 2, 2.6, 3], ZOOM = 5.4, PRE = 1.3, POST = 1.5, INTRO = 1.5, TEAR = .8, END = 3.4, ZMAX = 18, ZW0 = 760, ZH0 = ZW0 * 1092 / 900, ZCY = 930;
  let cv, ctx, st = null, raf = 0, t0 = 0, recorder = null, chunks = [], blob = null, mime = "", fired = 0, parts = [], lastNow = 0, recording = false;

  function T(str, x, y, size, color, weight, align, alpha) { ctx.font = `${weight || 600} ${size}px ${FONT}`; ctx.textAlign = align || "left"; ctx.textBaseline = "alphabetic"; ctx.fillStyle = color; ctx.globalAlpha = alpha == null ? 1 : alpha; ctx.fillText(str, x, y); ctx.globalAlpha = 1; }
  function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  const glow = (x, y, rad, col, a) => { const g = ctx.createRadialGradient(x, y, 0, x, y, rad); g.addColorStop(0, col); g.addColorStop(1, "rgba(0,0,0,0)"); ctx.globalAlpha = a; ctx.fillStyle = g; ctx.fillRect(x - rad, y - rad, rad * 2, rad * 2); ctx.globalAlpha = 1; };

  /* ---- the picture read into letters, like the card itself was made ---- */
  function readGrid(img, chars) {
    const cols = Math.max(80, Math.round(Math.sqrt(chars * 1.537))), rows = Math.max(60, Math.round(chars / cols)), c = document.createElement("canvas"); c.width = cols; c.height = rows; const x = c.getContext("2d"); x.drawImage(img, 0, 0, cols, rows);
    const d = x.getImageData(0, 0, cols, rows).data, n = cols * rows, lum = new Float32Array(n), col = new Uint8Array(n * 3), chi = new Uint8Array(n);
    for (let i = 0; i < n; i++) { const r = d[i * 4], g = d[i * 4 + 1], b = d[i * 4 + 2], l = (r * .299 + g * .587 + b * .114) / 255; lum[i] = l; col[i * 3] = r; col[i * 3 + 1] = g; col[i * 3 + 2] = b; chi[i] = Math.min(RAMP.length - 1, Math.floor(Math.pow(l, .85) * RAMP.length)); }
    // aim the dive at the busiest patch in the upper middle of the card, where the picture is
    const ww = Math.round(cols * .1), wh = Math.round(rows * .08); let bx = .5, by = .3, bs = -1;
    for (let j = Math.round(rows * .12); j < rows * .55; j += 3) for (let i = Math.round(cols * .2); i < cols * .8 - ww; i += 3) {
      let s = 0, s2 = 0, m = 0; for (let jj = 0; jj < wh; jj += 2) for (let ii = 0; ii < ww; ii += 2) { const l = lum[(j + jj) * cols + i + ii]; s += l; s2 += l * l; m++; }
      const mean = s / m, v = s2 / m - mean * mean, score = v * 4 + mean * .3; if (score > bs) { bs = score; bx = (i + ww / 2) / cols; by = (j + wh / 2) / rows; }
    }
    return { cols, rows, lum, col, chi, tx: bx, ty: by };
  }

  /* ---- the plan: when everything happens ---- */
  async function plan(items, pack, free, price) {
    const rows = items.map(c => ({ c, card: BY_NO[c.no], R: RAR[BY_NO[c.no].rar], val: valueOf(c) })).sort((a, b) => a.val - b.val), best = rows[rows.length - 1], others = rows.slice(0, -1);
    try { await Promise.race([document.fonts.load(`700 40px "JetBrains Mono"`), sleep(1500)]); } catch (e) {}
    for (const r of rows) r.img = await loadImg(imgOf(r.card, r.c.fx));
    let t = INTRO + TEAR; for (const r of others) { r.t0 = t; r.dur = DWELL[Math.min(6, r.R.tier)]; t += r.dur; }
    best.t0 = t; best.zoomAt = t + PRE; t += PRE + ZOOM + POST; best.dur = PRE + ZOOM + POST;
    best.grid = best.img ? readGrid(best.img, best.card.chars) : null;
    const total = rows.reduce((a, r) => a + r.val, 0);
    return { rows, best, others, total, end: t, dur: t + END, pack, free, price, link: Ref.info() ? Ref.link(Ref.info().code) : "", seq: [...others, best] };
  }

  /* ---- drawing ---- */
  function field(t) {                                                       // a quiet drift of characters behind everything
    ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H); ctx.font = `500 26px ${FONT}`; ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillStyle = "#ffffff";
    for (let i = 0; i < 90; i++) { const x = hash(i, 1, 5) * W, y = ((hash(i, 2, 5) * H + t * (14 + hash(i, 3, 5) * 30)) % (H + 40)) - 20; ctx.globalAlpha = .05 + hash(i, 4, 5) * .06; ctx.fillText(".:+*#"[Math.floor(hash(i, 5, 5) * 5)], x, y); } ctx.globalAlpha = 1;
  }
  function card(r, cx, cy, w, a, rot, glowA) {
    if (!r.img || a <= 0) return; const h = w * 1092 / 900; ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot || 0); ctx.globalAlpha = a;
    if (glowA) { glow(0, 0, w * 1.05, r.R.col, glowA * a); ctx.globalAlpha = a; }
    rr(-w / 2, -h / 2, w, h, w * .045); ctx.save(); ctx.clip(); ctx.imageSmoothingQuality = "high"; ctx.drawImage(r.img, -w / 2, -h / 2, w, h); ctx.restore();
    rr(-w / 2, -h / 2, w, h, w * .045); ctx.strokeStyle = r.R.col; ctx.lineWidth = 3; ctx.globalAlpha = a * .8; ctx.stroke(); ctx.restore(); ctx.globalAlpha = 1;
  }
  function burst(x, y, n, col, sp) { for (let i = 0; i < n; i++) { const a = Math.random() * 6.283, v = sp * (.3 + Math.random() * .8); parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - sp * .15, life: .7 + Math.random() * .6, age: 0, col, ch: ".:+*#"[Math.floor(Math.random() * 5)] }); } }
  function drawParts(dt) {
    ctx.font = `700 30px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (const p of parts) { p.age += dt; p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 520 * dt; ctx.globalAlpha = cl(1 - p.age / p.life); ctx.fillStyle = p.col; ctx.fillText(p.ch, p.x, p.y); } ctx.globalAlpha = 1; parts = parts.filter(p => p.age < p.life);
  }
  const cue = (t, fn) => { if (t > fired.t && t <= fired.now) fn(); };

  function frame(now, dt) {
    const s = st, t = now; fired = { t: Math.max(-1, lastNow), now: t }; lastNow = t; field(t);
    // header: what this is, and a running total of what has been revealed so far
    T("STIXX", 66, 112, 52, INK, 700); T(s.free ? "free pack" : s.pack.name, W - 66, 108, 28, DIM, 600, "right");
    const revealed = s.seq.filter(r => t >= r.t0 + .25).reduce((a, r) => a + r.val, 0); if (t > INTRO + TEAR) { T("pulled so far", 66, 168, 24, DIM, 500); T(money(revealed), 66, 226, 56, INK, 700); }
    if (t < INTRO + TEAR) return intro(t, s);
    // the cards
    for (const r of s.seq) {
      const u = t - r.t0; if (u < 0 || u > r.dur) continue; const isBest = r === s.best, tier = r.R.tier, cx = W / 2;
      if (isBest) { best(r, u, t); continue; }
      const inK = ease(u / .28), outK = ease((u - (r.dur - .22)) / .22), y = 1010 + (1 - inK) * 380 - outK * 80, a = inK * (1 - outK), w = 700;
      cue(r.t0 + .02, () => { Snd.reveal(tier); buzz(tier >= 3 ? [30, 25, 50] : [18]); }); cue(r.t0 + .26, () => { if (tier >= 1) burst(cx, 1010, 8 + tier * 10, tier >= 2 ? r.R.col : "#c9c5bb", 420 + tier * 80); });
      card(r, cx, y, w, a, (1 - inK) * .12 * (r.c.uid.charCodeAt(2) % 2 ? 1 : -1), tier >= 2 ? .5 + tier * .06 : .25);
      T(`${r.R.name}${r.c.fx ? " · " + STYLES[r.c.fx].name : ""}`.toUpperCase(), cx, 1480, 30, r.R.col, 700, "center", a); T(r.card.name, cx, 1556, 62, INK, 700, "center", a); T(money(r.val), cx, 1630, 54, GREEN, 700, "center", a);
    }
    drawParts(dt);
    if (t > s.end) endCard(t - s.end, s);
  }
  function intro(t, s) {
    const a = ease(t / .5), tt = t - INTRO, pk = s.pack.name.toUpperCase();
    if (t < INTRO) { T(s.free ? "OPENING A FREE PACK" : "OPENING A PACK", W / 2, 700, 44, DIM, 600, "center", a); T(pk, W / 2, 860, 124, INK, 700, "center", a); T("tap. rip. see what's inside.", W / 2, 960, 34, DIM, 500, "center", a * sm(.5, 1, t)); cue(.9, () => Snd.tear()); return; }
    // the tear: a bright line sweeps across and the pack splits
    const k = ease(tt / TEAR); cue(INTRO + .02, () => { buzz(35); });
    ctx.save(); ctx.translate((Math.random() - .5) * 8 * (1 - k), (Math.random() - .5) * 8 * (1 - k)); T(pk, W / 2 - k * 700, 860, 124, INK, 700, "center", 1 - k); ctx.restore();
    ctx.globalAlpha = 1 - k; ctx.fillStyle = "#fff"; ctx.fillRect(0, 900 - 2, W * Math.min(1, k * 3), 4); ctx.globalAlpha = 1; if (tt < .06 && !parts.length) burst(W / 2, 900, 40, "#fff", 700);
    drawParts(1 / 60);
  }
  /* the best card: it comes in, the camera dives into its letters, then pulls back out to the whole card */
  function best(r, u, t) {
    const R = r.R, cx = W / 2, zu = u - PRE;
    cue(r.t0 + .02, () => { Snd.reveal(Math.min(6, R.tier + 1)); buzz([40, 30, 60, 30, 90]); }); cue(r.t0 + .3, () => burst(cx, ZCY, 60 + R.tier * 20, [R.col, "#fff"][0], 700));
    if (zu < 0 || zu > ZOOM + .05) {
      const inK = ease(u / .35), back = zu > ZOOM ? ease((zu - ZOOM) / .7) : 0, w = ZW0 * (zu > ZOOM ? 1 : .92 + .08 * inK);
      glow(cx, ZCY, 900, R.col, .3 * inK); card(r, cx, ZCY, w, inK, 0, .5);
      if (zu > ZOOM) { const q = ease((zu - ZOOM) / .5); T(`${R.name}${r.c.fx ? " · " + STYLES[r.c.fx].name : ""}`.toUpperCase(), cx, 1500, 32, R.col, 700, "center", q); T(r.card.name, cx, 1585, 74, INK, 700, "center", q); T(money(r.val), cx, 1670, 62, GREEN, 700, "center", q); }
      else T("your best pull", cx, 1500, 34, DIM, 600, "center", inK);
      return;
    }
    cue(r.t0 + PRE + .1, () => Snd.tear()); drawZoom(r, zu, t);
  }
  function zoomAt(u) {
    const a = .5, b = 3, c = 3.9, p = u < a ? 0 : u < b ? ease2((u - a) / (b - a)) : u < c ? 1 : 1 - ease((u - c) / (ZOOM - c)), z = Math.exp(Math.log(ZMAX) * p), g = st.best.grid, tx = g ? g.tx : .5, ty = g ? g.ty : .3;
    const w = (1 - 1 / z) / (1 - 1 / ZMAX), hold = u > b ? Math.min(u, c) - b : 0; return { z, px: .5 + (tx - .5) * w + hold * .0035, py: .5 + (ty - .5) * w + hold * .001 };
  }
  function drawZoom(r, u, t) {
    const { z, px, py } = zoomAt(u), g = r.grid, w0 = ZW0 * z, h0 = ZH0 * z, X = x => W / 2 + (x - px) * w0, Y = y => ZCY + (y - py) * h0, ccx = () => rr(X(0), Y(0), w0, h0, ZW0 * .045 * z);
    glow(W / 2, ZCY, 900, r.R.col, .28 * (1 - sm(1.2, 3, z)));
    const imgA = 1 - sm(2.2, 6.5, z); if (imgA > .01 && r.img) { ctx.save(); ccx(); ctx.clip(); ctx.globalAlpha = imgA; ctx.imageSmoothingQuality = "high"; ctx.drawImage(r.img, X(0), Y(0), w0, h0); ctx.restore(); }
    const bgA = sm(1.8, 6, z); if (bgA > .01) { ctx.save(); ccx(); ctx.clip(); ctx.globalAlpha = bgA * .92; ctx.fillStyle = BG; ctx.fillRect(X(0), Y(0), w0, h0); ctx.restore(); }
    const tA = sm(1.6, 4.5, z), cwp = g ? w0 / g.cols : 0;
    if (g && tA > .01 && cwp > 3.2) {
      const i0 = Math.max(0, Math.floor(((0 - W / 2) / w0 + px) * g.cols)), i1 = Math.min(g.cols - 1, Math.ceil(((W - W / 2) / w0 + px) * g.cols)), j0 = Math.max(0, Math.floor(((0 - ZCY) / h0 + py) * g.rows)), j1 = Math.min(g.rows - 1, Math.ceil(((H - ZCY) / h0 + py) * g.rows));
      ctx.font = `700 ${cwp / ADV}px ${FONT}`; ctx.textBaseline = "top"; ctx.textAlign = "left";
      for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
        const k = j * g.cols + i; if (g.lum[k] < .05) continue; const aa = cl(tA * 1.7 - hash(i, j, 77) * .7); if (aa <= 0) continue; const m = 1.3 * (.92 + .08 * Math.sin(t * 5 + hash(i, j, 78) * 9));
        ctx.globalAlpha = aa; ctx.fillStyle = `rgb(${Math.min(255, g.col[k * 3] * m) | 0},${Math.min(255, g.col[k * 3 + 1] * m) | 0},${Math.min(255, g.col[k * 3 + 2] * m) | 0})`; ctx.fillText(RAMP[g.chi[k]], X(i / g.cols), Y(j / g.rows));
      }
      ctx.globalAlpha = 1; ctx.textBaseline = "alphabetic";
    }
    const chars = fmt(r.card.chars);
    T(z < 5 ? "every card is made of letters" : `${chars} characters`, W / 2, 1640, z < 5 ? 38 : 56, INK, 700, "center", sm(1.15, 1.9, z) * (z < 5 ? 1 : sm(5, 9, z) * .9 + .1));
    T("your best pull", W / 2, 1500, 34, DIM, 600, "center", 1 - sm(1.1, 1.7, z));
  }
  function endCard(u, s) {
    const a = ease(u / .5); ctx.globalAlpha = a * .9; ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1;
    cue(s.end + .1, () => { Snd.level(); buzz([20, 30, 20]); });
    T(s.free ? "from a free pack" : s.price < 0 ? "from a pack" : `from a ${money(s.price)} pack`, W / 2, 560, 38, DIM, 600, "center", a);
    T(money(s.total), W / 2, 760, 188, INK, 700, "center", a); T("worth of cards", W / 2, 830, 40, DIM, 600, "center", a);
    T(`best: ${s.best.card.name} · ${s.best.R.name}`, W / 2, 960, 40, s.best.R.col, 700, "center", a * sm(.3, .8, u));
    const k = sm(.6, 1.2, u); ctx.globalAlpha = k; rr(140, 1130, W - 280, 150, 24); ctx.fillStyle = INK; ctx.fill(); ctx.globalAlpha = 1; T("open yours free", W / 2, 1230, 62, "#050507", 700, "center", k);
    T(s.link ? s.link.replace(/^https?:\/\//, "") : location.host || "stixx", W / 2, 1360, s.link && s.link.length > 40 ? 30 : 38, INK, 600, "center", k);
    T("play money · no cash value · 18+", W / 2, 1810, 26, DIM, 500, "center", k);
  }

  /* ---- playing and recording ---- */
  function loop(ts) {
    if (!st) return; const now = (ts - t0) / 1000, dt = Math.min(.05, (ts - (loop.last || ts)) / 1000); loop.last = ts;
    if (now >= st.dur + .3) { finish(); return; } frame(Math.max(0, now), dt); raf = requestAnimationFrame(loop);
  }
  function start() { cancelAnimationFrame(raf); parts = []; lastNow = -1; loop.last = 0; t0 = performance.now(); raf = requestAnimationFrame(loop); }
  function finish() {
    cancelAnimationFrame(raf); frame(st.dur - .2, .016); if (recorder && recorder.state !== "inactive") recorder.stop(); else ready();
  }
  function ready() { const b = $("clSave"); b.disabled = false; $("clShare").disabled = false; $("clState").textContent = blob ? "Your clip is ready." : "Your clip played. This browser can't record video, so you can save the end card as a picture."; if (!blob) b.textContent = "save picture"; }
  async function record() {
    blob = null; recorder = null; chunks = []; if (!window.MediaRecorder || !cv.captureStream) return;
    mime = ["video/mp4;codecs=avc1,mp4a.40.2", "video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9,opus", "video/webm;codecs=vp9", "video/webm"].find(m => MediaRecorder.isTypeSupported(m)); if (!mime) return;
    const stream = cv.captureStream(30); try { const at = Snd.tap(); if (at && /mp4a|opus/.test(mime)) at.getAudioTracks().forEach(tk => stream.addTrack(tk)); } catch (e) {}
    try { recorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 7e6 }); } catch (e) { recorder = null; return; }
    recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); }; recorder.onstop = () => { blob = chunks.length ? new Blob(chunks, { type: mime }) : null; ready(); }; recorder.start(250);
  }
  async function open(items, pack, free, price) {
    cv = $("clCv"); ctx = cv.getContext("2d"); $("clip").hidden = false; $("clSave").disabled = true; $("clShare").disabled = true; $("clSave").textContent = "save video"; $("clState").textContent = "Making your clip…";
    ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H); st = await plan(items, pack, free, price); if ($("clip").hidden) { st = null; return; }
    API.post("event", { uid: state.uid, name: "clip" }); await record(); start();
  }
  function close() { cancelAnimationFrame(raf); if (recorder && recorder.state !== "inactive") { recorder.onstop = null; try { recorder.stop(); } catch (e) {} } st = null; recorder = null; $("clip").hidden = true; }
  const fname = ext => `stixx-pull-${Date.now().toString(36)}.${ext}`;
  const caption = () => `${st ? money(st.total) : ""} of cards from a ${st && st.free ? "free " : ""}STIXX pack. ${Ref.text} ${st && st.link ? st.link : ""}`.trim();
  async function stillBlob() { frame(st.dur - .2, .016); return new Promise(res => cv.toBlob(res, "image/png")); }
  async function save() {
    if (!st) return; API.post("event", { uid: state.uid, name: "clipSave" }); if (blob) return saveBlob(blob, fname(mime.startsWith("video/mp4") ? "mp4" : "webm")); const b = await stillBlob(); if (b) saveBlob(b, fname("png"));
  }
  async function share() {
    if (!st) return; API.post("event", { uid: state.uid, name: "clipShare" }); const b = blob || await stillBlob(); if (!b) return; const ext = blob ? (mime.startsWith("video/mp4") ? "mp4" : "webm") : "png", f = new File([b], fname(ext), { type: blob ? mime.split(";")[0] : "image/png" });
    try { if (navigator.canShare && navigator.canShare({ files: [f] })) { await navigator.share({ files: [f], title: "STIXX", text: caption() }); return; } } catch (e) { if (e && e.name === "AbortError") return; }
    saveBlob(b, fname(ext));
  }
  return { open, close, save, share, replay: () => { if (st) { blob = null; $("clState").textContent = "Replaying…"; start(); } }, get blob() { return blob; } };
})();
