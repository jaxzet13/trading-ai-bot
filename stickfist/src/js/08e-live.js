/* ============================================================================
   8e. LIVE. The third tab: what other players are pulling, as it happens.
   Everything on it is real. The feed is the hits (a legendary or better) that players actually pulled, kept by the server,
   which re-draws each one itself before listing it (see /api/fair/hit in server.js); nothing here is made up, padded or
   replayed. Under it, the rarest cards of each pack with how many times each has ever been found, and whether you have it.
   Players are named by two letters and dots, never by their email.
   It is here to make you want the cards, and it does that with true things only: the odds on it are the published odds,
   and they are the same for everyone. With no server (a preview, a file) there is no feed to show, and the page says so
   rather than inventing one.
   ========================================================================== */
const Live = (() => {
  let data = null, at = 0, busy = false, timer = 0, seen = 0;
  async function pull(force) {
    if (!API.on || busy || (!force && Date.now() - at < 9000)) return; busy = true; const r = await API.get("feed"); busy = false;
    if (r && Array.isArray(r.feed)) { data = r; at = Date.now(); if (view === "live") render(); }
  }
  const ago = t => { const s = Math.max(0, Math.round((Date.now() - t) / 1000)); return s < 50 ? "just now" : s < 3600 ? Math.max(1, Math.round(s / 60)) + "m" : s < 86400 ? Math.round(s / 3600) + "h" : Math.round(s / 86400) + "d"; };
  const odds = c => "1 in " + fmt(Math.round(1 / Math.max(1e-9, packP(c.id))));
  const found = id => data && data.found ? data.found[id] || 0 : null;
  const foundS = n => n == null ? "" : n === 0 ? "never found" : n === 1 ? "found once" : `found ${fmt(n)} times`;
  // the cards to want: the rarest few of each pack
  const chase = () => PACKS.flatMap(pk => LIVE.filter(c => c.set === pk.set && RAR[c.rar].tier >= 4).sort((a, b) => packP(a.id) - packP(b.id)).slice(0, 4));
  function render() {
    const el = $("lvBody"); if (!el) return; const feed = data ? data.feed.filter(e => BY_ID[e.id]) : [], day = feed.filter(e => Date.now() - e.t < 864e5);
    const top = day.slice().sort((a, b) => BY_ID[b.id].val - BY_ID[a.id].val)[0], best = chase().sort((a, b) => b.val - a.val)[0];
    // the hero: the biggest pull of the last day; with none, the card nobody has
    const hc = top ? BY_ID[top.id] : best, R = RAR[hc.rar], mine = copiesOf(hc.no).length, n = found(hc.id);
    const hero = `<button class="lv-hero" data-card="${hc.no}" style="--rc:${R.col}" aria-label="${esc(hc.name)}"><span class="lv-art"><img src="${imgOf(hc)}" alt="" draggable="false"></span>
      <span class="lv-ht"><small class="lv-k">${top ? "biggest pull today" : n === 0 ? "nobody has found it yet" : "the one to find"}</small><b class="lv-n">${esc(hc.name)}</b><span class="lv-r"><i></i>${esc(R.name)} · ${odds(hc)} packs</span>
      <span class="lv-v">${money(hc.val)}</span><small class="lv-w">${top ? `pulled by <b>${esc(top.who)}</b> · ${ago(top.t)}` : n ? foundS(n) + " so far" : API.on ? "it is in the pack right now" : ""}${mine ? " · you have it" : ""}</small></span></button>`;
    const stat = data ? `<div class="lv-stat"><div><b>${fmt(data.day || 0)}</b><small>hits today</small></div><div><b>${day.length ? money(BY_ID[top.id].val).replace(/\\.00$/, "") : "–"}</b><small>biggest today</small></div><div><b>${fmt(Object.values(data.found || {}).reduce((a, b) => a + b, 0))}</b><small>hits ever</small></div></div>` : "";
    const rows = feed.slice(0, 10).map(e => { const c = BY_ID[e.id], r = RAR[c.rar], fresh = e.t > seen && seen > 0; return `<button class="lv-row${fresh ? " new" : ""}" data-card="${c.no}" style="--rc:${r.col}"><span class="thumb"><img src="${imgOf(c, "", true)}" alt="" loading="lazy" draggable="false"></span><span class="lv-rt"><b><i>${esc(e.who)}</i> pulled ${esc(c.name)}</b><small><em>${esc(r.name)}</em> · ${odds(c)} · ${money(c.val)}</small></span><time>${ago(e.t)}</time></button>`; }).join("");
    const list = !API.on ? `<p class="lv-none">The live feed needs the game's server, and this copy is running without one. Nothing is shown rather than something made up.</p>` : !data ? `<p class="lv-none">Loading…</p>` : rows || `<p class="lv-none">No hits yet. The next legendary anyone pulls shows up here, yours included.</p>`;
    const tiles = chase().map(c => { const r = RAR[c.rar], k = found(c.id), have = copiesOf(c.no).length; return `<button class="lv-tile${have ? " have" : ""}" data-card="${c.no}" style="--rc:${r.col}"><span class="lv-ti"><img src="${imgOf(c, "", true)}" alt="" loading="lazy" draggable="false"><i class="lv-own">${have ? "yours" : "not yet"}</i></span><b>${esc(c.name)}</b><small><em>${esc(r.name)}</em> · ${odds(c)}</small><span class="lv-tv">${money(c.val)}</span><small class="lv-f">${foundS(k)}</small></button>`; }).join("");
    el.live = `<div class="lv-top"><h1 class="ttl">Live</h1><span class="lv-live"><i></i>real pulls, as they happen</span></div>${hero}${stat}
      <h3 class="sec">Just pulled</h3><div class="lv-feed">${list}</div>
      <h3 class="sec">Still out there</h3><div class="lv-grid">${tiles}</div>
      <a class="btn solid lv-go" href="#/">Open a pack</a>
      <p class="small lv-fine">Every pull listed here was made by a player and checked by the server before it was listed. Everyone gets the same odds, and most packs do not hold one of these. <a class="linkbtn" href="#/odds">See the odds</a></p>`;
    if (feed.length) seen = Math.max(seen, feed[0].t);
  }
  function start() { pull(true); if (!timer) timer = setInterval(() => { if (view === "live" && !document.hidden) pull(); }, 10000); }
  return { render: () => { render(); start(); }, pull };
})();
