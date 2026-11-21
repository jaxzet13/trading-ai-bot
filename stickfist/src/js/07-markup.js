/* ============================================================================
   6. CARDS AND THE PACK
   ========================================================================== */
function cardHTML(copy, o) {
  o = o || {}; const card = BY_NO[copy.no], fx = copy.fx || "", tint = fx ? STYLE_TINT[fx] : card.tint, code = copy.code || "";
  return `<div class="card t${RAR[card.rar].tier}${o.sm ? " sm" : ""}${o.locked ? " locked" : ""}" style="--tint:${tint}" data-no="${card.no}">
    <div class="pic"><img src="${imgOf(card, fx)}" alt="${esc(card.name)}" draggable="false"></div>
    <div class="strip"><div class="l1"><span class="nm">${esc(card.name)}</span><i class="hr"></i><span class="ct"><b>${fmt(card.chars)}</b><u>chars</u></span></div>
    <div class="l2">${code ? idHTML(code, card.rar) : `<span>No. ${card.no}</span>`}${card.cap ? `<span class="cap">${esc(card.cap)}</span>` : ""}</div></div></div>`;
}
const CRIMP = fill("╱╲", 120);
const packHTML = () => `<div class="pk"><div class="crimp t">${CRIMP}</div><div class="win"><canvas class="scr"></canvas></div>
  <div class="readout"><div class="r-stat"></div><div class="r-name"></div><div class="r-sub"></div><div class="r-meter"></div></div><div class="crimp b">${CRIMP}</div></div>`;
// the animated picture in the pack
function liveWindow(pk) { const ps = new PackScreen(pk); ps.fit(); ps.start(); return ps; }
// a snapshot of the animation so a torn half still shows the picture it had
function freezeScreen(el, src) { const cv = el.querySelector("canvas.scr"); if (!cv) return; const img = new Image(); img.className = "scr"; img.src = src; cv.replaceWith(img); }
function tiltPack(pk) {
  pk.addEventListener("pointermove", e => { const r = pk.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5; pk.style.setProperty("--ry", (x * 16).toFixed(1) + "deg"); pk.style.setProperty("--rx", (-y * 12).toFixed(1) + "deg"); pk.style.setProperty("--sx", (50 + x * 80).toFixed(0) + "%"); });
  pk.addEventListener("pointerleave", () => { pk.style.setProperty("--ry", "0deg"); pk.style.setProperty("--rx", "0deg"); });
}
