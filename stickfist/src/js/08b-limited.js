/* ============================================================================
   7b. REQUIEM, the limited drop. A preview page: the six cards, what they are worth, the exact odds, and what the real pack would be.
   Nothing here can be bought or opened in the beta, and the page says so first. No countdown and no "only N left" unless a real limit is set in 01b-limited.js.
   ========================================================================== */
// the odds and the return, worked out exactly from the slot tables (the same maths as packDist in 04-state.js, with Requiem's own fixed price)
const rqSell = c => Math.floor(c.val * SELLBACK);
const RQS = (() => {
  const cap = RQ.price * 3; let dist = new Float64Array(cap + 1); dist[0] = 1; let ev = 0, avg = 0, floor = 0;
  for (const slot of RQ.slots) {
    const t = slot.reduce((a, [, w]) => a + w, 0), outs = new Map(); floor += Math.min(...slot.map(([id]) => rqSell(RQ_BY_ID[id])));
    for (const [id, w] of slot) { const c = RQ_BY_ID[id], v = rqSell(c); outs.set(v, (outs.get(v) || 0) + w / t); avg += c.val * w / t; }
    for (const [v, p] of outs) ev += v * p;
    const next = new Float64Array(cap + 1);
    for (const [v, p] of outs) for (let i = 0; i <= cap; i++) { const q = dist[i]; if (q) next[Math.min(cap, i + v)] += p * q; }
    dist = next;
  }
  let hit = 0, acc = 0, median = cap; for (let i = RQ.price; i <= cap; i++) hit += dist[i]; for (let i = 0; i <= cap; i++) { acc += dist[i]; if (acc >= .5) { median = i; break; } }
  const chance = {}; for (const c of RQ.cards) chance[c.id] = 1 - RQ.slots.reduce((a, s) => a * (1 - slotP(s, c.id)), 1);
  return { ev, avg, floor, rtp: ev / RQ.price, hit, median, chance };
})();
const rqCard = id => RQ_BY_ID[id];
const rqLimitText = () => {
  const bits = []; if (RQ.run) bits.push(`A run of ${fmt(RQ.run)} packs, printed once.`); if (RQ.closes) bits.push(`Orders close ${new Date(RQ.closes + "T23:59:59").toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}.`);
  return bits.length ? bits.join(" ") : "How many packs are printed, and the date orders close, will be published on this page before anything is sold. Until then there is no limit to count down to.";
};

function rqCardHTML(c, o) {
  o = o || {}; const R = RAR[c.rar];
  return `<div class="card rq t${R.tier}${o.sm ? " sm" : ""}" style="--tint:${c.tint};--rc:${R.col}" data-rqcard="${c.id}">
    <div class="pic"><img src="cards/rq/${o.full ? "" : "m/"}${c.id}.jpg" alt="${esc(c.name)}: ${esc(c.look)}" draggable="false"${o.lazy ? ' loading="lazy"' : ""}></div><i class="sheen"></i>
    <div class="strip"><div class="l1"><span class="nm">${esc(c.name)}</span><i class="hr"></i><span class="ct"><b>${fmt(c.chars)}</b><u>chars</u></span></div>
    <div class="l2"><span>${c.no} · ${R.name}</span><span class="cap">${esc(c.cap)}</span></div></div></div>`;
}
// the same-rarity comparison with the cards that are already in the other packs
function rqVs(c) {
  const same = CARDS.filter(x => x.rar === c.rar), big = same.reduce((a, x) => x.chars > a.chars ? x : a, same[0]), rich = same.reduce((a, x) => x.val > a.val ? x : a, same[0]);
  const x = (a, b) => { const r = a / b; return "×" + (r >= 10 ? Math.round(r) : r.toFixed(1)); };
  return { big, rich, cx: x(c.chars, big.chars), vx: x(c.val / 100, rich.val / UNIT) };               // real cents against game units: compared in dollars
}
const rqBarHTML = () => `<a class="rqbar" href="#/limited"><span class="rqimg"><img src="cards/rq/s/seraph.jpg" alt="" loading="lazy" draggable="false"></span><span class="rqtx"><span class="label">limited drop · ${Sale.open() ? "on sale" : "preview"}</span><b>Requiem</b><span class="small">six premium cards · ${rmoney(RQ.price)} physical pack</span></span><span class="go"><span>see the cards </span>›</span></a>`;

