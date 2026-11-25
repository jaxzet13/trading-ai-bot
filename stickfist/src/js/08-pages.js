/* ============================================================================
   7. PAGES: pack, market, collection, odds
   ========================================================================== */
// two tabs: the pack, and you (your money, your cards, the market); the other pages hang off those two
const VIEWS = ["home", "market", "profile", "collection", "odds", "invite", "limited"], TAB_OF = { home: "home", odds: "home", limited: "home", profile: "profile", market: "profile", collection: "profile", invite: "profile" }; let view = "home", modalNo = null, oddsPack = "";
const copiesOf = no => state.vault.filter(c => c.no === no).sort((a, b) => valueOf(b) - valueOf(a));
function renderBal(anim) { const el = $("bal"), from = +(el.dataset.v || state.coins); el.dataset.v = state.coins; if (anim) countTo(el, from, state.coins, money); else el.textContent = money(state.coins); if (typeof renderBroke === "function") renderBroke(); }

/* ---- the market's numbers, ready to show ---- */
// your copies, each with its own last day: the only market there is
function myMovers() { return state.vault.map(copy => { const s = Val.series(copy, 24, 24); return { c: BY_NO[copy.no], copy, s, now: valueOf(copy), was: s[0], p24: Val.pct(copy, 24) }; }); }
function movers() { const rows = myMovers(); return { rows, gain: rows.filter(r => r.p24 > .005).sort((a, b) => b.p24 - a.p24).slice(0, 3), drop: rows.filter(r => r.p24 < -.005).sort((a, b) => a.p24 - b.p24).slice(0, 3) }; }

