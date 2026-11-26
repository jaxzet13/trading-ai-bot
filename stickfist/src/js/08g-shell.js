/* ============================================================================
   8g. THE SHELL: a menu, a title for every page, and two pages that hang off the tab bar: What's inside (a pack's best cards, its odds, the hits) and Rewards.
   Everything is drawn with text: box lines, brackets, block bars, glyphs for icons.
   ========================================================================== */
const Shell = (() => {
  const TITLES = { home: "Packs", collection: "Collection", rewards: "Rewards", profile: "Account", inside: "Inside", invite: "Invite", odds: "Odds", live: "Live", market: "Movers", limited: "Requiem" };
  function title(v) { const el = $("hTitle"); if (el) el.textContent = TITLES[v] || "STIXX"; if (typeof Glass !== "undefined") Glass.sync(v); }
  const frame = (t, body, cls) => `<section class="abox${cls ? " " + cls : ""}"><span class="atitle">${t}</span>${body}</section>`;
  const bars = (f, n) => { const k = Math.max(f > 0 ? 1 : 0, Math.round(f * n)); return "█".repeat(k) + `<u>${"░".repeat(n - k)}</u>`; };
  const when = t => { const m = Math.max(0, Math.round((Date.now() - t) / 60000)); return m < 1 ? "just now" : m < 60 ? m + "m ago" : m < 1440 ? Math.round(m / 60) + "h ago" : Math.round(m / 1440) + "d ago"; };

  /* ---- the menu ---- */
  function menu(open) {
    const d = $("drawer"), s = $("scrim"); if (!d) return; const on = open == null ? d.hidden : open; d.hidden = !on; s.hidden = !on; document.body.classList.toggle("drawer-open", on);
    if (on) {
      const st = state.streak && state.streak.n || 0;
      $("drawerBody").innerHTML = `<div class="dr-logo"><span class="dr-mark">╳</span><b>STIXX</b></div>
        <a class="dr-promo" href="#/rewards" data-menuclose><span>${dailyReady() ? "▸ your free pack is ready" : "▸ come back tomorrow for the next one"}</span><b>${st ? "day " + st : "day 1"}</b><i>›</i></a>
        <div class="dr-sec">CARD PACKS</div>
        ${PACKS.map(p => `<button class="dr-row${p.id === state.pack ? " on" : ""}" data-dpack="${p.id}" style="--pc:${p.col}"><i>◆</i><span>${esc(p.name)}</span><small>${money(packPrice(p)).replace(/\.00$/, "")}</small></button>`).join("")}
        <div class="dr-sec">MORE</div>
        <a class="dr-row" href="#/live" data-menuclose><i>~</i><span>Live hits</span></a>
        <a class="dr-row" href="#/odds" data-menuclose><i>%</i><span>Odds and how it works</span></a>
        <a class="dr-row" href="#/limited" data-menuclose><i>★</i><span>Requiem · limited pack</span></a>
        <a class="dr-row" href="terms.html" data-menuclose><i>§</i><span>Terms and privacy</span></a>
        <p class="dr-fine">Play money only. Nothing is charged or paid out. 18+</p>`;
    }
  }

  /* ---- the pack page: a row of packs you swipe through, the pack's name, what is inside, its best and worst card, and one big button ---- */
  const packRange = pk => { const cards = [...new Set(pk.slots.flat().map(([id]) => id))].map(id => BY_ID[id]).filter(Boolean), v = cards.map(c => c.val); return [Math.min(...v), Math.max(...v)]; };
  const buyLabel = pk => { const fp = freeOk(pk) ? state.freePacks : 0, pp = boughtOf(pk.id); return fp ? "Open a free pack" : pp ? "Open the pack you bought" : "Open for " + money(packPrice(pk)); };
  let car = null, curIdx = -1, scrollT = 0, settling = false;
  function text(pk) {
    const [lo, hi] = packRange(pk), q = s => $("tp").querySelector(s);
    q(".tp-name").textContent = pk.name + " Pack"; q(".tp-min b").textContent = lo / UNIT < 1 ? "$" + (lo / UNIT).toFixed(2) : money(lo).replace(/\.00$/, ""); q(".tp-big").textContent = money(hi).replace(/\.00$/, ""); q(".tp-buy span").textContent = buyLabel(pk); q(".tp-buy").style.setProperty("--pc", pk.col);
    q(".tp-sub").textContent = `${LIVE.filter(c => inPack(pk, c)).length} cards`;
  }
  function build() {
    const tp = $("tp"); tp.innerHTML = `<div class="tp-car" id="tpCar">${PACKS.map((p, i) => `<div class="tp-s" data-i="${i}" style="--pc:${p.col}">${packHTML(p)}</div>`).join("")}</div>
      <h2 class="tp-name"></h2>
      <div class="tp-pills"><a class="tp-pill" href="#/inside"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M1.500 12S5.500 5 12 5s10.500 7 10.500 7-4 7-10.500 7S1.500 12 1.500 12Z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3.200" fill="currentColor"/></svg>What's inside</a><span class="tp-pill tp-sub">7 cards</span></div>
      <div class="tp-maxh"><i></i><span>Max Pull</span><i></i></div>
      <div class="tp-row"><div class="tp-min"><small>Min Value</small><b>$0</b></div><div class="tp-big">$0</div><a class="tp-style" href="#/inside"><small>Pack style</small><b>Odds <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.600" stroke-linecap="round" stroke-linejoin="round"/></svg></b></a></div>
      <button class="tp-buy" data-open type="button"><span>Open</span></button>
      <p class="tp-fine">Play money only. Nothing is charged or paid out.</p>`;
    car = $("tpCar"); curIdx = -1;
    [...car.children].forEach((s, i) => { const pkEl = s.firstChild, ps = new PackScreen(pkEl, PACKS[i]); s._ps = ps; });
    car.addEventListener("scroll", () => { clearTimeout(scrollT); scrollT = setTimeout(settle, 90); mark(); }, { passive: true });
    car.addEventListener("click", e => { const s = e.target.closest(".tp-s"); if (!s) return; const i = +s.dataset.i; if (i === curIdx) { if (performance.now() - stageShut < 500) return; openPack(); } else go(i); });
  }
  const centred = () => { const r = car.getBoundingClientRect(), mid = r.left + r.width / 2; let best = 0, bd = 1e9; [...car.children].forEach((s, i) => { const q = s.getBoundingClientRect(), d = Math.abs(q.left + q.width / 2 - mid); if (d < bd) { bd = d; best = i; } }); return best; };
  function mark() { const r = car.getBoundingClientRect(), mid = r.left + r.width / 2; [...car.children].forEach(s => { const q = s.getBoundingClientRect(), d = Math.min(1, Math.abs(q.left + q.width / 2 - mid) / (q.width * 1.05)); s.style.setProperty("--d", d.toFixed(3)); }); }
  function go(i, instant) { const s = car.children[i]; if (!s) return; const left = s.offsetLeft - (car.clientWidth - s.clientWidth) / 2; car.scrollTo({ left, behavior: instant || matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }
  function settle() { const i = centred(); if (i === curIdx) return; pick(i, true); }
  function pick(i, fromScroll) {
    curIdx = i; const pk = PACKS[i]; [...car.children].forEach((s, k) => { const on = k === i; s.classList.toggle("on", on); if (on) { s._ps.fit(); s._ps.start(); } else { s._ps.stop(); s._ps.fit(); s._ps.frame(performance.now()); } });
    if (state.pack !== pk.id) { state.pack = pk.id; persist(); if (fromScroll) { Snd.whoosh && Snd.whoosh(); buzz(8); } }
    document.body.dataset.pack = pk.id; document.body.style.setProperty("--halo", `color-mix(in srgb, ${pk.col} 24%, transparent)`); document.body.style.setProperty("--halo2", `color-mix(in srgb, ${pk.col} 60%, transparent)`); text(pk);
  }
  function home() {
    const tp = $("tp"); if (!tp) return; const want = PACKS.findIndex(p => p.id === state.pack);
    if (!car || !car.isConnected) { build(); requestAnimationFrame(() => { go(want, true); requestAnimationFrame(() => { mark(); pick(want); }); }); return; }
    if (want !== curIdx && want >= 0 && !settling) { go(want, true); pick(want); } else text(PACKS[Math.max(0, curIdx)]);
  }

  return { title, menu, home, frame, bars, when, TITLES, go: i => car && go(i) };
})();

/* ---- the glass lens that slides between the tabs: it carries the active tab magnified inside it, stretches while it moves, and shows a rainbow rim as light bends at its edge ---- */
const Glass = (() => {
  let x = 0, v = 0, tx = 0, raf = 0, ready = false, idx = 0, last = 0;
  const bar = () => $("btabs"), lens = () => $("lens"), inn = () => $("lensIn");
  function geom(i) { const b = bar(); if (!b) return null; const links = [...b.querySelectorAll("a")], a = links[i]; if (!a) return null; const br = b.getBoundingClientRect(), r = a.getBoundingClientRect(); return { left: r.left - br.left, w: r.width, W: br.width, H: br.height }; }
  function apply() {
    const L = lens(), I = inn(), b = bar(); if (!L || !b) return; const g0 = geom(idx); if (!g0) return; const stretch = Math.min(.5, Math.abs(v) / 1100), w = g0.w * (1 + stretch) + 4, left = x - stretch * g0.w / 2 - 2;
    L.style.width = w.toFixed(1) + "px"; L.style.transform = `translateX(${left.toFixed(1)}px)`; L.style.setProperty("--rim", (.28 + Math.min(.72, Math.abs(v) / 650)).toFixed(2));
    const bp = parseFloat(getComputedStyle(b).paddingLeft) || 0; I.style.width = g0.W + "px"; I.style.left = (-left - bp - 1) + "px"; const cx = left + w / 2; I.style.transformOrigin = `${(cx + bp).toFixed(1)}px 50%`; I.style.transform = `scale(${(1.12 + Math.min(.1, Math.abs(v) / 4000)).toFixed(3)})`;
  }
  function tick(now) {
    const dt = Math.min(.034, (now - (last || now)) / 1000); last = now; const k = 240, c = 21; v += ((tx - x) * k - v * c) * dt; x += v * dt; apply();
    if (Math.abs(tx - x) > .15 || Math.abs(v) > .5) raf = requestAnimationFrame(tick); else { x = tx; v = 0; apply(); raf = 0; last = 0; }
  }
  function build() { const b = bar(); if (!b || !inn()) return; inn().innerHTML = [...b.querySelectorAll("a")].map(a => `<span class="li">${a.innerHTML}</span>`).join(""); ready = true; b.classList.add("lensed"); }
  function to(i, jump) {
    if (!ready) build(); const g0 = geom(i); if (!g0) return; idx = i; tx = g0.left;
    if (jump || reducedMotion()) { x = tx; v = 0; apply(); return; } if (!raf) raf = requestAnimationFrame(tick);
  }
  const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  function sync(view) { const links = [...document.querySelectorAll("#btabs a")], i = links.findIndex(a => a.dataset.v === (TAB_OF[view] || view)); if (i >= 0) to(i, !ready); }
  addEventListener("resize", () => { if (ready) to(idx, true); });
  return { sync, to };
})();

addEventListener("hashchange", () => Shell.menu(false));
const _renderHome = renderHome; renderHome = function () { _renderHome(); Shell.home(); };

/* ---- what's inside ---- */
function insideOdds(pk) {
  const price = packPrice(pk) / UNIT, slot = pk.slots[RARE_SLOT], t = slot.reduce((a, [, w]) => a + w, 0);
  const edges = [0, price * .5, price, price * 2, price * 5, price * 20, Infinity], names = ["below half the pack", "half the pack to the pack", "1x to 2x the pack", "2x to 5x", "5x to 20x", "20x and up"];
  const cols = ["#8c919b", "#3be477", "#4d8dff", "#a96bff", "#ff5d5d", "#ffd23f"];
  const out = edges.slice(0, -1).map((lo, i) => ({ lo, hi: edges[i + 1], p: 0, n: names[i], c: cols[i] }));
  for (const [id, w] of slot) { const v = BY_ID[id].val / UNIT, b = out.find(o => v >= o.lo && v < o.hi); if (b) b.p += w / t; }
  return out.filter(o => o.p > 0);
}
function renderInside() {
  const pk = curPack(), price = packPrice(pk), slot = pk.slots[RARE_SLOT], t = slot.reduce((a, [, w]) => a + w, 0);
  const grails = [...slot].sort((a, b) => BY_ID[b[0]].val - BY_ID[a[0]].val).slice(0, 4).map(([id, w]) => BY_ID[id]);
  const feed = API.on && typeof Live.feed === "function" ? Live.feed().filter(e => BY_ID[e.id]).slice(0, 8) : [];
  const mine = (state.opens || []).slice().reverse().flatMap(o => o.c.map(([no]) => ({ no, t: o.t }))).filter(x => BY_NO[x.no]).slice(0, 8);
  const hit = (c, tt, who) => `<button class="hit" data-card="${c.no}" style="--rc:${RAR[c.rar].col}"><span class="hit-art"><img src="${imgOf(c, "", true)}" alt="" draggable="false"></span><span class="hit-t"><b>${money(c.val).replace(/\.00$/, "")}</b><i>${esc(c.name)}</i><small>${esc(who)} · ${Shell.when(tt)}</small></span></button>`;
  const hits = feed.length ? feed.map(e => hit(BY_ID[e.id], e.t, "a player")).join("") : mine.length ? mine.map(x => hit(BY_NO[x.no], x.t, "you")).join("") : `<p class="small in-none">${API.on ? "No hits yet." : "The live feed needs the game's server. Nothing is shown rather than something made up."}</p>`;
  const od = insideOdds(pk);
  $("inBody").innerHTML = `<div class="in-head"><button class="hback" data-back aria-label="Back">←</button></div>
    <div class="in-title"><span class="in-pack" style="--pc:${pk.col}"></span><div><small>${esc(pk.name)} pack</small><h1>What's Inside</h1></div></div>
    ${Shell.frame("Sell-back and fair play", `<p>Every card is a picture made of text. Each pack has 7 cards, and card 5 is the rare slot. Cards sell back for 90% of what they are worth. This is play money: nothing is charged or paid out.</p>`, "in-note")}
    <h3 class="in-h"><i class="live-dot"></i> ${feed.length ? "Recent hits" : "Your recent pulls"}</h3><div class="hits">${hits}</div>
    <h3 class="in-h">Grails</h3><div class="grails">${grails.map(c => `<button class="grail" data-card="${c.no}" style="--rc:${RAR[c.rar].col}"><span class="gr-art"><img src="${imgOf(c, "", true)}" alt="" draggable="false"></span><b>${money(c.val).replace(/\.00$/, "")}</b><i>${esc(c.name)}</i><small>1 in ${fmt(Math.round(t / (slot.find(([id]) => id === c.id)[1])))} packs</small></button>`).join("")}</div>
    <h3 class="in-h">Payout odds <small>(card 5)</small></h3>${Shell.frame(esc(pk.name).toUpperCase(), od.map(o => `<div class="orow" style="--c:${o.c}"><span class="o-l">${o.n}</span><span class="o-bar"><i style="width:${Math.max(4, o.p / Math.max(...od.map(z => z.p)) * 100).toFixed(1)}%"></i></span><span class="o-p">${(o.p * 100).toFixed(1)}%</span></div>`).join("") + `<p class="small">The pack costs ${money(price)}. The full odds for every card are on the <a class="linkbtn" href="#/odds">odds page</a>.</p>`, "in-odds")}`;
}

/* ---- rewards ---- */
function renderRewards() {
  const fp = state.freePacks, st = state.streak && state.streak.n || 0, ready = dailyReady();
  $("rwBody").innerHTML = `${Shell.frame("YOUR FREE PACK", `<div class="rw-row"><div><b>${fp ? fp + " free pack" + (fp > 1 ? "s" : "") + " waiting" : ready ? "today's pack is ready" : "all collected today"}</b><small>${ready ? "tap below to claim it" : "a new one every day. Missing a day does not end your streak."}</small></div><span class="rw-st"><b>${st}</b><small>day streak</small></span></div>${fp || ready ? `<button class="abtn" data-open>◆ OPEN A FREE PACK</button>` : ""}`)}
    ${Shell.frame("GOALS", Goals.html())}
    ${Shell.frame("INVITE A FRIEND", `<p class="small">You both get a free pack when they join and open it.</p><a class="abtn soft" href="#/invite">◆ GET YOUR LINK</a>`)}
    <p class="dr-fine">Play money only. Nothing is charged or paid out. 18+</p>`;
}
