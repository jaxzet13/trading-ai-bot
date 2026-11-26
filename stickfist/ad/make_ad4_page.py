import os, re
os.chdir('/home/user/trading-ai-bot/stickfist/ad')
s = open('ad3.html').read()

# ---- css: the Me tab as the app draws it, plus a few film-only rules
css = '''
#screen { top: 54px; padding: 0 18px; }
#screen .pf2 { padding-top: 22px; } #screen .pf2 .bignum { font-size: 72px; } #screen .pf-chart { height: 190px; margin: 10px -6px 8px; }
#screen .pf-chart svg { width: 100%; height: 100%; } #screen .favh { margin-top: 18px; } #screen .pf-stats { margin-top: 22px; }
#screen .fvt.big { position: relative; } #screen .fvt.big small { font-variant-numeric: tabular-nums; }
#screen .prow { display: flex; align-items: center; gap: 12px; height: 66px; border-bottom: 1px solid rgba(255,255,255,.08); }
#screen .prow .th { width: 46px; height: 56px; border: 2px solid var(--rc); border-radius: 3px; overflow: hidden; box-shadow: 0 0 16px color-mix(in srgb, var(--rc) 40%, transparent); } #screen .prow .th img { width: 100%; height: 100%; object-fit: cover; display: block; }
#screen .prow .nm { flex: 1; } #screen .prow .nm b { display: block; font-size: 17px; } #screen .prow .nm small { color: var(--dim); font-size: 12px; }
#screen .prow .rt { text-align: right; font-variant-numeric: tabular-nums; } #screen .prow .rt b { display: block; font-size: 17px; color: var(--ok); } #screen .prow .rt small { color: var(--ink); font-size: 12.5px; opacity: .85; }
#screen .plist { margin-top: 4px; }
#foot { position: absolute; left: 0; right: 0; bottom: 6px; text-align: center; font-size: 10px; color: var(--dim); z-index: 5; letter-spacing: .02em; }
.btabs { position: absolute; z-index: 4; }
'''
s = s.replace('</style>', css + '</style>', 1)

# ---- dom
a = s.index('<div id="cam">') + len('<div id="cam">'); b = s.index('\n  <div id="fx">')
dom = '''
    <header class="top"><div class="wrap"><a class="logo"><svg class="mark" viewBox="0 0 28 28" aria-hidden="true"><rect x=".5" y=".5" width="27" height="27" rx="7.5" fill="#000" stroke="rgba(255,255,255,.18)"/><circle cx="14" cy="5.9" r="1.55" fill="#fff"/><path d="M8.2 9.8 19.8 21.4M19.8 9.8 8.2 21.4" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round"/></svg><span>STIXX</span></a><div class="wallet"><button class="chip ready" style="color:var(--ok)"><i></i>free pack</button><span class="bal">$18.50</span></div></div></header>
    <div id="screen">
      <div class="pf2 pos" id="pf"><span class="label">my collection</span><div class="bignum" id="hbig">+$7.04</div>
        <div class="pf-row"><span class="pf-pill" id="hpill">▲ 3.6%</span><span class="dim" id="hcap">since you started</span></div>
        <div class="pf-chart"><svg viewBox="0 0 400 112" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="pfG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="g0"/><stop offset="1" class="g1"/></linearGradient></defs><path class="b" id="hbase"/><path class="a" id="hfill" fill="url(#pfG)"/><path class="l" id="hline"/></svg><i class="pf-dot" id="hdot"></i></div>
        <div class="pf-rng"><button>1H</button><button>1D</button><button>1W</button><button class="on">All</button></div></div>
      <h3 class="favh">most profitable cards</h3>
      <div class="plist" id="fav"></div>
    </div>
    <nav class="btabs"><a><svg viewBox="0 0 24 24"><path d="M7 3h10v18H7z"/><path d="M7 7l1.7-1.6L10.3 7l1.7-1.6L13.7 7l1.7-1.6L17 7"/><path d="M10 12h4M10 15h3"/></svg><span>pack</span></a><a><svg viewBox="0 0 24 24"><path d="M3 12h4l2.5-6 4 12 2.5-6h5"/></svg><span>live</span></a><a class="on" aria-current="page"><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4.5 21c.7-4 3.8-6 7.5-6s6.8 2 7.5 6"/></svg><span>me</span></a></nav>
    <div id="foot">an illustration of one lucky collection in the simulated market · play money · 18+</div>
'''
s = s[:a] + dom + '  </div>' + s[b:]

# ---- script: drop the rows, rewrite render
i = s.index('const rowEls = '); j = s.index('\n', i); s = s[:i] + '''const TOP = ["reaper", "grimm", "ronin", "liftoff"].map(id => C.find(c => c.id === id));
$("fav").innerHTML = TOP.map(c => `<div class="prow" style="--rc:${c.col}"><span class="th"><img src="../cards/s/${c.id}.jpg" alt=""></span><span class="nm"><b>${c.name}</b><small>bought for ${money(c.cost)}</small></span><span class="rt"><b data-p="${c.id}"></b><small data-v="${c.id}"></small></span></div>`).join("");''' + s[j:]
s = s.replace('const CAPS = [[0, 2.4, "since you started"], [2.4, 6, "most of your cards are up"], [6, 9.4, "two are down. that happens"], [9.4, 14, "the rest start to fly"], [14, 19.1, "watch it go"], [19.1, 23, null]];',
              'const CAPS = [[0, 2.4, "since you started"], [2.4, 9.4, "your cards are climbing"], [9.4, 19.1, "watch it go"], [19.1, 23, null]];')
