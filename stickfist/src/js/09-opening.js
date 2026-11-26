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
// The one pack that can be free is the cheapest: a free pack is a way in, not a way to get a $50 pack for nothing.
const freeOk = pk => pk.id === PACKS[0].id;
async function openPack(pack) {
  if (SS || opening) return; const pk = pack || curPack(), gate = packGate(); if (gate) { toast(gate); return; }
  // out of play money with nothing left to sell: one free pack a day so nobody is ever stuck
  if (!state.freePacks && state.coins < packPrice(PACKS[0]) && !state.vault.length && Date.now() - state.rescueAt > 864e5) { state.freePacks++; state.rescueAt = Date.now(); persist(); toast("You're out of play money, so here's a free pack."); }
  const free = freeOk(pk) && state.freePacks > 0, bought = !free && boughtOf(pk.id) > 0, price = free || bought ? 0 : packPrice(pk);      // a pack you bought costs no play money to open
  if (state.coins < price && Shop.has(pk.id)) { Shop.modal(pk.id); return; }
  if (state.coins < price) { toast(state.vault.length ? `You need ${money(price - state.coins)} more. Sell a card to open this pack.` : "You're out of play money. Your free daily pack is back tomorrow, or invite a friend for one now.", Shop.has(pk.id) ? { key: "buy", label: Shop.cash() ? "Add money" : "Buy packs" } : null); return; }
  // the stage comes up at once, with the pack on it, while the draw is on its way (a round trip to the server): no waiting on a blank screen
  opening = true; const mine = SS = { items: null, idx: 0, phase: "wait", busy: false, pack: pk, free, bought, ref: packPrice(pk), n: 1, price };      // ref: what this pack costs at today's price, free or not, so a pull can be measured against it
  $("stName").textContent = pk.name; $("stCount").textContent = ""; $("stSummary").hidden = true; $("stTray").innerHTML = ""; $("stTitle").innerHTML = ""; $("stTitle").className = "st-title";
  $("stBox").innerHTML = `<div class="st-pack enter" id="stPack">${packHTML(pk)}</div><div class="cstack" id="stStack"></div>`;
  hint(""); stage.hidden = false; stage.focus({ preventScroll: true }); FX.clear();
  const pkEl = $("stPack").firstChild; mine.ps = liveWindow(pkEl, pk); tiltPack(pkEl);
  let items; try { items = await Fair.next(pk); } finally { opening = false; } if (SS !== mine) return;
  // the pack is paid for and the cards are yours the moment it is drawn
  if (free) { state.freePacks--; state.s.free++; state.s.added += Math.round(items.reduce((a, c) => a + c.cost, 0)); } else if (bought) { state.paid[pk.id]--; state.s.bought = (state.s.bought || 0) + 1; state.s.added += Math.round(items.reduce((a, c) => a + c.cost, 0)); } else state.coins -= price;      // a free pack counts as money handed to you, so it never shows up as profit
  state.s.big = Math.max(state.s.big || 0, ...items.map(c => costOf(c))); state.s.packs++; state.s.spent += price; state.packLog.push(Date.now()); if (state.packLog.length > 300) state.packLog.shift(); History.log(pk, 1, free || bought ? 0 : price, price, items); SS_PRICE = price;
  { noteFound(); const seenNo = new Set(); mine.fresh = new Set(items.filter(c => { const nw = !state.found[c.no] && !seenNo.has(c.no); seenNo.add(c.no); return nw; }).map(c => c.uid)); }
  state.vault.push(...items); save(); renderBal(true); renderChips(); if (typeof Ref !== "undefined") Ref.activated();
  Object.assign(mine, { items, veils: [], phase: "pack", all: items, refAll: packPrice(pk), paid: price }); hint("Swipe across the top to rip it open"); Rip.arm();
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
  SS.veils = SS.items.map((c, i) => { const v = new Veil(st.children[i].querySelector(".card"), BY_NO[c.no].rar); v.col = "#cfd3da"; v.back = v.drawBack(v.w, v.h, v.dpr); v.frame(); return v; });      // every back is the same plain one
  requestAnimationFrame(() => requestAnimationFrame(() => [...st.children].forEach((el, i) => setTimeout(() => el.classList.remove("rise"), 60 + i * 70))));
}
const scEl = i => $("stStack") && $("stStack").querySelector(`.sc[data-i="${i}"]`);
function focusTop() {
  const el = scEl(SS.idx); if (!el) return; el.classList.add("top"); SS.veils[SS.idx].idle(); SS.veils[SS.idx].frame(); el.onclick = e => { if (el._drag) { el._drag = false; e.stopPropagation(); return; } advance(); }; armFling(el);
  $("stCount").textContent = `${cmeter(SS.idx + 1, SS.items.length)} card ${SS.idx + 1} of ${SS.items.length}`; hint(""); hidePills();
  const at = SS.idx, mine = SS, rare = at === RARE_SLOT;
  if (rare && !reduced) { hint("press and hold the card"); $("stHint").classList.add("holdhint"); el.classList.add("beat"); Snd.beat(); buzz([14, 120, 14]); holdOpen(el, mine, at); return; }   // the fifth card: you press and hold, the light builds, then it turns
  setTimeout(() => { if (SS === mine && SS.idx === at && !SS.busy && SS.phase === "stack" && !el.dataset.rev) advance(); }, rare ? 300 : at ? 200 : 420);   // each card turns itself over
}
// press and hold: the glow climbs with your finger, the phone ticks faster, and at the top the card turns. Let go and it eases back. Enter or Space turns it at once.
function holdOpen(el, mine, at) {
  let p = 0, down = false, last = 0, tick = 0, done = false; const orig = el.onclick;
  const set = v => el.style.setProperty("--hold", v.toFixed(3));
  const go = () => { if (done) return; done = true; el.classList.remove("beat", "holding"); cue.remove(); $("stHint").classList.remove("holdhint"); set(1); el.onclick = orig; el.onkeydown = null; buzz([30, 40, 60]); advance(); };
  el.onclick = e => { e.stopPropagation(); if (e.detail === 0) go(); };
  el.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } };
  el.tabIndex = 0; const cue = document.createElement("div"); cue.className = "holdcue"; cue.innerHTML = `<span class="hc-bar"><i></i><b>HOLD</b></span>`; el.appendChild(cue);
  const loop = t => {
    if (done || SS !== mine || SS.idx !== at || SS.phase !== "stack") return;
    const dt = Math.min(50, t - (last || t)); last = t;
    p = down ? Math.min(1, p + dt / 1100) : Math.max(0, p - dt / 500); set(p);
    if (down && t - tick > 220 - p * 150) { tick = t; buzz([6 + Math.round(p * 20)]); }
    if (p >= 1) { go(); return; }
    requestAnimationFrame(loop);
  };
  el.addEventListener("pointerdown", e => { if (done) return; down = true; el.classList.add("holding"); try { el.setPointerCapture(e.pointerId); } catch (_) {} });
  const up = () => { down = false; el.classList.remove("holding"); };
  el.addEventListener("pointerup", up); el.addEventListener("pointercancel", up);
  requestAnimationFrame(loop);
  setTimeout(() => { if (!done && SS === mine && SS.idx === at) { hint("tap and hold"); } }, 4000);
}
/* ---- sell or hold: the one choice you make about every card ----
   Two pills under a card once it is face up. Red sells it now for what it shows. Blue holds it: it goes to your collection, where
   its value keeps moving. For a rare card, a styled copy, or one worth at least the pack, the blue pill is the lit one. */
