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
  // a picture read into characters: its brightness at `cols` by `rows` points
  function sampleImage(img, cols, rows) { const c = document.createElement("canvas"); c.width = cols; c.height = rows; const x = c.getContext("2d"); x.drawImage(img, 0, 0, cols, rows); const d = x.getImageData(0, 0, cols, rows).data, l = new Float32Array(cols * rows); for (let i = 0; i < cols * rows; i++) l[i] = Math.pow(cl(((d[i * 4] * .299 + d[i * 4 + 1] * .587 + d[i * 4 + 2] * .114) / 255 - .03) * 2.6), .7); return { cols, rows, l }; }
  const mkpal = stops => Array.from({ length: 32 }, (_, i) => { const k = i / 31 * (stops.length - 1), j = Math.min(stops.length - 2, Math.floor(k)), f = k - j, a = stops[j], b = stops[j + 1]; return `rgb(${Math.round(mixv(a[0], b[0], f))},${Math.round(mixv(a[1], b[1], f))},${Math.round(mixv(a[2], b[2], f))})`; });

  /* ---- the scenes. cell(x, y, t, g) gives the brightness (0 to 1) of the character at that spot: x and y are in screen-height units, 0,0 in the middle,
          y pointing down, so a circle with radius .2 is a circle. It may set g.pi to choose a palette, g.ch to force a character.
          over(g, t) draws what is not a formula: a figure, a line of type, a flash. */
  const FIG = ["  _o_  ", " / | \\ ", "   |   ", "  / \\  ", " /   \\ "];
  const INTRO_SERIES = (() => { const a = [10, 11, 9.5, 12, 10.5, 14, 13, 24, 70, 150, 184], n = 80, out = []; for (let i = 0; i < n; i++) { const f = i / (n - 1) * (a.length - 1), j = Math.min(a.length - 2, Math.floor(f)), k = f - j, e = k * k * (3 - 2 * k); out.push(Math.exp(mixv(Math.log(a[j]), Math.log(a[j + 1]), e) + (hash(i, 3, 9) - .5) * .06)); } return out; })();   // a price that wobbles and then runs, for the intro
  const SCENES = {
    /* INTRO: what the app is, in about twenty seconds, slow enough to read. A logo, a foil pack that tears open onto five real cards drawn in ASCII,
       the AI trading bots that move every price, and a sale that pays out. */
    intro: {
      dur: 24.8, fsMul: 1.6, pals: [mkpal([[0, 0, 0], [30, 30, 32], [120, 118, 110], [200, 195, 185], [236, 231, 220]])],
      cards: null,
      prep() {   // the five cards on the screen are the app's own pictures, read into characters
        const ids = ["stitch", "phantom", "null", "ronin", "grimm"], tints = [[200, 196, 186], [236, 231, 220], [169, 201, 255], [255, 138, 201], [168, 255, 176]], names = ["STITCH", "PHANTOM", "NULL", "RONIN", "GRIMM"], rars = ["common", "uncommon", "rare", "epic", "legendary"];
        return Promise.all(ids.map(id => loadImg(imgOf(BY_ID[id], "")))).then(imgs => { this.cards = imgs.map((im, k) => ({ id: ids[k], tint: tints[k], name: names[k], rar: rars[k], im, grids: {} })); });
      },
      cell: () => 0,
      over(g, t) {
        const C = g.C, R = g.R, cx = C >> 1, cy = R >> 1, INK = [236, 231, 220], GRN = [159, 216, 166], RED = [232, 120, 109], DIM = [141, 137, 127], FAINT = [74, 74, 82], DARK = [5, 5, 6];
        const vis = (a, b, f) => { f = f || .35; return sm(a, a + f, t) * (1 - sm(b - f, b, t)); };
        const big = R > C * .95, rowsH = big ? 1.25 : 1;
        // a dim field of stars behind everything
        for (let i = 0; i < 70; i++) { const x = Math.floor(hash(i, 1, 40) * C), y = Math.floor(hash(i, 2, 40) * R), tw = .5 + .5 * Math.sin(t * 1.6 + i * 3.1); g.put(x, y, i % 5 ? "." : "+", FAINT, .25 + .3 * tw); }
        const LOGO = ["███████╗████████╗██╗██╗  ██╗██╗  ██╗", "██╔════╝╚══██╔══╝██║╚██╗██╔╝╚██╗██╔╝", "███████╗   ██║   ██║ ╚███╔╝  ╚███╔╝ ", "╚════██║   ██║   ██║ ██╔██╗  ██╔██╗ ", "███████║   ██║   ██║██╔╝ ██╗██╔╝ ██╗", "╚══════╝   ╚═╝   ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝"];
        const logo = (x0, y0, al, rev, shine) => {
          LOGO.forEach((s, j) => { for (let i = 0; i < s.length; i++) { const ch = s[i]; if (ch === " ") continue; const k = rev * 1.6 - hash(i, j, 3) * .7 - i * .004; if (k <= 0) continue; const sh = shine != null ? Math.max(0, 1 - Math.abs(i + j * 2 - shine) / 4) : 0;
            g.put(x0 + i, y0 + j, k < .3 ? ".:*#"[(i + j + Math.floor(t * 18)) % 4] : ch, sh > .1 ? [255, 255, 255] : ch === "█" ? INK : [150, 146, 136], al * (k < .3 ? .5 : 1)); } });
        };
        const cursor = (x, y, al) => g.art(["█▙   ", "███▙  ", "████▙ ", "█████▙", "███▛▀ ", "█▛ ▜▙ ", "▀   ▜▙"].map(s => s.trimEnd()), x, y, [255, 255, 255], al);
        const robots = [[" .---. ", "( o o )", " \\ ~ / ", ".-|=|-.", "d |_| b"], [" .---. ", "( ! ! )", " \\ O / ", ".-|=|-.", "d |_| b"], [" .---. ", "( + + )", " \\ - / ", ".-|=|-.", "d |_| b"]];

        // ---------- 1. the name (0 - 4.4)
        const a1 = vis(-.4, 4.9, .5); if (a1 > 0) {
          const lx = cx - 18, ly = cy - 4; logo(lx, ly, a1, ease(t / 1.8), t > .7 && t < 2.6 ? (t - .7) / 1.9 * 52 - 6 : null);
          for (let i = 0; i < 36; i++) g.put(lx + i, ly + 7, "═", FAINT, a1 * sm(1.6, 2.2, t));
          g.text(typed("trading cards made of text.", t, 1.5, 12), .66, DIM);
        }
        // ---------- 2. open a pack (4.4 - 10.6)
        const a2 = vis(4.7, 10.9, .4); if (a2 > 0) {
          g.text(typed("1   open a pack", t, 4.7, 10), .09, INK);
          const PH = 19, px0 = cx - 17, k = ease((t - 4.6) / .8), sway = t > 5.4 && t < 7.0 ? Math.round(Math.sin(t * 2.6)) : 0, py0 = cy - 9 + Math.round((1 - k) * -14) + (t > 5.4 ? Math.round(Math.sin(t * 3) * .5) : 0), clickAt = 7.2, torn = t > clickAt;
          const IW = 34, ctr = str => { const l = Math.floor((IW - str.length) / 2); return "|" + " ".repeat(l) + str + " ".repeat(IW - str.length - l) + "|"; }, plate = "┌" + "─".repeat(22) + "┐", plateB = "└" + "─".repeat(22) + "┘", sh = Math.sin(t * 3) * .5 + .5;
          const emblem = Array.from({ length: 9 }, (_, j) => Array.from({ length: 23 }, (_, i) => { const dx = (i - 11) / 11, dy = (j - 4) / 4, d = Math.hypot(dx, dy) + .05 * Math.sin(t * 2 + i * .7 + j); return d < .3 ? "#" : d < .5 ? "*" : d < .68 ? ":" : d < .84 ? "." : d < .95 ? (j === 4 || i === 11 ? "+" : "'") : " "; }).join(""));
          const body = [" " + "/\\".repeat(17) + " ", ctr(""), ctr(plate), ctr("│      F I R S T       │"), ctr("│      P R I N T       │"), ctr(plateB), ctr(""), ...emblem.map(ctr), ctr(""), ctr("5   C A R D S"), " " + "\\/".repeat(17) + " "];
          const tearK = torn ? ease((t - clickAt) / .9) : 0, shown = torn ? Math.max(0, 1 - sm(clickAt + .1, clickAt + .8, t)) : 1;
          body.forEach((s, j) => { const top = j < 3, dx = torn && top ? Math.round(tearK * 10) : 0, dy = torn && top ? -Math.round(tearK * 12) : 0, al = a2 * (top && torn ? 1 - sm(clickAt + .3, clickAt + 1.4, t) : shown); if (al <= 0) return; for (let i = 0; i < s.length; i++) { if (s[i] === " ") continue; const hot = j > 1 && j < 6 ? INK : j > 6 && j < 15 ? [200, 195, 185] : INK; g.put(px0 + i + sway + dx, py0 + j + dy, s[i], s[i] === "*" || s[i] === "#" ? [255, 210, 122] : hot, al); } });
          // the pointer comes in, clicks the top, and the pack rips
          if (t > 6.0 && t < clickAt + 1.0) { const m = ease((t - 6.0) / 1.0), cxp = Math.round(mixv(cx + 18, cx + 1, m)), cyp = Math.round(mixv(cy + 8, py0 - 1, m)), press = t > clickAt - .15 && t < clickAt + .1; cursor(cxp + (press ? 1 : 0), cyp + (press ? 1 : 0), a2 * (1 - sm(clickAt + .6, clickAt + 1.0, t))); }
          if (t > clickAt && t < clickAt + 1.7) { if (Math.floor(t * 14) % 2 || t > clickAt + .5) g.text("R I P !", .5, [255, 255, 255]); for (let i = 0; i < 40; i++) { const age = t - clickAt - hash(i, 1, 41) * .2, life = 1.1; if (age < 0 || age > life) continue; const ang = hash(i, 2, 41) * 6.283, sp = 8 + 16 * hash(i, 3, 41); g.put(Math.round(cx + Math.cos(ang) * sp * age * 1.6), Math.round(cy - 6 + Math.sin(ang) * sp * age * .8), "*+.'"[i % 4], [255, 225, 160], a2 * (1 - age / life)); } }
          // real cards, as ASCII, rise out of the pack and fan: five on a wide screen, three on a narrow one
          if (t > clickAt + .4 && this.cards) {
            const n = C >= 118 ? 5 : 3, CW = C >= 100 ? 28 : C >= 72 ? 24 : 15, CH = Math.round(CW * .62), pick = n === 5 ? [0, 1, 2, 3, 4] : [1, 2, 3], f = ease((t - clickAt - .4) / 1.2), gap = CW + 3;
            pick.forEach((ci, c) => { const cd = this.cards[ci], gr = cd.grids[CW] || (cd.grids[CW] = cd.im ? sampleImage(cd.im, CW, CH) : null), mid = (n - 1) / 2, x0 = Math.round(cx - CW / 2 + (c - mid) * gap * f), y0 = Math.round(cy - CH / 2 - 1 + Math.abs(c - mid) * 1.2 * f * rowsH + (1 - f) * 7), al = a2 * sm(clickAt + .4, clickAt + 1.0, t);
              if (gr) g.img(gr, x0, y0, cd.tint, al, cl((t - clickAt - .6 - c * .18) / 1.6)); g.frame(x0 - 1, y0 - 1, CW + 2, CH + 2, cd.tint, al * .85);
              g.art([typed(cd.name, t, clickAt + 2.6 + c * .3, 8)], x0 + (CW >> 1) - (cd.name.length >> 1), y0 + CH + 1, INK, al); g.art([typed(cd.rar, t, clickAt + 2.9 + c * .3, 8)], x0 + (CW >> 1) - (cd.rar.length >> 1), y0 + CH + 2, cd.tint, al * .9); });
          }
          g.text(typed("every pack holds five cards.", t, 8.6, 11), .91, DIM);
        }
        // ---------- 3. prices move (10.6 - 15.8)
        const a3 = vis(10.7, 16.3, .4); if (a3 > 0) {
          g.text(typed("2   prices move all day", t, 10.8, 10), .09, INK);
          const W = Math.min(54, C - 6), H = big ? 14 : 10, pg = plotGrid(INTRO_SERIES, W, H, [INTRO_SERIES[0]]), p = ease2((t - 11.6) / 3.0), head = Math.floor(p * (W - 1)), x0 = cx - (W >> 1), by0 = Math.max(4, cy - 11 - (big ? 5 : 0)), y0 = by0 + 9, v = INTRO_SERIES[Math.round(p * (INTRO_SERIES.length - 1))];
          // the bots
          const say = [["bought $212K", GRN], ["sold $49K", RED], ["bought $1.2M", GRN]], names = ["DegenBot-12", "FomoBot-7", "WhaleBot-3"], si = Math.max(0, Math.floor((t - 11.8) / 1.5));
          robots.forEach((rb, b) => { const bx = cx - 24 + b * 17, by = by0, bob = Math.round(Math.sin(t * 3 + b * 2) * .5); g.art(rb, bx, by + bob, [200, 195, 185], a3, cl((t - 10.9 - b * .2) / .8)); const [msg, col] = say[(si + b) % 3]; if (t > 11.6) g.art([names[b]], bx - 2, by + 6, DIM, a3); if (t > 12.0) { const m = typed(msg, t, 11.9 + si * 1.5 + b * .25, 16); g.art([m], bx - 2, by + 7, col, a3 * .95); } });
          for (let x = 0; x <= head; x++) for (let y = 0; y < H; y++) { const ch = pg.grid[y][x]; if (ch !== " ") g.put(x0 + x, y0 + y, ch, x > head - 3 ? [255, 255, 255] : GRN, a3); }
          g.put(x0, y0 + (H - 1 - pg.Y[0]) + 0, "◆", INK, a3 * sm(11.6, 12, t)); if (t > 11.9) g.art(["you got it: $0.10"], x0, y0 + H + 1, DIM, a3);
          const hy = y0 + (H - 1 - pg.Y[head]); g.art(["  /\\  ", " /__\\ ", "  ||  "], x0 + head - 2, hy - 3 + Math.round(Math.sin(t * 8) * .5), [255, 210, 122], a3 * sm(11.7, 12, t));
          const tag = "$" + (v / 100).toFixed(2), tw = tag.length + 4, tx = Math.max(x0, x0 + head - tw - 4), ty = Math.min(Math.max(hy - 1, y0), y0 + H - 3); g.frame(tx, ty, tw, 3, GRN, a3); g.art([tag], tx + 2, ty + 1, GRN, a3);
          g.text("▲ +" + Math.round((v / 10 - 1) * 100).toLocaleString("en-US") + "%", .80, GRN);
          g.text(typed("AI trading bots buy and sell", t, 11.4, 13), .875, DIM); g.text(typed("every card, all day long.", t, 12.9, 13), .93, DIM);
        }
        // ---------- 4. sell (16.0 - 20.6)
        const a4 = vis(16.1, 21.0, .4); if (a4 > 0) {
          g.text(typed("3   sell whenever you like", t, 16.2, 10), .09, INK);
          const bx = cx - 14, by = cy - 4, clickAt = 18.6, press = t > clickAt;
          const rows = ["╔════════════════════════╗", "║                        ║", "╚════════════════════════╝"]; const lab = "S E L L    $ 1 . 6 6";
          if (press) for (let j = 0; j < 3; j++) for (let i = 0; i < 26; i++) g.put(bx + i, by + j, "█", GRN, a4 * (.9 - .5 * sm(clickAt + .6, clickAt + 1.4, t)));
          rows.forEach((s, j) => { for (let i = 0; i < s.length; i++) g.put(bx + i, by + j, s[i], press ? DARK : INK, a4 * sm(16.8, 17.3, t)); }); for (let i = 0; i < lab.length; i++) g.put(bx + 4 + i, by + 1, lab[i], press ? DARK : INK, a4 * sm(16.8, 17.3, t));
          if (t > 17.4 && t < clickAt + .5) { const m = ease((t - 17.4) / 1.1), cxp = Math.round(mixv(cx + 22, bx + 18, m)), cyp = Math.round(mixv(cy + 10, by + 1, m)), pr = t > clickAt - .12 && t < clickAt + .1; cursor(cxp + (pr ? 1 : 0), cyp + (pr ? 1 : 0), a4 * (1 - sm(clickAt + .2, clickAt + .5, t))); }
          if (press) {
            for (let i = 0; i < 36; i++) { const age = t - clickAt - hash(i, 1, 43) * .5, life = 1.8; if (age < 0 || age > life) continue; const x = Math.round(cx + (hash(i, 2, 43) - .5) * 40), y = Math.round(by - 4 + age * age * 10 + age * 3), bounce = y > cy + 10 ? cy + 10 - (y - cy - 10) * .4 : y; g.art(["(\\$)"], x, Math.round(bounce), [255, 210, 122], a4 * (1 - age / life)); }
            g.text("+$1.66", .70, GRN); g.text(typed("paid at once: the price minus 10%.", t, clickAt + .9, 14), .78, DIM); g.text(typed("you got it for $0.10.", t, clickAt + 2.0, 14), .84, GRN);
          } else g.text("a card is worth what the market says.", .74, DIM);
        }
        // ---------- 5. the name again (20.6 - 21.4+)
        const a5 = sm(20.9, 21.4, t); if (a5 > 0) { logo(cx - 18, cy - 5, a5, 1, t > 21.4 ? (t - 21.4) * 40 : null); g.text("ASCII trading cards", .58, DIM); g.text("$10 of demo money to start", .65, GRN); if (Math.floor(t * 2) % 2) g.text("tap to begin", .9, [110, 108, 100]); }
      },
    },
    /* ORBIT (uncommon): a galaxy turns and comes closer. */
    orbit: {
      dur: 5.8, pals: [mkpal([[0, 0, 0], [10, 20, 60], [40, 90, 200], [150, 200, 255], [255, 255, 255]])],
      cell(x, y, t) {
        const z = 1.2 - .3 * ease(t / 4.6), px = x * z, py = y * z * 1.12, r = Math.hypot(px, py), th = Math.atan2(py, px), rot = t * .55;
        const arms = Math.pow(.5 + .5 * Math.cos(2 * (th - 11 * r - rot)), 3.2), dust = fbm(px * 5 + 3, py * 5, 4);
        let l = (arms * .85 + .15) * Math.exp(-r * 3.3) * (.55 + .8 * dust) + Math.exp(-r * 24) * 1.2;
        if (l < .08 && hash(Math.floor(x * 140), Math.floor(y * 140), 9) > .996) l = .3 + .2 * Math.sin(t * 5 + x * 90);
        return l * sm(0, .8, t);
      },
      over(g, t) { g.text(typed("already read the ending.", t, 2.4, 14), .84, [150, 200, 255]); g.flash(sm(5.2, 5.8, t)); },
    },
    /* NULL (rare): a star, the record of everything, swallowed whole. */
    null: {
      dur: 7.8, pals: [mkpal([[0, 0, 0], [8, 18, 50], [30, 80, 190], [140, 190, 255], [255, 255, 255]])],
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
      over(g, t) { const s = "not on any record.", n = Math.max(0, Math.floor((t - 3.9) * 10)), e = Math.max(0, Math.floor((t - 6.4) * 9)); g.text(s.slice(0, Math.min(n, s.length)).slice(0, Math.max(0, s.length - e)), .5, [140, 190, 255]); g.flash(sm(7.2, 7.8, t) * .8); },
    },
    /* SHOGUN (rare): a figure raises its arms and two golden wings unfold, then beat twice. */
    shogun: {
      dur: 7.8, pals: [mkpal([[0, 0, 0], [70, 40, 0], [190, 130, 20], [255, 210, 110], [255, 250, 220]])],
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
        g.text(typed("rents you the air.", t, 4.2, 9), .88, [255, 210, 110]); g.flash(Math.max(sm(.6, .7, t) * (1 - sm(.7, 1.2, t)) * .25, sm(7.1, 7.8, t)));
      },
    },
    /* RONIN (epic): the cliff, the wind, one cut that splits the night. */
    ronin: {
      dur: 8.8, pals: [mkpal([[0, 0, 0], [60, 14, 44], [150, 48, 110], [255, 138, 201], [255, 232, 246]])],
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
        g.text(typed("no master. no map.", t, 4.9, 9), .88, [255, 138, 201]); g.flash(Math.max(sm(3.4, 3.44, t) * (1 - sm(3.44, 3.9, t)) * .75, sm(8.1, 8.8, t)));
      },
    },
    /* GRIMM (legendary): down the nave toward the rose window. The bell tolls twice. */
    grimm: {
      dur: 9.0, pals: [mkpal([[0, 0, 0], [10, 60, 42], [60, 170, 120], [168, 255, 176], [240, 255, 240]]), mkpal([[0, 0, 0], [100, 70, 10], [240, 180, 50], [255, 228, 140], [255, 250, 232]]), mkpal([[0, 0, 0], [100, 24, 56], [240, 80, 140], [255, 160, 200], [255, 238, 246]]), mkpal([[0, 0, 0], [12, 46, 110], [60, 130, 240], [150, 210, 255], [240, 250, 255]])],
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
        g.text(typed("the walls remember.", t, 5.8, 9), .88, [168, 255, 176]); g.flash(Math.max(sm(4.3, 4.35, t) * (1 - sm(4.35, 4.8, t)) * .4, sm(5.5, 5.55, t) * (1 - sm(5.55, 6, t)) * .35, sm(8.3, 9.0, t)));
      },
    },
    /* REAPER (mythic): a wall of embers, one slash, and the night splits open along it. */
    reaper: {
      dur: 9.2, pals: [mkpal([[0, 0, 0], [70, 8, 0], [200, 50, 8], [255, 150, 40], [255, 240, 190]])],
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
        g.text(typed("still warm.", t, 4.9, 7), .88, [255, 150, 40]); g.flash(Math.max(sm(3.0, 3.05, t) * (1 - sm(3.05, 3.6, t)) * .85, sm(8.4, 9.2, t)));
      },
    },
    /* UMBRA (secret): the sun, the moon, the corona, one figure on a cliff. */
    umbra: {
      dur: 11.8, pals: [mkpal([[0, 0, 0], [70, 30, 6], [190, 100, 20], [255, 190, 70], [255, 245, 210]])],
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
        g.text(typed("the sun blinked first.", t, 6.6, 9), .22, [255, 190, 70]);
        g.flash(Math.max(sm(5.55, 5.6, t) * (1 - sm(5.6, 6.1, t)) * .5, sm(10.8, 11.8, t)));
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
        art: (lines, x, y, c, al, rev) => { const rv = rev == null ? 1 : rev; lines.forEach((s, j) => { for (let i = 0; i < s.length; i++) { const ch = s[i]; if (ch === " ") continue; const k = rv * 1.5 - hash(i, j, 3) * .6; if (k <= 0) continue; ov.push([x + i, y + j, k < .35 ? ".:*#"[(i + j + Math.floor(performance.now() / 55)) % 4] : ch, c, k < .35 ? al * .5 : al]); } }); },
        img: (gr, x, y, tint, al, rev) => { const rv = rev == null ? 1 : rev; for (let j = 0; j < gr.rows; j++) for (let i = 0; i < gr.cols; i++) { const l = gr.l[j * gr.cols + i]; if (l < .09) continue; const k = rv * 1.5 - hash(i, j, 4) * .6; if (k <= 0) continue; const m = .45 + .55 * l; ov.push([x + i, y + j, k < .3 ? ".:*#"[(i + j) % 4] : RAMP[Math.min(RAMP.length - 1, Math.floor(l * RAMP.length))], [tint[0] * m, tint[1] * m, tint[2] * m], k < .3 ? al * .5 : al]); } },
        frame: (x0, y0, w, h, c, al) => { for (let i = 1; i < w - 1; i++) { ov.push([x0 + i, y0, "─", c, al]); ov.push([x0 + i, y0 + h - 1, "─", c, al]); } for (let j = 1; j < h - 1; j++) { ov.push([x0, y0 + j, "│", c, al]); ov.push([x0 + w - 1, y0 + j, "│", c, al]); } ov.push([x0, y0, "┌", c, al], [x0 + w - 1, y0, "┐", c, al], [x0, y0 + h - 1, "└", c, al], [x0 + w - 1, y0 + h - 1, "┘", c, al]); },
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
      const frame = now => { const t = (now - t0) / 1000; try { render(t); } catch (e) { console.error(e); finish(); return; } if (t >= sc.dur) { finish(); return; } raf = requestAnimationFrame(frame); };   // a film that breaks must never leave the screen stuck
      const ready = sc.prep ? Promise.race([sc.prep(), new Promise(r => setTimeout(r, 2500))]) : Promise.resolve();
      if (o && o.freeze != null) { ready.then(() => { render(o.freeze); res(); }); return; }
      ready.then(() => { if (ended) return; t0 = performance.now(); raf = requestAnimationFrame(frame); });
    });
  }
  // the film that explains the app plays once, for someone who has not opened a pack yet
  const maybeIntro = () => { if (!state.seenIntro && !state.s.packs && !state.vault.length && !busy) { state.seenIntro = true; save(); play("intro"); } };
  const close = () => { if (stopLive) stopLive(); stopLive = null; $("cut").hidden = true; busy = false; };
  return { has, play, close, maybeIntro, ids: Object.keys(SCENES), dur: id => SCENES[id].dur };
})();
