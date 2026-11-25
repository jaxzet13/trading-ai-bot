/* ---- the pack screen: the window in the pack plays the pack's own ASCII scene, not its cards (what is inside stays a surprise until you open it).
        Each scene is painted as a small picture first (light, shading, colour), then every cell of the grid becomes the character whose ink matches
        that cell's brightness, in that cell's colour. That is what gives the scene real depth instead of a few hand-placed symbols.
        First Print is a print run: the logo is printed under a glowing print head, catches a shine, then the sheet runs again.
        Moonshot is a launch: a shaded rocket on a flickering flame climbs through moving stars, the Moon glowing in the corner.
        A pack with a cover card wears that card's picture behind the scene: the scene is then drawn lighter and lower, over the art. ---- */
const SPIN = "|/-\\";
const PS_RAMP = " .,:;-=+*xo%#&@";                                                  // ink grows steadily from left to right, so solid shapes read as solid
class PackScreen {
  constructor(pk, pack) {
    this.pk = pk; this.pack = pack || PACKS[0]; this.cv = pk.querySelector("canvas.scr"); this.ctx = this.cv.getContext("2d");
    this.el = { stat: pk.querySelector(".r-stat"), name: pk.querySelector(".r-name"), sub: pk.querySelector(".r-sub"), meter: pk.querySelector(".r-meter") };
    this.on = false; this.last = 0; this.t0 = performance.now(); this.off = document.createElement("canvas"); this.g = this.off.getContext("2d", { willReadFrequently: true }); this.cache = new Map(); this.layer = document.createElement("canvas"); this.lc = this.layer.getContext("2d");
    const n = LIVE.filter(c => c.set === this.pack.set).length;
    this.art = !!this.pack.cover; scramble(this.el.name, this.pack.name.toUpperCase(), 520); this.el.sub.textContent = this.art ? `on the cover: ${BY_ID[this.pack.cover].name} · ${chanceS(packP(this.pack.cover))}` : `${n} cards · one in every pack`;
  }
  fit() {
    const dpr = Math.min(devicePixelRatio || 1, 2), w = this.cv.clientWidth, h = this.cv.clientHeight; if (!w || !h) return;
    if (this.cv.width !== Math.round(w * dpr) || this.cv.height !== Math.round(h * dpr)) { this.cv.width = Math.round(w * dpr); this.cv.height = Math.round(h * dpr); }
    this.dpr = dpr; this.w = w; this.h = h; this.cols = Math.max(48, Math.round(w / 3.1)); const cw = w / this.cols; this.rows = Math.max(30, Math.round(h / (cw * 1.62)));
    if (this.off.width !== this.cols || this.off.height !== this.rows) { this.off.width = this.layer.width = this.cols; this.off.height = this.layer.height = this.rows; }
  }
  status(now, s) { const v = "> " + s + " " + SPIN[Math.floor(now / 110) % 4]; if (v !== this.el.stat._s) { this.el.stat._s = v; this.el.stat.textContent = v; } const mt = meter((Math.floor(now / 380) % 5) + 1, 5); if (mt !== this.el.meter._s) { this.el.meter._s = mt; this.el.meter.textContent = mt; } }
  col(r, g, b) { const k = (r >> 4) << 8 | (g >> 4) << 4 | b >> 4; let v = this.cache.get(k); if (!v) { v = `rgb(${(r >> 4) * 17},${(g >> 4) * 17},${(b >> 4) * 17})`; this.cache.set(k, v); } return v; }
  frame(now) {
    this.fit(); if (!this.w) return; const { cols, rows, w: W, h: H, g } = this, t = Math.max(0, (now - this.t0) / 1000);
    g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = "source-over"; g.shadowBlur = 0; g.fillStyle = "#000"; g.fillRect(0, 0, cols, rows);
    g.setTransform(cols / W, 0, 0, rows / H, 0, 0);                                      // paint in the pack's own pixels; the small canvas averages them into cells
    if (this.pack.id === "ms") this.launch(g, t, W, H); else this.print(g, t, W, H);
    const d = g.getImageData(0, 0, cols, rows).data, c = this.ctx, cw = W / cols, ch = H / rows, N = PS_RAMP.length - 1;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0); if (this.art) c.clearRect(0, 0, W, H); else { c.fillStyle = "#030304"; c.fillRect(0, 0, W, H); }
    c.font = `700 ${(cw / .6).toFixed(2)}px "JetBrains Mono","DejaVu Sans Mono",ui-monospace,monospace`; c.textAlign = "center"; c.textBaseline = "middle";
    for (let y = 0, k = 0; y < rows; y++) for (let x = 0; x < cols; x++, k += 4) {
      const r = d[k], gg = d[k + 1], b = d[k + 2], l = (r * .299 + gg * .587 + b * .114) / 255; if (l < .06) continue;
      const m = Math.max(r, gg, b) || 1, s = Math.min(1, .35 + l * .9), boost = 255 / m * s;                 // vivid colour, dimmer where the picture is dark
      c.fillStyle = this.col(Math.min(255, r * boost), Math.min(255, gg * boost), Math.min(255, b * boost)); c.fillText(PS_RAMP[Math.min(N, Math.round(Math.pow(l, .8) * N))], (x + .5) * cw, (y + .55) * ch);
    }
  }
  print(g, t, W, H) {                                                                    // First Print: the logo prints under a glowing head, shines, then the sheet runs again
    const CYC = 6.4, u = t % CYC, head = u < 2.6 ? (u / 2.6) * (H + 20) - 10 : H + 40, fade = u > 5.8 ? 1 - (u - 5.8) / .6 : 1, run = Math.floor(t / CYC);
    this.status(t * 1000, u < 2.6 ? "printing" : "printed");
    const fit = (txt, wt, maxW, maxS) => { let fs = maxS; g.font = `${wt} ${fs}px "Inter",system-ui,sans-serif`; while (g.measureText(txt).width > maxW && fs > 6) { fs -= 1; g.font = `${wt} ${fs}px "Inter",system-ui,sans-serif`; } return fs; };
    // the sheet: a faint grid of halftone dots, crop marks in the corners
    if (!this.art) { g.fillStyle = "#1c1b19"; for (let y = 8; y < H; y += 9) for (let x = 6 + (y / 9 % 2) * 4.5; x < W; x += 9) g.fillRect(x, y, 1.6, 1.6);
    g.strokeStyle = "#5a574f"; g.lineWidth = 1.4; const cm = 10, L = 14; for (const [x, y, sx, sy] of [[cm, cm, 1, 1], [W - cm, cm, -1, 1], [cm, H - cm, 1, -1], [W - cm, H - cm, -1, -1]]) { g.beginPath(); g.moveTo(x, y + sy * L); g.lineTo(x, y); g.lineTo(x + sx * L, y); g.stroke(); }
    const glow = g.createRadialGradient(W / 2, H * .45, 0, W / 2, H * .45, W * .7); glow.addColorStop(0, "rgba(120,90,40,.55)"); glow.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = glow; g.fillRect(0, 0, W, H); }
    const G0 = g, Lc = this.lc; Lc.setTransform(1, 0, 0, 1, 0, 0); Lc.clearRect(0, 0, this.cols, this.rows); Lc.setTransform(this.cols / W, 0, 0, this.rows / H, 0, 0); g = Lc;     // the ink goes on its own clear layer, so the shine only lights the ink
    g.save(); g.beginPath(); g.rect(0, 0, W, Math.max(0, head)); g.clip(); g.globalAlpha = fade;
    const cx = W / 2, cy = this.art ? H * .84 : H * .44, fs = fit("STIXX", 900, W * (this.art ? .62 : .86), H * .4);
    g.textAlign = "center"; g.textBaseline = "middle"; g.font = `900 ${fs}px "Inter",system-ui,sans-serif`;
    const SY = this.art ? 1.25 : 1.7; g.save(); g.translate(cx, cy); g.scale(1, SY);                              // tall poster lettering
    g.fillStyle = "#34312b"; g.fillText("STIXX", fs * .045, fs * .04);                                              // the shadow under the ink
    const gr = g.createLinearGradient(0, -fs / 2, 0, fs / 2); gr.addColorStop(0, "#ffffff"); gr.addColorStop(.6, "#f3ecdc"); gr.addColorStop(1, "#c9bfa8"); g.fillStyle = gr; g.fillText("STIXX", 0, 0); g.restore();
    const ry = cy + fs * (this.art ? .8 : 1.05), rl = g.createLinearGradient(W * .14, 0, W * .86, 0); rl.addColorStop(0, "rgba(255,196,106,0)"); rl.addColorStop(.5, "#ffc46a"); rl.addColorStop(1, "rgba(255,196,106,0)"); g.fillStyle = rl; g.fillRect(W * .14, ry, W * .72, Math.max(3, H * .012));      // a gold rule under the name
        if (u > 3 && u < 4.4) { const p = (u - 3) / 1.4, bx = -W * .4 + p * W * 1.8, sh = g.createLinearGradient(bx - W * .25, 0, bx + W * .25, 0); sh.addColorStop(0, "rgba(255,255,255,0)"); sh.addColorStop(.5, "rgba(255,246,220,.75)"); sh.addColorStop(1, "rgba(255,255,255,0)"); g.globalCompositeOperation = "source-atop"; g.fillStyle = sh; g.fillRect(0, 0, W, H); g.globalCompositeOperation = "source-over"; }
    if (head < H) { const wet = g.createLinearGradient(0, head - 26, 0, head); wet.addColorStop(0, "rgba(255,210,120,0)"); wet.addColorStop(1, "rgba(255,200,110,.55)"); g.globalCompositeOperation = "source-atop"; g.fillStyle = wet; g.fillRect(0, head - 26, W, 26); g.globalCompositeOperation = "source-over"; }
    g.restore(); g = G0; g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(this.layer, 0, 0); g.restore();
    if (head > -4 && head < H + 4) { g.save(); g.fillStyle = "rgba(255,220,150,.12)"; g.fillRect(0, head - 6, W, 12); g.fillStyle = "#fff6dc"; g.fillRect(0, head - 1.2, W, 2.4); g.restore(); }
  }
  launch(g, t, W, H) {                                                                   // Moonshot: a rocket climbs through moving stars, the Moon in the corner
    this.status(t * 1000, "launching");
    const art = this.art; if (!art) { const sky = g.createLinearGradient(0, 0, 0, H); sky.addColorStop(0, "#0e1a3e"); sky.addColorStop(.5, "#050816"); sky.addColorStop(1, "#000"); g.fillStyle = sky; g.fillRect(0, 0, W, H); }
    const h3 = (a, b) => { const v = Math.imul(a * 73856093 ^ b * 19349663, 2654435761) >>> 0; return v / 4294967296; };
    for (let k = 0; k < (art ? 26 : 70); k++) { const sp = k % 3 === 0 ? 46 : 18, x = h3(k, 1) * W, y = (h3(k, 2) * H + t * sp) % H, tw = .5 + .5 * Math.sin(t * 3 + k), r = k % 3 === 0 ? 1.6 : 1; g.fillStyle = `rgba(235,240,255,${.45 + .55 * tw})`; if (k % 3 === 0) g.fillRect(x - .6, y - r * 3, 1.2, r * 6); else g.fillRect(x, y, r * 1.4, r * 1.4); }
    const mx = W * .8, my = H * .15, mr = art ? 0 : W * .14; if (!art) { g.save(); g.shadowColor = "#a9c4ff"; g.shadowBlur = mr; const mg = g.createRadialGradient(mx - mr * .35, my - mr * .35, mr * .1, mx, my, mr); mg.addColorStop(0, "#ffffff"); mg.addColorStop(1, "#8fa6d6"); g.fillStyle = mg; g.beginPath(); g.arc(mx, my, mr, 0, 7); g.fill(); g.restore();
    g.fillStyle = "rgba(60,75,120,.55)"; for (const [a, b, r] of [[-.3, -.1, .25], [.3, .25, .2], [.05, .45, .13], [.4, -.35, .12]]) { g.beginPath(); g.arc(mx + a * mr, my + b * mr, r * mr, 0, 7); g.fill(); } }
    const cx = W * .44 + Math.sin(t * 1.3) * W * .01, top = H * (art ? .55 : .2) + Math.sin(t * 2.2) * H * .012, rw = W * (art ? .15 : .24), rh = H * (art ? .27 : .44), base = top + rh;
    // smoke and flame first, so the rocket sits on top
    for (let k = 0; k < 16; k++) { const age = (t * .7 + h3(k, 5)) % 1, x = cx + (h3(k, 6) - .5) * W * .9 * age, y = base + rh * .18 + age * (H - base), r = W * (.04 + .1 * age); g.fillStyle = `rgba(150,145,140,${(art ? .3 : .55) * (1 - age)})`; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); }
    const fl = rh * (.42 + .1 * Math.sin(t * 31) + .06 * Math.sin(t * 17)), fw = rw * .42; g.save(); g.globalCompositeOperation = "lighter";
    const fg = g.createLinearGradient(0, base, 0, base + fl); fg.addColorStop(0, "#ffffff"); fg.addColorStop(.25, "#ffe28a"); fg.addColorStop(.6, "#ff8a3c"); fg.addColorStop(1, "rgba(255,60,30,0)"); g.fillStyle = fg;
    g.beginPath(); g.moveTo(cx - fw, base); g.quadraticCurveTo(cx - fw * .9, base + fl * .5, cx, base + fl); g.quadraticCurveTo(cx + fw * .9, base + fl * .5, cx + fw, base); g.closePath(); g.fill();
    g.fillStyle = "rgba(255,255,255,.9)"; g.beginPath(); g.ellipse(cx, base + fl * .12, fw * .45, fl * .18, 0, 0, 7); g.fill(); g.restore();
    // the rocket: shaded like a cylinder, red nose and fins, a lit window
    const body = g.createLinearGradient(cx - rw / 2, 0, cx + rw / 2, 0); body.addColorStop(0, "#9b968e"); body.addColorStop(.4, "#ffffff"); body.addColorStop(.75, "#e4dfd6"); body.addColorStop(1, "#8a857d"); 
    g.fillStyle = "#c8372f"; for (const s of [-1, 1]) { g.beginPath(); g.moveTo(cx + s * rw * .45, base - rh * .3); g.lineTo(cx + s * rw * 1.0, base + rh * .02); g.lineTo(cx + s * rw * .45, base - rh * .02); g.closePath(); g.fill(); }
    g.fillStyle = body; g.beginPath(); g.moveTo(cx, top); g.bezierCurveTo(cx + rw * .62, top + rh * .18, cx + rw * .5, top + rh * .4, cx + rw * .5, base - rh * .05); g.lineTo(cx - rw * .5, base - rh * .05); g.bezierCurveTo(cx - rw * .5, top + rh * .4, cx - rw * .62, top + rh * .18, cx, top); g.fill();
    g.save(); g.clip(); const nose = g.createLinearGradient(cx - rw / 2, 0, cx + rw / 2, 0); nose.addColorStop(0, "#b8322a"); nose.addColorStop(.4, "#ff6a58"); nose.addColorStop(1, "#a82a22"); g.fillStyle = nose; g.fillRect(cx - rw, top, rw * 2, rh * .22); g.fillStyle = "#3d3b38"; g.fillRect(cx - rw, top + rh * .22, rw * 2, rh * .015); g.restore();
    const wy = top + rh * .42, wr = rw * .2; g.fillStyle = "#2f2d2a"; g.beginPath(); g.arc(cx, wy, wr * 1.3, 0, 7); g.fill(); const wg = g.createRadialGradient(cx - wr * .4, wy - wr * .4, 1, cx, wy, wr); wg.addColorStop(0, "#e6f6ff"); wg.addColorStop(1, "#2d8fd8"); g.fillStyle = wg; g.beginPath(); g.arc(cx, wy, wr, 0, 7); g.fill();
    g.fillStyle = "#3a3835"; g.fillRect(cx - rw * .32, base - rh * .05, rw * .64, rh * .05); g.fillStyle = "#c8372f"; g.fillRect(cx - rw * .06, base - rh * .3, rw * .12, rh * .26);
  }
  start() { if (this.on) return; this.on = true; const loop = now => { if (!this.on) return; if (!this.pk.isConnected) { this.on = false; return; } if (!document.hidden && now - this.last > 40 && this.pk.offsetParent) { this.last = now; this.frame(now); } requestAnimationFrame(loop); }; requestAnimationFrame(loop); }
  stop() { this.on = false; }
}

