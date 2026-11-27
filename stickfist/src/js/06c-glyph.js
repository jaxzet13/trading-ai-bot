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

  /* The cards are stick figures, so the scenes are too: a plain figure (a ring for a head, lines for the rest) doing one thing that only it could do. */
  const LW = 1.7, limb = (g, pts, col, w) => { g.strokeStyle = col; g.lineWidth = w || LW; g.lineCap = "round"; g.lineJoin = "round"; g.beginPath(); pts.forEach((p, i) => i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])); g.stroke(); };
  const headAt = (g, x, y, r, col) => { g.strokeStyle = col; g.lineWidth = LW; g.fillStyle = "#030304"; g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill(); g.stroke(); };
  const arm2 = (g, sx, sy, tx, ty, L, side, col) => { let dx = tx - sx, dy = ty - sy, d = Math.hypot(dx, dy); if (d > L * 1.98) { tx = sx + dx / d * L * 1.98; ty = sy + dy / d * L * 1.98; dx = tx - sx; dy = ty - sy; d = L * 1.98; } const h = Math.sqrt(Math.max(0, L * L - d * d / 4)), mx = sx + dx / 2, my = sy + dy / 2, ex = mx - dy / d * h * side, ey = my + dx / d * h * side; limb(g, [[sx, sy], [ex, ey], [tx, ty]], col); return [tx, ty]; };

  /* ---------- Morpho: a stick figure with butterfly wings, hovering and beating them ---------- */
  function morpho(g, t) {
    glow(g, 50, 62, 52, "50,150,255", .13 + .05 * Math.sin(t * 2.4));
    const flap = t * 2.9, open = .2 + .8 * (.5 + .5 * Math.cos(flap)), bob = Math.sin(t * 1.3) * 2.2, tilt = Math.sin(t * .8) * .03;
    g.save(); g.translate(50, 66 + bob); g.rotate(tilt); g.scale(.98, .98); g.translate(-52, -58);
    const fore = "M52,56 C60,40 78,14 97,13 C99,30 98,46 90,54 C80,60 64,62 54,62 Z", hind = "M54,61 C70,56 88,58 90,70 C90,84 76,96 64,86 C58,80 55,72 53,68 Z";
    for (const sd of [-1, 1]) {
      g.save(); g.translate(52, 0); g.scale(sd * open, 1 + (1 - open) * .06); g.translate(-52, 0);
      for (const d of [hind, fore]) { const p = new Path2D(d), gr = g.createRadialGradient(54, 58, 2, 60, 52, 52); gr.addColorStop(0, "#d8f8ff"); gr.addColorStop(.2, "#4fd0ff"); gr.addColorStop(.55, "#1568ff"); gr.addColorStop(1, "#0b2b9c"); g.fillStyle = gr; g.fill(p); g.strokeStyle = "#020a22"; g.lineWidth = 1.5; g.lineJoin = "round"; g.stroke(p); }
      g.strokeStyle = "rgba(4,16,70,.55)"; g.lineWidth = .5; for (let k = 0; k <= 7; k++) { const q = bez([97, 13], [99, 30], [98, 46], [90, 54], k / 7); g.beginPath(); g.moveTo(54, 59); g.lineTo(q[0], q[1]); g.stroke(); }
      g.fillStyle = "rgba(235,250,255,.95)"; for (let k = 0; k < 15; k++) { const q = bez([97, 13], [99, 30], [98, 46], [90, 54], k / 14); g.beginPath(); g.arc(q[0] - 1.6, q[1] + .4, .55, 0, TAU); g.fill(); } for (let k = 0; k < 11; k++) { const q = bez([90, 70], [90, 84], [76, 96], [64, 86], k / 10); g.beginPath(); g.arc(q[0] - 1.2, q[1] - .8, .5, 0, TAU); g.fill(); }
      g.restore();
    }
    g.restore();
    // the figure in front: head, body, arms held out, legs hanging
    const W0 = "#f4f6ff", sw = Math.sin(t * 2.1) * 2, bx = 50, hy = 54 + bob;
    headAt(g, bx, hy, 4.3, W0); limb(g, [[bx, hy + 4.3], [bx, hy + 28]], W0); limb(g, [[bx, hy + 9], [bx - 13, hy + 17 + sw], [bx - 21, hy + 14]], W0); limb(g, [[bx, hy + 9], [bx + 13, hy + 17 - sw], [bx + 21, hy + 14]], W0);
    limb(g, [[bx, hy + 28], [bx - 5, hy + 40 + sw * .4], [bx - 4, hy + 52]], W0); limb(g, [[bx, hy + 28], [bx + 5, hy + 40 - sw * .4], [bx + 4, hy + 52]], W0);
    sparkles(g, t, 24, "160,220,255", 6, 112);
  }

  /* ---------- Heartstring: a stick figure holding a heart of words on a string ---------- */
  const WORDS = ["stixx", "pulled it", "rare", "mint", "yours", "text", "hold", "glow", "one of one", "i love it"];
  function heartPath(g, cx, cy, k) { g.beginPath(); for (let i = 0; i <= 120; i++) { const a = i / 120 * TAU, x = 16 * Math.pow(Math.sin(a), 3), y = -(13 * Math.cos(a) - 5 * Math.cos(2 * a) - 2 * Math.cos(3 * a) - Math.cos(4 * a)); if (i) g.lineTo(cx + x * k, cy + y * k); else g.moveTo(cx + x * k, cy + y * k); } g.closePath(); }
  function heartstring(g, t) {
    const ph = (t % 1.25) / 1.25, beat = Math.exp(-Math.pow((ph - .08) / .05, 2)) + .7 * Math.exp(-Math.pow((ph - .27) / .06, 2)), s = 1 + .09 * beat, hx = 62 + Math.sin(t * 1.3) * 3.5, hy = 34 + Math.cos(t * 1.7) * 2.5 - beat * 1.2, k = 1.75 * s;
    glow(g, hx, hy, 56, "255,40,90", .2 + .12 * beat);
    const hop = Math.abs(Math.sin(t * 2.5)) * -2.2, fx = 30, W0 = "#f6f2f4", top = 56 + hop;
    // the string from his hand up to the heart
    const hand = [fx + 16, top - 9 + Math.sin(t * 1.7) * 1.2]; g.strokeStyle = "rgba(255,230,235,.85)"; g.lineWidth = .5; g.beginPath(); g.moveTo(hand[0], hand[1]); g.quadraticCurveTo((hand[0] + hx) / 2 + Math.sin(t * 2) * 3, (hand[1] + hy + 16) / 2 + 6, hx, hy + 14 * s); g.stroke();
    heartPath(g, hx, hy, k); const gr = g.createLinearGradient(hx - 26, hy - 20, hx + 26, hy + 24); gr.addColorStop(0, "#ff7a9c"); gr.addColorStop(.5, "#e0204f"); gr.addColorStop(1, "#8c0a2c"); g.fillStyle = gr; g.fill();
    g.save(); heartPath(g, hx, hy, k); g.clip(); g.textAlign = "center"; g.textBaseline = "middle"; for (let i = 0; i < 130; i++) { const x = hx - 30 + hs(i, 1) * 60, y = hy - 28 + hs(i, 2) * 56, ang = hs(i, 3) * TAU + Math.sin(t * .6 + i) * .15, w = WORDS[(hs(i, 4) * WORDS.length) | 0]; g.save(); g.translate(x, y); g.rotate(ang); g.font = `700 ${2.2 + hs(i, 6) * 1.4}px Georgia, serif`; g.fillStyle = `rgba(255,235,240,${.55 + .4 * hs(i, 5)})`; g.fillText(w, 0, 0); g.restore(); } g.restore();
    heartPath(g, hx, hy, k); g.strokeStyle = "rgba(255,190,205,.8)"; g.lineWidth = .7; g.stroke();
    g.font = `700 ${6 + beat}px Georgia, serif`; g.textAlign = "center"; g.textBaseline = "middle"; g.shadowColor = "rgba(255,255,255,.9)"; g.shadowBlur = 4; g.fillStyle = "#fff"; g.fillText("stixx", hx, hy - 1); g.shadowBlur = 0;
    // the figure, hopping on the beat: one arm up holding the string, the other waving
    headAt(g, fx, top, 4.2, W0); limb(g, [[fx, top + 4.2], [fx, top + 28]], W0); arm2(g, fx, top + 9, hand[0], hand[1], 12, 1, W0); arm2(g, fx, top + 9, fx - 16, top + 14 + Math.sin(t * 6) * 5, 10, -1, W0);
    limb(g, [[fx, top + 28], [fx - 6, 108 - 6 + hop * .5], [fx - 6, 108]], W0); limb(g, [[fx, top + 28], [fx + 6, 108 - 6 + hop * .5], [fx + 6, 108]], W0);
    g.strokeStyle = "rgba(255,255,255,.12)"; g.lineWidth = .5; g.beginPath(); g.moveTo(10, 108.6); g.lineTo(90, 108.6); g.stroke();
    for (let i = 0; i < 9; i++) { const u = ((t * (.25 + hs(i, 1) * .3) + hs(i, 2)) % 1), x = hx + (hs(i, 3) - .5) * 40, y = hy + 10 - u * 40; g.fillStyle = `rgba(255,120,150,${(1 - u) * .8})`; heartPath(g, x, y, .1 + hs(i, 4) * .06); g.fill(); }
    sparkles(g, t, 14, "255,180,200", 6, 112);
  }

  /* ---------- Vigil: a stick figure kneeling in the dark, holding a candle up ---------- */
  function flame(g, tx, ty, sc, col, bx, by) { g.fillStyle = col; g.beginPath(); g.moveTo(bx, by); g.bezierCurveTo(bx - 4.5 * sc, by - 2, bx - 4.5 * sc, by - 10, bx - 1 * sc, by - 15); g.bezierCurveTo(bx - .6, by - 19, tx - .8, ty + 4, tx, ty); g.bezierCurveTo(tx + .9, ty + 4, bx + .8, by - 18, bx + 1.2 * sc, by - 14); g.bezierCurveTo(bx + 4.5 * sc, by - 9, bx + 4.5 * sc, by - 2, bx, by); g.fill(); }
  function vigil(g, t) {
    const fl = Math.sin(t * 9.1) * .5 + Math.sin(t * 14.3 + 1) * .35 + Math.sin(t * 5.7) * .4, sway = Math.sin(t * 4.7) * 1 + Math.sin(t * 7.9) * .6, bx = 64, by = 56;
    glow(g, bx, by - 6, 64, "255,150,50", .22 + fl * .05); glow(g, bx, by - 8, 26, "255,210,120", .2 + fl * .04);
    const tint = "#ffe6bc"; // the figure is lit from the flame: warm on the side facing it
    // the ground, and the shadow the flame throws behind him
    const gr = g.createLinearGradient(0, 106, 0, 114); gr.addColorStop(0, "rgba(255,170,80,.18)"); gr.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = gr; g.fillRect(0, 106, 100, 8);
    // kneeling: one knee down, torso leaning toward the light, head bowed a little
    headAt(g, 40, 68, 4.3, tint); limb(g, [[41, 72], [44, 90]], tint); limb(g, [[44, 90], [56, 91], [57, 106]], tint); limb(g, [[44, 90], [36, 100], [28, 106]], tint);
    const hand = arm2(g, 42, 77, bx - 2, by + 8 + fl * .4, 10, -1, tint); limb(g, [[42, 77], [33, 84], [36, 92]], "#c9a979");
    // the candle in his hand
    g.fillStyle = "#fff0cc"; g.beginPath(); g.roundRect(hand[0] - 2.1, hand[1] - 10, 4.2, 13, 1); g.fill(); g.fillStyle = "#ffd890"; g.beginPath(); g.ellipse(hand[0], hand[1] - 10, 2.1, .8, 0, 0, TAU); g.fill();
    const H = 15 + fl * 2.2, tx = hand[0] + sway, ty = hand[1] - 11 - H; glow(g, hand[0], hand[1] - 16, 30, "255,200,110", .1);
    flame(g, tx, ty, 1, "rgba(255,110,20,.95)", hand[0], hand[1] - 10.5); flame(g, tx, ty + H * .25, .72, "#ffb62e", hand[0], hand[1] - 10.5); flame(g, tx, ty + H * .5, .45, "#fff3c4", hand[0], hand[1] - 10.5);
    for (let i = 0; i < 16; i++) { const u = ((t * (.35 + hs(i, 1) * .5) + hs(i, 2)) % 1), x = hand[0] + Math.sin(u * 6 + i) * (2 + u * 11) + sway, y = hand[1] - 14 - u * 46; g.fillStyle = `rgba(255,${150 + (hs(i, 3) * 90) | 0},60,${(1 - u) * .9})`; g.beginPath(); g.arc(x, y, .35 + hs(i, 4) * .6, 0, TAU); g.fill(); }
  }

  /* ---------- Light Writer: a stick figure writing in the air with a sparkler, and the light stays behind it ---------- */
  function lightwriter(g, t) {
    const fx = 30, sh = [fx, 68], W0 = "#f4f6ff", tau = t * 1.7, P = tt => [60 + 22 * Math.sin(1.3 * tt + .6), 56 + 19 * Math.sin(2.0 * tt)];
    glow(g, 60, 56, 52, "255,150,200", .07);
    // the trail: the last second and a half of where the tip has been, fading through gold, pink and blue
    const N = 150; let prev = P(tau);
    for (let i = 1; i < N; i++) { const q = P(tau - i * .016), u = i / N, a = Math.pow(1 - u, 1.6), hue = 48 + u * 280; g.strokeStyle = `hsla(${hue % 360},95%,${72 - u * 18}%,${a})`; g.lineWidth = 2.3 * (1 - u * .8) + .3; g.lineCap = "round"; g.beginPath(); g.moveTo(prev[0], prev[1]); g.lineTo(q[0], q[1]); g.stroke(); prev = q; }
    const tip = P(tau); glow(g, tip[0], tip[1], 14, "255,230,170", .9);
    for (let i = 0; i < 46; i++) { const life = ((t * 3 + hs(i, 1) * 5) % 1), ang = hs(i, 2) * TAU + i, r = life * (4 + hs(i, 3) * 11); g.fillStyle = `rgba(255,${200 + (hs(i, 4) * 55) | 0},${120 + (hs(i, 5) * 100) | 0},${(1 - life) * .95})`; g.beginPath(); g.arc(tip[0] + Math.cos(ang) * r, tip[1] + Math.sin(ang) * r + life * 3, .3 + hs(i, 6) * .55, 0, TAU); g.fill(); }
    // the figure: arm reaching to the sparkler, a small step in time with the writing
    const stp = Math.sin(t * 3) * 2; headAt(g, fx, 58, 4.3, W0); limb(g, [[fx, 62.3], [fx, 88]], W0);
    const dx = tip[0] - sh[0], dy = tip[1] - sh[1], d = Math.hypot(dx, dy), reach = Math.min(d - 7, 37), hand = [sh[0] + dx / d * reach, sh[1] + dy / d * reach]; arm2(g, sh[0], sh[1] - 4, hand[0], hand[1], 19.5, dy > 0 ? 1 : -1, W0);
    g.strokeStyle = "#ffd890"; g.lineWidth = .7; g.beginPath(); g.moveTo(hand[0], hand[1]); g.lineTo(tip[0], tip[1]); g.stroke(); arm2(g, sh[0], sh[1] - 4, fx - 10, 88 + Math.sin(t * 2) * 3, 10, -1, W0);
    limb(g, [[fx, 88], [fx - 6 + stp, 99], [fx - 7 + stp, 108]], W0); limb(g, [[fx, 88], [fx + 6 - stp, 99], [fx + 7 - stp, 108]], W0);
    g.strokeStyle = "rgba(255,255,255,.12)"; g.lineWidth = .5; g.beginPath(); g.moveTo(8, 108.6); g.lineTo(60, 108.6); g.stroke();
    sparkles(g, t, 14, "255,200,230", 6, 112);
  }

  /* ---------- Phoenix: a stick figure on fire, with wings of flame, rising ---------- */
  function feather(g, L, w, c0, c1, c2) { const gr = g.createLinearGradient(0, 0, L, 0); gr.addColorStop(0, c0); gr.addColorStop(.55, c1); gr.addColorStop(1, c2); g.fillStyle = gr; g.beginPath(); g.moveTo(0, 0); g.quadraticCurveTo(L * .45, -w, L, 0); g.quadraticCurveTo(L * .45, w * .75, 0, 0); g.fill(); g.strokeStyle = "rgba(60,0,0,.35)"; g.lineWidth = .4; g.stroke(); }
  function phoenix(g, t) {
    const fl = Math.sin(t * 2.3), up = .5 + .5 * fl, rise = Math.sin(t * 1.2) * 3; glow(g, 50, 60 + rise, 66, "255,80,20", .16 + up * .06); glow(g, 50, 58 + rise, 28, "255,200,80", .12);
    g.save(); g.translate(0, rise);
    for (let i = 0; i < 6; i++) { g.save(); g.translate(50 + (i - 2.5) * 1.8, 80); const sway = Math.sin(t * 2 + i * .7) * .12 + (i - 2.5) * .11; g.rotate(Math.PI / 2 + sway); feather(g, 36 - Math.abs(i - 2.5) * 3, 2.8, "#ff9a1f", "#ff4a1a", "#ffe066"); g.restore(); }
    for (const sd of [-1, 1]) for (let i = 0; i < 9; i++) { g.save(); g.translate(50 + sd * 4, 62); const base = (-1.15 + i * .2) + (fl * .32 - .1) * (1 - i * .05) - .25; g.scale(sd, 1); g.rotate(base); feather(g, 44 - i * 2.3, 4.8 - i * .22, "#ffd24a", i < 4 ? "#ff7a1f" : "#ff4a1a", i < 5 ? "#d4162c" : "#8e0a22"); g.restore(); }
    // the figure, white hot, arms along the wings, legs trailing into the flame
    const W0 = "#fff7e0", ar = (fl * .32 - .1);
    headAt(g, 50, 50, 4.3, W0); limb(g, [[50, 54.3], [50, 80]], W0); limb(g, [[50, 60], [40, 56 - ar * 8], [31, 49 - ar * 14]], W0); limb(g, [[50, 60], [60, 56 - ar * 8], [69, 49 - ar * 14]], W0); limb(g, [[50, 80], [46, 92], [47 + Math.sin(t * 3) * 1.5, 100]], W0); limb(g, [[50, 80], [54, 92], [53 - Math.sin(t * 3) * 1.5, 100]], W0);
    g.restore();
    for (let i = 0; i < 28; i++) { const u = ((t * (.3 + hs(i, 1) * .45) + hs(i, 2)) % 1), x = 50 + (hs(i, 3) - .5) * 74 + Math.sin(u * 7 + i) * 4, y = 100 - u * 94; g.fillStyle = `rgba(255,${130 + (hs(i, 4) * 110) | 0},40,${(1 - u) * .95})`; g.beginPath(); g.arc(x, y, .4 + hs(i, 5) * .8, 0, TAU); g.fill(); }
  }
  // the moment each one looks best as a still picture, and how its characters arrive: from dust, row by row, or in a burst from the middle
  const STILL = { vigil: 1.1, lightwriter: 2.1, heartstring: .1, morpho: .97, phoenix: .72 }, MODE = { vigil: "dust", lightwriter: "dust", heartstring: "rows", morpho: "burst", phoenix: "burst" };
  return { vigil, lightwriter, heartstring, morpho, phoenix, STILL, MODE };
})();

