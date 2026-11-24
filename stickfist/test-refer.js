// server-level check of invites: late attach, instant credit for an already-active friend, no self/mutual codes, the shared-network cap
const { spawn } = require('child_process'); const http = require('http'); const crypto = require('crypto'); const fs = require('fs'); const os = require('os'); const path = require('path');
const PORT = 8877, DATA = path.join(os.tmpdir(), 'stixx-reftest-' + Date.now() + '.json'); let fails = 0;
const ok = (c, m) => { console.log((c ? 'ok   ' : 'FAIL ') + m); if (!c) fails++; };
const call = (p, body, ip) => new Promise((res, rej) => { const d = JSON.stringify(body); const r = http.request({ port: PORT, method: 'POST', path: '/api/' + p, headers: { 'content-type': 'application/json', 'content-length': Buffer.byteLength(d), 'x-forwarded-for': ip || '1.1.1.1' } }, x => { let o = ''; x.on('data', c => o += c); x.on('end', () => { try { res(JSON.parse(o)); } catch (e) { res({}); } }); }); r.on('error', rej); r.end(d); });
const id = () => crypto.randomBytes(8).toString('hex');
(async () => {
  const srv = spawn('node', [path.join(__dirname, 'server.js')], { env: Object.assign({}, process.env, { PORT, DATA_FILE: DATA, TRUST_PROXY: '1' }), stdio: 'ignore' }); await new Promise(r => setTimeout(r, 900));
  try {
    const A = id(), B = id(), C = id(); const a = await call('hello', { uid: A }, '10.0.0.1');
    // B already has the app and has opened a pack, THEN gets A's link
    await call('hello', { uid: B }, '10.0.0.2'); await call('active', { uid: B }, '10.0.0.2');
    let b = await call('hello', { uid: B, ref: a.code }, '10.0.0.2'); ok(b.by === a.code && b.credits === 1, 'someone who already had the app can still join on a friend\'s code, and gets their pack');
    let a2 = await call('hello', { uid: A }, '10.0.0.1'); ok(a2.joined === 1 && a2.invited === 1 && a2.credits === 1, 'they had already opened a pack, so the inviter\'s pack is credited at once (' + JSON.stringify({ j: a2.joined, i: a2.invited, c: a2.credits }) + ')');
    b = await call('hello', { uid: B, ref: 'ZZZZZZ' }, '10.0.0.2'); ok(b.by === a.code, 'a second code changes nothing');
    a2 = await call('hello', { uid: A, ref: a.code }, '10.0.0.1'); ok(!a2.by, 'your own code does nothing');
    a2 = await call('hello', { uid: A, ref: b.code }, '10.0.0.1'); ok(!a2.by, 'and codes can\'t be traded back (the person you invited can\'t invite you)');
    // C is new, joins by link, opens later
    let c = await call('hello', { uid: C, ref: a.code }, '10.0.0.3'); ok(c.by === a.code && c.credits === 1, 'a brand-new friend still gets their pack on joining');
    a2 = await call('hello', { uid: A }, '10.0.0.1'); ok(a2.invited === 1, 'the inviter is not paid until that friend opens a pack'); await call('active', { uid: C }, '10.0.0.3'); a2 = await call('hello', { uid: A }, '10.0.0.1'); ok(a2.invited === 2 && a2.credits === 2, 'then they are');
    // seven friends on the inviter's own network: five count
    const H = id(); const h = await call('hello', { uid: H }, '10.9.9.9'); for (let i = 0; i < 7; i++) { const f = id(); await call('hello', { uid: f, ref: h.code }, '10.9.9.9'); await call('active', { uid: f }, '10.9.9.9'); }
    const h2 = await call('hello', { uid: H }, '10.9.9.9'); ok(h2.joined === 7 && h2.invited === 5, 'on the inviter\'s own network five friends count, not unlimited (' + h2.invited + ' of 7)');
    const cl = await call('claim', { uid: A }, '10.0.0.1'); ok(cl.packs === 2 && cl.friends === 2, 'claiming hands the inviter their two packs');
  } finally { srv.kill(); try { fs.unlinkSync(DATA); } catch (e) {} }
  console.log(fails ? fails + ' FAILED' : 'all passed'); process.exit(fails ? 1 : 0);
})();