/* ---- the veil: a card face-down is a field of flickering characters; revealing it decodes row by row ---- */
class Veil {
  constructor(host, rar) {
    this.host = host; this.tier = RAR[rar].tier; this.col = RAR[rar].col; this.cv = document.createElement("canvas"); this.cv.className = "veil"; host.appendChild(this.cv);
    const dpr = Math.min(devicePixelRatio || 1, 2), w = host.offsetWidth, h = host.offsetHeight; this.w = w; this.h = h; this.cv.width = w * dpr; this.cv.height = h * dpr; this.ctx = this.cv.getContext("2d"); this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.cell = Math.max(9, Math.round(w / 24)); this.cols = Math.ceil(w / this.cell); this.rows = Math.ceil(h / (this.cell * 1.55));
    this.thr = Float32Array.from({ length: this.cols * this.rows }, (_, i) => .72 * Math.floor(i / this.cols) / this.rows + .28 * Math.random());
    this.gl = Array.from({ length: this.cols * this.rows }, () => "01#%&@$*+=-:."[Math.floor(Math.random() * 13)]);
    this.p = -1; this.live = false; this.dpr = dpr; this.back = this.drawBack(w, h, dpr);
  }
  // the back of a card: a steel frame, a field of quiet type, and the STIXX mark in the middle, lit in the colour of what is underneath
  drawBack(w, h, dpr) {
    const cv = document.createElement("canvas"); cv.width = w * dpr; cv.height = h * dpr; const x = cv.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0);
    const rr = (a, b, c, d, r) => { x.beginPath(); x.moveTo(a + r, b); x.arcTo(a + c, b, a + c, b + d, r); x.arcTo(a + c, b + d, a, b + d, r); x.arcTo(a, b + d, a, b, r); x.arcTo(a, b, a + c, b, r); x.closePath(); };
    let g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, "#16181d"); g.addColorStop(.5, "#08090b"); g.addColorStop(1, "#111317"); x.fillStyle = g; x.fillRect(0, 0, w, h);
    const cx = w / 2, cy = h * .47, R = w * .46; g = x.createRadialGradient(cx, cy, 0, cx, cy, R); g.addColorStop(0, this.col); g.addColorStop(1, "transparent"); x.globalAlpha = .2 + this.tier * .035; x.fillStyle = g; x.fillRect(0, 0, w, h); x.globalAlpha = 1;
    const f = w * .0115; g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, "#d9dce2"); g.addColorStop(.2, "#8b8f98"); g.addColorStop(.48, "#3c3f46"); g.addColorStop(.84, "#8b8f98"); g.addColorStop(1, "#c8ccd4");
    x.strokeStyle = g; x.lineWidth = f; rr(f / 2, f / 2, w - f, h - f, w * .05 - f / 2); x.stroke();                                       // the frame
    const m = w * .05; x.strokeStyle = this.col; x.globalAlpha = .55; x.lineWidth = Math.max(1, w * .004); rr(m, m, w - m * 2, h - m * 2, w * .03); x.stroke();   // an inner line in the rarity's colour
    x.globalAlpha = .18; x.lineWidth = 1; rr(m * 1.5, m * 1.5, w - m * 3, h - m * 3, w * .022); x.stroke(); x.globalAlpha = 1;
    const s = w * .25, k = s / 28, ox = cx - s / 2, oy = cy - s / 2; x.shadowColor = this.col; x.shadowBlur = w * .09; x.fillStyle = "#000"; rr(ox, oy, s, s, 7.5 * k); x.fill(); x.shadowBlur = 0;   // the mark
    x.strokeStyle = "rgba(255,255,255,.28)"; x.lineWidth = Math.max(1, k * .6); rr(ox, oy, s, s, 7.5 * k); x.stroke();
    x.fillStyle = "#fff"; x.beginPath(); x.arc(ox + 14 * k, oy + 5.9 * k, 1.55 * k, 0, 7); x.fill();
    x.strokeStyle = "#fff"; x.lineWidth = 1.7 * k; x.lineCap = "round"; x.beginPath(); x.moveTo(ox + 8.2 * k, oy + 9.8 * k); x.lineTo(ox + 19.8 * k, oy + 21.4 * k); x.moveTo(ox + 19.8 * k, oy + 9.8 * k); x.lineTo(ox + 8.2 * k, oy + 21.4 * k); x.stroke();
    x.font = `800 ${Math.round(w * .058)}px Inter,system-ui,sans-serif`; x.textAlign = "center"; x.textBaseline = "middle"; x.fillStyle = "rgba(255,255,255,.9)"; "STIXX".split("").forEach((c, i) => x.fillText(c, cx + (i - 2) * w * .078, cy + s * .82));
    this.hole = [cx, cy + s * .12, w * .31]; return cv;
  }
  frame() {
    const { ctx, cols, rows, cell, p } = this, rh = cell * 1.55; ctx.clearRect(0, 0, this.w, this.h);
    ctx.font = `700 ${Math.round(cell * 1.02)}px "JetBrains Mono","DejaVu Sans Mono",monospace`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const idle = .34 + this.tier * .05;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const i = r * cols + c, th = this.thr[i]; if (p >= 0 && p > th + .1) continue;
      const d = this.dpr, x0 = c * cell, y0 = r * rh, sw = Math.min(cell + 1, this.w - x0), sh = Math.min(rh + 1, this.h - y0); ctx.globalAlpha = 1; ctx.drawImage(this.back, x0 * d, y0 * d, sw * d, sh * d, x0, y0, sw, sh);
      const hx = x0 + cell / 2 - this.hole[0], hy = y0 + rh / 2 - this.hole[1], near = Math.min(1, Math.max(0, (Math.hypot(hx, hy) - this.hole[2] * .78) / (this.hole[2] * .5))), edge = c < 2 || c > cols - 3 || r < 1 || r > rows - 2;   // the type keeps clear of the mark and the frame
      const front = p >= 0 && p > th; if (Math.random() < (front ? .9 : .12)) this.gl[i] = "01#%&@$*+=-:."[Math.floor(Math.random() * 13)];
      if (!front && (edge || near <= 0)) continue;
      ctx.globalAlpha = front ? 1 : (idle * .62 + (this.live && this.tier ? .12 * Math.sin(performance.now() / 260 + c * .6 + r * .4) : 0)) * near;
      ctx.fillStyle = front ? "#fff" : this.col; ctx.fillText(this.gl[i], c * cell + cell / 2, r * rh + rh / 2);
    }
    ctx.globalAlpha = 1;
  }
  scatter() { for (let i = 0; i < this.thr.length; i++) this.thr[i] = Math.random(); return this; }     // come off all over at once, not from the top down
  idle() { this.live = true; const loop = () => { if (!this.live || this.p >= 0) return; this.frame(); setTimeout(() => requestAnimationFrame(loop), 70); }; loop(); }
  play(ms, onBeat) {
    this.live = false; const t0 = performance.now(); let beat = 0;
    return new Promise(res => { const step = now => { this.p = (now - t0) / ms * 1.2 - .05; if (onBeat && this.p > beat * .22 && beat < 4) { beat++; onBeat(beat); } this.frame(); if (this.p < 1.1) requestAnimationFrame(step); else { this.cv.remove(); res(); } }; this.p = -.05; requestAnimationFrame(step); });
  }
  drop() { this.live = false; this.cv.remove(); }
}

