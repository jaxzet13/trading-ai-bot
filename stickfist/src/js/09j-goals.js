/* ============================================================================
   8j. GOALS. Things to aim for, each with a free pack or two at the end: filling the collection, opening packs, and selling well.
   A goal is finished by playing, never by paying, and nothing here has a timer. Finished goals wait until you claim them.
   ========================================================================== */
const Goals = (() => {
  const foundN = () => { noteFound(); return Object.keys(state.found).length; };
  const LIST = [
    { id: "f5", t: "Find 5 different cards", n: 5, v: foundN, r: 1 },
    { id: "f10", t: "Find 10 different cards", n: 10, v: foundN, r: 1 },
    { id: "f15", t: "Find 15 different cards", n: 15, v: foundN, r: 1 },
    { id: "f20", t: "Find 20 different cards", n: 20, v: foundN, r: 1 },
    { id: "f25", t: "Find 25 different cards", n: 25, v: foundN, r: 2 },
    { id: "fall", t: `Find all ${CARDS.length} cards`, n: CARDS.length, v: foundN, r: 3 },
    { id: "p10", t: "Open 10 packs", n: 10, v: () => state.s.packs, r: 1 },
    { id: "p50", t: "Open 50 packs", n: 50, v: () => state.s.packs, r: 1 },
    { id: "p100", t: "Open 100 packs", n: 100, v: () => state.s.packs, r: 2 },
    { id: "s1", t: "Sell your first card", n: 1, v: () => state.s.nSold || 0, r: 1 },
    { id: "x2", t: "Sell a card for 2× what it started at", n: 2, v: () => state.s.bestX || 0, r: 1, x: true },
    { id: "x5", t: "Sell a card for 5× what it started at", n: 5, v: () => state.s.bestX || 0, r: 2, x: true },
    { id: "x10", t: "Sell a card for 10× what it started at", n: 10, v: () => state.s.bestX || 0, r: 3, x: true },
  ];
  const got = () => (state.goals = state.goals || {});
  const done = g => g.v() >= g.n, claimed = g => !!got()[g.id];
  const ready = () => LIST.filter(g => done(g) && !claimed(g));
  function claim(id) {
    const g = LIST.find(x => x.id === id); if (!g || claimed(g) || !done(g)) return;
    got()[g.id] = Date.now(); state.freePacks += g.r; save(); renderChips(); Snd.level(); buzz([30, 40, 30, 40, 60]);
    toast(`Goal done: +${g.r} free pack${g.r > 1 ? "s" : ""}`); badge(); if (view === "profile") renderProfile(); if (view === "home") renderHome();
  }
  let open = false;
  function html() {
    const rd = ready(), rest = LIST.filter(g => !claimed(g) && !done(g)).sort((a, b) => b.v() / b.n - a.v() / a.n), nDone = LIST.filter(claimed).length;
    const show = open ? rd.concat(rest, LIST.filter(claimed)) : rd.concat(rest).slice(0, 2);
    const row = g => { const v = Math.min(g.n, g.v()), c = claimed(g), d = done(g), pc = Math.max(0, Math.min(1, v / g.n));
      return `<div class="goal${c ? " got" : d ? " rdy" : ""}"><div class="gmain"><b>${esc(g.t)}</b><div class="gbar" role="img" aria-label="${g.x ? (Math.round(v * 10) / 10) + "×" : Math.floor(v)} of ${g.n}${g.x ? "×" : ""}"><i style="width:${(pc * 100).toFixed(1)}%"></i></div><small>${c ? "done" : g.x ? `best so far ${v ? (Math.round(v * 10) / 10) + "×" : "–"}` : `${Math.floor(v)} of ${g.n}`}</small></div>${c ? `<span class="gdone" aria-hidden="true">✓</span>` : d ? `<button class="btn solid free gclaim" data-goal="${g.id}">Claim +${g.r}</button>` : `<span class="grew">+${g.r} pack${g.r > 1 ? "s" : ""}</span>`}</div>`; };
    return `<div class="goals">${show.map(row).join("")}</div><button class="linkbtn plain gmore" id="gMore">${open ? "Show less" : `All goals · ${nDone} of ${LIST.length} done${rd.length > 2 ? ` · ${rd.length} to claim` : ""}`}</button>`;
  }
  function toggle() { open = !open; if (view === "profile") renderProfile(); }
  function badge() {}                                                                      // no badge dots anywhere: a finished goal waits quietly on the Me page and in the pack result
  // the closest goal you haven't finished, for a one-line nudge after a pack
  function next() { const g = LIST.filter(g => !claimed(g) && !done(g) && !g.x).sort((a, b) => b.v() / b.n - a.v() / a.n)[0]; return g ? { g, left: g.n - Math.floor(g.v()) } : null; }
  return { html, claim, toggle, badge, ready, next, LIST };
})();
