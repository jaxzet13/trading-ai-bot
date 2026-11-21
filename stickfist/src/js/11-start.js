/* ============================================================================
   10. START
   ========================================================================== */
document.querySelectorAll("[data-block]").forEach(e => { e.innerHTML = blockSVG(e.dataset.block); });
renderBal(); route(); if (!state.ageOK) $("gate").hidden = false;
setTimeout(() => CARDS.forEach(c => loadImg(imgOf(c))), 700);   // warm the pictures so a reveal never waits on one
