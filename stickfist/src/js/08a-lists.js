/* ============================================================================
   7a. THE LISTS: the market and the collection. Both are built from the same few parts: a thumbnail, a price, a coloured change pill and a little line.
   The market answers three questions in order: is it going up or down, what is moving, and what is each card worth. The collection answers: what do I have,
   what is missing, and how likely am I to find it.
   ========================================================================== */
const pill = p => { const up = p > .0005, dn = p < -.0005, a = Math.abs(p * 100); return `<span class="pill ${up ? "up" : dn ? "dn" : "fl"}">${up ? "▲" : dn ? "▼" : "–"} ${a >= 100 ? fmt(a) : a.toFixed(1)}%</span>`; };
const rdot = card => `<i class="rd" style="--rc:${RAR[card.rar].col}"></i>`;
const thumb = (card, fx) => `<span class="thumb" style="--rc:${RAR[card.rar].col}"><img src="${imgOf(card, fx, true)}" alt="" loading="lazy" draggable="false"></span>`;
const chanceS = p => p >= .5 ? Math.round(p * 100) + "% of packs" : "1 in " + fmt(1 / p) + " packs";
const seg = (scope, key, opts, cur) => `<div class="seg" role="group">${opts.map(([v, l]) => `<button data-f="${scope}:${key}:${v}" class="${v === cur ? "on" : ""}" aria-pressed="${v === cur}">${l}</button>`).join("")}</div>`;
const selectHTML = (id, opts, cur, label) => `<label class="sortsel"><span>${label}</span><select id="${id}" aria-label="${label}">${opts.map(([v, l]) => `<option value="${v}"${v === cur ? " selected" : ""}>${l}</option>`).join("")}</select></label>`;
// one card on one line: picture, name, a line of its last day, price, change
const cardRow = (c, o) => `<button class="crow${o.nospark ? " nospark" : ""}" data-card="${c.no}">${thumb(c, o.fx)}<span class="cmain"><b class="nm">${esc(c.name)}</b><span class="sub">${rdot(c)}${o.sub}</span></span>${o.nospark ? "" : `<span class="spark">${o.s ? sparkSVG(o.s) : ""}</span>`}<span class="cval"><b>${o.price}</b>${o.pill}</span></button>`;

