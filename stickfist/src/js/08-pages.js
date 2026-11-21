/* ============================================================================
   7. PAGES: pack, collection, odds
   ========================================================================== */
const VIEWS = ["home", "collection", "odds"]; let view = "home";
const copiesOf = no => state.vault.filter(c => c.no === no).sort((a, b) => valueOf(b) - valueOf(a));
function renderBal(anim) { const el = $("bal"), from = +(el.dataset.v || state.coins); el.dataset.v = state.coins; if (anim) countTo(el, from, state.coins, money); else el.textContent = money(state.coins); }

function renderHome() {
  const ps = packStats(); $("banner").textContent = BANNER.join("\n");
  $("packLine").textContent = `${PACK.n} cards · ${money(PACK.price)}`; $("openBtn").textContent = `open pack · ${money(PACK.price)}`;
  $("honest").innerHTML = `Every card is a picture made of text: the rarer the card, the more characters it holds. About <b>${Math.round(ps.hit * 100)}%</b> of packs are worth at least what you pay. <a class="linkbtn" href="#/odds">See the odds</a>`;
  const hp = $("homePack"); if (!hp.firstChild) { hp.innerHTML = packHTML(); const pk = hp.firstChild; tiltPack(pk); pk.style.cursor = "pointer"; pk.onclick = () => openPack(); liveWindow(pk); }
}

