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
    const rows = o.slice().reverse().slice(0, showAll ? MAX : 6).map(e => {
      const pk = PACK_BY[e.p], d = e.ref ? e.v / e.ref - 1 : 0, mins = Math.round((Date.now() - e.t) / 60000);
      const th = e.c.slice(0, 4).map(([no, fx], i) => { const card = BY_NO[no]; return card ? `<img src="${imgOf(card, fx, true)}" alt="${esc(card.name)}" loading="lazy" style="--rc:${RAR[card.rar].col};z-index:${4 - i}">` : ""; }).join("");
      const lead = BY_NO[e.c[0] && e.c[0][0]];
      return `<div class="hrow"><div class="hth">${th}</div><div class="hmid"><b>${esc(pk ? pk.name : e.p)}${e.n > 1 ? ` <span class="dim">×${e.n}</span>` : ""}</b><span class="dim">${agoText(mins)} · ${e.paid ? "paid " + moneyR(e.paid) : "free"}${lead ? ` · best ${esc(lead.name)}` : ""}</span></div><div class="hval"><b>${moneyR(e.v)}</b>${e.ref ? pctR(d) : ""}</div></div>`;
    }).join("");
    const more = o.length > 6 ? `<button class="linkbtn plain hmore" id="hMore">${showAll ? "Show less" : `Show all ${o.length}`}</button>` : "";
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
    g.fillStyle = "#050506"; g.fillRect(0, 0, W, H);
    const gl = g.createRadialGradient(W / 2, 980, 40, W / 2, 980, 900); gl.addColorStop(0, col + "55"); gl.addColorStop(1, "#05050600"); g.fillStyle = gl; g.fillRect(0, 0, W, H);
    g.font = M(500, 22); g.fillStyle = "rgba(236,231,220,.06)"; const chs = ".:-=+*#%@"; let sd = 7;
    for (let y = 30; y < H; y += 34) { let row = ""; for (let x = 0; x < 64; x++) { sd = (sd * 16807) % 2147483647; row += chs[sd % chs.length]; } g.fillText(row, 14, y); }
    g.textAlign = "center"; g.textBaseline = "alphabetic";
    // header
    g.fillStyle = "#ece7dc"; g.font = F(800, 54); g.letterSpacing = "18px"; g.fillText("STIXX", W / 2 + 9, 150); g.letterSpacing = "0px";
    g.fillStyle = "#9a968b"; g.font = F(500, 34); g.fillText(o.title || "my collection", W / 2, 215);
    // the big number
    g.fillStyle = "#ffffff"; g.font = F(800, 150); g.fillText(moneyR(net), W / 2, 380);
    g.fillStyle = pl >= 0 ? "#9be0a6" : "#ff8a80"; g.font = F(700, 46); g.fillText(`${pl >= 0 ? "+" : "−"}${moneyR(pl)} since I started`, W / 2, 455);
    // the best card
    if (bc) {
      const im = await load(imgOf(bc, best.fx, false)), cw = 600, chh = Math.round(cw * 1092 / 900), cx = (W - cw) / 2, cy = 530;
      g.save(); g.shadowColor = col; g.shadowBlur = 90; g.fillStyle = "#000"; g.fillRect(cx, cy, cw, chh); g.restore();
      if (im) g.drawImage(im, cx, cy, cw, chh); g.strokeStyle = col; g.lineWidth = 4; g.strokeRect(cx, cy, cw, chh);
      g.fillStyle = col; g.font = F(700, 30); g.fillText("BEST PULL", W / 2, cy + chh + 70);
      g.fillStyle = "#ffffff"; g.font = F(800, 72); g.fillText(bc.name + (best.fx ? " · " + STYLES[best.fx].name : ""), W / 2, cy + chh + 150);
      g.fillStyle = "#c9c4b8"; g.font = F(500, 38); g.fillText(`${rarLabel(bc)} · worth ${moneyR(valueOf(best))}`, W / 2, cy + chh + 210);
    }
    // three numbers
    const cols = [[String(st.packs), "packs opened"], [`${st.found}/${CARDS.length}`, "cards found"], (st.opens >= 3 ? [Math.round(st.hitRate * 100) + "%", "packs that paid off"] : [String(state.vault.length), "cards owned"])];
    cols.forEach(([v, l], i) => { const x = W / 6 + i * W / 3; g.fillStyle = "#ffffff"; g.font = F(800, 64); g.fillText(v, x, 1660); g.fillStyle = "#9a968b"; g.font = F(500, 28); g.fillText(l, x, 1705); });
    g.strokeStyle = "rgba(236,231,220,.14)"; g.lineWidth = 2; g.beginPath(); g.moveTo(90, 1580); g.lineTo(W - 90, 1580); g.stroke();
    g.fillStyle = "#ece7dc"; g.font = F(700, 34); g.fillText(o.host || location.host || "stixx", W / 2, 1810);
    g.fillStyle = "#6f6b62"; g.font = F(500, 24); g.fillText("play money · no cash value · 18+", W / 2, 1852);
    if (o.tag) { g.textAlign = "right"; g.fillStyle = "rgba(236,231,220,.45)"; g.font = F(600, 24); g.fillText(o.tag, W - 40, 60); }
    return cv;
  }
  async function share() {
    const btn = $("pShare"); if (btn) { btn.disabled = true; btn.textContent = "Making your card…"; }
    try {
      const cv = await card(), blob = await new Promise(r => cv.toBlob(r, "image/png")), file = new File([blob], "stixx-stats.png", { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) { try { await navigator.share({ files: [file], title: "My STIXX" }); } catch (e) {} }
      else { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "stixx-stats.png"; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); toast("Saved your stats card"); }
    } finally { if (btn) { btn.disabled = false; btn.textContent = "Share my stats"; } }
  }
  return { log, html, toggle, stats, card, share };
})();
