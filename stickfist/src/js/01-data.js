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
  { no: "001", id: "stitch",  name: "Stitch",  sub: "frog hat",   rar: "uncommon",  chars: 6432,   val: 15,    tint: "#ece7dc", cap: "frog hat. zero regrets.",       styles: true },
  { no: "003", id: "brick",   name: "Brick",   sub: "colander",   rar: "uncommon",  chars: 6432,   val: 15,    tint: "#a8ffbe", cap: "it is a colander. it works.", styles: true },
  { no: "004", id: "rook",    name: "Rook",    sub: "pool noodle", rar: "common", chars: 6432,   val: 15,    tint: "#a8ffbe", cap: "reach: floppy.", styles: true },
  { no: "012", id: "orbit",   name: "Orbit",   sub: "galaxy",     rar: "uncommon",  chars: 7260,   val: 20,    tint: "#a9c9ff", cap: "already read the ending.", styles: true },
  { no: "019", id: "phantom", name: "Phantom", sub: "wings",      rar: "epic",  chars: 15750,  val: 350,    tint: "#ece7dc", cap: "gone before the cape lands.", styles: true },
  { no: "018", id: "null",    name: "Null",    sub: "star",       rar: "exotic",      chars: 29260,  val: 3250,   tint: "#a9c9ff", cap: "not on any record.", styles: true },
  { no: "017", id: "shogun",  name: "Shogun",  sub: "gold wings", rar: "divine",      chars: 31970,  val: 5500,   tint: "#ffd27a", cap: "rents you the air.", styles: true },
  { no: "006", id: "ronin",   name: "Ronin",   sub: "cliff",      rar: "celestial",      chars: 71680,  val: 8500,   tint: "#ff8ac9", cap: "", styles: true },
  { no: "011", id: "grimm",   name: "Grimm",   sub: "cathedral",  rar: "eternal", chars: 219520, val: 30000,  tint: "#a8ffb0", cap: "", styles: true },
  { no: "015", id: "reaper",  name: "Reaper",  sub: "ember",      rar: "ascended",    chars: 701000, val: 55000, tint: "#ffc87a", cap: "", styles: true },
  { no: "020", id: "umbra",   name: "Umbra",   sub: "eclipse",    rar: "secret",    chars: 1578000, val: 110000, tint: "#ffb54a", cap: "the sun blinked first.", styles: true },
  // ---- more First Print cards (same worth as the card each one shares a rarity with, so what a pack returns and how often it pays are unchanged; they only make the packs less repetitive)
  { no: "026", id: "mop",     name: "Mop",     sub: "bucket helmet", rar: "common", chars: 6432,  val: 15,  tint: "#a8ffbe", cap: "swab the deck.",              styles: true },
  { no: "027", id: "pan",     name: "Pan",     sub: "frying pan",    rar: "common", chars: 6432,  val: 20,  tint: "#ece7dc", cap: "it's a frying pan. it counts.", styles: true },
  { no: "028", id: "cone",    name: "Cone",    sub: "traffic cone",  rar: "common", chars: 6432,  val: 20,  tint: "#ffd27a", cap: "caution: confident.",         styles: true },
  { no: "029", id: "tempest", name: "Tempest", sub: "storm",         rar: "rare", chars: 7260,  val: 150,  tint: "#a9c9ff", cap: "weather is a choice.",         styles: true },
  { no: "030", id: "surge",   name: "Surge",   sub: "big wave",      rar: "rare", chars: 15750, val: 175,  tint: "#9fe8ff", cap: "ride it before it breaks.",    styles: true },
  { no: "031", id: "kraken",  name: "Kraken",  sub: "tentacles",     rar: "epic",     chars: 28000, val: 450, tint: "#9fe8d8", cap: "it was always down there.",    styles: true },
  // ---- Moonshot: one launch, five altitudes. The higher the card, the rarer it is.
  { no: "021", set: "ms", id: "fuse",     name: "Fuse",     sub: "match",         rar: "uncommon",  chars: 8736,   val: 20,   tint: "#ffd27a", cap: "light it and walk away.",       styles: true },
  { no: "022", set: "ms", id: "ignition", name: "Ignition", sub: "launch pad",    rar: "rare",  chars: 10080,  val: 200,   tint: "#ffb070", cap: "no turning back from here.",     styles: true },
  { no: "023", set: "ms", id: "liftoff",  name: "Liftoff",  sub: "plume",         rar: "mythic",      chars: 40320,  val:  2200,  tint: "#ffb070", cap: "gravity lost the argument.",    styles: true },
  { no: "024", set: "ms", id: "apogee",   name: "Apogee",   sub: "edge of space", rar: "divine",      chars: 123480, val: 6500, tint: "#7ee8ff", cap: "the top is quiet.",            styles: true },
  { no: "025", set: "ms", id: "luna",     name: "Luna",     sub: "first flag",    rar: "celestial", chars: 448800, val: 11000, tint: "#b8d4ff", cap: "to the moon was never a joke.", styles: true },
  // ---- more Moonshot cards, each at the altitude (and worth) of a card already there
  { no: "032", set: "ms", id: "spark",     name: "Spark",     sub: "sparkler",     rar: "common", chars: 8736,   val: 25,   tint: "#ffb070", cap: "small things start fires.", styles: true },
  { no: "033", set: "ms", id: "countdown", name: "Countdown", sub: "launch button", rar: "uncommon", chars: 10080,  val: 25,   tint: "#ff8a7a", cap: "three. two. one.",           styles: true },
  { no: "034", set: "ms", id: "booster",   name: "Booster",   sub: "stage split",  rar: "exotic",     chars: 40320,  val:  4000, tint: "#ffc98a", cap: "dead weight, dropped.",      styles: true },
  { no: "035", set: "ms", id: "flare",     name: "Flare",     sub: "signal flare", rar: "common", chars: 8736,   val: 25,   tint: "#ff8a7a", cap: "the sky has been told.",     styles: true },
  { no: "036", set: "ms", id: "bubble",    name: "Bubble",    sub: "fishbowl helmet", rar: "common", chars: 8736,  val: 30,   tint: "#ece7dc", cap: "all systems: smiling.",      styles: true },
  { no: "037", set: "ms", id: "gantry",    name: "Gantry",    sub: "tower arm",    rar: "legendary", chars: 10080,  val: 1100,   tint: "#9fe8ff", cap: "the arm lets go.",           styles: true }
  ,
  // ---- new designs (2026-11)
  { no: "038", id: "colossus",  name: "Colossus",  sub: "buried head",  rar: "legendary", chars: 29400, val: 800, tint: "#ece7dc", cap: "it was here before the sand.", styles: true },
  { no: "039", id: "leviathan", name: "Leviathan", sub: "sky whale",    rar: "mythic", chars: 30912, val: 1600, tint: "#8ad8ff", cap: "the sky has tides too.",       styles: true },
  { no: "040", id: "titan",     name: "Titan",     sub: "storm giant",  rar: "cosmic", chars: 72600, val: 19000, tint: "#e6ecff", cap: "it knelt first.",              styles: true },
  { no: "041", set: "ms", id: "console", name: "Console", sub: "mission control", rar: "rare", chars: 11008, val: 225, tint: "#9fc4ff", cap: "all stations: go.",     styles: true },
  { no: "042", set: "ms", id: "suit",    name: "Suit",    sub: "suit up",         rar: "epic", chars: 10416, val: 600, tint: "#ece7dc", cap: "one size fits nobody.", styles: true },
  { no: "043", set: "ms", id: "mars",    name: "Mars",    sub: "second flag",   rar: "ascended", chars: 117600, val: 75000,  tint: "#ffb08a", cap: "second flag. first footprint.",     styles: true },
  { no: "044", set: "ms", id: "horizon", name: "Horizon", sub: "event horizon", rar: "secret",   chars: 179920, val: 225000, tint: "#e8e6ff", cap: "nothing leaves. you looked anyway.", styles: true }
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
  // Five packs, cheap to dear, of seven cards each, the way a real pack is: cards 1 to 4 are commons, card 5 is the rare slot (a rare or
  // better, and the card you open a pack for), cards 6 and 7 are mostly commons with a chance of a rare. A dearer pack starts its rare slot
  // higher up the ladder, so its worst rare is worth more and its best is worth a great deal. Every pack returns 94.7% on average.
  { id: "fp", name: "First Print", blurb: "The first run: stick figures printed in text. Seven cards, one rare or better in the middle.", price: 500, min: 500, max: 500, n: 7, col: "#3be477", scene: "print",
    slotNames: ["Cards 1 to 4: commons", "Card 5: the rare slot, a rare or better", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["tempest", 32.1329], ["surge", 21.822], ["ignition", 14.8197], ["console", 10.0643], ["phantom", 6.8349], ["kraken", 4.6417], ["suit", 3.1523], ["colossus", 2.1408], ["gantry", 1.4538], ["leviathan", 0.9873], ["liftoff", 0.6705], ["null", 0.4554], ["booster", 0.3092], ["shogun", 0.21], ["apogee", 0.1426], ["ronin", 0.0969], ["luna", 0.0658]],
      [["stitch", 9.8133], ["brick", 9.8133], ["orbit", 9.8133], ["rook", 9.8133], ["mop", 9.8133], ["pan", 6.1333], ["cone", 6.1333], ["fuse", 6.1333], ["countdown", 6.1333], ["spark", 6.1333], ["flare", 6.1333], ["bubble", 6.1333], ["tempest", 2], ["surge", 2], ["ignition", 2], ["console", 2]],
      [["stitch", 9.8133], ["brick", 9.8133], ["orbit", 9.8133], ["rook", 9.8133], ["mop", 9.8133], ["pan", 6.1333], ["cone", 6.1333], ["fuse", 6.1333], ["countdown", 6.1333], ["spark", 6.1333], ["flare", 6.1333], ["bubble", 6.1333], ["tempest", 2], ["surge", 2], ["ignition", 2], ["console", 2]]
    ] },
  { id: "ms", name: "Moonshot", blurb: "A launch in seven cards: the rare slot climbs from storms to rockets and the Moon.", price: 1500, min: 1500, max: 1500, n: 7, col: "#ffa046", scene: "launch",
    slotNames: ["Cards 1 to 4: commons", "Card 5: the rare slot, a rare or better", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["surge", 17.6113], ["ignition", 14.6445], ["console", 12.1775], ["phantom", 10.1261], ["kraken", 8.4202], ["suit", 7.0017], ["colossus", 5.8222], ["gantry", 4.8414], ["leviathan", 4.0258], ["liftoff", 3.3476], ["null", 2.7837], ["booster", 2.3147], ["shogun", 1.9248], ["apogee", 1.6005], ["ronin", 1.3309], ["luna", 1.1067], ["titan", 0.9203]],
      [["stitch", 9.1733], ["brick", 9.1733], ["orbit", 9.1733], ["rook", 9.1733], ["mop", 9.1733], ["pan", 5.7333], ["cone", 5.7333], ["fuse", 5.7333], ["countdown", 5.7333], ["spark", 5.7333], ["flare", 5.7333], ["bubble", 5.7333], ["tempest", 2.8], ["surge", 2.8], ["ignition", 2.8], ["console", 2.8], ["phantom", 2.8]],
      [["stitch", 9.1733], ["brick", 9.1733], ["orbit", 9.1733], ["rook", 9.1733], ["mop", 9.1733], ["pan", 5.7333], ["cone", 5.7333], ["fuse", 5.7333], ["countdown", 5.7333], ["spark", 5.7333], ["flare", 5.7333], ["bubble", 5.7333], ["tempest", 2.8], ["surge", 2.8], ["ignition", 2.8], ["console", 2.8], ["phantom", 2.8]]
    ] },
  { id: "ec", name: "Eclipse", blurb: "The sun goes dark and the rare slot gets serious: legendaries are one pack in ten.", price: 4000, min: 4000, max: 4000, n: 7, col: "#ffc24a", scene: "eclipse",
    slotNames: ["Cards 1 to 4: commons", "Card 5: the rare slot, a rare or better", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["phantom", 13.2987], ["kraken", 11.8396], ["suit", 10.5405], ["colossus", 9.3839], ["gantry", 8.3543], ["leviathan", 7.4376], ["liftoff", 6.6216], ["null", 5.895], ["booster", 5.2482], ["shogun", 4.6723], ["apogee", 4.1597], ["ronin", 3.7033], ["luna", 3.2969], ["titan", 2.9352], ["grimm", 2.6131]],
      [["stitch", 8.5333], ["brick", 8.5333], ["orbit", 8.5333], ["rook", 8.5333], ["mop", 8.5333], ["pan", 5.3333], ["cone", 5.3333], ["fuse", 5.3333], ["countdown", 5.3333], ["spark", 5.3333], ["flare", 5.3333], ["bubble", 5.3333], ["ignition", 5], ["console", 5], ["phantom", 5], ["kraken", 5]],
      [["stitch", 8.5333], ["brick", 8.5333], ["orbit", 8.5333], ["rook", 8.5333], ["mop", 8.5333], ["pan", 5.3333], ["cone", 5.3333], ["fuse", 5.3333], ["countdown", 5.3333], ["spark", 5.3333], ["flare", 5.3333], ["bubble", 5.3333], ["ignition", 5], ["console", 5], ["phantom", 5], ["kraken", 5]]
    ] },
  { id: "td", name: "Tidal", blurb: "Deep water. Every rare slot is a legendary or better, up to the secret cards.", price: 10000, min: 10000, max: 10000, n: 7, col: "#46d2ff", scene: "tidal",
    slotNames: ["Cards 1 to 4: commons", "Card 5: the rare slot, a rare or better", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["suit", 14.1929], ["colossus", 12.4153], ["gantry", 10.8603], ["leviathan", 9.5001], ["liftoff", 8.3102], ["null", 7.2694], ["booster", 6.3589], ["shogun", 5.5625], ["apogee", 4.8658], ["ronin", 4.2564], ["luna", 3.7233], ["titan", 3.2569], ["grimm", 2.849], ["reaper", 2.4922], ["mars", 2.18], ["umbra", 1.907]],
      [["stitch", 7.68], ["brick", 7.68], ["orbit", 7.68], ["rook", 7.68], ["mop", 7.68], ["pan", 4.8], ["cone", 4.8], ["fuse", 4.8], ["countdown", 4.8], ["spark", 4.8], ["flare", 4.8], ["bubble", 4.8], ["console", 7], ["phantom", 7], ["kraken", 7], ["suit", 7]],
      [["stitch", 7.68], ["brick", 7.68], ["orbit", 7.68], ["rook", 7.68], ["mop", 7.68], ["pan", 4.8], ["cone", 4.8], ["fuse", 4.8], ["countdown", 4.8], ["spark", 4.8], ["flare", 4.8], ["bubble", 4.8], ["console", 7], ["phantom", 7], ["kraken", 7], ["suit", 7]]
    ] },
  { id: "sg", name: "Singularity", blurb: "The top shelf: nothing in the rare slot is worth less than a pack, and the biggest cards live here.", price: 25000, min: 25000, max: 25000, n: 7, col: "#b78cff", scene: "void",
    slotNames: ["Cards 1 to 4: commons", "Card 5: the rare slot, a rare or better", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["stitch", 1.6], ["brick", 1.6], ["orbit", 1.6], ["rook", 1.6], ["mop", 1.6], ["pan", 1], ["cone", 1], ["fuse", 1], ["countdown", 1], ["spark", 1], ["flare", 1], ["bubble", 1]],
      [["liftoff", 14.9737], ["null", 13.1432], ["booster", 11.5365], ["shogun", 10.1262], ["apogee", 8.8883], ["ronin", 7.8017], ["luna", 6.848], ["titan", 6.0108], ["grimm", 5.276], ["reaper", 4.631], ["mars", 4.0649], ["umbra", 3.568], ["horizon", 3.1318]],
      [["stitch", 6.6133], ["brick", 6.6133], ["orbit", 6.6133], ["rook", 6.6133], ["mop", 6.6133], ["pan", 4.1333], ["cone", 4.1333], ["fuse", 4.1333], ["countdown", 4.1333], ["spark", 4.1333], ["flare", 4.1333], ["bubble", 4.1333], ["phantom", 9.5], ["kraken", 9.5], ["suit", 9.5], ["colossus", 9.5]],
      [["stitch", 6.6133], ["brick", 6.6133], ["orbit", 6.6133], ["rook", 6.6133], ["mop", 6.6133], ["pan", 4.1333], ["cone", 4.1333], ["fuse", 4.1333], ["countdown", 4.1333], ["spark", 4.1333], ["flare", 4.1333], ["bubble", 4.1333], ["phantom", 9.5], ["kraken", 9.5], ["suit", 9.5], ["colossus", 9.5]]
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
