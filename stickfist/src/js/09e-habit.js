/* ============================================================================
   8e. THE HABIT LAYER. What brings someone back, and what keeps coming back healthy.
   The pulls here are the honest ones: a market that really moves while you are away, a collection with holes in it and the odds of filling them,
   a free drop each day, a streak that forgives a missed day, a sound and a buzz for every win, price targets you set yourself. Nothing in this file
   shows a made-up number, a fake timer or a fake crowd, hides a cost, or nudges you to spend to win something back. It also keeps the other side
   in plain sight: a reminder every half hour, a limit on packs per day, a break button, and the pack's average return stated flatly.
   ========================================================================== */

/* ---- sound and touch: a small synthesiser, so a win can be heard and felt. Off with one tap, remembered. ---- */
const Snd = (() => {
  let ac = null, out = null, comp = null, dst = null;
  const ready = () => {
    if (state.mute || !tapped()) return false;
    if (!ac) { try { ac = new (window.AudioContext || window.webkitAudioContext)(); out = ac.createGain(); out.gain.value = .5; comp = ac.createDynamicsCompressor(); out.connect(comp); comp.connect(ac.destination); } catch (e) { ac = null; return false; } }
    if (ac.state === "suspended") ac.resume(); return true;
  };
  const env = (g, t, a, d, v) => { g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(v, t + a); g.gain.exponentialRampToValueAtTime(.0001, t + a + d); };
  const tone = (f, dur, type, v, at, f2) => { const t = ac.currentTime + (at || 0), o = ac.createOscillator(), g = ac.createGain(); o.type = type || "sine"; o.frequency.setValueAtTime(f, t); if (f2) o.frequency.exponentialRampToValueAtTime(f2, t + dur); env(g, t, .006, dur, v || .2); o.connect(g); g.connect(out); o.start(t); o.stop(t + dur + .05); };
  const hiss = (dur, v, at, lo, hi) => { const t = ac.currentTime + (at || 0), n = Math.floor(ac.sampleRate * dur), b = ac.createBuffer(1, n, ac.sampleRate), d = b.getChannelData(0); for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1; const s = ac.createBufferSource(); s.buffer = b; const f = ac.createBiquadFilter(); f.type = "bandpass"; f.frequency.value = Math.sqrt(lo * hi); f.Q.value = .5; const g = ac.createGain(); env(g, t, .005, dur, v); s.connect(f); f.connect(g); g.connect(out); s.start(t); s.stop(t + dur + .05); };
  const NOTE = [523.25, 587.33, 659.25, 783.99, 880, 1046.5, 1318.5, 1568];
  return {
    unlock() { ready(); },
    tear() { if (!ready()) return; hiss(.4, .35, 0, 1400, 9000); tone(140, .22, "sine", .3, 0, 50); },
    reveal(tier) {                                              // the better the card, the longer and fuller the sound
      if (!ready()) return; const n = [1, 2, 3, 4, 5, 6, 8][tier] || 1;
      for (let i = 0; i < n; i++) tone(NOTE[Math.min(7, i + (tier > 3 ? 0 : 1))], .35 + tier * .08, "triangle", .13 + tier * .01, i * .07);
      if (tier >= 2) tone(90, .35, "sine", .3, 0, 45); if (tier >= 4) { hiss(.8, .18, 0, 2000, 12000); tone(NOTE[0] / 2, 1.2, "sine", .16, .05); } if (tier >= 6) { [1, 1.25, 1.5, 2].forEach((m, i) => tone(NOTE[0] * m, 1.8, "sine", .12, .1 + i * .02)); }
    },
    sell() { if (!ready()) return; tone(1568, .25, "triangle", .14); tone(2093, .5, "triangle", .12, .06); for (let i = 0; i < 7; i++) tone([2093, 2637, 3136, 3520][i % 4], .12, "sine", .06, .14 + i * .045 + Math.random() * .02); },
    alert(up) { if (!ready()) return; if (up) { tone(300, .5, "sawtooth", .08, 0, 1200); tone(880, .3, "triangle", .12, .35); tone(1318, .5, "triangle", .1, .45); } else { tone(420, .6, "sawtooth", .08, 0, 110); tone(110, .5, "sine", .2, .15); } },
    claim(big) { if (!ready()) return; [0, 2, 4, big ? 6 : 5].forEach((k, i) => tone(NOTE[k], .4, "triangle", .13, i * .08)); },
    level() { if (!ready()) return; [0, 2, 4, 6, 7].forEach((k, i) => tone(NOTE[k], .5, "triangle", .12, i * .09)); },
    click() { if (!ready()) return; tone(900, .05, "sine", .07); },
    tap() { if (!ready()) return null; if (!dst) { dst = ac.createMediaStreamDestination(); comp.connect(dst); } return dst.stream; },       // what you hear, as a stream, so a recorded clip can carry the sound
  };
})();
const tapped = () => !navigator.userActivation || navigator.userActivation.hasBeenActive;       // browsers allow sound and vibration only after you have tapped something
const buzz = p => { if (!state.mute && !reduced && navigator.vibrate && tapped()) { try { navigator.vibrate(p); } catch (e) {} } };
document.addEventListener("pointerdown", () => Snd.unlock(), { once: true }); document.addEventListener("keydown", () => Snd.unlock(), { once: true });