function fitHomePack() {
  const col = document.querySelector("#homePack"), bt = $("btabs"); if (!col || view !== "home") return; const pc = col.closest(".packcol") || col; pc.style.width = "";
  if (!bt || getComputedStyle(bt).display === "none") return;                                               // only on a phone, where the page must not scroll
  const top = pc.getBoundingClientRect().top, bottom = bt.getBoundingClientRect().top - 10, after = ["packmeta", "openBtn", "multiRow", "homeTrust", "homeInvite", "homeNext"].map(id => { const e = id === "packmeta" ? document.querySelector(".packmeta") : $(id); return e && !e.hidden ? e.offsetHeight + 12 : 0; }).reduce((a, b) => a + b, 0);
  const ratio = pc.offsetHeight / Math.max(1, pc.offsetWidth) || 1.45, w = Math.max(100, Math.min(300, innerWidth * .74, (bottom - top - after) / ratio)); pc.style.width = Math.floor(w) + "px";
}
addEventListener("resize", () => { if (view === "home") fitHomePack(); });
function renderHome() {
  const pk = curPack(), ps = packStats(pk); $("banner").textContent = BANNER.join("\n");
  $("packTabs").live = PACKS.map(p => `<button role="tab" class="ptab${p.id === pk.id ? " on" : ""}" data-pack="${p.id}" aria-selected="${p.id === pk.id}"><b>${esc(p.name)}</b><span>${money(packPrice(p))}</span></button>`).join("");
  $("packName").textContent = pk.name; $("packBlurb").textContent = pk.blurb;
  const fp = state.freePacks, pp = boughtOf(pk.id); { noteFound(); const inSet = LIVE.filter(c => c.set === pk.set); $("packLine").innerHTML = `${pk.n === 1 ? "1 card" : pk.n + " cards"} · ${money(ps.price)}${state.s.packs ? ` · ${inSet.filter(c => state.found[c.no]).length}/${inSet.length} found` : ""} · <a class="linkbtn" href="#/odds">odds</a>`; } const mk = Math.min(openN(), maxN(pk)), many = mk >= 2; $("openBtn").textContent = many ? `open ${mk} packs${(() => { const c = Math.max(0, mk - fp - pp) * ps.price; return c ? " · " + money(c) : ""; })()}` : fp ? `open your free pack${fp > 1 ? " · " + fp + " left" : ""}` : pp ? `open a pack you bought${pp > 1 ? " · " + pp + " left" : ""}` : (Shop.cash() && state.coins < ps.price) ? "add money to open a pack" : (Shop.has(pk.id) && state.coins < ps.price) ? `buy a pack · ${rmoney(Shop.price(pk.id))}` : `open pack · ${money(ps.price)}`; $("openBtn").classList.toggle("free", fp > 0 || pp > 0);
  { const r = $("multiRow"), top = maxN(pk), opts = MANY.filter(n => n === 1 || n <= top); r.hidden = top < 2; r.innerHTML = `<span class="small dim">open at once</span>` + opts.map(n => `<button type="button" class="seg1${n === Math.min(openN(), top) ? " on" : ""}" data-many="${n}" aria-pressed="${n === Math.min(openN(), top)}">${n}</button>`).join(""); }
  $("buyRow").hidden = !Shop.has(pk.id) || (!fp && !pp && state.coins < ps.price); $("buyBtn").textContent = Shop.cash() ? "Add money" : `Buy packs · ${rmoney(Shop.price(pk.id))} each`;
  $("how").hidden = state.s.packs > 0; $("inviteBar").live = state.s.packs > 0 ? inviteBarHTML() : "";
  $("honest").live = `<span class="dsk">Every card is a picture made of text: the rarer the card, the more characters it holds. </span>About <b>${Math.round(ps.hit * 100)}%</b> of packs are worth at least what you pay. <a class="linkbtn" href="#/odds">See the odds</a>`;
  const mv = movers(); $("hot").live = `<span class="label">market right now</span>` + [mv.gain[0], mv.drop[0]].filter(Boolean).map(m => `<button class="mover mini" data-card="${m.c.no}"><span class="nm">${esc(m.c.name)}</span>${sparkSVG(m.s)}${pctHTML(m.p24)} <span class="dim">24h</span></button>`).join("") + `<a class="linkbtn" href="#/market">open the market</a>`;
  const bf = null; if (bf) $("hot").insertAdjacentHTML("beforeend", `<span class="hotflip">best flip this week: <b>${esc(bf.name)}</b> sold ${esc(bf.card.name)} ${pctHTML(bf.pct)} <span class="faint">simulated</span></span>`);
  $("chase").live = chaseHTML(); $("rqBar").live = "";      // the Requiem pack is for later: not on the pack page for now
  const hp = $("homePack"); if (hp.dataset.pack !== pk.id) { if (hp._ps) hp._ps.stop(); hp.innerHTML = packHTML(pk); hp.dataset.pack = pk.id; const el = hp.firstChild; tiltPack(el); el.style.cursor = "pointer"; el.onclick = () => openPack(); hp._ps = liveWindow(el, pk); }
  document.body.dataset.pack = pk.id; { const ts = $("tStripe"); if (ts) ts.hidden = !Shop.open(); }
  { const hi = $("homeInvite"), html = homeInviteHTML(); hi.hidden = !html; hi.innerHTML = html; }
  { const hn = $("homeNext"), html = innerHeight >= 700 || Goals.ready().length ? Goals.homeHTML() : ""; hn.hidden = !html; if (hn.dataset.sig !== html) { hn.dataset.sig = html; hn.innerHTML = html; hn.className = "homenext" + (Goals.ready().length ? " rdy" : ""); } }   // what to aim for next (left out on a short screen unless there is something to claim)
  fitHomePack(); requestAnimationFrame(fitHomePack);
}