let pillT = 0;
function hidePills() { const p = $("stPills"), w = $("stWorth"), f = $("stFav"); if (f) f.hidden = true; if (p) p.hidden = true; if (w) w.hidden = true; clearInterval(pillT); pillT = 0; }
function showPills(c, card) {
  const p = $("stPills"), keep = RAR[card.rar].tier >= 2 || !!c.fx || sellOf(c) >= SS.ref, w = Val.watching(c); p.className = "pills" + (keep ? " keep" : ""); p.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : RAR[card.rar].col);
  $("pillSell").innerHTML = `<small>sell</small>`; $("pillHold").innerHTML = `<small>keep</small>`;
  p.hidden = false; p.classList.remove("in"); void p.offsetWidth; p.classList.add("in");
  clearInterval(pillT); pillT = setInterval(() => { const b = $("pillSell").querySelector("b"); if (!SS || !b || $("stPills").hidden) { clearInterval(pillT); pillT = 0; return; } const txt = "+" + money(sellOf(c)); if (b.textContent !== txt) b.textContent = txt; const v = $("swV"); if (v && !v.dataset.run) { const t2 = money(valueOf(c)); if (v.textContent !== t2) v.textContent = t2; } }, 250);   // the price is moving while you decide: the pill always says what selling pays this instant
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
  if (!SS || SS.busy) return; if (SS.phase === "pack") { tear(); return; } if (SS.phase === "pick") { pickRail(); return; } if (SS.phase !== "stack") return;
  const el = scEl(SS.idx); if (!el) return; SS.busy = true; const c = SS.items[SS.idx], card = BY_NO[c.no];
  if (!el.dataset.rev) {
    el.dataset.rev = 1; const at = SS.idx; await reveal(el, c, card, RAR[card.rar], SS.veils[SS.idx]); el.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : RAR[card.rar].col); el.classList.add("lit"); if (!reduced) el.animate([{ scale: "1" }, { scale: "1.06" }, { scale: "1" }], { duration: 300, easing: "cubic-bezier(.2,.9,.3,1.3)" }); valueChip(el, c); SS.busy = false; SS.litAt = performance.now(); hint(""); Alive.on(el.querySelector(".card"), c); if (SS && SS.idx === at) { const T = momentOf(c); if (T >= 2 || at === RARE_SLOT) hint("tap for the next card"); else setTimeout(() => { if (SS && SS.idx === at && SS.phase === "stack" && !SS.busy) decide("hold"); }, T ? 900 : 650); }
  }
  else { SS.busy = false; if (rushed() || performance.now() - (SS.litAt || 0) < 350) return; await decide("hold"); }                                         // a tap on a card that is face up holds it: one deliberate tap, not the tail of a rush, and not in the first moment it is up
}
// How big a card's moment is follows its rarity, or what this copy really sells for next to what the pack costs, whichever is bigger. A styled copy of a plain card can be worth more than a rare one.
const momentOf = c => { const x = sellOf(c) / Math.max(1, SS.ref); return Math.max(RAR[BY_NO[c.no].rar].tier, x >= 10 ? 5 : x >= 4 ? 4 : x >= 2 ? 3 : 0); };
const isHit = c => momentOf(c) >= 4;                                                      // legendary or better, or a copy that sells for four packs
/* ---- the build-up to a good card ----
   Before the back comes off, a good card climbs the ladder a step at a time: Rare, Epic, Legendary... each step a thump, a
   brighter glow and a higher note, until it reaches what it is. It only ever climbs to its real rarity and never shows one
   above it, so the longer it goes the better the card, and nothing is teased that you did not get. A copy that is a hit for
   what it sells for (a styled copy of a plain card) climbs in multiples of the pack instead. */
