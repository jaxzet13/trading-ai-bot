/* ============================================================================
   10. START
   ========================================================================== */
// (when you were last here is kept for the market catch-up only; nothing welcomes you back with a summary)
MK.advance(); logWorth(); state.lastSeen = Date.now(); persist(); renderBal(); renderChips(); if (Sale.ret() && location.hash !== "#/limited") location.hash = "#/limited"; route(); renderTape(); Sale.load(); Shop.load(); Shop.back();
if (!state.ageOK) $("gate").hidden = false; else setTimeout(() => Cut.maybeIntro(), 400);
// the market moves every 20 seconds; redraw whatever is on screen when it does
let lastTick = MK.tick();
// the market is live: every number on screen is redrawn once a second, in place, and the once-a-round jobs run when a new round of trading lands
setInterval(() => { MK.advance(); if (MK.tick() !== lastTick) { lastTick = MK.tick(); logWorth(); persist(); renderTape(); } refreshLive(); habitTick(); }, 1000);
document.addEventListener("visibilitychange", () => { state.lastSeen = Date.now(); persist(); });
Ref.sync(); setInterval(Ref.sync, 60000); document.addEventListener("visibilitychange", () => { if (!document.hidden && Date.now() - Ref.last() > 20000) Ref.sync(); });
tickLive(); setInterval(tickLive, 1000);
setTimeout(() => CARDS.forEach(c => loadImg(imgOf(c))), 700);   // warm the pictures so a reveal never waits on one
