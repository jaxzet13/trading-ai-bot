/* ============================================================================
   6c. GLYPH CARDS. A few rare cards are not a picture that is moved about: they are a little scene, drawn from shapes, that lives as text.
   Each scene (GlyphScenes) draws itself at any moment t on a black ground, in 100 units across: a butterfly beating its wings, a heart that beats, a bouquet swaying,
   a candle that flickers, a phoenix. The scene is read back as a grid and every cell becomes the character whose ink matches it, in its own colour.
   When the card is turned over, the characters do not print in: they arrive. Every one of them flies in from a scatter of dust, a few at a time from the middle out,
   and locks into place; then the scene keeps living for as long as the card is on show.
   The scenes are plain functions of (g, t, W, H), so the same file draws the card's still picture (design-concepts/glyph/stills.js) and its animation.
   ========================================================================== */
const GlyphScenes = (() => {
  const TAU = Math.PI * 2, hs = (a, b) => { let h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  const glow = (g, x, y, r, rgb, a) => { const k = g.createRadialGradient(x, y, 0, x, y, r); k.addColorStop(0, `rgba(${rgb},${a})`); k.addColorStop(1, `rgba(${rgb},0)`); g.fillStyle = k; g.fillRect(x - r, y - r, r * 2, r * 2); };
  const bez = (p0, p1, p2, p3, t) => { const u = 1 - t; return [u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0], u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]]; };
  const star = (g, x, y, r, a) => { g.strokeStyle = `rgba(255,255,255,${a})`; g.lineWidth = .35; g.beginPath(); g.moveTo(x - r, y); g.lineTo(x + r, y); g.moveTo(x, y - r); g.lineTo(x, y + r); g.stroke(); g.fillStyle = `rgba(255,255,255,${a})`; g.beginPath(); g.arc(x, y, r * .22, 0, TAU); g.fill(); };
  const sparkles = (g, t, n, rgb, y0, y1) => { for (let k = 0; k < n; k++) { const x = 6 + hs(k, 1) * 88, y = y0 + hs(k, 2) * (y1 - y0), a = Math.max(0, Math.sin(t * (1.4 + hs(k, 3) * 2.4) + hs(k, 4) * 6)); if (a > .55) star(g, x, y, .8 + hs(k, 5) * 1.6, a * .8); } void rgb; };

  /* ---------- Morpho: a blue butterfly that beats its wings ---------- */
  function morpho(g, t) {
    glow(g, 50, 58, 56, "50,150,255", .14 + .05 * Math.sin(t * 2.4));
    const flap = t * 2.9, open = .2 + .8 * (.5 + .5 * Math.cos(flap)), bob = Math.sin(t * 1.3) * 1.8, tilt = Math.sin(t * .8) * .035;
    g.save(); g.translate(50, 60 + bob); g.rotate(tilt); g.translate(-50, -60);
    const fore = "M52,56 C60,40 78,14 97,13 C99,30 98,46 90,54 C80,60 64,62 54,62 Z", hind = "M54,61 C70,56 88,58 90,70 C90,84 76,96 64,86 C58,80 55,72 53,68 Z";
    for (const s of [-1, 1]) {
      g.save(); g.translate(50, 0); g.scale(s * open, 1 + (1 - open) * .06); g.translate(-50, 0);
      for (const d of [hind, fore]) {
        const p = new Path2D(d), gr = g.createRadialGradient(54, 58, 2, 60, 52, 52); gr.addColorStop(0, "#d8f8ff"); gr.addColorStop(.2, "#4fd0ff"); gr.addColorStop(.55, "#1568ff"); gr.addColorStop(1, "#0b2b9c"); g.fillStyle = gr; g.fill(p); g.strokeStyle = "#020a22"; g.lineWidth = 1.5; g.lineJoin = "round"; g.stroke(p);
      }
      g.strokeStyle = "rgba(4,16,70,.55)"; g.lineWidth = .5; for (let k = 0; k <= 7; k++) { const q = bez([97, 13], [99, 30], [98, 46], [90, 54], k / 7); g.beginPath(); g.moveTo(54, 59); g.lineTo(q[0], q[1]); g.stroke(); }
      for (let k = 0; k <= 5; k++) { const q = bez([90, 70], [90, 84], [76, 96], [64, 86], k / 5); g.beginPath(); g.moveTo(54, 62); g.lineTo(q[0], q[1]); g.stroke(); }
      g.fillStyle = "rgba(235,250,255,.95)"; for (let k = 0; k < 15; k++) { const q = bez([97, 13], [99, 30], [98, 46], [90, 54], k / 14); g.beginPath(); g.arc(q[0] - 1.6, q[1] + .4, .55, 0, TAU); g.fill(); } for (let k = 0; k < 11; k++) { const q = bez([90, 70], [90, 84], [76, 96], [64, 86], k / 10); g.beginPath(); g.arc(q[0] - 1.2, q[1] - .8, .5, 0, TAU); g.fill(); }
      g.restore();
    }
    g.fillStyle = "#1a0f08"; g.beginPath(); g.ellipse(50, 63, 2.1, 13, 0, 0, TAU); g.fill(); g.fillStyle = "#3a2410"; g.beginPath(); g.arc(50, 49, 3.1, 0, TAU); g.fill(); g.beginPath(); g.arc(50, 44.5, 2, 0, TAU); g.fill();
    g.strokeStyle = "#e0b060"; g.lineWidth = .5; g.beginPath(); g.moveTo(49.4, 43); g.quadraticCurveTo(44, 34, 38, 33); g.moveTo(50.6, 43); g.quadraticCurveTo(56, 34, 62, 33); g.stroke(); g.restore();
    sparkles(g, t, 26, "160,220,255", 6, 112);
  }

  /* ---------- Heartword: a heart made of words, beating ---------- */
  const WORDS = ["stixx", "pulled it", "rare", "mint", "yours", "text", "hold", "glow", "one of one", "i love it"];
  function heartPath(g, cx, cy, k) { g.beginPath(); for (let i = 0; i <= 120; i++) { const a = i / 120 * TAU, x = 16 * Math.pow(Math.sin(a), 3), y = -(13 * Math.cos(a) - 5 * Math.cos(2 * a) - 2 * Math.cos(3 * a) - Math.cos(4 * a)); if (i) g.lineTo(cx + x * k, cy + y * k); else g.moveTo(cx + x * k, cy + y * k); } g.closePath(); }
  function heartword(g, t) {
    const ph = (t % 1.25) / 1.25, beat = Math.exp(-Math.pow((ph - .08) / .05, 2)) + .7 * Math.exp(-Math.pow((ph - .27) / .06, 2)), s = 1 + .08 * beat, k = 2.85 * s;
    glow(g, 50, 58, 66, "255,40,90", .22 + .14 * beat);
    heartPath(g, 50, 60, k); const gr = g.createLinearGradient(20, 20, 80, 100); gr.addColorStop(0, "#ff7a9c"); gr.addColorStop(.5, "#e0204f"); gr.addColorStop(1, "#8c0a2c"); g.fillStyle = gr; g.fill();
    g.save(); heartPath(g, 50, 60, k); g.clip(); g.textAlign = "center"; g.textBaseline = "middle";
    for (let i = 0; i < 190; i++) { const x = 6 + hs(i, 1) * 88, y = 12 + hs(i, 2) * 90, ang = hs(i, 3) * TAU + Math.sin(t * .6 + i) * .15, w = WORDS[(hs(i, 4) * WORDS.length) | 0], a = .55 + .4 * hs(i, 5); g.save(); g.translate(x, y); g.rotate(ang); g.font = `700 ${2.6 + hs(i, 6) * 1.8}px Georgia, serif`; g.fillStyle = `rgba(255,${230 + (hs(i, 7) * 25) | 0},${235},${a})`; g.fillText(w, 0, 0); g.restore(); }
    g.restore(); heartPath(g, 50, 60, k); g.strokeStyle = "rgba(255,190,205,.8)"; g.lineWidth = .8; g.stroke();
    g.font = `700 ${7.5 + beat * 1.2}px Georgia, serif`; g.textAlign = "center"; g.textBaseline = "middle"; g.shadowColor = "rgba(255,255,255,.9)"; g.shadowBlur = 5; g.fillStyle = "#fff"; g.fillText("stixx", 50, 56); g.shadowBlur = 0;
    sparkles(g, t, 20, "255,180,200", 6, 112);
  }

  /* ---------- Bouquet: flowers that sway ---------- */
  const FLOWERS = [[50, 24, 10.5, "#ff4a68", 8], [31, 33, 9.5, "#ffd23f", 9], [69, 33, 9.5, "#ffa83a", 8], [20, 52, 8.5, "#b078ff", 7], [80, 52, 8.5, "#ff7ad0", 7], [41, 47, 9.5, "#ffffff", 8], [60, 48, 10, "#ff3040", 8], [50, 66, 8.5, "#ffd23f", 8], [30, 66, 7, "#7ad0ff", 7], [70, 66, 7, "#ff9a3b", 7]];
  function bouquet(g, t) {
    glow(g, 50, 56, 60, "255,120,200", .07); const sw = Math.sin(t * 1.15) * .04;
    g.save(); g.translate(50, 112); g.rotate(sw); g.translate(-50, -112);
    g.strokeStyle = "#1f7a38"; g.lineWidth = 1.5; g.lineCap = "round"; for (const f of FLOWERS) { g.beginPath(); g.moveTo(50, 110); g.quadraticCurveTo((50 + f[0]) / 2, (110 + f[1]) / 2 + 6, f[0], f[1]); g.stroke(); }
    for (let i = 0; i < 12; i++) { const a = -2.6 + i * .44, x = 50 + Math.cos(a) * 30, y = 74 + Math.sin(a) * 36 * .6; g.save(); g.translate(x, y); g.rotate(a + 1.5 + Math.sin(t * 1.5 + i) * .08); g.fillStyle = i % 2 ? "#2fbf5a" : "#1f9a46"; g.beginPath(); g.ellipse(0, 0, 3, 8.5, 0, 0, TAU); g.fill(); g.restore(); }
    FLOWERS.forEach((f, i) => { const [x, y, r, col, n] = f, pr = r * (1 + .06 * Math.sin(t * 2.1 + i * 1.3)); g.save(); g.translate(x, y); g.rotate(t * .25 * (i % 2 ? 1 : -1) + i); g.fillStyle = col; for (let p = 0; p < n; p++) { g.save(); g.rotate(p / n * TAU); g.beginPath(); g.ellipse(0, -pr * .58, pr * .3, pr * .5, 0, 0, TAU); g.fill(); g.strokeStyle = "rgba(0,0,0,.25)"; g.lineWidth = .35; g.stroke(); g.restore(); } g.fillStyle = col === "#ffffff" ? "#ffcf3a" : "#5a2a08"; g.beginPath(); g.arc(0, 0, pr * .26, 0, TAU); g.fill(); g.restore(); });
    const wr = g.createLinearGradient(20, 66, 80, 112); wr.addColorStop(0, "#ff8fb8"); wr.addColorStop(1, "#c4306a"); g.fillStyle = wr; g.beginPath(); g.moveTo(22, 70); g.quadraticCurveTo(50, 80, 78, 70); g.lineTo(53, 114); g.lineTo(47, 114); g.closePath(); g.fill(); g.strokeStyle = "rgba(255,255,255,.35)"; g.lineWidth = .5; g.beginPath(); g.moveTo(40, 76); g.lineTo(49, 112); g.moveTo(60, 76); g.lineTo(51, 112); g.stroke();
    g.fillStyle = "#fff2f8"; g.beginPath(); g.ellipse(41, 93, 8, 4, -.45, 0, TAU); g.ellipse(59, 93, 8, 4, .45, 0, TAU); g.fill(); g.fillStyle = "#ff4f8a"; g.beginPath(); g.arc(50, 94, 3, 0, TAU); g.fill(); g.restore();
    sparkles(g, t, 22, "255,230,200", 4, 110);
  }

  /* ---------- Last Candle: a flame that never sits still ---------- */
  function flame(g, tx, ty, sc, col) { g.fillStyle = col; g.beginPath(); g.moveTo(50, 56); g.bezierCurveTo(50 - 8 * sc, 54, 50 - 8 * sc, 46, 49 - 2 * sc, 41); g.bezierCurveTo(48.5, 36, tx - 1.2, ty + 7, tx, ty); g.bezierCurveTo(tx + 1.4, ty + 7, 52.5, 38, 52 + 2 * sc, 42); g.bezierCurveTo(50 + 8 * sc, 47, 50 + 8 * sc, 54, 50, 56); g.fill(); }
  function candle(g, t) {
    const fl = Math.sin(t * 9.1) * .5 + Math.sin(t * 14.3 + 1) * .35 + Math.sin(t * 5.7) * .4, sway = Math.sin(t * 4.7) * 1.4 + Math.sin(t * 7.9) * .8, H = 21 + fl * 2.6;
    glow(g, 50, 50, 64, "255,150,50", .2 + fl * .05); glow(g, 50, 48, 26, "255,210,120", .18 + fl * .04);
    const wx = g.createLinearGradient(37, 0, 63, 0); wx.addColorStop(0, "#8f6a38"); wx.addColorStop(.35, "#fff0cc"); wx.addColorStop(.7, "#e0bf86"); wx.addColorStop(1, "#7c5a30"); g.fillStyle = wx; g.beginPath(); g.moveTo(37, 66); g.lineTo(37, 106); g.quadraticCurveTo(50, 112, 63, 106); g.lineTo(63, 66); g.ellipse(50, 66, 13, 3.4, 0, 0, Math.PI, true); g.closePath(); g.fill();
    g.fillStyle = "#fff7df"; g.beginPath(); g.ellipse(50, 66, 13, 3.4, 0, 0, TAU); g.fill(); g.fillStyle = "#ffd890"; g.beginPath(); g.ellipse(50, 66, 8, 1.8, 0, 0, TAU); g.fill();
    g.fillStyle = "rgba(255,248,225,.9)"; for (const [x, h] of [[41, 16], [56, 22], [47, 9]]) { g.beginPath(); g.roundRect(x - 1.4, 66, 2.8, h, 1.4); g.fill(); g.beginPath(); g.arc(x, 66 + h, 1.7, 0, TAU); g.fill(); }
    g.fillStyle = "#3a2a10"; g.beginPath(); g.ellipse(50, 110, 24, 4.4, 0, 0, TAU); g.fill(); g.strokeStyle = "#d6a23a"; g.lineWidth = .9; g.stroke();
    g.strokeStyle = "#1a1008"; g.lineWidth = 1; g.lineCap = "round"; g.beginPath(); g.moveTo(50, 66); g.quadraticCurveTo(50.5, 60, 50 + sway * .2, 56); g.stroke();
    const tx = 50 + sway, ty = 55 - H; flame(g, tx, ty, 1.05, "rgba(255,110,20,.95)"); flame(g, tx, ty + H * .2, .78, "#ffb62e"); flame(g, tx, ty + H * .42, .5, "#fff3c4"); g.fillStyle = "rgba(70,130,255,.85)"; g.beginPath(); g.ellipse(50, 53.5, 2.2, 3.2, 0, 0, TAU); g.fill();
    for (let i = 0; i < 16; i++) { const u = ((t * (.35 + hs(i, 1) * .5) + hs(i, 2)) % 1), x = 50 + Math.sin(u * 6 + i) * (3 + u * 12) + sway, y = 52 - u * 46; g.fillStyle = `rgba(255,${150 + (hs(i, 3) * 90) | 0},60,${(1 - u) * .9})`; g.beginPath(); g.arc(x, y, .35 + hs(i, 4) * .6, 0, TAU); g.fill(); }
  }

  /* ---------- Phoenix: flame with wings ---------- */
  function feather(g, L, w, c0, c1, c2) { const gr = g.createLinearGradient(0, 0, L, 0); gr.addColorStop(0, c0); gr.addColorStop(.55, c1); gr.addColorStop(1, c2); g.fillStyle = gr; g.beginPath(); g.moveTo(0, 0); g.quadraticCurveTo(L * .45, -w, L, 0); g.quadraticCurveTo(L * .45, w * .75, 0, 0); g.fill(); g.strokeStyle = "rgba(60,0,0,.35)"; g.lineWidth = .4; g.stroke(); }
  function phoenix(g, t) {
    const fl = Math.sin(t * 2.3), up = .5 + .5 * fl; glow(g, 50, 56, 68, "255,80,20", .16 + up * .06); glow(g, 50, 52, 30, "255,200,80", .1);
    // tail: long wavy feathers
    for (let i = 0; i < 6; i++) { g.save(); g.translate(50 + (i - 2.5) * 2.2, 78); const sway = Math.sin(t * 2 + i * .7) * .12 + (i - 2.5) * .12; g.rotate(Math.PI / 2 + sway); feather(g, 40 - Math.abs(i - 2.5) * 3, 3.2, "#ff9a1f", "#ff4a1a", "#ffe066"); g.restore(); }
    // wings: eight feathers fanned out, beating
    for (const s of [-1, 1]) for (let i = 0; i < 9; i++) { g.save(); g.translate(50 + s * 5, 54); const base = (-1.15 + i * .2) + (fl * .32 - .1) * (1 - i * .05) - .25; g.scale(s, 1); g.rotate(base); feather(g, 46 - i * 2.3, 5 - i * .22, "#ffd24a", i < 4 ? "#ff7a1f" : "#ff4a1a", i < 5 ? "#d4162c" : "#8e0a22"); g.restore(); }
    const bd = g.createLinearGradient(0, 44, 0, 80); bd.addColorStop(0, "#ffe066"); bd.addColorStop(1, "#ff7a1f"); g.fillStyle = bd; g.beginPath(); g.ellipse(50, 62, 7.2, 15, 0, 0, TAU); g.fill();
    g.beginPath(); g.moveTo(46, 52); g.quadraticCurveTo(44, 42, 49, 36); g.lineTo(51, 36); g.quadraticCurveTo(56, 42, 54, 52); g.fill(); g.beginPath(); g.arc(50, 35, 5.4, 0, TAU); g.fill();
    g.fillStyle = "#ffb62e"; g.beginPath(); g.moveTo(53.5, 33.5); g.lineTo(61, 36); g.lineTo(53.5, 38); g.closePath(); g.fill(); g.fillStyle = "#2a0505"; g.beginPath(); g.arc(51.5, 34, 1, 0, TAU); g.fill();
    for (let i = 0; i < 3; i++) { g.save(); g.translate(48 + i * 2, 31); g.rotate(-.7 + i * .7 + Math.sin(t * 6 + i) * .1); feather(g, 9 - i, 1.5, "#ff6a1f", "#ffb62e", "#ffe066"); g.restore(); }
    for (let i = 0; i < 26; i++) { const u = ((t * (.3 + hs(i, 1) * .45) + hs(i, 2)) % 1), x = 50 + (hs(i, 3) - .5) * 70 + Math.sin(u * 7 + i) * 4, y = 96 - u * 92; g.fillStyle = `rgba(255,${130 + (hs(i, 4) * 110) | 0},40,${(1 - u) * .95})`; g.beginPath(); g.arc(x, y, .4 + hs(i, 5) * .8, 0, TAU); g.fill(); }
  }
  // the moment each one looks best as a still picture
  const STILL = { morpho: .97, heartword: .09, bouquet: 0, candle: 1.1, phoenix: .72 };
  return { morpho, heartword, bouquet, candle, phoenix, STILL };
})();

