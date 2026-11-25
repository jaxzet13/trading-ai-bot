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
// val is in units of play money, 500 to the dollar (see UNIT). chars is the exact number printed on the card.
const CARDS = [
  { no: "001", id: "stitch",  name: "Stitch",  sub: "frog hat",   rar: "common",    chars: 6432,   val: 4,    tint: "#ece7dc", cap: "frog hat. zero regrets.",       styles: true },
  { no: "003", id: "brick",   name: "Brick",   sub: "colander",   rar: "common",    chars: 6432,   val: 5,    tint: "#a8ffbe", cap: "it is a colander. it works.", styles: true },
  { no: "004", id: "rook",    name: "Rook",    sub: "pool noodle", rar: "common",   chars: 6432,   val: 6,    tint: "#a8ffbe", cap: "reach: floppy.", styles: true },
  { no: "012", id: "orbit",   name: "Orbit",   sub: "galaxy",     rar: "uncommon",  chars: 7260,   val: 34,    tint: "#a9c9ff", cap: "already read the ending.", styles: true },
  { no: "019", id: "phantom", name: "Phantom", sub: "wings",      rar: "uncommon",  chars: 15750,  val: 42,    tint: "#ece7dc", cap: "gone before the cape lands.", styles: true },
  { no: "018", id: "null",    name: "Null",    sub: "star",       rar: "rare",      chars: 29260,  val: 292,   tint: "#a9c9ff", cap: "not on any record.", styles: true },
  { no: "017", id: "shogun",  name: "Shogun",  sub: "gold wings", rar: "rare",      chars: 31970,  val: 261,   tint: "#ffd27a", cap: "rents you the air.", styles: true },
  { no: "006", id: "ronin",   name: "Ronin",   sub: "cliff",      rar: "epic",      chars: 71680,  val: 445,   tint: "#ff8ac9", cap: "", styles: true },
  { no: "011", id: "grimm",   name: "Grimm",   sub: "cathedral",  rar: "legendary", chars: 219520, val: 1170,  tint: "#a8ffb0", cap: "", styles: true },
  { no: "015", id: "reaper",  name: "Reaper",  sub: "ember",      rar: "mythic",    chars: 701000, val: 7250, tint: "#ffc87a", cap: "", styles: true },
  { no: "020", id: "umbra",   name: "Umbra",   sub: "eclipse",    rar: "secret",    chars: 1578000, val: 15625, tint: "#ffb54a", cap: "the sun blinked first.", styles: true },
  // ---- more First Print cards (same worth as the card each one shares a rarity with, so what a pack returns and how often it pays are unchanged; they only make the packs less repetitive)
  { no: "026", id: "mop",     name: "Mop",     sub: "bucket helmet", rar: "common",   chars: 6432,  val: 7,  tint: "#a8ffbe", cap: "swab the deck.",              styles: true },
  { no: "027", id: "pan",     name: "Pan",     sub: "frying pan",    rar: "common",   chars: 6432,  val: 8,  tint: "#ece7dc", cap: "it's a frying pan. it counts.", styles: true },
  { no: "028", id: "cone",    name: "Cone",    sub: "traffic cone",  rar: "common",   chars: 6432,  val: 9,  tint: "#ffd27a", cap: "caution: confident.",         styles: true },
  { no: "029", id: "tempest", name: "Tempest", sub: "storm",         rar: "uncommon", chars: 7260,  val: 38,  tint: "#a9c9ff", cap: "weather is a choice.",         styles: true },
  { no: "030", id: "surge",   name: "Surge",   sub: "big wave",      rar: "uncommon", chars: 15750, val: 46,  tint: "#9fe8ff", cap: "ride it before it breaks.",    styles: true },
  { no: "031", id: "kraken",  name: "Kraken",  sub: "tentacles",     rar: "rare",     chars: 28000, val: 233, tint: "#9fe8d8", cap: "it was always down there.",    styles: true },
  // ---- Moonshot: one launch, five altitudes. The higher the card, the rarer it is.
  { no: "021", set: "ms", id: "fuse",     name: "Fuse",     sub: "match",         rar: "common",    chars: 8736,   val: 14,   tint: "#ffd27a", cap: "light it and walk away.",       styles: true },
  { no: "022", set: "ms", id: "ignition", name: "Ignition", sub: "launch pad",    rar: "uncommon",  chars: 10080,  val: 65,   tint: "#ffb070", cap: "no turning back from here.",     styles: true },
  { no: "023", set: "ms", id: "liftoff",  name: "Liftoff",  sub: "plume",         rar: "rare",      chars: 40320,  val:  1134,  tint: "#ffb070", cap: "gravity lost the argument.",    styles: true },
  { no: "024", set: "ms", id: "apogee",   name: "Apogee",   sub: "edge of space", rar: "epic",      chars: 123480, val: 1667, tint: "#7ee8ff", cap: "the top is quiet.",            styles: true },
  { no: "025", set: "ms", id: "luna",     name: "Luna",     sub: "first flag",    rar: "legendary", chars: 448800, val: 4145, tint: "#b8d4ff", cap: "to the moon was never a joke.", styles: true },
  // ---- more Moonshot cards, each at the altitude (and worth) of a card already there
  { no: "032", set: "ms", id: "spark",     name: "Spark",     sub: "sparkler",     rar: "common",   chars: 8736,   val: 16,   tint: "#ffb070", cap: "small things start fires.", styles: true },
  { no: "033", set: "ms", id: "countdown", name: "Countdown", sub: "launch button", rar: "uncommon", chars: 10080,  val: 270,   tint: "#ff8a7a", cap: "three. two. one.",           styles: true },
  { no: "034", set: "ms", id: "booster",   name: "Booster",   sub: "stage split",  rar: "rare",     chars: 40320,  val:  1333, tint: "#ffc98a", cap: "dead weight, dropped.",      styles: true },
  { no: "035", set: "ms", id: "flare",     name: "Flare",     sub: "signal flare", rar: "common",   chars: 8736,   val: 19,   tint: "#ff8a7a", cap: "the sky has been told.",     styles: true },
  { no: "036", set: "ms", id: "bubble",    name: "Bubble",    sub: "fishbowl helmet", rar: "common", chars: 8736,  val: 21,   tint: "#ece7dc", cap: "all systems: smiling.",      styles: true },
  { no: "037", set: "ms", id: "gantry",    name: "Gantry",    sub: "tower arm",    rar: "uncommon", chars: 10080,  val: 480,   tint: "#9fe8ff", cap: "the arm lets go.",           styles: true }
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
/* Each pack holds the cards of one set. A slot is a list of [card id, weight]. The packs are tuned so that each one sells back for at least its cost about 40% of the time (a bit less when the market is hot)
   and returns 93 to 95% on average, never more than 95% (both move with the market, and are worked out live in 04-state.js). */
const PACKS = [
  { id: "fp", set: "fp", name: "First Print", blurb: "Stick figures made of text, from a galaxy in a jar to a total eclipse.", price: 259, min: 130, max: 2500, n: 3,
    order: ["orbit", "tempest", "phantom", "surge", "null", "shogun", "kraken", "ronin", "grimm", "reaper", "umbra"],
    slotNames: ["Card 1: an uncommon", "Card 2: an uncommon", "Card 3: the hit: a rare or better in 4 packs out of 10"],
    slots: [
      [["orbit", 30], ["tempest", 27], ["phantom", 23], ["surge", 20]],
      [["orbit", 30], ["tempest", 27], ["phantom", 23], ["surge", 20]],
      [["orbit", 17.1283], ["tempest", 15.4155], ["phantom", 13.1317], ["surge", 11.4189], ["kraken", 15.2], ["shogun", 12.54], ["null", 10.26], ["ronin", 4.2924], ["grimm", 0.5212], ["reaper", 0.0613], ["umbra", 0.0308]]
    ] },
  { id: "ms", set: "ms", name: "Moonshot", blurb: "One launch and what happens on the way up: the pad, a rocket on its plume, a flag on the Moon. The higher the card, the rarer it is.", price: 726, min: 375, max: 7500, n: 3,
    order: ["luna", "liftoff", "booster", "ignition", "countdown", "gantry", "apogee"],
    slotNames: ["Card 1: a launch-pad card", "Card 2: a launch-pad card", "Card 3: the hit: now and then a Liftoff or higher"],
    slots: [
      [["ignition", 55], ["countdown", 30], ["gantry", 15]],
      [["ignition", 55], ["countdown", 30], ["gantry", 15]],
      [["ignition", 49.8438], ["countdown", 27.1875], ["gantry", 13.5938], ["liftoff", 3.6], ["booster", 2.9], ["apogee", 2.5], ["luna", 0.375]]
    ] }
];
// A card that no pack holds any more is retired: copies people already have keep their worth and can still be sold, but it is no longer counted, chased or shown as missing.
// (The ten commons were retired when packs went from five cards to three: every card in a pack is now worth looking at.)
{ const live = new Set(); PACKS.forEach(pk => pk.slots.forEach(sl => sl.forEach(([id]) => live.add(id)))); CARDS.forEach(c => { c.retired = !live.has(c.id); }); }
const LIVE = CARDS.filter(c => !c.retired);
const PACK_BY = Object.fromEntries(PACKS.map(p => [p.id, p])), packOf = card => PACK_BY[card.set];
// Play money is counted in units: 500 of them are one dollar, so a unit is a fifth of a cent. First Print costs $1.00 (500 units) and Moonshot $3.00 (1,500), and every card in a pack
// is worth in proportion, so what a pack returns is unchanged by it. You start with $2.00.
const SELLBACK = .9, START = 500, UNIT = 500;