/* ---- the daily drop and the streak ---- */
const dayKey = d => (d || new Date()).toLocaleDateString("en-CA");                       // 2026-11-21, in the player's own time
const STREAK_BONUS = { 3: 1, 7: 1, 14: 2, 30: 3 };                                     // extra free packs on these streak days
const dailyReady = () => state.streak.last !== dayKey();
function claimDaily() {
  const st = state.streak; if (!dailyReady()) return null;
  const y = dayKey(new Date(Date.now() - 864e5)), y2 = dayKey(new Date(Date.now() - 2 * 864e5)); let used = false;
  if (st.last === y) st.n++; else if (st.last === y2 && st.freezes > 0) { st.freezes--; st.n++; used = true; } else st.n = 1;      // one missed day is forgiven if you have a freeze
  st.last = dayKey(); st.best = Math.max(st.best, st.n); if (st.n % 7 === 0) st.freezes = Math.min(2, st.freezes + 1);
  const bonus = STREAK_BONUS[st.n] || 0, packs = 1 + bonus; state.freePacks += packs; save(); renderChips(); Snd.claim(bonus > 0); buzz([30, 40, 30]);
  return { packs, bonus, n: st.n, used };
}
function dailyModal(res) {
  const st = state.streak, ready = dailyReady(), n = st.n, nextM = [3, 7, 14, 30].find(m => m > n), wk = n > 0 && n % 7 === 0 ? 7 : n % 7, have = state.freePacks;
  openModal(`<div class="minfo"><div><span class="label">Free daily pack</span><h2>${res ? "+" + res.packs + " free pack" + (res.packs > 1 ? "s" : "") : ready ? "Your free pack is ready" : "You've got today's pack"}</h2></div>
    ${res ? `<p class="dim">Day ${res.n} in a row.${res.bonus ? ` That is a streak bonus: ${res.bonus} extra.` : ""}${res.used ? " A streak freeze covered the day you missed." : ""} You have ${have} free pack${have === 1 ? "" : "s"} to open.</p>` : ready ? `<p class="dim">One free pack every day. Nothing to buy.</p>` : `<p class="dim">Come back tomorrow for the next one.${have ? ` You have ${have} free pack${have === 1 ? "" : "s"} to open now.` : ""}</p>`}
    <div><div class="label">Streak · day ${n}</div><div class="mono-meter" aria-hidden="true">${meter(wk, 7)}</div><p class="small" style="margin-top:6px">${nextM ? `Day ${nextM} adds ${STREAK_BONUS[nextM]} extra free pack${STREAK_BONUS[nextM] > 1 ? "s" : ""}. ` : ""}Miss a day and your streak survives if you have a freeze (you have ${st.freezes}). You earn one every 7 days, up to 2.</p></div>
    <div class="row">${ready ? `<button class="btn solid" id="claimDaily">claim your pack</button>` : have ? `<button class="btn solid" id="claimOpen">open a free pack</button>` : ""}<button class="btn ghost" data-close>${ready ? "not now" : "close"}</button></div></div>`, true);
}
function renderChips() {
  if (typeof renderBroke === "function") renderBroke();
  const d = $("dailyBtn"); if (d) { const ready = dailyReady(); d.className = "chip" + (ready ? " ready" : ""); d.innerHTML = ready ? `<i></i>free <span class="xs">daily </span>pack` : `streak ${state.streak.n}`; d.title = ready ? "A free pack, once a day" : "Your daily streak"; }
  const m = $("muteBtn"); if (m) { m.textContent = state.mute ? "sound off" : "sound on"; m.setAttribute("aria-pressed", state.mute ? "true" : "false"); }
}

