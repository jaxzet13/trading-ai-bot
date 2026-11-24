/* ============================================================================
   8f. INVITES, FAIR PLAY AND THE SMALL PRINT.
   A friend who follows your link gets a free pack the moment they join, and you get one when they open it. Those rewards are counted by the beta server
   (the page cannot be trusted to count its own rewards), so without a server this page says so and gives nothing out. Everything the server learns about
   you is a random id, your invite code, the days you visited and a few counts. Nothing here asks for a name, an email or a payment.
   ========================================================================== */
const Ref = (() => {
  let info = null, busy = false, last = 0;
  const incoming = (() => {                                                // ?ref=CODE on the link a friend sent; picked up once, then the address bar is tidied
    try { const p = new URLSearchParams(location.search); if (!p.has("ref")) return ""; const r = (p.get("ref") || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16); p.delete("ref"); history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : "") + location.hash); return r; } catch (e) { return ""; }
  })();
  if (incoming && !state.ref.by && !state.s.packs) { state.ref.by = incoming; persist(); }
  const link = code => location.origin + location.pathname.replace(/index\.html$/, "") + "?ref=" + code;
  const text = "Free ASCII card packs. Open one on STIXX, play money only:";
  async function sync() {
    if (!API.on || busy || !state.ageOK) return; busy = true;
    try {
      const r = await API.post("hello", { uid: state.uid, ref: state.ref.by }); if (!r || !r.code) return; info = r; last = Date.now(); state.ref.code = r.code; state.ref.n = r.invited; Fair.adopt(r.fair);
      applyPaid(r.paid);
      if (r.credits > 0) { const c = await API.post("claim", { uid: state.uid }); if (c && c.packs > 0) { state.freePacks += c.packs; persist(); renderChips(); const r2 = await API.post("hello", { uid: state.uid, ref: state.ref.by }); if (r2 && r2.code) info = r2; if (view === "home") renderHome(); } }
      if (state.s.packs > 0 && !r.activated) activated();
    } finally { busy = false; if (view === "invite" && $("modal").hidden) renderInvite(); }
  }
  const activated = () => { if (!API.on || state.ref.act) return; API.post("active", { uid: state.uid }).then(r => { if (r && r.ok) { state.ref.act = 1; persist(); setTimeout(sync, 400); } }); };
  async function vanity(raw) {
    const code = String(raw).toUpperCase().replace(/[^A-Z0-9]/g, ""), msg = $("vanityMsg"); msg.className = "small bad";
    if (code.length < 3 || code.length > 16) { msg.textContent = "Use 3 to 16 letters or numbers."; return; }
    msg.className = "small"; msg.textContent = "Checking…"; const r = await API.post("vanity", { uid: state.uid, code });
    if (r && r.ok) { info = Object.assign(info || {}, r.info || {}, { code: r.code }); state.ref.code = r.code; persist(); renderInvite(); toast("Your link now ends in " + r.code); return; }
    msg.className = "small bad"; msg.textContent = (r && r.error) || "Couldn't reach the server. Try again in a moment.";
  }
  async function copy() {
    if (!info) return; const u = link(info.code);
    API.post("event", { uid: state.uid, name: "inviteCopy" }); try { await navigator.clipboard.writeText(u); toast("Link copied"); } catch (e) { const el = $("invLink"); if (el) { el.select(); try { document.execCommand("copy"); toast("Link copied"); } catch (e2) { toast("Press and hold the link to copy it"); } } }
  }
  async function share() {
    if (!info) return; const u = link(info.code);
    API.post("event", { uid: state.uid, name: "inviteShare" }); if (navigator.share) { try { await navigator.share({ title: "STIXX", text, url: u }); return; } catch (e) { if (e && e.name === "AbortError") return; } }
    copy();
  }
  return { sync, activated, vanity, copy, share, link, info: () => info, text, last: () => last, incoming };
})();

