/* ============================================================================
   8. OPENING A PACK: tear it, reveal the cards one at a time, then keep or sell
   ========================================================================== */
let SS = null, SS_PRICE = 0, opening = false; const stage = $("stage"), hint = t => { $("stHint").textContent = t; };
// the meter under the cards: what the cards turned over so far would sell for, against what the pack cost. It fills the same way for every pack, win or lose.
// a long name in big block letters must never run off a narrow screen: shrink its pixel size until it fits
const cmeter = (i, n) => n > 8 ? meter(Math.max(1, Math.round(i / n * 8)), 8) : meter(i, n);      // the little bar in the top line stays 8 wide however many cards there are, so it never pushes skip off the screen
function fitName(el) { const go = () => { const room = Math.min(innerWidth, (el.parentNode && el.parentNode.clientWidth) || innerWidth) - 24, w = el.scrollWidth; if (w > room && w) { const px = parseFloat(getComputedStyle(el).getPropertyValue("--px")) || 8; el.style.setProperty("--px", Math.max(2, Math.floor(px * room / w * 10) / 10) + "px"); } }; go(); requestAnimationFrame(go); }
function meterInit(start) { const m = $("stMeter"), ref = SS.refAll || SS.ref; SS.got = start || 0; SS.paidBack = false; m.hidden = false; m.classList.remove("paid"); $("stMeterFill").style.width = Math.min(100, SS.got / Math.max(1, ref) * 100) + "%"; $("stMeterTxt").textContent = `${money(SS.got)} of ${money(ref)}`; SS.paidBack = SS.got >= ref; m.classList.toggle("paid", SS.paidBack); m.setAttribute("aria-label", `Your cards so far sell for ${money(SS.got)}; the pack cost ${money(ref)}`); }
// what a card sells for leaves the card as a chip and drops into the meter; the meter moves when it lands
function valueChip(el, c) {
  const bar = $("stMeter"); if (reduced || !bar || bar.hidden) { meterAdd(c); return; }
  const a = el.getBoundingClientRect(), b = bar.getBoundingClientRect(), chip = document.createElement("span"), mine = SS; chip.className = "vchip"; chip.textContent = "+" + money(sellOf(c)); chip.style.setProperty("--rc", getComputedStyle(el).getPropertyValue("--rc") || "#fff"); stage.appendChild(chip);
  const x0 = a.left + a.width / 2, y0 = a.top + a.height * .5, x1 = b.left + b.width / 2, y1 = b.top;
  chip.animate([{ transform: `translate(${x0}px, ${y0}px) translate(-50%, -50%) scale(.5)`, opacity: 0 }, { transform: `translate(${x0}px, ${y0 - 26}px) translate(-50%, -50%) scale(1.15)`, opacity: 1, offset: .3 }, { transform: `translate(${x0}px, ${y0 - 30}px) translate(-50%, -50%) scale(1)`, opacity: 1, offset: .55 }, { transform: `translate(${x1}px, ${y1}px) translate(-50%, -50%) scale(.6)`, opacity: .2 }], { duration: 620, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" }).onfinish = () => { chip.remove(); if (SS === mine && SS.phase === "stack") { Snd.chip(); bar.classList.remove("hit"); void bar.offsetWidth; bar.classList.add("hit"); } };
  meterAdd(c);
}
function meterAdd(c) {
  const m = $("stMeter"), ref = SS.refAll || SS.ref; SS.got += sellOf(c); const f = Math.min(1, SS.got / Math.max(1, ref)); $("stMeterFill").style.width = (f * 100) + "%"; $("stMeterTxt").textContent = `${money(SS.got)} of ${money(ref)}`; m.setAttribute("aria-label", `Your cards so far sell for ${money(SS.got)}; the pack cost ${money(ref)}`);
  if (!SS.paidBack && SS.got >= ref) { SS.paidBack = true; m.classList.add("paid"); Snd.paid(); buzz([18, 24, 36]); }
}
async function openPack(pack) {
  if (SS || opening) return; const pk = pack || curPack(), gate = packGate(); if (gate) { toast(gate); return; }
  { const k = Math.min(openN(), maxN(pk)); if (k >= 2) { openMany(pk, k); return; } }
  // out of play money with nothing left to sell: one free pack a day so nobody is ever stuck
  if (!state.freePacks && !Shop.has(pk.id) && state.coins < packPrice(pk) && !state.vault.length && Date.now() - state.rescueAt > 864e5) { state.freePacks++; state.rescueAt = Date.now(); persist(); toast("You're out of play money, so here's a free pack."); }
  const free = state.freePacks > 0, bought = !free && boughtOf(pk.id) > 0, price = free || bought ? 0 : packPrice(pk);      // a pack you bought costs no play money to open
  if (state.coins < price && Shop.has(pk.id)) { Shop.modal(pk.id); return; }      // out of play money and buying is on: straight to the buy window, this pack already chosen (the 18+ and real-money confirmation stays: Stripe opens after it)
  if (state.coins < price) { toast(state.vault.length ? `You need ${money(price - state.coins)} more. Sell a card to open another pack.` : "You're out of play money. Your free daily pack is back tomorrow, or invite a friend for one now.", Shop.has(pk.id) ? { key: "buy", label: Shop.cash() ? "Add money" : "Buy packs" } : null); return; }
  // the stage comes up at once, with the pack on it, while the draw is on its way (a round trip to the server): no waiting on a blank screen
  opening = true; const mine = SS = { items: null, idx: 0, phase: "wait", busy: false, pack: pk, free, bought, ref: packPrice(pk), n: 1 };      // ref: what this pack costs at today's price, free or not, so a pull can be measured against it
  $("stName").textContent = pk.name; $("stCount").textContent = ""; $("stSummary").hidden = true; $("stTray").innerHTML = ""; $("stTitle").innerHTML = ""; $("stTitle").className = "st-title";
  $("stBox").innerHTML = `<div class="st-pack enter" id="stPack">${packHTML(pk)}</div><div class="cstack" id="stStack"></div>`;
  hint(""); stage.hidden = false; stage.focus({ preventScroll: true }); FX.clear();
  const pkEl = $("stPack").firstChild; mine.ps = liveWindow(pkEl, pk); tiltPack(pkEl);
  let items; try { items = await Fair.next(pk); } finally { opening = false; } if (SS !== mine) return;
  if (free) { state.freePacks--; state.s.free++; state.s.added += Math.round(items.reduce((a, c) => a + c.cost, 0)); } else if (bought) { state.paid[pk.id]--; state.s.bought = (state.s.bought || 0) + 1; state.s.added += Math.round(items.reduce((a, c) => a + c.cost, 0)); } else state.coins -= price;      // a free pack counts as money handed to you, so it never shows up as profit
  state.s.packs++; state.s.spent += price; state.packLog.push(Date.now()); if (state.packLog.length > 300) state.packLog.shift(); History.log(pk, 1, free || bought ? 0 : price, price, items); SS_PRICE = price; { noteFound(); const seenNo = new Set(); mine.fresh = new Set(items.filter(c => { const nw = !state.found[c.no] && !seenNo.has(c.no); seenNo.add(c.no); return nw; }).map(c => c.uid)); } state.vault.push(...items); save(); renderBal(true); renderChips(); if (typeof Ref !== "undefined") Ref.activated();
  mine.items = items; mine.phase = "pack"; hint("Swipe across the top to rip it open"); Rip.arm();
}
/* ---- ripping the pack. Drag across the top and the foil tears right under your finger: it lifts away from the tear, light spills out of the gap
        (in the colour of the best card inside), paper flies, and each notch can be felt and heard. Let go past halfway and it finishes itself; a plain tap
        rips it for you. Then the strip is thrown clear and the cards come up out of the pack one by one. ---- */
const Rip = (() => {
  let R = null;
  const yAt = (R, x) => { const k = Math.max(0, Math.min(24, x / 100 * 24)), i = Math.floor(k), f = k - i; return R.jag[i] + ((R.jag[Math.min(24, i + 1)]) - R.jag[i]) * f; };
  function build() {                                                                // made on the first touch, so the pack's own animation runs until then
    const wrap = $("stPack"), pk = wrap.querySelector(".pk"); let snap = ""; try { snap = pk.querySelector("canvas.scr").toDataURL("image/png"); } catch (e) {} if (SS.ps) SS.ps.stop();
    const A = 13 + rand() * 4, jag = Array.from({ length: 25 }, (_, i) => A + (i % 2 ? 1 : -1) * (.35 + rand() * .9)), top = pk.cloneNode(true), bot = pk.cloneNode(true); freezeScreen(top, snap); freezeScreen(bot, snap);
    top.classList.add("cutp", "rtop"); bot.classList.add("cutp"); pk.style.visibility = "hidden";
    const best = SS.items.map(c => RAR[BY_NO[c.no].rar]).sort((a, b) => b.tier - a.tier)[0], col = best && best.tier >= 2 ? best.col : "#fff3d6";
    const inside = document.createElement("div"); inside.className = "ripin"; const glow = document.createElement("div"); glow.className = "ripglow"; const spark = document.createElement("div"); spark.className = "ripspark";
    wrap.style.setProperty("--rip", col); wrap.append(inside, bot, top, glow, spark); const g = wrap.querySelector(".ripguide"); if (g) g.remove();
    Object.assign(R, { built: true, top, bot, glow, spark, inside, A, jag, col });
  }
  function draw(p) {
    if (!R.built) return; R.p = p; const d = R.dir, x0 = d > 0 ? 0 : 100 - p * 100, x1 = d > 0 ? p * 100 : 100, hx = d > 0 ? x1 : x0, pts = [];
    for (let i = 0; i <= 24; i++) { const x = i / 24 * 100; if (x > x0 && x < x1) pts.push([x, R.jag[i]]); }
    const edge = [[x0, yAt(R, x0)], ...pts, [x1, yAt(R, x1)]], P = a => a.map(([x, y]) => `${x.toFixed(2)}% ${y.toFixed(2)}%`).join(", ");
    R.top.style.clipPath = p <= 0 ? "polygon(0 0, 0 0, 0 0)" : `polygon(${P([[x0 - (d > 0 ? 6 : 0), -6], [x1 + (d > 0 ? 0 : 6), -6], ...edge.slice().reverse()])})`;
    R.bot.style.clipPath = d > 0 ? `polygon(${P([[-6, yAt(R, 0)], ...edge.slice(1), [x1, -6], [106, -6], [106, 106], [-6, 106]])})` : `polygon(${P([[-6, -6], [x0, -6], ...edge.slice(0, -1), [106, yAt(R, 100)], [106, 106], [-6, 106]])})`;
    R.inside.style.clipPath = `polygon(${P([[x0, -6], [x1, -6], [x1, R.A + 3], [x0, R.A + 3]])})`;
    R.top.style.transformOrigin = `${hx}% ${yAt(R, hx)}%`; R.top.style.transform = `rotate(${(d * (5 + 13 * p)).toFixed(2)}deg) translateY(${(-3 - 5 * p).toFixed(1)}px)`;
    R.glow.style.left = x0 + "%"; R.glow.style.width = (x1 - x0) + "%"; R.glow.style.top = R.A + "%"; R.glow.style.opacity = p > 0 ? 1 : 0;
    R.spark.style.left = hx + "%"; R.spark.style.top = yAt(R, hx) + "%"; R.spark.style.opacity = p > 0 && p < 1 ? 1 : 0;
    R.wrap.style.setProperty("--rp", p.toFixed(3));
    const n = Math.floor(p * 18); if (n !== R.tick) { R.tick = n; if (p > 0) { buzz(6); Snd.rip(p); const r = R.wrap.getBoundingClientRect(); FX.burst(r.left + r.width * hx / 100, r.top + r.height * yAt(R, hx) / 100, 4, ["#ffffff", R.col, "#c9c5bb"], 220 + p * 260); } }
  }
  function glide(to, ms) { return new Promise(res => { const from = R.p, t0 = performance.now(); (function step(now) { if (!R || !R.built) return res(); const k = Math.min(1, (now - t0) / Math.max(1, ms)); draw(from + (to - from) * (1 - Math.pow(1 - k, 2))); if (k < 1) requestAnimationFrame(step); else res(); })(t0); }); }
  async function finish() {
    if (!SS || R.done) return; R.done = true; SS.phase = "tearing"; hint(""); const { wrap, top, col } = R, d = R.dir, r = wrap.getBoundingClientRect();
    draw(1); Snd.tear(); buzz([20, 30, 70]); R.glow.classList.add("flash");
    top.animate([{ transform: top.style.transform, opacity: 1 }, { transform: `translate(${d * 55}%, -85%) rotate(${d * 48}deg)`, opacity: 0 }], { duration: 620, easing: "cubic-bezier(.2,.7,.3,1)", fill: "forwards" });
    for (let i = 0; i <= 18; i++) FX.burst(r.left + r.width * i / 18, r.top + r.height * R.A / 100, 5, ["#ffffff", col, "#c9c5bb"], 320 + Math.random() * 380);
    const beam = document.createElement("div"); beam.className = "ripbeam"; wrap.appendChild(beam);
    stage.animate([{ transform: "translate(0,0)" }, { transform: "translate(-6px,4px)" }, { transform: "translate(5px,-4px)" }, { transform: "translate(-2px,2px)" }, { transform: "translate(0,0)" }], { duration: 260 });
    await sleep(220); if (!SS || SS.phase !== "tearing") return; buildStack(); SS.items.forEach((_, i) => setTimeout(() => { if (SS && SS.phase !== "summary") { Snd.rise(i); buzz(7); } }, 60 + i * 70));
    await sleep(240); wrap.classList.add("drop"); await sleep(380); if (!SS || SS.phase !== "tearing") return; SS.phase = "stack"; meterInit(); focusTop();
  }
  function arm() {
    const wrap = $("stPack"); if (!wrap) return; R = { wrap, p: 0, dir: 1, tick: 0, built: false, done: false, live: false, x: 0, moved: 0 };
    const g = document.createElement("div"); g.className = "ripguide"; g.innerHTML = `<i></i><span>swipe</span>`; wrap.appendChild(g);
    wrap.addEventListener("pointerdown", e => { if (!SS || SS.phase !== "pack" || R.done || R.busy) return; R.live = true; R.x = e.clientX; R.moved = 0; R.set = false; try { wrap.setPointerCapture(e.pointerId); } catch (x) {} });
    wrap.addEventListener("pointermove", e => {
      if (!R.live || R.done) return; const dx = e.clientX - R.x; R.moved = Math.max(R.moved, Math.abs(dx)); if (!R.set) { if (Math.abs(dx) < 7) return; R.set = true; R.dir = dx > 0 ? 1 : -1; if (!R.built) build(); }
      const p = Math.max(0, Math.min(1, dx * R.dir / (wrap.getBoundingClientRect().width * .8))); draw(p); if (p >= 1) { R.live = false; finish(); }
    });
    const up = async () => { if (!R.live || R.done) return; R.live = false; if (R.moved < 7) return; R.busy = true; if (R.p > .45) { await glide(1, 150); finish(); } else { await glide(0, 180); R.busy = false; } };      // a tap falls through to the click below
    wrap.addEventListener("pointerup", up); wrap.addEventListener("pointercancel", up);
    wrap.addEventListener("click", e => { e.stopPropagation(); if (R.moved < 7) tear(); });
  }
  // a tap, or skip: the pack rips itself, left to right
  async function auto() { if (!SS || SS.phase !== "pack" || !R || R.done || R.busy) return; R.busy = true; R.dir = 1; if (!R.built) build(); await glide(1, 190); finish(); }
  return { arm, auto };
})();
function tear() { Rip.auto(); }
function buildStack() {
  const st = $("stStack"); st.innerHTML = SS.items.map((c, i) => `<div class="sc rise" data-i="${i}" style="z-index:${50 - i};--rot:${i ? ((rand() - .5) * 5).toFixed(1) : 0}deg;--ox:${Math.min(i, 4) * 2 - 4}px;--oy:${Math.min(i, 4) * 3}px">${cardHTML(c)}</div>`).join("");
  SS.veils = SS.items.map((c, i) => { const v = new Veil(st.children[i].querySelector(".card"), BY_NO[c.no].rar); v.frame(); return v; });
  requestAnimationFrame(() => requestAnimationFrame(() => [...st.children].forEach((el, i) => setTimeout(() => el.classList.remove("rise"), 60 + i * 70))));
}
const scEl = i => $("stStack") && $("stStack").querySelector(`.sc[data-i="${i}"]`);
function focusTop() {
  const el = scEl(SS.idx); if (!el) return; el.classList.add("top"); SS.veils[SS.idx].idle(); SS.veils[SS.idx].frame(); el.onclick = e => { if (el._drag) { el._drag = false; e.stopPropagation(); return; } advance(); }; armFling(el);
  $("stCount").textContent = `${cmeter(SS.idx + 1, SS.items.length)} card ${SS.idx + 1} of ${SS.items.length}`; hint(""); hidePills();
  const at = SS.idx, mine = SS; setTimeout(() => { if (SS === mine && SS.idx === at && !SS.busy && SS.phase === "stack" && !el.dataset.rev) advance(); }, at ? 160 : 420);   // each card turns itself over: what you do is choose
}
/* ---- sell or hold: the one choice you make about every card ----
   Two pills under a card once it is face up. Red sells it now for what it shows. Blue holds it: it goes to your collection, where
   its value keeps moving. For a rare card, a styled copy, or one worth at least the pack, the blue pill is the lit one. */
function hidePills() { const p = $("stPills"); if (p) p.hidden = true; }
function showPills(c, card) {
  const p = $("stPills"), keep = RAR[card.rar].tier >= 2 || !!c.fx || sellOf(c) >= SS.ref, w = Val.watching(c); p.className = "pills" + (keep ? " keep" : ""); p.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : RAR[card.rar].col);
  $("pillSell").innerHTML = `<small>sell</small><b>+${money(sellOf(c))}</b>`; $("pillHold").innerHTML = `<small>hold</small><b>${w} buyer${w === 1 ? "" : "s"} watching</b>`;
  p.hidden = false; p.classList.remove("in"); void p.offsetWidth; p.classList.add("in");
}
async function decide(kind, vec) {
  if (!SS || SS.busy || SS.phase !== "stack") return; const el = scEl(SS.idx); if (!el || !el.dataset.rev || !el.classList.contains("lit")) return; SS.busy = true;
  const c = SS.items[SS.idx], pill = $(kind === "sell" ? "pillSell" : "pillHold"), r = pill.getBoundingClientRect(), mid = [r.left + r.width / 2, r.top + r.height / 2]; pill.classList.add("hit"); setTimeout(() => pill.classList.remove("hit"), 320);
  if (kind === "sell") { const g = sell([c.uid]); SS.soldG = (SS.soldG || 0) + g; SS.soldN = (SS.soldN || 0) + 1; FX.burst(mid[0], mid[1], 26, ["#ff5d5d", "#ffd0c8", "#fff"], 420); await dismiss(el, c, vec || [0, 1], true); }
  else { Snd.chip(); buzz(12); FX.burst(mid[0], mid[1], 22, ["#5aa2ff", "#cfe3ff", "#fff"], 380); await dismiss(el, c, vec || [0, -1]); }
  if (SS) SS.busy = false;
}
async function advance() {
  if (SS && SS.busy && SS.rs) { SS.rs.rush(); return; }                                    // a tap while a card is still forming finishes it now
  if (!SS || SS.busy) return; if (SS.phase === "pack") { tear(); return; } if (SS.phase !== "stack") return;
  const el = scEl(SS.idx); if (!el) return; SS.busy = true; const c = SS.items[SS.idx], card = BY_NO[c.no];
  if (!el.dataset.rev) {
    el.dataset.rev = 1; const at = SS.idx; await reveal(el, c, card, RAR[card.rar], SS.veils[SS.idx]); el.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : RAR[card.rar].col); el.classList.add("lit"); if (!reduced) el.animate([{ scale: "1" }, { scale: "1.06" }, { scale: "1" }], { duration: 300, easing: "cubic-bezier(.2,.9,.3,1.3)" }); valueChip(el, c); SS.busy = false; hint(""); if (SS && SS.idx === at) showPills(c, card);
  }
  else { SS.busy = false; await decide("hold"); }                                         // a tap on a card that is face up holds it
}
async function reveal(el, c, card, R, v) {
  // How big the moment is follows the rarity, or what this copy really sells for next to what the pack costs, whichever is bigger. A styled copy of a plain card can be worth more than a rare one.
  const x = sellOf(c) / Math.max(1, SS.ref), T = Math.max(R.tier, x >= 10 ? 5 : x >= 4 ? 4 : x >= 2 ? 3 : 0);
  const ms = reduced ? 10 : [650, 850, 1300, 1900, 2700, 3500, 5200][T], rect = el.getBoundingClientRect(), mid = [rect.left + rect.width / 2, rect.top + rect.height / 2]; hint(""); $("stTitle").innerHTML = ""; stage.style.setProperty("--rc", R.col);
  if (SS.n < 2 && x >= 2 && Cut.has(card.id) && (R.tier >= 3 || !state.seen[card.id])) { state.seen[card.id] = 1; save(); await Cut.play(card.id); }   // some cards come with a short ASCII film: always for epic and above, and the first time for the rest, but only for a copy that sells for at least what the pack cost. A card that barely gives anything gets no film (it is still there to watch from its card window)
  // The back comes off, then the picture prints in: a few big characters first, then finer and finer passes, longer for a rarer card.
  // While it does, the count of characters and what the card is worth climb together at the top.
  const cardEl = el.querySelector(".card"), rs = reduced ? null : new Resolve(cardEl, R.tier, c.fx ? STYLE_TINT[c.fx] : R.tier ? R.col : "#cfd3da"), okPic = rs ? await rs.ready() : false, worth = valueOf(c), tt = $("stTitle");
  if (rs && !okPic) rs.drop();
  if (okPic) {
    el.classList.add("loading"); tt.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : R.col); tt.className = "st-title loading";
    tt.innerHTML = `<div class="rw">forming · <b id="ldN">0</b> characters</div><div class="vl">worth <b id="ldV">${money(0)}</b></div>`; const ldN = $("ldN"), ldV = $("ldV");
    await v.scatter().play(130);
    SS.rs = rs; await rs.play([420, 520, 700, 950, 1250, 1550, 1900][T], p => { const e = Math.pow(p, 1.7); ldN.textContent = fmt(Math.round(card.chars * e)); ldV.textContent = money(worth * e); },
      (k, n) => { if (k % 2 === 0) { Snd.rise(k / 2); buzz(6); } });                 // a soft tick as it sharpens; no shaking and nothing thrown while it forms
    SS.rs = null; el.classList.remove("loading"); tt.className = "st-title";
  } else await v.play(ms, () => { if (T >= 2) { el.classList.add("shake"); setTimeout(() => el.classList.remove("shake"), 120 + T * 40); FX.burst(mid[0], mid[1], 6 + T * 4, [R.col, "#fff"], 260 + T * 60); } });
  Snd.reveal(T); if (T >= 2) buzz(T >= 5 ? [40, 30, 60, 30, 90] : T >= 3 ? [30, 25, 50] : [25]);
  FX.burst(mid[0], mid[1], [14, 22, 50, 90, 150, 240, 380][T], T >= 2 ? [R.col, "#fff", R.col] : ["#c9c5bb", "#8d897f"], 380 + T * 130);
  if (T >= 4) FX.rain(mid[0], rect.width * 1.6, 40 + T * 14, [R.col, "#fff"]);
  if (T >= 5) stage.animate([{ background: "#fff" }, { background: "#040405" }], { duration: 700 });
  const t = $("stTitle"); t.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : R.col);
  t.innerHTML = `<div class="rw">${SS.fresh && SS.fresh.has(c.uid) ? `<span class="newtag">new</span> ` : ""}${rarLabel(card)}${c.fx ? " · " + STYLES[c.fx].name + " ×" + STYLES[c.fx].x : ""} ${cuts(card.rar) ? `<span style="color:var(--red)">${cuts(card.rar)}</span>` : ""}</div><div class="nm" role="img" aria-label="${esc(card.name)}"></div><div class="vl">worth <b>${money(valueOf(c))}</b> <span class="dim">· ${Val.watching(c)} AI buyers watching</span></div>${x >= 2 ? `<div class="xm">sells for ${x >= 10 ? Math.round(x) : x.toFixed(1)}× the pack price</div>` : ""}`;
  { const nm = t.querySelector(".nm"); nm.style.removeProperty("--px"); blockReveal(nm, card.name, 480); fitName(nm); } t.classList.remove("in"); void t.offsetWidth; t.classList.add("in");
}
// once a card is face up, drag it and let go: it leaves the way you threw it (a tap still sends it off)
function armFling(el) {
  let st = null;
  el.addEventListener("pointerdown", e => { if (!SS || SS.busy || SS.phase !== "stack" || !el.dataset.rev || !el.classList.contains("top")) return; st = { x: e.clientX, y: e.clientY, t: performance.now(), dx: 0, dy: 0, drag: false }; try { el.setPointerCapture(e.pointerId); } catch (x) {} });
  el.addEventListener("pointermove", e => { if (!st) return; st.dx = e.clientX - st.x; st.dy = e.clientY - st.y; if (!st.drag && Math.hypot(st.dx, st.dy) > 9) { st.drag = true; el.style.transition = "none"; } if (st.drag) el.style.transform = `translate(${st.dx}px, ${st.dy}px) rotate(${(st.dx / 14).toFixed(1)}deg)`; });
  const up = async () => {
    if (!st) return; const s = st; st = null; if (!s.drag) return; el._drag = true; setTimeout(() => { el._drag = false; }, 60);
    const dist = Math.hypot(s.dx, s.dy), v = dist / Math.max(1, performance.now() - s.t); el.style.transition = "";
    if ((dist > 80 || (v > .6 && dist > 30)) && SS && !SS.busy && SS.phase === "stack") { Snd.whoosh(); await decide("hold", [s.dx / dist, s.dy / dist]); }
    else el.style.transform = "";
  };
  el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
}
async function dismiss(el, c, vec, sold) {
  hidePills(); const dir = vec ? (vec[0] >= 0 ? 1 : -1) : rand() < .5 ? -1 : 1; el.onclick = null; el.classList.remove("top"); el.classList.add("gone"); el.style.transform = vec ? `translate(${(vec[0] * 120).toFixed(0)}vw, ${(vec[1] * 120).toFixed(0)}vh) rotate(${dir * 34}deg)` : `translate(${dir * 110}vw, -40px) rotate(${dir * 30}deg)`; el.style.opacity = "0";
  if (!sold) { const m = document.createElement("div"); m.className = "mini"; m.innerHTML = cardHTML(c, { sm: true }); $("stTray").appendChild(m); } $("stTitle").className = "st-title"; $("stTitle").innerHTML = "";   // the row under the stack is what you are holding
  SS.idx++; await sleep(260); if (SS.idx >= SS.items.length) summary(); else focusTop();
}
function skipAll() { if (!SS || SS.phase === "summary") return; if (SS.phase === "wait") { Machine.stop(); return; } Machine.stop(); SS.veils && SS.veils.forEach(v => v.drop()); SS.phase = "stack"; SS.idx = SS.items.length; summary(); }
// one tap to turn the pack into money and open the next: only offered when the next pack is covered (a free pack, one you bought, or what these cards sell for plus your balance)
const sellNext = back => { const pk = SS.pack, price = packPrice(pk), ok = state.freePacks > 0 || boughtOf(pk.id) > 0 || state.coins + back >= price; return ok && back > 0 ? `<button class="btn solid" id="sumSellAgain">sell all · open another</button>` : ""; };
const againLabel = pk => (openN() > 1 && maxN(pk) >= 2) ? (() => { const k = Math.min(openN(), maxN(pk)), c = Math.max(0, k - state.freePacks - boughtOf(pk.id)) * packPrice(pk); return `open ${k} more${c ? " · " + money(c) : ""}`; })() : state.freePacks ? `open a free pack${state.freePacks > 1 ? " · " + state.freePacks + " left" : ""}` : boughtOf(pk.id) ? `open a pack you bought${boughtOf(pk.id) > 1 ? " · " + boughtOf(pk.id) + " left" : ""}` : state.coins >= packPrice(pk) ? "open another · " + money(packPrice(pk)) : Shop.cash() ? "add money to open another" : Shop.has(pk.id) ? "buy a pack · " + rmoney(Shop.price(pk.id)) : "invite a friend, get a free pack";
// under a pack's result: how many of its cards were new, and how close the next goal is
function goalLine() {
  const nw = SS && SS.fresh ? SS.fresh.size : 0, rd = Goals.ready().length, nx = Goals.next(), parts = [];
  if (nw) parts.push(`<b>${nw} new card${nw > 1 ? "s" : ""}</b> for your collection`);
  if (rd) { const tot = Goals.ready().reduce((a, g) => a + g.r, 0); return `<div class="goalline claim" id="goalLine">${nw ? `<span><b>${nw} new card${nw > 1 ? "s" : ""}</b> for your collection</span>` : ""}<button class="btn solid free" id="sumClaim"><b>${rd} goal${rd > 1 ? "s" : ""} done</b>&nbsp;· claim +${tot} free pack${tot > 1 ? "s" : ""}</button></div>`; }
  if (0) parts.push(""); else if (nx && nx.left <= 5) parts.push(`${nx.left} more to “${esc(nx.g.t)}” (+${nx.g.r} free pack${nx.g.r > 1 ? "s" : ""})`);
  return parts.length ? `<p class="goalline">${parts.join(" · ")}</p>` : "";
}
// The result, straight to the point: what you sold, what you are holding, and the next pack.
function endHTML(o) {
  const net = o.back - o.paid, pk = SS.pack;
  return `<div class="sum v2"><div class="end-top"><div class="label">${esc(o.title)}</div>
      <div class="end-num ${o.paid ? (net >= 0 ? "up" : "dn") : "up"}"><div class="bx" role="img" aria-label="${money(o.back)}">${blockSVG(money(o.back))}</div></div>
      <div class="end-line">${o.paid ? `for ${money(o.paid)}` : "free"}${o.x >= 2 && o.paid ? ` · ${o.x >= 10 ? Math.round(o.x) : o.x.toFixed(1)}×` : ""}</div></div>
    <div class="end-split"><div class="es sold"><small>sold</small><b>${money(o.soldG)}</b></div><div class="es held"><small>holding${o.held.length ? " · " + o.held.length : ""}</small><b>${money(o.heldV)}</b></div></div>
    ${o.fan}
    ${Goals.ready().length ? goalLine() : ""}
    <div class="end-acts"><button class="btn solid big" id="sumAgain">${againLabel(pk)}</button>
      <div class="row" style="justify-content:center">${o.held.length ? `<button class="btn" id="sumSell">sell what I held · ${money(o.heldSell)}</button>` : ""}<button class="btn ghost" id="sumKeep">done</button>${o.share ? `<button class="btn ghost" id="sumClip">share</button>` : ""}</div></div></div>`;
}
const inVault = c => state.vault.some(v => v.uid === c.uid);
function summary() {
  $("stMeter").hidden = true; hidePills(); if (SS.n > 1) { multiSummary(); return; }
  SS.phase = "summary"; const items = SS.items, held = items.filter(inVault), soldG = SS.soldG || 0, heldSell = held.reduce((a, c) => a + sellOf(c), 0), heldV = held.reduce((a, c) => a + valueOf(c), 0), back = soldG + heldSell, ref = SS.ref, x = back / Math.max(1, ref), won = back >= ref;
  $("stCount").textContent = ""; $("stTitle").className = "st-title"; $("stTitle").innerHTML = "";
  $("stSummary").innerHTML = endHTML({ title: SS.pack.name, back, paid: SS.free || SS.bought ? 0 : SS_PRICE, x, soldG, held, heldV, heldSell, share: true,
    fan: held.length ? `<div class="fan">${held.map(c => `<div class="${SS.fresh && SS.fresh.has(c.uid) ? "isnew" : ""}">${cardHTML(c, { sm: true })}</div>`).join("")}</div>` : "" });
  $("stSummary").hidden = false; hint(""); FX.burst(innerWidth / 2, innerHeight * .3, won ? (x >= 2 ? 160 : 90) : 30, won ? ["#9fd8a6", "#fff", "#ece7dc"] : ["#c9c5bb", "#8d897f"], 700); SS.sumAt = performance.now();
}
// one quiet line under a pack result: the free way to get another
function invNudge() { return (typeof API !== "undefined" && API.on) ? `<button class="btn ghost invnudge" id="sumInvite">${GIFT} Invite a friend — you both get a free pack</button>` : ""; }
function closeStage() { if (SS && SS.phase === "wait") return; Machine.stop(); $("stMeter").hidden = true; stage.hidden = true; const keep = SS; SS = null; FX.clear(); $("stBox").innerHTML = ""; if (keep && keep.veils) keep.veils.forEach(v => v.drop()); renderBal(); show(view, true); }

