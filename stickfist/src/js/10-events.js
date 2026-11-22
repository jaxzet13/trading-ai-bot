/* ============================================================================
   9. EVENTS
   ========================================================================== */
document.addEventListener("click", e => {
  const t = e.target.closest("button"); if (!t) { if (e.target === $("modal")) closeModal(); return; }
  if (t.hasAttribute("data-open")) { openPack(); return; }
  if (t.hasAttribute("data-close")) { closeModal(); return; }
  if (t.dataset.card) { if (t.closest("#alert")) hideAlert(); cardModal(t.dataset.card); return; }
  if (t.dataset.cut) { closeModal(); Cut.play(t.dataset.cut); return; }
  if (t.dataset.tgt) { const [no, dir, pct] = t.dataset.tgt.split("|"); setTarget(no, dir, +pct); cardModal(no, true); toast(dir === "clear" ? "Alerts cleared" : "Alert set. You'll hear from us when it gets there."); Snd.click(); return; }
  if (t.dataset.pack) { if (PACK_BY[t.dataset.pack] && state.pack !== t.dataset.pack) { state.pack = t.dataset.pack; persist(); Snd.click(); renderHome(); } return; }
  if (t.dataset.opack) { oddsPack = t.dataset.opack; renderOdds(); return; }
  if (t.dataset.brk) { startBreak(+t.dataset.brk); return; }
  if (t.dataset.recap) { closeModal(); location.hash = "#/" + t.dataset.recap; return; }
  if (t.dataset.share) { const c = state.vault.find(x => x.uid === t.dataset.share); if (c) Share.open(receiptOf(c, false)); return; }
  if (t.dataset.sell) {
    const c = state.vault.find(x => x.uid === t.dataset.sell), rec = c ? receiptOf(c, true) : null;
    const g = sell([t.dataset.sell]); if (!g) return; toast("Sold for " + money(g));
    if (!$("modal").hidden) { if (state.vault.some(c => c.no === t.dataset.no)) cardModal(t.dataset.no); else closeModal(); } show(view); if (rec) Share.open(rec); return;
  }
  if (/^sum/.test(t.id) && SS && performance.now() - SS.sumAt < 500) return;
  switch (t.id) {
    case "shSave": Share.save(); break;
    case "shShare": Share.share(); break;
    case "shVideo": Share.video(); break;
    case "shPlay": Share.toggle(); break;
    case "shTrack": Share.seek(e); break;
    case "shSpeed": Share.cycle(); break;
    case "shSummary": Share.summary(); break;
    case "shClose": Share.close(); break;
    case "clSave": Clip.save(); break;
    case "clShare": Clip.share(); break;
    case "clAgain": Clip.replay(); break;
    case "clClose": Clip.close(); break;
    case "sumClip": if (SS) Clip.open(SS.items, SS.pack, SS.free, SS_PRICE); break;
    case "alertX": hideAlert(); break;
    case "dailyBtn": Snd.click(); dailyModal(); break;
    case "claimDaily": { const r = claimDaily(); if (r) dailyModal(r); break; }
    case "claimOpen": closeModal(); openPack(); break;
    case "muteBtn": state.mute = !state.mute; persist(); renderChips(); if (!state.mute) Snd.click(); break;
    case "stSkip": if (SS) { if (SS.phase === "pack") SS.phase = "stack"; skipAll(); } break;
    case "sumSell": { const g = sell(SS.items.map(c => c.uid)); closeStage(); toast("Sold for " + money(g)); break; }
    case "sumKeep": closeStage(); toast("Kept in your collection"); break;
    case "sumAgain": { const pk = SS.pack, can = state.freePacks > 0 || state.coins >= packPrice(pk); closeStage(); if (can) setTimeout(() => openPack(pk), 200); else location.hash = "#/invite"; break; }
    case "sellExtras": { const ex = extras(), g = sell(ex.map(c => c.uid)); if (g) { toast(`Sold ${ex.length} extra cop${ex.length === 1 ? "y" : "ies"} for ${money(g)}`); renderCollection(); } break; }
    case "resetBtn": if (t.dataset.armed) { startOver(); renderBal(); renderChips(); location.hash = "#/"; show("home"); toast("Fresh start. Your first pack is free."); } else { t.dataset.armed = 1; t.textContent = "tap again to wipe your cards and start over"; setTimeout(() => { delete t.dataset.armed; t.textContent = "start over"; }, 3500); } break;
    case "copyLink": Ref.copy(); break;
    case "shareLink": Ref.share(); break;
    case "fairRotate": rotateSeed(); break;
    case "fairBtn": case "fairBtn2": fairModal(); break;
    case "cashBtn": case "cashBtn2": cashModal(); break;
    case "aboutBtn": aboutModal(); break;
    case "gateGo": state.ageOK = true; save(); $("gate").hidden = true; setTimeout(() => Cut.maybeIntro(), 300); Ref.sync(); break;
  }
});
document.addEventListener("change", e => { if (e.target.id === "ageOK") $("gateGo").disabled = !e.target.checked; if (e.target.id === "limPacks") { state.lim.packs = +e.target.value; persist(); toast(state.lim.packs ? `Limit set: ${state.lim.packs} packs a day` : "Daily pack limit removed"); } });
document.addEventListener("submit", e => { if (e.target.id === "vanityForm") { e.preventDefault(); Ref.vanity($("vanityIn").value); } if (e.target.id === "csForm") { e.preventDefault(); Fair.setClientSeed($("csIn").value); fairModal(true); toast("Client seed set"); } if (e.target.id === "vfForm") { e.preventDefault(); verifyHand(); } });
document.addEventListener("keydown", e => {
  const k = e.key;
  if (k === "Escape" && !$("clip").hidden) { Clip.close(); return; }
  if (!stage.hidden && SS) { if ((k === " " || k === "Enter") && SS.phase !== "summary") { e.preventDefault(); if (!e.repeat) advance(); } if (k === "Escape") { if (SS.phase === "summary") closeStage(); else skipAll(); } return; }
  if (k === "Escape" && !$("share").hidden) { Share.close(); return; }
  if (k === "Escape" && !$("modal").hidden) { closeModal(); return; }
  if ((k === " " || k === "Enter") && view === "home" && $("modal").hidden && $("share").hidden && $("gate").hidden && !e.repeat && !/^(BUTTON|INPUT|SELECT|A|SUMMARY)$/.test(e.target.tagName)) { e.preventDefault(); openPack(); }
});
window.addEventListener("hashchange", route);