// every copy beyond the best one of each card (copies you added by code are never sold in bulk)
function extras() { const out = []; for (const c of CARDS) copiesOf(c.no).slice(1).forEach(x => { if (!x.phys) out.push(x); }); return out; }
function renderCollection() {
  const found = new Set(state.vault.map(c => c.no)), worth = state.vault.reduce((a, c) => a + valueOf(c), 0), ex = extras(), exSum = ex.reduce((a, c) => a + sellOf(c), 0);
  $("cSub").textContent = state.vault.length ? `${found.size} of ${CARDS.length} cards found · ${state.vault.length} cop${state.vault.length === 1 ? "y" : "ies"} worth ${money(worth)}` : "Open the pack to start your collection.";
  $("cActions").innerHTML = (ex.length ? `<button class="btn" id="sellExtras">sell ${ex.length} extra cop${ex.length === 1 ? "y" : "ies"} · ${money(exSum)}</button>` : "") + `<button class="linkbtn" id="addCode">add a card by its code</button>`;
  $("cGrid").innerHTML = CARDS.map(c => { const cs = copiesOf(c.no), best = cs[0];
    return `<div class="tile"><button class="tilebtn" data-card="${c.no}" aria-label="${esc(c.name)}">${cardHTML(best || { no: c.no }, { sm: true, locked: !best })}</button>
      <div class="meta">${best ? `<span><b>×${cs.length}</b></span><span>${money(valueOf(best))}</span>` : `<span>not found yet</span><span></span>`}</div></div>`; }).join("");
}
function renderOdds() {
  const ps = packStats(), slotName = ["Card 1: a common", "Card 2: a common", "Card 3: a common, sometimes better", "Card 4: an uncommon or better", "Card 5: the best card in the pack"];
  const rows = CARDS.slice().sort((a, b) => a.chars - b.chars).map(c => { const p = packP(c.id); return `<tr><td>${esc(c.name)} <span class="faint">${esc(c.sub)}</span></td><td>${RAR[c.rar].name}</td><td class="r num">${fmt(c.chars)}</td><td class="r num">${money(c.val)}</td><td class="r num">${p >= .5 ? Math.round(p * 100) + "%" : "1 in " + fmt(1 / p)}</td></tr>`; }).join("");
  const tot = Object.values(STYLES).reduce((a, s) => a + s.p, 0);
  $("oBody").innerHTML = `
    <div class="facts"><div><div class="bx" role="img" aria-label="${money(PACK.price)}">${blockSVG(money(PACK.price))}</div><span>per pack · ${PACK.n} cards</span></div><div><div class="bx" role="img" aria-label="${(ps.hit * 100).toFixed(0)}%">${blockSVG((ps.hit * 100).toFixed(0) + "%")}</div><span>of packs are worth at least what you paid</span></div><div><div class="bx" role="img" aria-label="${(ps.rtp * 100).toFixed(0)}%">${blockSVG((ps.rtp * 100).toFixed(0) + "%")}</div><span>comes back on average when you sell</span></div></div>
    <h3 class="sec">What can be in a pack</h3>
    <div class="tablewrap"><table><thead><tr><th>Card</th><th>Rarity</th><th class="r">Characters</th><th class="r">Worth</th><th class="r">Chance per pack</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="small" style="margin-bottom:44px">Selling a card back pays 90% of what it is worth. A typical pack sells back for ${money(ps.median)}.</p>
    <details><summary>How each card in the pack is picked</summary><div>${PACK.slots.map((s, i) => { const t = s.reduce((a, [, w]) => a + w, 0); return `<div class="slot"><div class="label">${slotName[i]}</div>${s.map(([id, w]) => `<div class="row"><span>${esc(BY_ID[id].name)} <span class="faint">${esc(BY_ID[id].sub)}</span></span><span class="bar">${bar(w / t, 24)}</span><span class="pct">${(w / t * 100).toFixed(1)}%</span></div>`).join("")}</div>`; }).join("")}</div></details>
    <details><summary>Stitch styles</summary><div><p class="small" style="margin-bottom:14px">A Stitch can come out in one of twelve ASCII styles, decided by its own code. ${(tot * 100).toFixed(1)}% of Stitches are not the plain default. A styled Stitch is worth its multiple of the card.</p>
      <div class="tablewrap"><table><thead><tr><th>Style</th><th class="r">Chance per Stitch</th><th class="r">Worth</th></tr></thead><tbody><tr><td>Bone <span class="faint">default</span></td><td class="r num">${((1 - tot) * 100).toFixed(1)}%</td><td class="r">×1</td></tr>${Object.keys(STYLES).map(k => `<tr><td>${STYLES[k].name}</td><td class="r num">1 in ${fmt(1 / STYLES[k].p)}</td><td class="r">×${STYLES[k].x}</td></tr>`).join("")}</tbody></table></div></div></details>
    <details><summary>Copy ids and the red slashes</summary><ul class="plain"><li>Every copy has its own id, like <b>IS015-000003-A2JM</b>: the set, the card number, the copy's serial and four check characters.</li><li>The red slashes after an id show rarity: none for commons and uncommons, one for rares and epics, two for legendary, three for mythic, four for the one Secret card.</li><li>Type an id into “add a card by its code” on the collection page and, if the check characters match, that exact copy is added.</li></ul></details>
    <details><summary>Fair play</summary><ul class="plain"><li>Every pack is worth less than it costs on average, and the numbers above are worked out exactly from the odds.</li><li>Cards are drawn with your browser's random number generator, and the odds never change with what you have spent or pulled.</li><li>The money is simulated. Nothing is ever charged.</li></ul></details>
    <p style="margin-top:30px"><button class="linkbtn" id="resetBtn">reset the demo</button></p>`;
}
function show(v) {
  view = VIEWS.includes(v) ? v : "home";
  VIEWS.forEach(x => $("v-" + x).classList.toggle("on", x === view)); document.querySelectorAll("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.v === view));
  ({ home: renderHome, collection: renderCollection, odds: renderOdds })[view](); scrollTo(0, 0);
}
function route() { const h = location.hash.replace(/^#\/?/, ""); show(h === "vault" || h === "index" ? "collection" : h || "home"); }

/* ---- the card window ---- */
function openModal(html, slim) { $("mbox").className = "mbox" + (slim ? " slim" : ""); $("mbox").innerHTML = `<button class="x" data-close aria-label="Close">×</button>` + html; $("modal").hidden = false; }
const closeModal = () => { $("modal").hidden = true; $("mbox").innerHTML = ""; };
function cardModal(no) {
  const card = BY_NO[no], R = RAR[card.rar], cs = copiesOf(no), best = cs[0], p = packP(card.id), have = new Set(cs.map(c => c.fx)), keys = [""].concat(Object.keys(STYLES));
  const styles = card.styles ? `<div><div class="label" style="margin-bottom:8px">Styles found: ${keys.filter(k => have.has(k)).length} of ${keys.length}</div><div class="stylerow">${keys.map(k => `<figure class="${have.has(k) ? "" : "off"}" title="${styleName(k)}${k ? " · 1 in " + fmt(1 / STYLES[k].p) + " · ×" + STYLES[k].x : ""}"><img src="${imgOf(card, k)}" alt=""><figcaption>${styleName(k)}</figcaption></figure>`).join("")}</div></div>` : "";
  openModal(`<div class="mcard">${cardHTML(best || { no }, { locked: !best })}</div><div class="minfo">
    <div><span class="label" style="color:${R.col}">${R.name} · No. ${card.no}</span><h2>${esc(card.name)}</h2></div>
    <p class="dim">${fmt(card.chars)} characters · worth ${money(card.val)} · turns up in ${chance(p)}${card.cap ? `<br>“${esc(card.cap)}”` : ""}</p>
    ${cs.length ? `<div><div class="label" style="margin-bottom:8px">Your ${cs.length === 1 ? "copy" : "copies"}</div><div class="copies">${cs.map(c => `<div class="copy"><div>${idHTML(c.code, card.rar)}<small>${styleName(c.fx)}${c.fx ? " · ×" + STYLES[c.fx].x : ""} · ${c.phys ? "added" : "pulled"} ${new Date(c.t).toLocaleDateString()}</small></div><div class="r"><b>${money(valueOf(c))}</b><button class="btn small" data-sell="${c.uid}" data-no="${no}">sell ${money(sellOf(c))}</button></div></div>`).join("")}</div></div>` : `<p class="small">You haven't found this card yet.</p>`}
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
function sell(uids) { let g = 0; for (const u of uids) { const c = state.vault.find(x => x.uid === u); if (c) { g += sellOf(c); state.vault = state.vault.filter(x => x !== c); } } if (g) { state.coins += g; state.s.sold += g; save(); renderBal(true); } return g; }