async function climb(el, card, c) {
  if (reduced) return; const order = Object.keys(RAR), top = order.indexOf(card.rar), x = sellOf(c) / Math.max(1, SS.ref); let steps = [];
  for (let i = 2; i <= top; i++) steps.push([RAR[order[i]].name, RAR[order[i]].col]);
  if (steps.length < 2) { const col = c.fx ? STYLE_TINT[c.fx] : RAR[card.rar].col; steps = [2, 4, 10, 25, 50, 100].filter(m => x >= m).map(m => [m + "× the pack", col]); }
  if (!steps.length) return; const tt = $("stTitle"), mine = SS, n = steps.length; el.classList.add("climbing"); stage.classList.add("hush"); hint("");
  // The further it goes, the heavier it gets: the card swells and shakes harder, the screen closes in around it, each step lands
  // slower than the one before. Before the last step everything stops for a breath (dark, still, two low beats), then it lands.
  for (let i = 0; i < n; i++) {
    if (SS !== mine || SS.phase === "summary") break; const [name, col] = steps[i], last = i === n - 1, deep = Math.min(1, i / 6);
    if (last && n >= 3) { el.classList.add("held"); stage.classList.add("breath"); tt.innerHTML = `<div class="cl-d">${steps.slice(0, i).map(s => `<i style="--c:${s[1]}"></i>`).join("")}</div>`; Snd.beat(); buzz([14, 160, 14]); await sleep(520 + Math.min(500, n * 60)); el.classList.remove("held"); stage.classList.remove("breath"); if (SS !== mine || SS.phase === "summary") break; }
    el.style.setProperty("--cc", col); el.style.setProperty("--cz", (1 + deep * .1).toFixed(3)); el.style.setProperty("--cs", (2 + deep * 5).toFixed(1) + "px"); stage.style.setProperty("--rc", col); stage.style.setProperty("--deep", deep.toFixed(2)); tt.className = "st-title climb" + (last ? " last" : ""); tt.style.setProperty("--rc", col);
    tt.innerHTML = `<div class="cl-n">${esc(name)}</div><div class="cl-d">${steps.slice(0, i + 1).map(s => `<i style="--c:${s[1]}"></i>`).join("")}</div>`;
    el.classList.remove("thump"); void el.offsetWidth; el.classList.add("thump"); Snd.climb(i, last); buzz(last ? [40, 30, 80] : 12 + Math.min(40, i * 6));
    const r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2; ring(cx, cy, col, last ? 1.5 : .7 + deep * .5);
    if (last) flash(col, .5);
    await sleep(Math.max(190, 330 - i * 14) + i * 34 + (last ? 420 : 0));                         // each step a little longer than the last: you start to wonder how far it goes
  }
  el.classList.remove("climbing", "thump"); stage.classList.remove("hush"); stage.style.removeProperty("--deep");
}
// a ring of light going out from a point, and the whole screen lit for an instant
function ring(x, y, col, k) { if (reduced) return; const e = document.createElement("i"); e.className = "st-ring"; e.style.cssText = `left:${x}px;top:${y}px;--rc:${col};--k:${k}`; stage.appendChild(e); setTimeout(() => e.remove(), 900); }
function flash(col, a) { if (reduced) return; const e = document.createElement("i"); e.className = "st-flash"; e.style.cssText = `--rc:${col};--a:${a}`; stage.appendChild(e); setTimeout(() => e.remove(), 700); }
// the rarity's name across the whole screen for a beat, when a card that rare lands
function stamp(name, col) { if (reduced) return; const e = document.createElement("div"); e.className = "st-stamp"; e.style.setProperty("--rc", col); e.textContent = name; stage.appendChild(e); setTimeout(() => e.remove(), 1250); }
async function reveal(el, c, card, R, v) {
  c.t = Date.now();                                                                        // its price starts moving when it is turned over, not while it sat face down: every card is first seen at its set value
  const x = sellOf(c) / Math.max(1, SS.ref), T = momentOf(c);
  const ms = reduced ? 10 : [650, 850, 1300, 1900, 2700, 3500, 5200][T], rect = el.getBoundingClientRect(), mid = [rect.left + rect.width / 2, rect.top + rect.height / 2]; hint(""); $("stTitle").innerHTML = ""; stage.style.setProperty("--rc", R.col);
  // The back comes off, then the picture prints in: a few big characters first, then finer and finer passes, longer for a rarer card.
  // While it does, the count of characters and what the card is worth climb together at the top.
  const cardEl = el.querySelector(".card"), rs = reduced ? null : new Resolve(cardEl, R.tier, c.fx ? STYLE_TINT[c.fx] : R.tier ? R.col : "#cfd3da"), okPic = rs ? await rs.ready() : false, worth = valueOf(c), tt = $("stTitle");
  if (rs && !okPic) rs.drop();
  // The order of a good card's moment: first the climb tells you how rare it is, then its film plays, then the card itself forms.
  if (T >= 3) await climb(el, card, c);
  if (SS.n < 2 && x >= 2 && Cut.has(card.id) && (R.tier >= 3 || !state.seen[card.id])) { state.seen[card.id] = 1; save(); $("stTitle").innerHTML = ""; await Cut.play(card.id); if (!SS) return; }   // some cards come with a short ASCII film: always for epic and above, and the first time for the rest, but only for a copy that sells for at least what the pack cost. A card that barely gives anything gets no film (it is still there to watch from its card window)
  c.t = Date.now();                                                                        // and its price starts from here, so the card is first seen at its set value even after a film
  if (okPic) {
    el.classList.add("loading"); tt.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : R.col); tt.className = "st-title loading";
    tt.innerHTML = `<div class="rw">forming · <b id="ldN">0</b> characters</div><div class="vl">worth <b id="ldV">${money(0)}</b></div>`; const ldN = $("ldN"), ldV = $("ldV");
    await v.scatter().play(130);
    SS.rs = rs; await rs.play([420, 520, 700, 950, 1250, 1550, 1900][T], p => { const e = Math.pow(p, 1.7); ldN.textContent = fmt(Math.round(card.chars * e)); ldV.textContent = money(worth * e); },
      (k, n) => { if (k % 2 === 0) { Snd.rise(k / 2); buzz(6); } });                 // a soft tick as it sharpens; no shaking and nothing thrown while it forms
    SS.rs = null; el.classList.remove("loading"); tt.className = "st-title";
  } else await v.play(ms, () => { if (T >= 2) { el.classList.add("shake"); setTimeout(() => el.classList.remove("shake"), 120 + T * 40); } });
  Snd.reveal(T); if (T >= 2) buzz(T >= 5 ? [40, 30, 60, 30, 90] : T >= 3 ? [30, 25, 50] : [25]);
  if (T < 3) FX.burst(mid[0], mid[1], [10, 14, 20][T], T >= 2 ? [R.col, "#fff", R.col] : ["#c9c5bb", "#8d897f"], 380 + T * 130);      // a small puff for an ordinary card; a good card is light and rings, with nothing thrown across the picture
  if (T >= 5) stage.animate([{ background: "#fff" }, { background: "#040405" }], { duration: 700 });
  if (T >= 4 && !reduced) {                                                              // a hit: how hard it lands follows how rare it is
    const col = c.fx ? STYLE_TINT[c.fx] : R.col, lvl = Math.max(1, Object.keys(RAR).indexOf(card.rar) - 3), big = Math.min(1, lvl / 6), mine = SS, live = () => SS === mine && SS.phase === "stack";       // legendary is 1, secret is 9
    stage.style.setProperty("--q", (1 + big * 1.4).toFixed(2)); stage.classList.remove("quake"); void stage.offsetWidth; stage.classList.add("quake"); setTimeout(() => stage.classList.remove("quake"), 620);
    const ry = document.createElement("i"); ry.className = "rays"; ry.style.setProperty("--rc", col); el.insertBefore(ry, el.firstChild); el.classList.add("hit"); el.animate([{ scale: (1.22 + big * .2).toFixed(2), filter: "brightness(2.2)" }, { scale: ".97", filter: "brightness(1.1)", offset: .6 }, { scale: "1", filter: "none" }], { duration: 520, easing: "cubic-bezier(.2, .9, .3, 1)" });   // it slams down
    flash(col, .55 + big * .4); ring(mid[0], mid[1], col, 1.6 + big); setTimeout(() => { if (live()) ring(mid[0], mid[1], "#ffffff", 1.2 + big); }, 140); if (lvl >= 2) stamp(R.name, col);
    setTimeout(() => { if (live()) { Snd.paid(); buzz([20, 30, 40]); } }, 420);
    // the rarest get two more rings of light
    for (let w = 1; w <= Math.min(2, lvl - 2); w++) setTimeout(() => { if (live()) { ring(mid[0], mid[1], col, 1.4 + w * .5); Snd.chip(); buzz(18); } }, 700 + w * 380);
  }
  const t = $("stTitle"); t.style.setProperty("--rc", c.fx ? STYLE_TINT[c.fx] : R.col);
  t.innerHTML = `<div class="rw">${SS.fresh && SS.fresh.has(c.uid) ? `<span class="newtag">new</span> ` : ""}${T >= 3 ? `<b class="rn">${esc(R.name)}</b>` : ""}${rarLabel(card)}${c.fx ? " · " + STYLES[c.fx].name + " ×" + STYLES[c.fx].x : ""} ${cuts(card.rar) ? `<span style="color:var(--red)">${cuts(card.rar)}</span>` : ""}</div><div class="nm" role="img" aria-label="${esc(card.name)}"></div><div class="vl">worth <b>${money(valueOf(c))}</b> ${T >= 3 && x >= 2 ? `<span class="xm">${x >= 10 ? Math.round(x) : x.toFixed(1)}× the pack</span>` : `<span class="dim">· ${Val.watching(c)} AI buyers watching</span>`}</div>${x >= 2 && T < 3 ? `<div class="xm">sells for ${x >= 10 ? Math.round(x) : x.toFixed(1)}× the pack price</div>` : ""}`;
  { const nm = t.querySelector(".nm"); nm.style.removeProperty("--px");
    if (T >= 3) { const col = c.fx ? STYLE_TINT[c.fx] : R.col, rw = t.querySelector(".rw"), nw = SS.fresh && SS.fresh.has(c.uid);
      rw.innerHTML = `<span class="rchip"><i></i>${esc(R.name)}${c.fx ? " · " + esc(STYLES[c.fx].name) : ""}</span>${nw ? `<span class="newtag">new</span>` : ""}`;
      nm.className = "nm clean"; nm.style.setProperty("--n", Math.max(4, card.name.length)); nm.innerHTML = [...card.name.toUpperCase()].map((ch, i) => `<span style="--i:${i}">${ch === " " ? "&nbsp;" : esc(ch)}</span>`).join("");
      nm.insertAdjacentHTML("afterend", `<div class="ro">${rarLabel(card)}${c.fx ? " · ×" + STYLES[c.fx].x + " style" : ""}</div>`);
      const w = $("stWorth"), worth = valueOf(c); w.style.setProperty("--rc", col); w.innerHTML = `<small>worth</small><b id="swV" data-run="1">${money(0)}</b>${x >= 2 ? `<span class="xm">${x >= 10 ? Math.round(x) : x.toFixed(1)}× the pack</span>` : ""}`; w.hidden = false; w.classList.remove("in"); void w.offsetWidth; w.classList.add("in");
      const v = $("swV"), t0 = performance.now(), dur = reduced ? 0 : 650 + T * 90, mine = SS; let lastTick = 0;                                  // the number runs up to what the card is worth
      const run = now => { if (SS !== mine || !v.isConnected) return; const k = dur ? Math.min(1, (now - t0) / dur) : 1, e = 1 - Math.pow(1 - k, 3); v.textContent = money(worth * e); if (k < 1) { if (now - lastTick > 90) { lastTick = now; Snd.rise(Math.round(e * 8)); } requestAnimationFrame(run); } else { delete v.dataset.run; v.classList.add("done"); Snd.chip(); } }; requestAnimationFrame(run);
    } else { blockReveal(nm, card.name, 480); fitName(nm); } }
  { const f = $("stFav"); if (f) { f.dataset.fav = card.no; f.hidden = false; f.className = "favbtn big" + (isFav(card.no) ? " on" : ""); f.textContent = isFav(card.no) ? "♥" : "♡"; f.setAttribute("aria-pressed", isFav(card.no)); } }
  t.className = "st-title" + (T >= 4 ? " hit" : T >= 3 ? " good" : ""); void t.offsetWidth; t.classList.add("in");
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
  SS.idx++; await sleep(260); if (SS.pool) { railReturn(); return; } if (SS.idx >= SS.items.length) summary(); else focusTop();
}
function skipAll() { if (!SS || SS.phase === "summary") return; if (SS.phase === "wait") { Machine.stop(); return; }
  Machine.stop(); SS.veils && SS.veils.forEach(v => v && v.drop()); SS.phase = "stack"; SS.idx = SS.items.length; summary(); }
