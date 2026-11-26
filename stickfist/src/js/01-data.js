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
  { no: "019", id: "phantom", name: "Phantom", sub: "wings",      rar: "epic",  chars: 15750,  val: 350,    tint: "#ece7dc", cap: "gone before the cape lands.", styles: true },
  { no: "018", id: "null",    name: "Null",    sub: "star",       rar: "mythic",      chars: 29260,  val: 3250,   tint: "#a9c9ff", cap: "not on any record.", styles: true },
  { no: "017", id: "shogun",  name: "Shogun",  sub: "gold wings", rar: "exotic",      chars: 31970,  val: 5500,   tint: "#ffd27a", cap: "rents you the air.", styles: true },
  { no: "006", id: "ronin",   name: "Ronin",   sub: "cliff",      rar: "divine",      chars: 71680,  val: 8500,   tint: "#ff8ac9", cap: "", styles: true },
  { no: "011", id: "grimm",   name: "Grimm",   sub: "cathedral",  rar: "cosmic", chars: 219520, val: 30000,  tint: "#a8ffb0", cap: "", styles: true },
  { no: "015", id: "reaper",  name: "Reaper",  sub: "ember",      rar: "eternal",    chars: 701000, val: 55000, tint: "#ffc87a", cap: "", styles: true },
  { no: "020", id: "umbra",   name: "Umbra",   sub: "eclipse",    rar: "ascended",    chars: 1578000, val: 110000, tint: "#ffb54a", cap: "the sun blinked first.", styles: true },
  // ---- more First Print cards (same worth as the card each one shares a rarity with, so what a pack returns and how often it pays are unchanged; they only make the packs less repetitive)
  { no: "026", id: "mop",     name: "Mop",     sub: "bucket helmet", rar: "common", chars: 6432,  val: 15,  tint: "#a8ffbe", cap: "swab the deck.",              styles: true },
  { no: "027", id: "pan",     name: "Pan",     sub: "frying pan",    rar: "common", chars: 6432,  val: 20,  tint: "#ece7dc", cap: "it's a frying pan. it counts.", styles: true },
  { no: "028", id: "cone",    name: "Cone",    sub: "traffic cone",  rar: "common", chars: 6432,  val: 20,  tint: "#ffd27a", cap: "caution: confident.",         styles: true },
  { no: "029", id: "tempest", name: "Tempest", sub: "storm",         rar: "rare", chars: 7260,  val: 150,  tint: "#a9c9ff", cap: "weather is a choice.",         styles: true },
  { no: "030", id: "surge",   name: "Surge",   sub: "big wave",      rar: "rare", chars: 15750, val: 175,  tint: "#9fe8ff", cap: "ride it before it breaks.",    styles: true },
  { no: "031", id: "kraken",  name: "Kraken",  sub: "tentacles",     rar: "epic",     chars: 28000, val: 450, tint: "#9fe8d8", cap: "it was always down there.",    styles: true },
  // ---- Moonshot: one launch, five altitudes. The higher the card, the rarer it is.
  { no: "021", set: "ms", id: "fuse",     name: "Fuse",     sub: "match",         rar: "common",  chars: 8736,   val: 20,   tint: "#ffd27a", cap: "light it and walk away.",       styles: true },
  { no: "022", set: "ms", id: "ignition", name: "Ignition", sub: "launch pad",    rar: "rare",  chars: 10080,  val: 200,   tint: "#ffb070", cap: "no turning back from here.",     styles: true },
  { no: "023", set: "ms", id: "liftoff",  name: "Liftoff",  sub: "plume",         rar: "legendary",      chars: 40320,  val:  2200,  tint: "#ffb070", cap: "gravity lost the argument.",    styles: true },
  { no: "024", set: "ms", id: "apogee",   name: "Apogee",   sub: "edge of space", rar: "exotic",      chars: 123480, val: 6500, tint: "#7ee8ff", cap: "the top is quiet.",            styles: true },
  { no: "025", set: "ms", id: "luna",     name: "Luna",     sub: "first flag",    rar: "divine", chars: 448800, val: 11000, tint: "#b8d4ff", cap: "to the moon was never a joke.", styles: true },
  // ---- more Moonshot cards, each at the altitude (and worth) of a card already there
  { no: "032", set: "ms", id: "spark",     name: "Spark",     sub: "sparkler",     rar: "common", chars: 8736,   val: 25,   tint: "#ffb070", cap: "small things start fires.", styles: true },
  { no: "033", set: "ms", id: "countdown", name: "Countdown", sub: "launch button", rar: "common", chars: 10080,  val: 25,   tint: "#ff8a7a", cap: "three. two. one.",           styles: true },
  { no: "034", set: "ms", id: "booster",   name: "Booster",   sub: "stage split",  rar: "mythic",     chars: 40320,  val:  4000, tint: "#ffc98a", cap: "dead weight, dropped.",      styles: true },
  { no: "035", set: "ms", id: "flare",     name: "Flare",     sub: "signal flare", rar: "common", chars: 8736,   val: 25,   tint: "#ff8a7a", cap: "the sky has been told.",     styles: true },
  { no: "036", set: "ms", id: "bubble",    name: "Bubble",    sub: "fishbowl helmet", rar: "common", chars: 8736,  val: 30,   tint: "#ece7dc", cap: "all systems: smiling.",      styles: true },
  { no: "037", set: "ms", id: "gantry",    name: "Gantry",    sub: "tower arm",    rar: "legendary", chars: 10080,  val: 1100,   tint: "#9fe8ff", cap: "the arm lets go.",           styles: true }
  ,
  // ---- new designs (2026-11)
  { no: "038", id: "colossus",  name: "Colossus",  sub: "buried head",  rar: "legendary", chars: 29400, val: 800, tint: "#ece7dc", cap: "it was here before the sand.", styles: true },
  { no: "039", id: "leviathan", name: "Leviathan", sub: "sky whale",    rar: "legendary", chars: 30912, val: 1600, tint: "#8ad8ff", cap: "the sky has tides too.",       styles: true },
  { no: "040", id: "titan",     name: "Titan",     sub: "storm giant",  rar: "celestial", chars: 72600, val: 19000, tint: "#e6ecff", cap: "it knelt first.",              styles: true },
  { no: "041", set: "ms", id: "console", name: "Console", sub: "mission control", rar: "rare", chars: 11008, val: 225, tint: "#9fc4ff", cap: "all stations: go.",     styles: true },
  { no: "042", set: "ms", id: "suit",    name: "Suit",    sub: "suit up",         rar: "epic", chars: 10416, val: 600, tint: "#ece7dc", cap: "one size fits nobody.", styles: true },
  { no: "043", set: "ms", id: "mars",    name: "Mars",    sub: "second flag",   rar: "ascended", chars: 117600, val: 75000,  tint: "#ffb08a", cap: "second flag. first footprint.",     styles: true },
  { no: "044", set: "ms", id: "horizon", name: "Horizon", sub: "event horizon", rar: "secret",   chars: 179920, val: 225000, tint: "#e8e6ff", cap: "nothing leaves. you looked anyway.", styles: true },
  // generated cards: drawn in code (design-concepts/stick-cards), the new paintings that read well as text
  { no: "062", set: "ms", id: "ms062", name: "Weather Balloon", sub: "cyan painting", rar: "common", chars: 6432, val: 25, tint: "#9fc8fd", cap: "goes up to look. never comes back.", styles: false },
  { no: "068", set: "ms", id: "ms068", name: "Ground Control", sub: "glitch painting", rar: "uncommon", chars: 7260, val: 60, tint: "#a8b1fd", cap: "the quiet ones keep everyone alive.", styles: false },
  { no: "069", set: "ms", id: "ms069", name: "Eagle", sub: "lino painting", rar: "uncommon", chars: 7260, val: 70, tint: "#fdfbf8", cap: "a landing so slow it felt like waiting.", styles: false },
  { no: "074", set: "ms", id: "ms074", name: "Eclipse Over Tranquility", sub: "fire painting", rar: "epic", chars: 15750, val: 550, tint: "#e4d6fc", cap: "even the Moon needs a night off.", styles: false },
  { no: "081", set: "ec", id: "ec081", name: "Corona", sub: "lino painting", rar: "common", chars: 6432, val: 15, tint: "#e0ecfd", cap: "a crown the Moon steals for a minute.", styles: false },
  { no: "085", set: "ec", id: "ec085", name: "Black Bell", sub: "rust painting", rar: "common", chars: 6432, val: 20, tint: "#fdc194", cap: "rings once per eclipse.", styles: false },
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
  { id: "fp", name: "First Print", blurb: "Stick figures made of text, from a frog in a hat to a gantry. Seven cards a pack, and the fifth is the one you open it for.", price: 500, min: 500, max: 500, n: 7, col: "#3be477", scene: "print",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 10 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["tempest", 24.4803], ["surge", 18.9505], ["ignition", 14.6699], ["console", 11.3562], ["phantom", 8.791], ["kraken", 6.8053], ["suit", 5.2681], ["colossus", 4.0781], ["gantry", 3.1569], ["leviathan", 2.4438]],
      [["stitch", 7.6667], ["brick", 7.6667], ["orbit", 7.6667], ["rook", 7.6667], ["mop", 7.6667], ["pan", 7.6667], ["cone", 7.6667], ["fuse", 7.6667], ["countdown", 7.6667], ["spark", 7.6667], ["flare", 7.6667], ["bubble", 7.6667], ["tempest", 2], ["surge", 2], ["ignition", 2], ["console", 2]],
      [["stitch", 7.6667], ["brick", 7.6667], ["orbit", 7.6667], ["rook", 7.6667], ["mop", 7.6667], ["pan", 7.6667], ["cone", 7.6667], ["fuse", 7.6667], ["countdown", 7.6667], ["spark", 7.6667], ["flare", 7.6667], ["bubble", 7.6667], ["tempest", 2], ["surge", 2], ["ignition", 2], ["console", 2]]
    ] },
  { id: "ms", name: "Moonshot", blurb: "A launch: lit fuses, rockets, mission control and the Moon. The fifth card is the rare slot.", price: 1500, min: 1500, max: 1500, n: 7, col: "#ffa046", scene: "launch",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 9 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 7.1429], ["brick", 7.1429], ["orbit", 7.1429], ["rook", 7.1429], ["mop", 7.1429], ["pan", 7.1429], ["cone", 7.1429], ["fuse", 7.1429], ["countdown", 7.1429], ["spark", 7.1429], ["flare", 7.1429], ["bubble", 7.1429], ["ms062", 7.1429], ["ms068", 3.5714], ["ms069", 3.5714]],
      [["stitch", 7.1429], ["brick", 7.1429], ["orbit", 7.1429], ["rook", 7.1429], ["mop", 7.1429], ["pan", 7.1429], ["cone", 7.1429], ["fuse", 7.1429], ["countdown", 7.1429], ["spark", 7.1429], ["flare", 7.1429], ["bubble", 7.1429], ["ms062", 7.1429], ["ms068", 3.5714], ["ms069", 3.5714]],
      [["stitch", 7.1429], ["brick", 7.1429], ["orbit", 7.1429], ["rook", 7.1429], ["mop", 7.1429], ["pan", 7.1429], ["cone", 7.1429], ["fuse", 7.1429], ["countdown", 7.1429], ["spark", 7.1429], ["flare", 7.1429], ["bubble", 7.1429], ["ms062", 7.1429], ["ms068", 3.5714], ["ms069", 3.5714]],
      [["stitch", 7.1429], ["brick", 7.1429], ["orbit", 7.1429], ["rook", 7.1429], ["mop", 7.1429], ["pan", 7.1429], ["cone", 7.1429], ["fuse", 7.1429], ["countdown", 7.1429], ["spark", 7.1429], ["flare", 7.1429], ["bubble", 7.1429], ["ms062", 7.1429], ["ms068", 3.5714], ["ms069", 3.5714]],
      [["ms074", 31.566], ["suit", 21.9863], ["colossus", 15.3139], ["gantry", 10.6664], ["leviathan", 7.4294], ["liftoff", 5.1747], ["null", 3.6043], ["booster", 2.5104], ["shogun", 1.7486]],
      [["stitch", 6.1429], ["brick", 6.1429], ["orbit", 6.1429], ["rook", 6.1429], ["mop", 6.1429], ["pan", 6.1429], ["cone", 6.1429], ["fuse", 6.1429], ["countdown", 6.1429], ["spark", 6.1429], ["flare", 6.1429], ["bubble", 6.1429], ["ms062", 6.1429], ["ms068", 3.0714], ["ms069", 3.0714], ["ms074", 3.5], ["suit", 3.5], ["colossus", 3.5], ["gantry", 3.5]],
      [["stitch", 6.1429], ["brick", 6.1429], ["orbit", 6.1429], ["rook", 6.1429], ["mop", 6.1429], ["pan", 6.1429], ["cone", 6.1429], ["fuse", 6.1429], ["countdown", 6.1429], ["spark", 6.1429], ["flare", 6.1429], ["bubble", 6.1429], ["ms062", 6.1429], ["ms068", 3.0714], ["ms069", 3.0714], ["ms074", 3.5], ["suit", 3.5], ["colossus", 3.5], ["gantry", 3.5]]
    ] },
  { id: "ec", name: "Eclipse", blurb: "Cards from under a black sun. The rare slot starts at a mythic-class card.", price: 4000, min: 4000, max: 4000, n: 7, col: "#ffc24a", scene: "eclipse",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 8 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 7.1429], ["brick", 7.1429], ["orbit", 7.1429], ["rook", 7.1429], ["mop", 7.1429], ["pan", 7.1429], ["cone", 7.1429], ["fuse", 7.1429], ["countdown", 7.1429], ["spark", 7.1429], ["flare", 7.1429], ["bubble", 7.1429], ["ec081", 7.1429], ["ec085", 7.1429]],
      [["stitch", 7.1429], ["brick", 7.1429], ["orbit", 7.1429], ["rook", 7.1429], ["mop", 7.1429], ["pan", 7.1429], ["cone", 7.1429], ["fuse", 7.1429], ["countdown", 7.1429], ["spark", 7.1429], ["flare", 7.1429], ["bubble", 7.1429], ["ec081", 7.1429], ["ec085", 7.1429]],
      [["stitch", 7.1429], ["brick", 7.1429], ["orbit", 7.1429], ["rook", 7.1429], ["mop", 7.1429], ["pan", 7.1429], ["cone", 7.1429], ["fuse", 7.1429], ["countdown", 7.1429], ["spark", 7.1429], ["flare", 7.1429], ["bubble", 7.1429], ["ec081", 7.1429], ["ec085", 7.1429]],
      [["stitch", 7.1429], ["brick", 7.1429], ["orbit", 7.1429], ["rook", 7.1429], ["mop", 7.1429], ["pan", 7.1429], ["cone", 7.1429], ["fuse", 7.1429], ["countdown", 7.1429], ["spark", 7.1429], ["flare", 7.1429], ["bubble", 7.1429], ["ec081", 7.1429], ["ec085", 7.1429]],
      [["leviathan", 45.9632], ["liftoff", 24.9988], ["null", 13.5965], ["booster", 7.395], ["shogun", 4.022], ["apogee", 2.1875], ["ronin", 1.1898], ["luna", 0.6471]],
      [["stitch", 5.7143], ["brick", 5.7143], ["orbit", 5.7143], ["rook", 5.7143], ["mop", 5.7143], ["pan", 5.7143], ["cone", 5.7143], ["fuse", 5.7143], ["countdown", 5.7143], ["spark", 5.7143], ["flare", 5.7143], ["bubble", 5.7143], ["ec081", 5.7143], ["ec085", 5.7143], ["leviathan", 5], ["liftoff", 5], ["null", 5], ["booster", 5]],
      [["stitch", 5.7143], ["brick", 5.7143], ["orbit", 5.7143], ["rook", 5.7143], ["mop", 5.7143], ["pan", 5.7143], ["cone", 5.7143], ["fuse", 5.7143], ["countdown", 5.7143], ["spark", 5.7143], ["flare", 5.7143], ["bubble", 5.7143], ["ec081", 5.7143], ["ec085", 5.7143], ["leviathan", 5], ["liftoff", 5], ["null", 5], ["booster", 5]]
    ] },
  { id: "td", name: "Tidal", blurb: "The big names. The rare slot starts at a card worth as much as the pack.", price: 10000, min: 10000, max: 10000, n: 7, col: "#46d2ff", scene: "tidal",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 8 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["booster", 49.5826], ["shogun", 25.1044], ["apogee", 12.7108], ["ronin", 6.4357], ["luna", 3.2585], ["titan", 1.6498], ["grimm", 0.8353], ["reaper", 0.4229]],
      [["stitch", 6], ["brick", 6], ["orbit", 6], ["rook", 6], ["mop", 6], ["pan", 6], ["cone", 6], ["fuse", 6], ["countdown", 6], ["spark", 6], ["flare", 6], ["bubble", 6], ["booster", 7], ["shogun", 7], ["apogee", 7], ["ronin", 7]],
      [["stitch", 6], ["brick", 6], ["orbit", 6], ["rook", 6], ["mop", 6], ["pan", 6], ["cone", 6], ["fuse", 6], ["countdown", 6], ["spark", 6], ["flare", 6], ["bubble", 6], ["booster", 7], ["shogun", 7], ["apogee", 7], ["ronin", 7]]
    ] },
  { id: "sg", name: "Singularity", blurb: "The edge of the dark. The biggest cards in the game live here.", price: 25000, min: 25000, max: 25000, n: 7, col: "#b78cff", scene: "void",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of 8 cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["stitch", 8.3333], ["brick", 8.3333], ["orbit", 8.3333], ["rook", 8.3333], ["mop", 8.3333], ["pan", 8.3333], ["cone", 8.3333], ["fuse", 8.3333], ["countdown", 8.3333], ["spark", 8.3333], ["flare", 8.3333], ["bubble", 8.3333]],
      [["ronin", 70.675], ["luna", 20.7282], ["titan", 6.0793], ["grimm", 1.783], ["reaper", 0.5229], ["mars", 0.1534], ["umbra", 0.045], ["horizon", 0.0132]],
      [["stitch", 5.1667], ["brick", 5.1667], ["orbit", 5.1667], ["rook", 5.1667], ["mop", 5.1667], ["pan", 5.1667], ["cone", 5.1667], ["fuse", 5.1667], ["countdown", 5.1667], ["spark", 5.1667], ["flare", 5.1667], ["bubble", 5.1667], ["ronin", 9.5], ["luna", 9.5], ["titan", 9.5], ["grimm", 9.5]],
      [["stitch", 5.1667], ["brick", 5.1667], ["orbit", 5.1667], ["rook", 5.1667], ["mop", 5.1667], ["pan", 5.1667], ["cone", 5.1667], ["fuse", 5.1667], ["countdown", 5.1667], ["spark", 5.1667], ["flare", 5.1667], ["bubble", 5.1667], ["ronin", 9.5], ["luna", 9.5], ["titan", 9.5], ["grimm", 9.5]]
    ] }
];
const RARE_SLOT = 4;                                                                         // the card you look forward to: the fifth of seven
const inPack = (pk, c) => pk.slots.some(sl => sl.some(([id]) => id === c.id));
// A card that no pack holds is retired; every card is in a pack now.
CARDS.forEach(c => { c.retired = !PACKS.some(pk => inPack(pk, c)); });
const LIVE = CARDS.filter(c => !c.retired);
const PACK_BY = Object.fromEntries(PACKS.map(p => [p.id, p]));
// Play money is counted in units: 500 of them are one dollar, so a unit is a fifth of a cent. The packs cost $1, $3, $8, $20 and $50. You start with $10.
const SELLBACK = .9, START = 5000, UNIT = 500;