r0 = s.index('function render(t) {'); r1 = s.index('window.renderAt')
render = '''function render(t) {
  t = Math.max(0, Math.min(DUR - 1 / FPS / 2, t));
  const p = profitAt(t), k = stepOf(t), since = t - stepTime(k), flashK = Math.max(0, 1 - since / .45);
  const big = $("hbig"); big.textContent = (p >= 0 ? "+" : "-") + money(Math.abs(p)); const [cls, txt] = pillHTML(p / BASIS); $("hpill").textContent = txt;
  const rate = profitAt(t + .5) - profitAt(t - .1), hot = cl(rate / 12000); big.style.textShadow = `0 0 ${10 + hot * 38}px rgba(59,228,119,${.15 + hot * .6})`; big.style.fontSize = (72 + 6 * sm(LOCK - 1.5, LOCK, t) - 6 * sm(LOCK + 1.2, LOCK + 2.6, t)) + "px";
  const cap = CAPS.find(c => t >= c[0] && t < c[1]); $("hcap").textContent = cap && cap[2] ? cap[2] : t >= LOCK ? "up from +" + money(START_PROFIT) : "";
  // the chart: your profit so far, filling the width as time goes on, the way the Me tab draws it
  const n = 60, pts = []; let mx = 0; for (let j = 0; j <= n; j++) { const tt = t * j / n, v = profitAt(tt); pts.push(v); mx = Math.max(mx, v); } const top = Math.max(mx * 1.1, 2500), X = j => (j / n * 400).toFixed(1), Y = v => (104 - v / top * 88).toFixed(1), d = pts.map((v, j) => X(j) + " " + Y(v)).join(" L");
  $("hline").setAttribute("d", "M" + d); $("hfill").setAttribute("d", "M" + d + " L400 112 L0 112 Z"); $("hbase").setAttribute("d", "M0 " + Y(pts[0]) + " L400 " + Y(pts[0])); $("hdot").style.top = (Y(pts[n]) / 112 * 100).toFixed(1) + "%";
  // the three best cards, and what each is worth now
  TOP.forEach(c => { const v = val(c, t), pr = v / c.cost - 1, pe = document.querySelector(`[data-p="${c.id}"]`), ve = document.querySelector(`[data-v="${c.id}"]`); pe.textContent = "▲ " + (pr * 100 >= 1000 ? Math.round(pr * 100).toLocaleString("en-US") : (pr * 100).toFixed(pr * 100 >= 100 ? 0 : 1)) + "%"; ve.textContent = "sold for " + money(v); });
  // particles: dollar signs and plus signs rising off the profit when it jumps
  const jumpT = EV.filter(e => e.k === "tick" && e.a > .4 && e.t <= t && t - e.t < 1.2); PTS.forEach(e => { e.style.opacity = 0; });
  let pi = 0; for (const e of jumpT) for (let j = 0; j < 3 && pi < PTS.length; j++, pi++) { const u = (t - e.t) / 1.2, h = hash(Math.round(e.t * 100), j, 5), el = PTS[pi]; el.textContent = h > .5 ? "$" : "+"; el.style.left = (60 + h * 380 + Math.sin(u * 5 + j) * 14).toFixed(1) + "px"; el.style.top = (230 - u * 150).toFixed(1) + "px"; el.style.fontSize = (14 + h * 14).toFixed(0) + "px"; el.style.opacity = (Math.sin(Math.PI * u) * .9).toFixed(3); }
  // the camera: a slow push, a kick on a milestone and a long glide on the last climb
  let hit = 0; for (const e of EV) if ((e.k === "mile" || e.k === "lock") && t >= e.t && t - e.t < .6) hit += Math.exp(-(t - e.t) * 8) * (e.k === "lock" ? 1.6 : .7);
  const zoom = 1 + .02 * sm(0, 19, t) + .018 * hit - .02 * sm(LOCK + 1, LOCK + 3, t), sx = Math.sin(t * 37) * hit * 2.2, sy = Math.cos(t * 41) * hit * 2.2;
  $("cam").style.transform = `translate(${sx}px,${sy}px) scale(${zoom})`;
  $("flash").style.opacity = Math.min(.3, hit * .08 + (t > LOCK && t < LOCK + .2 ? (1 - (t - LOCK) / .2) * .22 : 0));
  $("stage").style.opacity = sm(0, .45, t); $("end").style.opacity = sm(END0, END0 + .5, t);
  $("grain").children[0] && $("gt").setAttribute("seed", String(Math.floor(t * 30) % 97));
}
'''
s = s[:r0] + render + s[r1:]
s = s.replace('<title>STIXX: the collection</title>', '<title>STIXX: up</title>')
open('ad4.html', 'w').write(s)
print('ad4.html written', len(s))
