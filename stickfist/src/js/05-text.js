/* ============================================================================
   5. TEXT EFFECTS. The only things that move on this site are made of characters.
   ========================================================================== */
const RAMP = " .:-=+*#%@", R70 = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$";
const BANNER = [
  "███████╗████████╗██╗██╗  ██╗██╗  ██╗",
  "██╔════╝╚══██╔══╝██║╚██╗██╔╝╚██╗██╔╝",
  "███████╗   ██║   ██║ ╚███╔╝  ╚███╔╝ ",
  "╚════██║   ██║   ██║ ██╔██╗  ██╔██╗ ",
  "███████║   ██║   ██║██╔╝ ██╗██╔╝ ██╗",
  "╚══════╝   ╚═╝   ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝"
];
const fill = (ch, n) => ch.repeat(n);
const NOISE = "01#%&@$*+=-:.";
const bar = (p, w) => { const n = Math.round(clamp(p, 0, 1) * w); return fill("█", n) + fill("░", w - n); };
const chance = p => p >= .5 ? Math.round(p * 100) + "% of packs" : "1 in " + fmt(1 / p) + " packs";

// a name that settles: letters scramble, then lock in left to right
const GL = "!<>-_\\/[]{}=+*^?#abcdefghijklmnopqrstuvwxyz0123456789";
function scramble(el, to, ms) {
  if (reduced) { el.textContent = to; return; }
  const n = to.length, t0 = performance.now(); ms = ms || 380; cancelAnimationFrame(el._sc);
  (function step(now) {
    const k = clamp((now - t0) / ms, 0, 1); let out = "";
    for (let i = 0; i < n; i++) out += k * 1.4 - i / n > .1 || to[i] === " " ? to[i] : GL[Math.floor(Math.random() * GL.length)];
    el.textContent = out; if (k < 1) el._sc = requestAnimationFrame(step); else el.textContent = to;
  })(t0);
}
function countTo(el, from, to, fn, ms) {
  if (reduced || from === to) { el.textContent = fn(to); return; } const t0 = performance.now(); ms = ms || 450;
  (function s(now) { const k = clamp((now - t0) / ms, 0, 1); el.textContent = fn(Math.round(from + (to - from) * (1 - Math.pow(1 - k, 3)))); if (k < 1) requestAnimationFrame(s); })(t0);
}