// one tap to turn the pack into money and open the next: only offered when the next pack is covered (a free pack, one you bought, or what these cards sell for plus your balance)
const sellNext = back => { const pk = SS.pack, price = packPrice(pk), ok = state.freePacks > 0 || boughtOf(pk.id) > 0 || state.coins + back >= price; return ok && back > 0 ? `<button class="btn solid" id="sumSellAgain">sell all · open another</button>` : ""; };
const againLabel = pk => freeOk(pk) && state.freePacks ? `open a free pack${state.freePacks > 1 ? " · " + state.freePacks + " left" : ""}` : boughtOf(pk.id) ? `open a pack you bought${boughtOf(pk.id) > 1 ? " · " + boughtOf(pk.id) + " left" : ""}` : state.coins >= packPrice(pk) ? "open another" : Shop.cash() ? "add money to open another" : Shop.has(pk.id) ? "buy a pack · " + rmoney(Shop.price(pk.id)) : "invite a friend, get a free pack";
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
  const pk = SS.pack, nw = SS.fresh ? SS.fresh.size : 0, n = SS.all.length, sold = SS.soldN || 0;
  return `<div class="sum v2"><div class="end-top"><div class="label">${esc(o.title)}</div>
      <div class="end-num up"><div class="end-big" role="img" aria-label="${n} cards">${n} cards</div></div>
      <div class="end-line">${nw ? "" : "nothing new this time"}${sold ? `${nw ? "" : " · "}${sold} sold` : ""}</div></div>
    <div class="end-cards">${o.fan}${goalLine()}</div>
    <div class="end-acts"><button class="btn solid big" id="sumAgain">${againLabel(pk)}</button>
      <div class="row" style="justify-content:center">${o.rest ? `<button class="btn" id="sumSellRest">sell the commons · keep the rest</button>` : ""}${o.held.length ? `<button class="btn" id="sumSell">${o.rest ? "sell all" : "sell what I held"}</button>` : ""}<button class="btn ghost" id="sumKeep">done</button>${o.share ? `<button class="btn ghost" id="sumClip">share</button>` : ""}${typeof API !== "undefined" && API.on ? `<button class="btn ghost" id="sumInvite">invite · free pack</button>` : ""}</div></div></div>`;
}
const inVault = c => state.vault.some(v => v.uid === c.uid);
function summary() {
  $("stMeter").hidden = true; hidePills(); { const r = $("stRail"), dk = $("stDeck"); if (r) r.remove(); if (dk) dk.remove(); } multiSummary();
}
// one quiet line under a pack result: the free way to get another
function invNudge() { return (typeof API !== "undefined" && API.on) ? `<button class="btn ghost invnudge" id="sumInvite">${GIFT} Invite a friend — you both get a free pack</button>` : ""; }
function closeStage() { if (SS && SS.phase === "wait") return; stageShut = performance.now(); Machine.stop(); $("stMeter").hidden = true; stage.hidden = true; const keep = SS; SS = null; FX.clear(); $("stBox").innerHTML = ""; if (keep && keep.veils) keep.veils.forEach(v => v && v.drop()); renderBal(); show(view, true); }

