/* ============================================================================
   1. DATA. Two packs, sixteen cards. Every card is a finished ASCII card; the picture is a file,
      the type under it (name, count, copy id, caption) is drawn live so every copy can carry its own id.
   ========================================================================== */
const RAR = {
  common:    { name: "Common",    cuts: 0, tier: 0, col: "#6f6c65" },
  uncommon:  { name: "Uncommon",  cuts: 0, tier: 1, col: "#7f9bff" },
  rare:      { name: "Rare",      cuts: 1, tier: 2, col: "#b07aff" },
  epic:      { name: "Epic",      cuts: 1, tier: 3, col: "#ff6fd0" },
  legendary: { name: "Legendary", cuts: 2, tier: 4, col: "#ffc94a" },
  mythic:    { name: "Mythic",    cuts: 3, tier: 5, col: "#ff4a4a" },
  secret:    { name: "Secret",    cuts: 4, tier: 6, col: "#ffe2a8" }
};
// val is in cents. chars is the exact number printed on the card.
const CARDS = [
  { no: "001", id: "stitch",  name: "Stitch",  sub: "frog hat",   rar: "common",    chars: 2772,   val: 11,    tint: "#ece7dc", cap: "frog hat. zero regrets.",       styles: true },
  { no: "003", id: "brick",   name: "Brick",   sub: "colander",   rar: "common",    chars: 2816,   val: 11,    tint: "#a8ffbe", cap: "it is a colander. it works.", styles: true },
  { no: "004", id: "rook",    name: "Rook",    sub: "pool noodle", rar: "common",   chars: 2816,   val: 11,    tint: "#a8ffbe", cap: "reach: floppy.", styles: true },
  { no: "012", id: "orbit",   name: "Orbit",   sub: "galaxy",     rar: "uncommon",  chars: 7260,   val: 14,    tint: "#a9c9ff", cap: "already read the ending.", styles: true },
  { no: "019", id: "phantom", name: "Phantom", sub: "wings",      rar: "uncommon",  chars: 15750,  val: 35,    tint: "#ece7dc", cap: "gone before the cape lands.", styles: true },
  { no: "018", id: "null",    name: "Null",    sub: "star",       rar: "rare",      chars: 29260,  val: 306,   tint: "#a9c9ff", cap: "not on any record.", styles: true },
  { no: "017", id: "shogun",  name: "Shogun",  sub: "gold wings", rar: "rare",      chars: 31970,  val: 700,   tint: "#ffd27a", cap: "rents you the air.", styles: true },
  { no: "006", id: "ronin",   name: "Ronin",   sub: "cliff",      rar: "epic",      chars: 71680,  val: 890,   tint: "#ff8ac9", cap: "", styles: true },
  { no: "011", id: "grimm",   name: "Grimm",   sub: "cathedral",  rar: "legendary", chars: 219520, val: 2340,  tint: "#a8ffb0", cap: "", styles: true },
  { no: "015", id: "reaper",  name: "Reaper",  sub: "ember",      rar: "mythic",    chars: 701000, val: 14500, tint: "#ffc87a", cap: "", styles: true },
  { no: "020", id: "umbra",   name: "Umbra",   sub: "eclipse",    rar: "secret",    chars: 1578000, val: 31250, tint: "#ffb54a", cap: "the sun blinked first.", styles: true },
  // ---- Moonshot: one launch, five altitudes. The higher the card, the rarer it is.
  { no: "021", set: "ms", id: "fuse",     name: "Fuse",     sub: "match",         rar: "common",    chars: 3600,   val: 12,   tint: "#ffd27a", cap: "light it and walk away.",       styles: true },
  { no: "022", set: "ms", id: "ignition", name: "Ignition", sub: "launch pad",    rar: "uncommon",  chars: 10080,  val: 30,   tint: "#ffb070", cap: "no turning back from here.",     styles: true },
  { no: "023", set: "ms", id: "liftoff",  name: "Liftoff",  sub: "plume",         rar: "rare",      chars: 40320,  val: 780,  tint: "#ff7a6a", cap: "gravity lost the argument.",    styles: true },
  { no: "024", set: "ms", id: "apogee",   name: "Apogee",   sub: "edge of space", rar: "epic",      chars: 123480, val: 1250, tint: "#7ee8ff", cap: "the top is quiet.",            styles: true },
  { no: "025", set: "ms", id: "luna",     name: "Luna",     sub: "first flag",    rar: "legendary", chars: 448800, val: 3200, tint: "#b8d4ff", cap: "to the moon was never a joke.", styles: true }
];
// the sets: the two letters a copy id starts with, and what the set is called
const SETS = { fp: { code: "IS", name: "First Print" }, ms: { code: "MS", name: "Moonshot" } };
CARDS.forEach(c => { c.set = c.set || "fp"; });
const BY_NO = Object.fromEntries(CARDS.map(c => [c.no, c])), BY_ID = Object.fromEntries(CARDS.map(c => [c.id, c]));
// The twelve ASCII styles any card can come out in (odds per card, value multiplier). The default is the plain look. A copy's own code decides its style.
const STYLES = {
  steel:   { name: "Phosphor",     p: .006,  x: 3   }, dots:  { name: "Amber",    p: .005,  x: 3   },
  vhs:     { name: "Glitch",       p: .004,  x: 3.5 }, scratch: { name: "Typeset", p: .004, x: 3.5 },
  ice:     { name: "Stipple",      p: .0025, x: 5   }, chain: { name: "Linework", p: .0025, x: 5   },
  wire:    { name: "Pixel",        p: .002,  x: 6   }, print: { name: "Blood",    p: .002,  x: 6   },
  glass:   { name: "Glow",         p: .001,  x: 10  }, blood: { name: "Toxic Glitch", p: .001, x: 10 },
  leaf:    { name: "Iridescent",   p: .0006, x: 15  }, kin:   { name: "Dissolve", p: .0003, x: 25  }
};
const STYLE_TINT = { "": "#ece7dc", steel: "#aaffbd", dots: "#ffd27a", vhs: "#c9a5ff", scratch: "#ece7dc", ice: "#a9c9ff", chain: "#ece7dc", wire: "#b6ff9c", print: "#ff9a94", glass: "#ff8ac9", blood: "#a8ffb0", leaf: "#d6c9ff", kin: "#a9c9ff" };
/* Each pack holds the cards of one set. A slot is a list of [card id, weight]. The packs are tuned so that each one sells back for at least its cost about 40 to 45% of the time
   and returns about 89% on average (both move with the market, and are worked out live in 04-state.js). */
