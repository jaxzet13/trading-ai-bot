/* ============================================================================
   3. COPY CODES. Every copy has an id: IS015-000003-A2JM = set + card number, serial, check.
      The style a copy comes out in is rolled from its code, so a printed card and its digital twin always match.
   ========================================================================== */
const B32 = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789", SALT = "stixx-s2-ink";
const fnv = str => { let h = 0x811c9dc5; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; } return h >>> 0; };
const codeCheck = pl => { let h = fnv(SALT + pl), out = ""; for (let i = 0; i < 4; i++) { out += B32[h % 32]; h = Math.floor(h / 32); } return out; };
const cardCode = (card, serial) => { const pl = `IS${card.no}-${String(serial).padStart(6, "0")}`; return `${pl}-${codeCheck(pl)}`; };
function parseCode(raw) {
  const m = /^IS(\d{3})-(\d{6})-([A-Z0-9]{4})$/.exec(String(raw).trim().toUpperCase()); if (!m) return null;
  const card = BY_NO[m[1]]; if (!card || codeCheck(`IS${m[1]}-${m[2]}`) !== m[3]) return null;
  return { card, serial: +m[2], code: `IS${m[1]}-${m[2]}-${m[3]}` };
}
function rollStyle(u) { let acc = 0; for (const k in STYLES) { acc += STYLES[k].p; if (u < acc) return k; } return ""; }
const styleOfCode = code => rollStyle(fnv("fx:" + code) / 4294967296);
const cuts = rar => "/".repeat(RAR[rar].cuts);
const idHTML = (code, rar) => `<span class="cid"><b>${esc(code)}</b>${cuts(rar) ? `<i>${cuts(rar)}</i>` : ""}</span>`;
const styleName = fx => fx ? STYLES[fx].name : "Bone";
const imgOf = (card, fx) => `cards/${card.styles ? "stitch-" + (fx || "bone") : card.id}.jpg`;
