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
  { no: "001", id: "stitch",  name: "Stitch",  sub: "frog hat",   rar: "common",    chars: 2772,   val: 11,    tint: "#ece7dc", cap: "frog hat. zero regrets.",       styles: true },
  { no: "003", id: "brick",   name: "Brick",   sub: "colander",   rar: "common",    chars: 2816,   val: 11,    tint: "#a8ffbe", cap: "it is a colander. it works.", styles: true },
  { no: "004", id: "rook",    name: "Rook",    sub: "pool noodle", rar: "common",   chars: 2816,   val: 11,    tint: "#a8ffbe", cap: "reach: floppy.", styles: true },
  { no: "012", id: "orbit",   name: "Orbit",   sub: "galaxy",     rar: "uncommon",  chars: 7260,   val: 51,    tint: "#a9c9ff", cap: "already read the ending.", styles: true },
  { no: "019", id: "phantom", name: "Phantom", sub: "wings",      rar: "uncommon",  chars: 15750,  val: 50,    tint: "#ece7dc", cap: "gone before the cape lands.", styles: true },
  { no: "018", id: "null",    name: "Null",    sub: "star",       rar: "rare",      chars: 29260,  val: 261,   tint: "#a9c9ff", cap: "not on any record.", styles: true },
  { no: "017", id: "shogun",  name: "Shogun",  sub: "gold wings", rar: "rare",      chars: 31970,  val: 766,   tint: "#ffd27a", cap: "rents you the air.", styles: true },
  { no: "006", id: "ronin",   name: "Ronin",   sub: "cliff",      rar: "epic",      chars: 71680,  val: 890,   tint: "#ff8ac9", cap: "", styles: true },
  { no: "011", id: "grimm",   name: "Grimm",   sub: "cathedral",  rar: "legendary", chars: 219520, val: 2340,  tint: "#a8ffb0", cap: "", styles: true },
  { no: "015", id: "reaper",  name: "Reaper",  sub: "ember",      rar: "mythic",    chars: 701000, val: 14500, tint: "#ffc87a", cap: "", styles: true },
  { no: "020", id: "umbra",   name: "Umbra",   sub: "eclipse",    rar: "secret",    chars: 1578000, val: 31250, tint: "#ffb54a", cap: "the sun blinked first.", styles: true },
  // ---- more First Print cards (same worth as the card each one shares a rarity with, so what a pack returns and how often it pays are unchanged; they only make the packs less repetitive)
  { no: "026", id: "mop",     name: "Mop",     sub: "bucket helmet", rar: "common",   chars: 2816,  val: 11,  tint: "#a8ffbe", cap: "swab the deck.",              styles: true },
  { no: "027", id: "pan",     name: "Pan",     sub: "frying pan",    rar: "common",   chars: 2816,  val: 11,  tint: "#ece7dc", cap: "it's a frying pan. it counts.", styles: true },
  { no: "028", id: "cone",    name: "Cone",    sub: "traffic cone",  rar: "common",   chars: 2816,  val: 11,  tint: "#ffd27a", cap: "caution: confident.",         styles: true },
  { no: "029", id: "tempest", name: "Tempest", sub: "storm",         rar: "uncommon", chars: 7260,  val: 51,  tint: "#a9c9ff", cap: "weather is a choice.",         styles: true },
  { no: "030", id: "surge",   name: "Surge",   sub: "big wave",      rar: "uncommon", chars: 15750, val: 50,  tint: "#9fe8ff", cap: "ride it before it breaks.",    styles: true },
  { no: "031", id: "kraken",  name: "Kraken",  sub: "tentacles",     rar: "rare",     chars: 28000, val: 766, tint: "#c9a5ff", cap: "it was always down there.",    styles: true },
  // ---- Moonshot: one launch, five altitudes. The higher the card, the rarer it is.
  { no: "021", set: "ms", id: "fuse",     name: "Fuse",     sub: "match",         rar: "common",    chars: 3600,   val: 44,   tint: "#ffd27a", cap: "light it and walk away.",       styles: true },
  { no: "022", set: "ms", id: "ignition", name: "Ignition", sub: "launch pad",    rar: "uncommon",  chars: 10080,  val: 80,   tint: "#ffb070", cap: "no turning back from here.",     styles: true },
  { no: "023", set: "ms", id: "liftoff",  name: "Liftoff",  sub: "plume",         rar: "rare",      chars: 40320,  val:  2400,  tint: "#ff7a6a", cap: "gravity lost the argument.",    styles: true },
  { no: "024", set: "ms", id: "apogee",   name: "Apogee",   sub: "edge of space", rar: "epic",      chars: 123480, val: 3314, tint: "#7ee8ff", cap: "the top is quiet.",            styles: true },
  { no: "025", set: "ms", id: "luna",     name: "Luna",     sub: "first flag",    rar: "legendary", chars: 448800, val: 8290, tint: "#b8d4ff", cap: "to the moon was never a joke.", styles: true },
  // ---- more Moonshot cards, each at the altitude (and worth) of a card already there
  { no: "032", set: "ms", id: "spark",     name: "Spark",     sub: "sparkler",     rar: "common",   chars: 3600,   val: 44,   tint: "#ffb070", cap: "small things start fires.", styles: true },
  { no: "033", set: "ms", id: "countdown", name: "Countdown", sub: "launch button", rar: "uncommon", chars: 10080,  val: 80,   tint: "#a8ffbe", cap: "three. two. one.",           styles: true },
  { no: "034", set: "ms", id: "booster",   name: "Booster",   sub: "stage split",  rar: "rare",     chars: 40320,  val:  2400, tint: "#ffd27a", cap: "dead weight, dropped.",      styles: true },
  { no: "035", set: "ms", id: "flare",     name: "Flare",     sub: "signal flare", rar: "common",   chars: 3600,   val: 44,   tint: "#ff8a7a", cap: "the sky has been told.",     styles: true },
  { no: "036", set: "ms", id: "bubble",    name: "Bubble",    sub: "fishbowl helmet", rar: "common", chars: 3600,  val: 44,   tint: "#ece7dc", cap: "all systems: smiling.",      styles: true },
  { no: "037", set: "ms", id: "gantry",    name: "Gantry",    sub: "tower arm",    rar: "uncommon", chars: 10080,  val: 80,   tint: "#9fe8ff", cap: "the arm lets go.",           styles: true }
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
  { id: "fp", set: "fp", name: "First Print", blurb: "Stick figures made of text, from a frog in a hat to a total eclipse.", price: 500, min: 250, max: 5000, n: 5,
    order: ["stitch", "brick", "rook", "mop", "pan", "cone", "orbit", "tempest", "phantom", "surge", "null", "shogun", "kraken", "ronin", "grimm", "reaper", "umbra"],
    slotNames: ["Card 1: a common", "Card 2: a common", "Card 3: a common, sometimes better", "Card 4: an uncommon or better", "Card 5: the best card in the pack"],
    slots: [
      [["stitch", 1], ["brick", 1], ["rook", 1], ["mop", 1], ["pan", 1], ["cone", 1]],
      [["stitch", 1], ["brick", 1], ["rook", 1], ["mop", 1], ["pan", 1], ["cone", 1]],
      [["stitch", 15.5265], ["brick", 15.5265], ["rook", 15.5265], ["mop", 15.5265], ["pan", 15.5265], ["cone", 15.5265], ["orbit", 2.0523], ["tempest", 2.0523], ["phantom", 1.3682], ["surge", 1.3682]],
      [["orbit", 13.2315], ["tempest", 13.2315], ["phantom", 30.4175], ["surge", 30.4175], ["null", 4.544], ["shogun", 4.079], ["kraken", 4.079]],
      [["orbit", 24.793], ["tempest", 24.793], ["phantom", 5.869], ["surge", 5.869], ["null", 4.13], ["shogun", 16.793], ["kraken", 16.793], ["ronin", 0.84], ["grimm", 0.102], ["reaper", 0.012], ["umbra", 0.006]]
    ] },
  { id: "ms", set: "ms", name: "Moonshot", blurb: "One launch and what happens on the way up: a lit fuse on the ground, a rocket on its plume, a flag on the Moon. The higher the card, the rarer it is.", price: 1500, min: 750, max: 15000, n: 5,
    order: ["luna", "fuse", "spark", "flare", "bubble", "liftoff", "booster", "ignition", "countdown", "gantry", "apogee"],
    slotNames: ["Card 1: a low-altitude card, now and then an Ignition", "Card 2: a low-altitude card, now and then an Ignition", "Card 3: low altitude, sometimes a Liftoff", "Card 4: an Ignition or higher", "Card 5: the best card in the pack"],
    slots: [
      [["fuse", 22.9105], ["spark", 22.9105], ["flare", 22.9105], ["bubble", 22.9105], ["ignition", 2.786], ["countdown", 2.786], ["gantry", 2.786], ["liftoff", 0], ["booster", 0]],
      [["fuse", 18.6468], ["spark", 18.6468], ["flare", 18.6468], ["bubble", 18.6468], ["ignition", 8.471], ["countdown", 8.471], ["gantry", 8.471], ["liftoff", 0], ["booster", 0]],
      [["fuse", 9.154], ["spark", 9.154], ["flare", 9.154], ["bubble", 9.154], ["ignition", 20.532], ["countdown", 20.532], ["gantry", 20.532], ["liftoff", 0.894], ["booster", 0.894]],
      [["fuse", 6.0493], ["spark", 6.0493], ["flare", 6.0493], ["bubble", 6.0493], ["ignition", 22.063], ["countdown", 22.063], ["gantry", 22.063], ["liftoff", 4.057], ["booster", 4.057], ["apogee", 1.5]],
      [["fuse", 7.3385], ["spark", 7.3385], ["flare", 7.3385], ["bubble", 7.3385], ["ignition", 12.701], ["countdown", 12.701], ["gantry", 12.701], ["liftoff", 13.909], ["booster", 13.909], ["apogee", 4.35], ["luna", 0.375]]
    ] }
];
const PACK_BY = Object.fromEntries(PACKS.map(p => [p.id, p])), packOf = card => PACK_BY[card.set];
// Play money is counted in units: 500 of them are one dollar, so a unit is a fifth of a cent. First Print costs $1.00 (500 units) and Moonshot $3.00 (1,500), and every card in a pack
// is worth in proportion, so what a pack returns is unchanged by it. You start with $2.00.
const SELLBACK = .9, START = 1000, UNIT = 500;