/* ---- the market ---- */
const MKF = { show: "all", set: "all", sort: "move", dir: "up" };
function renderMarket() {
  const mv = movers(), rows = mv.rows, n = rows.length, rn = MK.runs(), held = new Set(state.vault.map(c => c.no)); renderHero(rows, rn);
  const idx = k => rows.reduce((a, r) => a + r.s[k] / r.c.val, 0) / n * 100, iNow = idx(23), iWas = idx(0), upN = rows.filter(r => r.p24 > .0005).length;
  const heat = rows.slice().sort((a, b) => b.p24 - a.p24).map(r => `<i class="${r.p24 > .0005 ? "up" : r.p24 < -.0005 ? "dn" : "fl"}" style="--a:${(.35 + Math.min(1, Math.abs(r.p24) / .6) * .65).toFixed(2)}" title="${esc(r.c.name)} ${pctShort(r.p24)}"></i>`).join("");
  const hold = holdingsValue(), basis = state.vault.reduce((a, c) => a + costOf(c), 0);
  $("mPulse").live = `<div class="pulse"><div class="pa"><span class="label">Market index</span><div class="pbig"><b class="num">${iNow.toFixed(1)}</b>${pill(iNow / iWas - 1)}</div><span class="small">The average price of all ${n} cards today. 100 means every card is at its starting price.</span></div>
    <div class="pb">${sparkSVG(Array.from({ length: 24 }, (_, k) => idx(k)), true)}</div>
    <div class="pc"><span class="label">Going up today</span><div class="pbig"><b>${upN}</b><span class="small">of ${n} cards</span></div><div class="heat" role="img" aria-label="${upN} of ${n} cards are up today">${heat}</div></div></div>
    ${state.vault.length ? `<a class="yours" href="#/profile"><span>Your cards are worth</span><b>${moneyS(hold)}</b>${pill(hold / Math.max(1, basis) - 1)}<span class="go">see them ›</span></a>` : `<a class="yours" href="#/"><span>You don't hold any cards yet</span><b>Open a pack</b><span class="go">›</span></a>`}`;
  // what is moving
  const dirUp = MKF.dir === "up", mover = rows.filter(r => dirUp ? r.p24 > .005 : r.p24 < -.005).sort((a, b) => dirUp ? b.p24 - a.p24 : a.p24 - b.p24).slice(0, 6);
  $("mSeg").live = seg("m", "dir", [["up", "Rising"], ["dn", "Falling"]], MKF.dir);
  $("mMovers").live = mover.map(r => `<button class="mvc" data-card="${r.c.no}"><span class="mvimg" style="--rc:${RAR[r.c.rar].col}"><img src="${imgOf(r.c, "", true)}" alt="" loading="lazy" draggable="false">${pill(r.p24)}</span><b class="nm">${esc(r.c.name)}</b><span class="mvp">${moneyS(r.now)}</span>${sparkSVG(r.s)}</button>`).join("") || `<p class="small" style="padding:6px 2px">Nothing is ${dirUp ? "up" : "down"} right now.</p>`;
  // every card
  $("mFilters").live = seg("m", "show", [["all", "All"], ["up", "Going up"], ["down", "Going down"], ["mine", "Mine"]], MKF.show) + seg("m", "set", [["all", "All packs"], ...Object.keys(SETS).map(k => [k, SETS[k].name])], MKF.set) + selectHTML("mSort", [["move", "Biggest move"], ["price", "Highest price"], ["rare", "Rarest"]], MKF.sort, "Sort");
  let list = rows.filter(r => (MKF.set === "all" || r.c.set === MKF.set) && (MKF.show === "all" || (MKF.show === "up" && r.p24 > .0005) || (MKF.show === "down" && r.p24 < -.0005) || (MKF.show === "mine" && held.has(r.c.no))));
  list.sort(MKF.sort === "price" ? (a, b) => b.now - a.now : MKF.sort === "rare" ? (a, b) => RAR[b.c.rar].tier - RAR[a.c.rar].tier || b.now - a.now : (a, b) => Math.abs(b.p24) - Math.abs(a.p24));
  $("mList").live = list.map(r => { const own = copiesOf(r.c.no).length; return cardRow(r.c, { s: r.s, price: moneyS(r.now), pill: pill(r.p24), sub: `${RAR[r.c.rar].name}${own ? ` · <span class="own">you have ×${own}</span>` : `<span class="setn"> · ${esc(SETS[r.c.set].name)}</span>`}` }); }).join("") || `<p class="small" style="padding:14px 2px">No cards match. Try another filter.</p>`;
  // for the curious
  const fl = MK.flips();
  $("mFlips").live = `<div><h3 class="sec">Best trades · this week</h3>${fl.best.map(flipRow).join("")}</div><div><h3 class="sec">Worst trades · this week</h3>${fl.worst.map(flipRow).join("")}</div>`;
  $("mFlipNote").textContent = `Simulated traders, worked out from the real price path and after the 10% selling fee. ${fl.won} of the last ${fl.n} sold for more than they got.`;
  $("mTrades").live = MK.botFeed(8).map(t => `<div class="trade"><span class="who">${t.name}</span><span>${t.buy ? "bought" : "sold"} ${usd(t.usd)} of ${esc(t.card.name)}</span><span class="dim">at ${money(t.price)}</span><span class="${t.buy ? "up" : "dn"}">${t.buy ? "▲ buy" : "▼ sell"}</span><span class="faint">${agoText(t.ago)}</span></div>`).join("");
}

