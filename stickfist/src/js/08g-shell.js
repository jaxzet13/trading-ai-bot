/* ============================================================================
   8g. THE SHELL: a menu, a title for every page, and two pages that hang off the tab bar: What's inside (a pack's best cards, its odds, the hits) and Rewards.
   Everything is drawn with text: box lines, brackets, block bars, glyphs for icons.
   ========================================================================== */
const Shell = (() => {
  const TITLES = { home: "Packs", collection: "My Collection", rewards: "Rewards", profile: "Account", inside: "What's Inside", invite: "Invite", odds: "Odds", live: "Live", market: "Movers", limited: "Requiem" };
  function title(v) { const el = $("hTitle"); if (el) el.textContent = TITLES[v] || "STIXX"; }
  const frame = (t, body, cls) => `<section class="abox${cls ? " " + cls : ""}"><span class="atitle">┤ ${t} ├</span>${body}</section>`;
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

  /* ---- the pack page: what is in it, in one line ---- */
  function home() {
    const pk = curPack(), cards = [...new Set(pk.slots.flat().map(([id]) => id))].map(id => BY_ID[id]).filter(Boolean), vals = cards.map(c => c.val / UNIT), lo = Math.min(...vals), hi = Math.max(...vals);
    const el = $("mmRow"); if (!el) return; el.innerHTML = `<div class="mm-l"><small>MIN CARD</small><b>${money(lo * UNIT)}</b></div><div class="mm-c"><small>TOP CARD</small><b>${money(hi * UNIT).replace(/\.00$/, "")}</b></div><a class="mm-r" href="#/inside"><small>PAYOUT ODDS</small><b>view ›</b></a>`;
    $("packName").textContent = pk.name;
  }

  return { title, menu, home, frame, bars, when, TITLES };
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
    <div class="in-title"><span class="in-pack" style="--pc:${pk.col}">▓</span><div><small>${esc(pk.name)} pack</small><h1>What's Inside</h1></div></div>
    ${Shell.frame("FAIR PLAY", `<p>Every card is a picture made of text. Each pack has 7 cards, and card 5 is the rare slot. Cards sell back for 90% of what they are worth. Play money only: nothing is charged or paid out.</p>`, "in-note")}
    <h3 class="in-h"><i class="live-dot"></i> ${feed.length ? "Recent hits" : "Your recent pulls"}</h3><div class="hits">${hits}</div>
    <h3 class="in-h">Grails</h3><div class="grails">${grails.map(c => `<button class="grail" data-card="${c.no}" style="--rc:${RAR[c.rar].col}"><span class="gr-art"><img src="${imgOf(c, "", true)}" alt="" draggable="false"></span><b>${money(c.val).replace(/\.00$/, "")}</b><i>${esc(c.name)}</i><small>1 in ${fmt(Math.round(t / (slot.find(([id]) => id === c.id)[1])))} packs</small></button>`).join("")}</div>
    <h3 class="in-h">Payout odds <small>(card 5)</small></h3>${Shell.frame(esc(pk.name).toUpperCase(), od.map(o => `<div class="orow" style="--c:${o.c}"><span class="o-l">${o.n}</span><span class="o-b">${Shell.bars(o.p, 18)}</span><span class="o-p">${(o.p * 100).toFixed(1)}%</span></div>`).join("") + `<p class="small">The pack costs ${money(price)}. The full odds for every card are on the <a class="linkbtn" href="#/odds">odds page</a>.</p>`, "in-odds")}`;
}

/* ---- rewards ---- */
function renderRewards() {
  const fp = state.freePacks, st = state.streak && state.streak.n || 0, ready = dailyReady();
  $("rwBody").innerHTML = `${Shell.frame("YOUR FREE PACK", `<div class="rw-row"><div><b>${fp ? fp + " free pack" + (fp > 1 ? "s" : "") + " waiting" : ready ? "today's pack is ready" : "all collected today"}</b><small>${ready ? "tap below to claim it" : "a new one every day. Missing a day does not end your streak."}</small></div><span class="rw-st"><b>${st}</b><small>day streak</small></span></div>${fp || ready ? `<button class="abtn" data-open>◆ OPEN A FREE PACK</button>` : ""}`)}
    ${Shell.frame("GOALS", Goals.html())}
    ${Shell.frame("INVITE A FRIEND", `<p class="small">You both get a free pack when they join and open it.</p><a class="abtn soft" href="#/invite">◆ GET YOUR LINK</a>`)}
    <p class="dr-fine">Play money only. Nothing is charged or paid out. 18+</p>`;
}