/* ---- the reveal: the picture slowly comes into focus, from a few big characters to the real thing ----
   A canvas over the card's picture. The picture is drawn as coloured characters taken from the picture itself, first in a very
   coarse grid (6 across) and then in finer and finer ones (8, 11, 15, 21, 29, 40, 55, 76), each only a little finer than the
   last, so it reads as one slow sharpening and not as steps. Nothing sweeps and nothing flickers: in every pass the new
   characters come in all over the card in no order, the big early ones fading in, the small late ones simply appearing,
   and the whole canvas starts soft and dim and pulls into focus as it goes. At the end it fades to the real picture underneath.
   A rarer card gets a finer last pass and more time. play() reports how far along it is, so the count of characters and
   the card's worth can climb with it. Settled characters are stamped once onto a second canvas. */
const RV_RAMP = ".,:;-=+*xo%#&@";
class Resolve {
  constructor(card, tier, col) {
    this.pic = card.querySelector(".pic"); this.img = this.pic.querySelector("img"); this.tier = tier; this.col = col; this.cv = document.createElement("canvas"); this.cv.className = "resolve";
    const w = this.pic.clientWidth, h = this.pic.clientHeight, d = Math.min(devicePixelRatio || 1, 2); this.w = w; this.h = h; this.cv.width = Math.round(w * d); this.cv.height = Math.round(h * d);
    this.ctx = this.cv.getContext("2d"); this.ctx.setTransform(d, 0, 0, d, 0, 0); this.ctx.fillStyle = "#020203"; this.ctx.fillRect(0, 0, w, h); this.pic.appendChild(this.cv);
    this.base = document.createElement("canvas"); this.base.width = this.cv.width; this.base.height = this.cv.height; this.bx = this.base.getContext("2d"); this.bx.setTransform(d, 0, 0, d, 0, 0); this.bx.fillStyle = "#020203"; this.bx.fillRect(0, 0, w, h);
  }
  // the picture has to be loaded and readable; if it is not, the caller falls back to showing it at once
  async ready() {
    try { if (!this.img.complete || !this.img.naturalWidth) await Promise.race([this.img.decode(), new Promise((_, no) => setTimeout(no, 900))]); const t = document.createElement("canvas"); t.width = t.height = 2; const x = t.getContext("2d"); x.drawImage(this.img, 0, 0, 2, 2); x.getImageData(0, 0, 1, 1); return this.w > 0; } catch (e) { return false; }
  }
  grid(cols) {                                                                             // the picture at `cols` characters across: one colour per character, and the order they come in
    const cw = this.w / cols, ch = cw * 1.7, rows = Math.ceil(this.h / ch), t = document.createElement("canvas"); t.width = cols; t.height = rows; const x = t.getContext("2d");
    const iw = this.img.naturalWidth, ih = this.img.naturalHeight, s = Math.max(this.w / iw, this.h / ih), sw = this.w / s, sh = this.h / s;
    x.drawImage(this.img, (iw - sw) / 2, (ih - sh) / 2, sw, Math.min(ih, sh * rows * ch / this.h), 0, 0, cols, rows); const d = x.getImageData(0, 0, cols, rows).data, N = cols * rows;
    const ord = new Float32Array(N), idx = Array.from({ length: N }, (_, i) => i); for (let i = 0; i < N; i++) ord[i] = Math.random();
    idx.sort((a, b) => ord[a] - ord[b]); const soft = cols <= 29; return { cols, rows, cw, ch, d, N, ord, idx, soft, lead: soft ? .5 : 1 };       // the few big characters of an early pass fade in; the many small ones of a late pass just appear
  }
  ink(g, i) { const R = g.d[i * 4], G = g.d[i * 4 + 1], B = g.d[i * 4 + 2], m = Math.max(R, G, B); if (m < 16) return null; const l = m / 255, k = (.62 + .38 * l) * 255 / m; return { body: `rgb(${R * .28 | 0},${G * .28 | 0},${B * .28 | 0})`, col: `rgb(${Math.min(255, R * k) | 0},${Math.min(255, G * k) | 0},${Math.min(255, B * k) | 0})`, ch: RV_RAMP[Math.min(RV_RAMP.length - 1, (Math.pow(l, .8) * RV_RAMP.length) | 0)] }; }
  put(c, g, i, a) {                                                                        // one character in its place, at strength a
    const x = (i % g.cols) * g.cw, y = ((i / g.cols) | 0) * g.ch, k = this.ink(g, i); c.globalAlpha = a; c.fillStyle = "#020203"; c.fillRect(x, y, g.cw + .7, g.ch + .7); if (!k) return;
    c.fillStyle = k.body; c.fillRect(x, y, g.cw + .7, g.ch + .7); c.fillStyle = k.col; c.fillText(k.ch, x + g.cw / 2, y + g.ch / 2);
  }
  play(ms, onProg, onPass) {
    const all = [6, 8, 11, 15, 21, 29, 40, 55, 76], n = Math.min(all.length, 8 + Math.min(1, this.tier)), cols = all.slice(0, n), wts = cols.map(c => Math.pow(c, .35)), tot = wts.reduce((a, b) => a + b, 0), ctx = this.ctx, bx = this.bx;
    let acc = 0; const spans = wts.map(w => { const s = [acc / tot, (acc + w) / tot]; acc += w; return s; }), grids = cols.map(c => this.grid(c)), t0 = performance.now(), FADE = 170; let si = -1, ptr = 0, live = [], cut = null;
    const font = g => { const f = `700 ${Math.max(4, g.ch * .98).toFixed(1)}px "JetBrains Mono","DejaVu Sans Mono",ui-monospace,monospace`; [ctx, bx].forEach(c => { c.font = f; c.textAlign = "center"; c.textBaseline = "middle"; }); };
    const finish = g => { live.forEach(i => this.put(bx, g, i, 1)); live = []; for (; ptr < g.N; ptr++) this.put(bx, g, g.idx[ptr], 1); };                         // whatever of a pass is still coming in settles before the next one starts
    return new Promise(res => { const step = now => {
      let p = Math.min(1, (now - t0) / ms); if (this.hurry) { if (!cut) cut = { at: now, p }; p = Math.min(1, cut.p + (1 - cut.p) * (now - cut.at) / 220); }   // a tap while it forms: the rest arrives in a fifth of a second
      let k = spans.findIndex(s => p < s[1]); if (k < 0) k = n - 1;
      if (k !== si) { if (si >= 0) finish(grids[si]); si = k; ptr = 0; font(grids[k]); if (onPass) onPass(k, n); }
      const g = grids[k], q = (p - spans[k][0]) / (spans[k][1] - spans[k][0]), D = 1 - g.lead;
      while (ptr < g.N && g.ord[g.idx[ptr]] * g.lead <= q) { const i = g.idx[ptr++]; if (g.soft) live.push(i); else this.put(bx, g, i, 1); }
      if (g.soft) { const keep = []; for (const i of live) { if ((q - g.ord[i] * g.lead) / D >= 1) this.put(bx, g, i, 1); else keep.push(i); } live = keep; }
      bx.globalAlpha = 1; ctx.globalAlpha = 1; ctx.drawImage(this.base, 0, 0, this.w, this.h);
      for (const i of live) { const e = Math.max(0, (q - g.ord[i] * g.lead) / D); this.put(ctx, g, i, e * e * (3 - 2 * e)); } ctx.globalAlpha = 1;
      this.cv.style.filter = p < .97 ? `blur(${(Math.pow(1 - p, 1.6) * 6).toFixed(2)}px) brightness(${(.7 + .3 * p).toFixed(3)})` : "";             // soft and dim at first, pulling into focus
      if (onProg) onProg(p);
      if (p < 1) requestAnimationFrame(step); else { finish(g); bx.globalAlpha = 1; ctx.drawImage(this.base, 0, 0, this.w, this.h); this.cv.style.filter = ""; this.cv.style.transition = `opacity ${FADE}ms ease-out`; this.cv.style.opacity = "0"; setTimeout(() => this.cv.remove(), FADE + 40); res(); }
    }; requestAnimationFrame(step); });
  }
  rush() { this.hurry = true; }
  drop() { this.cv.remove(); }
}