/* ---- several packs at once. Every pack is drawn, charged and counted exactly like a single pack (same odds, same daily limit); only the show is shorter: cards worth less than $0.50
   are not revealed one by one, they are totalled on the result, and nothing is sold or hidden: they are in your collection and in the sums. ---- */
const SMALL = UNIT / 4, MANY = [1, 3, 5, 10, 25];                                                          // "small" is under $0.50 (UNIT units are a dollar)
const openN = () => MANY.includes(state.openN) ? state.openN : 1;
function maxN(pk) {                                                                                     // how many of this pack could be opened right now: free ones, ones you bought, then what the balance covers, never past the daily limit
  const price = Math.max(1, packPrice(pk)), have = state.freePacks + boughtOf(pk.id) + Math.floor(state.coins / price), l = state.lim, room = l && l.packs ? Math.max(0, l.packs - packsToday()) : 25;
  return Math.max(0, Math.min(25, have, room));
}
async function openMany(pk, n) {
  if (SS || opening) return; const price = packPrice(pk); opening = true;
  const mine = SS = { items: [], all: [], idx: 0, phase: "wait", busy: false, pack: pk, free: false, bought: false, ref: price, n };            // the machine starts at once; the draws are fetched in one request while it plays
  $("stName").textContent = `${pk.name} × ${n}`; $("stCount").textContent = ""; $("stSummary").hidden = true; $("stTray").innerHTML = ""; $("stTitle").innerHTML = ""; $("stTitle").className = "st-title"; $("stHint").textContent = "";
  $("stBox").innerHTML = `<div class="cstack" id="stStack"></div>`; stage.hidden = false; stage.focus({ preventScroll: true }); FX.clear();
  const anim = Machine.play(n, n * pk.n, pk.name); let sets; try { sets = await Fair.nextMany(pk, n); } finally { opening = false; } if (SS !== mine) return;
  let items = [], paid = 0, freeN = 0, boughtN = 0, packs = 0;
  for (const got of sets) {
    const isFree = state.freePacks > 0, isBought = !isFree && boughtOf(pk.id) > 0, cost = isFree || isBought ? 0 : price;
    if (isFree) { state.freePacks--; state.s.free++; state.s.added += Math.round(got.reduce((a, c) => a + c.cost, 0)); freeN++; } else if (isBought) { state.paid[pk.id]--; state.s.bought = (state.s.bought || 0) + 1; state.s.added += Math.round(got.reduce((a, c) => a + c.cost, 0)); boughtN++; } else { state.coins -= cost; paid += cost; }       // every pack is charged exactly like a single one
    state.s.packs++; state.s.spent += cost; state.packLog.push(Date.now()); if (state.packLog.length > 300) state.packLog.shift(); state.vault.push(...got); items.push(...got); packs++;
  }
  History.log(pk, packs, paid, price * packs, items); save(); renderBal(true); renderChips(); if (typeof Ref !== "undefined") Ref.activated();
  const hi = items.slice().sort((a, b) => valueOf(b) - valueOf(a)).slice(0, 4).reverse(), shown = new Set(hi.map(c => c.uid)); SS_PRICE = paid;      // however many packs, you turn over your four best cards, the best one last; the rest are on the result
  Object.assign(mine, { items: hi, all: items, phase: "machine", free: freeN === packs, refAll: price * packs, paid, freeN, boughtN, n: packs });
  await anim; if (SS !== mine || mine.phase === "summary") return; mine.phase = "stack";
  if (!hi.length) { summary(); return; } meterInit(items.filter(c => !shown.has(c.uid)).reduce((a, c) => a + sellOf(c), 0)); buildStack(); await sleep(400); focusTop();
}