function multiSummary() {
  SS.phase = "summary"; const all = SS.all, held = all.filter(inVault), soldG = SS.soldG || 0, heldSell = held.reduce((a, c) => a + sellOf(c), 0), heldV = held.reduce((a, c) => a + valueOf(c), 0), back = soldG + heldSell, x = back / Math.max(1, SS.refAll), won = back >= SS.refAll;
  const top = held.slice().sort((a, b) => valueOf(b) - valueOf(a)).slice(0, 7), topSet = new Set(top.map(c => c.uid)), groups = {}; held.filter(c => !topSet.has(c.uid)).forEach(c => { const k = c.no + "|" + (c.fx || ""); (groups[k] = groups[k] || []).push(c); });   // the best of what you hold as cards, the rest as one picture per card with how many
  const smallFan = Object.values(groups).sort((a, b) => valueOf(b[0]) - valueOf(a[0]) || b.length - a.length).map(g => `<div class="gc">${cardHTML(g[0], { sm: true })}<b class="gn">×${g.length}</b>${favBtn(g[0].no)}</div>`).join("");
  $("stCount").textContent = ""; $("stTitle").className = "st-title"; $("stTitle").innerHTML = "";
  const keep = held.filter(c => RAR[BY_NO[c.no].rar].tier >= 2 || c.fx), rest = keep.length && keep.length < held.length ? held.filter(c => !keep.includes(c)).reduce((a, c) => a + sellOf(c), 0) : 0;
  $("stSummary").innerHTML = endHTML({ title: SS.pack.name, back, paid: SS.paid, x, soldG, held, heldV, heldSell, rest, share: false,
    fan: (top.length ? `<div class="fan pack7">${top.map(c => `<div class="fcw">${cardHTML(c, { sm: true })}${favBtn(c.no)}</div>`).join("")}</div>` : "") + (smallFan ? `<div class="fan small">${smallFan}</div>` : "") });
  $("stSummary").hidden = false; hint(""); FX.burst(innerWidth / 2, innerHeight * .3, won ? (x >= 2 ? 40 : 24) : 0, won ? ["#9fd8a6", "#fff", "#ece7dc"] : ["#c9c5bb", "#8d897f"], 700); SS.sumAt = performance.now();
}
