/* ============================================================================
   1. DATA. Two packs, sixteen cards. Every card is a finished ASCII card; the picture is a file,
      the type under it (name, count, copy id, caption) is drawn live so every copy can carry its own id.
   ========================================================================== */
const RAR = {
  // Above epic the rarities are a ladder, one card of each in a set, every step about half as likely as the one before
  // (1 pack in 20, 50, 100, 200, 400, 800, 1,600, 3,200, 6,400). `tier` is how big the card's moment is (frame, glow, how long it
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
  { no: "001", id: "stitch",  name: "Stitch",  sub: "frog hat",   rar: "common",  chars: 6432,   val: 15,    tint: "#ece7dc", cap: "frog hat. zero regrets.",       styles: true },
  { no: "003", id: "brick",   name: "Brick",   sub: "colander",   rar: "common",  chars: 6432,   val: 15,    tint: "#a8ffbe", cap: "it is a colander. it works.", styles: true },
  { no: "004", id: "rook",    name: "Rook",    sub: "pool noodle", rar: "common", chars: 6432,   val: 15,    tint: "#a8ffbe", cap: "reach: floppy.", styles: true },
  { no: "012", id: "orbit",   name: "Orbit",   sub: "galaxy",     rar: "common",  chars: 7260,   val: 20,    tint: "#a9c9ff", cap: "already read the ending.", styles: true },
  { no: "019", id: "phantom", name: "Phantom", sub: "wings",      rar: "legendary",  chars: 15750,  val: 750,    tint: "#ece7dc", cap: "gone before the cape lands.", styles: true },
  { no: "018", id: "null",    name: "Null",    sub: "star",       rar: "divine",      chars: 29260,  val: 8250,   tint: "#a9c9ff", cap: "not on any record.", styles: true },
  { no: "017", id: "shogun",  name: "Shogun",  sub: "gold wings", rar: "divine",      chars: 31970,  val: 11236,   tint: "#ffd27a", cap: "rents you the air.", styles: true },
  { no: "006", id: "ronin",   name: "Ronin",   sub: "cliff",      rar: "cosmic",      chars: 71680,  val: 22575,   tint: "#ff8ac9", cap: "", styles: true },
  { no: "011", id: "grimm",   name: "Grimm",   sub: "cathedral",  rar: "eternal", chars: 219520, val: 50000,  tint: "#a8ffb0", cap: "", styles: true },
  { no: "015", id: "reaper",  name: "Reaper",  sub: "ember",      rar: "ascended",    chars: 701000, val: 100000, tint: "#ffc87a", cap: "", styles: true },
  { no: "020", id: "umbra",   name: "Umbra",   sub: "eclipse",    rar: "secret",    chars: 1578000, val: 500000, tint: "#ffb54a", cap: "the sun blinked first.", styles: true },
  // ---- more First Print cards (same worth as the card each one shares a rarity with, so what a pack returns and how often it pays are unchanged; they only make the packs less repetitive)
  { no: "026", id: "mop",     name: "Mop",     sub: "bucket helmet", rar: "common", chars: 6432,  val: 15,  tint: "#a8ffbe", cap: "swab the deck.",              styles: true },
  { no: "027", id: "pan",     name: "Pan",     sub: "frying pan",    rar: "common", chars: 6432,  val: 20,  tint: "#ece7dc", cap: "it's a frying pan. it counts.", styles: true },
  { no: "028", id: "cone",    name: "Cone",    sub: "traffic cone",  rar: "common", chars: 6432,  val: 20,  tint: "#ffd27a", cap: "caution: confident.",         styles: true },
  { no: "029", id: "tempest", name: "Tempest", sub: "storm",         rar: "uncommon", chars: 7260,  val: 51,  tint: "#a9c9ff", cap: "weather is a choice.",         styles: true },
  { no: "030", id: "surge",   name: "Surge",   sub: "big wave",      rar: "uncommon", chars: 15750, val: 103,  tint: "#9fe8ff", cap: "ride it before it breaks.",    styles: true },
  { no: "031", id: "kraken",  name: "Kraken",  sub: "tentacles",     rar: "legendary",     chars: 28000, val: 1030, tint: "#9fe8d8", cap: "it was always down there.",    styles: true },
  // ---- Moonshot: one launch, five altitudes. The higher the card, the rarer it is.
  { no: "021", set: "ms", id: "fuse",     name: "Fuse",     sub: "match",         rar: "common",  chars: 8736,   val: 20,   tint: "#ffd27a", cap: "light it and walk away.",       styles: true },
  { no: "022", set: "ms", id: "ignition", name: "Ignition", sub: "launch pad",    rar: "rare",  chars: 10080,  val: 251,   tint: "#ffb070", cap: "no turning back from here.",     styles: true },
  { no: "023", set: "ms", id: "liftoff",  name: "Liftoff",  sub: "plume",         rar: "exotic",      chars: 40320,  val:  6780,  tint: "#ffb070", cap: "gravity lost the argument.",    styles: true },
  { no: "024", set: "ms", id: "apogee",   name: "Apogee",   sub: "edge of space", rar: "celestial",      chars: 123480, val: 20200, tint: "#7ee8ff", cap: "the top is quiet.",            styles: true },
  { no: "025", set: "ms", id: "luna",     name: "Luna",     sub: "first flag",    rar: "cosmic", chars: 448800, val: 26400, tint: "#b8d4ff", cap: "to the moon was never a joke.", styles: true },
  // ---- more Moonshot cards, each at the altitude (and worth) of a card already there
  { no: "032", set: "ms", id: "spark",     name: "Spark",     sub: "sparkler",     rar: "common", chars: 8736,   val: 25,   tint: "#ffb070", cap: "small things start fires.", styles: true },
  { no: "033", set: "ms", id: "countdown", name: "Countdown", sub: "launch button", rar: "common", chars: 10080,  val: 25,   tint: "#ff8a7a", cap: "three. two. one.",           styles: true },
  { no: "034", set: "ms", id: "booster",   name: "Booster",   sub: "stage split",  rar: "divine",     chars: 40320,  val:  10000, tint: "#ffc98a", cap: "dead weight, dropped.",      styles: true },
  { no: "035", set: "ms", id: "flare",     name: "Flare",     sub: "signal flare", rar: "common", chars: 8736,   val: 25,   tint: "#ff8a7a", cap: "the sky has been told.",     styles: true },
  { no: "036", set: "ms", id: "bubble",    name: "Bubble",    sub: "fishbowl helmet", rar: "common", chars: 8736,  val: 30,   tint: "#ece7dc", cap: "all systems: smiling.",      styles: true },
  { no: "037", set: "ms", id: "gantry",    name: "Gantry",    sub: "tower arm",    rar: "exotic", chars: 10080,  val: 5000,   tint: "#9fe8ff", cap: "the arm lets go.",           styles: true }
  ,
  // ---- new designs (2026-11)
  { no: "038", id: "colossus",  name: "Colossus",  sub: "buried head",  rar: "mythic", chars: 29400, val: 2295, tint: "#ece7dc", cap: "it was here before the sand.", styles: true },
  { no: "039", id: "leviathan", name: "Leviathan", sub: "sky whale",    rar: "mythic", chars: 30912, val: 4036, tint: "#8ad8ff", cap: "the sky has tides too.",       styles: true },
  { no: "040", id: "titan",     name: "Titan",     sub: "storm giant",  rar: "cosmic", chars: 72600, val: 33900, tint: "#e6ecff", cap: "it knelt first.",              styles: true },
  { no: "041", set: "ms", id: "console", name: "Console", sub: "mission control", rar: "epic", chars: 11008, val: 402, tint: "#9fc4ff", cap: "all stations: go.",     styles: true },
  { no: "042", set: "ms", id: "suit",    name: "Suit",    sub: "suit up",         rar: "mythic", chars: 10416, val: 4020, tint: "#ece7dc", cap: "one size fits nobody.", styles: true },
  { no: "043", set: "ms", id: "mars",    name: "Mars",    sub: "second flag",   rar: "secret", chars: 117600, val: 250000,  tint: "#ffb08a", cap: "second flag. first footprint.",     styles: true },
  { no: "044", set: "ms", id: "horizon", name: "Horizon", sub: "event horizon", rar: "secret",   chars: 179920, val: 225000, tint: "#e8e6ff", cap: "nothing leaves. you looked anyway.", styles: true },
  // generated cards: drawn in code (design-concepts/stick-cards), the new paintings that read well as text
  { no: "160", set: "ms", id: "vigil", name: "Vigil", sub: "glyph scene", rar: "rare", chars: 9800, val: 302, tint: "#ffb866", cap: "it holds the light so you can see.", styles: false },
  { no: "062", set: "ms", id: "ms062", name: "Weather Balloon", sub: "cyan painting", rar: "common", chars: 6432, val: 25, tint: "#9fc8fd", cap: "goes up to look. never comes back.", styles: false },
  { no: "068", set: "ms", id: "ms068", name: "Ground Control", sub: "glitch painting", rar: "uncommon", chars: 7260, val: 60, tint: "#a8b1fd", cap: "the quiet ones keep everyone alive.", styles: false },
  { no: "161", set: "ec", id: "lightwriter", name: "Light Writer", sub: "glyph scene", rar: "mythic", chars: 40320, val: 2510, tint: "#ff7ad0", cap: "writes in the air. gone in a second.", styles: false },
  { no: "081", set: "ec", id: "ec081", name: "Corona", sub: "lino painting", rar: "mythic", chars: 40320, val: 3020, tint: "#e0ecfd", cap: "a crown the Moon steals for a minute.", styles: false },
  { no: "069", set: "ms", id: "ms069", name: "Eagle", sub: "lino painting", rar: "legendary", chars: 29400, val: 1515, tint: "#fdfbf8", cap: "a landing so slow it felt like waiting.", styles: false },
  { no: "085", set: "ec", id: "ec085", name: "Black Bell", sub: "rust painting", rar: "exotic", chars: 52000, val: 5280, tint: "#fdc194", cap: "rings once per eclipse.", styles: false },
  { no: "074", set: "ms", id: "ms074", name: "Eclipse Over Tranquility", sub: "fire painting", rar: "celestial", chars: 100000, val: 13072, tint: "#e4d6fc", cap: "even the Moon needs a night off.", styles: false },
  { no: "163", set: "sg", id: "morpho", name: "Morpho", sub: "glyph scene", rar: "celestial", chars: 100000, val: 16672, tint: "#4fd0ff", cap: "grew wings. forgot how to land.", styles: false },
  { no: "162", set: "td", id: "heartstring", name: "Heartstring", sub: "glyph scene", rar: "divine", chars: 72000, val: 7575, tint: "#ff6b8f", cap: "it floats as long as you hold on.", styles: false },
  { no: "164", set: "sg", id: "phoenix", name: "Phoenix", sub: "glyph scene", rar: "eternal", chars: 220000, val: 41250, tint: "#ff7a1f", cap: "burns out. comes back rarer.", styles: false },
];
// the sets: the two letters a copy id starts with, and what the set is called
const SETS = { fp: { code: "IS", name: "First Print" }, ms: { code: "MS", name: "Moonshot" }, ec: { code: "EC", name: "Eclipse" }, td: { code: "TD", name: "Tidal" }, sg: { code: "SG", name: "Singularity" } };
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
  // Five packs that share the twelve commons as fillers (cards 1 to 4, 6 and 7); card 5 is the rare slot, a window on the ladder of rare cards
  // that starts higher up in the dearer packs. A dearer pack's rare slot starts higher up the ladder. Every pack returns 94.7% on average.
  { id: "fp", name: "First Print", blurb: "Stick figures made of text. Seven cards a pack, and the fifth is the one you open it for. Cards from $0.10 to $20.", price: 500, min: 500, max: 500, edges: [0.1, 0.2, 0.5, 0.6, 0.8, 1.0, 20], n: 7, col: "#3be477", scene: "print",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 7 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slotsBy: {
      normal: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["tempest", 31.3], ["surge", 18.7], ["ignition", 19.2], ["vigil", 19], ["console", 7], ["phantom", 3.15023], ["booster", 1.64977]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["tempest", 0], ["surge", 0], ["ignition", 0], ["vigil", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["tempest", 0], ["surge", 0], ["ignition", 0], ["vigil", 0]]],
      high: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["tempest", 39.8], ["surge", 40.2], ["ignition", 2.6], ["vigil", 4], ["console", 2.8], ["phantom", 8.73995], ["booster", 1.96005]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["tempest", 0], ["surge", 0], ["ignition", 0], ["vigil", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["tempest", 0], ["surge", 0], ["ignition", 0], ["vigil", 0]]],
      max: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["tempest", 46], ["surge", 36], ["ignition", 1.5], ["vigil", 2.5], ["console", 1.5], ["phantom", 10.5469], ["booster", 1.95307]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["tempest", 0], ["surge", 0], ["ignition", 0], ["vigil", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["tempest", 0], ["surge", 0], ["ignition", 0], ["vigil", 0]]]
    },
    get slots() { return this.slotsBy[packStyleOf(this.id)]; } },
  { id: "ms", name: "Moonshot", blurb: "A launch: lit fuses, rockets, mission control and the Moon. Cards from $1 to $100.", price: 2500, min: 2500, max: 2500, edges: [1, 2, 5, 6, 8, 10, 100], n: 7, col: "#ffa046", scene: "launch",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 7 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slotsBy: {
      normal: [[["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["phantom", 31.3], ["kraken", 18.7], ["lightwriter", 19.2], ["ec081", 19], ["suit", 7], ["gantry", 4.05792], ["grimm", 0.74208]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615], ["phantom", 0], ["kraken", 0], ["lightwriter", 0], ["ec081", 0]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615], ["phantom", 0], ["kraken", 0], ["lightwriter", 0], ["ec081", 0]]],
      high: [[["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["phantom", 39.8], ["kraken", 40.2], ["lightwriter", 2.6], ["ec081", 4], ["suit", 2.8], ["gantry", 9.13478], ["grimm", 1.56522]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615], ["phantom", 0], ["kraken", 0], ["lightwriter", 0], ["ec081", 0]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615], ["phantom", 0], ["kraken", 0], ["lightwriter", 0], ["ec081", 0]]],
      max: [[["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615]],
        [["phantom", 46], ["kraken", 36], ["lightwriter", 1.5], ["ec081", 2.5], ["suit", 1.5], ["gantry", 10.8856], ["grimm", 1.61444]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615], ["phantom", 0], ["kraken", 0], ["lightwriter", 0], ["ec081", 0]],
        [["stitch", 7.69231], ["brick", 7.69231], ["orbit", 7.69231], ["rook", 7.69231], ["mop", 7.69231], ["pan", 7.69231], ["cone", 7.69231], ["fuse", 7.69231], ["countdown", 7.69231], ["spark", 7.69231], ["flare", 7.69231], ["bubble", 7.69231], ["ms062", 3.84615], ["ms068", 3.84615], ["phantom", 0], ["kraken", 0], ["lightwriter", 0], ["ec081", 0]]]
    },
    get slots() { return this.slotsBy[packStyleOf(this.id)]; } },
  { id: "ec", name: "Eclipse", blurb: "Cards from under a black sun. Cards from $3 to $200.", price: 5000, min: 5000, max: 5000, edges: [3.0, 4.5, 9.0, 10.5, 13.5, 16.5, 200], n: 7, col: "#ffc24a", scene: "eclipse",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 7 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slotsBy: {
      normal: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["ms069", 31.3], ["colossus", 18.7], ["gantry", 19.2], ["ec085", 19], ["liftoff", 7], ["null", 3.69771], ["reaper", 1.10229]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["ms069", 0], ["colossus", 0], ["gantry", 0], ["ec085", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["ms069", 0], ["colossus", 0], ["gantry", 0], ["ec085", 0]]],
      high: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["ms069", 39.8], ["colossus", 40.2], ["gantry", 2.6], ["ec085", 4], ["liftoff", 2.8], ["null", 8.7979], ["reaper", 1.9021]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["ms069", 0], ["colossus", 0], ["gantry", 0], ["ec085", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["ms069", 0], ["colossus", 0], ["gantry", 0], ["ec085", 0]]],
      max: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["ms069", 46], ["colossus", 36], ["gantry", 1.5], ["ec085", 2.5], ["liftoff", 1.5], ["null", 10.5181], ["reaper", 1.98193]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["ms069", 0], ["colossus", 0], ["gantry", 0], ["ec085", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["ms069", 0], ["colossus", 0], ["gantry", 0], ["ec085", 0]]]
    },
    get slots() { return this.slotsBy[packStyleOf(this.id)]; } },
  { id: "td", name: "Tidal", blurb: "The big names. Cards from $8 to $500.", price: 12500, min: 12500, max: 12500, edges: [8.0, 11.6, 22.4, 26.0, 33.2, 40.4, 500], n: 7, col: "#46d2ff", scene: "tidal",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 7 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slotsBy: {
      normal: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["leviathan", 31.3], ["null", 18.7], ["shogun", 19.2], ["ms074", 19], ["morpho", 7], ["apogee", 3.7277], ["mars", 1.0723]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["leviathan", 0], ["null", 0], ["shogun", 0], ["ms074", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["leviathan", 0], ["null", 0], ["shogun", 0], ["ms074", 0]]],
      high: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["leviathan", 39.8], ["null", 40.2], ["shogun", 2.6], ["ms074", 4], ["morpho", 2.8], ["apogee", 9.21285], ["mars", 1.48715]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["leviathan", 0], ["null", 0], ["shogun", 0], ["ms074", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["leviathan", 0], ["null", 0], ["shogun", 0], ["ms074", 0]]],
      max: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["leviathan", 46], ["null", 36], ["shogun", 1.5], ["ms074", 2.5], ["morpho", 1.5], ["apogee", 10.9194], ["mars", 1.58055]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["leviathan", 0], ["null", 0], ["shogun", 0], ["ms074", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["leviathan", 0], ["null", 0], ["shogun", 0], ["ms074", 0]]]
    },
    get slots() { return this.slotsBy[packStyleOf(this.id)]; } },
  { id: "sg", name: "Singularity", blurb: "The edge of the dark. Cards from $15 to $1,000.", price: 25000, min: 25000, max: 25000, edges: [15.0, 22.5, 45.0, 52.5, 67.5, 82.5, 1000], n: 7, col: "#b78cff", scene: "void",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 7 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slotsBy: {
      normal: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["heartstring", 31.3], ["apogee", 18.7], ["ronin", 19.2], ["luna", 19], ["titan", 7], ["phoenix", 3.92353], ["umbra", 0.87647]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["heartstring", 0], ["apogee", 0], ["ronin", 0], ["luna", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["heartstring", 0], ["apogee", 0], ["ronin", 0], ["luna", 0]]],
      high: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["heartstring", 39.8], ["apogee", 40.2], ["ronin", 2.6], ["luna", 4], ["titan", 2.8], ["phoenix", 9.38015], ["umbra", 1.31985]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["heartstring", 0], ["apogee", 0], ["ronin", 0], ["luna", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["heartstring", 0], ["apogee", 0], ["ronin", 0], ["luna", 0]]],
      max: [[["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333]],
        [["heartstring", 46], ["apogee", 36], ["ronin", 1.5], ["luna", 2.5], ["titan", 1.5], ["phoenix", 11.0023], ["umbra", 1.49769]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["heartstring", 0], ["apogee", 0], ["ronin", 0], ["luna", 0]],
        [["stitch", 8.33333], ["brick", 8.33333], ["orbit", 8.33333], ["rook", 8.33333], ["mop", 8.33333], ["pan", 8.33333], ["cone", 8.33333], ["fuse", 8.33333], ["countdown", 8.33333], ["spark", 8.33333], ["flare", 8.33333], ["bubble", 8.33333], ["heartstring", 0], ["apogee", 0], ["ronin", 0], ["luna", 0]]]
    },
    get slots() { return this.slotsBy[packStyleOf(this.id)]; } }
];
const RARE_SLOT = 4;                                                                         // the card you look forward to: the fifth of seven
// a pack has three styles, each with its own exactly solved odds: Normal, High (bigger swings, more weight on the top cards) and Max (the top cards at their likeliest, no small fillers).
// Every style returns 94.7% on average. The style you picked for a pack is kept in your save; `slots` is always the one in use.
const packStyleOf = id => { try { return (state.styles && state.styles[id]) || "normal"; } catch (e) { return "normal"; } };
const inPack = (pk, c) => pk.slotsBy.normal.some(sl => sl.some(([id]) => id === c.id));
// A card that no pack holds is retired; every card is in a pack now.
CARDS.forEach(c => { c.retired = !PACKS.some(pk => inPack(pk, c)); });
const LIVE = CARDS.filter(c => !c.retired);
const PACK_BY = Object.fromEntries(PACKS.map(p => [p.id, p]));
// Play money is counted in units: 500 of them are one dollar, so a unit is a fifth of a cent. The packs cost $1, $3, $8, $20 and $50. You start with $10.
const SELLBACK = .9, START = 5000, UNIT = 500;
