/* ============================================================================
   1. DATA. One pack, eleven cards. Every card is a finished ASCII card; the picture is a file,
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
  { no: "001", id: "stitch",  name: "Stitch",  sub: "frog hat",   rar: "common",    chars: 2772,   val: 15,    tint: "#ece7dc", cap: "frog hat. zero regrets.",       styles: true },
  { no: "003", id: "brick",   name: "Brick",   sub: "colander",   rar: "common",    chars: 2816,   val: 15,    tint: "#a8ffbe", cap: "it is a colander. it works." },
  { no: "004", id: "rook",    name: "Rook",    sub: "pool noodle", rar: "common",   chars: 2816,   val: 15,    tint: "#a8ffbe", cap: "reach: floppy." },
  { no: "012", id: "orbit",   name: "Grimm",   sub: "galaxy",     rar: "uncommon",  chars: 7260,   val: 25,    tint: "#a9c9ff", cap: "already read the ending." },
  { no: "019", id: "phantom", name: "Phantom", sub: "wings",      rar: "uncommon",  chars: 15750,  val: 90,    tint: "#ece7dc", cap: "gone before the cape lands." },
  { no: "018", id: "null",    name: "Null",    sub: "star",       rar: "rare",      chars: 29260,  val: 260,   tint: "#a9c9ff", cap: "not on any record." },
  { no: "017", id: "shogun",  name: "Shogun",  sub: "gold wings", rar: "rare",      chars: 31970,  val: 490,   tint: "#ffd27a", cap: "rents you the air." },
  { no: "006", id: "ronin",   name: "Ronin",   sub: "cliff",      rar: "epic",      chars: 71680,  val: 950,   tint: "#ff8ac9", cap: "" },
  { no: "011", id: "grimm",   name: "Grimm",   sub: "cathedral",  rar: "legendary", chars: 219520, val: 2200,  tint: "#a8ffb0", cap: "" },
  { no: "015", id: "reaper",  name: "Reaper",  sub: "ember",      rar: "mythic",    chars: 701000, val: 17000, tint: "#ffc87a", cap: "" },
  { no: "020", id: "umbra",   name: "Umbra",   sub: "eclipse",    rar: "secret",    chars: 1578000, val: 40000, tint: "#ffb54a", cap: "the sun blinked first." }
];
const BY_NO = Object.fromEntries(CARDS.map(c => [c.no, c])), BY_ID = Object.fromEntries(CARDS.map(c => [c.id, c]));
// The twelve styles a Stitch can come out in (odds per Stitch, value multiplier). The default is Bone.
const STYLES = {
  steel:   { name: "Phosphor",     p: .006,  x: 3   }, dots:  { name: "Amber",    p: .005,  x: 3   },
  vhs:     { name: "Glitch",       p: .004,  x: 3.5 }, scratch: { name: "Typeset", p: .004, x: 3.5 },
  ice:     { name: "Stipple",      p: .0025, x: 5   }, chain: { name: "Linework", p: .0025, x: 5   },
  wire:    { name: "Pixel",        p: .002,  x: 6   }, print: { name: "Blood",    p: .002,  x: 6   },
  glass:   { name: "Glow",         p: .001,  x: 10  }, blood: { name: "Toxic Glitch", p: .001, x: 10 },
  leaf:    { name: "Iridescent",   p: .0006, x: 15  }, kin:   { name: "Dissolve", p: .0003, x: 25  }
};
const STYLE_TINT = { "": "#ece7dc", steel: "#aaffbd", dots: "#ffd27a", vhs: "#c9a5ff", scratch: "#ece7dc", ice: "#a9c9ff", chain: "#ece7dc", wire: "#b6ff9c", print: "#ff9a94", glass: "#ff8ac9", blood: "#a8ffb0", leaf: "#d6c9ff", kin: "#a9c9ff" };
const PACK = {
  name: "First Print", price: 499, n: 5,
  slots: [   // each slot: [card id, weight]. Tuned so about 45% of packs sell back for at least what they cost (the exact figure is worked out below).
    [["stitch", 1], ["brick", 1], ["rook", 1]],
    [["stitch", 1], ["brick", 1], ["rook", 1]],
    [["stitch", 26], ["brick", 26], ["rook", 26], ["orbit", 19], ["phantom", 3]],
    [["orbit", 38], ["phantom", 47], ["null", 9], ["shogun", 6]],
    [["orbit", 29.3], ["phantom", 13], ["null", 18.1], ["shogun", 32.5], ["ronin", 6.1], ["grimm", .9], ["reaper", .1], ["umbra", .04]]
  ]
};;
const SELLBACK = .9, START = 1000, TOPUP = 1000;
