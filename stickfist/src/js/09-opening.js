/* ============================================================================
   8. OPENING A PACK: tear it, reveal the cards one at a time, then keep or sell
   ========================================================================== */
let SS = null, SS_PRICE = 0; const stage = $("stage"), hint = t => { $("stHint").textContent = t; };
function openPack() {
  if (SS) return; const price = packPrice(); if (state.coins < price) { toast(`You need ${money(price - state.coins)} more. Tap “add $10”.`); return; }
  state.coins -= price; state.s.packs++; state.s.spent += price; SS_PRICE = price; const items = pullPack(); state.vault.push(...items); save(); renderBal(true);
  SS = { items, idx: 0, phase: "pack", busy: false };
  $("stName").textContent = PACK.name; $("stCount").textContent = ""; $("stSummary").hidden = true; $("stTray").innerHTML = ""; $("stTitle").innerHTML = ""; $("stTitle").className = "st-title";
  $("stBox").innerHTML = `<div class="st-pack enter" id="stPack">${packHTML()}</div><div class="cstack" id="stStack"></div>`;
  hint("Tap the pack to tear it open"); stage.hidden = false; stage.focus({ preventScroll: true }); FX.clear();
  const pk = $("stPack").firstChild; SS.ps = liveWindow(pk); tiltPack(pk); $("stPack").addEventListener("click", tear);
}
async function tear() {
  if (!SS || SS.phase !== "pack") return; SS.phase = "tearing"; hint(""); const wrap = $("stPack"), pk = wrap.querySelector(".pk");
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
  const ms = reduced ? 10 : [650, 850, 1300, 1900, 2700, 3500, 5200][R.tier], rect = el.getBoundingClientRect(), mid = [rect.left + rect.width / 2, rect.top + rect.height / 2]; hint(""); $("stTitle").innerHTML = ""; stage.style.setProperty("--rc", R.col);
  if (Cut.has(card.id) && (R.tier >= 3 || !state.seen[card.id])) { state.seen[card.id] = 1; save(); await Cut.play(card.id); }   // some cards come with a short ASCII film: always for epic and above, and the first time for the rest
  await v.play(ms, () => { if (R.tier >= 2) { el.classList.add("shake"); setTimeout(() => el.classList.remove("shake"), 120 + R.tier * 40); FX.burst(mid[0], mid[1], 6 + R.tier * 4, [R.col, "#fff"], 260 + R.tier * 60); } });
  FX.burst(mid[0], mid[1], [14, 22, 50, 90, 150, 240, 380][R.tier], R.tier >= 2 ? [R.col, "#fff", R.col] : ["#c9c5bb", "#8d897f"], 380 + R.tier * 130);
  if (R.tier >= 4) FX.rain(mid[0], rect.width * 1.6, 40 + R.tier * 14, [R.col, "#fff"]);
  if (R.tier >= 5) stage.animate([{ background: "#fff" }, { background: "#040405" }], { duration: 700 });
  const t = $("stTitle"); t.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : R.col);
  t.innerHTML = `<div class="rw">${R.name}${c.fx ? " · " + STYLES[c.fx].name + " ×" + STYLES[c.fx].x : ""} ${cuts(card.rar) ? `<span style="color:var(--red)">${cuts(card.rar)}</span>` : ""}</div><div class="nm" role="img" aria-label="${esc(card.name)}"></div><div class="vl">worth <b>${money(valueOf(c))}</b></div>`;
  blockReveal(t.querySelector(".nm"), card.name, 480); t.classList.remove("in"); void t.offsetWidth; t.classList.add("in");
}
async function dismiss(el, c) {
  const dir = rand() < .5 ? -1 : 1; el.onclick = null; el.classList.remove("top"); el.classList.add("gone"); el.style.transform = `translate(${dir * 110}vw, -40px) rotate(${dir * 30}deg)`; el.style.opacity = "0";
  const m = document.createElement("div"); m.className = "mini"; m.innerHTML = cardHTML(c, { sm: true }); $("stTray").appendChild(m); $("stTitle").className = "st-title"; $("stTitle").innerHTML = "";
  SS.idx++; await sleep(260); if (SS.idx >= SS.items.length) summary(); else focusTop();
}
function skipAll() { if (!SS || SS.phase === "summary") return; SS.veils && SS.veils.forEach(v => v.drop()); SS.phase = "stack"; SS.idx = SS.items.length; summary(); }
function summary() {
  SS.phase = "summary"; const items = SS.items, worth = items.reduce((a, c) => a + valueOf(c), 0), back = items.reduce((a, c) => a + sellOf(c), 0), net = back - SS_PRICE;
  const best = items.slice().sort((a, b) => valueOf(b) - valueOf(a))[0], bc = BY_NO[best.no];
  $("stCount").textContent = ""; $("stTitle").className = "st-title"; $("stTitle").innerHTML = "";
  $("stSummary").innerHTML = `<div class="sum"><div><div class="label">You opened ${esc(PACK.name)}</div><div class="big" style="margin:14px 0"><div class="bx" role="img" aria-label="${money(worth)}">${blockSVG(money(worth))}</div><span class="dim" style="font-size:13px">of cards</span></div>
    <div class="net ${net >= 0 ? "up" : "dn"}">Sell them all for ${money(back)}: ${net >= 0 ? "+" : "−"}${money(Math.abs(net))} against the ${money(SS_PRICE)} pack.</div><div class="small" style="margin-top:4px">Best card: ${esc(bc.name)}, ${RAR[bc.rar].name}${best.fx ? " · " + STYLES[best.fx].name : ""}.</div></div>
    <div class="fan">${items.map(c => `<div>${cardHTML(c, { sm: true })}</div>`).join("")}</div>
    <div class="row" style="justify-content:center"><button class="btn" id="sumSell">sell all · ${money(back)}</button><button class="btn solid" id="sumKeep">keep all</button><button class="btn ghost" id="sumAgain">${state.coins >= packPrice() ? "open another · " + money(packPrice()) : "add $10 first"}</button></div></div>`;
  $("stSummary").hidden = false; hint(""); FX.burst(innerWidth / 2, innerHeight * .3, net >= 0 ? 90 : 30, net >= 0 ? ["#9fd8a6", "#fff", "#ece7dc"] : ["#c9c5bb", "#8d897f"], 700); SS.sumAt = performance.now();
}
function closeStage() { stage.hidden = true; const keep = SS; SS = null; FX.clear(); $("stBox").innerHTML = ""; if (keep && keep.veils) keep.veils.forEach(v => v.drop()); renderBal(); show(view); }