/* ---- the player: reads a scene as cells, and flies the characters in ---- */
const Glyph = (() => {
  const RAMP = " .'`:;il1tfrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$", N = RAMP.length - 1, all = new Set(), by = new WeakMap(); let raf = 0;
  const hh = (a, b, c) => { let h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263) ^ Math.imul((c || 0) | 0, 2147483647); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  const clamp = (x, a = 0, b = 1) => x < a ? a : x > b ? b : x, eo = x => 1 - Math.pow(1 - clamp(x), 3), back = x => { x = clamp(x); const c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
  class One {
    constructor(card, id, opts) {
      opts = opts || {}; this.card = card; this.id = id; this.scene = GlyphScenes[id]; this.mode = (GlyphScenes.MODE && GlyphScenes.MODE[id]) || "dust"; this.pic = card.querySelector(".pic"); this.cv = document.createElement("canvas"); this.cv.className = "alive"; this.cv.setAttribute("aria-hidden", "true");
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
          const dist = Math.hypot((x - cx) / cx, (y - cy) / cy), mode = this.mode; let u, e;
          if (mode === "rows") {                                                              // row by row, bottom to top: each character drops into its place
            const delay = (1 - y / rows) * .7 + hh(x, y, this.seed) * .08; u = clamp((p - delay) / .26); if (u <= 0) continue; e = eo(u); ox += (hh(x, y, this.seed + 1) - .5) * 34 * (1 - e); oy -= (1 - e) * 30; a = clamp(u * 3);
          } else if (mode === "burst") {                                                      // everything starts as one bright seed in the middle and blooms outward
            const delay = hh(x, y, this.seed) * .1 + dist * .12; u = clamp((p - delay) / .62); if (u <= 0) continue; e = back(u); const mx = cx * cw, my = cy * ch; ox = mx + (ox - mx) * (.03 + .97 * e); oy = my + (oy - my) * (.03 + .97 * e); a = clamp(u * 4);
          } else {                                                                            // dust: each flies in from a scatter and lands with a small overshoot, the middle first
            const delay = dist * .3 + hh(x, y, this.seed) * .2; u = clamp((p - delay) / .5); if (u <= 0) continue; e = back(u); const sc = 1 - e, ang = hh(x, y, this.seed + 1) * 6.283 + (1 - u) * 5.5, R = (40 + hh(x, y, this.seed + 2) * 190) * sc; ox += Math.cos(ang) * R; oy += Math.sin(ang) * R * .8 - sc * sc * 30; a = clamp(u * 2.2);
          }
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
  const has = id => typeof GlyphScenes[id] === "function";
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
