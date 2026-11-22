/* ============================================================================
   2. UTILITIES
   ========================================================================== */
const $ = id => document.getElementById(id);
const money = c => (c < 0 ? "-$" : "$") + (Math.abs(c) / UNIT).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
// real money (the Requiem pack and buying packs) is in real cents, never in game units
const rmoney = c => (c < 0 ? "-$" : "$") + (Math.abs(c) / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
// money for things that move: a 10 cent card needs four decimals for you to see it breathe
const moneyS = c => { const a = Math.abs(c) / UNIT, d = a >= 1 ? 2 : a >= .1 ? 3 : 4; return (c < 0 ? "-$" : "$") + a.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); };
// update a container in place instead of rebuilding it, so buttons you are pressing, scroll positions and pictures are never disturbed
function patchKids(a, b) {
  const an = a.childNodes, bn = b.childNodes;
  for (let i = 0; i < bn.length; i++) {
    const x = an[i], y = bn[i]; if (!x) { a.appendChild(y.cloneNode(true)); continue; }
    if (x.nodeType !== y.nodeType || x.nodeName !== y.nodeName) { a.replaceChild(y.cloneNode(true), x); continue; }
    if (x.nodeType === 3) { if (x.nodeValue !== y.nodeValue) x.nodeValue = y.nodeValue; continue; }
    if (x.nodeType !== 1) continue;
    for (const at of [...x.attributes]) if (!y.hasAttribute(at.name)) x.removeAttribute(at.name);
    for (const at of y.attributes) if (x.getAttribute(at.name) !== at.value) x.setAttribute(at.name, at.value);
    patchKids(x, y);
  }
  while (an.length > bn.length) a.removeChild(a.lastChild);
}
Object.defineProperty(HTMLElement.prototype, "live", { set(html) { put(this, html); } });
function put(el, html) { if (!el.firstChild) { el.innerHTML = html; return; } const t = document.createElement(el.tagName === "TABLE" ? "table" : el.tagName === "TBODY" ? "tbody" : "div"); t.innerHTML = html; patchKids(el, t); }
const fmt = n => Math.round(n).toLocaleString("en-US");
const esc = s => String(s).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
function rand() { try { return crypto.getRandomValues(new Uint32Array(1))[0] / 4294967296; } catch (e) { return Math.random(); } }
const rid = n => { try { return Array.from(crypto.getRandomValues(new Uint8Array(n)), b => b.toString(16).padStart(2, "0")).join(""); } catch (e) { let s = ""; for (let i = 0; i < n; i++) s += Math.floor(Math.random() * 256).toString(16).padStart(2, "0"); return s; } };
const pickU = (list, u) => { let t = 0; for (const [, w] of list) t += w; let r = u * t; for (const [id, w] of list) { if ((r -= w) < 0) return id; } return list[list.length - 1][0]; };   // the same weighted pick, from a number in [0,1) instead of a fresh random one
const pick = list => { let t = 0; for (const [, w] of list) t += w; let r = rand() * t; for (const [id, w] of list) { if ((r -= w) < 0) return id; } return list[0][0]; };
const loadImg = src => new Promise(res => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
let toastT; function toast(msg) { const old = document.querySelector(".toast"); if (old) old.remove(); const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; document.body.appendChild(t); clearTimeout(toastT); toastT = setTimeout(() => t.remove(), 2400); }