// ASCII lettering: a 5x5 block font for titles, names and big numbers. Lit cells are full blocks.
const GLYPH = {
  A: [" ### ", "#   #", "#####", "#   #", "#   #"], B: ["#### ", "#   #", "#### ", "#   #", "#### "], C: [" ####", "#    ", "#    ", "#    ", " ####"],
  D: ["#### ", "#   #", "#   #", "#   #", "#### "], E: ["#####", "#    ", "#### ", "#    ", "#####"], F: ["#####", "#    ", "#### ", "#    ", "#    "],
  G: [" ####", "#    ", "# ###", "#   #", " ####"], H: ["#   #", "#   #", "#####", "#   #", "#   #"], I: ["#####", "  #  ", "  #  ", "  #  ", "#####"],
  K: ["#   #", "#  # ", "###  ", "#  # ", "#   #"], L: ["#    ", "#    ", "#    ", "#    ", "#####"], M: ["#   #", "## ##", "# # #", "#   #", "#   #"],
  N: ["#   #", "##  #", "# # #", "#  ##", "#   #"], O: [" ### ", "#   #", "#   #", "#   #", " ### "], P: ["#### ", "#   #", "#### ", "#    ", "#    "],
  R: ["#### ", "#   #", "#### ", "#  # ", "#   #"], S: [" ####", "#    ", " ### ", "    #", "#### "], T: ["#####", "  #  ", "  #  ", "  #  ", "  #  "],
  U: ["#   #", "#   #", "#   #", "#   #", " ### "],
  V: ["#   #", "#   #", "#   #", " # # ", "  #  "], W: ["#   #", "#   #", "# # #", "## ##", "#   #"], X: ["#   #", " # # ", "  #  ", " # # ", "#   #"], Y: ["#   #", " # # ", "  #  ", "  #  ", "  #  "], Z: ["#####", "   # ", "  #  ", " #   ", "#####"],
  J: ["  ###", "   # ", "   # ", "#  # ", " ##  "], Q: [" ### ", "#   #", "# # #", "#  # ", " ## #"],
  0: [" ### ", "#  ##", "# # #", "##  #", " ### "], 1: ["  #  ", " ##  ", "  #  ", "  #  ", " ### "], 2: [" ### ", "#   #", "  ## ", " #   ", "#####"],
  3: ["#### ", "    #", " ### ", "    #", "#### "], 4: ["#  # ", "#  # ", "#####", "   # ", "   # "], 5: ["#####", "#    ", "#### ", "    #", "#### "],
  6: [" ### ", "#    ", "#### ", "#   #", " ### "], 7: ["#####", "   # ", "  #  ", " #   ", " #   "], 8: [" ### ", "#   #", " ### ", "#   #", " ### "],
  9: [" ### ", "#   #", " ####", "    #", " ### "],
  "$": [" ####", "# #  ", " ### ", "  # #", "#### "], "%": ["#   #", "   # ", "  #  ", " #   ", "#   #"], ".": [" ", " ", " ", " ", "#"], ",": [" ", " ", " ", "#", "#"],
  "-": ["   ", "   ", "###", "   ", "   "], "+": ["     ", "  #  ", "#####", "  #  ", "     "], " ": ["   ", "   ", "   ", "   ", "   "], "?": [" ### ", "#   #", "  ## ", "     ", "  #  "]
};
GLYPH["−"] = GLYPH["-"];
function blockText(str) {
  const rows = ["", "", "", "", ""]; let first = true;
  for (const ch of String(str).toUpperCase()) { const g = GLYPH[ch] || GLYPH["?"]; for (let r = 0; r < 5; r++) rows[r] += (first ? "" : " ") + g[r].replace(/#/g, "█"); first = false; }
  return rows.join("\n");
}
// the same lettering as crisp square pixels (SVG), sized by the --px custom property of whatever holds it
function blockSVG(str) {
  const rows = blockText(str).split("\n"), w = rows[0].length; let d = "";
  rows.forEach((row, y) => { for (let x = 0; x < row.length; x++) if (row[x] === "█") d += `M${x} ${y}h.88v.88h-.88z`; });
  return `<svg class="bsvg" style="--w:${w}" viewBox="0 0 ${w} 5" shape-rendering="crispEdges" fill="currentColor" aria-hidden="true"><path d="${d}"/></svg>`;
}
// letters appear one at a time
function blockReveal(el, str, ms) {
  if (reduced) { el.innerHTML = blockSVG(str); return; }
  const n = String(str).length, t0 = performance.now(); ms = ms || 420; cancelAnimationFrame(el._br);
  (function step(now) { const k = Math.min(1, (now - t0) / ms); el.innerHTML = blockSVG(String(str).slice(0, Math.max(1, Math.ceil(k * n)))); if (k < 1) el._br = requestAnimationFrame(step); })(t0);
}
// Charts are plain lines. A sparkline is a thin line; a chart is a line over a soft fill with a dot on the latest value and the high and low beside it.
// `log` plots ratios, so +100% and −50% look the same size.
let _lg = 0;
function sparkSVG(v) {
  const W = 84, H = 26, mn = Math.min(...v), sp = Math.max(...v) - mn || 1, pts = v.map((x, i) => (i / (v.length - 1) * W).toFixed(1) + " " + (H - 3 - (x - mn) / sp * (H - 6)).toFixed(1));
  return `<svg class="sp ${v[v.length - 1] >= v[0] ? "up" : "dn"}" viewBox="0 0 ${W} ${H}" aria-hidden="true"><path class="ln" d="M${pts.join(" L")}"/></svg>`;
}
function lineChart(vals, o) {
  o = o || {}; const W = 600, H = 200, P = 8, v = o.log ? vals.map(Math.log) : vals, mn = Math.min(...v), mx = Math.max(...v), mid = (mn + mx) / 2, sp = Math.max(mx - mn, o.log ? .06 : Math.abs(mid) * .01) * 1.2, lo = mid - sp / 2;
  const Y = x => P + (H - 2 * P) * (1 - (x - lo) / sp), pts = v.map((x, i) => (P + (W - 2 * P) * i / (v.length - 1)).toFixed(1) + " " + Y(x).toFixed(1)), d = "M" + pts.join(" L"), id = "lg" + (++_lg), fmt = o.fmt || String;
  return `<div class="lcbox ${vals[vals.length - 1] >= vals[0] ? "up" : "dn"}" style="--h:${o.h || 170}px"><div class="lcwrap"><svg class="lc" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="price chart"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:var(--c);stop-opacity:.28"/><stop offset="1" style="stop-color:var(--c);stop-opacity:0"/></linearGradient></defs><path d="${d} L${W - P} ${H} L${P} ${H} Z" fill="url(#${id})"/><path class="ln" d="${d}"/></svg><i class="dot" style="top:${(Y(v[v.length - 1]) / H * 100).toFixed(1)}%"></i></div><div class="axis"><span>${fmt(Math.max(...vals))}</span><span>${fmt(Math.min(...vals))}</span></div></div>`;
}
const buzzDots = n => `<span class="dots" role="img" aria-label="buzz ${n} of 5">${[0, 1, 2, 3, 4].map(i => `<i class="${i < n ? "on" : ""}"></i>`).join("")}</span>`;
// An ASCII line chart, drawn the way people draw them by hand with ╭ ╮ ╰ ╯ ─ │. Values are resampled to `w` columns and plotted on a log scale.
// Returns the character grid (row 0 is the top), each column's height Y (0 = bottom row) and the resampled values.
function plotGrid(vals, w, h) {
  const n = vals.length, v = []; for (let x = 0; x < w; x++) { const f = x / (w - 1) * (n - 1), i = Math.floor(f), j = Math.min(n - 1, i + 1); v.push(vals[i] + (vals[j] - vals[i]) * (f - i)); }
  const L = v.map(Math.log), mn = Math.min(...L), sp = Math.max(Math.max(...L) - mn, .1), Y = L.map(x => Math.round((x - mn) / sp * (h - 1))), grid = Array.from({ length: h }, () => Array(w).fill(" "));
  for (let x = 0; x < w - 1; x++) {
    const y0 = Y[x], y1 = Y[x + 1];
    if (y0 === y1) grid[h - 1 - y0][x] = "─";
    else { grid[h - 1 - y1][x] = y0 > y1 ? "╰" : "╭"; grid[h - 1 - y0][x] = y0 > y1 ? "╮" : "╯"; for (let y = Math.min(y0, y1) + 1; y < Math.max(y0, y1); y++) grid[h - 1 - y][x] = "│"; }
  }
  grid[h - 1 - Y[w - 1]][w - 1] = "─";
  return { grid, Y, v };
}
const pctShort = p => (p >= 0 ? "+" : "−") + (Math.abs(p * 100) >= 100 ? Math.round(Math.abs(p * 100)).toLocaleString("en-US") : Math.abs(p * 100).toFixed(1)) + "%";
const heldText = ms => { const m = Math.round(ms / 6e4); if (m < 1) return "under a minute"; if (m < 90) return m + " min"; const h = Math.floor(m / 60); return h < 48 ? h + "h " + (m % 60) + "m" : Math.round(h / 24) + " days"; };
const pnlHTML = (d, base) => `<span class="${d > 0 ? "up" : d < 0 ? "dn" : "fl"}">${d > 0 ? "▲ +" : d < 0 ? "▼ −" : "– "}${money(Math.abs(d))}${base > 0 ? ` <span class="dim">${Math.abs(d / base * 100).toFixed(Math.abs(d / base) >= 1 ? 0 : 1)}%</span>` : ""}</span>`;
const pctHTML = p => `<span class="${p > .0005 ? "up" : p < -.0005 ? "dn" : "fl"}">${p > .0005 ? "▲ +" : p < -.0005 ? "▼ −" : "– "}${Math.abs(p * 100) >= 100 ? Math.round(Math.abs(p * 100)).toLocaleString("en-US") : Math.abs(p * 100).toFixed(1)}%</span>`;
// a progress bar made of characters: [███░░] 
const meter = (i, n) => "[" + fill("█", i) + fill("░", n - i) + "]";
