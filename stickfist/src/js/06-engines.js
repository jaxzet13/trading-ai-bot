/* ---- the pack screen: the window in the pack plays the pack's own ASCII scene, not its cards (what is inside stays a surprise until you open it).
        Each scene is painted as a small picture first (light, shading, colour), then every cell of the grid becomes the character whose ink matches
        that cell's brightness, in that cell's colour. That is what gives the scene real depth instead of a few hand-placed symbols.
        First Print is a print run: the logo is printed under a glowing print head, catches a shine, then the sheet runs again.
        Moonshot is a launch: a shaded rocket on a flickering flame climbs through moving stars, the Moon glowing in the corner. ---- */
const SPIN = "|/-\\";
const PS_RAMP = " .,:;-=+*xo%#&@";                                                  // ink grows steadily from left to right, so solid shapes read as solid
class PackScreen {
  constructor(pk, pack) {
    this.pk = pk; this.pack = pack || PACKS[0]; this.cv = pk.querySelector("canvas.scr"); this.ctx = this.cv.getContext("2d");
    this.el = { stat: pk.querySelector(".r-stat"), name: pk.querySelector(".r-name"), sub: pk.querySelector(".r-sub"), meter: pk.querySelector(".r-meter") };
    this.on = false; this.last = 0; this.t0 = performance.now(); this.off = document.createElement("canvas"); this.g = this.off.getContext("2d", { willReadFrequently: true }); this.cache = new Map(); this.layer = document.createElement("canvas"); this.lc = this.layer.getContext("2d");
    const n = CARDS.filter(c => c.set === this.pack.set).length;
    scramble(this.el.name, this.pack.name.toUpperCase(), 520); this.el.sub.textContent = `${n} cards inside · ${this.pack.n} in every pack`;
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
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0); c.fillStyle = "#030304"; c.fillRect(0, 0, W, H);
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
    g.fillStyle = "#1c1b19"; for (let y = 8; y < H; y += 9) for (let x = 6 + (y / 9 % 2) * 4.5; x < W; x += 9) g.fillRect(x, y, 1.6, 1.6);
    g.strokeStyle = "#5a574f"; g.lineWidth = 1.4; const cm = 10, L = 14; for (const [x, y, sx, sy] of [[cm, cm, 1, 1], [W - cm, cm, -1, 1], [cm, H - cm, 1, -1], [W - cm, H - cm, -1, -1]]) { g.beginPath(); g.moveTo(x, y + sy * L); g.lineTo(x, y); g.lineTo(x + sx * L, y); g.stroke(); }
    const glow = g.createRadialGradient(W / 2, H * .45, 0, W / 2, H * .45, W * .7); glow.addColorStop(0, "rgba(120,90,40,.55)"); glow.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = glow; g.fillRect(0, 0, W, H);
    const G0 = g, Lc = this.lc; Lc.setTransform(1, 0, 0, 1, 0, 0); Lc.clearRect(0, 0, this.cols, this.rows); Lc.setTransform(this.cols / W, 0, 0, this.rows / H, 0, 0); g = Lc;     // the ink goes on its own clear layer, so the shine only lights the ink
    g.save(); g.beginPath(); g.rect(0, 0, W, Math.max(0, head)); g.clip(); g.globalAlpha = fade;
    const cx = W / 2, cy = H * .44, fs = fit("STIXX", 900, W * .86, H * .4);
    g.textAlign = "center"; g.textBaseline = "middle"; g.font = `900 ${fs}px "Inter",system-ui,sans-serif`;
    const SY = 1.7; g.save(); g.translate(cx, cy); g.scale(1, SY);                              // tall poster lettering
    g.fillStyle = "#34312b"; g.fillText("STIXX", fs * .045, fs * .04);                                              // the shadow under the ink
    const gr = g.createLinearGradient(0, -fs / 2, 0, fs / 2); gr.addColorStop(0, "#ffffff"); gr.addColorStop(.6, "#f3ecdc"); gr.addColorStop(1, "#c9bfa8"); g.fillStyle = gr; g.fillText("STIXX", 0, 0); g.restore();
    const ry = cy + fs * 1.05, rl = g.createLinearGradient(W * .14, 0, W * .86, 0); rl.addColorStop(0, "rgba(255,196,106,0)"); rl.addColorStop(.5, "#ffc46a"); rl.addColorStop(1, "rgba(255,196,106,0)"); g.fillStyle = rl; g.fillRect(W * .14, ry, W * .72, Math.max(3, H * .012));      // a gold rule under the name
        if (u > 3 && u < 4.4) { const p = (u - 3) / 1.4, bx = -W * .4 + p * W * 1.8, sh = g.createLinearGradient(bx - W * .25, 0, bx + W * .25, 0); sh.addColorStop(0, "rgba(255,255,255,0)"); sh.addColorStop(.5, "rgba(255,246,220,.75)"); sh.addColorStop(1, "rgba(255,255,255,0)"); g.globalCompositeOperation = "source-atop"; g.fillStyle = sh; g.fillRect(0, 0, W, H); g.globalCompositeOperation = "source-over"; }
    if (head < H) { const wet = g.createLinearGradient(0, head - 26, 0, head); wet.addColorStop(0, "rgba(255,210,120,0)"); wet.addColorStop(1, "rgba(255,200,110,.55)"); g.globalCompositeOperation = "source-atop"; g.fillStyle = wet; g.fillRect(0, head - 26, W, 26); g.globalCompositeOperation = "source-over"; }
    g.restore(); g = G0; g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(this.layer, 0, 0); g.restore();
    if (head > -4 && head < H + 4) { g.save(); g.fillStyle = "rgba(255,220,150,.12)"; g.fillRect(0, head - 6, W, 12); g.fillStyle = "#fff6dc"; g.fillRect(0, head - 1.2, W, 2.4); g.restore(); }
  }
  launch(g, t, W, H) {                                                                   // Moonshot: a rocket climbs through moving stars, the Moon in the corner
    this.status(t * 1000, "launching");
    const sky = g.createLinearGradient(0, 0, 0, H); sky.addColorStop(0, "#0e1a3e"); sky.addColorStop(.5, "#050816"); sky.addColorStop(1, "#000"); g.fillStyle = sky; g.fillRect(0, 0, W, H);
    const h3 = (a, b) => { const v = Math.imul(a * 73856093 ^ b * 19349663, 2654435761) >>> 0; return v / 4294967296; };
    for (let k = 0; k < 70; k++) { const sp = k % 3 === 0 ? 46 : 18, x = h3(k, 1) * W, y = (h3(k, 2) * H + t * sp) % H, tw = .5 + .5 * Math.sin(t * 3 + k), r = k % 3 === 0 ? 1.6 : 1; g.fillStyle = `rgba(235,240,255,${.45 + .55 * tw})`; if (k % 3 === 0) g.fillRect(x - .6, y - r * 3, 1.2, r * 6); else g.fillRect(x, y, r * 1.4, r * 1.4); }
    const mx = W * .8, my = H * .15, mr = W * .14; g.save(); g.shadowColor = "#a9c4ff"; g.shadowBlur = mr; const mg = g.createRadialGradient(mx - mr * .35, my - mr * .35, mr * .1, mx, my, mr); mg.addColorStop(0, "#ffffff"); mg.addColorStop(1, "#8fa6d6"); g.fillStyle = mg; g.beginPath(); g.arc(mx, my, mr, 0, 7); g.fill(); g.restore();
    g.fillStyle = "rgba(60,75,120,.55)"; for (const [a, b, r] of [[-.3, -.1, .25], [.3, .25, .2], [.05, .45, .13], [.4, -.35, .12]]) { g.beginPath(); g.arc(mx + a * mr, my + b * mr, r * mr, 0, 7); g.fill(); }
    const cx = W * .44 + Math.sin(t * 1.3) * W * .01, top = H * .2 + Math.sin(t * 2.2) * H * .012, rw = W * .24, rh = H * .44, base = top + rh;
    // smoke and flame first, so the rocket sits on top
    for (let k = 0; k < 16; k++) { const age = (t * .7 + h3(k, 5)) % 1, x = cx + (h3(k, 6) - .5) * W * .9 * age, y = base + rh * .18 + age * (H - base), r = W * (.04 + .1 * age); g.fillStyle = `rgba(150,145,140,${.55 * (1 - age)})`; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); }
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
    this.p = -1; this.live = false;
  }
  frame() {
    const { ctx, cols, rows, cell, p } = this, rh = cell * 1.55; ctx.clearRect(0, 0, this.w, this.h);
    ctx.font = `700 ${Math.round(cell * 1.02)}px "JetBrains Mono","DejaVu Sans Mono",monospace`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const idle = .34 + this.tier * .05;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const i = r * cols + c, th = this.thr[i]; if (p >= 0 && p > th + .1) continue;
      ctx.globalAlpha = 1; ctx.fillStyle = "#050506"; ctx.fillRect(c * cell, r * rh, cell + 1, rh + 1);
      const front = p >= 0 && p > th; if (Math.random() < (front ? .9 : .12)) this.gl[i] = "01#%&@$*+=-:."[Math.floor(Math.random() * 13)];
      ctx.globalAlpha = front ? 1 : idle + (this.live && this.tier ? .12 * Math.sin(performance.now() / 260 + c * .6 + r * .4) : 0);
      ctx.fillStyle = front ? "#fff" : this.col; ctx.fillText(this.gl[i], c * cell + cell / 2, r * rh + rh / 2);
    }
    ctx.globalAlpha = 1;
  }
  idle() { this.live = true; const loop = () => { if (!this.live || this.p >= 0) return; this.frame(); setTimeout(() => requestAnimationFrame(loop), 70); }; loop(); }
  play(ms, onBeat) {
    this.live = false; const t0 = performance.now(); let beat = 0;
    return new Promise(res => { const step = now => { this.p = (now - t0) / ms * 1.2 - .05; if (onBeat && this.p > beat * .22 && beat < 4) { beat++; onBeat(beat); } this.frame(); if (this.p < 1.1) requestAnimationFrame(step); else { this.cv.remove(); res(); } }; this.p = -.05; requestAnimationFrame(step); });
  }
  drop() { this.live = false; this.cv.remove(); }
}

