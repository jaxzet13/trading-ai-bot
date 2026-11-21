/* ============================================================================
   7. PAGES: pack, market, collection, odds
   ========================================================================== */
const VIEWS = ["home", "market", "profile", "collection", "odds"]; let view = "home", modalNo = null;
const copiesOf = no => state.vault.filter(c => c.no === no).sort((a, b) => valueOf(b) - valueOf(a));
function renderBal(anim) { const el = $("bal"), from = +(el.dataset.v || state.coins); el.dataset.v = state.coins; if (anim) countTo(el, from, state.coins, money); else el.textContent = money(state.coins); }

/* ---- the market's numbers, ready to show ---- */
function movers() {
  const rows = CARDS.map(c => { const s = MK.series(c, 24, 24); return { c, s, now: s[23], was: s[0], p24: MK.pct(c, 24) }; });
  return { rows, gain: rows.filter(r => r.p24 > .005).sort((a, b) => b.p24 - a.p24).slice(0, 3), drop: rows.filter(r => r.p24 < -.005).sort((a, b) => a.p24 - b.p24).slice(0, 3) };
}
const moverRow = m => `<button class="mover" data-card="${m.c.no}"><span class="nm">${esc(m.c.name)}</span>${sparkSVG(m.s)}<span class="pc">${pctHTML(m.p24)}</span><span class="dim">${money(m.was)} → ${money(m.now)}</span></button>`;

function renderHome() {
  const ps = packStats(); $("banner").textContent = BANNER.join("\n");
  $("packLine").textContent = `${PACK.n} cards · ${money(ps.price)}`; $("openBtn").textContent = `open pack · ${money(ps.price)}`;
  $("honest").innerHTML = `Every card is a picture made of text: the rarer the card, the more characters it holds. About <b>${Math.round(ps.hit * 100)}%</b> of packs are worth at least what you pay. <a class="linkbtn" href="#/odds">See the odds</a>`;
  const mv = movers(); $("hot").innerHTML = `<span class="label">market right now</span>` + [mv.gain[0], mv.drop[0]].filter(Boolean).map(m => `<button class="mover mini" data-card="${m.c.no}"><span class="nm">${esc(m.c.name)}</span>${sparkSVG(m.s)}${pctHTML(m.p24)} <span class="dim">24h</span></button>`).join("") + `<a class="linkbtn" href="#/market">open the market</a>`;
  const bf = MK.flips().best[0]; if (bf && bf.gain > 0) $("hot").insertAdjacentHTML("beforeend", `<span class="hotflip">best flip in 24h: <b>${esc(bf.name)}</b> sold ${esc(bf.card.name)} ${pctHTML(bf.pct)} <span class="faint">simulated</span></span>`);
  const hp = $("homePack"); if (!hp.firstChild) { hp.innerHTML = packHTML(); const pk = hp.firstChild; tiltPack(pk); pk.style.cursor = "pointer"; pk.onclick = () => openPack(); liveWindow(pk); }
}

