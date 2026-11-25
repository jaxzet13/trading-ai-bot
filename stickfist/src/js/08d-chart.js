/* ============================================================================
   8d. THE TRADING CHART. A copy's price as candles, the way a coin is watched: pick how long a candle is (one second up to
   an hour), the newest candle forms as you look, the price rides a line on the right, and two marks say where you came in
   and where you went out: B where you got the copy, S where you sold it. A copy you sold keeps trading, so its chart shows
   what it did after you let it go.
   The picture is drawn ten times a second from Val (which works any moment out from the copy and the clock).
   The Me tab opens on one of these, full size: the copy of yours that is moving most right now, with its price rolling.
   ========================================================================== */
const Chart = (() => {
  const TF = [[1, "1s"], [5, "5s"], [15, "15s"], [60, "1m"], [300, "5m"], [3600, "1h"]], N = 44, W = 720, H = 430, AX = 96, PT = 16, PB = 26;
  let tf = 1, timer = 0, heroUid = "", heroAt = 0;
  const px = u => { const a = Math.abs(u) / UNIT, d = a < 1 ? 4 : a < 10 ? 3 : 2; return "$" + a.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); };   // more places than elsewhere: the point is to see it move
  const lastSold = no => (state.sold || []).find(r => r.no === no) || null;
  const find = uid => state.vault.find(c => c.uid === uid) || (state.sold || []).find(r => r.uid === uid) || null;
  const ago = ms => { const s = Math.max(0, Math.round(ms / 1000)); return s < 60 ? s + "s ago" : s < 3600 ? Math.round(s / 60) + " min ago" : s < 86400 ? Math.round(s / 3600) + "h ago" : Math.round(s / 86400) + "d ago"; };
  function html(c, bare) {
    const tabs = `<div class="tc-tf" role="tablist" aria-label="Candle length">${TF.map(([s, l]) => `<button class="tcb${s === tf ? " on" : ""}" role="tab" aria-selected="${s === tf}" data-tf="${s}">${l}</button>`).join("")}</div>`, cv = `<canvas class="tc-cv" width="${W}" height="${H}" role="img" aria-label="Price chart"></canvas>`;
    if (bare) return `<div class="tchart" data-uid="${c.uid}">${cv}${tabs}</div>`;                                    // on Me: the picture, and the candle lengths small underneath
    const now = Val.now(c), from = c.ts ? c.at : Val.at(c, c.t), p = now / Math.max(1, from) - 1;
    return `<div class="tchart" data-uid="${c.uid}"><div class="tc-tf" role="tablist" aria-label="Candle length">${TF.map(([s, l]) => `<button class="tcb${s === tf ? " on" : ""}" role="tab" aria-selected="${s === tf}" data-tf="${s}">${l}</button>`).join("")}</div>
      <canvas class="tc-cv" width="${W}" height="${H}" role="img" aria-label="Price chart"></canvas>
      <div class="tc-foot"><span class="tc-b"><i>B</i>got at ${px(Val.at(c, c.t))} · ${ago(Date.now() - c.t)}</span>${c.ts ? `<span class="tc-s"><i>S</i>sold at ${px(c.at)} · ${ago(Date.now() - c.ts)}</span><span class="tc-n ${p >= 0 ? "up" : "dn"}">now ${px(now)} · ${pctShort(p)} since you sold</span>` : `<span class="tc-n ${p >= 0 ? "up" : "dn"}">${pctShort(p)} since you got it</span>`}</div></div>`;
  }
  function setTf(s) { tf = s; document.querySelectorAll(".tcb").forEach(b => { const on = +b.dataset.tf === s; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); }); draw(); buzz(4); }
  function drawOne(box) {
    const c = find(box.dataset.uid), cv = box.querySelector("canvas"); if (!c || !cv) return; const x = cv.getContext("2d"), now = Date.now(), cs = Val.candles(c, tf, N, now), live = cs.filter(Boolean); if (!live.length) return;
    const ms = tf * 1000, end = Math.ceil(now / ms) * ms, t0 = end - N * ms, PW = W - AX, cw = PW / N, marks = [{ t: c.t, v: Val.at(c, c.t), k: "B", col: "#3be477" }]; if (c.ts) marks.push({ t: c.ts, v: c.at, k: "S", col: "#ff5d5d" });
    let lo = Math.min(...live.map(k => k.l)), hi = Math.max(...live.map(k => k.h)); marks.forEach(m => { if (m.t >= t0) { lo = Math.min(lo, m.v); hi = Math.max(hi, m.v); } });
    const pad = Math.max((hi - lo) * .12, hi * .0015); lo -= pad; hi += pad; const Y = v => PT + (H - PT - PB) * (1 - (v - lo) / (hi - lo)), X = t => (t - t0) / ms * cw;
    x.clearRect(0, 0, W, H); x.font = '600 19px "JetBrains Mono", ui-monospace, monospace'; x.textBaseline = "middle"; x.textAlign = "left";
    for (let g = 0; g <= 4; g++) { const v = lo + (hi - lo) * g / 4, y = Math.round(Y(v)) + .5; x.strokeStyle = "rgba(255,255,255,.06)"; x.lineWidth = 1; x.beginPath(); x.moveTo(0, y); x.lineTo(PW, y); x.stroke(); x.fillStyle = "rgba(255,255,255,.38)"; x.fillText(px(v), PW + 10, y); }
    cs.forEach((k, i) => { if (!k) return; const up = k.c >= k.o, col = up ? "#3be477" : "#ff5d5d", cx = i * cw + cw / 2, yo = Y(k.o), yc = Y(k.c), top = Math.min(yo, yc), bh = Math.max(2, Math.abs(yc - yo));
      x.strokeStyle = col; x.lineWidth = 2; x.beginPath(); x.moveTo(cx, Y(k.h)); x.lineTo(cx, Y(k.l)); x.stroke(); x.fillStyle = col; x.fillRect(cx - cw * .32, top, cw * .64, bh); });
    const last = live[live.length - 1], yl = Y(last.c), up = last.c >= last.o, col = up ? "#3be477" : "#ff5d5d";                                                            // the price, riding the right edge
    x.setLineDash([5, 6]); x.strokeStyle = col; x.globalAlpha = .7; x.lineWidth = 1.5; x.beginPath(); x.moveTo(0, yl); x.lineTo(PW, yl); x.stroke(); x.setLineDash([]); x.globalAlpha = 1;
    x.fillStyle = col; const tw = AX - 6; x.beginPath(); x.roundRect(PW + 4, yl - 15, tw, 30, 8); x.fill(); x.fillStyle = "#04130a"; x.font = '800 19px "JetBrains Mono", ui-monospace, monospace'; x.fillText(px(last.c), PW + 10, yl + 1);
    for (const m of marks) {                                                                                                                                                 // where you came in, where you went out
      const off = m.t < t0, mx = off ? 20 : Math.max(20, Math.min(PW - 20, X(m.t))), my = Math.max(PT + 16, Math.min(H - PB - 16, Y(m.v)));
      x.strokeStyle = m.col; x.globalAlpha = .55; x.lineWidth = 1.5; x.setLineDash([3, 5]); x.beginPath(); x.moveTo(mx, my); x.lineTo(PW, my); x.stroke(); x.setLineDash([]); x.globalAlpha = 1;
      x.fillStyle = "#05060a"; x.beginPath(); x.arc(mx, my, 17, 0, 6.2832); x.fill(); x.fillStyle = m.col; x.beginPath(); x.arc(mx, my, 14, 0, 6.2832); x.fill();
      x.fillStyle = "#05060a"; x.font = "800 17px Inter, system-ui, sans-serif"; x.textAlign = "center"; x.fillText(off ? "‹" + m.k : m.k, mx, my + 1); x.textAlign = "left";
    }
    x.fillStyle = "rgba(255,255,255,.32)"; x.font = '500 16px "JetBrains Mono", ui-monospace, monospace'; x.fillText(`${TF.find(f => f[0] === tf)[1]} candles · live`, 6, H - 11);
  }
  /* ---- the live hero on Me ----
     Which copy to show: one that is running right now, else the biggest riser of the last minute. It stays put for a while
     so the picture does not flick between cards. */
  const heat = (c, t) => { const g = Val.surge(c, t); return g ? 10 + g.j * (1 - g.q) : Val.pctSec(c, 60); };
  function hero() {
    const v = state.vault; if (!v.length) return null; const t = Date.now();
    const cur = v.find(x => x.uid === heroUid), running = cur && Val.surge(cur, t); if (running) { heroAt = t - 12000; return cur; }      // a run is watched to the end, and a little past it
    const ranked = v.map(c => [heat(c, t), c]).sort((a, b) => b[0] - a[0]);
    if (cur && t - heroAt < 20000 && ranked[0][0] < 10) return cur;
    heroUid = ranked[0][1].uid; heroAt = t; return ranked[0][1];
  }
  const mult = p => p >= 1 ? "×" + (1 + p).toFixed(p >= 9 ? 0 : 1) : pctShort(p);                                                          // twice or more reads as a multiple
  const state3 = (g, m1) => g ? "pump" : m1 <= -.08 ? "dump" : "";
  function heroHTML() {
    const c = hero(); if (!c) return ""; const card = BY_NO[c.no], t = Date.now(), g = Val.surge(c, t), m1 = Val.pctSec(c, 60), now = Val.now(c), p = now / Math.max(1, Val.at(c, c.t)) - 1, st = state3(g, m1);
    return `<div class="lhero ${st}" data-uid="${c.uid}" style="--rc:${RAR[card.rar].col}">
      <div class="lh-top"><button class="lh-who" data-card="${card.no}" aria-label="${esc(card.name)}">${thumb(card, c.fx)}<span><b>${esc(card.name)}</b><small>${esc(RAR[card.rar].name)}</small></span></button><span class="lh-badge" data-lbadge>${st === "pump" ? "pumping" : st === "dump" ? "dumping" : "live"}</span></div>
      <div class="lh-px"><b data-lpx>${px(now)}</b><span class="lh-pct ${p >= 0 ? "up" : "dn"}" data-lpct>${p >= 0 ? "▲" : "▼"} ${mult(p).replace(/^[+−]/, "")}</span></div>
      ${html(c, true)}
      <button class="btn lh-sell" data-sell="${c.uid}" data-no="${card.no}">Sell <b data-lsell>${money(sellOf(c))}</b></button></div>`;
  }
  // between redraws of the page the hero's numbers keep rolling
  function roll() {
    const box = document.querySelector(".lhero"); if (!box) return; const c = state.vault.find(x => x.uid === box.dataset.uid); if (!c) return;
    const t = Date.now(), now = Val.at(c, t), p = now / Math.max(1, Val.at(c, c.t)) - 1, g = Val.surge(c, t), m1 = Val.pctSec(c, 60), st = state3(g, m1), set = (sel, txt, cls) => { const e = box.querySelector(sel); if (!e) return; if (e.textContent !== txt) e.textContent = txt; if (cls) { e.classList.toggle("up", cls === "up"); e.classList.toggle("dn", cls === "dn"); } };
    set("[data-lpx]", px(now)); set("[data-lpct]", (p >= 0 ? "▲ " : "▼ ") + mult(p).replace(/^[+−]/, ""), p >= 0 ? "up" : "dn"); set("[data-lsell]", money(sellOf(c)));
    set("[data-lbadge]", st === "pump" ? "pumping" : st === "dump" ? "dumping" : "live"); box.classList.toggle("pump", st === "pump"); box.classList.toggle("dump", st === "dump");
  }
  const shown = b => b.offsetParent !== null;
  function draw() { let n = 0; document.querySelectorAll(".tchart").forEach(b => { if (shown(b)) { drawOne(b); n++; } }); roll(); return n; }
  function start() { draw(); if (timer) return; timer = setInterval(() => { if (document.hidden) return; if (!draw()) { clearInterval(timer); timer = 0; } }, 100); }
  return { html, heroHTML, start, setTf, lastSold, px };
})();