const flipRow = e => `<button class="flip" data-card="${e.card.no}"><span class="nm">${esc(e.name)} <span class="faint">sold ${esc(e.card.name)}</span></span><span class="pc">${pctHTML(e.pct)}</span><span class="dim">held ${e.hours}h · ${money(e.got)} → ${money(e.sold)} · ${e.gain >= 0 ? "+" : "−"}${money(Math.abs(e.gain))}</span></button>`;
const usd = n => n >= 1e9 ? "$" + (n / 1e9).toFixed(2) + "B" : n >= 1e6 ? "$" + (n / 1e6).toFixed(n >= 1e8 ? 0 : 1) + "M" : n >= 1e3 ? "$" + (n / 1e3).toFixed(n >= 1e5 ? 0 : 1) + "K" : "$" + Math.round(n);
const agoText = m => m === 0 ? "just now" : m < 60 ? m + " min ago" : m < 2880 ? Math.floor(m / 60) + "h ago" : Math.floor(m / 1440) + " days ago";
const whenText = h => h < 2 ? "just now" : h < 48 ? h + " hours ago" : Math.round(h / 24) + " days ago";
// the profile: your money, live, and every card you hold with its price and profit or loss
// what the cards you hold now were worth over the last hours: each copy's own path, at its starting value before you pulled it
let pRange = 24, awaySince = 0, pAll = false, pInviteSig = "";
function cardsSeries(hours, n) { const v = state.vault; if (!v.length) return null; const t = Date.now(), out = []; for (let i = 0; i < n; i++) { const ti = t - hours * 36e5 * (1 - i / (n - 1)); let s = 0; for (const c of v) s += ti <= (c.t || 0) ? Val.startOf(c) : Val.at(c, ti, i < n - 1); out.push(s); } return out; }
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
  const net = netWorth(), hold = holdingsValue(), basis = state.vault.reduce((a, c) => a + costOf(c), 0), all = profitAll(), d24 = profitSince(864e5), found = new Set(state.vault.map(c => c.no)).size;
  $("pWorth").live = `<div class="worth"><div class="bignum" role="img" aria-label="${money(net)}" data-tick="net" data-v="${Math.round(net)}">${moneyR(net)}</div><div class="wmeta"><span>${signR(all, "since you started")}</span>${Math.abs(d24) >= 5 ? `<span>${signR(d24, "today")}</span>` : ""}${awayLine()}</div></div>
    <div class="wsplit"><div><span class="label">cash</span><b>${moneyR(state.coins)}</b></div><div><span class="label">your cards</span><b>${moneyR(hold)}</b></div><div><span class="label">made on sales</span><b>${signR(state.s.realized)}</b></div></div>`;
  const cs = cardsSeries(pRange, 72);
  $("pChart").live = cs ? `<div class="mk"><div class="row chead"><span class="label">Your cards · ${pRange === 24 ? "last 24 hours" : "last 7 days"} ${pill(cs[cs.length - 1] / Math.max(1, cs[0]) - 1)}</span><span class="seg mini" role="group"><button data-prange="24" class="${pRange === 24 ? "on" : ""}" aria-pressed="${pRange === 24}">24h</button><button data-prange="168" class="${pRange === 168 ? "on" : ""}" aria-pressed="${pRange === 168}">7d</button></span></div>${lineChart(cs, { fmt: money, h: 120 })}</div>` : "";
  $("pGoals").live = Goals.html(); Goals.badge(); $("pTip").live = tipHTML(); $("pRank").live = rankLine();
  { const inf = typeof Ref !== "undefined" ? Ref.info() : null, sig = inf ? [inf.code, inf.joined, inf.invited, inf.earned, inf.credits, API.on].join("|") : "off";   // only rebuild the invite hero (and replay its bar) when the numbers change, not on every live tick
    if (sig !== pInviteSig) { pInviteSig = sig; $("pInvite").live = inviteHeroHTML(); if (typeof playRewardBars === "function") playRewardBars(); } }
  const groups = CARDS.map(c => { const cs = copiesOf(c.no); if (!cs.length) return null; return { c, n: cs.length, val: cs.reduce((a, x) => a + valueOf(x), 0), cost: cs.reduce((a, x) => a + costOf(x), 0), q: quickCopy(c.no), hot: cs.some(x => { const m = Val.moves(x, 6)[0]; return m && m.pct > .15; }) }; }).filter(Boolean).sort((a, b) => b.val - a.val);
  const shown = pAll ? groups : groups.slice(0, 6);
  $("pTable").live = groups.length ? shown.map(g => `<div class="mrow"><button class="mmain" data-card="${g.c.no}" aria-label="${esc(g.c.name)}">${thumb(g.c)}<span class="mn"><b>${esc(g.c.name)}${g.hot ? ` <i class="rush" title="AI buyers rushed into a copy in the last few hours">buyers in</i>` : ""}</b><small>${g.n > 1 ? `×${g.n} · ` : ""}${rarLabel(g.c)}</small></span><span class="mp"><b data-tick="g${g.c.no}" data-v="${g.val.toFixed(2)}">${moneyR(g.val)}</b>${pctR(g.val / Math.max(1, g.cost) - 1)}</span></button><button class="msell" data-qsell="${g.c.no}" aria-label="${esc(quickAria(g.c.no))}">${g.n > 1 ? "Sell 1" : "Sell"}<small>${moneyR(sellOf(g.q))}</small></button></div>`).join("") + (groups.length > 6 ? `<button class="linkbtn plain pall" id="pAllBtn">${pAll ? "Show fewer" : `Show all ${groups.length} cards`}</button>` : "") + `<div class="mtot"><span>All your cards</span><b>${moneyR(hold)}</b></div>` : "";
  $("pNote").innerHTML = groups.length ? `Tap a card for its chart. <span class="faint">${state.s.packs} pack${state.s.packs === 1 ? "" : "s"} opened · ${moneyR(state.s.spent)} spent · ${moneyR(state.s.sold)} back from sales</span>` : `No cards yet. <a class="linkbtn" href="#/">Open a pack</a> and they show up here with a live price.`;
  const rows = movers().rows.slice().sort((a, b) => Math.abs(b.p24) - Math.abs(a.p24)).slice(0, 4); $("pMktH").hidden = !rows.length;
  $("pMkt").live = rows.map(m => `<button class="mover mini" data-card="${m.c.no}"><span class="nm">${esc(m.c.name)}</span>${sparkSVG(m.s)}${pctHTML(m.p24)}<span class="dim">24h</span></button>`).join("");
  $("pLinks").live = `<a class="linkbtn plain" href="#/collection">All ${LIVE.length} cards · ${LIVE.filter(c => state.found[c.no]).length} found ›</a><a class="linkbtn plain" href="#/market">All movers ›</a>`;
}