const BONUS_AT = [[5, 2], [10, 3], [25, 5]], MAX_FRIENDS = 30;
function inviteBarHTML() {
  const i = Ref.info(); return `<a class="invitelink" href="#/invite"><b>Invite a friend, get a free pack.</b> They get one too.</a>${i && i.invited ? ` <span class="faint">${i.invited} friend${i.invited > 1 ? "s" : ""} so far</span>` : ""}`;
}
function renderInvite() {
  $("iSub").textContent = "Give a free pack. Get a free pack.";
  const i = Ref.info();
  if (!API.on) { $("iBody").innerHTML = `<div class="inv"><p class="dim">Invites switch on when the beta goes live. Here is how they will work:</p><ol class="plain"><li>You get a link that ends in your own code.</li><li>A friend who opens it gets a free pack as soon as they join.</li><li>When they open it, you get a free pack too. Every 5 friends adds bonus packs.</li></ol><p class="small">This copy of STIXX isn't connected to the beta server, so it can't count invites or hand out rewards, and it won't pretend to.</p></div>`; return; }
  if (!i) { $("iBody").innerHTML = `<p class="small">Getting your link…</p>`; Ref.sync(); return; }
  const next = BONUS_AT.find(([n]) => n > i.invited), u = Ref.link(i.code), typed = document.activeElement && document.activeElement.id === "vanityIn" ? document.activeElement.value : "";
  $("iBody").innerHTML = `<div class="inv">
    <div class="invhero"><span class="label">your link</span><input id="invLink" class="linkbox" readonly value="${esc(u)}" aria-label="Your invite link" onfocus="this.select()">
      <div class="row"><button class="btn solid" id="copyLink">copy link</button><button class="btn" id="shareLink">share…</button></div>
      <p class="small">A friend gets a free pack the moment they join. You get one when they open it.</p></div>
    <div class="invstats"><div><span class="label">friends joined</span><b>${i.joined}</b></div><div><span class="label">opened a pack</span><b>${i.invited}</b></div><div><span class="label">free packs you've earned</span><b>${i.earned}</b></div><div><span class="label">waiting for you</span><b>${i.credits}</b></div></div>
    <div><span class="label">bonus packs</span>${next ? `<div class="mono-meter" aria-hidden="true">${meter(i.invited, next[0])}</div><p class="small" style="margin-top:6px">${i.invited} of ${next[0]} friends. At ${next[0]} you get ${next[1]} bonus packs on top.</p>` : `<p class="small">You've earned every bonus. Thank you.</p>`}</div>
    <form id="vanityForm" autocomplete="off"><span class="label">make the link yours</span>
      <div class="row"><input id="vanityIn" placeholder="${i.activated ? "YOURNAME" : "open a pack first"}" maxlength="16" spellcheck="false" value="${esc(typed)}" ${i.activated ? "" : "disabled"} style="text-transform:uppercase;min-width:0;flex:1"><button class="btn" type="submit" ${i.activated ? "" : "disabled"}>claim</button></div>
      <div class="small" id="vanityMsg">${i.activated ? "3 to 16 letters or numbers. One change a day. Creators: put your name here and share the link." : "You can pick your own code once you've opened your first pack."}</div></form>
    <p class="small">Rewards are free packs of play-money cards and have no cash value. One reward per friend, up to ${MAX_FRIENDS} friends, and we check for abuse, so invites from the same person or device don't count.</p></div>`;
}

/* ---- settings on the Me page ---- */
function settingsHTML() {
  return `<h3 class="sec">More</h3><div class="row" style="margin-bottom:14px"><button class="btn small" data-cut="intro">watch the intro</button><button class="btn small" id="fairBtn2">check your packs</button><button class="btn small" id="aboutBtn">fine print</button></div>
    <p class="small" style="margin-bottom:10px">Everything is saved in this browser. Clearing your browser data clears your cards.</p><p><button class="linkbtn" id="resetBtn">start over</button></p>`;
}

