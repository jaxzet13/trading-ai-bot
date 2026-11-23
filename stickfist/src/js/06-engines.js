/* ---- the pack screen: the window in the pack plays the pack's own ASCII scene, not its cards (what is inside stays a surprise until you open it).
        First Print is a print run: the logo is printed line by line under a moving print head, in ink that settles, then the sheet runs again.
        Moonshot is a launch: a rocket on a flickering flame climbs through a starfield, with the Moon hanging in the corner. ---- */
const SPIN = "|/-\\";
class PackScreen {
  constructor(pk, pack) {
    this.pk = pk; this.pack = pack || PACKS[0]; this.cv = pk.querySelector("canvas.scr"); this.ctx = this.cv.getContext("2d");
    this.el = { stat: pk.querySelector(".r-stat"), name: pk.querySelector(".r-name"), sub: pk.querySelector(".r-sub"), meter: pk.querySelector(".r-meter") };
    this.on = false; this.last = 0; this.t0 = performance.now(); this.mask = null; this.stars = null;
    const n = CARDS.filter(c => c.set === this.pack.set).length;
    scramble(this.el.name, this.pack.name.toUpperCase(), 520); this.el.sub.textContent = `${n} cards inside · ${this.pack.n} in every pack`;
  }
  fit() {
    const dpr = Math.min(devicePixelRatio || 1, 2), w = this.cv.clientWidth, h = this.cv.clientHeight; if (!w || !h) return;
    if (this.cv.width !== Math.round(w * dpr) || this.cv.height !== Math.round(h * dpr)) { this.cv.width = Math.round(w * dpr); this.cv.height = Math.round(h * dpr); this.mask = null; this.stars = null; }
    this.dpr = dpr; this.w = w; this.h = h; this.cols = Math.max(30, Math.round(w / 5.2)); this.rows = Math.max(20, Math.round(h / (w / this.cols * 1.6)));
  }
  logo() {                                                                              // the word, as a grid of on/off cells, for the print run
    const c = document.createElement("canvas"), cols = this.cols, rows = this.rows; c.width = cols; c.height = rows; const g = c.getContext("2d");
    g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "middle"; let fs = rows; g.font = `900 ${fs}px "Inter",sans-serif`; while (g.measureText("STIXX").width > cols * .9 && fs > 4) { fs -= .5; g.font = `900 ${fs}px "Inter",sans-serif`; }
    g.save(); g.translate(cols / 2, rows * .46); g.scale(1, .62 * 1.15); g.fillText("STIXX", 0, 0); g.restore();      // cells are taller than wide, so the word is squashed to read upright
    const d = g.getImageData(0, 0, cols, rows).data, m = new Float32Array(cols * rows); for (let k = 0; k < m.length; k++) m[k] = d[k * 4 + 3] / 255; return m;
  }
  status(now, s) { const v = "> " + s + " " + SPIN[Math.floor(now / 110) % 4]; if (v !== this.el.stat._s) { this.el.stat._s = v; this.el.stat.textContent = v; } const mt = meter((Math.floor(now / 380) % 5) + 1, 5); if (mt !== this.el.meter._s) { this.el.meter._s = mt; this.el.meter.textContent = mt; } }
  frame(now) {
    this.fit(); if (!this.w) return; const { cols, rows, w: W, h: H } = this, cw = W / cols, ch = H / rows, c = this.ctx, t = (now - this.t0) / 1000;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0); c.fillStyle = "#040405"; c.fillRect(0, 0, W, H); c.font = `700 ${Math.round(ch * .92)}px "JetBrains Mono","DejaVu Sans Mono",monospace`; c.textAlign = "center"; c.textBaseline = "middle";
    const put = (ch_, x, y, col, a) => { if (x < 0 || y < 0 || x >= cols || y >= rows) return; c.globalAlpha = a; c.fillStyle = col; c.fillText(ch_, (x + .5) * cw, (y + .55) * ch); };
    const h3 = (a, b, k) => { let v = Math.imul(a * 73856093 ^ b * 19349663 ^ k * 83492791, 2654435761) >>> 0; return v / 4294967296; };
    if (this.pack.id === "ms") this.launch(t, put, h3, cols, rows); else this.print(t, put, h3, cols, rows);
    c.globalAlpha = 1;
  }
  print(t, put, h3, cols, rows) {                                                       // First Print: the sheet is printed line by line, holds, then runs again
    if (!this.mask) this.mask = this.logo(); const m = this.mask, CYC = 5.2, u = (t % CYC) / CYC, head = u < .55 ? u / .55 * (rows + 2) - 1 : rows + 9, fade = u > .86 ? (u - .86) / .14 : 0, run = Math.floor(t / CYC);
    this.status(t * 1000, u < .55 ? "printing" : "printed");
    for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
      const k = y * cols + x, v = m[k], r = h3(x, y, run);
      if (y > head) { if (r < .05) put(".:"[r < .025 ? 0 : 1], x, y, "#8d897f", .25); continue; }                    // paper not printed yet
      if (Math.abs(y - head) < 1) { put("=#@%"[Math.floor(r * 4)], x, y, "#ffffff", .95); continue; }                // the print head
      if (v > .35) { const ink = v > .7 ? "@" : v > .5 ? "#" : "%", wob = Math.max(0, 1 - (head - y) / 6); put(fade && r < fade ? "." : ink, x, y, wob > 0 ? "#ffffff" : "#ece7dc", fade ? 1 - fade * .8 : .9 + .1 * wob); }
      else if (r < .035) put("·", x, y, "#5b5953", .5);
    }
    const st = Math.floor(t * 1.5); for (let k = 0; k < 6; k++) { const x = Math.floor(h3(k, st, 7) * cols), y = Math.floor(h3(k, st, 9) * rows); put("+", x, y, "#ece7dc", .3); }   // a few specks of ink in the air
  }
  launch(t, put, h3, cols, rows) {                                                      // Moonshot: a rocket climbs through the stars, the Moon in the corner
    this.status(t * 1000, "launching");
    for (const [n, sp, chs, col, a] of [[cols * rows * .035, 3, ".", "#8d897f", .55], [cols * rows * .012, 8, "·*", "#ece7dc", .85]]) for (let k = 0; k < n; k++) { const x = Math.floor(h3(k, 1, sp) * cols), y = Math.floor((h3(k, 2, sp) * rows + t * sp) % rows); put(chs[k % chs.length], x, y, col, a); }
    const mx = cols - 7, my = 3, R = Math.max(2, Math.round(cols / 14)); for (let y = -R; y <= R; y++) for (let x = -R * 2; x <= R * 2; x++) { const d = Math.hypot(x / 2, y) / R; if (d <= 1) put(d > .8 ? "o" : (h3(x, y, 3) < .2 ? "o" : "@"), mx + x, my + y, "#b8d4ff", d > .8 ? .55 : .8); }
    const cx = Math.floor(cols / 2), bob = Math.round(Math.sin(t * 2.2) * .8), top = Math.floor(rows * .16) + bob;
    const ship = ["    /\\    ", "   /  \\   ", "  /    \\  ", "  |    |  ", "  | () |  ", "  |    |  ", "  |    |  ", "  |    |  ", " /|    |\\ ", "/_|____|_\\", "   /__\\   "]; ship.forEach((row, i) => [...row].forEach((chr, j) => { if (chr !== " ") put(chr, cx - 5 + j, top + i, i < 3 ? "#ffffff" : "#ece7dc", 1); }));
    const fy = top + ship.length; for (let i = 0; i < 12; i++) for (let j = -3; j <= 3; j++) { const r = h3(j + 9, i, Math.floor(t * 14)), wdt = 3.4 - i * .25; if (Math.abs(j) > wdt || r > 1 - i * .09) continue; put("^*'\",."[Math.min(5, (i / 2 | 0) + (r * 2 | 0))], cx + j, fy + i, i < 2 ? "#ffffff" : i < 6 ? "#ffd27a" : "#ff8a5c", 1 - i * .07); }
    for (let k = 0; k < 14; k++) { const age = (t * .9 + h3(k, 5, 1)) % 1, x = cx + Math.round((h3(k, 6, 1) - .5) * 20 * age), y = fy + 12 + Math.round(age * Math.max(1, rows - fy - 12)); put(age < .5 ? "O" : "o", x, y, "#8d897f", .5 * (1 - age)); }
  }
  start() { if (this.on) return; this.on = true; const loop = now => { if (!this.on) return; if (!this.pk.isConnected) { this.on = false; return; } if (!document.hidden && now - this.last > 42 && this.pk.offsetParent) { this.last = now; this.frame(now); } requestAnimationFrame(loop); }; requestAnimationFrame(loop); }
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
    const idle = .13 + this.tier * .045;
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
