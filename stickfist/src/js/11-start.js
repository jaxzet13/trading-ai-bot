/* ============================================================================
   10. START
   ========================================================================== */
MK.advance(); logWorth(); persist(); renderBal(); route(); renderTape();
if (!state.ageOK) $("gate").hidden = false; else setTimeout(() => Cut.maybeIntro(), 400);
// the market moves every 20 seconds; redraw whatever is on screen when it does
let lastTick = MK.tick();
// the market is live: every number on screen is redrawn once a second, in place, and the once-a-round jobs run when a new round of trading lands
setInterval(() => { MK.advance(); if (MK.tick() !== lastTick) { lastTick = MK.tick(); logWorth(); persist(); renderTape(); checkAlerts(); } refreshLive(); }, 1000);
setTimeout(checkAlerts, 2500);
tickLive(); setInterval(tickLive, 1000);
setTimeout(() => CARDS.forEach(c => loadImg(imgOf(c))), 700);   // warm the pictures so a reveal never waits on one
