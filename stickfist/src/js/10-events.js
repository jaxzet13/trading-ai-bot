/* ============================================================================
   9. EVENTS
   ========================================================================== */
document.addEventListener("click", e => {
  const t = e.target.closest("button"); if (!t) { if (e.target === $("modal")) closeModal(); return; }
  if (t.hasAttribute("data-open")) { openPack(); return; }
  if (t.hasAttribute("data-close")) { closeModal(); return; }
  if (t.dataset.rq) { rqModal(t.dataset.rq); Snd.click(); return; }
  if (t.dataset.card) { cardModal(t.dataset.card); return; }
  if (t.dataset.cut) { closeModal(); Cut.play(t.dataset.cut); return; }
  if (t.dataset.f) { const [sc, k, v] = t.dataset.f.split(":"); if (sc === "m") { MKF[k] = v; renderMarket(); } else { CF[k] = v; renderCollection(); } Snd.click(); return; }
  if (t.dataset.pack) { if (PACK_BY[t.dataset.pack] && state.pack !== t.dataset.pack) { state.pack = t.dataset.pack; persist(); Snd.click(); renderHome(); } return; }
  if (t.dataset.opack) { oddsPack = t.dataset.opack; renderOdds(true); return; }
  if (t.dataset.brk) { startBreak(+t.dataset.brk); return; }
  if (t.dataset.buy) { Shop.modal(); return; }
  if (t.dataset.goal) { Goals.claim(t.dataset.goal); return; }
  if (t.dataset.prange) { pRange = +t.dataset.prange === 168 ? 168 : 24; renderProfile(); return; }
  if (t.dataset.many) { state.openN = +t.dataset.many || 1; persist(); Snd.click(); if (view === "home") renderHome(); return; }
  if (t.dataset.qsell) { quickSell(t.dataset.qsell); return; }
  if (t.dataset.share) { const c = state.vault.find(x => x.uid === t.dataset.share); if (c && replayable(c)) Share.open(receiptOf(c, false)); else toast("A replay is only offered for a card that is up more than 50%."); return; }
  if (t.dataset.sell) {
    const c = state.vault.find(x => x.uid === t.dataset.sell), rec = c ? receiptOf(c, true) : null;
    const g = sell([t.dataset.sell]); if (!g) return; soldToast(null, g);
    if (!$("modal").hidden) { if (state.vault.some(c => c.no === t.dataset.no)) cardModal(t.dataset.no); else closeModal(); } show(view, true); return;
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
    case "sumClip": if (SS) Clip.open(SS.items, SS.pack, SS.free, SS.bought ? -1 : SS_PRICE); break;
    case "rqShare": rqShare(); break;
    case "rqPay": Sale.pay(); break;
    case "buyBtn": case "topBuy": Shop.modal(); break;
    case "shopPay": Shop.pay(); break;
    case "shopOpen": closeModal(); openPack(); break;
    case "dailyBtn": Snd.click(); dailyModal(); break;
    case "claimDaily": { const r = claimDaily(); if (r) dailyModal(r); break; }
    case "claimOpen": closeModal(); openPack(); break;
    case "muteBtn": state.mute = !state.mute; persist(); renderChips(); if (!state.mute) Snd.click(); break;
    case "stSkip": if (SS) { if (SS.phase === "pack") SS.phase = "stack"; skipAll(); } break;
    case "sumSell": { const g = sell((SS.all || SS.items).map(c => c.uid)); closeStage(); soldToast(null, g); break; }
    case "sumSellAgain": { const pk = SS.pack, g = sell((SS.all || SS.items).map(c => c.uid)); closeStage(); soldToast(null, g); setTimeout(() => openPack(pk), 300); break; }
    case "sumSellSmall": { const g = sell((SS.all || []).filter(c => valueOf(c) < SMALL).map(c => c.uid)); closeStage(); soldToast(null, g); break; }
    case "sumKeep": closeStage(); toast("Kept in your collection"); break;
    case "sumAgain": { const pk = SS.pack, can = state.freePacks > 0 || boughtOf(pk.id) > 0 || state.coins >= packPrice(pk); closeStage(); if (can) setTimeout(() => openPack(pk), 200); else if (Shop.has(pk.id)) setTimeout(() => Shop.modal(pk.id), 200); else location.hash = "#/invite"; break; }
    case "sellExtras": { const ex = extras(), g = sell(ex.map(c => c.uid)); if (g) { soldToast(`Sold ${ex.length} extra cop${ex.length === 1 ? "y" : "ies"} for ${money(g)}`, g); renderCollection(); } break; }
    case "sellAll": {                                                      // sell everything: the first tap asks, the second sells (sales are final)
      const all = state.vault.slice(); if (!all.length) break;
      if (!(sellAllAt && Date.now() - sellAllAt < 4000)) { sellAllAt = Date.now(); renderCollection(); clearTimeout(sellAllT); sellAllT = setTimeout(() => { sellAllAt = 0; if (view === "collection") renderCollection(); }, 4000); break; }
      sellAllAt = 0; clearTimeout(sellAllT); const g = sell(all.map(c => c.uid)); if (g) { soldToast(`Sold all ${all.length} cards for ${money(g)}`, g); renderCollection(); } break; }
    case "sellUp": { const up = upCopies(), g = sell(up.map(c => c.uid)); if (g) { soldToast(`Sold ${up.length} card${up.length === 1 ? "" : "s"} that ${up.length === 1 ? "was" : "were"} up, for ${money(g)}`, g); renderCollection(); } break; }
    case "resetBtn": if (t.dataset.armed) { startOver(); renderBal(); renderChips(); location.hash = "#/"; show("home"); toast("Fresh start. Your first pack is free."); } else { t.dataset.armed = 1; t.textContent = "tap again to wipe your cards and start over"; setTimeout(() => { delete t.dataset.armed; t.textContent = "start over"; }, 3500); } break;
    case "copyLink": Ref.copy(); break;
    case "shareLink": Ref.share(); break;
    case "fairRotate": rotateSeed(); break;
    case "fairBtn3": case "fairBtn": case "fairBtn2": fairModal(); break;
    case "cashBtn": case "cashBtn2": cashModal(); break;
    case "pShare": History.share(); break;
    case "gMore": Goals.toggle(); break;
    case "pAllBtn": pAll = !pAll; renderProfile(); break;
    case "tipX": state.tg = state.tg || {}; state.tg.a2hs = 1; persist(); renderProfile(); break;
    case "hMore": History.toggle(); break;
    case "aboutBtn": aboutModal(); break;
    case "gateGo": state.ageOK = true; save(); $("gate").hidden = true; setTimeout(() => Cut.maybeIntro(), 300); Ref.sync(); break;
  }
});
document.addEventListener("change", e => { if (e.target.id === "rqAge") { const b = $("rqPay"); if (b && !b.dataset.busy) b.disabled = !e.target.checked; } if (e.target.id === "rqQty") Sale.qty(); if (e.target.id === "shopAge") { const b = $("shopPay"); if (b && !b.dataset.busy) b.disabled = !e.target.checked; } if (e.target.id === "shopQty" || e.target.id === "shopPack") Shop.qty(); if (e.target.id === "mSort") { MKF.sort = e.target.value; renderMarket(); } if (e.target.id === "cSort") { CF.sort = e.target.value; renderCollection(); } if (e.target.id === "ageOK") $("gateGo").disabled = !e.target.checked; if (e.target.id === "limPacks") { state.lim.packs = +e.target.value; persist(); toast(state.lim.packs ? `Limit set: ${state.lim.packs} packs a day` : "Daily pack limit removed"); } });
document.addEventListener("submit", e => { if (e.target.id === "vanityForm") { e.preventDefault(); Ref.vanity($("vanityIn").value); } if (e.target.id === "csForm") { e.preventDefault(); Fair.setClientSeed($("csIn").value); fairModal(true); toast("Client seed set"); } if (e.target.id === "vfForm") { e.preventDefault(); verifyHand(); } });
document.addEventListener("keydown", e => {
  const k = e.key;
  if (k === "Escape" && !$("clip").hidden) { Clip.close(); return; }
  if (!stage.hidden && SS) { if ((k === " " || k === "Enter") && SS.phase !== "summary") { e.preventDefault(); if (!e.repeat) advance(); } if (k === "Escape") { if (SS.phase === "summary") closeStage(); else skipAll(); } return; }
  if (k === "Escape" && !$("share").hidden) { Share.close(); return; }
  if (k === "Escape" && !$("modal").hidden) { closeModal(); return; }
  if ((k === " " || k === "Enter") && view === "home" && $("modal").hidden && $("share").hidden && $("gate").hidden && !e.repeat && !/^(BUTTON|INPUT|SELECT|A|SUMMARY)$/.test(e.target.tagName)) { e.preventDefault(); openPack(); }
});
// while cards are being revealed a tap anywhere on the stage goes on to the next one (the card itself still works), so a thumb never has to aim
stage.addEventListener("click", e => { if (SS && SS.phase === "stack" && !e.target.closest("button, a, .summary, .st-bar")) advance(); });
window.addEventListener("hashchange", route);
