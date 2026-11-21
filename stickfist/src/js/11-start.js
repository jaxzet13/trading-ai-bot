/* ============================================================================
   10. START
   ========================================================================== */
MK.advance(); logWorth(); persist(); renderBal(); route(); renderTape();
if (!state.ageOK) $("gate").hidden = false;
// the market moves every 20 seconds; redraw whatever is on screen when it does
setInterval(() => { if (MK.advance()) { logWorth(); persist(); refreshLive(); renderTape(); checkAlerts(); } }, 2000);
setTimeout(checkAlerts, 2500);
tickLive(); setInterval(tickLive, 1000);
setTimeout(() => CARDS.forEach(c => loadImg(imgOf(c))), 700);   // warm the pictures so a reveal never waits on one