/* ---- fair play: the window where a pull can be checked ---- */
const short = h => h ? h.slice(0, 10) + "…" + h.slice(-6) : "";
function fairModal(keep) {
  const f = Fair.F(), srv = API.on && f.srv, cur = srv ? f.srv : f.local, mode = srv ? "server" : "device";
  const rows = f.log.slice().reverse().slice(0, 10).map(x => { const st = Fair.status(f, x), pk = PACK_BY[x.pack];
    return `<tr><td class="num">#${x.n}</td><td>${esc(pk ? pk.name : x.pack)}</td><td>${x.picks.map(id => esc(BY_ID[id].name)).join(", ")}</td><td class="r"><span class="fbadge ${st === true ? "ok" : st === false ? "bad" : ""}">${st === true ? "✓ checked" : st === false ? "✗ doesn't match" : x.mode === "local" ? "reveal to check" : "sealed"}</span></td></tr>`; }).join("");
  openModal(`<div class="minfo fair"><div><span class="label">fair play</span><h2>Check your packs</h2></div>
    <p class="dim">Every pack is drawn from numbers you can check. Before you open a pack, a secret seed is locked in by showing its hash. The cards come from that seed and a client seed you choose. When you reveal the seed, this page redoes every draw and checks it matches.</p>
    <p class="small">${srv ? "<b>Server mode.</b> The seed is held by the STIXX server and stays hidden until you reveal it, so it can't be changed after seeing your client seed." : "<b>Device mode.</b> The seed is kept on this device. That proves the cards followed the published odds, but not that nobody else could have chosen the seed. Server mode turns on with the live beta."}</p>
    <div class="kv"><div><span class="label">locked-in seed (SHA-256)</span><code>${short(cur.commit)}</code></div><div><span class="label">packs drawn with it</span><b>${cur.nonce}</b></div></div>
    <form id="csForm" class="row" autocomplete="off"><label class="small" for="csIn">Your client seed</label><input id="csIn" value="${esc(f.cs)}" maxlength="24" spellcheck="false" style="min-width:0;flex:1;max-width:220px"><button class="btn small" type="submit">set</button></form>
    <div class="row"><button class="btn" id="fairRotate">reveal the seed and start a new one</button></div>
    ${rows ? `<div class="tablewrap"><table class="oddsT fairT"><thead><tr><th>#</th><th>Pack</th><th>Cards</th><th class="r"></th></tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="small">Open a pack and it shows up here.</p>`}
    <details><summary>Check a draw by hand</summary><form id="vfForm" autocomplete="off" class="vf"><input id="vfSeed" placeholder="revealed server seed (hex)" spellcheck="false"><div class="row"><input id="vfCs" placeholder="client seed" spellcheck="false" value="${esc(f.cs)}" style="flex:1;min-width:0"><input id="vfN" placeholder="pack #" inputmode="numeric" style="width:84px"></div><div class="row"><select id="vfPk">${PACKS.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select><button class="btn small" type="submit">work it out</button></div><div class="small" id="vfOut"></div></form></details>
    <details><summary>How it works</summary><ul class="plain"><li>The digest for pack <b>n</b> is <b>HMAC-SHA256(server seed, "client seed:n")</b>, with the seed's hex text as the key.</li><li>Slot 1 uses the first 8 hex characters of the digest as a number from 0 to 1 and walks down the slot's odds on the odds page; slot 2 uses the next 8, and so on.</li><li>The locked-in value is <b>SHA-256(server seed)</b>. After you reveal a seed, its hash has to equal what you were shown before.</li><li>The style of a copy comes from its copy id, which is a public formula, not from the draw.</li></ul></details></div>`, true, keep);
}
function verifyHand() {
  const seed = $("vfSeed").value.trim().toLowerCase(), cs = $("vfCs").value.trim(), n = +$("vfN").value, pk = PACK_BY[$("vfPk").value], out = $("vfOut");
  if (!/^[0-9a-f]{16,128}$/.test(seed) || !cs || !(n >= 0) || $("vfN").value === "") { out.className = "small bad"; out.textContent = "Fill in the seed (hex), your client seed and the pack number."; return; }
  const hex = hmacHex(seed, `${cs}:${n}`); out.className = "small"; out.innerHTML = `Locked-in hash of this seed: <code>${short(sha256hex(seed))}</code><br>Digest: <code>${short(hex)}</code><br>Cards: <b>${Fair.cardsOf(pk, hex).map(c => esc(c.name)).join(", ")}</b>`;
}
async function rotateSeed() { const b = $("fairRotate"); if (b) b.disabled = true; await Fair.rotate(); fairModal(true); toast("Seed revealed. A new one is locked in."); }

/* ---- cash out: a notice, not a feature. Nothing in the beta can be paid out, and the window says so plainly. ---- */
function cashModal() {
  if (Shop.open()) { openModal(`<div class="minfo"><div><span class="label">cash out</span><h2>Not available</h2></div>
    <p class="dim">You can't cash out. Real money ${Shop.cash() ? "adds play money" : "buys packs"}, and nothing else. Your balance, your cards and every price in STIXX are part of the game and have no cash value.${Money.note(true)}</p>
    <div class="row"><button class="btn solid" data-close>ok</button></div></div>`, true); return; }
  openModal(`<div class="minfo"><div><span class="label">cash out</span><h2>Coming at public release</h2></div>
    <p class="dim">Cashing out will be available on public release. At public release, cards are bought with real money through Stripe.</p>
    <p class="small">Until then everything in the beta is play money. This balance and these cards can't be paid out, and nothing in the game is charged.${Money.note()}</p>
    <div class="row"><button class="btn solid" data-close>ok</button></div></div>`, true);
}

/* ---- the fine print ---- */
function aboutModal() {
  openModal(`<div class="minfo"><div><span class="label">the fine print</span><h2>STIXX beta</h2></div>
    <ul class="plain"><li>${Money.about()}</li><li><b>18+.</b> The cards contain explicit language and violence, and packs are a game of chance, so STIXX is for adults.</li><li><b>The market is simulated.</b> Prices come from AI trading bots, not real people. Every number is labelled as simulated where it is one.</li><li><b>What is stored.</b> Your cards and settings stay in this browser. If you use invites or fair-play seeds online, our server holds a random id, your invite code, the days you visited and a few counts. No name, email or payment details, ever.</li><li><b>It's a beta.</b> Things will change, and progress can be lost if you clear your browser data or we reset the beta.</li><li><b>Take it easy.</b> You can set a pack limit or take a break on the Me page at any time.</li></ul>
    <div class="row"><button class="btn solid" data-close>ok</button></div></div>`, true);
}
