/* ============================================================================
   6. CARDS AND THE PACK
   ========================================================================== */
function cardHTML(copy, o) {
  o = o || {}; const card = BY_NO[copy.no], fx = copy.fx || "", tint = fx ? STYLE_TINT[fx] : card.tint, code = copy.code || "", R = RAR[card.rar];
  // a framed card: a ring in the rarity's colour, the picture in a window, the rarity and number over it, a nameplate under it, and foil that catches the light
  return `<div class="card v3 t${R.tier}${fx ? " fx" : ""}${o.sm ? " sm" : ""}${o.locked ? " locked" : ""}" style="--tint:${tint};--rc:${R.col}" data-no="${card.no}">
    <div class="pic"><img src="${imgOf(card, fx, o.thumb)}" alt="${esc(card.name)}" draggable="false"${o.thumb ? ' loading="lazy"' : ""}></div>
    <div class="hd"><span class="rr"><i></i><b>${R.name}</b></span>${fx ? `<span class="fxn">${esc(STYLES[fx].name)}</span>` : `<span class="no">${SETS[card.set].code} ${card.no}</span>`}</div>
    <div class="strip"><div class="l1"><span class="nm">${esc(card.name)}</span><i class="hr"></i><span class="ct"><b>${fmt(card.chars)}</b><u>chars</u></span></div>
    <div class="l2">${code ? idHTML(code, card.rar) : `<span>No. ${card.no}</span>`}${card.cap ? `<span class="cap">${esc(card.cap)}</span>` : ""}</div></div><i class="sheen"></i></div>`;
}
const CRIMPS = { fp: fill("╱╲", 120), ms: fill("△▲", 120) };
const packHTML = pack => `<div class="pk pk-${pack.id}"><div class="crimp t">${CRIMPS[pack.id]}</div><div class="win"><canvas class="scr"></canvas></div>
  <div class="readout"><div class="r-stat"></div><div class="r-name"></div><div class="r-sub"></div><div class="r-meter"></div></div><div class="crimp b">${CRIMPS[pack.id]}</div></div>`;
// the animated picture in the pack
function liveWindow(pk, pack) { const ps = new PackScreen(pk, pack); ps.fit(); ps.start(); return ps; }
// a snapshot of the animation so a torn half still shows the picture it had
function freezeScreen(el, src) { const cv = el.querySelector("canvas.scr"); if (!cv) return; const img = new Image(); img.className = "scr"; img.src = src; cv.replaceWith(img); }
function tiltPack(pk) {
  pk.addEventListener("pointermove", e => { pk.classList.add("held"); const r = pk.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5; pk.style.setProperty("--ry", (x * 16).toFixed(1) + "deg"); pk.style.setProperty("--rx", (-y * 12).toFixed(1) + "deg"); pk.style.setProperty("--sx", (50 + x * 80).toFixed(0) + "%"); });
  const drop = () => { pk.classList.remove("held"); pk.style.removeProperty("--ry"); pk.style.removeProperty("--rx"); }; pk.addEventListener("pointerleave", drop); pk.addEventListener("pointerup", drop); pk.addEventListener("pointercancel", drop);
}
