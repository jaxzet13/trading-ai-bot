/* ---- the pack screen: the picture inside the pack. Every card goes through the same three beats so you always know what you are
        looking at: DECODING (noise settles into the picture) -> DECODED (hold, with its name and character count) -> NEXT (it glitches out) ---- */
const PACKPICS = new Map(), SPIN = "|/-\\";
async function packPic(card) {
  const src = imgOf(card, "");
  if (PACKPICS.has(src)) return PACKPICS.get(src);
  const img = await loadImg(src); if (!img) return null;
  const cols = 80, rows = Math.round(cols * img.height / img.width / 1.73), c = document.createElement("canvas"); c.width = cols; c.height = rows;
  const x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(img, 0, 0, cols, rows);
  let d; try { d = x.getImageData(0, 0, cols, rows).data; } catch (e) { return null; }
  const n = cols * rows, L = new Float32Array(n), t = new Float32Array(n), bl = new Float32Array(n), col = new Uint8Array(n * 3), R = 3;
  for (let i = 0; i < n; i++) { const r = d[i * 4], g = d[i * 4 + 1], b = d[i * 4 + 2], m = Math.max(r, g, b, 1); L[i] = (r * .3 + g * .59 + b * .11) / 255; col[i * 3] = r / m * 255; col[i * 3 + 1] = g / m * 255; col[i * 3 + 2] = b / m * 255; }
  const S = Array.from(L).sort((a, b) => a - b), look = PACKLOOK[card.id] || {}, lo = S[Math.floor(S.length * (look.lo || .1))], hi = Math.max(lo + .2, S[Math.floor(S.length * (look.hi || .985))]);
  for (let y = 0; y < rows; y++) for (let xx = 0; xx < cols; xx++) { let a = 0, k = 0; for (let j = -R; j <= R; j++) for (let i = -R; i <= R; i++) { const yy = y + j, x2 = xx + i; if (yy >= 0 && yy < rows && x2 >= 0 && x2 < cols) { a += L[yy * cols + x2]; k++; } } bl[y * cols + xx] = a / k; }
  for (let i = 0; i < n; i++) t[i] = Math.pow(clamp((L[i] - lo) / (hi - lo) * (look.base || .85) + (L[i] - bl[i]) * (look.local || 2.2), 0, 1), look.gamma || 1.15);
  const r = { cols, rows, t, col }; PACKPICS.set(src, r); return r;
}
const PACKLOOK = {   // per-card tone tweaks for the pack screen: lo/hi = black and white points, base = overall level, local = edge boost, gamma = contrast
  stitch: { base: 1.1, local: .5, gamma: .8, lo: .02 }, ronin: { base: .7, local: 3.4, gamma: 1.5 }, grimm: { base: .7, local: 3.2, gamma: 1.4 }, reaper: { base: .55, local: 3.6, gamma: 1.9 }
};
const PACK_ORDER = ["stitch", "umbra", "orbit", "brick", "null", "phantom", "rook", "shogun", "ronin", "grimm", "reaper"];
class PackScreen {
  constructor(pk) {
    this.pk = pk; this.cv = pk.querySelector("canvas.scr"); this.ctx = this.cv.getContext("2d"); this.el = { stat: pk.querySelector(".r-stat"), name: pk.querySelector(".r-name"), sub: pk.querySelector(".r-sub"), meter: pk.querySelector(".r-meter") };
    this.cards = PACK_ORDER.map(id => BY_ID[id]); this.i = -1; this.pic = null; this.on = false; this.last = 0; this.ph = -1; this.shift = null; this.shiftAt = 0; this.loading = false;
    this.IN = 1.0; this.HOLD = 2.6; this.OUT = .8;
  }
  fit() { const dpr = Math.min(devicePixelRatio || 1, 2), w = this.cv.clientWidth, h = this.cv.clientHeight; if (w && this.cv.width !== Math.round(w * dpr)) { this.cv.width = Math.round(w * dpr); this.cv.height = Math.round(h * dpr); } this.w = w; this.h = h; this.dpr = dpr; }
  async advance() {
    if (this.loading) return; this.loading = true;
    const card = this.cards[(this.i + 1) % this.cards.length], pic = await packPic(card); this.loading = false; if (!pic) return;
    this.i = (this.i + 1) % this.cards.length; this.card = card; this.pic = pic; this.th = Float32Array.from({ length: pic.cols * pic.rows }, (_, k) => .62 * Math.floor(k / pic.cols) / pic.rows + .38 * Math.random());
    this.shift = new Float32Array(pic.rows); this.t0 = performance.now(); this.ph = -1;
    scramble(this.el.name, card.name.toUpperCase(), 520); this.el.sub.textContent = `${RAR[card.rar].name} · ${fmt(card.chars)} characters`; this.el.meter.textContent = meter(this.i + 1, this.cards.length);
  }
  status(ph, now) { const s = ph === 1 ? "decoded" : (ph === 0 ? "decoding " : "next card ") + SPIN[Math.floor(now / 110) % 4]; if (s !== this.el.stat._s) { this.el.stat._s = s; this.el.stat.textContent = "> " + s; } }
  frame(now) {
    const pic = this.pic; if (!pic) return; this.fit(); if (!this.w) return;
    const { cols, rows } = pic, W = this.w, H = this.h, cw = W / cols, ch = H / rows, c = this.ctx, t = (now - this.t0) / 1000;
    const ph = reduced ? 1 : t < this.IN ? 0 : t < this.IN + this.HOLD ? 1 : 2, p = ph === 0 ? t / this.IN : ph === 2 ? (t - this.IN - this.HOLD) / this.OUT : 0;
    this.status(ph, now);
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0); c.fillStyle = "#040405"; c.fillRect(0, 0, W, H); c.font = `700 ${Math.round(ch * .96)}px "JetBrains Mono","DejaVu Sans Mono",monospace`; c.textAlign = "center"; c.textBaseline = "middle";
    if (ph === 2 && now - this.shiftAt > 80) { this.shiftAt = now; for (let y = 0; y < rows; y++) this.shift[y] = Math.random() < p * .7 ? Math.round((Math.random() * 2 - 1) * (1 + p * 9)) : 0; }
    const scan = (t * 11) % (rows + 12) - 6, tint = this.card.tint;
    for (let y = 0; y < rows; y++) {
      const sh = ph === 2 ? this.shift[y] : 0;
      for (let x = 0; x < cols; x++) {
        const i = y * cols + x; let v = pic.t[i], mode = 0;
        if (ph === 0) { const th = this.th[i]; if (p < th) mode = 1; else if (p < th + .1) mode = 2; }
        else if (ph === 2 && Math.random() < p * p * 1.1) mode = 1;
        if (mode === 0 && v < .04) continue;
        let chr, fs;
        if (mode === 1) { chr = NOISE[(Math.random() * 13) | 0]; c.globalAlpha = .22 + Math.random() * .25; fs = tint; }
        else if (mode === 2) { chr = "@"; c.globalAlpha = 1; fs = "#fff"; }
        else {
          v += .05 * Math.sin(now / 420 + x * .31 + y * .23); const dd = Math.abs(y - scan); if (ph === 1 && dd < 2.2) v += .3 * (1 - dd / 2.2);
          v = clamp(v, 0, 1); chr = RAMP[Math.min(9, Math.round(v * 9))]; if (chr === " ") continue; const k = .5 + .5 * v;
          c.globalAlpha = 1; fs = `rgb(${pic.col[i * 3] * k | 0},${pic.col[i * 3 + 1] * k | 0},${pic.col[i * 3 + 2] * k | 0})`;
        }
        c.fillStyle = fs; c.fillText(chr, (x + .5 + sh) * cw, (y + .55) * ch);
      }
    }
    c.globalAlpha = 1;
    if (now - this.t0 > (this.IN + this.HOLD + this.OUT) * 1000 && !reduced) this.advance();
  }
  start() { if (this.on) return; this.on = true; this.advance(); const loop = now => { if (!this.on) return; if (!this.pk.isConnected) { this.on = false; return; } if (!document.hidden && now - this.last > 42 && this.pk.offsetParent) { this.last = now; this.frame(now); } requestAnimationFrame(loop); }; requestAnimationFrame(loop); }
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