/* ---- rank: earned by finding things and turning up, not by how much you spend or win ---- */
const RANKS = [["Tourist", 0], ["Paper hands", 60], ["Degen", 150], ["Flipper", 300], ["Diamond hands", 520], ["Whale", 800], ["Legend", 1200]];
const FX_ALL = CARDS.length * 13;
function noteFound() { for (const c of state.vault) { state.found[c.no] = 1; state.foundFx[c.no + "|" + (c.fx || "")] = 1; } }
const xpOf = () => { noteFound(); return state.s.packs * 4 + Object.keys(state.found).length * 40 + Object.keys(state.foundFx).length * 12 + state.streak.best * 10; };
const rankIdx = xp => { let i = 0; RANKS.forEach(([, x], k) => { if (xp >= x) i = k; }); return i; };
function rankHTML() {
  const xp = xpOf(), i = rankIdx(xp), cur = RANKS[i], nx = RANKS[i + 1];
  return `<div class="rank"><div><span class="label">rank</span><b>${cur[0]}</b></div><div class="mono-meter" aria-hidden="true">${meter(nx ? Math.round((xp - cur[1]) / (nx[1] - cur[1]) * 16) : 16, 16)}</div><div class="small">${xp} xp${nx ? ` · ${nx[1] - xp} to ${nx[0]}` : " · top rank"}. It comes from cards and styles you find, packs you open and your daily streak.</div></div>`;
}

/* ---- the collection has holes in it, and you can see them ---- */
const missingCards = set => { const have = new Set(state.vault.map(c => c.no)); return CARDS.filter(c => !have.has(c.no) && (!set || c.set === set)); };
const chaseChance = pk => { pk = pk || curPack(); const m = missingCards(pk.set); return m.length ? 1 - m.reduce((a, c) => a * (1 - packP(c.id)), 1) : 0; };      // a pack only holds cards of its own set
function chaseHTML() {
  if (!state.s.packs && !state.vault.length) return "";
  const pk = curPack(), size = CARDS.filter(c => c.set === pk.set).length, miss = missingCards(pk.set); if (!miss.length) return `<span class="label">${esc(pk.name)}</span><span>You have every ${esc(pk.name)} card. The styles are next: ${Object.keys(state.foundFx).length} of ${FX_ALL} found.</span>`;
  const rows = miss.slice().sort((a, b) => MK.price(b) - MK.price(a)).slice(0, 3), hot = miss.map(c => ({ c, p: MK.pct(c, 24) })).sort((a, b) => b.p - a.p)[0];
  return `<span class="label">still out there in ${esc(pk.name)} · ${size - miss.length} of ${size} found</span>` + rows.map(c => `<button class="mover mini" data-card="${c.no}"><span class="nm">${esc(c.name)}</span><span class="faint">${RAR[c.rar].name}</span>${money(MK.price(c))} ${pctHTML(MK.pct(c, 24))}<span class="dim">${chance(packP(c.id))}</span></button>`).join("")
    + (hot && hot.p >= .3 ? `<span class="hotflip"><b>${esc(hot.c.name)}</b> is up ${pctShort(hot.p).slice(1)} in a day and you don't have one. It turns up in ${chance(packP(hot.c.id), packOf(hot.c))}, and a pack costs ${money(packPrice(packOf(hot.c)))}.</span>` : "");
}