/* ---- the collection ---- */
const CF = { show: "all", set: "all", sort: "num" };
// every copy beyond the best one of each card (copies you added by code are never sold in bulk)
// the copies that are worth more now than they were when you got them (physical cards you added are left alone)
function upCopies() { return state.vault.filter(c => !c.phys && gainOf(c) > 0); }
function extras() { const out = []; for (const c of CARDS) copiesOf(c.no).slice(1).forEach(x => { if (!x.phys) out.push(x); }); return out; }
function renderCollection() {
  noteFound(); const found = new Set(state.vault.map(c => c.no)), worth = holdingsValue(), basis = state.vault.reduce((a, c) => a + costOf(c), 0), ex = extras(), exSum = ex.reduce((a, c) => a + sellOf(c), 0), fx = Object.keys(state.foundFx).length, pk = curPack(), ch = chaseChance(pk);
  $("cSub").textContent = "Tap a card to see its price and to sell it.";
  $("cSum").live = `<div class="stat"><span class="label">Cards found</span><div class="sbig"><b>${found.size}</b><span>of ${CARDS.length}</span></div><div class="bar"><i style="width:${found.size / CARDS.length * 100}%"></i></div></div>
    <div class="stat"><span class="label">Worth now</span><div class="sbig"><b>${money(worth)}</b></div>${state.vault.length ? `<div class="srow">${pill(worth / Math.max(1, basis) - 1)} <span class="small">since you got them</span></div>` : `<span class="small">Open a pack to start.</span>`}</div>
    <div class="stat"><span class="label">Styles found</span><div class="sbig"><b>${fx}</b><span>of ${FX_ALL}</span></div><div class="bar"><i style="width:${fx / FX_ALL * 100}%"></i></div></div>
    <div class="stat go"><span class="label">Next ${esc(pk.name)} pack</span><div class="sbig"><b>${ch ? Math.round(ch * 100) + "%" : "–"}</b><span>a new card</span></div><button class="btn small solid" data-open>${state.freePacks ? "open free pack" : "open pack"}</button></div>`;
  const up = upCopies(), upSum = up.reduce((a, c) => a + sellOf(c), 0);
  $("cActions").live = (ex.length ? `<button class="btn" id="sellExtras">sell ${ex.length} extra cop${ex.length === 1 ? "y" : "ies"} · ${money(exSum)}</button>` : "") + (up.length ? `<button class="btn" id="sellUp">sell the ${up.length} that ${up.length === 1 ? "is" : "are"} up · ${money(upSum)}</button>` : "") + (state.vault.length ? `<button class="btn ghost" id="sellAll" data-label="sell all ${state.vault.length} · ${money(state.vault.reduce((a, c) => a + sellOf(c), 0))}">sell all ${state.vault.length} · ${money(state.vault.reduce((a, c) => a + sellOf(c), 0))}</button>` : "") + (ex.length || up.length || state.vault.length ? `<span class="small">${ex.length ? "Extras keep your best copy of every card. " : ""}You can undo a sale for a few seconds.</span>` : "");
  $("cFilters").live = seg("c", "show", [["all", "All"], ["found", "Found"], ["missing", "Missing"]], CF.show) + selectHTML("cSort", [["num", "Number"], ["rare", "Rarest first"], ["value", "Most valuable"], ["new", "Newest"]], CF.sort, "Sort") + seg("c", "set", [["all", "All packs"], ...Object.keys(SETS).map(k => [k, SETS[k].name])], CF.set);
  const val = c => { const b = copiesOf(c.no)[0]; return b ? valueOf(b) : MK.price(c); }, cmp = { num: (a, b) => +a.no - +b.no, rare: (a, b) => RAR[b.rar].tier - RAR[a.rar].tier || +a.no - +b.no, value: (a, b) => val(b) - val(a), new: (a, b) => ((copiesOf(b.no)[0] || { t: 0 }).t) - ((copiesOf(a.no)[0] || { t: 0 }).t) || +a.no - +b.no }[CF.sort];
  const tile = c => {
    const cs = copiesOf(c.no), best = cs[0], pk2 = packOf(c);
    return `<div class="ctw"><button class="ctile${best ? "" : " miss"}" data-card="${c.no}" aria-label="${esc(c.name)}"><span class="cimg">${cardHTML(best || { no: c.no }, { sm: true, locked: !best, thumb: true })}${best ? `<span class="cb n">×${cs.length}</span>` : ""}${best && best.fx ? `<span class="cb fx">${STYLES[best.fx].name}</span>` : ""}</span>
      <span class="cmeta">${best ? `<b>${moneyS(valueOf(best))}</b>${pill(gainOf(best))}` : `<b class="faint">Not found yet</b>`}</span>
      <span class="csub">${best ? `${rdot(c)}${RAR[c.rar].name}${cs.length > 1 ? ` · ${cs.length} copies` : ""}` : `${rdot(c)}${RAR[c.rar].name} · ${chanceS(packP(c.id))}`}</span></button>${sellBtn(c.no)}</div>`;
  };
  $("cGrid").live = Object.keys(SETS).filter(k => CF.set === "all" || CF.set === k).map(k => {
    const all = CARDS.filter(c => c.set === k), got = all.filter(c => found.has(c.no)).length, list = all.filter(c => CF.show === "all" || (CF.show === "found" ? found.has(c.no) : !found.has(c.no))).sort(cmp);
    return `<div class="sethead"><h3>${esc(SETS[k].name)}</h3><span class="small">${got} of ${all.length} found</span><div class="bar slim"><i style="width:${got / all.length * 100}%"></i></div></div>` + (list.length ? `<div class="cgrid">${list.map(tile).join("")}</div>` : `<p class="small" style="padding:6px 2px 22px">${CF.show === "found" ? "You haven't found any of these yet." : "You have every card here."}</p>`);
  }).join("");
}
