/* ============================================================================
   3. COPY CODES. Every copy has an id: IS015-000003-A2JM = set + card number, serial, check.
      The style a copy comes out in is rolled from its code, so a printed card and its digital twin always match.
   ========================================================================== */
const B32 = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789", SALT = "stixx-s2-ink";
const fnv = str => { let h = 0x811c9dc5; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; } return h >>> 0; };
const codeCheck = pl => { let h = fnv(SALT + pl), out = ""; for (let i = 0; i < 4; i++) { out += B32[h % 32]; h = Math.floor(h / 32); } return out; };
const cardCode = (card, serial) => { const pl = `${SETS[card.set].code}${card.no}-${String(serial).padStart(6, "0")}`; return `${pl}-${codeCheck(pl)}`; };
function rollStyle(u) { let acc = 0; for (const k in STYLES) { acc += STYLES[k].p; if (u < acc) return k; } return ""; }
const styleOfCode = code => rollStyle(fnv("fx:" + code) / 4294967296);
const cuts = rar => "/".repeat(RAR[rar].cuts);
const idHTML = (code, rar) => `<span class="cid"><b>${esc(code)}</b>${cuts(rar) ? `<i>${cuts(rar)}</i>` : ""}</span>`;
const styleName = fx => fx ? STYLES[fx].name : "Plain";
const ART = 6;                                                                              // bump when card pictures are redrawn: the address changes, so no phone keeps showing an old picture from its cache
const imgOf = (card, fx, small) => `cards/${small ? "s/" : ""}${card.id}${fx ? "-" + fx : card.id === "stitch" ? "-bone" : ""}.jpg?v=${ART}`;   // the plain look is cards/<id>.jpg; a styled copy is cards/<id>-<style>.jpg
