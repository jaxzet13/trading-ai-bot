// node test-acct.js : accounts on the real server (sign up, stay signed in, save, log in elsewhere, the tester flag)
const fs = require("fs"), os = require("os"), path = require("path"), http = require("http");
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "stixx-acct-")); process.env.DATA_FILE = path.join(dir, "d.json"); process.env.TESTER_EMAILS = "Dev@Example.com";
const { server } = require("./server.js"); let fails = 0; const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) fails++; };
const call = (port, p, body) => new Promise(res => { const d = body ? JSON.stringify(body) : ""; const r = http.request({ port, path: "/api/" + p, method: body ? "POST" : "GET", headers: { "content-type": "application/json", "content-length": Buffer.byteLength(d) } }, x => { let s = ""; x.on("data", c => s += c); x.on("end", () => { let j = null; try { j = JSON.parse(s); } catch (e) {} res({ status: x.statusCode, j }); }); }); r.on("error", () => res({ status: 0, j: null })); r.end(d); });
server.listen(0, async () => { const port = server.address().port, P = (p, b) => call(port, p, b);
  ok((await P("health")).j.accounts === true, "the server says accounts are on");
  ok((await P("signup", { email: "nope", pw: "secret1" })).status === 400 && (await P("signup", { email: "a@b.co", pw: "123" })).status === 400, "a bad email or a short password is refused");
  const uid = "ab".repeat(8), s1 = await P("signup", { email: " A@B.co ", pw: "secret1", uid });
  ok(s1.status === 200 && s1.j.token && s1.j.email === "a@b.co" && s1.j.uid === uid && s1.j.tester === false, "signing up takes an email and a password, keeps the player id, and signs you in");
  ok((await P("signup", { email: "a@b.co", pw: "other12" })).status === 409, "the same email cannot sign up twice");
  ok((await P("me", { token: s1.j.token })).j.email === "a@b.co" && (await P("me", { token: "x".repeat(64) })).status === 401, "the session is remembered; a made-up one is not");
  const game = JSON.stringify({ coins: 777, vault: [{ no: "001" }] });
  ok((await P("save", { token: s1.j.token, state: game })).j.ok && (await P("save", { token: "x".repeat(64), state: game })).status === 401 && (await P("save", { token: s1.j.token, state: "{}" })).status === 400, "the game is saved for the signed-in player only, and only if it is a game");
  ok((await P("login", { email: "a@b.co", pw: "wrong00" })).status === 401 && (await P("login", { email: "no@one.co", pw: "secret1" })).status === 401, "a wrong password or an unknown email is refused the same way");
  const l = await P("login", { email: "A@b.CO", pw: "secret1" });
  ok(l.status === 200 && l.j.save === game && l.j.uid === uid && l.j.token !== s1.j.token, "logging in on another device brings the saved game back");
  const s2 = await P("signup", { email: "c@d.co", pw: "secret2", uid }); ok(s2.status === 200 && s2.j.uid !== uid, "a second account on the same device gets its own player id");
  ok((await P("logout", { token: l.j.token })).j.ok && (await P("me", { token: l.j.token })).status === 401 && (await P("me", { token: s1.j.token })).status === 200, "logging out ends that device's session and no other");
  const t = await P("signup", { email: "dev@example.com", pw: "secret3" }); ok(t.j.tester === true && (await P("me", { token: t.j.token })).j.tester === true, "an email listed as a tester is one");
  await new Promise(r => setTimeout(r, 600));                                                 // the store is written a moment after a change
  const file = fs.existsSync(process.env.DATA_FILE) ? fs.readFileSync(process.env.DATA_FILE, "utf8") : ""; ok(file && !file.includes("secret1") && !file.includes(s1.j.token), "no password and no session token is written to disk as it is");
  console.log(fails ? fails + " failed" : "all passed"); server.close(); process.exit(fails ? 1 : 0); });