/* ---- characters thrown around the stage ---- */
const FX = (() => {
  const cv = $("fx"), c = cv.getContext("2d"); let parts = [], raf = 0, last = 0;
  const G = ".:-=+*#%@&$", fit = () => { const d = Math.min(devicePixelRatio || 1, 2), w = cv.clientWidth, h = cv.clientHeight; if (cv.width !== Math.round(w * d)) { cv.width = Math.round(w * d); cv.height = Math.round(h * d); } c.setTransform(d, 0, 0, d, 0, 0); return [w, h]; };
  function loop(now) {
    const dt = Math.min(.05, (now - last) / 1000); last = now; const [w, h] = fit(); c.clearRect(0, 0, w, h); c.textAlign = "center"; c.textBaseline = "middle";
    for (const p of parts) { p.vx *= p.dr; p.vy = p.vy * p.dr + p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt; p.l -= dt; c.globalAlpha = clamp(p.l / p.m * 1.4, 0, 1); c.fillStyle = p.col; c.font = `700 ${p.s}px "JetBrains Mono",monospace`; c.fillText(p.ch, p.x, p.y); }
    parts = parts.filter(p => p.l > 0); c.globalAlpha = 1; if (parts.length) raf = requestAnimationFrame(loop); else { c.clearRect(0, 0, w, h); raf = 0; }
  }
  const kick = () => { if (!raf && !reduced) { last = performance.now(); raf = requestAnimationFrame(loop); } };
  return {
    burst(x, y, n, cols, speed) { for (let i = 0; i < n; i++) { const a = Math.random() * 6.283, v = speed * (.2 + Math.random() * .9), l = .6 + Math.random() * .9; parts.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, g: 380, dr: .985, l, m: l, s: 11 + Math.random() * 12, col: cols[i % cols.length], ch: G[Math.floor(Math.random() * G.length)] }); } kick(); },
    rain(x, w, n, cols) { for (let i = 0; i < n; i++) { const l = 1.4 + Math.random(); parts.push({ x: x + (Math.random() - .5) * w, y: -20 - Math.random() * 160, vx: (Math.random() - .5) * 50, vy: 120 + Math.random() * 240, g: 380, dr: .995, l, m: l, s: 10 + Math.random() * 12, col: cols[i % cols.length], ch: G[Math.floor(Math.random() * G.length)] }); } kick(); },
    clear() { parts = []; }
  };
})();
