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
  // ---- flips ----
  const fnv = str => { let h = 0x811c9dc5; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; } return h >>> 0; };
  const G2 = new Function(fs.readFileSync(path.join(__dirname, "src", "js", "01-data.js"), "utf8") + "; return { RAR, STYLES, BY_NO, BY_ID };")(), V = new Function("BY_NO", "STYLES", "RAR", "fnv", fs.readFileSync(path.join(__dirname, "src", "js", "04d-value.js"), "utf8") + "; return Val;")(G2.BY_NO, G2.STYLES, G2.RAR, fnv);
  const mkCopy = (id, i, ageS) => ({ no: G2.BY_ID[id].no, code: "IS0" + G2.BY_ID[id].no.slice(-2) + "-" + String(100000 + i) + "-TEST", uid: "copy" + i, serial: i + 1, fx: "", t: Date.now() - ageS * 1000 });
  const sellAt = c => Math.floor(V.at(c, Date.now()) * .9);
  // look through copies pulled a few minutes ago for one that has really run, and one that has not
  let up = null, flat = null; for (let i = 0; i < 6000 && !(up && flat); i++) { const c = mkCopy("grimm", i, 200 + (i % 7) * 40), s = sellAt(c), st0 = V.startOf(c); if (!up && s >= st0 * 1.8 && Math.abs(V.at(c, Date.now() - 6000) / V.at(c, Date.now()) - 1) < .05) up = c; if (!flat && s < st0 * 1.1 && s > st0 * .5) flat = c; }
  ok(up && flat, "found a copy whose price has run (by the game's own price engine) and one whose price has not");
  const gotUp = sellAt(up), r1 = (await P("flip", { uid, c: up, got: gotUp })).j, f3 = (await P("feed")).j;
  ok(r1.listed === true && f3.flips.length === 1 && f3.flips[0].id === "grimm" && f3.flips[0].from === Math.round(V.startOf(up)) && Math.abs(f3.flips[0].to - gotUp) <= 1 && f3.flips[0].who === "jo•••" && !JSON.stringify(f3.flips).includes(up.code), "a real flip is listed with what it came out at, what it sold for, and a masked name (" + (gotUp / V.startOf(up)).toFixed(1) + "x)");
  ok((await P("flip", { uid, c: up, got: gotUp })).j.ok === false && (await P("feed")).j.flips.length === 1, "the same copy is listed once");
  ok((await P("flip", { uid, c: flat, got: sellAt(flat) })).j.listed === false, "a sale that is not much of a gain is not a flip");
  const lie = mkCopy("grimm", 9001, 300); ok((await P("flip", { uid, c: lie, got: Math.floor(V.startOf(lie) * 40) })).j.listed === false && (await P("feed")).j.flips.length === 1, "a sale claimed for far more than the copy was worth is not listed");
  ok((await P("flip", { uid, c: Object.assign({}, up, { no: "999", code: "IS099-000001-TEST" }), got: 99999 })).j.ok === false && (await P("flip", { uid: "ee".repeat(8), c: up, got: gotUp })).status === 404, "an unknown card, or a player the server has never seen, is refused");
  console.log(fails ? fails + " failed" : "all passed"); server.close(); process.exit(fails ? 1 : 0);
});