let oddsKey = "";
function renderOdds(force) {
  if (!PACK_BY[oddsPack]) oddsPack = state.pack; const key = oddsPack; if (!force && key === oddsKey && $("oBody").firstChild) return; oddsKey = key; const opened = [...document.querySelectorAll("#oBody details")].map(d => d.open); const pk = PACK_BY[oddsPack], ps = packStats(pk), slotName = pk.slotNames;
  const rows = LIVE.filter(c => c.set === pk.set).sort((a, b) => a.chars - b.chars).map(c => { const p = packP(c.id); return cardRow(c, { nospark: true, price: p >= .1 ? Math.round(p * 100) + "%" : "1 in " + fmt(1 / p), pill: `<span class="small">${p >= .1 ? "of packs" : "packs"}</span>`, sub: `starts at ${moneyS(c.val)} · ${fmt(c.chars)} characters` }); }).join("");
  const tot = Object.values(STYLES).reduce((a, s) => a + s.p, 0);
  $("oBody").innerHTML = `
    <div class="packtabs" role="tablist" aria-label="Which pack">${PACKS.map(p => `<button role="tab" class="ptab${p.id === pk.id ? " on" : ""}" data-opack="${p.id}" aria-selected="${p.id === pk.id}"><b>${esc(p.name)}</b><span>${money(packPrice(p))}</span></button>`).join("")}</div>
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
    <details><summary>How each card in the pack is picked</summary><div>${pk.slots.map((s, i) => { const t = s.reduce((a, [, w]) => a + w, 0); return `<div class="slot"><div class="label">${slotName[i]}</div>${s.map(([id, w]) => `<div class="row"><span>${esc(BY_ID[id].name)} <span class="faint">${esc(BY_ID[id].sub)}</span></span><span class="bar">${bar(w / t, 24)}</span><span class="pct">${(w / t * 100).toFixed(1)}%</span></div>`).join("")}</div>`; }).join("")}</div></details>
    <details><summary>Styles</summary><div><p class="small" style="margin-bottom:14px">Every card can come out in one of twelve ASCII styles, decided by that copy's own code. ${(tot * 100).toFixed(1)}% of cards are not the plain default. A styled copy is worth its multiple of the card, so a styled Reaper is worth a lot more than a plain one.</p>
      <div class="tablewrap"><table><thead><tr><th>Style</th><th class="r">Chance per card</th><th class="r">Worth</th></tr></thead><tbody><tr><td>Plain <span class="faint">default</span></td><td class="r num">${((1 - tot) * 100).toFixed(1)}%</td><td class="r">×1</td></tr>${Object.keys(STYLES).map(k => `<tr><td>${STYLES[k].name}</td><td class="r num">1 in ${fmt(1 / STYLES[k].p)}</td><td class="r">×${STYLES[k].x}</td></tr>`).join("")}</tbody></table></div></div></details>
    <details><summary>Copy ids and the red slashes</summary><ul class="plain"><li>Every copy has its own id, like <b>IS015-000003-A2JM</b>: the set, the card number, the copy's serial and four check characters.</li><li>The red slashes after an id show rarity: none for commons and uncommons, one for rares and epics, two for legendary, three for mythic, four for the one Secret card.</li><li>The style a copy comes out in is fixed by its id, so a printed card and its digital twin always match.</li></ul></details>
    <details><summary>Fair play</summary><ul class="plain"><li>A pack is worth less than it costs on average, and the numbers above are worked out exactly from the odds and today's prices.</li><li>Every pack is drawn from a seed that was committed to before you opened it, so you can check afterwards that the cards followed the odds above. <button class="linkbtn" id="fairBtn2">Check your packs</button></li><li>The odds never change with what you have spent, pulled or been given.</li><li>The money is play money. Nothing is ever charged and nothing can be cashed out.</li></ul></details>`;
  document.querySelectorAll("#oBody details").forEach((d, i) => { if (opened[i]) d.open = true; });
}
function show(v, keep) {                                                  // keep: draw the page again where you are (after selling, say) instead of jumping back to the top
  view = VIEWS.includes(v) ? v : "home"; document.body.classList.toggle("on-home", view === "home");
  if (view === "odds") oddsKey = ""; VIEWS.forEach(x => $("v-" + x).classList.toggle("on", x === view)); document.querySelectorAll("#tabs a, #btabs a").forEach(a => a.classList.toggle("on", a.dataset.v === (TAB_OF[view] || view)));
  ({ home: renderHome, market: renderMarket, profile: renderProfile, collection: renderCollection, odds: renderOdds, invite: renderInvite, limited: renderLimited })[view](); if (!keep) scrollTo(0, 0);
}
function route() { const h = location.hash.replace(/^#\/?/, ""); show(h === "vault" || h === "index" ? "collection" : h || "home"); }
// the market moved: redraw whatever is on screen without jumping the page
function refreshLive() {
  if (SS || !$("share").hidden || !$("cut").hidden || view === "invite" || view === "limited") return; ({ home: renderHome, market: renderMarket, profile: renderProfile, collection: renderCollection, odds: renderOdds })[view]();
  if (modalNo && !$("modal").hidden) cardModal(modalNo, true);   // updated in place: the buttons you are pressing stay where they are
  if (typeof Tick !== "undefined") Tick.scan();
}

/* ---- the card window ---- */
function openModal(html, slim, keep) { $("mbox").className = "mbox" + (slim ? " slim" : ""); const full = `<button class="x" data-close aria-label="Close">×</button>` + html; if (keep) put($("mbox"), full); else $("mbox").innerHTML = full; $("modal").hidden = false; }
const closeModal = () => { try { Shop.drop(); } catch (e) {} $("modal").hidden = true; $("mbox").innerHTML = ""; modalNo = null; };
function cardModal(no, keep) {
  modalNo = no; const card = BY_NO[no], R = RAR[card.rar], cs = copiesOf(no), best = cs[0], p = packP(card.id), have = new Set(cs.map(c => c.fx)), keys = [""].concat(Object.keys(STYLES));
  const styles = card.styles ? `<div><div class="label" style="margin-bottom:8px">Styles found: ${keys.filter(k => have.has(k)).length} of ${keys.length}</div><div class="stylerow">${keys.map(k => `<figure class="${have.has(k) ? "" : "off"}" title="${styleName(k)}${k ? " · 1 in " + fmt(1 / STYLES[k].p) + " · ×" + STYLES[k].x : ""}"><img src="${imgOf(card, k, true)}" alt="" loading="lazy"><figcaption>${styleName(k)}</figcaption></figure>`).join("")}</div></div>` : "";
  const hrs = best ? Math.min(168, Math.max(1, (Date.now() - (best.t || Date.now())) / 36e5)) : 0, ser = best ? Val.series(best, hrs, 56) : null, now = best ? valueOf(best) : card.val, mv = best ? Val.moves(best, 72)[0] : null;
  const copies = cs.length ? `<div><div class="label" style="margin-bottom:8px">Your ${cs.length === 1 ? "copy" : "copies"}</div><div class="copies">${cs.map(c => `<div class="copy"><div class="ci">${idHTML(c.code, card.rar)}<small>${styleName(c.fx)}${c.fx ? " · ×" + STYLES[c.fx].x : ""} · ${c.phys ? "added" : "pulled"} ${new Date(c.t).toLocaleDateString()} · cost ${moneyS(costOf(c))}</small></div><div class="r"><span class="cv"><b>${moneyS(valueOf(c))}</b>${pill(gainOf(c))}</span>${replayable(c) ? `<button class="btn small ghost" data-share="${c.uid}">replay &amp; share</button>` : ""}<button class="btn small sellb" data-sell="${c.uid}" data-no="${no}" aria-label="Sell ${esc(card.name)} for ${money(sellOf(c))}, after the 10% fee">Sell for ${money(sellOf(c))}</button></div></div>`).join("")}</div></div>` : `<div class="notyet"><b>You haven't found this card yet.</b><span class="small">It turns up in ${chance(p, packOf(card))}.</span><button class="btn small solid" data-open data-close>open a pack</button></div>`;
  openModal(`<div class="mcard" style="--glow:${best && best.fx ? STYLE_TINT[best.fx] : R.tier ? R.col : card.tint}">${cardHTML(best || { no }, { locked: !best })}</div><div class="minfo">
    <div class="mhead"><span class="label" style="color:${R.col}">${rarLabel(card)} · No. ${card.no}</span><h2>${esc(card.name)}</h2>
      <div class="pricebox">${best ? `<b data-tick="m${card.no}" data-v="${now.toFixed(2)}">${moneyS(now)}</b><div class="chgs"><span>${pill(Val.pct(best, 24))}<small>today</small></span><span>${pill(gainOf(best))}<small>since you pulled it</small></span></div>` : `<b>${moneyS(card.val)}</b><span class="dim">starting value</span>`}</div></div>
    ${copies}
    ${best ? `<div class="mk"><div class="label">Your best copy · ${hrs >= 168 ? "last 7 days" : "since you pulled it"}</div>${ser.length > 1 && hrs > .05 ? lineChart(ser, { log: true, fmt: moneyS, h: 150 }) : `<p class="small">Just pulled. Its value starts moving now.</p>`}<div class="small">${Val.watching(best)} AI buyers watching${mv ? ` · ${mv.ago ? mv.ago + "h ago" : "this hour"} buyers ${mv.pct > 0 ? "rushed in" : "dumped it"} ${pctShort(mv.pct)}` : ""} · simulated</div></div>` : ""}
    <p class="dim facts">${fmt(card.chars)} characters · starts at ${money(card.val)} · ${card.retired ? "retired: no pack holds it any more" : "turns up in " + chance(p, packOf(card))}${card.cap ? `<br>“${esc(card.cap)}”` : ""}</p>
    ${Cut.has(card.id) ? `<div><button class="btn small" data-cut="${card.id}">▶ ${cs.length ? "Watch" : "Preview"} its cutscene</button></div>` : ""}
    ${styles}</div>`, false, keep);
}
/* ---- selling: one tap, and a few seconds to take it back ---- */
let lastSale = null;
function sell(uids) {
  let g = 0, realized = 0; const copies = [];
  for (const u of uids) { const c = state.vault.find(x => x.uid === u); if (c) { g += sellOf(c); realized += sellOf(c) - costOf(c); state.s.bestX = Math.max(state.s.bestX || 0, sellOf(c) / Math.max(1, Val.startOf(c))); copies.push(c); state.vault = state.vault.filter(x => x !== c); } }
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
