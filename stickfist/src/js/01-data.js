/* ============================================================================
   1. DATA. Two packs, sixteen cards. Every card is a finished ASCII card; the picture is a file,
      the type under it (name, count, copy id, caption) is drawn live so every copy can carry its own id.
   ========================================================================== */
const RAR = {
  // Above epic the rarities are a ladder, one card of each in a set, every step about half as likely as the one before
  // (1 pack in 16, 50, 100, 200, 400, 800, 1,600, 3,200, 6,400). `tier` is how big the card's moment is (frame, glow, how long it
  // takes to form): it stops at 6. `like` names the older rarity whose market behaviour a newer one borrows.
  common:    { name: "Common",    cuts: 0, tier: 0, col: "#6f6c65" },
  uncommon:  { name: "Uncommon",  cuts: 0, tier: 1, col: "#7f9bff" },
  rare:      { name: "Rare",      cuts: 1, tier: 2, col: "#b07aff" },
  epic:      { name: "Epic",      cuts: 1, tier: 3, col: "#ff6fd0" },
  legendary: { name: "Legendary", cuts: 2, tier: 4, col: "#ffc94a" },
  mythic:    { name: "Mythic",    cuts: 3, tier: 5, col: "#ff4a4a" },
  exotic:    { name: "Exotic",    cuts: 3, tier: 5, col: "#3ff0d0", like: "mythic" },
  divine:    { name: "Divine",    cuts: 3, tier: 5, col: "#fff1a8", like: "mythic" },
  celestial: { name: "Celestial", cuts: 4, tier: 6, col: "#8fd0ff", like: "secret" },
  cosmic:    { name: "Cosmic",    cuts: 4, tier: 6, col: "#c58cff", like: "secret" },
  eternal:   { name: "Eternal",   cuts: 4, tier: 6, col: "#ff9d5c", like: "secret" },
  ascended:  { name: "Ascended",  cuts: 4, tier: 6, col: "#f2f4ff", like: "secret" },
  secret:    { name: "Secret",    cuts: 4, tier: 6, col: "#ffe2a8" }
};
// val is in units of play money, 500 to the dollar (see UNIT). chars is the exact number printed on the card.
const CARDS = [
  { no: "001", id: "stitch",  name: "Stitch",  sub: "frog hat",   rar: "uncommon",  chars: 6432,   val: 49,    tint: "#ece7dc", cap: "frog hat. zero regrets.",       styles: true },
  { no: "003", id: "brick",   name: "Brick",   sub: "colander",   rar: "uncommon",  chars: 6432,   val: 57,    tint: "#a8ffbe", cap: "it is a colander. it works.", styles: true },
  { no: "004", id: "rook",    name: "Rook",    sub: "pool noodle", rar: "uncommon", chars: 6432,   val: 143,    tint: "#a8ffbe", cap: "reach: floppy.", styles: true },
  { no: "012", id: "orbit",   name: "Orbit",   sub: "galaxy",     rar: "uncommon",  chars: 7260,   val: 65,    tint: "#a9c9ff", cap: "already read the ending.", styles: true },
  { no: "019", id: "phantom", name: "Phantom", sub: "wings",      rar: "epic",  chars: 15750,  val: 330,    tint: "#ece7dc", cap: "gone before the cape lands.", styles: true },
  { no: "018", id: "null",    name: "Null",    sub: "star",       rar: "exotic",      chars: 29260,  val: 1000,   tint: "#a9c9ff", cap: "not on any record.", styles: true },
  { no: "017", id: "shogun",  name: "Shogun",  sub: "gold wings", rar: "divine",      chars: 31970,  val: 1500,   tint: "#ffd27a", cap: "rents you the air.", styles: true },
  { no: "006", id: "ronin",   name: "Ronin",   sub: "cliff",      rar: "celestial",      chars: 71680,  val: 2300,   tint: "#ff8ac9", cap: "", styles: true },
  { no: "011", id: "grimm",   name: "Grimm",   sub: "cathedral",  rar: "eternal", chars: 219520, val: 12500,  tint: "#a8ffb0", cap: "", styles: true },
  { no: "015", id: "reaper",  name: "Reaper",  sub: "ember",      rar: "ascended",    chars: 701000, val: 25000, tint: "#ffc87a", cap: "", styles: true },
  { no: "020", id: "umbra",   name: "Umbra",   sub: "eclipse",    rar: "secret",    chars: 1578000, val: 50000, tint: "#ffb54a", cap: "the sun blinked first.", styles: true },
  // ---- more First Print cards (same worth as the card each one shares a rarity with, so what a pack returns and how often it pays are unchanged; they only make the packs less repetitive)
  { no: "026", id: "mop",     name: "Mop",     sub: "bucket helmet", rar: "uncommon", chars: 6432,  val: 151,  tint: "#a8ffbe", cap: "swab the deck.",              styles: true },
  { no: "027", id: "pan",     name: "Pan",     sub: "frying pan",    rar: "uncommon", chars: 6432,  val: 159,  tint: "#ece7dc", cap: "it's a frying pan. it counts.", styles: true },
  { no: "028", id: "cone",    name: "Cone",    sub: "traffic cone",  rar: "uncommon", chars: 6432,  val: 167,  tint: "#ffd27a", cap: "caution: confident.",         styles: true },
  { no: "029", id: "tempest", name: "Tempest", sub: "storm",         rar: "rare", chars: 7260,  val: 290,  tint: "#a9c9ff", cap: "weather is a choice.",         styles: true },
  { no: "030", id: "surge",   name: "Surge",   sub: "big wave",      rar: "rare", chars: 15750, val: 294,  tint: "#9fe8ff", cap: "ride it before it breaks.",    styles: true },
  { no: "031", id: "kraken",  name: "Kraken",  sub: "tentacles",     rar: "epic",     chars: 28000, val: 350, tint: "#9fe8d8", cap: "it was always down there.",    styles: true },
  // ---- Moonshot: one launch, five altitudes. The higher the card, the rarer it is.
  { no: "021", set: "ms", id: "fuse",     name: "Fuse",     sub: "match",         rar: "uncommon",  chars: 8736,   val: 155,   tint: "#ffd27a", cap: "light it and walk away.",       styles: true },
  { no: "022", set: "ms", id: "ignition", name: "Ignition", sub: "launch pad",    rar: "rare",  chars: 10080,  val: 810,   tint: "#ffb070", cap: "no turning back from here.",     styles: true },
  { no: "023", set: "ms", id: "liftoff",  name: "Liftoff",  sub: "plume",         rar: "mythic",      chars: 40320,  val:  2400,  tint: "#ffb070", cap: "gravity lost the argument.",    styles: true },
  { no: "024", set: "ms", id: "apogee",   name: "Apogee",   sub: "edge of space", rar: "divine",      chars: 123480, val: 9000, tint: "#7ee8ff", cap: "the top is quiet.",            styles: true },
  { no: "025", set: "ms", id: "luna",     name: "Luna",     sub: "first flag",    rar: "celestial", chars: 448800, val: 17500, tint: "#b8d4ff", cap: "to the moon was never a joke.", styles: true },
  // ---- more Moonshot cards, each at the altitude (and worth) of a card already there
  { no: "032", set: "ms", id: "spark",     name: "Spark",     sub: "sparkler",     rar: "uncommon", chars: 8736,   val: 425,   tint: "#ffb070", cap: "small things start fires.", styles: true },
  { no: "033", set: "ms", id: "countdown", name: "Countdown", sub: "launch button", rar: "uncommon", chars: 10080,  val: 163,   tint: "#ff8a7a", cap: "three. two. one.",           styles: true },
  { no: "034", set: "ms", id: "booster",   name: "Booster",   sub: "stage split",  rar: "exotic",     chars: 40320,  val:  5000, tint: "#ffc98a", cap: "dead weight, dropped.",      styles: true },
  { no: "035", set: "ms", id: "flare",     name: "Flare",     sub: "signal flare", rar: "uncommon", chars: 8736,   val: 445,   tint: "#ff8a7a", cap: "the sky has been told.",     styles: true },
  { no: "036", set: "ms", id: "bubble",    name: "Bubble",    sub: "fishbowl helmet", rar: "uncommon", chars: 8736,  val: 465,   tint: "#ece7dc", cap: "all systems: smiling.",      styles: true },
  { no: "037", set: "ms", id: "gantry",    name: "Gantry",    sub: "tower arm",    rar: "legendary", chars: 10080,  val: 1400,   tint: "#9fe8ff", cap: "the arm lets go.",           styles: true }
  ,
  // ---- new designs (2026-11)
  { no: "038", id: "colossus",  name: "Colossus",  sub: "buried head",  rar: "legendary", chars: 29400, val: 460, tint: "#ece7dc", cap: "it was here before the sand.", styles: true },
  { no: "039", id: "leviathan", name: "Leviathan", sub: "sky whale",    rar: "mythic", chars: 30912, val: 700, tint: "#8ad8ff", cap: "the sky has tides too.",       styles: true },
  { no: "040", id: "titan",     name: "Titan",     sub: "storm giant",  rar: "cosmic", chars: 72600, val: 3600, tint: "#e6ecff", cap: "it knelt first.",              styles: true },
  { no: "041", set: "ms", id: "console", name: "Console", sub: "mission control", rar: "rare", chars: 11008, val: 840, tint: "#9fc4ff", cap: "all stations: go.",     styles: true },
  { no: "042", set: "ms", id: "suit",    name: "Suit",    sub: "suit up",         rar: "epic", chars: 10416, val: 950, tint: "#ece7dc", cap: "one size fits nobody.", styles: true },
  { no: "043", set: "ms", id: "mars",    name: "Mars",    sub: "second flag",   rar: "ascended", chars: 117600, val: 37500,  tint: "#ffb08a", cap: "second flag. first footprint.",     styles: true },
  { no: "044", set: "ms", id: "horizon", name: "Horizon", sub: "event horizon", rar: "secret",   chars: 179920, val: 100000, tint: "#e8e6ff", cap: "nothing leaves. you looked anyway.", styles: true }
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
  // One card a pack. A pack pays for itself when its card sells for at least the price: 45 packs in 100. The uncommons sell for
  // less than the pack; rares and epics for a little more; then the ladder: one card per rarity, each about half as likely and
  // worth about half as much again as the one below it. A legendary or better is 1 pack in 10.
  { id: "fp", set: "fp", name: "First Print", blurb: "Stick figures made of text, from a frog in a hat to a total eclipse.", price: 259, min: 130, max: 2500, n: 1,
    order: ["stitch", "brick", "orbit", "tempest", "surge", "phantom", "kraken", "colossus", "leviathan", "null", "shogun", "ronin", "titan", "grimm", "reaper", "umbra"],
    slotNames: ["The card: a rare or better in 45 packs out of 100. From Legendary up, each rarity is about half as likely as the one before"],
    slots: [
      [["stitch", 21.5804], ["brick", 18.3434], ["orbit", 15.5919], ["tempest", 10.6579], ["surge", 9.5921], ["phantom", 7.3684], ["kraken", 6.6316], ["colossus", 6.25], ["leviathan", 2], ["null", 1], ["shogun", 0.5], ["ronin", 0.25], ["titan", 0.125], ["grimm", 0.0625], ["reaper", 0.0313], ["umbra", 0.0156]]
    ] },
  { id: "ms", set: "ms", name: "Moonshot", blurb: "One launch and what happens on the way up: a lit fuse, the pad, a rocket on its plume, a flag on the Moon. The higher the card, the rarer it is.", price: 726, min: 375, max: 7500, n: 1,
    order: ["fuse", "countdown", "ignition", "console", "suit", "gantry", "liftoff", "booster", "apogee", "luna", "mars", "horizon"],
    slotNames: ["The card: a rare or better in 45 packs out of 100. From Legendary up, each rarity is about half as likely as the one before"],
    slots: [
      [["fuse", 29.9716], ["countdown", 25.4759], ["ignition", 13.4211], ["console", 12.0789], ["suit", 9], ["gantry", 6.25], ["liftoff", 2], ["booster", 1], ["apogee", 0.5], ["luna", 0.25], ["mars", 0.04], ["horizon", 0.0125]]
    ] }
];
// A card that no pack holds any more is retired: copies people already have keep their worth and can still be sold, but it is no longer counted, chased or shown as missing.
// (Retired now: Rook, Mop, Pan, Cone, Spark, Flare and Bubble. A set keeps two uncommons and three rares, and its variety is higher up.)
{ const live = new Set(); PACKS.forEach(pk => pk.slots.forEach(sl => sl.forEach(([id]) => live.add(id)))); CARDS.forEach(c => { c.retired = !live.has(c.id); }); }
const LIVE = CARDS.filter(c => !c.retired);
const PACK_BY = Object.fromEntries(PACKS.map(p => [p.id, p])), packOf = card => PACK_BY[card.set];
// Play money is counted in units: 500 of them are one dollar, so a unit is a fifth of a cent. First Print costs $1.00 (500 units) and Moonshot $3.00 (1,500), and every card in a pack
// is worth in proportion, so what a pack returns is unchanged by it. You start with $2.00.
const SELLBACK = .9, START = 500, UNIT = 500;