const PACKS = [
  { id: "fp", set: "fp", name: "First Print", blurb: "Stick figures made of text, from a frog in a hat to a total eclipse.", price: 499, min: 249, max: 4999, n: 5,
    order: ["stitch", "umbra", "orbit", "brick", "null", "phantom", "rook", "shogun", "ronin", "grimm", "reaper"],
    slotNames: ["Card 1: a common", "Card 2: a common", "Card 3: a common, sometimes better", "Card 4: an uncommon or better", "Card 5: the best card in the pack"],
    slots: [
      [["stitch", 1], ["brick", 1], ["rook", 1]],
      [["stitch", 1], ["brick", 1], ["rook", 1]],
      [["stitch", 32.4], ["brick", 32.4], ["rook", 32.4], ["orbit", 1.7], ["phantom", 1.2]],
      [["orbit", 2.1], ["phantom", 88.5], ["null", 2.1], ["shogun", 7.3]],
      [["orbit", 44.8], ["phantom", 10.5], ["null", 5], ["shogun", 36.6], ["ronin", 2.8], ["grimm", .34], ["reaper", .04], ["umbra", .02]]
    ] },
  { id: "ms", set: "ms", name: "Moonshot", blurb: "One launch, five altitudes: a lit fuse on the ground up to a flag on the Moon. The higher the card, the rarer it is.", price: 579, min: 289, max: 5799, n: 5,
    order: ["luna", "fuse", "liftoff", "ignition", "apogee"],
    slotNames: ["Card 1: a Fuse, now and then an Ignition", "Card 2: a Fuse, now and then an Ignition", "Card 3: low altitude, sometimes a Liftoff", "Card 4: an Ignition or higher", "Card 5: the best card in the pack"],
    slots: [
      [["fuse", 92], ["ignition", 8]],
      [["fuse", 88], ["ignition", 12]],
      [["fuse", 54], ["ignition", 43.5], ["liftoff", 2.5]],
      [["fuse", 20], ["ignition", 61.7], ["liftoff", 16.3], ["apogee", 2]],
      [["fuse", 3.7], ["ignition", 67.8], ["liftoff", 22.2], ["apogee", 5.8], ["luna", .5]]
    ] }
];
const PACK_BY = Object.fromEntries(PACKS.map(p => [p.id, p])), packOf = card => PACK_BY[card.set];
const SELLBACK = .9, START = 1000, TOPUP = 1000;