// the top of the page: the buy box while the sale is open, otherwise the preview note; plus what Stripe sent the buyer back with
function rqSaleHTML() {
  const c = Sale.cfg(), top = Sale.banner(), price = c.price || RQ.price;
  if (c.open) {
    const hash = c.commit ? `<code>${esc(c.commit.slice(0, 8))}…${esc(c.commit.slice(-6))}</code>` : "";
    return top + `<div class="rqbuy"><div class="rqbuyh"><div><b>Buy Requiem</b><span class="small">${rmoney(price)} per pack · 3 real cards · ships to the United States</span></div>
      <label class="rqqty"><span class="small">Packs</span><select id="rqQty" aria-label="How many packs">${Array.from({ length: c.maxQty || 1 }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("")}</select></label></div>
      <label class="rqage"><input type="checkbox" id="rqAge"><span>I'm 18 or older. I've read the odds on this page, and I understand the cards inside are random.</span></label>
      <button class="btn solid big" id="rqPay" disabled>Pay ${Sale.total()}</button>
      <p class="small">Apple Pay, Google Pay or card, on Stripe's secure page. STIXX never sees your card. You are only charged after you confirm there. <a href="${esc(c.terms)}" target="_blank" rel="noopener">Terms, shipping and returns</a>.</p>
      <p class="small">${esc(rqLimitText())} The packs were sealed in a fixed order before the first sale (fingerprint ${hash}), so nobody can change what is in a pack after you pay.</p></div>`;
  }
  if (c.soldOut) return top + `<div class="rqnote"><b>Sold out.</b> Every pack in the run has been sold. ${esc(rqLimitText())}</div>`;
  return top + `<div class="rqnote"><b>Preview only.</b> You can't buy Requiem in the beta: no payment is taken here, and these cards can't be opened, held or traded in the app. The real pack comes on public release, paid for through Stripe, and how it goes on sale will be published here first.<br><span class="small">${esc(rqLimitText())}</span></div>`;
}
// the real counts of the run, once there is one: a run is whole cards, so these replace the target odds where they differ
function rqRunHTML() {
  const c = Sale.cfg(); if (!c.counts || !c.run) return "";
  return `<div class="sechead"><h3>This run, as packed</h3></div>
    <p class="small rqlead">${fmt(c.run)} packs, ${fmt(3 * c.run)} cards. A run is whole cards, so these are the real counts and they replace the target odds above wherever they differ.</p>
    <div class="rqrun">${RQ.cards.slice().reverse().map(x => `<div><i class="rd" style="--rc:${RAR[x.rar].col}"></i><span>${esc(x.name)}</span><b>×${fmt(c.counts[x.id] || 0)}</b></div>`).join("")}</div>
    ${c.commit ? `<p class="small">Fingerprint of the packing list (SHA-256): <code>${esc(c.commit)}</code>. It is fixed before the first sale. When the run sells out the list is published, so you can check it against this and see what was in your pack number.</p>` : ""}`;
}

