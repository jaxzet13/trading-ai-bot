/* ============================================================================
   The dealing machine: a short animation (about two seconds, tap to skip) for opening more than one pack. A machine takes the packs in, deals the cards out and
   shuffles them into a stack. It looks the same for every result: it is drawn before anything is revealed and says nothing about what you got, only how many cards there are.
   ========================================================================== */
const Machine = (() => {
  if (typeof CanvasRenderingContext2D !== "undefined" && !CanvasRenderingContext2D.prototype.roundRect) CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h) { this.rect(x, y, w, h); };       // older browsers draw square corners
  let cv = null, raf = 0, done = null, skipped = false;
  const INK = "#ece7dc", DIM = "#8d897f", LINE = "#3a3a3f", GREEN = "#9fd8a6", AMBER = "#ffc94a";
  const hash = (i, k) => { let h = Math.imul(i * 374761393 + k * 668265263, 1274126177); h ^= h >>> 13; h = Math.imul(h, 1103515245); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  const ease = t => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3), inout = t => { t = Math.min(1, Math.max(0, t)); return t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }, lerp = (a, b, t) => a + (b - a) * t;
  function back(w, h) {                                                                                // one card back, drawn once and stamped for every card
    const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d");
    g.fillStyle = "#0b0b0d"; g.strokeStyle = INK; g.lineWidth = Math.max(1.5, w / 36); g.beginPath(); g.roundRect(1, 1, w - 2, h - 2, w / 12); g.fill(); g.stroke();
    g.fillStyle = DIM; g.font = `${Math.round(w / 8)}px ui-monospace, Menlo, monospace`; g.textAlign = "center"; g.textBaseline = "middle"; const gl = "░▒▓#%@+=:."; const cols = 7, rows = 9;
    for (let r = 0; r < rows; r++) for (let q = 0; q < cols; q++) { g.globalAlpha = .18 + .5 * hash(r * 9 + q, 3); g.fillText(gl[Math.floor(hash(r * 9 + q, 5) * gl.length)], w * (.14 + q * .12), h * (.1 + r * .098)); }
    g.globalAlpha = 1; g.fillStyle = INK; g.font = `700 ${Math.round(w / 5)}px ui-monospace, Menlo, monospace`; g.fillText("STIXX", w / 2, h / 2); return c;
  }
  function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; if (cv) { cv.remove(); cv = null; } const d = done; done = null; if (d) d(); }
  function skip() { skipped = true; stop(); }
  // n packs, total cards: resolves when the animation ends or is skipped
  function play(n, total, name) {
    if (reduced) return Promise.resolve();
    return new Promise(res => {
      done = res; skipped = false; const st = $("stage"); cv = document.createElement("canvas"); cv.className = "mach"; st.appendChild(cv);
      const dpr = Math.min(2, devicePixelRatio || 1), W = st.clientWidth, H = st.clientHeight; cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px"; const g = cv.getContext("2d"); g.scale(dpr, dpr);
      cv.addEventListener("pointerdown", () => skip());
      const C = Math.min(total, 36), cw = Math.min(64, W * .17), ch = cw * 1.4, bk = back(Math.round(cw * dpr), Math.round(ch * dpr));
      const mw = Math.min(W * .78, 320), mh = 118, mx = W / 2 - mw / 2, my = H * .13, slotY = my + mh;
      const T = 2.35, t0 = performance.now(); Snd.machine(total); buzz([18, 20, 18]);
      const tgt = i => ({ x: W / 2 + (hash(i, 1) - .5) * (W * .66), y: H * .62 + (hash(i, 2) - .5) * H * .2, r: (hash(i, 3) - .5) * .9 });
      const tgt2 = i => ({ x: W / 2 + (hash(i, 11) - .5) * (W * .66), y: H * .62 + (hash(i, 12) - .5) * H * .2, r: (hash(i, 13) - .5) * .9 });
      const frame = now => {
        const t = (now - t0) / 1000; if (t >= T || !cv) { stop(); return; }
        g.clearRect(0, 0, W, H);
        // the machine slides down into place, then hums
        const slide = ease(t / .35), shake = t > .35 && t < 1.8 ? Math.sin(t * 90) * 1.2 : 0, oy = (1 - slide) * -mh * 1.4;
        g.save(); g.translate(shake, oy);
        g.fillStyle = "#0b0b0d"; g.strokeStyle = INK; g.lineWidth = 2; g.beginPath(); g.roundRect(mx, my, mw, mh, 14); g.fill(); g.stroke();
        g.strokeStyle = LINE; g.beginPath(); g.moveTo(mx + 14, my + 38); g.lineTo(mx + mw - 14, my + 38); g.stroke();
        g.fillStyle = INK; g.font = "600 13px ui-monospace, Menlo, monospace"; g.textAlign = "left"; g.textBaseline = "middle"; g.fillText("STIXX · DEALER", mx + 16, my + 20);
        for (let k = 0; k < 3; k++) { const on = Math.sin(t * 14 + k * 2.1) > -.2 && t > .3; g.fillStyle = on ? (k === 1 ? AMBER : GREEN) : "#25252a"; g.beginPath(); g.arc(mx + mw - 20 - k * 18, my + 20, 4.5, 0, 6.3); g.fill(); }
        // the number of cards, counting up as they come out (the real number)
        const dealt = Math.min(total, Math.round(total * Math.min(1, Math.max(0, (t - .5) / 1.15))));
        g.fillStyle = DIM; g.font = "12px ui-monospace, Menlo, monospace"; g.fillText(`${n} × ${name}`, mx + 16, my + 62); g.fillStyle = INK; g.font = "700 22px ui-monospace, Menlo, monospace"; g.textAlign = "right"; g.fillText(`${dealt} / ${total}`, mx + mw - 16, my + 66); g.textAlign = "left";
        g.fillStyle = "#050506"; g.fillRect(mx + 16, slotY - 22, mw - 32, 8); g.strokeStyle = t > .5 && t < 1.7 ? GREEN : LINE; g.lineWidth = 2; g.strokeRect(mx + 16, slotY - 22, mw - 32, 8);   // the slot
        // packs drop into the top of the machine
        for (let k = 0; k < Math.min(n, 6); k++) { const s = k * .05, p = ease((t - s) / .32); if (t - s < 0 || p >= 1) continue; g.save(); g.globalAlpha = 1 - p * .3; g.translate(W / 2 + (k - (Math.min(n, 6) - 1) / 2) * 26, my - 64 + p * 62); g.rotate((hash(k, 7) - .5) * .5); g.fillStyle = "#16161a"; g.strokeStyle = INK; g.lineWidth = 1.5; g.beginPath(); g.roundRect(-11, -16, 22, 32, 3); g.fill(); g.stroke(); g.restore(); }
        g.restore();
        // the cards come out one by one, land in a spread, get shuffled about, and are gathered into one stack
        const sx = W / 2, sy = slotY + oy;
        for (let i = 0; i < C; i++) {
          const ts = .5 + i * (1.15 / C), f = (t - ts) / .5; if (f < 0) continue;
          const a = tgt(i), b = tgt2(i), land = ease(f), shuf = inout((t - 1.5) / .35), gat = inout((t - 1.95) / .32);
          let x = lerp(sx, lerp(a.x, b.x, shuf), land), y = lerp(sy, lerp(a.y, b.y, shuf), land) - Math.sin(Math.min(1, f) * Math.PI) * 46, r = lerp(0, lerp(a.r, b.r, shuf), land);
          x = lerp(x, W / 2, gat); y = lerp(y, H * .62, gat); r = lerp(r, (hash(i, 9) - .5) * .12, gat);
          const sc = lerp(.4, 1, ease(f * 1.4)); g.save(); g.translate(x, y); g.rotate(r + (shuf > 0 && shuf < 1 ? Math.sin(t * 40 + i) * .06 : 0)); g.scale(sc, sc); g.drawImage(bk, -cw / 2, -ch / 2, cw, ch); g.restore();
        }
        // a short flash as the stack lands
        if (t > 2.2) { g.fillStyle = `rgba(236,231,220,${Math.max(0, .5 - (t - 2.2) * 3.3)})`; g.fillRect(0, 0, W, H); }
        g.fillStyle = DIM; g.font = "12px ui-monospace, Menlo, monospace"; g.textAlign = "center"; g.fillText(t < 1.5 ? "dealing your cards" : "shuffling them into a stack", W / 2, H * .9); g.textAlign = "left";
        raf = requestAnimationFrame(frame);
      };
      raf = requestAnimationFrame(frame);
    });
  }
  return { play, skip, stop, active: () => !!cv };
})();
