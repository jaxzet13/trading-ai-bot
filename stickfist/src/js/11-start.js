/* ============================================================================
   10. START
   ========================================================================== */
document.querySelectorAll("[data-block]").forEach(e => { e.innerHTML = blockSVG(e.dataset.block); });
MK.advance(); logWorth(); persist(); renderBal(); route();
if (!state.ageOK) $("gate").hidden = false;
// the market moves every 20 seconds; redraw whatever is on screen when it does
setInterval(() => { if (MK.advance()) { logWorth(); persist(); refreshLive(); } }, 2000);
setTimeout(() => CARDS.forEach(c => loadImg(imgOf(c))), 700);   // warm the pictures so a reveal never waits on one