function multiSummary() {
  SS.phase = "summary"; const all = SS.all, held = all.filter(inVault), soldG = SS.soldG || 0, heldSell = held.reduce((a, c) => a + sellOf(c), 0), heldV = held.reduce((a, c) => a + valueOf(c), 0), back = soldG + heldSell, x = back / Math.max(1, SS.refAll), won = back >= SS.refAll;
  const top = held.slice().sort((a, b) => valueOf(b) - valueOf(a)).slice(0, 4), topSet = new Set(top.map(c => c.uid)), groups = {}; held.filter(c => !topSet.has(c.uid)).forEach(c => { const k = c.no + "|" + (c.fx || ""); (groups[k] = groups[k] || []).push(c); });   // the best of what you hold as cards, the rest as one picture per card with how many
  const smallFan = Object.values(groups).sort((a, b) => valueOf(b[0]) - valueOf(a[0]) || b.length - a.length).map(g => `<div class="gc">${cardHTML(g[0], { sm: true })}<b class="gn">×${g.length}</b></div>`).join("");
  $("stCount").textContent = ""; $("stTitle").className = "st-title"; $("stTitle").innerHTML = "";
  $("stSummary").innerHTML = endHTML({ title: `${SS.n} × ${SS.pack.name}`, back, paid: SS.paid, x, soldG, held, heldV, heldSell, share: false,
    fan: (top.length ? `<div class="fan">${top.map(c => `<div>${cardHTML(c, { sm: true })}</div>`).join("")}</div>` : "") + (smallFan ? `<div class="fan small">${smallFan}</div>` : "") });
  $("stSummary").hidden = false; hint(""); FX.burst(innerWidth / 2, innerHeight * .3, won ? (x >= 2 ? 160 : 90) : 30, won ? ["#9fd8a6", "#fff", "#ece7dc"] : ["#c9c5bb", "#8d897f"], 700); SS.sumAt = performance.now();
}
