/* ============================================================================
   1b. REQUIEM. The limited, physical pack: six cards, three to a pack, $65.
   In the beta this is a preview only. Nothing here can be opened, and the cards are not in anyone's collection or in the market. A real-money purchase of the physical pack exists in pay.js but stays off unless the server is set up for it (STRIPE.md): the page shows the buy box only when the server says the sale is open.
   Values are what each card is planned to be worth at launch (cents): a guide, not a promise. The odds are exact, and are worked out from the slot tables below
   (the same maths as the other packs, checked by design-concepts/requiem/requiem_pack.py).
   A real limit is published here BEFORE anything is sold: run = how many packs are printed, closes = the date orders close (ISO, e.g. "2027-02-14").
   While both are null the page says so. There is no countdown and no "only N left": a limit that is not real is not shown.
   ========================================================================== */
const RQ = {
  id: "rq", name: "Requiem", price: 6500, n: 3, run: null, closes: null,
  cards: [
    { no: "R1", id: "pallbearer", name: "Pallbearer", rar: "uncommon",  chars: 1795200, cols: 1600, rows: 1122, val: 900,    tint: "#b8c4d6", look: "Painted in fog",        sub: "four carry, one listens", fin: "Matte, spot-gloss name", cap: "four carry. one is listening." },
    { no: "R2", id: "vigil",      name: "Vigil",      rar: "rare",      chars: 2806000, cols: 2000, rows: 1403, val: 1800,   tint: "#8fb4ff", look: "Cyanotype blue print",  sub: "lantern and wing",        fin: "Silver foil name and lantern", cap: "the lantern is for the living." },
    { no: "R3", id: "halation",   name: "Halation",   rar: "epic",      chars: 4039200, cols: 2400, rows: 1683, val: 5500,   tint: "#ff9ad8", look: "Signal loss, VHS glitch", sub: "faceless saint",       fin: "Rainbow holo on the glitch bands", cap: "the saint stayed. the tape did not." },
    { no: "R4", id: "witness",    name: "The Witness", rar: "legendary", chars: 5499200, cols: 2800, rows: 1964, val: 16000,  tint: "#f2efe6", look: "Stipple and linocut",   sub: "the eye over the graves", fin: "Etched silver foil on the eye", cap: "it does not blink. it counts." },
    { no: "R5", id: "orrery",     name: "Orrery",     rar: "mythic",    chars: 7180800, cols: 3200, rows: 2244, val: 52000,  tint: "#7fa8ff", look: "Pixel cosmos",          sub: "the king of planets",     fin: "Blue star-holo over the planets", cap: "he keeps the planets. they keep time." },
    { no: "R6", id: "seraph",     name: "Seraph",     rar: "secret",    chars: 9090000, cols: 3600, rows: 2525, val: 360000, tint: "#d9ccff", look: "Stipple and white fire", sub: "six wings, one spear",   fin: "Full-card holo, serial-numbered", cap: "the sky was only the first thing it opened." }
  ],
  // the planned print finish of each card: a proposal, confirmed after printer proofs (see PRINT_SPEC.md)
  // each slot is a list of [card id, weight]; a card is picked in proportion to its weight
  slots: [
    [["pallbearer", 72], ["vigil", 28]],
    [["pallbearer", 36], ["vigil", 56.5], ["halation", 6.6], ["witness", .9]],
    [["pallbearer", 14], ["vigil", 63.3], ["halation", 17.6], ["witness", 4.4], ["orrery", .64], ["seraph", .04]]
  ],
  slotNames: ["Card 1: Pallbearer or Vigil", "Card 2: Pallbearer or Vigil, sometimes better", "Card 3: the best card in the pack"]
};
const RQ_BY_ID = Object.fromEntries(RQ.cards.map(c => [c.id, c]));
