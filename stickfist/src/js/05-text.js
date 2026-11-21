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
  0: [" ### ", "#  ##", "# # #", "##  #", " ### "], 1: ["  #  ", " ##  ", "  #  ", "  #  ", " ### "], 2: [" ### ", "#   #", "  ## ", " #   ", "#####"],
  3: ["#### ", "    #", " ### ", "    #", "#### "], 4: ["#  # ", "#  # ", "#####", "   # ", "   # "], 5: ["#####", "#    ", "#### ", "    #", "#### "],
  6: [" ### ", "#    ", "#### ", "#   #", " ### "], 7: ["#####", "   # ", "  #  ", " #   ", " #   "], 8: [" ### ", "#   #", " ### ", "#   #", " ### "],
  9: [" ### ", "#   #", " ####", "    #", " ### "],
  "$": [" ####", "# #  ", " ### ", "  # #", "#### "], "%": ["#   #", "   # ", "  #  ", " #   ", "#   #"], ".": [" ", " ", " ", " ", "#"], ",": [" ", " ", " ", "#", "#"],
  "-": ["   ", "   ", "###", "   ", "   "], " ": ["   ", "   ", "   ", "   ", "   "], "?": [" ### ", "#   #", "  ## ", "     ", "  #  "]
};
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
// a sparkline: one block character per value, scaled between the lowest and highest
const SPARKS = "▁▂▃▄▅▆▇█";
const spark = v => { const mn = Math.min(...v), sp = Math.max(...v) - mn || 1; return v.map(x => SPARKS[clamp(Math.round((x - mn) / sp * 7), 0, 7)]).join(""); };
// a small chart: `h` rows of block characters, one column per value
function asciiChart(vals, h) {
  const mn = Math.min(...vals), sp = Math.max(...vals) - mn || 1, B = " ▁▂▃▄▅▆▇█", rows = [];
  for (let r = h - 1; r >= 0; r--) { let line = ""; for (const v of vals) line += B[clamp(Math.round((v - mn) / sp * h * 8 - r * 8), 0, 8)]; rows.push(line); }
  return rows.join("\n");
}
const pctHTML = p => `<span class="${p > .0005 ? "up" : p < -.0005 ? "dn" : "fl"}">${p > .0005 ? "▲ +" : p < -.0005 ? "▼ −" : "– "}${Math.abs(p * 100).toFixed(Math.abs(p) >= 1 ? 0 : 1)}%</span>`;
// a progress bar made of characters: [███░░] 
const meter = (i, n) => "[" + fill("█", i) + fill("░", n - i) + "]";
