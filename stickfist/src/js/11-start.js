/* ============================================================================
   10. START
   ========================================================================== */
const lastSeen0 = state.lastSeen;                                       // when you were last here, read before this visit overwrites it
MK.advance(); logWorth(); state.lastSeen = Date.now(); persist(); renderBal(); renderChips(); route(); renderTape();
if (!state.ageOK) $("gate").hidden = false; else setTimeout(() => Cut.maybeIntro(), 400);
// the market moves every 20 seconds; redraw whatever is on screen when it does
let lastTick = MK.tick();
// the market is live: every number on screen is redrawn once a second, in place, and the once-a-round jobs run when a new round of trading lands
setInterval(() => { MK.advance(); if (MK.tick() !== lastTick) { lastTick = MK.tick(); logWorth(); persist(); renderTape(); checkAlerts(); } refreshLive(); habitTick(); }, 1000);
setTimeout(() => maybeRecap(lastSeen0), 1400);
document.addEventListener("visibilitychange", () => { if (document.hidden) { state.lastSeen = Date.now(); persist(); } else { const since = state.lastSeen; maybeRecap(since); state.lastSeen = Date.now(); } });
setTimeout(checkAlerts, 2500);
Ref.sync(); setInterval(Ref.sync, 60000); document.addEventListener("visibilitychange", () => { if (!document.hidden && Date.now() - Ref.last() > 20000) Ref.sync(); });
tickLive(); setInterval(tickLive, 1000);
setTimeout(() => CARDS.forEach(c => loadImg(imgOf(c))), 700);   // warm the pictures so a reveal never waits on one
