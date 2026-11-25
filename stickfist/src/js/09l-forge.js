/* ============================================================================
   8l. THE FORGE. Spare cards become the card you are after.
   Packs hand out a lot of commons and uncommons. The forge gives them somewhere to go: trade in spare cards of one rarity and
   get the card you pick from the next rarity up in the same set. So every pack moves you toward a card you chose, even
   when its best card was not the one you wanted.
   Kept fair to both sides by three rules:
   - A spare is a plain extra copy. Styled copies are never used, and you always keep one copy of every card.
   - The price is set so that even the cheapest spares are worth more, at their starting values, than the card they make
     (15% more), so the forge never hands out value: selling the spares always pays at least as much as forging.
   - A forged card is always the plain look. Styles only come out of packs.
   Nothing here touches what packs contain or their odds.
   ========================================================================== */
const Forge = (() => {
  const tier = c => RAR[c.rar].tier;
  // the cards one rarity down in the same set (the nearest rarity below that the set has)
  function below(card) { const lower = CARDS.filter(c => c.set === card.set && tier(c) < tier(card)); if (!lower.length) return []; const t = Math.max(...lower.map(tier)); return lower.filter(c => tier(c) === t); }
  function need(card) { const m = below(card); return m.length ? Math.ceil(1.15 * card.val / Math.min(...m.map(c => c.val))) : 0; }
  // your spare copies of those cards, cheapest first
  function spares(card) {
    const out = []; for (const m of below(card)) { const cs = state.vault.filter(c => c.no === m.no), plain = cs.filter(c => !c.fx).sort((a, b) => valueOf(b) - valueOf(a)); out.push(...(cs.some(c => c.fx) ? plain : plain.slice(1))); }
    return out.sort((a, b) => valueOf(a) - valueOf(b));
  }
  const info = card => { const n = need(card); if (!n || card.retired) return null; const have = spares(card).length, m = below(card); if (!have && m.every(c => c.retired)) return null;   // nothing to forge from cards no pack holds any more, unless you still have spares of them
    return { n, have, ok: have >= n, rar: RAR[m[0].rar].name, set: SETS[card.set].name }; };
  function make(no) {
    const card = BY_NO[no], i = card && info(card); if (!i || !i.ok) return null; const used = spares(card).slice(0, i.n), gone = new Set(used.map(c => c.uid)), paid = used.reduce((a, c) => a + valueOf(c), 0);
    state.vault = state.vault.filter(c => !gone.has(c.uid)); const copy = mint(card, false, null, paid); copy.fx = ""; copy.forged = 1; state.vault.push(copy); state.s.forged = (state.s.forged || 0) + 1; noteFound(); save(); return copy;
  }
  // in the card window: what this card costs to forge, how far along you are, and the button
  function html(card) {
    const i = info(card); if (!i) return ""; const pc = Math.min(1, i.have / i.n), own = state.vault.some(c => c.no === card.no);
    return `<div class="forge${i.ok ? " rdy" : ""}"><div class="fg-top"><span class="label">Forge ${own ? "another" : "this card"}</span><b>${Math.min(i.have, i.n)} / ${i.n}</b></div>
      <div class="gbar" role="img" aria-label="${i.have} of ${i.n} spare cards"><i style="width:${(pc * 100).toFixed(1)}%"></i></div>
      <p class="small">Trade in <b>${i.n} spare ${esc(i.rar)}</b> cards from ${esc(i.set)} for one ${esc(card.name)}. A spare is a plain extra copy: you always keep one of each, and styled copies are never used.${i.ok ? "" : ` You have ${i.have}.`}</p>
      <button class="btn ${i.ok ? "solid free" : "ghost"}" data-forge="${card.no}"${i.ok ? "" : " disabled"}>${i.ok ? `forge ${esc(card.name)}` : `${i.n - i.have} more spare${i.n - i.have === 1 ? "" : "s"} to go`}</button></div>`;
  }
  // on Me: the cards you are closest to forging, the ones you have never found first
  function listHTML() {
    const rows = CARDS.map(c => ({ c, i: info(c) })).filter(r => r.i && r.i.have > 0).map(r => Object.assign(r, { own: state.vault.some(v => v.no === r.c.no), pc: Math.min(1, r.i.have / r.i.n) })).sort((a, b) => (b.i.ok - a.i.ok) || (a.own - b.own) || (b.pc - a.pc) || (b.c.val - a.c.val)).slice(0, 3);
    if (!rows.length) return "";
    return `<h3 class="sec">Forge</h3><p class="small fg-lead">Spare cards become the card you are after: trade in extras of one rarity for the card you pick from the next one up.</p><div class="fg-list">${rows.map(r => `<button class="fg-row${r.i.ok ? " rdy" : ""}" data-card="${r.c.no}"><img src="${imgOf(r.c, "", true)}" alt="" loading="lazy"><span class="fg-main"><b>${esc(r.c.name)}</b><span class="gbar"><i style="width:${(r.pc * 100).toFixed(1)}%"></i></span><small>${r.i.ok ? "Ready to forge" : `${r.i.have} of ${r.i.n} spare ${esc(r.i.rar)}s`}${r.own ? "" : " · not found yet"}</small></span><span class="fg-go" style="color:${RAR[r.c.rar].col}">${RAR[r.c.rar].name}</span></button>`).join("")}</div>`;
  }
  return { info, make, html, listHTML, need, spares };
})();
