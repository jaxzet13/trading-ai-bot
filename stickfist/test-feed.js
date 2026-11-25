// node test-feed.js : the live feed on the real server (a hit is re-drawn and checked here, listed once, and named without giving the name away)
const fs = require("fs"), os = require("os"), path = require("path"), http = require("http");
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "stixx-feed-")); process.env.DATA_FILE = path.join(dir, "d.json");
const { server } = require("./server.js"); let fails = 0; const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) fails++; };
const call = (port, p, body) => new Promise(res => { const d = body ? JSON.stringify(body) : ""; const r = http.request({ port, path: "/api/" + p, method: body ? "POST" : "GET", headers: { "content-type": "application/json", "content-length": Buffer.byteLength(d) } }, x => { let s = ""; x.on("data", c => s += c); x.on("end", () => { let j = null; try { j = JSON.parse(s); } catch (e) {} res({ status: x.statusCode, j }); }); }); r.end(d); });
// the game's own tables, read the way the server reads them, so the test can work out what every draw holds
const G = new Function(fs.readFileSync(path.join(__dirname, "src", "js", "01-data.js"), "utf8") + "; return { RAR, CARDS, PACKS };")();
const pickU = (list, u) => { let t = 0; for (const [, w] of list) t += w; let r = u * t; for (const [id, w] of list) { if ((r -= w) < 0) return id; } return list[list.length - 1][0]; };
const cardOf = (pack, digest, i) => { const pk = G.PACKS.find(p => p.id === pack), id = pickU(pk.slots[0], parseInt(digest.slice(i * 8, i * 8 + 8), 16) / 4294967296); return G.CARDS.find(c => c.id === id); };
const isHit = c => G.RAR[c.rar].tier >= 4;
server.listen(0, async () => { const port = server.address().port, P = (p, b) => call(port, p, b);
  const f0 = (await P("feed")).j; ok(f0 && f0.on === true && Array.isArray(f0.feed) && f0.feed.length === 0 && f0.day === 0, "the feed starts empty, and the server has the game's tables");
  // a player with an account, and one without
  const uid = "ab".repeat(8), anon = "cd".repeat(8); await P("signup", { email: "Jordan.Smith@example.com", pw: "secret1", uid }); await P("hello", { uid }); await P("hello", { uid: anon });
  // 100 packs, several at a time, exactly as the page asks for them
  const draws = []; for (let k = 0; k < 4; k++) { const r = (await P("fair/draws", { uid, cs: "TEST", n: 25 })).j; draws.push(...r.draws); }
  const mine = draws.map(d => ({ d, card: cardOf("fp", d.digest, 0) })), want = mine.filter(x => isHit(x.card));
  ok(draws.length === 100 && want.length >= 1, `100 packs drawn; by the published tables ${want.length} of them hold a legendary or better`);
  let said = 0, lied = 0; for (const x of mine) { const r = (await P("fair/hit", { uid, n: x.d.nonce, of: 0, k: 0, pack: "fp" })).j; if (r.hit) said++; if (r.hit !== isHit(x.card)) lied++; }
  ok(said === want.length && lied === 0, "reporting every one of them: the server lists exactly the real hits and none of the rest (" + said + ")");
  const f1 = (await P("feed")).j; ok(f1.feed.length === Math.min(40, want.length) && f1.day === want.length && f1.feed[0].id === want[want.length - 1].card.id, "the feed holds them, newest first");
  ok(Object.entries(f1.found).every(([id, n]) => want.filter(x => x.card.id === id).length === n) && Object.values(f1.found).reduce((a, b) => a + b, 0) === want.length, "and counts how many of each card have ever been found");
  ok(f1.feed.every(e => e.who === "jo•••") && !JSON.stringify(f1).includes("jordan") && !JSON.stringify(f1).includes("example.com") && !JSON.stringify(f1).includes(uid), "a player is named by two letters and dots: no email, no id");
  ok((await P("fair/hit", { uid, n: want[0].d.nonce, of: 0, k: 0, pack: "fp" })).j.ok === false && (await P("feed")).j.day === want.length, "the same draw cannot be reported twice");
  ok((await P("fair/hit", { uid, n: 99999, of: 0, k: 0, pack: "fp" })).j.ok === false && (await P("fair/hit", { uid: anon, n: want[0].d.nonce, of: 0, k: 0, pack: "fp" })).j.ok === false, "a draw the server never gave that player is refused");
  // a single pack: one draw read as five cards, and the player says which one they took
  let one = null, pos = -1; for (let k = 0; k < 400 && pos < 0; k++) { const r = (await P("fair/draw", { uid: anon, cs: "SOLO" })).j; for (let i = 0; i < 5; i++) if (isHit(cardOf("ms", r.digest, i))) { one = r; pos = i; break; } }
  const r5 = (await P("fair/hit", { uid: anon, n: one.nonce, of: 5, k: pos, pack: "ms" })).j, f2 = (await P("feed")).j;
  ok(r5.hit === true && f2.feed[0].id === cardOf("ms", one.digest, pos).id && f2.feed[0].pack === "ms" && /^player cdcd$/.test(f2.feed[0].who), "a pick of five is checked at the position taken; a player without an account is 'player' and four characters of an id");
  // a new seed: old draws can no longer be claimed
  const d2 = (await P("fair/draw", { uid, cs: "TEST" })).j; await P("fair/rotate", { uid }); ok((await P("fair/hit", { uid, n: d2.nonce, of: 0, k: 0, pack: "fp" })).j.ok === false, "after the seed is rotated, a draw from the old seed is not accepted");
  console.log(fails ? fails + " failed" : "all passed"); server.close(); process.exit(fails ? 1 : 0);
});