/* ---- keeping it healthy: a reminder every half hour, a limit on packs per day, a break nobody can talk you out of ---- */
const packsToday = () => { const m = new Date(); m.setHours(0, 0, 0, 0); return state.packLog.filter(t => t >= m.getTime()).length; };
function packGate() {
  const l = state.lim; if (l.breakUntil > Date.now()) return `You're on a break for another ${heldText(l.breakUntil - Date.now())}. You asked for it, and it can't be undone.`;
  if (l.packs && packsToday() >= l.packs) return `You set a limit of ${l.packs} packs a day and you've opened ${packsToday()}. It resets at midnight.`; return "";
}
const REMIND = 30 * 60000;                                                                             // a reminder every half hour
const ses0 = { packs: state.s.packs, spent: state.s.spent, sold: state.s.sold, net: netWorth() - state.s.added }; let activeMs = 0, remindedAt = 0;
function sessionTick() {
  if (document.hidden) return; activeMs += 1000;
  if (activeMs - remindedAt >= REMIND && !SS && $("modal").hidden && $("cut").hidden && $("share").hidden && $("gate").hidden) { remindedAt = activeMs; breakModal(); }
}
function breakModal() {
  const np = state.s.packs - ses0.packs, sp = state.s.spent - ses0.spent, back = state.s.sold - ses0.sold, d = (netWorth() - state.s.added) - ses0.net, rtp = Math.round(packStats().rtp * 100);
  openModal(`<div class="minfo"><div><span class="label">a pause</span><h2>You've been here ${activeMs >= 90000 ? Math.round(activeMs / 60000) + " minutes" : Math.round(activeMs / 1000) + " seconds"}</h2></div>
    <p class="dim">This session: ${np} pack${np === 1 ? "" : "s"} opened, ${money(sp)} spent on packs, ${money(back)} back from sales. Your net worth moved ${d >= 0 ? "+" : "−"}${money(Math.abs(d))}.</p>
    <p class="small">A pack returns about ${rtp}% on average when you sell, so the more you open, the more likely you are to end up behind. Stopping now is always fine.</p>
    <div class="row"><button class="btn" data-brk="1">take a 1 hour break</button><button class="btn ghost" data-close>keep going</button></div></div>`, true);
}
function limitsHTML() {
  const l = state.lim, onBreak = l.breakUntil > Date.now(), rtp = Math.round(packStats().rtp * 100);
  return `<h3 class="sec">Keep it fun</h3><p class="small" style="margin-bottom:12px">A pack returns about ${rtp}% on average when you sell, so over many packs most people end behind. These are yours to set, and you'll get a reminder every 30 minutes.</p>
    <div class="row" style="margin-bottom:10px"><label class="small" for="limPacks">Packs per day</label><select id="limPacks">${[0, 1, 3, 5, 10, 20].map(n => `<option value="${n}"${l.packs === n ? " selected" : ""}>${n || "no limit"}</option>`).join("")}</select><span class="small">${packsToday()} opened today</span></div>
    <div class="row"><span class="small">${onBreak ? `On a break for another ${heldText(l.breakUntil - Date.now())}.` : "Take a break"}</span>${onBreak ? "" : `<button class="btn small" data-brk="1">1 hour</button><button class="btn small" data-brk="24">24 hours</button>`}</div>`;
}
function startBreak(h) { state.lim.breakUntil = Math.max(state.lim.breakUntil, Date.now() + h * 36e5); persist(); closeModal(); toast(`Break started. Packs are off for ${h === 1 ? "an hour" : h + " hours"}.`); if (view === "profile") renderProfile(); }

/* ---- one second at a time ---- */
let rankSeen = null;
function habitTick() {
  sessionTick(); const i = rankIdx(xpOf()); if (rankSeen === null) { rankSeen = i; state.rank = i; }                  // the rank you arrive with is not news
  if (i > rankSeen) { rankSeen = i; state.rank = i; persist(); }                                                          // your rank still moves, quietly: nothing pops up
  if (!document.hidden && Math.floor(Date.now() / 1000) % 30 === 0) { state.lastSeen = Date.now(); persist(); renderChips(); }
}
