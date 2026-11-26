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
  // generated cards: drawn in code (design-concepts/stick-cards), 115 of them, the fillers and the rare-slot cards of every pack
  { no: "045", set: "fp", id: "fp045", name: "Warden in the Rift", sub: "knight, rift", rar: "uncommon", chars: 7260, val: 40, tint: "#ffc0a5", cap: "something is leaving through the crack.", styles: false },
  { no: "046", set: "fp", id: "fp046", name: "Pilgrim of the Eclipse", sub: "robed, eclipse", rar: "uncommon", chars: 7260, val: 50, tint: "#ffe1a5", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "047", set: "fp", id: "fp047", name: "Hollow King at Moonrise", sub: "crowned, moon", rar: "uncommon", chars: 7260, val: 60, tint: "#a5e1ff", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "048", set: "fp", id: "fp048", name: "Gate at Moonrise", sub: "gate, moon", rar: "uncommon", chars: 7260, val: 70, tint: "#ffe1a5", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "049", set: "fp", id: "fp049", name: "Seraph at Moonrise", sub: "angel, moon", rar: "uncommon", chars: 7260, val: 85, tint: "#a5e1ff", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "050", set: "fp", id: "fp050", name: "Horned One in the Void", sub: "horned, void", rar: "uncommon", chars: 7260, val: 100, tint: "#ffc0a5", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "051", set: "fp", id: "fp051", name: "Monk in the Storm", sub: "monk, storm", rar: "rare", chars: 9800, val: 125, tint: "#a5e1ff", cap: "the weather answers to it.", styles: false },
  { no: "052", set: "fp", id: "fp052", name: "Hollow King at Sunburst", sub: "crowned, sunburst", rar: "rare", chars: 9800, val: 275, tint: "#ffc0a5", cap: "looks straight at it. does not blink.", styles: false },
  { no: "053", set: "fp", id: "fp053", name: "Mourner in the Rift", sub: "mourner, rift", rar: "legendary", chars: 29400, val: 1500, tint: "#ffe1a5", cap: "something is leaving through the crack.", styles: false },
  { no: "054", set: "ms", id: "ms054", name: "Pilgrim in Halo", sub: "robed, halo", rar: "common", chars: 6432, val: 10, tint: "#a5e1ff", cap: "no one asked it to be holy.", styles: false },
  { no: "055", set: "ms", id: "ms055", name: "Pilgrim at Sunburst", sub: "robed, sunburst", rar: "common", chars: 6432, val: 12, tint: "#a5fff7", cap: "looks straight at it. does not blink.", styles: false },
  { no: "056", set: "ms", id: "ms056", name: "Spire at Moonrise", sub: "tower, moon", rar: "common", chars: 6432, val: 15, tint: "#a5fff7", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "057", set: "ms", id: "ms057", name: "Gate of the Eclipse", sub: "gate, eclipse", rar: "common", chars: 6432, val: 15, tint: "#a5ffb4", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "058", set: "ms", id: "ms058", name: "Teeth of the Rings", sub: "spire, rings", rar: "common", chars: 6432, val: 18, tint: "#a5caff", cap: "each ring is a year it waited.", styles: false },
  { no: "059", set: "ms", id: "ms059", name: "Seraph of the Rings", sub: "angel, rings", rar: "common", chars: 6432, val: 20, tint: "#a5caff", cap: "each ring is a year it waited.", styles: false },
  { no: "060", set: "ms", id: "ms060", name: "Mourner in Halo", sub: "mourner, halo", rar: "common", chars: 6432, val: 20, tint: "#a5ffb4", cap: "no one asked it to be holy.", styles: false },
  { no: "061", set: "ms", id: "ms061", name: "Idol of the Rings", sub: "idol, rings", rar: "common", chars: 6432, val: 22, tint: "#a5caff", cap: "each ring is a year it waited.", styles: false },
  { no: "062", set: "ms", id: "ms062", name: "Pilgrim in Halo 2", sub: "robed, halo", rar: "common", chars: 6432, val: 25, tint: "#a5caff", cap: "no one asked it to be holy.", styles: false },
  { no: "063", set: "ms", id: "ms063", name: "Gate at Moonrise 2", sub: "gate, moon", rar: "common", chars: 6432, val: 25, tint: "#a5caff", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "064", set: "ms", id: "ms064", name: "Pilgrim in the Rift", sub: "robed, rift", rar: "common", chars: 6432, val: 28, tint: "#a5caff", cap: "something is leaving through the crack.", styles: false },
  { no: "065", set: "ms", id: "ms065", name: "Gate in the Rift", sub: "gate, rift", rar: "common", chars: 6432, val: 30, tint: "#a5caff", cap: "something is leaving through the crack.", styles: false },
  { no: "066", set: "ms", id: "ms066", name: "Seraph in Halo", sub: "angel, halo", rar: "uncommon", chars: 7260, val: 40, tint: "#a5e1ff", cap: "no one asked it to be holy.", styles: false },
  { no: "067", set: "ms", id: "ms067", name: "Warden in the Rift 2", sub: "knight, rift", rar: "uncommon", chars: 7260, val: 50, tint: "#a5fff7", cap: "something is leaving through the crack.", styles: false },
  { no: "068", set: "ms", id: "ms068", name: "Teeth in the Storm", sub: "spire, storm", rar: "uncommon", chars: 7260, val: 60, tint: "#a5e1ff", cap: "the weather answers to it.", styles: false },
  { no: "069", set: "ms", id: "ms069", name: "Seraph at Sunburst", sub: "angel, sunburst", rar: "uncommon", chars: 7260, val: 70, tint: "#a5e1ff", cap: "looks straight at it. does not blink.", styles: false },
  { no: "070", set: "ms", id: "ms070", name: "Pilgrim in the Storm", sub: "robed, storm", rar: "uncommon", chars: 7260, val: 85, tint: "#a5caff", cap: "the weather answers to it.", styles: false },
  { no: "071", set: "ms", id: "ms071", name: "Idol at Moonrise", sub: "idol, moon", rar: "uncommon", chars: 7260, val: 100, tint: "#a5e1ff", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "072", set: "ms", id: "ms072", name: "Hollow King at Moonrise 2", sub: "crowned, moon", rar: "rare", chars: 9800, val: 300, tint: "#a5fff7", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "073", set: "ms", id: "ms073", name: "Horned One in the Storm", sub: "horned, storm", rar: "epic", chars: 15750, val: 400, tint: "#a5fff7", cap: "the weather answers to it.", styles: false },
  { no: "074", set: "ms", id: "ms074", name: "Spire in the Storm", sub: "tower, storm", rar: "epic", chars: 15750, val: 550, tint: "#a5fff7", cap: "the weather answers to it.", styles: false },
  { no: "075", set: "ms", id: "ms075", name: "Twins in Halo", sub: "twin, halo", rar: "legendary", chars: 29400, val: 750, tint: "#a5e1ff", cap: "no one asked it to be holy.", styles: false },
  { no: "076", set: "ms", id: "ms076", name: "Gate at Moonrise 3", sub: "gate, moon", rar: "legendary", chars: 29400, val: 1000, tint: "#a5fff7", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "077", set: "ms", id: "ms077", name: "Wanderer at Sunburst", sub: "lone, sunburst", rar: "legendary", chars: 29400, val: 1400, tint: "#a5e1ff", cap: "looks straight at it. does not blink.", styles: false },
  { no: "078", set: "ms", id: "ms078", name: "Gate in the Storm", sub: "gate, storm", rar: "divine", chars: 72000, val: 7500, tint: "#a5fff7", cap: "the weather answers to it.", styles: false },
  { no: "079", set: "ec", id: "ec079", name: "Hollow King of the Eclipse", sub: "crowned, eclipse", rar: "common", chars: 6432, val: 10, tint: "#d2a5ff", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "080", set: "ec", id: "ec080", name: "Gate of the Rings", sub: "gate, rings", rar: "common", chars: 6432, val: 12, tint: "#a5fff7", cap: "each ring is a year it waited.", styles: false },
  { no: "081", set: "ec", id: "ec081", name: "Monk in Halo", sub: "monk, halo", rar: "common", chars: 6432, val: 15, tint: "#a5ffb4", cap: "no one asked it to be holy.", styles: false },
  { no: "082", set: "ec", id: "ec082", name: "Spire in the Storm 2", sub: "tower, storm", rar: "common", chars: 6432, val: 15, tint: "#a5ffb4", cap: "the weather answers to it.", styles: false },
  { no: "083", set: "ec", id: "ec083", name: "Horned One in the Void 2", sub: "horned, void", rar: "common", chars: 6432, val: 18, tint: "#d2a5ff", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "084", set: "ec", id: "ec084", name: "Horned One in the Rift", sub: "horned, rift", rar: "common", chars: 6432, val: 20, tint: "#a5fff7", cap: "something is leaving through the crack.", styles: false },
  { no: "085", set: "ec", id: "ec085", name: "Mourner in the Storm", sub: "mourner, storm", rar: "common", chars: 6432, val: 20, tint: "#a5ffb4", cap: "the weather answers to it.", styles: false },
  { no: "086", set: "ec", id: "ec086", name: "Seraph in Halo 2", sub: "angel, halo", rar: "common", chars: 6432, val: 22, tint: "#ffd9a5", cap: "no one asked it to be holy.", styles: false },
  { no: "087", set: "ec", id: "ec087", name: "Warden at Sunburst", sub: "knight, sunburst", rar: "common", chars: 6432, val: 25, tint: "#a5fff7", cap: "looks straight at it. does not blink.", styles: false },
  { no: "088", set: "ec", id: "ec088", name: "Mourner at Moonrise", sub: "mourner, moon", rar: "common", chars: 6432, val: 25, tint: "#d2a5ff", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "089", set: "ec", id: "ec089", name: "Horned One of the Rings", sub: "horned, rings", rar: "common", chars: 6432, val: 28, tint: "#a5fff7", cap: "each ring is a year it waited.", styles: false },
  { no: "090", set: "ec", id: "ec090", name: "Warden at Moonrise", sub: "knight, moon", rar: "common", chars: 6432, val: 30, tint: "#a5fff7", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "091", set: "ec", id: "ec091", name: "Spire in the Void", sub: "tower, void", rar: "uncommon", chars: 7260, val: 40, tint: "#a5fff7", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "092", set: "ec", id: "ec092", name: "Idol of the Rings 2", sub: "idol, rings", rar: "uncommon", chars: 7260, val: 50, tint: "#ffd9a5", cap: "each ring is a year it waited.", styles: false },
  { no: "093", set: "ec", id: "ec093", name: "Hollow King in the Void", sub: "crowned, void", rar: "uncommon", chars: 7260, val: 60, tint: "#d2a5ff", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "094", set: "ec", id: "ec094", name: "Teeth in Halo", sub: "spire, halo", rar: "uncommon", chars: 7260, val: 70, tint: "#d2a5ff", cap: "no one asked it to be holy.", styles: false },
  { no: "095", set: "ec", id: "ec095", name: "Pilgrim at Moonrise", sub: "robed, moon", rar: "uncommon", chars: 7260, val: 85, tint: "#a5fff7", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "096", set: "ec", id: "ec096", name: "Mourner in the Storm 2", sub: "mourner, storm", rar: "uncommon", chars: 7260, val: 100, tint: "#ffd9a5", cap: "the weather answers to it.", styles: false },
  { no: "097", set: "ec", id: "ec097", name: "Horned One of the Eclipse", sub: "horned, eclipse", rar: "legendary", chars: 29400, val: 750, tint: "#d2a5ff", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "098", set: "ec", id: "ec098", name: "Seraph in Halo 3", sub: "angel, halo", rar: "legendary", chars: 29400, val: 1100, tint: "#a5ffb4", cap: "no one asked it to be holy.", styles: false },
  { no: "099", set: "ec", id: "ec099", name: "Monk in the Rift", sub: "monk, rift", rar: "legendary", chars: 29400, val: 1500, tint: "#ffd9a5", cap: "something is leaving through the crack.", styles: false },
  { no: "100", set: "ec", id: "ec100", name: "Twins in Halo 2", sub: "twin, halo", rar: "legendary", chars: 29400, val: 2000, tint: "#a5fff7", cap: "no one asked it to be holy.", styles: false },
  { no: "101", set: "ec", id: "ec101", name: "Monk at Moonrise", sub: "monk, moon", rar: "mythic", chars: 40320, val: 2750, tint: "#a5ffb4", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "102", set: "ec", id: "ec102", name: "Warden of the Eclipse", sub: "knight, eclipse", rar: "mythic", chars: 40320, val: 3750, tint: "#a5ffb4", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "103", set: "ec", id: "ec103", name: "Horned One of the Rings 2", sub: "horned, rings", rar: "exotic", chars: 52000, val: 5000, tint: "#a5ffb4", cap: "each ring is a year it waited.", styles: false },
  { no: "104", set: "ec", id: "ec104", name: "Spire in the Void 2", sub: "tower, void", rar: "celestial", chars: 100000, val: 14000, tint: "#ffd9a5", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "105", set: "ec", id: "ec105", name: "Seraph at Moonrise 2", sub: "angel, moon", rar: "celestial", chars: 100000, val: 17000, tint: "#ffd9a5", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "106", set: "td", id: "td106", name: "Twins of the Rings", sub: "twin, rings", rar: "common", chars: 6432, val: 10, tint: "#d2a5ff", cap: "each ring is a year it waited.", styles: false },
  { no: "107", set: "td", id: "td107", name: "Pilgrim at Sunburst 2", sub: "robed, sunburst", rar: "common", chars: 6432, val: 12, tint: "#ffa5ad", cap: "looks straight at it. does not blink.", styles: false },
  { no: "108", set: "td", id: "td108", name: "Teeth in the Rift", sub: "spire, rift", rar: "common", chars: 6432, val: 15, tint: "#ffa5ad", cap: "something is leaving through the crack.", styles: false },
  { no: "109", set: "td", id: "td109", name: "Seraph of the Rings 2", sub: "angel, rings", rar: "common", chars: 6432, val: 15, tint: "#ffc0a5", cap: "each ring is a year it waited.", styles: false },
  { no: "110", set: "td", id: "td110", name: "Monk of the Eclipse", sub: "monk, eclipse", rar: "common", chars: 6432, val: 18, tint: "#ffa5e1", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "111", set: "td", id: "td111", name: "Twins of the Rings 2", sub: "twin, rings", rar: "common", chars: 6432, val: 20, tint: "#ffa5ad", cap: "each ring is a year it waited.", styles: false },
  { no: "112", set: "td", id: "td112", name: "Gate of the Eclipse 2", sub: "gate, eclipse", rar: "common", chars: 6432, val: 20, tint: "#ffa5e1", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "113", set: "td", id: "td113", name: "Seraph in the Storm", sub: "angel, storm", rar: "common", chars: 6432, val: 22, tint: "#d2a5ff", cap: "the weather answers to it.", styles: false },
  { no: "114", set: "td", id: "td114", name: "Hollow King of the Rings", sub: "crowned, rings", rar: "common", chars: 6432, val: 25, tint: "#ffc0a5", cap: "each ring is a year it waited.", styles: false },
  { no: "115", set: "td", id: "td115", name: "Teeth in the Void", sub: "spire, void", rar: "common", chars: 6432, val: 25, tint: "#d2a5ff", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "116", set: "td", id: "td116", name: "Warden in the Rift 3", sub: "knight, rift", rar: "common", chars: 6432, val: 28, tint: "#d2a5ff", cap: "something is leaving through the crack.", styles: false },
  { no: "117", set: "td", id: "td117", name: "Warden at Sunburst 2", sub: "knight, sunburst", rar: "common", chars: 6432, val: 30, tint: "#ffa5ad", cap: "looks straight at it. does not blink.", styles: false },
  { no: "118", set: "td", id: "td118", name: "Idol in the Rift", sub: "idol, rift", rar: "uncommon", chars: 7260, val: 40, tint: "#ffc0a5", cap: "something is leaving through the crack.", styles: false },
  { no: "119", set: "td", id: "td119", name: "Mourner in Halo 2", sub: "mourner, halo", rar: "uncommon", chars: 7260, val: 50, tint: "#d2a5ff", cap: "no one asked it to be holy.", styles: false },
  { no: "120", set: "td", id: "td120", name: "Hollow King in the Storm", sub: "crowned, storm", rar: "uncommon", chars: 7260, val: 60, tint: "#ffc0a5", cap: "the weather answers to it.", styles: false },
  { no: "121", set: "td", id: "td121", name: "Seraph at Moonrise 3", sub: "angel, moon", rar: "uncommon", chars: 7260, val: 70, tint: "#ffa5e1", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "122", set: "td", id: "td122", name: "Hollow King of the Eclipse 2", sub: "crowned, eclipse", rar: "uncommon", chars: 7260, val: 85, tint: "#ffa5e1", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "123", set: "td", id: "td123", name: "Mourner at Sunburst", sub: "mourner, sunburst", rar: "uncommon", chars: 7260, val: 100, tint: "#ffa5ad", cap: "looks straight at it. does not blink.", styles: false },
  { no: "124", set: "td", id: "td124", name: "Idol in Halo", sub: "idol, halo", rar: "legendary", chars: 29400, val: 2000, tint: "#ffa5e1", cap: "no one asked it to be holy.", styles: false },
  { no: "125", set: "td", id: "td125", name: "Monk of the Rings", sub: "monk, rings", rar: "mythic", chars: 40320, val: 2750, tint: "#ffc0a5", cap: "each ring is a year it waited.", styles: false },
  { no: "126", set: "td", id: "td126", name: "Gate of the Eclipse 3", sub: "gate, eclipse", rar: "mythic", chars: 40320, val: 3750, tint: "#d2a5ff", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "127", set: "td", id: "td127", name: "Monk in the Storm 2", sub: "monk, storm", rar: "exotic", chars: 52000, val: 5000, tint: "#ffa5e1", cap: "the weather answers to it.", styles: false },
  { no: "128", set: "td", id: "td128", name: "Idol of the Rings 3", sub: "idol, rings", rar: "divine", chars: 72000, val: 7000, tint: "#ffa5ad", cap: "each ring is a year it waited.", styles: false },
  { no: "129", set: "td", id: "td129", name: "Pilgrim in the Void", sub: "robed, void", rar: "divine", chars: 72000, val: 9500, tint: "#ffa5ad", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "130", set: "td", id: "td130", name: "Wanderer of the Eclipse", sub: "lone, eclipse", rar: "celestial", chars: 100000, val: 13000, tint: "#ffc0a5", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "131", set: "td", id: "td131", name: "Horned One of the Eclipse 2", sub: "horned, eclipse", rar: "celestial", chars: 100000, val: 16000, tint: "#ffa5ad", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "132", set: "td", id: "td132", name: "Gate of the Rings 2", sub: "gate, rings", rar: "eternal", chars: 220000, val: 42500, tint: "#ffa5e1", cap: "each ring is a year it waited.", styles: false },
  { no: "133", set: "sg", id: "sg133", name: "Teeth in the Rift 2", sub: "spire, rift", rar: "common", chars: 6432, val: 10, tint: "#ffa5e1", cap: "something is leaving through the crack.", styles: false },
  { no: "134", set: "sg", id: "sg134", name: "Idol at Sunburst", sub: "idol, sunburst", rar: "common", chars: 6432, val: 12, tint: "#a5e1ff", cap: "looks straight at it. does not blink.", styles: false },
  { no: "135", set: "sg", id: "sg135", name: "Horned One of the Rings 3", sub: "horned, rings", rar: "common", chars: 6432, val: 15, tint: "#ffe1a5", cap: "each ring is a year it waited.", styles: false },
  { no: "136", set: "sg", id: "sg136", name: "Teeth in the Void 2", sub: "spire, void", rar: "common", chars: 6432, val: 15, tint: "#ffa5e1", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "137", set: "sg", id: "sg137", name: "Horned One in the Void 3", sub: "horned, void", rar: "common", chars: 6432, val: 18, tint: "#ffe1a5", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "138", set: "sg", id: "sg138", name: "Horned One in the Storm 2", sub: "horned, storm", rar: "common", chars: 6432, val: 20, tint: "#ffa5e1", cap: "the weather answers to it.", styles: false },
  { no: "139", set: "sg", id: "sg139", name: "Seraph in the Storm 2", sub: "angel, storm", rar: "common", chars: 6432, val: 20, tint: "#a5e1ff", cap: "the weather answers to it.", styles: false },
  { no: "140", set: "sg", id: "sg140", name: "Warden in Halo", sub: "knight, halo", rar: "common", chars: 6432, val: 22, tint: "#ffe1a5", cap: "no one asked it to be holy.", styles: false },
  { no: "141", set: "sg", id: "sg141", name: "Teeth in the Storm 2", sub: "spire, storm", rar: "common", chars: 6432, val: 25, tint: "#ffe1a5", cap: "the weather answers to it.", styles: false },
  { no: "142", set: "sg", id: "sg142", name: "Teeth of the Eclipse", sub: "spire, eclipse", rar: "common", chars: 6432, val: 25, tint: "#ffa5e1", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "143", set: "sg", id: "sg143", name: "Spire in the Rift", sub: "tower, rift", rar: "common", chars: 6432, val: 28, tint: "#a5e1ff", cap: "something is leaving through the crack.", styles: false },
  { no: "144", set: "sg", id: "sg144", name: "Idol at Sunburst 2", sub: "idol, sunburst", rar: "common", chars: 6432, val: 30, tint: "#ffd9a5", cap: "looks straight at it. does not blink.", styles: false },
  { no: "145", set: "sg", id: "sg145", name: "Idol in the Rift 2", sub: "idol, rift", rar: "uncommon", chars: 7260, val: 40, tint: "#ffa5ad", cap: "something is leaving through the crack.", styles: false },
  { no: "146", set: "sg", id: "sg146", name: "Pilgrim at Sunburst 3", sub: "robed, sunburst", rar: "uncommon", chars: 7260, val: 50, tint: "#a5e1ff", cap: "looks straight at it. does not blink.", styles: false },
  { no: "147", set: "sg", id: "sg147", name: "Twins of the Eclipse", sub: "twin, eclipse", rar: "uncommon", chars: 7260, val: 60, tint: "#ffe1a5", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "148", set: "sg", id: "sg148", name: "Seraph at Moonrise 4", sub: "angel, moon", rar: "uncommon", chars: 7260, val: 70, tint: "#ffa5ad", cap: "the only lamp for a hundred miles.", styles: false },
  { no: "149", set: "sg", id: "sg149", name: "Horned One of the Rings 4", sub: "horned, rings", rar: "uncommon", chars: 7260, val: 85, tint: "#a5e1ff", cap: "each ring is a year it waited.", styles: false },
  { no: "150", set: "sg", id: "sg150", name: "Teeth at Sunburst", sub: "spire, sunburst", rar: "uncommon", chars: 7260, val: 100, tint: "#ffa5ad", cap: "looks straight at it. does not blink.", styles: false },
  { no: "151", set: "sg", id: "sg151", name: "Idol at Sunburst 3", sub: "idol, sunburst", rar: "exotic", chars: 52000, val: 4500, tint: "#ffa5ad", cap: "looks straight at it. does not blink.", styles: false },
  { no: "152", set: "sg", id: "sg152", name: "Monk of the Rings 2", sub: "monk, rings", rar: "exotic", chars: 52000, val: 6000, tint: "#ffa5e1", cap: "each ring is a year it waited.", styles: false },
  { no: "153", set: "sg", id: "sg153", name: "Gate in the Void", sub: "gate, void", rar: "divine", chars: 72000, val: 8000, tint: "#ffa5e1", cap: "the quiet got bigger, not emptier.", styles: false },
  { no: "154", set: "sg", id: "sg154", name: "Seraph of the Eclipse", sub: "angel, eclipse", rar: "divine", chars: 72000, val: 11000, tint: "#a5e1ff", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "155", set: "sg", id: "sg155", name: "Hollow King in Halo", sub: "crowned, halo", rar: "celestial", chars: 100000, val: 15000, tint: "#ffe1a5", cap: "no one asked it to be holy.", styles: false },
  { no: "156", set: "sg", id: "sg156", name: "Teeth in Halo 2", sub: "spire, halo", rar: "celestial", chars: 100000, val: 21000, tint: "#ffd9a5", cap: "no one asked it to be holy.", styles: false },
  { no: "157", set: "sg", id: "sg157", name: "Gate in the Storm 2", sub: "gate, storm", rar: "cosmic", chars: 150000, val: 29000, tint: "#ffa5e1", cap: "the weather answers to it.", styles: false },
  { no: "158", set: "sg", id: "sg158", name: "Mourner of the Eclipse", sub: "mourner, eclipse", rar: "eternal", chars: 220000, val: 40000, tint: "#ffa5e1", cap: "it went dark at noon. it stayed.", styles: false },
  { no: "159", set: "sg", id: "sg159", name: "Idol of the Rings 4", sub: "idol, rings", rar: "secret", chars: 700000, val: 150000, tint: "#ffe1a5", cap: "each ring is a year it waited.", styles: false },
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
  // Five packs of thirty different cards each: eighteen fillers (twelve commons, six uncommons) for cards 1 to 4, 6 and 7, and twelve rare-slot cards
  // for card 5, dearest last. A dearer pack's rare slot starts higher up the ladder. Every pack returns 94.7% on average.
  { id: "fp", name: "First Print", blurb: "Thirty stick figures printed in text. Seven cards a pack, and the one in the middle is the one you open it for.", price: 500, min: 500, max: 500, n: 7, col: "#3be477", scene: "print",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of twelve cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["stitch", 6.6667], ["brick", 6.6667], ["orbit", 6.6667], ["rook", 6.6667], ["mop", 6.6667], ["pan", 6.6667], ["cone", 6.6667], ["fuse", 6.6667], ["countdown", 6.6667], ["spark", 6.6667], ["flare", 6.6667], ["bubble", 6.6667], ["fp045", 3.3333], ["fp046", 3.3333], ["fp047", 3.3333], ["fp048", 3.3333], ["fp049", 3.3333], ["fp050", 3.3333]],
      [["stitch", 6.6667], ["brick", 6.6667], ["orbit", 6.6667], ["rook", 6.6667], ["mop", 6.6667], ["pan", 6.6667], ["cone", 6.6667], ["fuse", 6.6667], ["countdown", 6.6667], ["spark", 6.6667], ["flare", 6.6667], ["bubble", 6.6667], ["fp045", 3.3333], ["fp046", 3.3333], ["fp047", 3.3333], ["fp048", 3.3333], ["fp049", 3.3333], ["fp050", 3.3333]],
      [["stitch", 6.6667], ["brick", 6.6667], ["orbit", 6.6667], ["rook", 6.6667], ["mop", 6.6667], ["pan", 6.6667], ["cone", 6.6667], ["fuse", 6.6667], ["countdown", 6.6667], ["spark", 6.6667], ["flare", 6.6667], ["bubble", 6.6667], ["fp045", 3.3333], ["fp046", 3.3333], ["fp047", 3.3333], ["fp048", 3.3333], ["fp049", 3.3333], ["fp050", 3.3333]],
      [["stitch", 6.6667], ["brick", 6.6667], ["orbit", 6.6667], ["rook", 6.6667], ["mop", 6.6667], ["pan", 6.6667], ["cone", 6.6667], ["fuse", 6.6667], ["countdown", 6.6667], ["spark", 6.6667], ["flare", 6.6667], ["bubble", 6.6667], ["fp045", 3.3333], ["fp046", 3.3333], ["fp047", 3.3333], ["fp048", 3.3333], ["fp049", 3.3333], ["fp050", 3.3333]],
      [["fp051", 20.0838], ["tempest", 16.4064], ["surge", 13.4024], ["ignition", 10.9484], ["console", 8.9437], ["fp052", 7.3061], ["phantom", 5.9683], ["kraken", 4.8755], ["suit", 3.9828], ["colossus", 3.2535], ["gantry", 2.6578], ["fp053", 2.1712]],
      [["stitch", 6.1333], ["brick", 6.1333], ["orbit", 6.1333], ["rook", 6.1333], ["mop", 6.1333], ["pan", 6.1333], ["cone", 6.1333], ["fuse", 6.1333], ["countdown", 6.1333], ["spark", 6.1333], ["flare", 6.1333], ["bubble", 6.1333], ["fp045", 3.0667], ["fp046", 3.0667], ["fp047", 3.0667], ["fp048", 3.0667], ["fp049", 3.0667], ["fp050", 3.0667], ["fp051", 2], ["tempest", 2], ["surge", 2], ["ignition", 2]],
      [["stitch", 6.1333], ["brick", 6.1333], ["orbit", 6.1333], ["rook", 6.1333], ["mop", 6.1333], ["pan", 6.1333], ["cone", 6.1333], ["fuse", 6.1333], ["countdown", 6.1333], ["spark", 6.1333], ["flare", 6.1333], ["bubble", 6.1333], ["fp045", 3.0667], ["fp046", 3.0667], ["fp047", 3.0667], ["fp048", 3.0667], ["fp049", 3.0667], ["fp050", 3.0667], ["fp051", 2], ["tempest", 2], ["surge", 2], ["ignition", 2]]
    ] },
  { id: "ms", name: "Moonshot", blurb: "Thirty cards from a launch: storms, rockets and the Moon. The fifth card is the rare slot.", price: 1500, min: 1500, max: 1500, n: 7, col: "#ffa046", scene: "launch",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of twelve cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["ms054", 6.6667], ["ms055", 6.6667], ["ms056", 6.6667], ["ms057", 6.6667], ["ms058", 6.6667], ["ms059", 6.6667], ["ms060", 6.6667], ["ms061", 6.6667], ["ms062", 6.6667], ["ms063", 6.6667], ["ms064", 6.6667], ["ms065", 6.6667], ["ms066", 3.3333], ["ms067", 3.3333], ["ms068", 3.3333], ["ms069", 3.3333], ["ms070", 3.3333], ["ms071", 3.3333]],
      [["ms054", 6.6667], ["ms055", 6.6667], ["ms056", 6.6667], ["ms057", 6.6667], ["ms058", 6.6667], ["ms059", 6.6667], ["ms060", 6.6667], ["ms061", 6.6667], ["ms062", 6.6667], ["ms063", 6.6667], ["ms064", 6.6667], ["ms065", 6.6667], ["ms066", 3.3333], ["ms067", 3.3333], ["ms068", 3.3333], ["ms069", 3.3333], ["ms070", 3.3333], ["ms071", 3.3333]],
      [["ms054", 6.6667], ["ms055", 6.6667], ["ms056", 6.6667], ["ms057", 6.6667], ["ms058", 6.6667], ["ms059", 6.6667], ["ms060", 6.6667], ["ms061", 6.6667], ["ms062", 6.6667], ["ms063", 6.6667], ["ms064", 6.6667], ["ms065", 6.6667], ["ms066", 3.3333], ["ms067", 3.3333], ["ms068", 3.3333], ["ms069", 3.3333], ["ms070", 3.3333], ["ms071", 3.3333]],
      [["ms054", 6.6667], ["ms055", 6.6667], ["ms056", 6.6667], ["ms057", 6.6667], ["ms058", 6.6667], ["ms059", 6.6667], ["ms060", 6.6667], ["ms061", 6.6667], ["ms062", 6.6667], ["ms063", 6.6667], ["ms064", 6.6667], ["ms065", 6.6667], ["ms066", 3.3333], ["ms067", 3.3333], ["ms068", 3.3333], ["ms069", 3.3333], ["ms070", 3.3333], ["ms071", 3.3333]],
      [["ms072", 20.7651], ["ms073", 16.7899], ["ms074", 13.5757], ["ms075", 10.9768], ["ms076", 8.8755], ["ms077", 7.1764], ["leviathan", 5.8026], ["liftoff", 4.6917], ["null", 3.7936], ["booster", 3.0673], ["shogun", 2.4801], ["ms078", 2.0054]],
      [["ms054", 5.7333], ["ms055", 5.7333], ["ms056", 5.7333], ["ms057", 5.7333], ["ms058", 5.7333], ["ms059", 5.7333], ["ms060", 5.7333], ["ms061", 5.7333], ["ms062", 5.7333], ["ms063", 5.7333], ["ms064", 5.7333], ["ms065", 5.7333], ["ms066", 2.8667], ["ms067", 2.8667], ["ms068", 2.8667], ["ms069", 2.8667], ["ms070", 2.8667], ["ms071", 2.8667], ["ms072", 3.5], ["ms073", 3.5], ["ms074", 3.5], ["ms075", 3.5]],
      [["ms054", 5.7333], ["ms055", 5.7333], ["ms056", 5.7333], ["ms057", 5.7333], ["ms058", 5.7333], ["ms059", 5.7333], ["ms060", 5.7333], ["ms061", 5.7333], ["ms062", 5.7333], ["ms063", 5.7333], ["ms064", 5.7333], ["ms065", 5.7333], ["ms066", 2.8667], ["ms067", 2.8667], ["ms068", 2.8667], ["ms069", 2.8667], ["ms070", 2.8667], ["ms071", 2.8667], ["ms072", 3.5], ["ms073", 3.5], ["ms074", 3.5], ["ms075", 3.5]]
    ] },
  { id: "ec", name: "Eclipse", blurb: "Thirty cards from under a black sun. The rare slot starts at a legendary-class card.", price: 4000, min: 4000, max: 4000, n: 7, col: "#ffc24a", scene: "eclipse",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of twelve cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["ec079", 6.6667], ["ec080", 6.6667], ["ec081", 6.6667], ["ec082", 6.6667], ["ec083", 6.6667], ["ec084", 6.6667], ["ec085", 6.6667], ["ec086", 6.6667], ["ec087", 6.6667], ["ec088", 6.6667], ["ec089", 6.6667], ["ec090", 6.6667], ["ec091", 3.3333], ["ec092", 3.3333], ["ec093", 3.3333], ["ec094", 3.3333], ["ec095", 3.3333], ["ec096", 3.3333]],
      [["ec079", 6.6667], ["ec080", 6.6667], ["ec081", 6.6667], ["ec082", 6.6667], ["ec083", 6.6667], ["ec084", 6.6667], ["ec085", 6.6667], ["ec086", 6.6667], ["ec087", 6.6667], ["ec088", 6.6667], ["ec089", 6.6667], ["ec090", 6.6667], ["ec091", 3.3333], ["ec092", 3.3333], ["ec093", 3.3333], ["ec094", 3.3333], ["ec095", 3.3333], ["ec096", 3.3333]],
      [["ec079", 6.6667], ["ec080", 6.6667], ["ec081", 6.6667], ["ec082", 6.6667], ["ec083", 6.6667], ["ec084", 6.6667], ["ec085", 6.6667], ["ec086", 6.6667], ["ec087", 6.6667], ["ec088", 6.6667], ["ec089", 6.6667], ["ec090", 6.6667], ["ec091", 3.3333], ["ec092", 3.3333], ["ec093", 3.3333], ["ec094", 3.3333], ["ec095", 3.3333], ["ec096", 3.3333]],
      [["ec079", 6.6667], ["ec080", 6.6667], ["ec081", 6.6667], ["ec082", 6.6667], ["ec083", 6.6667], ["ec084", 6.6667], ["ec085", 6.6667], ["ec086", 6.6667], ["ec087", 6.6667], ["ec088", 6.6667], ["ec089", 6.6667], ["ec090", 6.6667], ["ec091", 3.3333], ["ec092", 3.3333], ["ec093", 3.3333], ["ec094", 3.3333], ["ec095", 3.3333], ["ec096", 3.3333]],
      [["ec097", 19.668], ["ec098", 16.1681], ["ec099", 13.291], ["ec100", 10.9258], ["ec101", 8.9816], ["ec102", 7.3833], ["ec103", 6.0695], ["apogee", 4.9894], ["ronin", 4.1015], ["luna", 3.3717], ["ec104", 2.7717], ["ec105", 2.2785]],
      [["ec079", 5.3333], ["ec080", 5.3333], ["ec081", 5.3333], ["ec082", 5.3333], ["ec083", 5.3333], ["ec084", 5.3333], ["ec085", 5.3333], ["ec086", 5.3333], ["ec087", 5.3333], ["ec088", 5.3333], ["ec089", 5.3333], ["ec090", 5.3333], ["ec091", 2.6667], ["ec092", 2.6667], ["ec093", 2.6667], ["ec094", 2.6667], ["ec095", 2.6667], ["ec096", 2.6667], ["ec097", 5], ["ec098", 5], ["ec099", 5], ["ec100", 5]],
      [["ec079", 5.3333], ["ec080", 5.3333], ["ec081", 5.3333], ["ec082", 5.3333], ["ec083", 5.3333], ["ec084", 5.3333], ["ec085", 5.3333], ["ec086", 5.3333], ["ec087", 5.3333], ["ec088", 5.3333], ["ec089", 5.3333], ["ec090", 5.3333], ["ec091", 2.6667], ["ec092", 2.6667], ["ec093", 2.6667], ["ec094", 2.6667], ["ec095", 2.6667], ["ec096", 2.6667], ["ec097", 5], ["ec098", 5], ["ec099", 5], ["ec100", 5]]
    ] },
  { id: "td", name: "Tidal", blurb: "Thirty cards from deep water. The rare slot never pays less than a card worth fifth of the pack.", price: 10000, min: 10000, max: 10000, n: 7, col: "#46d2ff", scene: "tidal",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of twelve cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["td106", 6.6667], ["td107", 6.6667], ["td108", 6.6667], ["td109", 6.6667], ["td110", 6.6667], ["td111", 6.6667], ["td112", 6.6667], ["td113", 6.6667], ["td114", 6.6667], ["td115", 6.6667], ["td116", 6.6667], ["td117", 6.6667], ["td118", 3.3333], ["td119", 3.3333], ["td120", 3.3333], ["td121", 3.3333], ["td122", 3.3333], ["td123", 3.3333]],
      [["td106", 6.6667], ["td107", 6.6667], ["td108", 6.6667], ["td109", 6.6667], ["td110", 6.6667], ["td111", 6.6667], ["td112", 6.6667], ["td113", 6.6667], ["td114", 6.6667], ["td115", 6.6667], ["td116", 6.6667], ["td117", 6.6667], ["td118", 3.3333], ["td119", 3.3333], ["td120", 3.3333], ["td121", 3.3333], ["td122", 3.3333], ["td123", 3.3333]],
      [["td106", 6.6667], ["td107", 6.6667], ["td108", 6.6667], ["td109", 6.6667], ["td110", 6.6667], ["td111", 6.6667], ["td112", 6.6667], ["td113", 6.6667], ["td114", 6.6667], ["td115", 6.6667], ["td116", 6.6667], ["td117", 6.6667], ["td118", 3.3333], ["td119", 3.3333], ["td120", 3.3333], ["td121", 3.3333], ["td122", 3.3333], ["td123", 3.3333]],
      [["td106", 6.6667], ["td107", 6.6667], ["td108", 6.6667], ["td109", 6.6667], ["td110", 6.6667], ["td111", 6.6667], ["td112", 6.6667], ["td113", 6.6667], ["td114", 6.6667], ["td115", 6.6667], ["td116", 6.6667], ["td117", 6.6667], ["td118", 3.3333], ["td119", 3.3333], ["td120", 3.3333], ["td121", 3.3333], ["td122", 3.3333], ["td123", 3.3333]],
      [["td124", 21.6411], ["td125", 17.2702], ["td126", 13.782], ["td127", 10.9984], ["td128", 8.777], ["td129", 7.0043], ["td130", 5.5896], ["td131", 4.4607], ["titan", 3.5597], ["grimm", 2.8408], ["td132", 2.267], ["reaper", 1.8091]],
      [["td106", 4.8], ["td107", 4.8], ["td108", 4.8], ["td109", 4.8], ["td110", 4.8], ["td111", 4.8], ["td112", 4.8], ["td113", 4.8], ["td114", 4.8], ["td115", 4.8], ["td116", 4.8], ["td117", 4.8], ["td118", 2.4], ["td119", 2.4], ["td120", 2.4], ["td121", 2.4], ["td122", 2.4], ["td123", 2.4], ["td124", 7], ["td125", 7], ["td126", 7], ["td127", 7]],
      [["td106", 4.8], ["td107", 4.8], ["td108", 4.8], ["td109", 4.8], ["td110", 4.8], ["td111", 4.8], ["td112", 4.8], ["td113", 4.8], ["td114", 4.8], ["td115", 4.8], ["td116", 4.8], ["td117", 4.8], ["td118", 2.4], ["td119", 2.4], ["td120", 2.4], ["td121", 2.4], ["td122", 2.4], ["td123", 2.4], ["td124", 7], ["td125", 7], ["td126", 7], ["td127", 7]]
    ] },
  { id: "sg", name: "Singularity", blurb: "Thirty cards from the edge of the dark. The biggest cards in the game live here.", price: 25000, min: 25000, max: 25000, n: 7, col: "#b78cff", scene: "void",
    slotNames: ["Cards 1 to 4: commons and uncommons", "Card 5: the rare slot, one of twelve cards worth having", "Cards 6 and 7: mostly commons, sometimes a rare"],
    slots: [
      [["sg133", 6.6667], ["sg134", 6.6667], ["sg135", 6.6667], ["sg136", 6.6667], ["sg137", 6.6667], ["sg138", 6.6667], ["sg139", 6.6667], ["sg140", 6.6667], ["sg141", 6.6667], ["sg142", 6.6667], ["sg143", 6.6667], ["sg144", 6.6667], ["sg145", 3.3333], ["sg146", 3.3333], ["sg147", 3.3333], ["sg148", 3.3333], ["sg149", 3.3333], ["sg150", 3.3333]],
      [["sg133", 6.6667], ["sg134", 6.6667], ["sg135", 6.6667], ["sg136", 6.6667], ["sg137", 6.6667], ["sg138", 6.6667], ["sg139", 6.6667], ["sg140", 6.6667], ["sg141", 6.6667], ["sg142", 6.6667], ["sg143", 6.6667], ["sg144", 6.6667], ["sg145", 3.3333], ["sg146", 3.3333], ["sg147", 3.3333], ["sg148", 3.3333], ["sg149", 3.3333], ["sg150", 3.3333]],
      [["sg133", 6.6667], ["sg134", 6.6667], ["sg135", 6.6667], ["sg136", 6.6667], ["sg137", 6.6667], ["sg138", 6.6667], ["sg139", 6.6667], ["sg140", 6.6667], ["sg141", 6.6667], ["sg142", 6.6667], ["sg143", 6.6667], ["sg144", 6.6667], ["sg145", 3.3333], ["sg146", 3.3333], ["sg147", 3.3333], ["sg148", 3.3333], ["sg149", 3.3333], ["sg150", 3.3333]],
      [["sg133", 6.6667], ["sg134", 6.6667], ["sg135", 6.6667], ["sg136", 6.6667], ["sg137", 6.6667], ["sg138", 6.6667], ["sg139", 6.6667], ["sg140", 6.6667], ["sg141", 6.6667], ["sg142", 6.6667], ["sg143", 6.6667], ["sg144", 6.6667], ["sg145", 3.3333], ["sg146", 3.3333], ["sg147", 3.3333], ["sg148", 3.3333], ["sg149", 3.3333], ["sg150", 3.3333]],
      [["sg151", 24.8128], ["sg152", 18.8893], ["sg153", 14.3799], ["sg154", 10.947], ["sg155", 8.3337], ["sg156", 6.3442], ["sg157", 4.8297], ["sg158", 3.6767], ["mars", 2.799], ["umbra", 2.1308], ["sg159", 1.6221], ["horizon", 1.2349]],
      [["sg133", 4.1333], ["sg134", 4.1333], ["sg135", 4.1333], ["sg136", 4.1333], ["sg137", 4.1333], ["sg138", 4.1333], ["sg139", 4.1333], ["sg140", 4.1333], ["sg141", 4.1333], ["sg142", 4.1333], ["sg143", 4.1333], ["sg144", 4.1333], ["sg145", 2.0667], ["sg146", 2.0667], ["sg147", 2.0667], ["sg148", 2.0667], ["sg149", 2.0667], ["sg150", 2.0667], ["sg151", 9.5], ["sg152", 9.5], ["sg153", 9.5], ["sg154", 9.5]],
      [["sg133", 4.1333], ["sg134", 4.1333], ["sg135", 4.1333], ["sg136", 4.1333], ["sg137", 4.1333], ["sg138", 4.1333], ["sg139", 4.1333], ["sg140", 4.1333], ["sg141", 4.1333], ["sg142", 4.1333], ["sg143", 4.1333], ["sg144", 4.1333], ["sg145", 2.0667], ["sg146", 2.0667], ["sg147", 2.0667], ["sg148", 2.0667], ["sg149", 2.0667], ["sg150", 2.0667], ["sg151", 9.5], ["sg152", 9.5], ["sg153", 9.5], ["sg154", 9.5]]
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
