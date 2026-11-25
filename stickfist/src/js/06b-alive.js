/* ============================================================================
   6b. ALIVE. A good card's picture does not sit still.
   On a rare card or better, the picture in the card keeps moving while you look at it, the way a living ASCII piece does:
     - it has depth: the lit parts of the picture ride a little in front of the dark parts, and the two sway slowly, so the
       picture seems to turn in the light;
     - its characters shimmer: here and there a character flares and changes, and a soft band of light crosses it;
     - bits of it lift off: characters the colour of the picture drift away on a wind and fade;
     - and on a legendary or better, every so often a gust crosses the card: the picture is blown off into characters along
       the gust's front and forms again behind it.
   How much of this a card gets follows its rarity. It runs only on a card shown large (the one you have just turned over, and
   the card window), never on lists, and not at all with reduced motion. The picture itself is untouched underneath: this is a
   canvas laid over it, drawn from it.
   ========================================================================== */
const Alive = (() => {
  const all = new Set(), by = new WeakMap(); let raf = 0, tick = 0;
  const hash = (a, b) => { let h = Math.imul(a ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(b + 0x6a09e667, 0xc2b2ae35); h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d); h ^= h >>> 12; return (h >>> 0) / 4294967296; };
  // by tier: how far it sways (px), characters lifting off a second, shimmer, and seconds between gusts (0 = none)
  const K = [null, null, { a: 1.4, emit: 3, sh: .012, gust: 0 }, { a: 1.9, emit: 6, sh: .018, gust: 0 }, { a: 2.5, emit: 10, sh: .024, gust: 13 }, { a: 3, emit: 14, sh: .03, gust: 11 }, { a: 3.4, emit: 18, sh: .036, gust: 9 }];
  class One {
    constructor(card, tier) {
      this.card = card; this.pic = card.querySelector(".pic"); this.img = this.pic && this.pic.querySelector("img"); this.k = K[Math.min(6, tier)]; this.cv = document.createElement("canvas"); this.cv.className = "alive"; this.cv.setAttribute("aria-hidden", "true");
      this.ctx = this.cv.getContext("2d"); this.t0 = performance.now(); this.last = this.t0; this.parts = []; this.ok = false; this.w = 0; this.gust = null; this.nextGust = this.k.gust ? 2.5 + Math.random() * 3 : 1e9; this.acc = 0; this.prep();
    }
    async prep() {
      const pic = this.pic, img = this.img; if (!pic || !img) return; try { if (!img.complete || !img.naturalWidth) await img.decode(); } catch (e) { return; }
      const w = pic.clientWidth, h = pic.clientHeight; if (!w || !h || !img.naturalWidth) return; const d = Math.min(devicePixelRatio || 1, 2), W = Math.round(w * d), H = Math.round(h * d);
      try {
        const base = document.createElement("canvas"); base.width = W; base.height = H; const bx = base.getContext("2d"), iw = img.naturalWidth, ih = img.naturalHeight, s = Math.max(w / iw, h / ih), sw = w / s, sh = h / s; bx.drawImage(img, (iw - sw) / 2, (ih - sh) / 2, sw, sh, 0, 0, W, H);
        // the lit parts on a layer of their own: how bright a point is decides how much of it rides in front
        const fg = document.createElement("canvas"); fg.width = W; fg.height = H; const fx = fg.getContext("2d"), px = bx.getImageData(0, 0, W, H), p = px.data;
        for (let i = 0; i < p.length; i += 4) { const l = (p[i] * .299 + p[i + 1] * .587 + p[i + 2] * .114) / 255, a = Math.max(0, Math.min(1, (l - .2) / .42)); p[i + 3] = a * a * (3 - 2 * a) * 255; } fx.putImageData(px, 0, 0);
        // the picture as a grid of cells: each one's colour, how bright it is, and the character that stands for it
        const cols = 46, cw = w / cols, ch = cw * 1.7, rows = Math.ceil(h / ch), sm = document.createElement("canvas"); sm.width = cols; sm.height = rows; const sx = sm.getContext("2d", { willReadFrequently: true }); sx.drawImage(base, 0, 0, W, Math.min(H, rows * ch * d), 0, 0, cols, rows);
        const g = sx.getImageData(0, 0, cols, rows).data, N = cols * rows, lum = new Float32Array(N), col = new Array(N), chr = new Array(N), lit = [];
        for (let i = 0; i < N; i++) { const R = g[i * 4], G = g[i * 4 + 1], B = g[i * 4 + 2], m = Math.max(R, G, B, 1), l = m / 255, q = (.62 + .38 * l) * 255 / m; lum[i] = l; col[i] = `rgb(${Math.min(255, R * q) | 0},${Math.min(255, G * q) | 0},${Math.min(255, B * q) | 0})`; chr[i] = RV_RAMP[Math.min(RV_RAMP.length - 1, (Math.pow(l, .8) * RV_RAMP.length) | 0)]; if (l > .38) lit.push(i); }
        Object.assign(this, { w, h, d, base, fg, cols, rows, cw, ch, N, lum, col, chr, lit, blown: new Float32Array(N).fill(-1) }); this.cv.width = W; this.cv.height = H; this.ok = lit.length > 12; if (this.ok) { this.mount(); requestAnimationFrame(() => this.cv.classList.add("on")); }
      } catch (e) { this.ok = false; }
    }
    mount() { if (this.pic && this.cv.parentNode !== this.pic) this.pic.appendChild(this.cv); }
    emit(i, fast) { const x = (i % this.cols + .5) * this.cw, y = ((i / this.cols | 0) + .5) * this.ch, r = Math.random; this.parts.push({ x, y, vx: fast ? 70 + r() * 110 : 10 + r() * 24, vy: fast ? -30 + r() * 50 : -(5 + r() * 14), life: 0, max: fast ? .55 + r() * .6 : 1.5 + r() * 1.8, ch: this.chr[i], col: this.col[i], ph: r() * 6.28, s: fast ? 1 : .85 + r() * .5 }); }
    frame(now) {
      if (!this.ok) return; if (this.pic.clientWidth !== this.w) { this.ok = false; this.cv.classList.remove("on"); this.prep(); return; }
      const c = this.ctx, { w, h, d, k, cols, rows, cw, ch } = this, t = (now - this.t0) / 1000, dt = Math.min(.1, (now - this.last) / 1000); this.last = now;
      const dx = Math.sin(t * .55) * k.a, dy = Math.cos(t * .41) * k.a * .6, pad = k.a + 2;
      c.setTransform(d, 0, 0, d, 0, 0); c.globalCompositeOperation = "source-over"; c.globalAlpha = 1; c.fillStyle = "#020203"; c.fillRect(0, 0, w, h);
      c.globalAlpha = 1; c.drawImage(this.base, -pad - dx * .6, -pad - dy * .6, w + pad * 2, h + pad * 2);                                    // the back of the picture leans one way
      c.globalAlpha = 1; c.drawImage(this.fg, -pad - 1.5 + dx, -pad - 1.5 + dy, w + pad * 2 + 3, h + pad * 2 + 3);                              // its lit parts the other, a touch larger: nearer
      // a gust: the picture comes away along its front and forms again behind it
      if (!this.gust && t > this.nextGust) { this.gust = { t0: t, dur: 2.3, id: t }; }
      if (this.gust) { const G = this.gust, p = (t - G.t0) / G.dur; if (p >= 1) { this.gust = null; this.nextGust = t + k.gust * (.7 + Math.random() * .6); } else {
          const front = -.15 + p * 1.6, TR = .3; c.fillStyle = "#020203";
          for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) { const i = y * cols + x, u = x / cols + y / rows * .22 + (hash(i, 7) - .5) * .05, back = front - u; if (back < 0 || back > TR) continue; if (this.lum[i] < .1) continue;
            const e = 1 - back / TR; c.globalAlpha = Math.min(1, e * 1.25); c.fillRect(x * cw - .4 + dx, y * ch - .4 + dy, cw + .8, ch + .8); if (this.blown[i] !== G.id) { this.blown[i] = G.id; if (this.lum[i] > .3 && hash(i, 11) < .34) this.emit(i, true); } } } }
      c.font = `700 ${Math.max(5, ch * .98).toFixed(1)}px "JetBrains Mono","DejaVu Sans Mono",ui-monospace,monospace`; c.textAlign = "center"; c.textBaseline = "middle"; c.globalCompositeOperation = "lighter";
      // characters flare and change; a band of light crosses the picture
      { const step = Math.floor(t * 7), band = (t * .22) % 1.7 - .35, lit = this.lit; for (let n = 0; n < lit.length; n++) { const i = lit[n], x = i % cols, y = i / cols | 0, u = x / cols * .7 + y / rows * .3, near = Math.max(0, 1 - Math.abs(u - band) / .09), r = hash(i, step);
          if (r > k.sh + near * .22) continue; c.globalAlpha = .35 + .5 * near; c.fillStyle = this.col[i]; c.fillText(RV_RAMP[(r * 9973 | 0) % RV_RAMP.length], (x + .5) * cw + dx, (y + .5) * ch + dy); } }
      // bits of it lift off and drift away
      this.acc += dt * k.emit; while (this.acc >= 1) { this.acc -= 1; this.emit(this.lit[Math.random() * this.lit.length | 0], false); }
      const keep = []; for (const q of this.parts) { q.life += dt; if (q.life >= q.max) continue; const f = q.life / q.max; q.x += (q.vx + Math.sin(t * 2.1 + q.ph) * 9) * dt; q.y += (q.vy + Math.cos(t * 1.7 + q.ph) * 7) * dt; q.vy -= 4 * dt;
        c.globalAlpha = Math.sin(Math.PI * Math.min(1, f * 1.15)) * .8; c.fillStyle = q.col; c.fillText(q.ch, q.x, q.y); keep.push(q); } this.parts = keep.length > 500 ? keep.slice(-500) : keep;
      c.globalAlpha = 1; c.globalCompositeOperation = "source-over";
    }
  }
  function loop(now) {
    raf = 0; if (!all.size) return; tick++;
    for (const o of [...all]) { if (!o.card.isConnected) { all.delete(o); by.delete(o.card); continue; } if (o.ok) o.mount(); if (tick % 2 === 0 && !document.hidden && o.card.offsetParent !== null) o.frame(now); }   // thirty frames a second is plenty
    if (all.size) raf = requestAnimationFrame(loop);
  }
  // bring a card's picture to life (safe to call again and again for the same card: it only puts the canvas back if the page was redrawn)
  function on(card, copy) {
    if (reduced || !card || !copy) return; const tier = Math.min(6, RAR[BY_NO[copy.no].rar].tier + (copy.fx ? 1 : 0)); if (tier < 2) return;
    let o = by.get(card); if (!o) { o = new One(card, tier); by.set(card, o); all.add(o); } else if (o.ok) o.mount();
    if (!raf) raf = requestAnimationFrame(loop);
  }
  return { on };
})();
