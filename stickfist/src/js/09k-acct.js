/* ============================================================================
   8k. ACCOUNTS. An email and a password, asked for once on the first screen. After that this device stays signed in, and the
   game is saved to the server as you play, so logging in on another phone brings your cards with you.
   Accounts exist only where the server has them (it says so on /api/health). With no server, or a server without accounts,
   the first screen is just the 18+ tick box, as before, and the game is kept in this browser.
   A tester account (the server decides which) gets a button that adds play money, for trying things out.
   ========================================================================== */
const Acct = (() => {
  let accounts = API.on, checking = API.on, mode = "signup", busy = false, pushT = 0, lastPush = "";   // checking: the server has not yet said whether it has accounts, so the button waits (a moment) rather than guess
  const me = () => state.acct || null, need = () => accounts && !me();
  const say = m => { const e = $("acErr"); if (!e) return; e.hidden = !m; e.textContent = m || ""; };
  // the first screen in its three shapes: no accounts (a tick box), sign up (email, password, tick box), log in (email, password)
  function paint() {
    const f = $("gateForm"), sw = $("acSwitch"), chk = document.querySelector("#gate .gcheck"), go = $("gateGo"), fine = $("gNoCard"), ttl = $("gateSub"); if (!f || !go) return;
    const login = accounts && mode === "login"; f.hidden = !accounts; sw.hidden = !accounts; chk.hidden = login; $("gate").dataset.mode = accounts ? mode : "plain";
    if (fine) fine.textContent = accounts ? "A free account, no card, nothing to download" : "No sign-up, no card, nothing to download";
    if (ttl && accounts && state.ageOK && !login) ttl.textContent = "Make a free account to keep your cards: it takes ten seconds and you only do it once.";
    $("acPw").autocomplete = login ? "current-password" : "new-password"; $("acPw").placeholder = login ? "Password" : "Password (6 or more characters)";
    sw.textContent = login ? "New here? Make an account" : "I already have an account"; if (state.ageOK && $("ageOK")) $("ageOK").checked = true;
    go.textContent = busy ? "one moment…" : login ? "log in" : accounts ? "create account · get my free pack" : "get my free pack"; go.disabled = busy || checking || (!login && !$("ageOK").checked);
  }
  const flip = () => { mode = mode === "login" ? "signup" : "login"; say(""); paint(); const e = $("acEmail"); if (e && !e.value) e.focus(); };
  function done() { $("gate").hidden = true; renderChips(); if (typeof Ref !== "undefined") Ref.sync(); if (view === "profile") renderProfile(); }
  async function go() {
    if (!accounts) { state.ageOK = true; save(); done(); return; }
    if (busy) return; const email = $("acEmail").value.trim(), pw = $("acPw").value;
    if (!/^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$/.test(email)) { say("Type your email address."); $("acEmail").focus(); return; }
    if (pw.length < 6) { say(mode === "login" ? "Type your password." : "Pick a password with 6 or more characters."); $("acPw").focus(); return; }
    busy = true; say(""); paint(); const r = await API.raw(mode, { email, pw, uid: state.uid }); busy = false; paint();
    if (!r.status) { say("Can't reach the server. Check your connection and try again."); return; }
    if (r.status === 409) { mode = "login"; paint(); say("That email already has an account. Log in with its password."); return; }
    if (r.status === 401) { say("Wrong email or password."); return; }
    if (r.status === 429) { say("Too many tries. Wait a few minutes."); return; }
    if (r.status !== 200 || !r.data || !r.data.token) { say("That didn't work. Try again."); return; }
    const acct = { email: r.data.email, token: r.data.token, tester: !!r.data.tester };
    if (mode === "login" && r.data.save) {                                                // your saved game replaces whatever this device had (in memory too, so nothing writes the old one back on the way out)
      try { const s = JSON.parse(r.data.save); if (s && typeof s.coins === "number") { s.acct = acct; s.ageOK = true; s.uid = r.data.uid || s.uid; onPersist = null; state = Object.assign(fresh(), s, { s: Object.assign(fresh().s, s.s || {}) }); state = purgeGone(state); lastPush = body(); persist(); location.reload(); return; } } catch (e) {}
    }
    state.acct = acct; state.ageOK = true; if (r.data.uid) state.uid = r.data.uid; save(); done(); push(); toast(mode === "login" ? "Welcome back" : "Account made. You're signed in on this device.");
  }
  // the game goes to the server a few seconds after it changes, and when the page is put away
  function body() { const c = Object.assign({}, state); delete c.acct; return JSON.stringify(c); }
  async function push(leaving) {
    const a = me(); if (!a || !API.on) return; const b = body(); if (b === lastPush) return; lastPush = b;
    const r = await API.raw("save", { token: a.token, state: b }, leaving); if (r.status === 401) signedOut(); else if (r.status !== 200) lastPush = "";
  }
  const dirty = () => { if (!me() || pushT) return; pushT = setTimeout(() => { pushT = 0; push(); }, 4000); };          // at most 4 seconds behind, however often the game is saved
  function signedOut() { state.acct = null; persist(); mode = "login"; paint(); $("gate").hidden = false; say("You were signed out. Log in to carry on."); }
  async function logout() {
    const a = me(); if (!a) return; clearTimeout(pushT); pushT = 0; await push(); await API.raw("logout", { token: a.token });
    onPersist = null; state = fresh(); persist(); location.hash = "#/"; location.reload();          // the game is on the server; this device forgets it
  }
  function testMoney(d) { if (!me() || !me().tester) return; state.coins += d * UNIT; state.s.added = (state.s.added || 0) + d * UNIT; save(); renderBal(); if (view === "profile") renderProfile(); if (view === "home") renderHome(); toast(`+${money(d * UNIT)} test money`); buzz(20); }
  // more test-account tools (the server decides who is a tester; nobody else sees the buttons or can use them)
  const ADM = [["restart", "Restart as a new player", 1], ["packs1", "+1 free pack"], ["packs10", "+10 free packs"], ["allcards", "Add every card"], ["rare", "Add a random rare card"], ["sellall", "Sell all my cards", 1], ["cash10", "Set money to $10", 1], ["clearfavs", "Clear favourites"], ["clearhist", "Clear profit history", 1], ["intro", "Replay the intro"], ["daily", "Reset the daily pack"], ["reload", "Reload the app"]];
  function testAdmin(k) {
    const a = me(); if (!a || !a.tester) return; const d = ADM.find(x => x[0] === k); if (!d) return;
    if (d[2] && !confirm(d[1] + "?")) return; const done = m => { save(); renderBal(); if (view === "profile") renderProfile(); if (view === "home") renderHome(); if (view === "collection") renderCollection(); toast(m); buzz(20); };
    if (k === "restart") { startOver(); state.seenIntro = false; state.pack = "fp"; persist(); location.hash = "#/"; location.reload(); return; }
    if (k === "packs1" || k === "packs10") { state.freePacks += k === "packs1" ? 1 : 10; return done("Free packs: " + state.freePacks); }
    if (k === "allcards" || k === "rare") {
      const have = new Set(state.vault.map(c => c.no)), rares = LIVE.filter(c => RAR[c.rar].tier >= 3), list = k === "allcards" ? LIVE.filter(c => !have.has(c.no)) : [rares[Math.floor(rand() * rares.length)]].filter(Boolean); let v = 0;
      for (const c of list) { const m = mint(c); state.vault.push(m); v += valueOf(m); } state.s.added = (state.s.added || 0) + v;
      return done(list.length ? "Added " + list.length + " card" + (list.length > 1 ? "s" : "") : "You have them all");
    }
    if (k === "sellall") { const g = sell(state.vault.map(c => c.uid)); return done("Sold everything for " + money(g)); }
    if (k === "cash10") { state.coins = START; return done("Money set to " + money(START)); }
    if (k === "clearfavs") { state.favs = []; return done("Favourites cleared"); }
    if (k === "clearhist") { state.hist = []; state.opens = []; return done("History cleared"); }
    if (k === "intro") { state.seenIntro = false; persist(); location.reload(); return; }
    if (k === "daily") { state.rescueAt = 0; state.freePacks = Math.max(state.freePacks, 1); return done("Daily pack reset"); }
    if (k === "reload") location.reload();
  }
  // the Me page: who is signed in, and for a tester the money buttons
  function html() {
    const a = me(); if (!a) return "";
    return `<div class="acctbox"><div class="ac-who"><span class="label">Signed in</span><b>${esc(a.email)}</b><small>Your cards are saved to your account.</small></div><button class="btn small ghost" id="acLogout">log out</button></div>` +
      (a.tester ? `<div class="acctbox test"><div class="ac-who"><span class="label">Test account</span><b>Add play money</b><small>Only this account sees these.</small></div><div class="ac-money">${[10, 100, 1000].map(d => `<button class="btn small" data-testmoney="${d}">+$${fmt(d)}</button>`).join("")}</div></div><div class="acctbox test admin"><div class="ac-who"><span class="label">Admin tools</span><small>Only test accounts see these.</small></div><div class="ac-admin">${ADM.map(x => `<button class="btn small${x[2] ? " warn" : ""}" data-testadm="${x[0]}">${x[1]}</button>`).join("")}</div></div>` : "");
  }
  async function start() {
    paint(); onPersist = dirty; if (!state.ageOK || (API.on && me() === null && !state.ageOK)) $("gate").hidden = false;
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") push(true); });
    const f = $("gateForm"); if (f) f.addEventListener("submit", e => { e.preventDefault(); go(); });
    if (!API.on) return;
    const h = await API.raw("health"); checking = false; if (h.status && !(h.data && h.data.accounts)) { accounts = false; paint(); return; } paint();   // a server without accounts: the plain first screen
    if (!h.status && state.ageOK && !me()) return;                                           // can't tell yet (the server is waking up): don't lock out someone already playing
    if (need()) { paint(); $("gate").hidden = false; return; }
    const a = me(); if (a) { const r = await API.raw("me", { token: a.token }); if (r.status === 401) signedOut(); else if (r.status === 200 && r.data && !!r.data.tester !== !!a.tester) { a.tester = !!r.data.tester; persist(); if (view === "profile") renderProfile(); } }
  }
  return { start, go, flip, paint, logout, testMoney, testAdmin, html, me, on: () => accounts };
})();