const flipRow = e => `<button class="flip" data-card="${e.card.no}"><span class="nm">${esc(e.name)} <span class="faint">sold ${esc(e.card.name)}</span></span><span class="pc">${pctHTML(e.pct)}</span><span class="dim">held ${e.hours}h · ${money(e.got)} → ${money(e.sold)} · ${e.gain >= 0 ? "+" : "−"}${money(Math.abs(e.gain))}</span></button>`;
const agoText = m => m === 0 ? "just now" : m < 60 ? m + " min ago" : Math.floor(m / 60) + "h ago";
function renderMarket() {
  const mv = movers(), rows = mv.rows, ps = packStats(), n = rows.length, fl = MK.flips();
  const idxNow = rows.reduce((a, r) => a + r.now / r.c.val, 0) / n * 100, idxWas = rows.reduce((a, r) => a + r.was / r.c.val, 0) / n * 100, up = rows.filter(r => r.p24 > 0).length;
  $("mStats").innerHTML = `<div><span class="label">market index</span><b>${idxNow.toFixed(1)}</b> ${pctHTML(idxNow / idxWas - 1)}</div><div><span class="label">cards up in 24h</span><b>${up} of ${n}</b></div><div><span class="label">pack price right now</span><b>${money(ps.price)}</b></div>`;
  $("mMovers").innerHTML = `<div><h3 class="sec">Skyrocketing · 24h</h3>${mv.gain.map(moverRow).join("") || `<p class="small">Nothing is up right now.</p>`}</div><div><h3 class="sec">Crashing · 24h</h3>${mv.drop.map(moverRow).join("") || `<p class="small">Nothing is down right now.</p>`}</div>`;
  $("mFlips").innerHTML = `<div><h3 class="sec">Best flips · 24h</h3>${fl.best.map(flipRow).join("")}</div><div><h3 class="sec">Worst flips · 24h</h3>${fl.worst.map(flipRow).join("")}</div>`;
  $("mFlipNote").textContent = `Simulated traders, worked out from the real price path and after the 10% selling fee. ${fl.won} of the last ${fl.n} sold for more than they got.`;
  $("mTable").innerHTML = `<thead><tr><th>Card</th><th class="r">Price</th><th class="r">24h</th><th>24h chart</th><th>Buzz</th><th class="r">You hold</th></tr></thead><tbody>` + rows.map(r => {
    const c = r.c, own = copiesOf(c.no).length, bz = MK.buzz(c);
    return `<tr><td><button class="linkbtn plain" data-card="${c.no}">${esc(c.name)}</button> <span class="faint">${RAR[c.rar].name}</span></td><td class="r num"><b>${money(r.now)}</b></td><td class="r">${pctHTML(r.p24)}</td>
      <td class="spk">${sparkSVG(r.s)}</td><td>${buzzDots(bz)}</td><td class="r">${own ? "×" + own : "–"}</td></tr>`; }).join("") + `</tbody>`;
  $("mTrades").innerHTML = MK.feed(10).map(t => `<div class="trade"><span class="who">${t.name}</span><span>sold ${esc(t.card.name)} after ${t.hours}h</span><span class="dim">${money(t.got)} → ${money(t.sold)}</span><span>${pctHTML(t.pct)}</span><span class="faint">${agoText(t.ago)}</span></div>`).join("");
}