function renderLimited() {
  const s = RQS, top = rqCard("seraph"), fan = ["orrery", "seraph", "witness"].map(rqCard), most = RQ.cards.reduce((a, c) => c.chars > a.chars ? c : a, RQ.cards[0]);
  const umbra = BY_ID.umbra;
  $("lBody").innerHTML = `
    <div class="rqhero">
      <div class="rqfan" aria-hidden="false">${fan.map((c, i) => `<button class="rqf f${i}" data-rq="${c.id}" aria-label="${esc(c.name)}, ${RAR[c.rar].name}">${rqCardHTML(c)}</button>`).join("")}</div>
      <div class="rqtitle"><span class="label rqeye">Limited drop · preview</span><h2>Requiem</h2>
        <p>Six cards painted in the dark and built from millions of characters. Three come in every pack. Every card has its own rarity, and the rarest turns up in about 1 pack in ${fmt(((c0) => c0.counts && c0.run && c0.counts.seraph ? c0.run / c0.counts.seraph : 1 / s.chance.seraph)(Sale.cfg()))}.</p>
        <div class="rqfacts"><div><b>${rmoney(RQ.price)}</b><span>per pack · ${RQ.n} real cards</span></div><div><b>${(most.chars / 1e6).toFixed(2)}M</b><span>characters on ${esc(most.name)}</span></div><div><b>${Math.round(s.hit * 100)}%</b><span>of packs are worth at least ${rmoney(RQ.price)}</span></div></div>
      </div>
    </div>
    ${rqSaleHTML()}

    <div class="sechead"><h3>The six cards</h3><span class="small">tap one to look closer</span></div>
    <div class="rqgrid">${RQ.cards.map(c => `<button class="rqtile" data-rq="${c.id}">${rqCardHTML(c, { lazy: true })}<span class="rqmeta"><span class="rqrar"><i class="rd" style="--rc:${RAR[c.rar].col}"></i>${RAR[c.rar].name}</span><b>${esc(c.name)}</b><span class="small">${esc(c.look)}</span><span class="rqw">worth <b>${rmoney(c.val)}</b></span></span></button>`).join("")}</div>

    <div class="sechead"><h3>How they compare with the other packs</h3></div>
    <p class="small rqlead">Each Requiem card is the only card of its rarity in the pack, and each one is made of more characters and is worth more than the best card of the same rarity in First Print or Moonshot. Worth here is the card's base worth, before any market move.</p>
    <div class="rqvs">${RQ.cards.map(c => { const v = rqVs(c); return `<div class="rqv"><div class="rqvh"><i class="rd" style="--rc:${RAR[c.rar].col}"></i><b>${esc(c.name)}</b><span class="faint">${RAR[c.rar].name}</span></div>
      <div><u>characters</u><b>${fmt(c.chars)}</b><span class="small">${v.cx} ${esc(v.big.name)}'s ${fmt(v.big.chars)}</span></div>
      <div><u>base worth</u><b>${rmoney(c.val)}</b><span class="small">${v.vx} ${esc(v.rich.name)}'s ${money(v.rich.val)}</span></div></div>`; }).join("")}</div>
    <p class="small">The biggest card in the other packs is ${esc(umbra.name)}, with ${fmt(umbra.chars)} characters. Even Pallbearer, the smallest Requiem card, has ${fmt(rqCard("pallbearer").chars)}.</p>

    <div class="sechead"><h3>The odds, exactly</h3></div>
    <div class="facts"><div><div class="bignum sm">${rmoney(Math.round(s.avg))}</div><span>average value of the 3 cards in a pack</span></div><div><div class="bignum sm">${(s.hit * 100).toFixed(0)}%</div><span>of packs sell back for at least ${rmoney(RQ.price)}</span></div><div><div class="bignum sm">${(s.rtp * 100).toFixed(0)}%</div><span>comes back on average when you sell</span></div></div>
    <div class="clist rqodds">${RQ.cards.slice().reverse().map(c => { const p = s.chance[c.id]; return `<button class="crow nospark" data-rq="${c.id}"><span class="thumb" style="--rc:${RAR[c.rar].col}"><img src="cards/rq/s/${c.id}.jpg" alt="" loading="lazy" draggable="false"></span><span class="cmain"><b class="nm">${esc(c.name)}</b><span class="sub"><i class="rd" style="--rc:${RAR[c.rar].col}"></i>${RAR[c.rar].name} · worth ${rmoney(c.val)}</span></span><span class="cval"><b>${p >= .5 ? Math.round(p * 100) + "%" : "1 in " + fmt(1 / p)}</b><span class="small">of packs</span></span></button>`; }).join("")}</div>
    <p class="small">A typical pack sells back for ${rmoney(s.median)}, and the worst possible pack sells back for ${rmoney(s.floor)}. Selling back pays 90% of a card's worth. Worth is what each card is planned to be worth at launch: a guide, not a promise. Once real people trade the cards, the market sets the price.</p>
    ${rqRunHTML()}
    <details class="more big"><summary>How each card in the pack is picked</summary><div>${RQ.slots.map((sl, i) => { const t = sl.reduce((a, [, w]) => a + w, 0); return `<div class="slot"><div class="label">${RQ.slotNames[i]}</div>${sl.map(([id, w]) => `<div class="row"><span>${esc(rqCard(id).name)} <span class="faint">${esc(RAR[rqCard(id).rar].name)}</span></span><span class="bar">${bar(w / t, 24)}</span><span class="pct">${(w / t * 100).toFixed(w / t < .01 ? 2 : 1)}%</span></div>`).join("")}</div>`; }).join("")}</div></details>

    <div class="sechead"><h3>What the real pack would be</h3></div>
    <ul class="plain rqlist">
      <li>Three real cards in a sealed pack, <b>63 × 88 mm</b>, the standard trading card size, on heavy black-core stock.</li>
      <li>A finish for each rarity, so a Seraph does not feel like a Pallbearer: ${RQ.cards.map(c => `<b>${esc(c.name)}</b> ${esc(c.fin.charAt(0).toLowerCase() + c.fin.slice(1))}`).join("; ")}. Finishes are a plan until the printer's proofs are approved.</li>
      <li>Each card is printed from the same picture you see here, built from the same characters. The picture files are 1800 × 2184 pixels here and are remade at print size.</li>
      <li>Every card carries its own serial number, and the rarest are numbered out of the print run.</li>
    </ul>
    <p class="small rqfine">Requiem is a pack of random cards sold for real money, so the odds above are the odds, and they never change. ${Sale.open() ? "Buying is for people 18 and over only." : "Buying will be for people 18 and over only."} STIXX cards contain explicit language and violence. ${Sale.open() ? "You are only charged on Stripe's page, after you confirm there." : "Nothing on this page charges you."}</p>
    <div class="actions"><button class="btn solid" id="rqShare">share this drop</button><a class="btn ghost" href="#/odds">odds for the other packs</a></div>`;
  $("lSub").textContent = Sale.open() ? "A pack of six premium cards, made of far more characters than anything else here. Real, physical cards, on sale now. This is the one thing in STIXX that costs real money." : "A pack of six premium cards, made of far more characters than anything else here. A preview: it is not on sale in the beta.";
  Sale.poll();
}

function rqModal(id) {
  const c = rqCard(id); if (!c) return; const R = RAR[c.rar], s = RQS, p = s.chance[c.id], v = rqVs(c), i = RQ.cards.indexOf(c);
  openModal(`<div class="mcard">${rqCardHTML(c, { full: false })}</div><div class="minfo">
    <div class="mhead"><span class="label" style="color:${R.col}">${R.name} · ${c.no} of 6</span><h2>${esc(c.name)}</h2><p class="small" style="margin:0">${esc(c.look)} · ${esc(c.sub)}</p>
      <div class="pricebox"><b>${rmoney(c.val)}</b><span class="dim">planned worth at launch</span></div></div>
    <div class="rqmstat"><div><span class="label">characters</span><b>${fmt(c.chars)}</b><span class="small">${fmt(c.cols)} across × ${fmt(c.rows)} down</span></div><div><span class="label">found in</span><b>${p >= .5 ? Math.round(p * 100) + "% of packs" : "1 in " + fmt(1 / p) + " packs"}</b><span class="small">sells back for ${rmoney(rqSell(c))}</span></div></div>
    <p class="small rqmtxt">${v.cx} the characters of ${esc(v.big.name)}, the biggest ${R.name} in the other packs · ${v.vx} the worth of ${esc(v.rich.name)}, the richest.<br>Planned print finish: ${esc(c.fin.toLowerCase())}.<br>“${esc(c.cap)}”</p>
    <figure class="rqmacro"><img src="cards/rq/macro/${c.id}.jpg" alt="A small patch of ${esc(c.name)} at reading size, every cell a typed character" loading="lazy"><figcaption class="small">A real patch of this card, 58 characters wide, at reading size. The whole card is ${fmt(c.chars)} of them.</figcaption></figure>
    <div class="actions"><a class="btn small" href="cards/rq/${c.id}.jpg" target="_blank" rel="noopener">full-size picture</a>${i > 0 ? `<button class="btn small ghost" data-rq="${RQ.cards[i - 1].id}">‹ ${esc(RQ.cards[i - 1].name)}</button>` : ""}${i < RQ.cards.length - 1 ? `<button class="btn small ghost" data-rq="${RQ.cards[i + 1].id}">${esc(RQ.cards[i + 1].name)} ›</button>` : ""}</div>
  </div>`, false); $("mbox").classList.add("rq"); $("mbox").scrollTop = 0;
}
// the foil catches the light: the sheen and a slight tilt follow the finger or pointer
document.addEventListener("pointermove", e => {
  const el = e.target.closest && e.target.closest(".card.rq"); if (!el) return; const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
  el.style.setProperty("--mx", (x * 100).toFixed(0) + "%"); el.style.setProperty("--my", (y * 100).toFixed(0) + "%"); if (!reduced) el.style.transform = `perspective(900px) rotateY(${((x - .5) * 10).toFixed(1)}deg) rotateX(${((.5 - y) * 8).toFixed(1)}deg)`;
});
document.addEventListener("pointerout", e => { const el = e.target.closest && e.target.closest(".card.rq"); if (el && !el.contains(e.relatedTarget)) el.style.transform = ""; });
function rqShare() {
  const url = location.href.split("#")[0] + "#/limited", text = `STIXX Requiem: six cards built from up to ${(RQ.cards[5].chars / 1e6).toFixed(1)} million characters. A limited physical pack, ${rmoney(RQ.price)}.`;
  if (navigator.share) { navigator.share({ title: "STIXX Requiem", text, url }).catch(() => {}); return; }
  try { navigator.clipboard.writeText(url).then(() => toast("Link copied")); } catch (e) { toast(url); }
}