/* ---- light thrown around the stage: sparks and a ring, not letters ----
   A burst is a spray of small glowing streaks (each drawn as its own short trail, added on top of each other so they bloom where
   they cross) that slow, fall a little and die out, with one ring of light opening from the middle of a big one. */
const FX = (() => {
  const cv = $("fx"), c = cv.getContext("2d"); let parts = [], rings = [], raf = 0, last = 0;
  const fit = () => { const d = Math.min(devicePixelRatio || 1, 2), w = cv.clientWidth, h = cv.clientHeight; if (cv.width !== Math.round(w * d)) { cv.width = Math.round(w * d); cv.height = Math.round(h * d); } c.setTransform(d, 0, 0, d, 0, 0); return [w, h]; };
  function loop(now) {
    const dt = clamp((now - last) / 1000, 0, .05); last = now; const [w, h] = fit(); c.clearRect(0, 0, w, h); c.globalCompositeOperation = "lighter"; c.lineCap = "round";   // never negative: the first frame's clock can sit a hair before the moment the burst was asked for
    for (const r of rings) { r.l -= dt; r.r += r.v * dt; r.v *= .93; const a = clamp(r.l / r.m, 0, 1); c.globalAlpha = a * a * .7; c.strokeStyle = r.col; c.lineWidth = 1.5 + 10 * a; c.beginPath(); c.arc(r.x, r.y, Math.max(0, r.r), 0, 6.2832); c.stroke(); c.globalAlpha = a * a * .5; c.strokeStyle = "#fff"; c.lineWidth = 1.2; c.stroke(); }
    for (const p of parts) {
      p.vx *= p.dr; p.vy = p.vy * p.dr + p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt; p.l -= dt; const a = clamp(p.l / p.m * 1.5, 0, 1) * (.75 + .25 * Math.sin(p.l * 40 + p.s)), tx = p.x - p.vx * .045, ty = p.y - p.vy * .045, wd = p.s * .16;
      c.globalAlpha = a * .32; c.strokeStyle = p.col; c.lineWidth = wd * 3.2; c.beginPath(); c.moveTo(tx, ty); c.lineTo(p.x, p.y); c.stroke();                // its glow
      c.globalAlpha = a; c.lineWidth = wd; c.beginPath(); c.moveTo(tx, ty); c.lineTo(p.x, p.y); c.stroke();                                                    // the streak
      c.globalAlpha = a * .9; c.fillStyle = "#fff"; c.beginPath(); c.arc(p.x, p.y, wd * .55, 0, 6.2832); c.fill();                                             // a white-hot head
    }
    parts = parts.filter(p => p.l > 0); rings = rings.filter(r => r.l > 0); c.globalAlpha = 1; c.globalCompositeOperation = "source-over";
    if (parts.length || rings.length) raf = requestAnimationFrame(loop); else { c.clearRect(0, 0, w, h); raf = 0; }
  }
  const kick = () => { if (!raf && !reduced) { last = performance.now(); raf = requestAnimationFrame(loop); } };
  return {
    burst(x, y, n, cols, speed) {
      for (let i = 0; i < n; i++) { const a = Math.random() * 6.283, v = speed * (.25 + Math.random() * Math.random() * 1.1), l = .5 + Math.random() * .9; parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - speed * .12, g: 300, dr: .972, l, m: l, s: 9 + Math.random() * 13, col: cols[i % cols.length] }); }
      if (n >= 12) rings.push({ x, y, r: 8, v: speed * 1.5, l: .55, m: .55, col: cols[0] }); kick();
    },
    rain(x, w, n, cols) { for (let i = 0; i < n; i++) { const l = 1.4 + Math.random(); parts.push({ x: x + (Math.random() - .5) * w, y: -20 - Math.random() * 160, vx: (Math.random() - .5) * 50, vy: 120 + Math.random() * 240, g: 380, dr: .995, l, m: l, s: 9 + Math.random() * 12, col: cols[i % cols.length] }); } kick(); },
    clear() { parts = []; rings = []; }
  };
})();
