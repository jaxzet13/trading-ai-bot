/* ============================================================================
   8d. CUTSCENES. Seven cards come with a short ASCII film. Every character is worked out from a formula for its place on the screen and the moment
   in time, the way a shader works out pixels, so nothing is stored frame by frame: a sun, a corona, a cathedral, a pair of wings, a collapsing star.
   ========================================================================== */
const Cut = (() => {
  const RAMP = " .'`,:;-~=+*xX#%@", FONT = "'JetBrains Mono', 'DejaVu Sans Mono', ui-monospace, Menlo, Consolas, monospace";
  const hash = (a, b, c) => { let h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263) ^ Math.imul((c || 0) | 0, 2147483647); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
  const cl = (x, a, b) => x < (a == null ? 0 : a) ? (a == null ? 0 : a) : x > (b == null ? 1 : b) ? (b == null ? 1 : b) : x;
  const sm = (a, b, x) => { x = cl((x - a) / (b - a)); return x * x * (3 - 2 * x); }, mixv = (a, b, k) => a + (b - a) * k, ease = x => 1 - Math.pow(1 - cl(x), 3), ease2 = x => { x = cl(x); return x < .5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2; };
  const vn = (x, y, s) => { const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi, u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf); return mixv(mixv(hash(xi, yi, s), hash(xi + 1, yi, s), u), mixv(hash(xi, yi + 1, s), hash(xi + 1, yi + 1, s), u), v); };
  const fbm = (x, y, s) => (vn(x, y, s) * .5 + vn(x * 2, y * 2, s + 1) * .25 + vn(x * 4, y * 4, s + 2) * .125 + vn(x * 8, y * 8, s + 3) * .0625) / .9375;
  const typed = (str, t, t0, cps) => str.slice(0, Math.max(0, Math.floor((t - t0) * (cps || 16))));
  const mkpal = stops => Array.from({ length: 32 }, (_, i) => { const k = i / 31 * (stops.length - 1), j = Math.min(stops.length - 2, Math.floor(k)), f = k - j, a = stops[j], b = stops[j + 1]; return `rgb(${Math.round(mixv(a[0], b[0], f))},${Math.round(mixv(a[1], b[1], f))},${Math.round(mixv(a[2], b[2], f))})`; });

  /* ---- the scenes. cell(x, y, t, g) gives the brightness (0 to 1) of the character at that spot: x and y are in screen-height units, 0,0 in the middle,
          y pointing down, so a circle with radius .2 is a circle. It may set g.pi to choose a palette, g.ch to force a character.
          over(g, t) draws what is not a formula: a figure, a line of type, a flash. */
  const FIG = ["  _o_  ", " / | \\ ", "   |   ", "  / \\  ", " /   \\ "];
  const INTRO_SERIES = (() => { const a = [10, 11, 9.5, 12, 10.5, 14, 13, 24, 70, 150, 184], n = 80, out = []; for (let i = 0; i < n; i++) { const f = i / (n - 1) * (a.length - 1), j = Math.min(a.length - 2, Math.floor(f)), k = f - j, e = k * k * (3 - 2 * k); out.push(Math.exp(mixv(Math.log(a[j]), Math.log(a[j + 1]), e) + (hash(i, 3, 9) - .5) * .06)); } return out; })();   // a price that wobbles and then runs, for the intro
  const SCENES = {
    /* INTRO: what the app is, in six seconds. A pack tears, a card runs, a sale. */
    intro: {
      dur: 5.4, fsMul: 1.3, pals: [mkpal([[0, 0, 0], [30, 30, 32], [120, 118, 110], [200, 195, 185], [236, 231, 220]])],
      cell: () => 0,
      over(g, tt) {
        const t = tt * 1.15;   // written for six seconds, played in five and a bit
        const C = g.C, R = g.R, cx = C >> 1, cy = R >> 1, INK = [236, 231, 220], GRN = [159, 216, 166], DIM = [141, 137, 127], RED = [232, 120, 109];
        const vis = (a, b, f) => { f = f || .22; return sm(a, a + f, t) * (1 - sm(b - f, b, t)); };
        const logo = (x0, y0, col, al, dec) => {      // the pixel lettering, two columns for every pixel, decoding from noise
          const rows = blockText("STIXX").split("\n"), w = rows[0].length;
          rows.forEach((row, r) => { for (let i = 0; i < w; i++) if (row[i] === "█") { const seed = hash(i, r, 1), k = dec == null ? 1 : dec * 1.5 - seed * .7; if (k <= 0) continue; const ch = k < .4 ? ".:*#"[(Math.floor(t * 28) + i * 3 + r) % 4] : "█"; g.put(x0 + i * 2, y0 + r, ch, col, al * (k < .4 ? .55 : 1)); g.put(x0 + i * 2 + 1, y0 + r, ch, col, al * (k < .4 ? .55 : 1)); } });
        };
        const box = (x0, y0, w, h, col, al) => { for (let i = 1; i < w - 1; i++) { g.put(x0 + i, y0, "─", col, al); g.put(x0 + i, y0 + h - 1, "─", col, al); } for (let j = 1; j < h - 1; j++) { g.put(x0, y0 + j, "│", col, al); g.put(x0 + w - 1, y0 + j, "│", col, al); } g.put(x0, y0, "┌", col, al); g.put(x0 + w - 1, y0, "┐", col, al); g.put(x0, y0 + h - 1, "└", col, al); g.put(x0 + w - 1, y0 + h - 1, "┘", col, al); };
        const lx = cx - 29, ly = cy - 3, tall = R > C * .9 ? 1.55 : 1;   // on a tall screen the pictures are drawn taller
        // 0 - 1.4: the name
        const a0 = vis(-.3, 1.5, .3); if (a0 > 0) { logo(lx, ly, INK, a0, t / .8); g.text(typed("cards made of text.", t, .55, 20), .6, DIM); }
        // 1.4 - 2.7: open a pack
        const a1 = vis(1.4, 2.8, .25); if (a1 > 0) {
          const PH = Math.round(10 * tall), k = ease((t - 1.4) / .45), dropY = Math.round((1 - k) * -16), shake = t > 1.85 && t < 2.05 ? (Math.floor(t * 40) % 2 ? 1 : -1) : 0, tear = t > 2.05, tx = cx - 13 + shake, ty = cy - Math.round(PH / 2) + dropY;
          g.text(typed("1   open a pack", t, 1.5, 22), .16, INK);
          const crimp = y => { for (let i = 0; i < 26; i++) g.put(tx + i, y, i % 2 ? "/" : "\\", INK, a1); };
          const ty2 = tear ? ty - Math.round((t - 2.05) * 26) : ty, topA = tear ? a1 * (1 - sm(2.05, 2.5, t)) : a1;
          for (let i = 0; i < 26; i++) g.put(tx + i, ty2, i % 2 ? "\\" : "/", INK, topA);
          if (!tear || t < 2.6) { const bodyA = tear ? a1 * (1 - sm(2.15, 2.6, t)) : a1; for (let j = 1; j < PH; j++) { g.put(tx, ty + j, "|", INK, bodyA); g.put(tx + 25, ty + j, "|", INK, bodyA); } const m = Math.round(PH * .3), lab = [[m, "F I R S T"], [m + 1, "P R I N T"], [Math.round(PH * .75), "5 cards"]]; lab.forEach(([j, str]) => { for (let i = 0; i < str.length; i++) g.put(tx + 13 - (str.length >> 1) + i, ty + j, str[i], INK, bodyA); }); for (let i = 0; i < 12; i++) g.put(tx + 7 + i, ty + Math.round(PH * .5), "░▒▓█▓▒░░▒▓█▓▒"[i], DIM, bodyA); crimp(ty + PH); }
          if (tear) { const CH = Math.round(11 * tall), tints = [[141, 137, 127], [141, 137, 127], [169, 201, 255], [255, 210, 122], [255, 138, 201]], arc = [[-22, 3], [-11, 1], [0, 0], [11, 1], [22, 3]], f = ease((t - 2.1) / .5);
            for (let c = 0; c < 5; c++) { const x0 = Math.round(cx - 4 + arc[c][0] * f), y0 = Math.round(cy - CH / 2 + arc[c][1] * tall * f + (1 - f) * 2), col = tints[c], al = a1 * sm(2.1, 2.25, t); box(x0, y0, 9, CH, col, al);
              for (let j = 1; j < CH - 1; j++) for (let i = 1; i < 8; i++) if (hash(i, j, c + 5) > .55) g.put(x0 + i, y0 + j, ".:+*"[Math.floor(hash(i, j, c) * 4)], col, al * .55); g.put(x0 + 4, y0 + (CH >> 1), c === 4 ? "*" : "o", col, al); } }
        }
        // 2.7 - 4.0: watch it move
        const a2 = vis(2.7, 4.1, .25); if (a2 > 0) {
          g.text(typed("2   watch the price move", t, 2.8, 22), .16, INK);
          const W = Math.min(56, C - 12), H = Math.round(14 * tall), pg = plotGrid(INTRO_SERIES, W, H), p = ease((t - 2.85) / 1.05), head = Math.floor(p * (W - 1)), x0 = cx - (W >> 1), y0 = cy - (H >> 1) - 1, v = INTRO_SERIES[Math.round(p * (INTRO_SERIES.length - 1))];
          for (let x = 0; x <= head; x++) for (let y = 0; y < H; y++) { const ch = pg.grid[y][x]; if (ch !== " ") g.put(x0 + x, y0 + y, ch, x > head - 3 ? [255, 255, 255] : GRN, a2); }
          const hy = y0 + (H - 1 - pg.Y[head]); g.put(x0 + head, hy, "●", [255, 255, 255], a2);
          const tag = "$" + (v / 100).toFixed(2), tw = tag.length + 4, tx = Math.min(Math.max(x0 + head - (tw >> 1), x0), x0 + W - tw), ty = Math.max(y0 - 3, hy - 4); box(tx, ty, tw, 3, GRN, a2); for (let i = 0; i < tag.length; i++) g.put(tx + 2 + i, ty + 1, tag[i], GRN, a2);
          g.text("▲ +" + Math.round((v / 10 - 1) * 100).toLocaleString("en-US") + "%", .75, GRN); g.text("every card trades all day", .81, DIM);
        }
        // 4.0 - 5.2: sell when you like
        const a3 = vis(4.0, 5.3, .22); if (a3 > 0) {
          g.text(typed("3   sell whenever you like", t, 4.05, 22), .16, INK);
          const press = t > 4.6, bx = cx - 12, by = cy - 2; box(bx, by, 25, 3, press ? GRN : INK, a3); const label = "sell  $1.66"; for (let i = 0; i < label.length; i++) g.put(bx + 7 + i, by + 1, label[i], press ? GRN : INK, a3);
          if (press) { g.text("+$1.49", .64, GRN); g.text("paid at once, minus 10%", .72, DIM); for (let i = 0; i < 46; i++) { const age = (t - 4.6 - hash(i, 1, 7) * .25), life = 1.2; if (age < 0 || age > life) continue; g.put(Math.round(cx + (hash(i, 2, 7) - .5) * 30), Math.round(by - age * 16 + 4 * Math.sin(i)), "$+*"[i % 3], GRN, a3 * (1 - age / life)); } }
        }
        // 5.2 - 6.2: the name again
        const a4 = sm(5.3, 5.7, t); if (a4 > 0) { logo(lx, ly, INK, a4); g.text("ASCII trading cards", .58, DIM); g.text("$10 of demo money to start", .64, GRN); g.text("tap to begin", .9, [90, 88, 84]); }
        g.flash(sm(5.95, 6.2, t) * .0);
      },
    },
    /* ORBIT (uncommon): a galaxy turns and comes closer. */
    orbit: {
      dur: 4.6, pals: [mkpal([[0, 0, 0], [10, 20, 60], [40, 90, 200], [150, 200, 255], [255, 255, 255]])],
      cell(x, y, t) {
        const z = 1.2 - .3 * ease(t / 4.6), px = x * z, py = y * z * 1.12, r = Math.hypot(px, py), th = Math.atan2(py, px), rot = t * .55;
        const arms = Math.pow(.5 + .5 * Math.cos(2 * (th - 11 * r - rot)), 3.2), dust = fbm(px * 5 + 3, py * 5, 4);
        let l = (arms * .85 + .15) * Math.exp(-r * 3.3) * (.55 + .8 * dust) + Math.exp(-r * 24) * 1.2;
        if (l < .08 && hash(Math.floor(x * 140), Math.floor(y * 140), 9) > .996) l = .3 + .2 * Math.sin(t * 5 + x * 90);
        return l * sm(0, .8, t);
      },
      over(g, t) { g.text(typed("already read the ending.", t, 2.4, 14), .84, [150, 200, 255]); g.flash(sm(4.0, 4.6, t)); },
    },
    /* NULL (rare): a star, the record of everything, swallowed whole. */
    null: {
      dur: 6.4, pals: [mkpal([[0, 0, 0], [8, 18, 50], [30, 80, 190], [140, 190, 255], [255, 255, 255]])],
      cell(x, y, t, g) {
        const p = ease2((t - 1.7) / 1.9), d = Math.hypot(x, y), ang = Math.atan2(y, x), sw = p * 2.4 / (d + .06), sx = x * Math.cos(sw) - y * Math.sin(sw), sy = x * Math.sin(sw) + y * Math.cos(sw);
        const col = Math.floor((sx + 1) * 60), row = Math.floor((sy + 1) * 52), fall = (t * 7 + hash(col, 3, 1) * 40) % 40;       // the record: columns of digits falling
        let l = hash(col, Math.floor(row + fall), 2) > .55 ? .22 + .22 * hash(col, row, 5) : 0; g.ch = null; if (l > 0) g.ch = hash(col, row, 6) > .5 ? "1" : "0";
        l *= 1 - sm(.35, 1.3, p * 1.6 - d * 1.2 + .2) * (t > 1.7 ? 1 : 0);                                                        // swallowed from the middle outwards
        const star = (.014 / (d / (1 - .92 * p) + .014)), spikes = (Math.exp(-Math.abs(y) * 120) * Math.exp(-Math.abs(x) * 5) + Math.exp(-Math.abs(x) * 120) * Math.exp(-Math.abs(y) * 5)) * .8;
        const rh = .02 + .06 * p, ring = Math.exp(-Math.pow((d - rh * 1.5) / .012, 2)) * (.5 + .5 * Math.cos(5 * ang - 18 * p - t * 6)) * sm(0, .3, p);
        let s = (star + spikes * (1 - p)) * (1 - sm(.9, 1, p) * .6) + ring; if (t < .5) s *= sm(0, .5, t);
        if (d < rh * .85 && p > 0) { g.ch = null; return 0; }
        if (s > l) { g.ch = null; return s; } return l * sm(0, .6, t);
      },
      over(g, t) { const s = "not on any record.", n = Math.max(0, Math.floor((t - 3.9) * 14)), e = Math.max(0, Math.floor((t - 5.2) * 12)); g.text(s.slice(0, Math.min(n, s.length)).slice(0, Math.max(0, s.length - e)), .5, [140, 190, 255]); g.flash(sm(6.0, 6.4, t) * .8); },
    },
    /* SHOGUN (rare): a figure raises its arms and two golden wings unfold, then beat twice. */
    shogun: {
      dur: 6.6, pals: [mkpal([[0, 0, 0], [70, 40, 0], [190, 130, 20], [255, 210, 110], [255, 250, 220]])],
      wing(f, u) { return (.8 - .4 * Math.pow(f, 1.1)) * (.25 + .75 * u); },                                                 // how long the feather at a place along the wing is
      cell(x, y, t) {
        const u = ease((t - .6) / 2.2), flap = .3 * Math.sin((t - 2.9) * 5.2) * sm(2.8, 3.4, t) * (1 - sm(5.4, 6.2, t)), ox = Math.abs(x), oy = y + .02, r = Math.hypot(ox, oy), phi = Math.atan2(-oy, ox);
        const aLow = mixv(1.5, -.2 + flap * .5, u), aHigh = mixv(1.62, 1.3 + flap, u); let l = Math.exp(-r * 4.5) * .32 * sm(0, 1, t);
        if (phi > aLow && phi < aHigh && r > .035) {
          const f = (phi - aLow) / (aHigh - aLow), L = SCENES.shogun.wing(1 - f, u), N = 13;
          if (r < L) { const lines = Math.pow(Math.abs(Math.sin(f * N * Math.PI)), 14), barb = .16 + .1 * Math.sin(r * 90 + f * 40); l = Math.max(l, (barb + .85 * lines) * Math.pow(1 - r / L, .5) * (.55 + .45 * sm(0, .6, u))); l = Math.max(l, Math.exp(-Math.pow((r - L) / .012, 2)) * .9 * lines); }
        }
        if (r < .05) l = Math.max(l, .6);
        if (hash(Math.floor(x * 70), Math.floor(y * 70), 4) > .994) l = Math.max(l, .35 + .35 * Math.sin(t * 6 + x * 50));
        return l;
      },
      over(g, t) {
        g.sprite(["  \\ | /  ", "   \\|/   ", "    o    ", "   /|\\   ", "    |    ", "   / \\   "], g.col(0) - 4, g.row(-.06) - 1, [255, 250, 220]);
        const u = ease((t - .6) / 2.2); if (u > .3) for (let i = 0; i < 70; i++) { const side = i % 2 ? 1 : -1, f = hash(i, 1, 6), phi = mixv(-.1, 1.3, f), Lr = SCENES.shogun.wing(1 - f, u) * (.9 + .15 * hash(i, 2, 6)), tw = .5 + .5 * Math.sin(t * 7 + i * 2.1); g.put(g.col(side * Lr * Math.cos(phi)), g.row(.02 - Lr * Math.sin(phi) * 1 + .1 * ((t * .6 + hash(i, 3, 6)) % 1)), "*+."[i % 3], [255, 210 + tw * 40, 110 + tw * 100], tw * .9); }
        g.text(typed("rents you the air.", t, 4.2, 13), .88, [255, 210, 110]); g.flash(Math.max(sm(.6, .7, t) * (1 - sm(.7, 1.2, t)) * .25, sm(5.9, 6.6, t)));
      },
    },
    /* RONIN (epic): the cliff, the wind, one cut that splits the night. */
    ronin: {
      dur: 7.6, pals: [mkpal([[0, 0, 0], [60, 14, 44], [150, 48, 110], [255, 138, 201], [255, 232, 246]])],
      ridge: (x, t, i) => [.12, .21, .34][i] + [.05, .06, .03][i] * (fbm((x + (i < 2 ? t * [.012, .02][i] : 0)) * [2.2, 2.6, 1.7][i] + i * 9, i, 20 + i) - .5) * 2 - (i === 2 ? .05 * sm(-.55, -.15, x) : 0),
      cell(x, y, t) {
        const P = [-.12, SCENES.ronin.ridge(-.12, 0, 2) - .06], cutAmt = sm(3.4, 3.5, t) * (1 - sm(3.5, 4.6, t)), side = (x - P[0]) + .55 * (y - P[1]), xo = x + Math.sign(side) * .05 * cutAmt;
        let l = 0; const md = Math.hypot(xo - .22, y + .27), pulse = 1 + .35 * sm(2.2, 3.4, t) * Math.sin(t * 9);
        if (md < .09) l = .95 - .2 * fbm(xo * 40, y * 40, 3); else if (md < .3) l = Math.exp(-(md - .09) * 11) * .4 * pulse;
        if (l < .1 && hash(Math.floor(xo * 90), Math.floor(y * 90), 8) > .993) l = .55 + .3 * Math.sin(t * 4 + x * 77);
        const wind = hash(Math.floor((xo + t * (1.4 + 1.8 * sm(2, 3.4, t))) * 28), Math.floor(y * 24), 6); if (l < .1 && wind > .983) l = Math.max(l, .3);
        for (let i = 0; i < 3; i++) { const r = SCENES.ronin.ridge(xo, t, i); if (y > r) l = [.26, .4, .1][i] + (i < 2 ? .12 * fbm(xo * 20, y * 20, 30 + i) : .03 * hash(Math.floor(xo * 50), Math.floor(y * 50), 7)) + (y - r < .012 ? .35 : 0); }
        const mist = fbm(xo * 3 + t * .06, y * 9, 40) * sm(.05, .3, y) * (1 - sm(.3, .5, y)); l = Math.max(l, mist * .3);
        const sl = sm(3.4, 3.43, t) * (1 - sm(3.5, 5.0, t)); if (sl > 0) { const d = side / 1.14; if (Math.abs(d) < .004 + .03 * (1 - sm(3.45, 4.2, t)) + .003 && Math.hypot(x - P[0], y - P[1]) < .2 + 2 * sm(3.4, 3.52, t)) l = Math.max(l, sl * (.55 + .45 * Math.exp(-Math.abs(d) * 90))); }
        return l * sm(0, .7, t);
      },
      over(g, t) {
        const P = [-.12, SCENES.ronin.ridge(-.12, 0, 2) - .06], c = g.col(P[0]) - 3, rw = g.row(SCENES.ronin.ridge(-.12, 0, 2)) - 5;
        g.sprite(t < 2.7 ? FIG : t < 3.4 ? ["  _o_ /", " / | / ", "   |/  ", "  / \\  ", " /   \\ "] : ["  _o_   ", " /_|_===", "   |    ", "  / \\   ", " /   \\  "], c, rw, [255, 232, 246]);
        for (let i = 0; i < 70; i++) { const sp = .1 + .16 * hash(i, 1, 2), px = (((hash(i, 2, 2) + 2 - t * sp * .5) % 1) - .5) * g.asp, py = ((hash(i, 3, 2) + t * sp * .35) % 1) * 1.1 - .55, side = Math.sign((px - P[0]) + .55 * (py - P[1])), cut = t > 3.4 ? sm(3.4, 3.6, t) * (1 - sm(3.6, 5.6, t)) : 0; g.put(g.col(px + .06 * side * cut), g.row(py), "*`'."[i % 4], [255, 138, 201], .85); }
        g.text(typed("no master. no map.", t, 4.9, 13), .88, [255, 138, 201]); g.flash(Math.max(sm(3.4, 3.44, t) * (1 - sm(3.44, 3.9, t)) * .75, sm(6.9, 7.6, t)));
      },
    },
    /* GRIMM (legendary): down the nave toward the rose window. The bell tolls twice. */
    grimm: {
      dur: 7.6, pals: [mkpal([[0, 0, 0], [10, 60, 42], [60, 170, 120], [168, 255, 176], [240, 255, 240]]), mkpal([[0, 0, 0], [100, 70, 10], [240, 180, 50], [255, 228, 140], [255, 250, 232]]), mkpal([[0, 0, 0], [100, 24, 56], [240, 80, 140], [255, 160, 200], [255, 238, 246]]), mkpal([[0, 0, 0], [12, 46, 110], [60, 130, 240], [150, 210, 255], [240, 250, 255]])],
      cell(x, y, t, g) {
        const dy = y + .03, r = Math.hypot(x, dy), th = Math.atan2(dy, x), cam = t * .45, rp = Math.pow(Math.pow(Math.abs(x) * 1.5, 1.5) + Math.pow(Math.abs(dy) * .8, 1.5), 1 / 1.5); let l = 0; g.pi = 0;   // rp: a pointed arch shape, narrower than it is tall
        const z = Math.log(rp + .0001) + cam, ring = Math.abs(((z * 1.5) % 1 + 1) % 1 - .5); if (ring > .45) l = Math.max(l, .8 * sm(.06, .3, r));                  // the arches go by
        if (Math.abs(Math.sin(th * 12)) < .06 && r > .14) l = Math.max(l, .62 * sm(.12, .5, r));                                                              // the columns
        if (dy > .02) { const fl = Math.abs(Math.sin(x / (dy + .02) * 3.2)); if (fl < .08) l = Math.max(l, .4); }
        const win = .12 + .012 * Math.sin(t * 2);
        if (r < win) { const pet = .5 + .5 * Math.cos(12 * th + t * .8), ring2 = .55 + .45 * Math.cos(r * 100); l = Math.max(.5, (.35 + .65 * pet) * ring2); g.pi = 1 + (Math.floor(((th / 6.2832 + 1) % 1) * 6 + Math.floor(t * 2)) % 3); }
        else { l = Math.max(l, Math.pow(fbm(th * 7, r * 4 - t * .2, 12), 2) * Math.exp(-r * 2.4) * .6 * sm(.12, .3, r)); if (l < .3 && r < .4) { const bloom = Math.exp(-(r - win) * 12) * .45; if (bloom > l) { l = bloom; g.pi = 1; } } }
        for (const b of [4.3, 5.5]) { const w = (t - b) * .95; if (w > 0 && w < 1.4) { const rg = Math.exp(-Math.pow((r - w) / .035, 2)) * (1 - w / 1.4); if (rg > l) { l = rg; g.pi = 1; } } }
        return l * sm(0, .8, t);
      },
      over(g, t) {
        for (let i = 0; i < 40; i++) { const px = (hash(i, 1, 4) - .5) * g.asp, py = ((hash(i, 2, 4) - t * .03 * (1 + hash(i, 3, 4))) % 1 + 1) % 1 - .5; g.put(g.col(px), g.row(py), ".*"[i % 2], [255, 228, 140], .25 + .3 * Math.sin(t * 2 + i)); }
        g.text(typed("the walls remember.", t, 5.8, 14), .88, [168, 255, 176]); g.flash(Math.max(sm(4.3, 4.35, t) * (1 - sm(4.35, 4.8, t)) * .4, sm(5.5, 5.55, t) * (1 - sm(5.55, 6, t)) * .35, sm(6.9, 7.6, t)));
      },
    },
    /* REAPER (mythic): a wall of embers, one slash, and the night splits open along it. */
    reaper: {
      dur: 7.8, pals: [mkpal([[0, 0, 0], [70, 8, 0], [200, 50, 8], [255, 150, 40], [255, 240, 190]])],
      cell(x, y, t) {
        const cut = sm(3.0, 3.08, t) * (1 - sm(3.08, 3.9, t)), xo = x + (y < 0 ? .06 : -.06) * cut + .004 * Math.sin(t * 60) * cut; let l = 0;
        const fl = Math.pow(fbm(xo * 3.5, y * 3 - t * 1.1, 50), 1.6) * sm(.08, .55, y) * (1.15 + .5 * sm(3, 3.6, t)); l = Math.max(l, fl);                          // a wall of fire along the bottom
        l = Math.max(l, Math.pow(fbm(xo * 3 + 2, y * 2 + t * .5, 3), 3) * .5 * sm(-.3, .5, y));                                                                  // smoke
        const dy = y - .12, d = Math.hypot(xo, dy), a = Math.atan2(dy, xo), s = ease((t - 1.9) / 1.1), head = mixv(-2.9, -.05, s);                                  // the slash
        if (t > 1.9 && a < head && a > head - 2.2) { const tr = Math.exp(-(head - a) * 1.5), w = .02 + .06 * tr; l = Math.max(l, Math.exp(-Math.pow((d - .46) / w, 2)) * (.35 + .65 * tr) * (1 - sm(3.5, 5, t) * .85)); }
        if (t > 3) { const crack = Math.exp(-Math.pow((y - .035 * Math.sin(xo * 16 + 1)) / (.007 + .01 * (1 - sm(3, 3.3, t))), 2)); l = Math.max(l, crack * (.55 + .45 * Math.sin(t * 9 + xo * 12)) * (1 - sm(5.5, 6.8, t) * .5)); }
        return l * sm(0, .6, t);
      },
      over(g, t) {
        const burst = 1 + 3 * sm(3.0, 3.1, t) * (1 - sm(3.1, 4.4, t));
        for (let i = 0; i < 260; i++) { const sp = (.1 + .3 * hash(i, 1, 3)) * burst, ph = hash(i, 2, 3), life = (t * sp + ph) % 1.15, k = hash(i, 5, 3), fromCrack = t > 3.2 && i % 3 === 0, px = (hash(i, 4, 3) - .5) * g.asp * (fromCrack ? 1 : 1) + .05 * Math.sin(t * 2 + i), py = fromCrack ? .02 - life * .6 : .62 - life * 1.2;
          g.put(g.col(px), g.row(py), k > .75 ? "*" : k > .4 ? "+" : "'", k > .85 ? [255, 235, 180] : [255, 110 + k * 90, 28], .3 + .7 * (1 - life / 1.15)); }
        g.text(typed("still warm.", t, 4.9, 11), .88, [255, 150, 40]); g.flash(Math.max(sm(3.0, 3.05, t) * (1 - sm(3.05, 3.6, t)) * .85, sm(7.0, 7.8, t)));
      },
    },
    /* UMBRA (secret): the sun, the moon, the corona, one figure on a cliff. */
    umbra: {
      dur: 10.4, pals: [mkpal([[0, 0, 0], [70, 30, 6], [190, 100, 20], [255, 190, 70], [255, 245, 210]])],
      ridge: x => .31 + .03 * Math.sin(x * 5 + 1) + .06 * (fbm(x * 2.2 + 3, 1, 7) - .5) - .04 * Math.exp(-x * x * 60),
      cell(x, y, t) {
        const R = .165, sy = -.1, mp = ease2((t - 1.6) / 4.4), mx = -.62 + .62 * mp, Rm = .171, d = Math.hypot(x, y - sy), md = Math.hypot(x - mx, y - sy), cov = 1 - sm(0, R + Rm, Math.abs(mx));
        const ang = Math.atan2(y - sy, x); let l = 0;
        if (md < Rm) l = 0;
        else if (d < R) l = .8 + .2 * fbm(x * 24, y * 24 + t, 5);
        else { const rays = .45 + .55 * fbm(ang * 3.2 + t * .12, d * 7, 11); l = Math.exp(-(d - R) * 6.5) * rays * (.12 + 1.15 * cov * cov * cov); }
        const gl = Math.exp(-Math.pow(Math.hypot(x - R * .98, y - sy) / .016, 2)) * sm(.9, .96, cov) * (1 - sm(.975, .995, cov)); l = Math.max(l, gl * 1.3);
        if (l < .1 && hash(Math.floor(x * 120), Math.floor(y * 120), 2) > .993) l = Math.max(l, cov * (.4 + .4 * Math.sin(t * 3 + x * 60)));
        { const rd = SCENES.umbra.ridge(x); if (y > rd) l = .1 + .07 * vn(x * 60, y * 60, 3) + .5 * Math.exp(-(y - rd) * 160); }
        return l * sm(0, .9, t);
      },
      over(g, t) {
        const r = SCENES.umbra.ridge(0); g.sprite(FIG, g.col(0) - 3, g.row(r) - 5, [236, 231, 220]);
        g.text(typed("the sun blinked first.", t, 6.6, 12), .22, [255, 190, 70]);
        g.flash(Math.max(sm(5.55, 5.6, t) * (1 - sm(5.6, 6.1, t)) * .5, sm(9.4, 10.4, t)));
      },
    },
  };

  const has = id => !!SCENES[id];
  let busy = false, stopLive = null;

  function play(id, o) {
    const sc = SCENES[id]; if (!sc || busy || reduced) return Promise.resolve();
    busy = true; return new Promise(res => {
      const wrap = $("cut"), cv = $("cutCv"), ctx = cv.getContext("2d"), dpr = Math.min(2, devicePixelRatio || 1);
      wrap.hidden = false; wrap.style.opacity = 1; const W = wrap.clientWidth, H = wrap.clientHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const fs = Math.max(9, Math.min(17, W / 56)) * (sc.fsMul || 1); ctx.font = `700 ${fs}px ${FONT}`; const cw = ctx.measureText("M").width, lh = fs * 1.12, C = Math.floor(W / cw), Rr = Math.floor(H / lh);
      const zoom = Math.min(1, W / H), px = Array.from({ length: C }, (_, x) => ((x + .5) * cw - W / 2) / (H * zoom)), py = Array.from({ length: Rr }, (_, y) => ((y + .5) * lh - H / 2) / (H * zoom));   // scenes are drawn on a square that always fits the screen
      const ov = [], tx = [], g = { W, H, C, R: Rr, pi: 0, ch: null,
        col: ux => Math.round((ux * H * zoom + W / 2) / cw - .5), row: uy => Math.round((uy * H * zoom + H / 2) / lh - .5), asp: W / H / zoom,
        put: (x, y, ch, c, a) => ov.push([x, y, ch, c, a == null ? 1 : a]),
        sprite: (lines, x, y, c) => lines.forEach((s, j) => { for (let i = 0; i < s.length; i++) if (s[i] !== " ") ov.push([x + i, y + j, s[i], c, 1]); }),
        text: (str, fy, c) => tx.push([str, fy, c]),
        flash: a => { g._f = Math.max(g._f || 0, a); } };
      let t0 = performance.now(), raf = 0, ended = false; stopLive = () => { ended = true; cancelAnimationFrame(raf); document.removeEventListener("keydown", onKey, true); };
      const finish = () => { if (ended) return; ended = true; cancelAnimationFrame(raf); document.removeEventListener("keydown", onKey, true); wrap.style.opacity = 0; setTimeout(() => { wrap.hidden = true; busy = false; res(); }, 260); };
      const onKey = e => { if (e.key === "Escape" || e.key === " " || e.key === "Enter") { e.preventDefault(); e.stopPropagation(); skip(); } };
      const skip = () => { t0 = performance.now() - sc.dur * 1000 + 220; }; wrap.onclick = e => { e.stopPropagation(); skip(); }; document.addEventListener("keydown", onKey, true);
      const render = t => {
        ctx.fillStyle = "#030304"; ctx.fillRect(0, 0, W, H); ctx.font = `700 ${fs}px ${FONT}`; ctx.textBaseline = "top"; ov.length = 0; tx.length = 0; g._f = 0;
        const pal0 = sc.pals[0]; let last = "";
        for (let y = 0; y < Rr; y++) for (let x = 0; x < C; x++) {
          g.pi = 0; g.ch = null; const l = sc.cell(px[x], py[y], t, g); if (l < .035) { if (g.ch === null) continue; }
          const k = Math.min(31, Math.max(0, Math.round(l * 31))), style = sc.pals[g.pi][k]; if (style !== last) { ctx.fillStyle = style; last = style; }
          ctx.fillText(g.ch || RAMP[Math.min(RAMP.length - 1, Math.floor(l * RAMP.length))], x * cw, y * lh);
        }
        sc.over(g, t);
        for (const [x, y, ch, c, a] of ov) { if (x < 0 || y < 0 || x >= C || y >= Rr) continue; ctx.globalAlpha = a; ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; ctx.fillText(ch, x * cw, y * lh); } ctx.globalAlpha = 1;
        { const big = Math.max(15, Math.min(30, W / 24)); ctx.font = `700 ${big}px ${FONT}`; ctx.textAlign = "center"; for (const [str, fy, c] of tx) { ctx.shadowColor = `rgb(${c[0]},${c[1]},${c[2]})`; ctx.shadowBlur = 14; ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; ctx.fillText(str, W / 2, H * fy); } ctx.shadowBlur = 0; ctx.textAlign = "left"; ctx.font = `700 ${fs}px ${FONT}`; }
        if (g._f > .003) { ctx.fillStyle = `rgba(255,255,255,${Math.min(1, g._f)})`; ctx.fillRect(0, 0, W, H); }
      };
      const frame = now => { const t = (now - t0) / 1000; render(t); if (t >= sc.dur) { finish(); return; } raf = requestAnimationFrame(frame); };
      if (o && o.freeze != null) { render(o.freeze); res(); return; }
      raf = requestAnimationFrame(frame);
    });
  }
  // the film that explains the app plays once, for someone who has not opened a pack yet
  const maybeIntro = () => { if (!state.seenIntro && !state.s.packs && !state.vault.length && !busy) { state.seenIntro = true; save(); play("intro"); } };
  const close = () => { if (stopLive) stopLive(); stopLive = null; $("cut").hidden = true; busy = false; };
  return { has, play, close, maybeIntro, ids: Object.keys(SCENES), dur: id => SCENES[id].dur };
})();
