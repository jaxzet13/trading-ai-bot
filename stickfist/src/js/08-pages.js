/* ============================================================================
   7. PAGES: pack, market, collection, odds
   ========================================================================== */
// two tabs: the pack, and you (your money, your cards, the market); the other pages hang off those two
const VIEWS = ["home", "live", "market", "profile", "collection", "odds", "invite", "limited"], TAB_OF = { live: "live", home: "home", odds: "home", limited: "home", profile: "profile", market: "profile", collection: "profile", invite: "profile" }; let view = "home", modalNo = null, oddsPack = "";
const copiesOf = no => state.vault.filter(c => c.no === no).sort((a, b) => valueOf(b) - valueOf(a));
function renderBal(anim) { const el = $("bal"), from = +(el.dataset.v || state.coins); el.dataset.v = state.coins; if (anim) countTo(el, from, state.coins, money); else el.textContent = money(state.coins); if (typeof renderBroke === "function") renderBroke(); }

/* ---- the market's numbers, ready to show ---- */
// your copies, each with its own last day: the only market there is
function myMovers() { return state.vault.map(copy => { const s = Val.series(copy, 24, 24); return { c: BY_NO[copy.no], copy, s, now: valueOf(copy), was: s[0], p24: Val.pct(copy, 24) }; }); }
function movers() { const rows = myMovers(); return { rows, gain: rows.filter(r => r.p24 > .005).sort((a, b) => b.p24 - a.p24).slice(0, 3), drop: rows.filter(r => r.p24 < -.005).sort((a, b) => a.p24 - b.p24).slice(0, 3) }; }

function fitHomePack() {
  // On a phone the pack is the page: it takes every bit of height the controls under it leave, up to the full width.
  const col = document.querySelector("#homePack"), bt = $("btabs"); if (!col || view !== "home") return; const pc = col.closest(".packcol") || col, was = pc.style.width; pc.style.width = "";
  if (bt && getComputedStyle(bt).display !== "none") {
    const shown = e => e && !e.hidden && getComputedStyle(e).display !== "none", gap = parseFloat(getComputedStyle(pc.parentNode).rowGap) || 10;
    const top = pc.getBoundingClientRect().top, bottom = bt.getBoundingClientRect().top - 8, after = ["openBtn", "homeTrust"].map(id => $(id)).filter(shown).reduce((a, e) => a + e.offsetHeight + gap, 0);
    pc.style.width = Math.floor(Math.max(120, Math.min(innerWidth - 28, 460, (bottom - top - after) / 1.5))) + "px";
  }
  pc.parentNode.style.setProperty("--pt", pc.offsetTop + "px");                                              // where the pack starts: a goal to claim floats over its top edge instead of pushing it down
  if (pc.style.width !== was && col._ps) col._ps.fit();                                                         // the picture in the pack is redrawn at its new size
}
addEventListener("resize", () => { if (view === "home") fitHomePack(); });
function renderHome() {
  const pk = curPack(), ps = packStats(pk); $("banner").textContent = BANNER.join("\n");
  $("packTabs").live = PACKS.map(p => `<button role="tab" class="ptab${p.id === pk.id ? " on" : ""}" data-pack="${p.id}" style="--pc:${p.col}" aria-selected="${p.id === pk.id}" aria-label="${esc(p.name)}, ${money(packPrice(p))}"><b>${money(packPrice(p)).replace(/\.00$/, "")}</b></button>`).join("");
  $("packName").textContent = pk.name; $("packBlurb").textContent = pk.blurb;
  const fp = state.freePacks, pp = boughtOf(pk.id); { noteFound(); const inSet = LIVE.filter(c => inPack(pk, c)); $("packLine").innerHTML = `7 cards · ${money(ps.price)}${state.s.packs ? ` · ${inSet.filter(c => state.found[c.no]).length}/${inSet.length} found` : ""} · <a class="linkbtn" href="#/odds">odds</a>`; } const fpk = freeOk(pk) ? fp : 0; const lab = fpk ? `open your free pack${fp > 1 ? " · " + fp + " left" : ""}` : pp ? `open a pack you bought${pp > 1 ? " · " + pp + " left" : ""}` : (Shop.cash() && state.coins < ps.price) ? "add money to open a pack" : (Shop.has(pk.id) && state.coins < ps.price) ? `buy a pack · ${rmoney(Shop.price(pk.id))}` : `open pack · ${money(ps.price)}`; { const i = lab.indexOf(" · "), ob = $("openBtn"), html = i < 0 ? `<span class="ob-t">${esc(lab)}</span>` : `<span class="ob-t">${esc(lab.slice(0, i))}</span><i class="ob-d"> · </i><b class="ob-p">${esc(lab.slice(i + 3))}</b>`; if (ob.dataset.sig !== html) { ob.dataset.sig = html; ob.innerHTML = html; } }   // the words, then what it costs in its own pill; read out, it is still one line ("open pack · $0.52")
  $("openBtn").classList.toggle("free", fpk > 0 || pp > 0); { const all = LIVE.filter(c => inPack(pk, c)), got = all.filter(c => copiesOf(c.no).length).length; $("homeFacts").textContent = `${got} of ${all.length} cards found`; }
  $("buyRow").hidden = !Shop.has(pk.id) || (!fpk && !pp && state.coins < ps.price); $("buyBtn").textContent = Shop.cash() ? "Add money" : `Buy packs · ${rmoney(Shop.price(pk.id))} each`;
  $("how").hidden = state.s.packs > 0; $("inviteBar").live = state.s.packs > 0 ? inviteBarHTML() : "";
  $("honest").live = `<span class="dsk">Every card is a picture made of text: the rarer the card, the more characters it holds. </span>About <b>${Math.round(ps.hit * 100)}%</b> of packs are worth at least what you pay. <a class="linkbtn" href="#/odds">See the odds</a>`;
  const mv = movers(); $("hot").live = `<span class="label">market right now</span>` + [mv.gain[0], mv.drop[0]].filter(Boolean).map(m => `<button class="mover mini" data-card="${m.c.no}"><span class="nm">${esc(m.c.name)}</span>${sparkSVG(m.s)}${pctHTML(m.p24)} <span class="dim">24h</span></button>`).join("") + `<a class="linkbtn" href="#/market">open the market</a>`;
  const bf = null; if (bf) $("hot").insertAdjacentHTML("beforeend", `<span class="hotflip">best flip this week: <b>${esc(bf.name)}</b> sold ${esc(bf.card.name)} ${pctHTML(bf.pct)} <span class="faint">simulated</span></span>`);
  $("chase").live = chaseHTML(); $("rqBar").live = "";      // the Requiem pack is for later: not on the pack page for now
  const hp = $("homePack"); if (hp.dataset.pack !== pk.id) { if (hp._ps) hp._ps.stop(); hp.innerHTML = packHTML(pk); hp.dataset.pack = pk.id; const el = hp.firstChild; tiltPack(el); el.style.cursor = "pointer"; el.onclick = () => { if (hp._swiped) { hp._swiped = false; return; } if (performance.now() - stageShut < 500) return; openPack(); }; hp._ps = liveWindow(el, pk); if (hp._dir) { el.animate([{ translate: `${hp._dir * 60}% 0`, opacity: 0, scale: ".9" }, { translate: "0 0", opacity: 1, scale: "1" }], { duration: 320, easing: "cubic-bezier(.2, .9, .3, 1.1)" }); hp._dir = 0; }
    if (!hp._sw) { hp._sw = 1; let x0 = null; hp.addEventListener("pointerdown", e => { x0 = e.clientX; }); hp.addEventListener("pointerup", e => { if (x0 == null) return; const dx = e.clientX - x0; x0 = null; if (Math.abs(dx) < 46 || PACKS.length < 2) return; const i = PACKS.findIndex(q => q.id === state.pack), nx = PACKS[(i + (dx < 0 ? 1 : -1) + PACKS.length) % PACKS.length]; hp._swiped = true; hp._dir = dx < 0 ? 1 : -1; setTimeout(() => { hp._swiped = false; }, 80); state.pack = nx.id; persist(); Snd.whoosh(); buzz(8); renderHome(); }); } }
  document.body.dataset.pack = pk.id; document.body.style.setProperty("--halo", `color-mix(in srgb, ${pk.col} 22%, transparent)`); document.body.style.setProperty("--halo2", `color-mix(in srgb, ${pk.col} 55%, transparent)`); { const ts = $("tStripe"); if (ts) ts.hidden = !Shop.open(); }
  { const hi = $("homeInvite"), html = homeInviteHTML(); hi.hidden = !html; hi.innerHTML = html; }
  { const hn = $("homeNext"), html = innerHeight >= 700 || Goals.ready().length ? Goals.homeHTML() : ""; hn.hidden = !html; if (hn.dataset.sig !== html) { hn.dataset.sig = html; hn.innerHTML = html; hn.className = "homenext" + (Goals.ready().length ? " rdy" : ""); } }   // what to aim for next (left out on a short screen unless there is something to claim)
  fitHomePack(); requestAnimationFrame(fitHomePack);
}