/* ---- the player: reads a scene as cells, and flies the characters in ---- */
const Glyph = (() => {
  const RAMP = " .'`:;il1tfrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$", N = RAMP.length - 1, all = new Set(), by = new WeakMap(); let raf = 0;
  const hh = (a, b, c) => { let h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263) ^ Math.imul((c || 0) | 0, 2147483647); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  const clamp = (x, a = 0, b = 1) => x < a ? a : x > b ? b : x, eo = x => 1 - Math.pow(1 - clamp(x), 3), back = x => { x = clamp(x); const c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
  class One {
    constructor(card, id, opts) {
      opts = opts || {}; this.card = card; this.id = id; this.scene = GlyphScenes[id]; this.pic = card.querySelector(".pic"); this.cv = document.createElement("canvas"); this.cv.className = "alive"; this.cv.setAttribute("aria-hidden", "true");
      this.t0 = performance.now(); this.asm = opts.assemble ? performance.now() : 0; this.dur = opts.dur || 2800; this.onTick = opts.onTick || null; this.onDone = opts.onDone || null; this.tk = -1; this.ok = false; this.w = 0; this.seed = id.charCodeAt(0) * 31 + id.length; this.prep();
    }
    prep() {
      const pic = this.pic; if (!pic) return; const w = pic.clientWidth, h = pic.clientHeight; if (!w || !h) return; const d = Math.min(devicePixelRatio || 1, 2); this.w = w; this.h = h; this.d = d;
      this.cv.width = Math.round(w * d); this.cv.height = Math.round(h * d); this.g = this.cv.getContext("2d");
      this.cw = Math.max(2.4, w / 74); this.cols = Math.round(w / this.cw); this.ch = this.cw * 1.7; this.rows = Math.round(h / this.ch);
      this.sc = document.createElement("canvas"); this.sc.width = this.cols * 4; this.sc.height = this.rows * 4; this.sg = this.sc.getContext("2d"); this.sm = document.createElement("canvas"); this.sm.width = this.cols; this.sm.height = this.rows; this.smg = this.sm.getContext("2d", { willReadFrequently: true });
      this.pic.appendChild(this.cv); requestAnimationFrame(() => this.cv.classList.add("on")); this.ok = true; this.frame(performance.now());
    }
    frame(now) {
      if (!this.ok) return; if (this.pic.clientWidth !== this.w) { this.ok = false; this.cv.remove(); this.prep(); return; }
      const t = (now - this.t0) / 1000, { cols, rows, g, sg, smg } = this, W = 100, H = 100 * this.sc.height / this.sc.width;
      sg.setTransform(1, 0, 0, 1, 0, 0); sg.fillStyle = "#030304"; sg.fillRect(0, 0, this.sc.width, this.sc.height); sg.setTransform(this.sc.width / W, 0, 0, this.sc.width / W, 0, 0); this.scene(sg, t + 1.2, W, H);
      smg.imageSmoothingEnabled = true; smg.drawImage(this.sc, 0, 0, cols, rows); const px = smg.getImageData(0, 0, cols, rows).data;
      const p = this.asm ? clamp((now - this.asm) / this.dur) : 1, cw = this.cw, ch = this.ch; g.setTransform(this.d, 0, 0, this.d, 0, 0); g.fillStyle = "#030304"; g.fillRect(0, 0, this.w, this.h);
      g.font = `700 ${(cw / .6).toFixed(2)}px "JetBrains Mono","DejaVu Sans Mono",ui-monospace,monospace`; g.textAlign = "center"; g.textBaseline = "middle";
      const cx = cols / 2, cy = rows / 2, fr = Math.floor(now / 70); let landed = 0, total = 0;
      for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
        const k = (y * cols + x) * 4, r = px[k], gg = px[k + 1], b = px[k + 2], l = (r * .299 + gg * .587 + b * .114) / 255; if (l < .1) continue; total++;
        let ox = (x + .5) * cw, oy = (y + .55) * ch, a = 1, glyphI = Math.min(N, Math.round(Math.pow(l, .75) * N)), boost = Math.min(1, .72 + l * .6), flash = 0;
        if (p < 1) {
          // each character waits its turn (the middle first), then flies in from a scatter of dust and lands with a small overshoot
          const dist = Math.hypot((x - cx) / cx, (y - cy) / cy), delay = dist * .3 + hh(x, y, this.seed) * .2, u = clamp((p - delay) / .5);
          if (u <= 0) continue; const e = back(u), s = 1 - e, ang = hh(x, y, this.seed + 1) * 6.283 + (1 - u) * 5.5, R = (40 + hh(x, y, this.seed + 2) * 190) * s;
          ox += Math.cos(ang) * R; oy += Math.sin(ang) * R * .8 - s * s * 30; a = clamp(u * 2.2);
          if (u < .85) glyphI = (glyphI + 3 + ((hh(x, y, fr) * 14) | 0)) % (N + 1) || 1; if (u < 1) flash = (1 - u) * .8; if (u >= 1) landed++;
        } else landed++;
        const m = Math.max(r, gg, b) || 1, kk = boost * 255 / m, cr = Math.min(255, r * kk + flash * 255), cg = Math.min(255, gg * kk + flash * 255), cb = Math.min(255, b * kk + flash * 255);
        g.globalAlpha = a; g.fillStyle = `rgb(${cr | 0},${cg | 0},${cb | 0})`; g.fillText(RAMP[glyphI], ox, oy);
      }
      g.globalAlpha = 1;
      if (this.asm && this.onTick) { const kk = Math.floor(p * 16); if (kk !== this.tk) { this.tk = kk; this.onTick(kk); } }
      if (this.asm && p >= 1) { this.asm = 0; if (this.onDone) { const f = this.onDone; this.onDone = null; f(); } }
      void landed; void total;
    }
    drop() { this.ok = false; this.cv.remove(); if (this.onDone) { const f = this.onDone; this.onDone = null; f(); } }
  }
  function loop(now) {
    raf = 0; if (!all.size) return;
    for (const o of [...all]) { if (!o.card.isConnected) { all.delete(o); by.delete(o.card); o.drop(); continue; } if (!document.hidden && o.card.offsetParent !== null) o.frame(now); }
    if (all.size) raf = requestAnimationFrame(loop);
  }
  const has = id => !!GlyphScenes[id] && id !== "STILL";
  // a card's scene, living (called again and again for the same card: it only starts once)
  function on(card, copy) {
    if (!card || !copy) return; const id = BY_NO[copy.no].id; if (!has(id)) return; let o = by.get(card); if (o) return o;
    o = new One(card, id, {}); by.set(card, o); all.add(o); if (!raf) raf = requestAnimationFrame(loop); return o;
  }
  // the card turns over and its characters arrive: resolves when the last one has landed
  function assemble(card, copy, opts) {
    const id = BY_NO[copy.no].id; return new Promise(res => {
      let o = by.get(card); if (o) { all.delete(o); by.delete(card); o.drop(); }
      o = new One(card, id, { assemble: true, dur: (opts && opts.dur) || 2800, onTick: opts && opts.onTick, onDone: res }); by.set(card, o); all.add(o); if (!raf) raf = requestAnimationFrame(loop);
      setTimeout(res, ((opts && opts.dur) || 2800) + 600);
    });
  }
  return { has, on, assemble };
})();
