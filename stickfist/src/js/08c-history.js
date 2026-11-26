/* ============================================================================
   8c. YOUR HISTORY AND YOUR STATS CARD.
   Every opening is kept (newest last): when, which pack, how many, what you paid, what the cards were worth the moment you pulled them, and the best
   few cards. The Me page lists them, and "Share my stats" draws a story-sized picture of your real numbers to post anywhere.
   ========================================================================== */
const History = (() => {
  const MAX = 200;
  // called once per opening (one pack or several at once)
  function log(pk, n, paid, ref, items) {
    const top = items.slice().sort((a, b) => costOf(b) - costOf(a)).slice(0, 5).map(c => [c.no, c.fx || ""]);
    (state.opens = state.opens || []).push({ t: Date.now(), p: pk.id, n, paid: Math.round(paid), ref: Math.round(ref), v: Math.round(items.reduce((a, c) => a + costOf(c), 0)), c: top });
    if (state.opens.length > MAX) state.opens.splice(0, state.opens.length - MAX);
  }
  const all = () => state.opens || [];
  function stats() {
    const o = all(); let best = null; for (const c of state.vault) if (!best || valueOf(c) > valueOf(best)) best = c;
    const won = o.filter(e => e.v >= e.ref).length;
    return { packs: state.s.packs, opens: o.length, best, hitRate: o.length ? won / o.length : 0, found: new Set(state.vault.map(c => c.no)).size };
  }
  let showAll = false;
  function html() {
    const o = all(); if (!o.length) return `<p class="dim small hempty">Your openings will show up here, starting with your next pack.</p>`;
    const rows = o.slice().reverse().slice(0, showAll ? MAX : 3).map(e => {
      const pk = PACK_BY[e.p], d = e.ref ? e.v / e.ref - 1 : 0, mins = Math.round((Date.now() - e.t) / 60000);
      const th = e.c.slice(0, 4).map(([no, fx], i) => { const card = BY_NO[no]; return card ? `<img src="${imgOf(card, fx, true)}" alt="${esc(card.name)}" loading="lazy" style="--rc:${RAR[card.rar].col};z-index:${4 - i}">` : ""; }).join("");
      const lead = BY_NO[e.c[0] && e.c[0][0]];
      return `<div class="hrow"><div class="hth">${th}</div><div class="hmid"><b>${esc(pk ? pk.name : e.p)}${e.n > 1 ? ` <span class="dim">×${e.n}</span>` : ""}</b><span class="dim">${agoText(mins)} · ${e.paid ? "paid " + moneyR(e.paid) : "free"}${lead ? ` · best ${esc(lead.name)}` : ""}</span></div><div class="hval"><b>${moneyR(e.v)}</b>${e.ref ? pctR(d) : ""}</div></div>`;
    }).join("");
    const more = o.length > 3 ? `<button class="linkbtn plain hmore" id="hMore">${showAll ? "Show less" : `Show all ${o.length}`}</button>` : "";
    return `<div class="hlist">${rows}</div>${more}`;
  }
  function toggle() { showAll = !showAll; $("pHist").innerHTML = html(); }

  /* ---- the stats card: 1080 × 1920, the size of a story ---- */
  const load = src => new Promise(res => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
  async function card(o) {
    o = Object.assign({}, state.demo || {}, o || {}); const W = 1080, H = 1920, cv = document.createElement("canvas"); cv.width = W; cv.height = H; const g = cv.getContext("2d");
    try { await document.fonts.ready; } catch (e) {}
    const st = stats(), net = netWorth(), pl = profitAll(), best = st.best, bc = best && BY_NO[best.no], col = bc ? (best.fx ? STYLE_TINT[best.fx] : RAR[bc.rar].col) : "#ece7dc";
    const F = (w, s) => `${w} ${s}px Inter, system-ui, sans-serif`, M = (w, s) => `${w} ${s}px "JetBrains Mono", ui-monospace, monospace`;
    // background: near black, a soft glow in the best card's colour, a faint field of characters
    g.fillStyle = "#07080a"; g.fillRect(0, 0, W, H);
    const gl = g.createRadialGradient(W / 2, 980, 40, W / 2, 980, 900); gl.addColorStop(0, col + "55"); gl.addColorStop(1, "#05050600"); g.fillStyle = gl; g.fillRect(0, 0, W, H);
    g.font = M(500, 22); g.fillStyle = "rgba(236,231,220,.06)"; const chs = ".:-=+*#%@"; let sd = 7;
    for (let y = 30; y < H; y += 34) { let row = ""; for (let x = 0; x < 64; x++) { sd = (sd * 16807) % 2147483647; row += chs[sd % chs.length]; } g.fillText(row, 14, y); }
    g.textAlign = "center"; g.textBaseline = "alphabetic";
    // header
    { const mx = W / 2 - 150, my = 100, k = 60 / 28; g.fillStyle = "#000"; g.strokeStyle = "rgba(255,255,255,.2)"; g.lineWidth = 2; g.beginPath(); g.roundRect(mx, my, 60, 60, 16); g.fill(); g.stroke();
      g.fillStyle = "#fff"; g.beginPath(); g.arc(mx + 14 * k, my + 5.9 * k, 1.6 * k, 0, 7); g.fill(); g.strokeStyle = "#fff"; g.lineWidth = 1.8 * k; g.lineCap = "round"; g.beginPath(); g.moveTo(mx + 8.2 * k, my + 9.8 * k); g.lineTo(mx + 19.8 * k, my + 21.4 * k); g.moveTo(mx + 19.8 * k, my + 9.8 * k); g.lineTo(mx + 8.2 * k, my + 21.4 * k); g.stroke();
      g.textAlign = "left"; g.fillStyle = "#f5f3ee"; g.font = F(800, 50); g.letterSpacing = "12px"; g.fillText("STIXX", mx + 82, 148); g.letterSpacing = "0px"; g.textAlign = "center"; }
    g.fillStyle = "#9a968b"; g.font = F(500, 34); g.fillText(o.title || "my collection", W / 2, 215);
    // the big number: your profit, and the line it took to get there
    g.fillStyle = pl >= 0 ? "#3be477" : "#ff6b6b"; g.font = F(800, 150); g.fillText(`${pl >= 0 ? "+" : "−"}${moneyR(Math.abs(pl))}`, W / 2, 380);
    g.fillStyle = "#9a968b"; g.font = F(600, 40); g.fillText("profit since I started", W / 2, 445);
    { const h = state.hist, N = 60, pts = []; let j = 0, t0 = h.length ? h[0][0] : Date.now(), t1 = Date.now();
      for (let i = 0; i < N; i++) { const ts = t0 + (t1 - t0) * i / (N - 1); while (j + 1 < h.length && h[j + 1][0] <= ts) j++; const e = h[j]; pts.push(e ? e[1] - (e[2] || 0) - START : 0); } pts[N - 1] = pl;
      const x0 = 90, x1 = W - 90, y0 = 500, y1 = 780, mn = Math.min(0, ...pts), mx = Math.max(0, ...pts), sp = Math.max(mx - mn, 1), X = i => x0 + (x1 - x0) * i / (N - 1), Y = v => y1 - (v - mn) / sp * (y1 - y0), col2 = pl >= 0 ? "#3be477" : "#ff6b6b";
      g.strokeStyle = "rgba(236,231,220,.18)"; g.lineWidth = 2; g.setLineDash([10, 10]); g.beginPath(); g.moveTo(x0, Y(0)); g.lineTo(x1, Y(0)); g.stroke(); g.setLineDash([]);
      const gr = g.createLinearGradient(0, y0, 0, y1); gr.addColorStop(0, col2 + "55"); gr.addColorStop(1, col2 + "00"); g.fillStyle = gr; g.beginPath(); g.moveTo(X(0), y1); pts.forEach((v, i) => g.lineTo(X(i), Y(v))); g.lineTo(X(N - 1), y1); g.closePath(); g.fill();
      g.strokeStyle = col2; g.lineWidth = 7; g.lineJoin = "round"; g.beginPath(); pts.forEach((v, i) => i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v))); g.stroke(); g.fillStyle = col2; g.beginPath(); g.arc(X(N - 1), Y(pts[N - 1]), 12, 0, 7); g.fill(); }
    // your three favourite cards (stars first, then your best cards)
    { const pick = []; for (const no of (state.favs || [])) if (BY_NO[no] && copiesOf(no).length && pick.length < 3) pick.push(no);
      for (const c of state.vault.slice().sort((a, b) => valueOf(b) - valueOf(a))) if (pick.length < 3 && !pick.includes(c.no)) pick.push(c.no);
      g.fillStyle = "#9a968b"; g.font = F(700, 30); g.letterSpacing = "6px"; g.fillText(state.favs && state.favs.length ? "MY FAVOURITES" : "MY BEST CARDS", W / 2, 880); g.letterSpacing = "0px";
      const cw = 300, chh = Math.round(cw * 1092 / 900), gap = 30, sx = (W - (pick.length * cw + (pick.length - 1) * gap)) / 2, cy = 920;
      for (let i = 0; i < pick.length; i++) { const cd = BY_NO[pick[i]], cp = copiesOf(pick[i])[0], rc = cp.fx ? STYLE_TINT[cp.fx] : RAR[cd.rar].col, im = await load(imgOf(cd, cp.fx, false)), cx = sx + i * (cw + gap);
        g.save(); g.shadowColor = rc; g.shadowBlur = 50; g.fillStyle = "#000"; g.fillRect(cx, cy, cw, chh); g.restore(); if (im) g.drawImage(im, cx, cy, cw, chh); g.strokeStyle = rc; g.lineWidth = 4; g.strokeRect(cx, cy, cw, chh);
        g.fillStyle = "#ffffff"; g.font = F(800, 38); g.fillText(cd.name, cx + cw / 2, cy + chh + 56); g.fillStyle = rc; g.font = F(600, 26); g.fillText(rarLabel(cd), cx + cw / 2, cy + chh + 94); } }
    // three numbers
    const cols = [[String(st.packs), "packs opened"], [`${Math.min(st.found, LIVE.length)}/${LIVE.length}`, "cards found"], (st.opens >= 3 ? [Math.round(st.hitRate * 100) + "%", "packs that paid off"] : [String(state.vault.length), "cards owned"])];
    cols.forEach(([v, l], i) => { const x = W / 6 + i * W / 3; g.fillStyle = "#ffffff"; g.font = F(800, 64); g.fillText(v, x, 1700); g.fillStyle = "#9a968b"; g.font = F(500, 28); g.fillText(l, x, 1745); });
    g.strokeStyle = "rgba(236,231,220,.14)"; g.lineWidth = 2; g.beginPath(); g.moveTo(90, 1620); g.lineTo(W - 90, 1620); g.stroke();
    g.fillStyle = "#ece7dc"; g.font = F(700, 34); g.fillText(o.host || location.host || "stixx", W / 2, 1810);
    g.fillStyle = "#6f6b62"; g.font = F(500, 24); g.fillText("play money · no cash value · 18+", W / 2, 1852);
    if (o.tag) { g.textAlign = "right"; g.fillStyle = "rgba(236,231,220,.45)"; g.font = F(600, 24); g.fillText(o.tag, W - 40, 60); }
    return cv;
  }
  async function share() {
    const btn = $("pShare"); if (btn) { btn.disabled = true; $("pShareTxt").textContent = "Making your card…"; }
    try {
      const cv = await card(), blob = await new Promise(r => cv.toBlob(r, "image/png")), file = new File([blob], "stixx-stats.png", { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) { try { await navigator.share({ files: [file], title: "My STIXX" }); } catch (e) {} }
      else { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "stixx-stats.png"; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); toast("Saved your stats card"); }
    } finally { if (btn) { btn.disabled = false; $("pShareTxt").textContent = "Share my stats"; } }
  }
  return { log, html, toggle, stats, card, share };
})();
