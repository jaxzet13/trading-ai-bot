/* ============================================================================
   8d. THE TRADING CHART. A copy's price as candles, the way a coin is watched: pick how long a candle is (one second up to
   an hour), the newest candle forms as you look, the price rides a line on the right, and two marks say where you came in
   and where you went out: B where you got the copy, S where you sold it. A copy you sold keeps trading, so its chart shows
   what it did after you let it go.
   The picture is drawn four times a second from Val (which works any moment out from the copy and the clock).
   ========================================================================== */
const Chart = (() => {
  const TF = [[1, "1s"], [5, "5s"], [15, "15s"], [60, "1m"], [300, "5m"], [3600, "1h"]], N = 44, W = 720, H = 430, AX = 96, PT = 16, PB = 26;
  let tf = 5, timer = 0;
  const px = u => { const a = Math.abs(u) / UNIT, d = a < 1 ? 4 : a < 10 ? 3 : 2; return "$" + a.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); };   // more places than elsewhere: the point is to see it move
  const lastSold = no => (state.sold || []).find(r => r.no === no) || null;
  const find = uid => state.vault.find(c => c.uid === uid) || (state.sold || []).find(r => r.uid === uid) || null;
  const ago = ms => { const s = Math.max(0, Math.round(ms / 1000)); return s < 60 ? s + "s ago" : s < 3600 ? Math.round(s / 60) + " min ago" : s < 86400 ? Math.round(s / 3600) + "h ago" : Math.round(s / 86400) + "d ago"; };
  function html(c) {
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
  function draw() { const boxes = document.querySelectorAll("#mbox .tchart"); boxes.forEach(drawOne); return boxes.length; }
  function start() { draw(); if (timer) return; timer = setInterval(() => { if ($("modal").hidden || !draw()) { clearInterval(timer); timer = 0; } }, 250); }
  return { html, start, setTf, lastSold, px };
})();