const flipRow = e => `<button class="flip" data-card="${e.card.no}"><span class="nm">${esc(e.name)} <span class="faint">sold ${esc(e.card.name)}</span></span><span class="pc">${pctHTML(e.pct)}</span><span class="dim">held ${e.hours}h · ${money(e.got)} → ${money(e.sold)} · ${e.gain >= 0 ? "+" : "−"}${money(Math.abs(e.gain))}</span></button>`;
const usd = n => n >= 1e9 ? "$" + (n / 1e9).toFixed(2) + "B" : n >= 1e6 ? "$" + (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + "M" : n >= 1e3 ? "$" + (n / 1e3).toFixed(n >= 1e5 ? 0 : 1) + "K" : "$" + Math.round(n);
const agoText = m => m === 0 ? "just now" : m < 60 ? m + " min ago" : m < 2880 ? Math.floor(m / 60) + "h ago" : Math.floor(m / 1440) + " days ago";
const whenText = h => h < 2 ? "just now" : h < 48 ? h + " hours ago" : Math.round(h / 24) + " days ago";
// the profile: your money, live, and every card you hold with its price and profit or loss
let awaySince = 0, pAll = false, pInviteSig = "", pRng = 864e5;
/* ---- selling many at once ----
   "Sell cards" above your cards turns the grid into a picker. Tap a card to mark every copy of it, or use a quick pick:
   extras (every copy but the best one of each card), under $1, everything that is not a hit, or all. A bar at the bottom
   says how many are marked and what they pay right now, and sells them in two taps: a sale is final, so the second tap is
   the "are you sure". */
let pSel = null, pSelAsk = 0;                                                              // the marked copies (null when not picking), and when the first of the two taps was made
const selHit = c => RAR[BY_NO[c.no].rar].tier >= 4 || !!c.fx;                                // legendary or better, or a styled copy
const SEL_QUICK = { extras: () => CARDS.flatMap(k => copiesOf(k.no).slice(1)), small: () => state.vault.filter(c => sellOf(c) < UNIT), low: () => state.vault.filter(c => !selHit(c)), all: () => state.vault.slice(), none: () => [] };
function selMode(on) { pSel = on ? new Set() : null; pSelAsk = 0; buzz(6); renderProfile(); }
function selCard(no) { if (!pSel) return; const cs = copiesOf(no), all = cs.every(c => pSel.has(c.uid)); cs.forEach(c => all ? pSel.delete(c.uid) : pSel.add(c.uid)); pSelAsk = 0; Snd.click(); buzz(4); renderProfile(); }
function selQuick(k) { if (!pSel || !SEL_QUICK[k]) return; pSel = new Set(SEL_QUICK[k]().map(c => c.uid)); pSelAsk = 0; Snd.click(); buzz(6); renderProfile(); }
function selGo() {
  if (!pSel) return; const uids = state.vault.filter(c => pSel.has(c.uid)).map(c => c.uid); if (!uids.length) return;
  if (Date.now() - pSelAsk > 6000) { pSelAsk = Date.now(); buzz(10); renderProfile(); setTimeout(() => { if (pSel && pSelAsk && Date.now() - pSelAsk >= 6000) { pSelAsk = 0; if (view === "profile") renderProfile(); } }, 6100); return; }   // first tap asks; it forgets after six seconds
  const g = sell(uids); pSel = null; pSelAsk = 0; soldToast(`Sold ${uids.length} card${uids.length === 1 ? "" : "s"} for ${money(g)}`, g); show(view, true);
}
// what your cards did while the app was closed (this visit only, and only if you were gone a while)
function awayLine() { if (!awaySince || Date.now() - awaySince < 30 * 60000 || !state.vault.length) return ""; let d = 0; for (const c of state.vault) if ((c.t || 0) < awaySince) d += valueOf(c) - Val.at(c, awaySince, true); const h = (Date.now() - awaySince) / 36e5; return Math.abs(d) < 1 ? "" : `<span>${signR(d, "while you were away " + (h >= 48 ? Math.round(h / 24) + " days" : h >= 1 ? Math.round(h) + "h" : Math.round(h * 60) + " min"))}</span>`; }
// iPhone only, and only in the browser: how to put it on the Home Screen. Shown until dismissed, never as a pop-up.
function tipHTML() { if (typeof Hap === "undefined" || !Hap.ios || navigator.standalone || (state.tg && state.tg.a2hs)) return ""; return `<div class="tip"><div><b>Make it an app</b><span>Tap Share in Safari, then “Add to Home Screen”. STIXX opens full screen from your Home Screen.</span></div><button class="x2" id="tipX" aria-label="Dismiss">×</button></div>`; }
function worthSeries(pts) {
  const h = state.hist, now = Date.now(), t0 = Math.max(h.length ? h[0][0] : now, now - 864e5); if (now - t0 < 90000) return null;
  const out = []; let j = 0; for (let i = 0; i < pts; i++) { const ts = t0 + (now - t0) * i / (pts - 1); while (j + 1 < h.length && h[j + 1][0] <= ts) j++; out.push(h[j][1]); } out[pts - 1] = netWorth();
  return { out, mins: Math.round((now - t0) / 60000) };
}
// money as people read it on a phone: cents, with "<$0.01" for anything smaller
const moneyR = u => money(Math.abs(u));
const signR = (u, label) => `<span class="${u > 0 ? "up" : u < 0 ? "dn" : "fl"}">${u > 0 ? "+" : u < 0 ? "−" : ""}${moneyR(u)}</span>${label ? ` <span class="dim">${label}</span>` : ""}`;
const pctR = p => `<small class="${p > .0005 ? "up" : p < -.0005 ? "dn" : "fl"}">${p > .0005 ? "▲" : p < -.0005 ? "▼" : "–"} ${Math.abs(p) >= 10 ? "×" + (1 + p).toFixed(0) : Math.round(Math.abs(p) * 100) + "%"}</small>`;
function renderProfile() {
  { const pa = $("pAcct"), h = Acct.html(); if (pa.dataset.sig !== h) { pa.dataset.sig = h; pa.innerHTML = h; } }
  $("pLimits").live = limitsHTML(); $("pSettings").live = settingsHTML(); $("pHist").live = History.html();
  $("pLive").live = Chart.heroHTML(); $("pFav").live = ""; $("pLive").live = "";
  const net = netWorth(), all = profitAll();
  { // who you are: a rank earned by finding cards and turning up, and the way to the settings
    const xp = xpOf(), ri = rankIdx(xp), cur = RANKS[ri], nx = RANKS[ri + 1], pc = nx ? (xp - cur[1]) / (nx[1] - cur[1]) : 1, a = Acct.me && Acct.me(), who = a && a.email ? a.email.split("@")[0] : "Player";
    $("pTop").live = `<div class="ptop"><span class="pt-av" aria-hidden="true">${esc(who[0].toUpperCase())}</span><div class="pt-who"><b>${esc(who)}</b><small><i>Lv ${ri + 1}</i> ${esc(cur[0])}${nx ? ` · ${nx[1] - xp} xp to ${esc(nx[0])}` : ""}</small><span class="pt-xp" role="img" aria-label="${xp} xp"><i style="width:${(pc * 100).toFixed(1)}%"></i></span></div><button class="pt-gear" data-pgear="1" aria-label="Limits and settings"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></svg></button></div>`; }
  { // what you have, what you have made over the range you picked, and its shape
    const now = Date.now(), h = state.hist, from = pRng ? now - pRng : (h.length ? h[0][0] : now), gain = pRng ? profitSince(pRng) : all, up = gain >= 0, N = 56, pts = [];
    let j = 0; for (let i = 0; i < N; i++) { const ts = from + (now - from) * i / (N - 1); while (j + 1 < h.length && h[j + 1][0] <= ts) j++; const e = h[j]; pts.push(e && e[0] <= ts ? e[1] - (e[2] || 0) - START : h.length ? h[0][1] - (h[0][2] || 0) - START : 0); } pts[N - 1] = all;
    const mn = Math.min(...pts), mx = Math.max(...pts), sp = Math.max(mx - mn, Math.max(4, Math.abs(net) * .004)), lo = (mn + mx) / 2 - sp / 2,     /* a quiet stretch is a line through the middle, not one stuck to the floor */ X = i => (i * 400 / (N - 1)).toFixed(1), Y = v => (104 - (v - lo) / sp * 88).toFixed(1), d = pts.map((v, i) => X(i) + " " + Y(v)).join(" L"), base = Y(pts[0]);
    const RNG = [[36e5, "1H"], [864e5, "1D"], [6048e5, "1W"], [0, "All"]], lbl = pRng === 36e5 ? "past hour" : pRng === 864e5 ? "today" : pRng ? "past week" : "all time";
    $("pWorth").live = `<div class="pf2 ${up ? "pos" : "neg"}"><span class="label">my collection</span><div class="bignum" role="img" aria-label="${money(all)}">${all >= 0 ? "+" : "−"}${moneyR(Math.abs(all))}</div>
      <div class="pf-row"><span class="pf-pill">${up ? "▲" : "▼"} ${moneyR(Math.abs(gain))}</span><span class="dim">${lbl}</span></div>
      <div class="pf-chart"><svg viewBox="0 0 400 112" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="pfG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="g0"/><stop offset="1" class="g1"/></linearGradient></defs><path class="b" d="M0 ${base} L400 ${base}"/><path class="a" d="M${d} L400 112 L0 112 Z" fill="url(#pfG)"/><path class="l" d="M${d}"/></svg><i class="pf-dot" style="top:${(Y(pts[N - 1]) / 112 * 100).toFixed(1)}%"></i></div>
      <div class="pf-rng" role="group" aria-label="Range">${RNG.map(([ms, t]) => `<button data-prng="${ms}" class="${ms === pRng ? "on" : ""}" aria-pressed="${ms === pRng}">${t}</button>`).join("")}</div>
      </div>${favShelf()}<div class="pf-stats"><div><b>${fmt(state.s.packs)}</b><small>packs opened</small></div><div><b>${new Set(state.vault.map(c => c.no)).size}/${LIVE.length}</b><small>cards found</small></div><div><b>${state.vault.length}</b><small>cards owned</small></div></div>`; }
  $("pGoals").live = Goals.html(); Goals.badge(); $("pTip").live = tipHTML();
  { const inf = typeof Ref !== "undefined" ? Ref.info() : null, sig = inf ? [inf.code, inf.joined, inf.invited, inf.earned, inf.credits, API.on].join("|") : "off";   // only rebuild the invite hero (and replay its bar) when the numbers change, not on every live tick
    if (sig !== pInviteSig) { pInviteSig = sig; $("pInvite").live = inviteHeroHTML(); if (typeof playRewardBars === "function") playRewardBars(); } }
  const groups = CARDS.map(c => { const cs = copiesOf(c.no); if (!cs.length) return null; return { c, n: cs.length, val: cs.reduce((a, x) => a + valueOf(x), 0), cost: cs.reduce((a, x) => a + costOf(x), 0), q: quickCopy(c.no), hot: cs.some(x => { const m = Val.moves(x, 6)[0]; return m && m.pct > .15; }), run: cs.some(x => Val.surge(x)) }; }).filter(Boolean).sort((a, b) => b.val - a.val);
  if (pSel) for (const u of [...pSel]) if (!state.vault.some(c => c.uid === u)) pSel.delete(u);
  const shown = pAll || pSel ? groups : groups.slice(0, 9);
  $("pTable").live = groups.length ? `<div class="pgrid">` + shown.map(g => { const top = copiesOf(g.c.no).reduce((a, x) => valueOf(x) > valueOf(a) ? x : a), p = g.val / Math.max(1, g.cost) - 1;
    const cs = copiesOf(g.c.no), nSel = pSel ? cs.filter(x => pSel.has(x.uid)).length : 0;
    if (pSel) return `<div class="hc pick${nSel ? " sel" : ""}" style="--rc:${top.fx ? STYLE_TINT[top.fx] : RAR[g.c.rar].col}"><button class="hc-main" data-selcard="${g.c.no}" aria-pressed="${!!nSel}" aria-label="${esc(g.c.name)}${nSel ? ", marked to sell" : ""}"><span class="hc-img"><img src="${imgOf(g.c, top.fx, true)}" alt="" loading="lazy" draggable="false">${g.n > 1 ? `<b class="hc-n">${nSel ? nSel + " of " + g.n : "×" + g.n}</b>` : ""}<i class="hc-ck" aria-hidden="true"></i></span><span class="hc-nm"><b>${esc(g.c.name)}</b><small>${g.c.retired ? "Retired" : esc(RAR[g.c.rar].name)}</small></span><b class="hc-px">${moneyR(cs.reduce((a, x) => a + sellOf(x), 0))}</b></button></div>`;
    return `<div class="hc${g.run ? " run" : ""}" style="--rc:${top.fx ? STYLE_TINT[top.fx] : RAR[g.c.rar].col}"><button class="hc-main" data-card="${g.c.no}" aria-label="${esc(g.c.name)}"><span class="hc-img"><img src="${imgOf(g.c, top.fx, true)}" alt="" loading="lazy" draggable="false">${g.n > 1 ? `<b class="hc-n">×${g.n}</b>` : ""}${g.run ? `<i class="hc-run">pumping</i>` : ""}<i class="hc-pct ${p > .0005 ? "up" : p < -.0005 ? "dn" : "fl"}">${p > .0005 ? "▲" : p < -.0005 ? "▼" : ""} ${Math.abs(p) >= 10 ? "×" + (1 + p).toFixed(0) : Math.round(Math.abs(p) * 100) + "%"}</i></span><span class="hc-nm"><b>${esc(g.c.name)}</b><small>${g.c.retired ? "Retired" : esc(RAR[g.c.rar].name)}</small></span><b class="hc-px" data-tick="g${g.c.no}" data-v="${g.val.toFixed(2)}">${moneyR(g.val)}</b></button><button class="hc-sell" data-qsell="${g.c.no}" aria-label="${esc(quickAria(g.c.no))}">${g.n > 1 ? "Sell 1" : "Sell"} · ${moneyR(sellOf(g.q))}</button></div>`; }).join("") + `</div>` + (groups.length > 9 && !pSel ? `<button class="linkbtn plain pall" id="pAllBtn">${pAll ? "Show fewer" : `Show all ${groups.length} cards`}</button>` : "") : "";
  $("pCardsH").textContent = groups.length ? `Your cards · ${state.vault.length}` : "Your cards";
  { const sb = $("pSelBtn"), bar = $("pSelBar"); if (pSel && !state.vault.length) pSel = null; sb.hidden = state.vault.length < 2; sb.textContent = pSel ? "Done" : "Sell cards"; sb.classList.toggle("on", !!pSel);
    const cnt = k => SEL_QUICK[k]().length, mine = pSel ? state.vault.filter(c => pSel.has(c.uid)) : [], tot = mine.reduce((a, c) => a + sellOf(c), 0), asking = pSelAsk && Date.now() - pSelAsk < 6000;
    $("pSelChips").live = pSel ? `<div class="selchips" role="group" aria-label="Quick picks">${[["extras", "Extras"], ["small", "Under $1"], ["low", "All but hits"], ["all", "All"]].filter(([k]) => cnt(k)).map(([k, t]) => `<button data-selq="${k}">${t} <small>${cnt(k)}</small></button>`).join("")}${mine.length ? `<button data-selq="none" class="clear">Clear</button>` : ""}</div>` : "";
    bar.hidden = !pSel; if (pSel) bar.live = mine.length ? `<div class="sb-t"><b>${mine.length} card${mine.length === 1 ? "" : "s"}</b><small>${asking ? "a sale can't be undone" : "you get " + moneyR(tot)}</small></div><button class="sb-go${asking ? " ask" : ""}" id="pSelGo">${asking ? `Tap again · ${moneyR(tot)}` : `Sell · ${moneyR(tot)}`}</button>` : `<div class="sb-t"><b>Pick cards to sell</b><small>tap a card, or use a quick pick</small></div><button class="sb-go" id="pSelGo" disabled>Sell</button>`;
    document.body.classList.toggle("picking", !!pSel && view === "profile"); }
  $("pNote").live = groups.length ? "" : `<div class="pempty"><svg class="pe-art" viewBox="0 0 64 88" aria-hidden="true"><rect x="3" y="3" width="58" height="82" rx="7"/><path d="M3 13h58M3 75h58"/><circle cx="32" cy="31" r="4.500" class="f"/><path d="M21 40 43 62M43 40 21 62" class="x"/></svg><b>No cards yet</b><span>Open a pack and your card lands here with a live price.</span><a class="btn solid" href="#/">Open a pack</a></div>`;
  $("pStats").textContent = state.s.packs ? `${state.s.packs} pack${state.s.packs === 1 ? "" : "s"} opened · ${moneyR(state.s.spent)} spent · ${moneyR(state.s.sold)} back from sales` : "";
  { const found = LIVE.filter(c => state.found[c.no]).length, rdy = Goals.ready().length, got = Object.keys(state.goals || {}).length, inf = typeof Ref !== "undefined" ? Ref.info() : null, set = (id, t, hot) => { const e = $(id); if (e.textContent !== t) e.textContent = t; e.classList.toggle("hot", !!hot); };
    set("pCollSub", `${found} of ${LIVE.length} found`); $("pCollBar").style.width = (found / LIVE.length * 100).toFixed(1) + "%";
    set("pGoalsSub", rdy ? `${rdy} to claim` : `${got} of ${Goals.LIST.length} done`, rdy); set("pInvSub", inf && inf.invited ? `${inf.invited} joined` : "Free packs for friends"); set("pHistSub", state.s.packs ? `${fmt(state.s.packs)} pack${state.s.packs === 1 ? "" : "s"} opened` : "Nothing yet"); }
}

let oddsKey = "";
function renderOdds(force) {
  if (!PACK_BY[oddsPack]) oddsPack = state.pack; const key = oddsPack; if (!force && key === oddsKey && $("oBody").firstChild) return; oddsKey = key; const opened = [...document.querySelectorAll("#oBody details")].map(d => d.open); const pk = PACK_BY[oddsPack], ps = packStats(pk), slotName = pk.slotNames;
  const rows = LIVE.filter(c => inPack(pk, c)).sort((a, b) => packHas(pk, b.id) - packHas(pk, a.id))        /* commonest first, so the list reads as the ladder */.map(c => { const p = packHas(pk, c.id); return cardRow(c, { nospark: true, price: p >= .1 ? Math.round(p * 100) + "%" : "1 in " + fmt(1 / p), pill: `<span class="small">${p >= .1 ? "of packs" : "packs"}</span>`, sub: `<b style="color:${RAR[c.rar].col};font-weight:650">${RAR[c.rar].name}</b> · starts at ${moneyS(c.val)}` }); }).join("");
  const tot = Object.values(STYLES).reduce((a, s) => a + s.p, 0);
  $("oBody").innerHTML = `
    <div class="packtabs" role="tablist" aria-label="Which pack">${PACKS.map(p => `<button role="tab" class="ptab${p.id === pk.id ? " on" : ""}" data-opack="${p.id}" style="--pc:${p.col}" aria-selected="${p.id === pk.id}" aria-label="${esc(p.name)}, ${money(packPrice(p))}"><b>${money(packPrice(p)).replace(/\.00$/, "")}</b></button>`).join("")}</div>
    <p class="small" style="margin:-4px 0 22px;text-align:center">${esc(pk.blurb)}</p>
    <div class="facts"><div><div class="bignum sm" role="img" aria-label="${money(ps.price)}">${money(ps.price)}</div><span>per ${esc(pk.name)} pack right now · ${pk.n === 1 ? "one card" : pk.n + " cards"}</span></div><div><div class="bignum sm" role="img" aria-label="${(ps.hit * 100).toFixed(0)}%">${(ps.hit * 100).toFixed(0) + "%"}</div><span>of packs are worth at least what you paid</span></div><div><div class="bignum sm" role="img" aria-label="${(ps.rtp * 100).toFixed(0)}%">${(ps.rtp * 100).toFixed(0) + "%"}</div><span>comes back on average when you sell</span></div></div>
    <h3 class="sec">What can be in a ${esc(pk.name)} pack</h3>
    <div class="clist">${rows}</div>
    <p class="small" style="margin-bottom:44px">Selling a card back pays 90% of its price. A typical pack sells back for ${money(ps.median)} right now.</p>
    <details><summary>How values work</summary><ul class="plain">
      <li>Every card comes out of the pack at its set starting value (shown above), times its style if it has one. The pack's odds and price never change.</li>
      <li>From then on each copy has a value of its own. Simulated AI buyers (bots, not people) trade every copy separately, around the clock: it drifts, rushes up when buyers pile in, and drops when they dump it. Rushes fade over a few days.</li>
      <li>Buyers judge each copy by small details of that copy, and some are worth more to them than others. Which details matter isn't listed anywhere: learning it is the skill, and even a copy buyers like can fall.</li>
      <li>On average a copy drifts a little down while you hold it, so a pack's cards are not a sure thing to hold. A copy can lose most of its value or climb many times over.</li>
      <li>Selling pays 90% of a copy's value, whenever you like. Everything here is play money with no cash value.</li></ul></details>
    <p class="small">When you open one pack you pick one of five face-down cards. Each of the five is drawn the same way from the table below, so whichever one you pick has exactly these odds: picking is your choice, not a way to change them. The four you leave are never made.</p>
    <details><summary>How each card in the pack is picked</summary><div>${pk.slots.map((s, i) => { const t = s.reduce((a, [, w]) => a + w, 0); return `<div class="slot"><div class="label">${slotName[i]}</div>${s.map(([id, w]) => `<div class="row"><span>${esc(BY_ID[id].name)} <span class="faint">${esc(BY_ID[id].sub)}</span></span><span class="bar">${bar(w / t, 24)}</span><span class="pct">${(w / t * 100).toFixed(1)}%</span></div>`).join("")}</div>`; }).join("")}</div></details>
    <details><summary>Styles</summary><div><p class="small" style="margin-bottom:14px">Every card can come out in one of twelve ASCII styles, decided by that copy's own code. ${(tot * 100).toFixed(1)}% of cards are not the plain default. A styled copy is worth its multiple of the card, so a styled Reaper is worth a lot more than a plain one.</p>
      <div class="tablewrap"><table><thead><tr><th>Style</th><th class="r">Chance per card</th><th class="r">Worth</th></tr></thead><tbody><tr><td>Plain <span class="faint">default</span></td><td class="r num">${((1 - tot) * 100).toFixed(1)}%</td><td class="r">×1</td></tr>${Object.keys(STYLES).map(k => `<tr><td>${STYLES[k].name}</td><td class="r num">1 in ${fmt(1 / STYLES[k].p)}</td><td class="r">×${STYLES[k].x}</td></tr>`).join("")}</tbody></table></div></div></details>
    <details><summary>Copy ids and the red slashes</summary><ul class="plain"><li>Every copy has its own id, like <b>IS015-000003-A2JM</b>: the set, the card number, the copy's serial and four check characters.</li><li>The red slashes after an id show rarity: none for commons and uncommons, one for rares and epics, two for legendary, three for mythic, four for the one Secret card.</li><li>The style a copy comes out in is fixed by its id, so a printed card and its digital twin always match.</li></ul></details>
    <details><summary>Fair play</summary><ul class="plain"><li>A pack is worth less than it costs on average, and the numbers above are worked out exactly from the odds and today's prices.</li><li>Every pack is drawn from a seed that was committed to before you opened it, so you can check afterwards that the cards followed the odds above. <button class="linkbtn" id="fairBtn2">Check your packs</button></li><li>The odds never change with what you have spent, pulled or been given.</li><li>The money is play money. Nothing is ever charged and nothing can be cashed out.</li></ul></details>`;
  document.querySelectorAll("#oBody details").forEach((d, i) => { if (opened[i]) d.open = true; });
}
function show(v, keep) {
  if (v !== "profile" && pSel) { pSel = null; pSelAsk = 0; } if (v !== "profile") document.body.classList.remove("picking");                                                  // keep: draw the page again where you are (after selling, say) instead of jumping back to the top
  view = VIEWS.includes(v) ? v : "home"; document.body.classList.toggle("on-home", view === "home");
  if (view === "odds") oddsKey = ""; VIEWS.forEach(x => $("v-" + x).classList.toggle("on", x === view)); document.querySelectorAll("#tabs a, #btabs a").forEach(a => a.classList.toggle("on", a.dataset.v === (TAB_OF[view] || view)));
  ({ home: renderHome, live: Live.render, market: renderMarket, profile: renderProfile, collection: renderCollection, odds: renderOdds, invite: renderInvite, limited: renderLimited })[view](); if (!keep) scrollTo(0, 0);
}
function route() { const h = location.hash.replace(/^#\/?/, ""); if (h === "fresh") { startOver(); state.seenIntro = false; state.ageOK = false; state.pack = "fp"; persist(); location.replace(location.pathname + "#/"); location.reload(); return; }   // /#/fresh: start again as a brand-new player (the age check and the intro come back too)
 show(h === "vault" || h === "index" ? "collection" : h || "home"); }
// the market moved: redraw whatever is on screen without jumping the page
function refreshLive() {
  if (SS || !$("share").hidden || !$("cut").hidden || view === "invite" || view === "limited") return; ({ home: renderHome, live: Live.render, market: renderMarket, profile: renderProfile, collection: renderCollection, odds: renderOdds })[view]();
  if (modalNo && !$("modal").hidden) cardModal(modalNo, true);   // updated in place: the buttons you are pressing stay where they are
  if (typeof Tick !== "undefined") Tick.scan();
}

/* ---- the card window ---- */
function openModal(html, slim, keep) { $("mbox").className = "mbox" + (slim ? " slim" : ""); const full = `<button class="x" data-close aria-label="Close">×</button>` + html; if (keep) put($("mbox"), full); else $("mbox").innerHTML = full; $("modal").hidden = false; }
const closeModal = () => { try { Shop.drop(); } catch (e) {} $("modal").hidden = true; $("mbox").innerHTML = ""; modalNo = null; };
function cardModal(no, keep) {
  modalNo = no; const card = BY_NO[no], R = RAR[card.rar], cs = copiesOf(no), best = cs[0], gone = best ? null : Chart.lastSold(no), p = packP(card.id), have = new Set(cs.map(c => c.fx)), keys = [""].concat(Object.keys(STYLES));
  const styles = card.styles ? `<div><div class="label" style="margin-bottom:8px">Styles found: ${keys.filter(k => have.has(k)).length} of ${keys.length}</div><div class="stylerow">${keys.map(k => `<figure class="${have.has(k) ? "" : "off"}" title="${styleName(k)}${k ? " · 1 in " + fmt(1 / STYLES[k].p) + " · ×" + STYLES[k].x : ""}"><img src="${imgOf(card, k, true)}" alt="" loading="lazy"><figcaption>${styleName(k)}</figcaption></figure>`).join("")}</div></div>` : "";
  const hrs = best ? Math.min(168, Math.max(1, (Date.now() - (best.t || Date.now())) / 36e5)) : 0, ser = best ? Val.series(best, hrs, 56) : null, now = best ? valueOf(best) : card.val, mv = best ? Val.moves(best, 72)[0] : null;
  const copies = cs.length ? `<div><div class="label" style="margin-bottom:8px">Your ${cs.length === 1 ? "copy" : "copies"}</div><div class="copies">${cs.map(c => `<div class="copy"><div class="ci">${idHTML(c.code, card.rar)}<small>${styleName(c.fx)}${c.fx ? " · ×" + STYLES[c.fx].x : ""} · ${c.phys ? "added" : "pulled"} ${new Date(c.t).toLocaleDateString()} · cost ${moneyS(costOf(c))}</small></div><div class="r"><span class="cv"><b>${moneyS(valueOf(c))}</b>${pill(gainOf(c))}</span>${replayable(c) ? `<button class="btn small ghost" data-share="${c.uid}">replay &amp; share</button>` : ""}<button class="btn small sellb" data-sell="${c.uid}" data-no="${no}" aria-label="Sell ${esc(card.name)} for ${money(sellOf(c))}, after the 10% fee">Sell for ${money(sellOf(c))}</button></div></div>`).join("")}</div></div>` : `<div class="notyet"><b>${gone ? "You sold your copy." : "You haven't found this card yet."}</b><span class="small">${card.retired ? "No pack holds it any more." : "It turns up in " + chance(p, packOf(card)) + "."}</span><button class="btn small solid" data-open data-close>open a pack</button></div>`;
  openModal(`<div class="mcard" style="--glow:${best && best.fx ? STYLE_TINT[best.fx] : R.tier ? R.col : card.tint}">${cardHTML(best || { no }, { locked: !best })}</div><div class="minfo">
    <div class="mhead"><span class="label" style="color:${R.col}">${rarLabel(card)} · No. ${card.no}</span><h2>${esc(card.name)} ${best ? favBtn(card.no) : ""}</h2>
      <div class="pricebox">${best ? `<b data-tick="m${card.no}" data-v="${now.toFixed(2)}">${moneyS(now)}</b><div class="chgs"><span>${pill(Val.pct(best, 24))}<small>today</small></span><span>${pill(gainOf(best))}<small>since you pulled it</small></span></div>` : `<b>${moneyS(card.val)}</b><span class="dim">starting value</span>`}</div></div>
    ${copies}
    ${gone ? `<div class="mk"><div class="label">The copy you sold · still trading</div>${Chart.html(gone)}</div>` : ""}
    ${best ? `<div class="mk"><div class="label">Your ${cs.length > 1 ? "best " : ""}copy · live</div>${Chart.html(best)}<div class="small">${Val.watching(best)} AI buyers watching${mv ? ` · ${mv.ago ? mv.ago + "h ago" : "this hour"} buyers ${mv.pct > 0 ? "rushed in" : "dumped it"} ${pctShort(mv.pct)}` : ""} · simulated</div></div>` : ""}
    <p class="dim facts">${fmt(card.chars)} characters · starts at ${money(card.val)} · ${card.retired ? "retired: no pack holds it any more" : "turns up in " + chance(p, packOf(card))}${card.cap ? `<br>“${esc(card.cap)}”` : ""}</p>
    ${Cut.has(card.id) ? `<div><button class="btn small" data-cut="${card.id}">▶ ${cs.length ? "Watch" : "Preview"} its cutscene</button></div>` : ""}
    ${styles}</div>`, false, keep); Chart.start(); if (best) Alive.on($("mbox").querySelector(".mcard .card"), best);
}
/* ---- selling: one tap, and a few seconds to take it back ---- */
let lastSale = null;
function sell(uids) {
  let g = 0, realized = 0; const copies = [];
  for (const u of uids) { const c = state.vault.find(x => x.uid === u); if (c) { c._got = sellOf(c); g += c._got; realized += c._got - costOf(c); state.s.bestX = Math.max(state.s.bestX || 0, sellOf(c) / Math.max(1, Val.startOf(c))); copies.push(c);
      (state.sold = state.sold || []).unshift({ uid: c.uid, no: c.no, code: c.code, serial: c.serial, fx: c.fx || "", t: c.t, cost: costOf(c), ts: Date.now(), at: valueOf(c), got: sellOf(c) }); if (state.sold.length > 60) state.sold.length = 60;                                                          /* the copy lives on as a record: where you got it, where you sold it, and what it did next */ state.vault = state.vault.filter(x => x !== c); } }
  if (g && API.on) copies.map(c => ({ c, got: Math.floor(c._got), start: Val.startOf(c) })).filter(x => x.got >= x.start * 1.5 && x.got - x.start >= 250).sort((a, b) => (b.got - b.start) - (a.got - a.start)).slice(0, 3).forEach(x => API.post("flip", { uid: state.uid, c: { no: x.c.no, code: x.c.code, uid: x.c.uid, serial: x.c.serial, fx: x.c.fx || "", t: x.c.t }, got: x.got }).then(() => { if (typeof Live !== "undefined") Live.pull(true); }));   // a real flip goes on the Live tab: the server prices the copy itself before listing it
  if (g) { state.coins += g; state.s.sold += g; state.s.realized += realized; state.s.nSold = (state.s.nSold || 0) + copies.length; lastSale = { copies, g, realized, at: Date.now() }; save(); renderBal(true); Snd.sell(); buzz([25, 35, 25]); if (typeof coinBurst === "function") coinBurst(lastTap, 3 + Math.min(6, copies.length)); Goals.badge(); }
  return g;
}
const soldToast = (msg, g) => toast(msg || "Sold for " + money(g));                        // a sale is final: no undo
// the copy a quick sell gives up: your only copy, or the cheapest of several (so the best one stays)
const quickCopy = no => { const cs = copiesOf(no); return cs.length ? cs[cs.length - 1] : null; };
const quickLabel = no => { const c = quickCopy(no); return c ? `Sell${copiesOf(no).length > 1 ? " extra" : ""} · ${moneyS(sellOf(c))}` : ""; };
const quickAria = no => { const c = quickCopy(no), n = copiesOf(no).length; return c ? `Sell ${n > 1 ? "one extra " : ""}${BY_NO[no].name} for ${money(sellOf(c))}, after the 10% fee` : ""; };
const sellBtn = no => copiesOf(no).length ? `<button class="sellq" data-qsell="${no}" aria-label="${esc(quickAria(no))}">${esc(quickLabel(no))}</button>` : "";
// a replay is only worth watching when the card went up by more than half
const REPLAY_MIN = .5, replayable = c => gainOf(c) > REPLAY_MIN;
function quickSell(no) {
  const c = quickCopy(no); if (!c) return; const rec = receiptOf(c, true), g = sell([c.uid]); if (!g) return;
  soldToast("Sold " + BY_NO[no].name + " for " + money(g), g); if (!$("modal").hidden) closeModal(); show(view, true);      // selling never opens the replay
}