// the profile: your money, live, and every card you hold with its price and profit or loss
function worthSeries(pts) {
  const h = state.hist, now = Date.now(), t0 = Math.max(h.length ? h[0][0] : now, now - 864e5); if (now - t0 < 90000) return null;
  const out = []; let j = 0; for (let i = 0; i < pts; i++) { const ts = t0 + (now - t0) * i / (pts - 1); while (j + 1 < h.length && h[j + 1][0] <= ts) j++; out.push(h[j][1]); } out[pts - 1] = netWorth();
  return { out, mins: Math.round((now - t0) / 60000) };
}
function renderProfile() {
  const net = netWorth(), hold = holdingsValue(), back = state.vault.reduce((a, c) => a + sellOf(c), 0), basis = state.vault.reduce((a, c) => a + costOf(c), 0), all = profitAll(), d24 = profitSince(864e5);
  $("pWorth").innerHTML = `<div class="worth"><div class="bignum" role="img" aria-label="${money(net)}">${money(net)}</div><div class="wmeta"><span>${pnlHTML(d24, START + state.s.added)} <span class="dim">last 24h</span></span><span>${pnlHTML(all, START + state.s.added)} <span class="dim">since you started</span></span></div></div>
    <div class="wsplit"><div><span class="label">cash</span><b>${money(state.coins)}</b></div><div><span class="label">your cards, at market price</span><b>${money(hold)}</b> ${state.vault.length ? pnlHTML(hold - basis, basis) : ""}</div><div><span class="label">they would sell for</span><b>${money(back)}</b><span class="dim">after the 10% fee</span></div><div><span class="label">made or lost on sales</span><b>${pnlHTML(state.s.realized, 0)}</b></div></div>`;
  const ws = worthSeries(120);
  $("pChart").innerHTML = ws ? `<div class="mk"><div class="label">Net worth · ${ws.mins >= 1380 ? "last 24 hours" : ws.mins < 90 ? "last " + ws.mins + " minutes" : "last " + Math.round(ws.mins / 60) + " hours"}</div>${lineChart(ws.out, { fmt: money, h: 190 })}</div>`
    : `<div class="mk"><div class="label">Net worth</div><p class="small">Your line starts now and fills in as the market moves. Keep this page open and watch it.</p></div>`;
  const groups = CARDS.map(c => { const cs = copiesOf(c.no); if (!cs.length) return null; return { c, n: cs.length, val: cs.reduce((a, x) => a + valueOf(x), 0), cost: cs.reduce((a, x) => a + costOf(x), 0), s: MK.series(c, 24, 24), p24: MK.pct(c, 24) }; }).filter(Boolean).sort((a, b) => b.val - a.val);
  $("pTable").innerHTML = groups.length ? `<thead><tr><th>Card</th><th class="r">Cost</th><th class="r">Worth now</th><th class="r">Profit / loss</th><th>24h chart</th></tr></thead><tbody>` + groups.map(g => `<tr><td><button class="linkbtn plain" data-card="${g.c.no}">${esc(g.c.name)}</button> <span class="faint">${g.n > 1 ? "×" + g.n + " · " : ""}${RAR[g.c.rar].name}</span></td><td class="r num">${money(g.cost)}</td><td class="r num"><b>${money(g.val)}</b></td><td class="r">${pnlHTML(g.val - g.cost, g.cost)}</td><td class="spk">${sparkSVG(g.s)}</td></tr>`).join("") + `</tbody><tfoot><tr><td>All cards</td><td class="r num">${money(basis)}</td><td class="r num"><b>${money(hold)}</b></td><td class="r">${pnlHTML(hold - basis, basis)}</td><td></td></tr></tfoot>` : "";
  $("pNote").innerHTML = groups.length ? `Tap a card to see its chart and sell it. “Cost” is what the card was worth when you got it. <span class="faint">${state.s.packs} pack${state.s.packs === 1 ? "" : "s"} opened · ${money(state.s.spent)} spent on packs · ${money(state.s.sold)} back from sales</span>` : `You don't hold any cards yet. <a class="linkbtn" href="#/">Open a pack</a> and they will show up here with a live price.`;
}

