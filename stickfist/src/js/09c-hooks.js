/* ============================================================================
   8c. THE TAPE AND THE ALERTS. A ticker that never stops, and ASCII pictures that tell you when a card you hold moons or gets rugged.
   ========================================================================== */
// ---- the tape: every card and the latest simulated trades, scrolling across the top of every page
let tapeAt = 0;
function renderTape() {
  const el = $("tapeIn"); if (!el || (el.firstChild && Date.now() - tapeAt < 60000)) return; tapeAt = Date.now();
  const mv = movers().rows.slice().sort((a, b) => Math.abs(b.p24) - Math.abs(a.p24)), fd = MK.feed(6), items = [];
  const tk = (cls, a, b) => `<span class="tk ${cls}"><b>${a}</b> ${b}</span>`;
  for (let i = 0; i < Math.max(mv.length, fd.length); i++) {
    if (mv[i]) items.push(tk(mv[i].p24 >= 0 ? "up" : "dn", esc(mv[i].c.name.toUpperCase()), `${money(mv[i].now)} ${mv[i].p24 >= 0 ? "▲" : "▼"} ${pctShort(mv[i].p24)}`));
    if (fd[i]) items.push(tk(fd[i].pct >= 0 ? "up" : "dn", esc(fd[i].name), `sold ${esc(fd[i].card.name)} ${fd[i].pct >= 0 ? "▲" : "▼"} ${pctShort(fd[i].pct)}`));
  }
  const one = items.join('<i>░▒▓</i>') + '<i>░▒▓</i>'; el.innerHTML = `<span class="run">${one}</span><span class="run" aria-hidden="true">${one}</span>`;
  el.style.animationDuration = Math.max(60, items.length * 4.5) + "s"; el.style.animationDelay = "-" + ((Date.now() / 1000) % parseFloat(el.style.animationDuration)).toFixed(1) + "s";
}

// ---- alerts: a card you hold doubled, or lost most of its price, in the last six hours
const ROCKET = f => `      /\\
     /  \\
    | ** |
    | ** |
   /|    |\\
  /_|_/\\_|_\\
    ${["\\||/", "(||)", "/||\\"][f % 3]}
     ${["\\/ ", "() ", "'' "][f % 3]}
   ${[" . ' .", "'  . '", ". '  ."][f % 3]}`;
const SKULL = f => `   _.-"""""-._
  /  _   _  \\
 |  (o) (o)  |
  \\    ^    /
   | ||||| |
    \\_____/
   ${["x  x  x", " x  x  x", "x   x  x", "  x x x "][f % 4]}`;
let alertIv = 0, alertTo = 0;
function hideAlert() { clearInterval(alertIv); clearTimeout(alertTo); $("alert").hidden = true; }
function showAlert(card, p) {
  const up = p > 0, cs = copiesOf(card.no), worth = cs.reduce((a, c) => a + valueOf(c), 0), cost = cs.reduce((a, c) => a + costOf(c), 0), d = worth - cost, a = $("alert");
  a.className = "alert " + (up ? "up" : "dn"); a.hidden = false;
  a.innerHTML = `<div class="art"><pre id="alertArt"></pre></div><div class="txt"><b>${esc(card.name)} ${up ? "is mooning" : "just got rugged"}</b><span>${up ? "Up" : "Down"} ${pctShort(Math.abs(p)).slice(1)} in 6 hours. ${cs.length === 1 ? "Your copy is" : "Your " + cs.length + " copies are"} worth ${money(worth)} now, ${d >= 0 ? "+" : "\u2212"}${money(Math.abs(d))} against what they were worth when you got them.</span><div class="row"><button class="btn small" data-card="${card.no}">See it</button><button class="btn small ghost" id="alertX">Dismiss</button></div></div>`;
  let f = 0; const art = $("alertArt"), step = () => { art.textContent = up ? ROCKET(f++) : SKULL(f++); }; step(); clearInterval(alertIv); if (!reduced) alertIv = setInterval(step, 140);
  clearTimeout(alertTo); alertTo = setTimeout(hideAlert, 14000);
}
function checkAlerts() {
  if (!state.ageOK || SS || !$("share").hidden || !$("alert").hidden) return;
  const now = Date.now(); state.alertAt = state.alertAt || {};
  for (const no of new Set(state.vault.map(c => c.no))) {
    const card = BY_NO[no], p = MK.pct(card, 6); if (now - (state.alertAt[no] || 0) < 6 * 36e5) continue;
    if (p >= 1 || p <= -.6) { state.alertAt[no] = now; persist(); showAlert(card, p); return; }
  }
}

// ---- the hottest card in the market, as a picture: an ASCII rocket or skull, and its day drawn as an ASCII line chart
let heroKey = "", heroFrame = 0;
function renderHero(rows) {
  const el = $("mHero"); if (!el) return; const top = rows.slice().sort((a, b) => Math.abs(b.p24) - Math.abs(a.p24))[0]; if (!top || Math.abs(top.p24) < .15) { el.innerHTML = ""; heroKey = ""; return; }
  const up = top.p24 > 0, key = top.c.no + (up ? "u" : "d") + MK.tick(); if (key === heroKey) return; const fresh = heroKey.slice(0, 4) !== key.slice(0, 4); heroKey = key;
  const pg = plotGrid(MK.series(top.c, 24, 96), innerWidth > 760 ? 100 : 40, innerWidth > 760 ? 9 : 7).grid.map(r => r.join("")).join("\n");
  el.innerHTML = `<button class="hero ${up ? "up" : "dn"}" data-card="${top.c.no}"><pre class="sprite" id="heroArt" aria-hidden="true">${up ? ROCKET(0) : SKULL(0)}</pre><div class="info"><h2>${esc(top.c.name)} ${up ? "is mooning" : "is getting rugged"}</h2><div class="big">${pctShort(top.p24)}</div><div class="dim">${money(top.was)} → ${money(top.now)} in 24 hours</div><pre class="plot${fresh ? " wipe" : ""}" aria-hidden="true">${pg}</pre></div></button>`;
}
// the countdown to the next price: a line that fills up over 20 seconds
function tickLive() {
  const s = 20 - Math.floor((Date.now() % 20000) / 1000), n = 12, k = Math.round((20 - s) / 20 * n);
  document.querySelectorAll(".live").forEach(e => { e.innerHTML = `<i></i>live · next price in ${s}s <span>${"━".repeat(k)}${"─".repeat(n - k)}</span>`; });
  const a = $("heroArt"); if (a && !reduced) { heroFrame++; a.textContent = a.closest(".hero").classList.contains("up") ? ROCKET(heroFrame) : SKULL(heroFrame); }
}
