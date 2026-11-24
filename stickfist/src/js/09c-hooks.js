/* ============================================================================
   8c. THE TAPE AND THE ALERTS. A ticker that never stops, and ASCII pictures that tell you when a card you hold takes off or drops fast.
   ========================================================================== */
// ---- the tape: every card and the latest simulated trades, scrolling across the top of every page
let tapeAt = 0;
function renderTape() {
  const el = $("tapeIn"); if (!el || (el.firstChild && Date.now() - tapeAt < 60000)) return; tapeAt = Date.now();
  const mv = movers().rows.slice().sort((a, b) => Math.abs(b.p24) - Math.abs(a.p24)).slice(0, 12), fd = [], items = [], rn = { up: [] };
  const tk = (cls, a, b) => `<span class="tk ${cls}"><b>${a}</b> ${b}</span>`;
  if (rn.up[0]) items.push(tk("up", "BEST RUN THIS WEEK", `${esc(rn.up[0].c.name.toUpperCase())} ▲ ${pctShort(rn.up[0].up)}`));
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
const FALL = f => `    .---.
    |   |
    |   |
 ___|   |___
 \\         /
  \\       /
   \\     /
    \\   /
     \\ /
      v
   ${["v  v  v", " v  v  v", "v   v  v", "  v v v "][f % 4]}`;
// (price alert banners were removed: nothing in the game pops up on its own)

// ---- the hottest card in the market, as a picture: an ASCII rocket or skull, and its day drawn as an ASCII line chart
let heroKey = "", heroFrame = 0;
function renderHero(rows, rn) {
  const el = $("mHero"); if (!el) return; const top = rows.slice().sort((a, b) => Math.abs(Math.log(1 + b.p24)) - Math.abs(Math.log(1 + a.p24)))[0], bu = rn.up[0], bd = rn.dn[0];
  // the biggest thing: a move happening right now, or the biggest run of the week, whichever is larger in either direction
  const cands = []; if (top) cands.push({ kind: "now", size: Math.abs(Math.log(1 + top.p24)), up: top.p24 > 0, c: top.c, pct: top.p24, was: top.was, nowP: top.now }); if (bu) cands.push({ kind: "run", size: Math.log(1 + bu.up), up: true, c: bu.c, pct: bu.up, ago: bu.upAgo, peak: bu.upPrice, nowP: bu.now }); if (bd) cands.push({ kind: "run", size: Math.abs(Math.log(1 + bd.dn)), up: false, c: bd.c, pct: bd.dn, ago: bd.dnAgo, peak: bd.dnPrice, nowP: bd.now });
  cands.sort((a, b) => b.size - a.size); const hero = cands[0]; if (!hero || hero.size < Math.log(1.15)) { el.innerHTML = ""; heroKey = ""; return; }
  const up = hero.up, key = hero.c.no + hero.kind + (up ? "u" : "d") + MK.tick(); if (key === heroKey) return; const fresh = heroKey.slice(0, 5) !== key.slice(0, 5); heroKey = key;
  const hours = hero.kind === "now" ? 24 : 168, pg = plotGrid(MK.series(hero.c, hours, 96), innerWidth > 760 ? 100 : 40, innerWidth > 760 ? 9 : 7).grid.map(r => r.join("")).join("\n");
  const title = hero.kind === "now" ? `${esc(hero.c.name)} ${up ? "is taking off" : "is dropping"}` : `${esc(hero.c.name)} ${up ? "took off" : "dropped"} ${whenText(hero.ago)}`;
  const sub = hero.kind === "now" ? `${money(hero.was)} → ${money(hero.nowP)} in 24 hours` : `${up ? "a run of" : "a fall of"} ${pctShort(hero.pct)} in a day · now ${money(hero.nowP)}${up ? ` (${pctShort(hero.nowP / hero.peak - 1)} from the peak)` : ""}`;
  el.innerHTML = `<button class="hero ${up ? "up" : "dn"}" data-card="${hero.c.no}"><pre class="sprite" id="heroArt" aria-hidden="true">${up ? ROCKET(0) : FALL(0)}</pre><div class="info"><h2>${title}</h2><div class="big">${pctShort(hero.pct)}</div><div class="dim">${sub}</div><pre class="plot${fresh ? " wipe" : ""}" aria-hidden="true">${pg}</pre></div></button>`;
}
// the countdown to the next price: a line that fills up over 20 seconds
function tickLive() {
  const s = 20 - Math.floor((Date.now() % 20000) / 1000), n = 12, k = Math.round((20 - s) / 20 * n);
  document.querySelectorAll(".live").forEach(e => { e.innerHTML = `<i></i>live · next price in ${s}s <span>${"━".repeat(k)}${"─".repeat(n - k)}</span>`; });
  const a = $("heroArt"); if (a && !reduced) { heroFrame++; a.textContent = a.closest(".hero").classList.contains("up") ? ROCKET(heroFrame) : FALL(heroFrame); }
}