// every copy beyond the best one of each card (copies you added by code are never sold in bulk)
function extras() { const out = []; for (const c of CARDS) copiesOf(c.no).slice(1).forEach(x => { if (!x.phys) out.push(x); }); return out; }
function renderCollection() {
  const found = new Set(state.vault.map(c => c.no)), worth = state.vault.reduce((a, c) => a + valueOf(c), 0), basis = state.vault.reduce((a, c) => a + costOf(c), 0), ex = extras(), exSum = ex.reduce((a, c) => a + sellOf(c), 0);
  $("cSub").innerHTML = state.vault.length ? `${found.size} of ${CARDS.length} cards found · ${state.vault.length} cop${state.vault.length === 1 ? "y" : "ies"} worth ${money(worth)} ${pctHTML(worth / Math.max(1, basis) - 1)} <span class="faint">since you got them</span>` : "Open the pack to start your collection.";
  $("cActions").innerHTML = (ex.length ? `<button class="btn" id="sellExtras">sell ${ex.length} extra cop${ex.length === 1 ? "y" : "ies"} · ${money(exSum)}</button>` : "") + `<button class="linkbtn" id="addCode">add a card by its code</button>`;
  $("cGrid").innerHTML = CARDS.map(c => { const cs = copiesOf(c.no), best = cs[0];
    return `<div class="tile"><button class="tilebtn" data-card="${c.no}" aria-label="${esc(c.name)}">${cardHTML(best || { no: c.no }, { sm: true, locked: !best })}</button>
      <div class="meta">${best ? `<span><b>×${cs.length}</b></span><span>${money(valueOf(best))} ${pctHTML(gainOf(best))}</span>` : `<span>not found yet</span><span class="dim">${money(MK.price(c))}</span>`}</div></div>`; }).join("");
}
function renderOdds() {
  const ps = packStats(), slotName = ["Card 1: a common", "Card 2: a common", "Card 3: a common, sometimes better", "Card 4: an uncommon or better", "Card 5: the best card in the pack"];
  const rows = CARDS.slice().sort((a, b) => a.chars - b.chars).map(c => { const p = packP(c.id); return `<tr><td>${esc(c.name)} <span class="faint">${esc(c.sub)}</span></td><td>${RAR[c.rar].name}</td><td class="r num">${fmt(c.chars)}</td><td class="r num">${money(MK.price(c))} ${pctHTML(MK.pct(c, 24))}</td><td class="r num">${p >= .5 ? Math.round(p * 100) + "%" : "1 in " + fmt(1 / p)}</td></tr>`; }).join("");
  const tot = Object.values(STYLES).reduce((a, s) => a + s.p, 0), cap = r => MK.CAP[r], vol = r => Math.round(MK.VOL[r] * 100);
  $("oBody").innerHTML = `
    <div class="facts"><div><div class="bignum sm" role="img" aria-label="${money(ps.price)}">${money(ps.price)}</div><span>per pack right now · ${PACK.n} cards</span></div><div><div class="bignum sm" role="img" aria-label="${(ps.hit * 100).toFixed(0)}%">${(ps.hit * 100).toFixed(0) + "%"}</div><span>of packs are worth at least what you paid</span></div><div><div class="bignum sm" role="img" aria-label="${(ps.rtp * 100).toFixed(0)}%">${(ps.rtp * 100).toFixed(0) + "%"}</div><span>comes back on average when you sell</span></div></div>
    <h3 class="sec">What can be in a pack</h3>
    <div class="tablewrap"><table><thead><tr><th>Card</th><th>Rarity</th><th class="r">Characters</th><th class="r">Price now · 24h</th><th class="r">Chance per pack</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="small" style="margin-bottom:44px">Selling a card back pays 90% of its price. A typical pack sells back for ${money(ps.median)} right now.</p>
    <details><summary>How the market works</summary><ul class="plain">
      <li>Cards come from packs. After you have one, its price keeps moving every 20 seconds by a fixed formula that is the same for everybody. Nothing in the formula looks at who owns what, and your cards never change a price.</li>
      <li>A price is a slow base level (how good the card looks next to the other cards of its rarity), random noise, and demand shocks: a card catches on, or falls out of favour. Up shocks and down shocks are equally likely and the same size, and they fade over a few hours.</li>
      <li>Cheap cards swing hardest. A common moves around ${vol("common")}% a day and sometimes doubles or halves; a Mythic around ${vol("mythic")}%; the Secret card barely moves. A price stays between ${MK.FLOOR}× and ${cap("common")}× (commons) down to ${cap("secret")}× (Secret) of the card's base worth.</li>
      <li>Selling a card pays its price minus 10%, whenever you like, so a card has to rise about 11% before selling it beats what it was worth when you got it. Your profile shows every card you hold with its live price and its profit or loss.</li>
      <li>The pack's price follows the market: it moves with what the cards inside are worth, so a pack returns about 89% on average whatever the market is doing. When cards run hot, packs get dearer.</li>
      <li>The traders on the market page are simulated for this demo. Each one pulled a card and sold it, worked out from the real price path after the same 10% fee, and the best and the worst of the day are shown side by side.</li></ul></details>
    <details><summary>How each card in the pack is picked</summary><div>${PACK.slots.map((s, i) => { const t = s.reduce((a, [, w]) => a + w, 0); return `<div class="slot"><div class="label">${slotName[i]}</div>${s.map(([id, w]) => `<div class="row"><span>${esc(BY_ID[id].name)} <span class="faint">${esc(BY_ID[id].sub)}</span></span><span class="bar">${bar(w / t, 24)}</span><span class="pct">${(w / t * 100).toFixed(1)}%</span></div>`).join("")}</div>`; }).join("")}</div></details>
    <details><summary>Styles</summary><div><p class="small" style="margin-bottom:14px">Every card can come out in one of twelve ASCII styles, decided by that copy's own code. ${(tot * 100).toFixed(1)}% of cards are not the plain default. A styled copy is worth its multiple of the card, so a styled Reaper is worth a lot more than a plain one.</p>
      <div class="tablewrap"><table><thead><tr><th>Style</th><th class="r">Chance per card</th><th class="r">Worth</th></tr></thead><tbody><tr><td>Plain <span class="faint">default</span></td><td class="r num">${((1 - tot) * 100).toFixed(1)}%</td><td class="r">×1</td></tr>${Object.keys(STYLES).map(k => `<tr><td>${STYLES[k].name}</td><td class="r num">1 in ${fmt(1 / STYLES[k].p)}</td><td class="r">×${STYLES[k].x}</td></tr>`).join("")}</tbody></table></div></div></details>
    <details><summary>Copy ids and the red slashes</summary><ul class="plain"><li>Every copy has its own id, like <b>IS015-000003-A2JM</b>: the set, the card number, the copy's serial and four check characters.</li><li>The red slashes after an id show rarity: none for commons and uncommons, one for rares and epics, two for legendary, three for mythic, four for the one Secret card.</li><li>Type an id into “add a card by its code” on the collection page and, if the check characters match, that exact copy is added.</li></ul></details>
    <details><summary>Fair play</summary><ul class="plain"><li>A pack is worth less than it costs on average, and the numbers above are worked out exactly from the odds and today's prices.</li><li>Cards are drawn with your browser's random number generator, and the odds never change with what you have spent or pulled.</li><li>The money is simulated. Nothing is ever charged.</li></ul></details>
    <p style="margin-top:30px"><button class="linkbtn" id="resetBtn">reset the demo</button></p>`;
}
function show(v) {
  view = VIEWS.includes(v) ? v : "home";
  VIEWS.forEach(x => $("v-" + x).classList.toggle("on", x === view)); document.querySelectorAll("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.v === view));
  ({ home: renderHome, market: renderMarket, profile: renderProfile, collection: renderCollection, odds: renderOdds })[view](); scrollTo(0, 0);
}
function route() { const h = location.hash.replace(/^#\/?/, ""); show(h === "vault" || h === "index" ? "collection" : h || "home"); }
// the market moved: redraw whatever is on screen without jumping the page
function refreshLive() {
  if (SS) return; ({ home: renderHome, market: renderMarket, profile: renderProfile, collection: renderCollection, odds: renderOdds })[view]();
  if (modalNo && !$("modal").hidden) { const sc = $("mbox").scrollTop; cardModal(modalNo); $("mbox").scrollTop = sc; }
}

/* ---- the card window ---- */
function openModal(html, slim) { $("mbox").className = "mbox" + (slim ? " slim" : ""); $("mbox").innerHTML = `<button class="x" data-close aria-label="Close">×</button>` + html; $("modal").hidden = false; }
const closeModal = () => { $("modal").hidden = true; $("mbox").innerHTML = ""; modalNo = null; };
function cardModal(no) {
  modalNo = no; const card = BY_NO[no], R = RAR[card.rar], cs = copiesOf(no), best = cs[0], p = packP(card.id), have = new Set(cs.map(c => c.fx)), keys = [""].concat(Object.keys(STYLES));
  const styles = card.styles ? `<div><div class="label" style="margin-bottom:8px">Styles found: ${keys.filter(k => have.has(k)).length} of ${keys.length}</div><div class="stylerow">${keys.map(k => `<figure class="${have.has(k) ? "" : "off"}" title="${styleName(k)}${k ? " · 1 in " + fmt(1 / STYLES[k].p) + " · ×" + STYLES[k].x : ""}"><img src="${imgOf(card, k)}" alt=""><figcaption>${styleName(k)}</figcaption></figure>`).join("")}</div></div>` : "";
  const ser = MK.series(card, 168, 56), now = MK.price(card), bz = MK.buzz(card);
  const market = `<div class="mk"><div class="label">Market · last 7 days</div><div class="mkrow"><b>${money(now)}</b> ${pctHTML(MK.pct(card, 24))} <span class="dim">24h</span> ${pctHTML(MK.pct(card, 168))} <span class="dim">7d</span></div>
    ${lineChart(ser, { log: true, fmt: money, h: 160 })}
    <div class="row small"><span>buzz ${buzzDots(bz)}</span><span class="dim">selling pays the price minus 10%</span></div></div>`;
  openModal(`<div class="mcard">${cardHTML(best || { no }, { locked: !best })}</div><div class="minfo">
    <div><span class="label" style="color:${R.col}">${R.name} · No. ${card.no}</span><h2>${esc(card.name)}</h2></div>
    <p class="dim">${fmt(card.chars)} characters · base worth ${money(card.val)} · turns up in ${chance(p)}${card.cap ? `<br>“${esc(card.cap)}”` : ""}</p>
    ${market}
    ${cs.length ? `<div><div class="label" style="margin-bottom:8px">Your ${cs.length === 1 ? "copy" : "copies"}</div><div class="copies">${cs.map(c => `<div class="copy"><div>${idHTML(c.code, card.rar)}<small>${styleName(c.fx)}${c.fx ? " · ×" + STYLES[c.fx].x : ""} · ${c.phys ? "added" : "pulled"} ${new Date(c.t).toLocaleDateString()} · cost ${money(costOf(c))}</small></div><div class="r"><span><b>${money(valueOf(c))}</b><br>${pctHTML(gainOf(c))}</span><button class="btn small" data-sell="${c.uid}" data-no="${no}">sell ${money(sellOf(c))}</button></div></div>`).join("")}</div></div>` : `<p class="small">You haven't found this card yet.</p>`}
    ${styles}</div>`);
}
function codeModal() {
  openModal(`<div class="minfo"><h2 style="font-size:18px">Add a card by its code</h2><p class="dim">Every printed card has an id under its picture, like <b>IS015-000003-A2JM</b>. Type it in and that exact copy is added to your collection.</p>
    <form id="codeForm" autocomplete="off" class="row"><input id="codeIn" placeholder="IS015-000003-A2JM" spellcheck="false" style="flex:1;min-width:0;text-transform:uppercase"><button class="btn solid" type="submit">add</button></form><div class="small" id="codeMsg"></div></div>`, true);
  setTimeout(() => $("codeIn").focus(), 30);
}
function addByCode(raw) {
  const r = parseCode(raw), msg = $("codeMsg"); if (!r) { msg.style.color = "var(--bad)"; msg.textContent = "That code doesn't check out. Look for the id under the picture."; return; }
  if (state.vault.some(c => c.code === r.code)) { msg.style.color = "var(--bad)"; msg.textContent = "That copy is already in your collection."; return; }
  const c = mint(r.card, true, r.serial); state.vault.push(c); save(); closeModal(); if (view === "collection") renderCollection(); toast(`Added ${r.card.name} · ${r.code}`); cardModal(r.card.no);
}
function sell(uids) { let g = 0; for (const u of uids) { const c = state.vault.find(x => x.uid === u); if (c) { g += sellOf(c); state.s.realized += sellOf(c) - costOf(c); state.vault = state.vault.filter(x => x !== c); } } if (g) { state.coins += g; state.s.sold += g; save(); renderBal(true); } return g; }
