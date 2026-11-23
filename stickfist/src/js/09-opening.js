/* ============================================================================
   8. OPENING A PACK: tear it, reveal the cards one at a time, then keep or sell
   ========================================================================== */
let SS = null, SS_PRICE = 0, opening = false; const stage = $("stage"), hint = t => { $("stHint").textContent = t; };
async function openPack(pack) {
  if (SS || opening) return; const pk = pack || curPack(), gate = packGate(); if (gate) { toast(gate); return; }
  // out of play money with nothing left to sell: one free pack a day so nobody is ever stuck
  if (!state.freePacks && !Shop.has(pk.id) && state.coins < packPrice(pk) && !state.vault.length && Date.now() - state.rescueAt > 864e5) { state.freePacks++; state.rescueAt = Date.now(); persist(); toast("You're out of play money, so here's a free pack."); }
  const free = state.freePacks > 0, bought = !free && boughtOf(pk.id) > 0, price = free || bought ? 0 : packPrice(pk);      // a pack you bought costs no play money to open
  if (state.coins < price && Shop.has(pk.id)) { Shop.modal(pk.id); return; }      // out of play money and buying is on: straight to the buy window, this pack already chosen (the 18+ and real-money confirmation stays: Stripe opens after it)
  if (state.coins < price) { toast(state.vault.length ? `You need ${money(price - state.coins)} more. Sell a card to open another pack.` : "You're out of play money. Your free daily pack is back tomorrow, or invite a friend for one now.", Shop.has(pk.id) ? { key: "buy", label: Shop.cash() ? "Add money" : "Buy packs" } : null); return; }
  opening = true; let items; try { items = await Fair.next(pk); } finally { opening = false; } if (SS) return;
  if (free) { state.freePacks--; state.s.free++; state.s.added += Math.round(items.reduce((a, c) => a + c.cost, 0)); } else if (bought) { state.paid[pk.id]--; state.s.bought = (state.s.bought || 0) + 1; state.s.added += Math.round(items.reduce((a, c) => a + c.cost, 0)); } else state.coins -= price;      // a free pack counts as money handed to you, so it never shows up as profit
  state.s.packs++; state.s.spent += price; state.packLog.push(Date.now()); if (state.packLog.length > 300) state.packLog.shift(); SS_PRICE = price; state.vault.push(...items); save(); renderBal(true); renderChips(); if (typeof Ref !== "undefined") Ref.activated();
  SS = { items, idx: 0, phase: "pack", busy: false, pack: pk, free, bought, ref: packPrice(pk) };            // ref: what this pack costs at today's price, free or not, so a pull can be measured against it
  $("stName").textContent = pk.name; $("stCount").textContent = ""; $("stSummary").hidden = true; $("stTray").innerHTML = ""; $("stTitle").innerHTML = ""; $("stTitle").className = "st-title";
  $("stBox").innerHTML = `<div class="st-pack enter" id="stPack">${packHTML(pk)}</div><div class="cstack" id="stStack"></div>`;
  hint("Tap the pack to tear it open"); stage.hidden = false; stage.focus({ preventScroll: true }); FX.clear();
  const pkEl = $("stPack").firstChild; SS.ps = liveWindow(pkEl, pk); tiltPack(pkEl); $("stPack").addEventListener("click", tear);
}
async function tear() {
  if (!SS || SS.phase !== "pack") return; SS.phase = "tearing"; hint(""); Snd.tear(); buzz(35); const wrap = $("stPack"), pk = wrap.querySelector(".pk");
  let snap = ""; try { snap = pk.querySelector("canvas.scr").toDataURL("image/png"); } catch (e) {} if (SS.ps) SS.ps.stop();
  const dir = rand() < .5 ? 1 : -1, A = 13 + rand() * 6, B = 13 + rand() * 6, top = pk.cloneNode(true), bot = pk.cloneNode(true); freezeScreen(top, snap); freezeScreen(bot, snap);
  top.classList.add("cutp", "top"); bot.classList.add("cutp"); top.style.setProperty("--dx", dir);
  top.style.clipPath = `polygon(-6% -6%, 106% -6%, 106% ${B}%, -6% ${A}%)`; bot.style.clipPath = `polygon(-6% ${A}%, 106% ${B}%, 106% 106%, -6% 106%)`;
  pk.style.visibility = "hidden"; wrap.append(bot, top);
  const line = document.createElement("div"); line.className = "cutline"; line.style.top = ((A + B) / 2) + "%"; line.style.transform = `rotate(${(B - A) / 3}deg)`; wrap.appendChild(line);
  const r = wrap.getBoundingClientRect(); for (let i = 0; i <= 16; i++) { const k = i / 16; FX.burst(r.left + r.width * k, r.top + r.height * (A + (B - A) * k) / 100, 3, ["#ffffff", "#c9c5bb", "#8d897f"], 300 + Math.random() * 300); }
  stage.animate([{ transform: "translate(0,0)" }, { transform: "translate(-5px,3px)" }, { transform: "translate(4px,-3px)" }, { transform: "translate(0,0)" }], { duration: 220 });
  await sleep(300); buildStack(); await sleep(260); wrap.classList.add("drop"); await sleep(420); SS.phase = "stack"; focusTop();
}
function buildStack() {
  const st = $("stStack"); st.innerHTML = SS.items.map((c, i) => `<div class="sc rise" data-i="${i}" style="z-index:${50 - i};--rot:${i ? ((rand() - .5) * 5).toFixed(1) : 0}deg;--ox:${i * 2}px;--oy:${i * 3}px">${cardHTML(c)}</div>`).join("");
  SS.veils = SS.items.map((c, i) => { const v = new Veil(st.children[i].querySelector(".card"), BY_NO[c.no].rar); v.frame(); return v; });
  requestAnimationFrame(() => requestAnimationFrame(() => [...st.children].forEach((el, i) => setTimeout(() => el.classList.remove("rise"), 60 + i * 70))));
}
const scEl = i => $("stStack") && $("stStack").querySelector(`.sc[data-i="${i}"]`);
function focusTop() {
  const el = scEl(SS.idx); if (!el) return; el.classList.add("top"); SS.veils[SS.idx].idle(); SS.veils[SS.idx].frame(); el.onclick = advance;
  $("stCount").textContent = `${meter(SS.idx + 1, SS.items.length)} card ${SS.idx + 1} of ${SS.items.length}`; hint("Tap the card to reveal it");
}
async function advance() {
  if (!SS || SS.busy) return; if (SS.phase === "pack") { tear(); return; } if (SS.phase !== "stack") return;
  const el = scEl(SS.idx); if (!el) return; SS.busy = true; const c = SS.items[SS.idx], card = BY_NO[c.no];
  if (!el.dataset.rev) { el.dataset.rev = 1; await reveal(el, c, card, RAR[card.rar], SS.veils[SS.idx]); SS.busy = false; hint(SS.idx < SS.items.length - 1 ? "Tap for the next card" : "Tap to see what you got"); }
  else { await dismiss(el, c); SS.busy = false; }
}
async function reveal(el, c, card, R, v) {
  // How big the moment is follows the rarity, or what this copy really sells for next to what the pack costs, whichever is bigger. A styled copy of a plain card can be worth more than a rare one.
  const x = sellOf(c) / Math.max(1, SS.ref), T = Math.max(R.tier, x >= 10 ? 5 : x >= 4 ? 4 : x >= 2 ? 3 : 0);
  const ms = reduced ? 10 : [650, 850, 1300, 1900, 2700, 3500, 5200][T], rect = el.getBoundingClientRect(), mid = [rect.left + rect.width / 2, rect.top + rect.height / 2]; hint(""); $("stTitle").innerHTML = ""; stage.style.setProperty("--rc", R.col);
  if (x >= 1 && Cut.has(card.id) && (R.tier >= 3 || !state.seen[card.id])) { state.seen[card.id] = 1; save(); await Cut.play(card.id); }   // some cards come with a short ASCII film: always for epic and above, and the first time for the rest, but only for a copy that sells for at least what the pack cost. A card that barely gives anything gets no film (it is still there to watch from its card window)
  await v.play(ms, () => { if (T >= 2) { el.classList.add("shake"); setTimeout(() => el.classList.remove("shake"), 120 + T * 40); FX.burst(mid[0], mid[1], 6 + T * 4, [R.col, "#fff"], 260 + T * 60); } });
  Snd.reveal(T); if (T >= 2) buzz(T >= 5 ? [40, 30, 60, 30, 90] : T >= 3 ? [30, 25, 50] : [25]);
  FX.burst(mid[0], mid[1], [14, 22, 50, 90, 150, 240, 380][T], T >= 2 ? [R.col, "#fff", R.col] : ["#c9c5bb", "#8d897f"], 380 + T * 130);
  if (T >= 4) FX.rain(mid[0], rect.width * 1.6, 40 + T * 14, [R.col, "#fff"]);
  if (T >= 5) stage.animate([{ background: "#fff" }, { background: "#040405" }], { duration: 700 });
  const t = $("stTitle"); t.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : R.col);
  t.innerHTML = `<div class="rw">${R.name}${c.fx ? " · " + STYLES[c.fx].name + " ×" + STYLES[c.fx].x : ""} ${cuts(card.rar) ? `<span style="color:var(--red)">${cuts(card.rar)}</span>` : ""}</div><div class="nm" role="img" aria-label="${esc(card.name)}"></div><div class="vl">worth <b>${money(valueOf(c))}</b></div>${x >= 2 ? `<div class="xm">sells for ${x >= 10 ? Math.round(x) : x.toFixed(1)}× the pack price</div>` : ""}`;
  blockReveal(t.querySelector(".nm"), card.name, 480); t.classList.remove("in"); void t.offsetWidth; t.classList.add("in");
}
async function dismiss(el, c) {
  const dir = rand() < .5 ? -1 : 1; el.onclick = null; el.classList.remove("top"); el.classList.add("gone"); el.style.transform = `translate(${dir * 110}vw, -40px) rotate(${dir * 30}deg)`; el.style.opacity = "0";
  const m = document.createElement("div"); m.className = "mini"; m.innerHTML = cardHTML(c, { sm: true }); $("stTray").appendChild(m); $("stTitle").className = "st-title"; $("stTitle").innerHTML = "";
  SS.idx++; await sleep(260); if (SS.idx >= SS.items.length) summary(); else focusTop();
}
function skipAll() { if (!SS || SS.phase === "summary") return; SS.veils && SS.veils.forEach(v => v.drop()); SS.phase = "stack"; SS.idx = SS.items.length; summary(); }
const againLabel = pk => state.freePacks ? `open a free pack${state.freePacks > 1 ? " · " + state.freePacks + " left" : ""}` : boughtOf(pk.id) ? `open a pack you bought${boughtOf(pk.id) > 1 ? " · " + boughtOf(pk.id) + " left" : ""}` : state.coins >= packPrice(pk) ? "open another · " + money(packPrice(pk)) : Shop.cash() ? "add money to open another" : Shop.has(pk.id) ? "buy a pack · " + rmoney(Shop.price(pk.id)) : "invite a friend, get a free pack";
function summary() {
  SS.phase = "summary"; const items = SS.items, back = items.reduce((a, c) => a + sellOf(c), 0), net = back - SS_PRICE, ref = SS.ref, x = back / Math.max(1, ref), won = back >= ref;
  const best = items.slice().sort((a, b) => valueOf(b) - valueOf(a))[0], bc = BY_NO[best.no];
  $("stCount").textContent = ""; $("stTitle").className = "st-title"; $("stTitle").innerHTML = "";
  $("stSummary").innerHTML = `<div class="sum"><div><div class="label">You opened ${esc(SS.pack.name)}</div><div class="big" style="margin:14px 0"><div class="bx" role="img" aria-label="${money(back)}">${blockSVG(money(back))}</div><span class="dim" style="font-size:13px">of cards you can sell</span></div>
    <div class="net ${net >= 0 ? "up" : "dn"}">${SS.free ? `A free pack. Its cards sell for ${money(back)}.` : SS.bought ? `A pack you bought. Its cards sell for ${money(back)} of play money.` : `You paid ${money(SS_PRICE)} and got ${money(back)} of cards: ${net >= 0 ? "+" : "−"}${money(Math.abs(net))}.`}${x >= 2 ? ` That is ${x >= 10 ? Math.round(x) : x.toFixed(1)}× the pack price.` : ""}</div><div class="small" style="margin-top:4px">Best card: ${esc(bc.name)}, ${RAR[bc.rar].name}${best.fx ? " · " + STYLES[best.fx].name : ""}.</div></div>
    <div class="fan">${items.map(c => `<div>${cardHTML(c, { sm: true })}</div>`).join("")}</div>
    <div class="row" style="justify-content:center"><button class="btn" id="sumSell">sell all · ${money(back)}</button><button class="btn solid" id="sumKeep">keep all</button><button class="btn" id="sumClip">share this pull</button><button class="btn ghost" id="sumAgain">${againLabel(SS.pack)}</button></div></div>`;
  $("stSummary").hidden = false; hint(""); FX.burst(innerWidth / 2, innerHeight * .3, won ? (x >= 2 ? 160 : 90) : 30, won ? ["#9fd8a6", "#fff", "#ece7dc"] : ["#c9c5bb", "#8d897f"], 700); SS.sumAt = performance.now();
}
function closeStage() { stage.hidden = true; const keep = SS; SS = null; FX.clear(); $("stBox").innerHTML = ""; if (keep && keep.veils) keep.veils.forEach(v => v.drop()); renderBal(); show(view); }
