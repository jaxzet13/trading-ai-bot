# Requiem: the limited, physical pack

Six premium cards, three to a pack, **$65**. Each card has its own rarity (Uncommon, Rare, Epic, Legendary, Mythic, Secret), is made of far more characters than anything in First Print or Moonshot, and has a higher base worth than the best card of its rarity in those packs.

In the beta Requiem is a **preview** (`#/limited` in the app). It can't be bought or opened: there is no payment, no shipping and no collection entry for it. See "What it takes to sell it for real" below.

| | Card | Rarity | Look | Characters | Grid | Planned worth | In how many packs |
|---|---|---|---|---|---|---|---|
| R1 | Pallbearer | Uncommon | painted in fog | 1,795,200 | 1600 × 1122 | $9 | 85% |
| R2 | Vigil | Rare | cyanotype blue print | 2,806,000 | 2000 × 1403 | $18 | 89% |
| R3 | Halation | Epic | signal loss, VHS glitch | 4,039,200 | 2400 × 1683 | $55 | 1 in 4 |
| R4 | The Witness | Legendary | stipple and linocut | 5,499,200 | 2800 × 1964 | $160 | 1 in 19 |
| R5 | Orrery | Mythic | pixel cosmos | 7,180,800 | 3200 × 2244 | $520 | 1 in 156 |
| R6 | Seraph | Secret | stipple and white fire | 9,090,000 | 3600 × 2525 | $3,600 | 1 in 2,499 |

For scale: the biggest card in the other packs is Umbra, with 1,578,000 characters and a base worth of $312.50.

## The pack and its odds

Three slots (`src/js/01b-limited.js`, checked by `requiem_pack.py`):

1. Pallbearer 72%, Vigil 28%
2. Pallbearer 36%, Vigil 56.5%, Halation 6.6%, The Witness 0.9%
3. Pallbearer 14%, Vigil 63.3%, Halation 17.6%, The Witness 4.4%, Orrery 0.64%, Seraph 0.04%

Worked out exactly, with selling back at 90% of a card's worth (the rule every pack uses):

- the average value of the three cards in a pack is **$64.15**, 99% of the price
- the average sell-back is **$57.73**, 88.8% of the price (the other packs are tuned to about 90%)
- **28.5%** of packs sell back for at least $65; a typical pack sells back for $40.50; the worst possible pack sells back for $24.30

Most packs are worth less than $65 and a few are worth far more. That is how a chase pack works, so the page says it in plain words. `python requiem_pack.py` prints all of it; the page and the test (`t18.js`) compute it from the same slot tables, so a changed table can't leave a stale number on screen.

"Worth" is what each card is planned to be worth at launch. It is a guide, not a promise: once real people trade the cards, the market sets the price.

## How a card is made

`sources/` holds the six paintings (and a spare). `requiem_render.py` turns each into a card made of text:

1. crop to the picture area (1500 : 1820, like every card) and upscale to the master size, 1800 × 2184
2. grade it for the card: tone curve, saturation, local contrast, and for two cards a toned-monochrome ramp
3. lay a grid of `cols × rows` cells (cell height / width = 1.73, as in every other pack) and sample the painting into it
4. pick a glyph per cell from the card's own family (stipple, engraving, paint, glitch, blocks) so its ink matches the cell's tone, with noise so neighbours differ; on Vigil strong edges get a stroke glyph that follows the edge
5. draw each glyph in a colour that makes the cell average to the painting's colour, over a dim copy of the painting, on a 5 × 9 px supersampled canvas that is shrunk with area averaging
6. lock the low frequencies to the painting so tone and colour match exactly, keeping the glyph texture on top
7. finish: bloom, grain, vignette, and for Halation an RGB split with tracking bands and scanlines

The character count printed on a card is `cols × rows`, the real size of that grid. `python requiem_render.py --list` prints them. Two small details matter for honesty: the master is shrunk to 1800 px for the screen, so a single glyph is about a pixel wide there, and the sources are 1024 px (Orrery 1792 px) paintings. The counts are real, but fine detail comes from the painting. To show that the cards really are text, every card has a **macro** picture (`cards/rq/macro/`): a 58 × 32 patch drawn at reading size.

```
python requiem_render.py                          # all six: out/<id>.jpg (1800 x 2184), out/m/ (720 wide), out/s/ (360 wide), out/macro/
python requiem_render.py --cards seraph --no-macro
python requiem_render.py --derive --out ../../cards/rq   # only rebuild m/ and s/ from the masters
python requiem_render.py --scale 2 --out print    # print masters, 3600 x 4368
python requiem_render.py --list
python requiem_pack.py                            # the odds and the return
```

The app loads `cards/rq/m/<id>.jpg` for the tiles and the card window, `cards/rq/s/` for the lists, and links the 1800 px master as "full-size picture". Needs numpy, opencv-python and Pillow; the fonts are JetBrains Mono and DejaVu Sans Mono.

## Where the paintings came from

The six sources were generated with image models, from prompts written for this pack (see `sources/PROMPTS.md`). The prompts name no artist, brand or existing character; they borrow only a style (dark stipple and halftone, cyanotype, VHS glitch, pixel-art cosmos, painted monochrome) from the reference pictures the pack was briefed from. Five were made from text alone. **Orrery was made with the briefing's pixel-cosmos picture attached as a style reference**, so it sits closer to that picture than the others do (same palette and pixel treatment, a galaxy for a head); the subject is new. Check it against the original before printing, and repaint it if the original's artist hasn't cleared it.

Before selling anything, check the terms of the services used for commercial printing and resale, and take advice on copyright: in some places purely machine-made images can't be copyrighted, so a competitor might be free to copy them. Then decide whether to repaint or heavily rework the sources.

## What it takes to sell it for real

None of this is in the beta, and none of it is code you can finish in an afternoon:

- **Payments and orders.** The checkout is built but off: Stripe Checkout (Apple Pay, Google Pay and cards on Stripe's own page), a signed webhook, and an order record of session id, pack numbers and amount (`stickfist/STRIPE.md`, `pay.js`, `node test-pay.js`). Still yours: a Stripe account, a test-mode run with your own keys, sales tax, and refund handling.
- **Fulfilment.** Printing (see `PRINT_SPEC.md`: art needs upscaling to print size, foil and holo finishes, serial numbering), sealed packs, packing, shipping and returns.
- **Randomness you can prove.** Built: `requiem_run.py` assembles the whole run in whole cards, shuffles it and gives a SHA-256 fingerprint to publish before the sale; each paid order gets the next packs of that list, and the server shuts the sale if the file changes. Publish the list when the run sells out so buyers can check it.
- **A real limit.** "Limited" has to be true. Set `RQ.run` (packs printed) and `RQ.closes` (a date) in `src/js/01b-limited.js` before anything is sold; the page then shows them. Print exactly that many, and never reprint. Until they are set the page says there is no limit to count down to, and it shows no countdown and no "N left".
- **Rules for paid random packs.** Selling sealed random cards for real money is regulated differently in different places, and some places treat paid random packs as gambling or require odds disclosure, age checks and refund rights. Get legal advice for each place you ship to. The page already states the odds and an 18+ rule, but that is not legal sign-off.
- **Age.** The beta's 18+ box is a tick box. A real-money sale needs a proper age check.

## The proof set: every card, once, before the run

Before a real run, order one set that holds every card so you can check how each one prints. It is a proof, not a pack: it is not drawn from the odds and it is not for sale.

- **Seven cards.** One of each of the six cards, plus a second **The Witness** on foil, because whether a black-and-white card looks better with a holo sheen is a judgement you can only make in the hand.
- **Two orders, one cart.** The foil Euro poker deck (63 × 88 mm, 320 gsm black-core, holographic sheen on the face only) takes Halation, Orrery, Seraph and the second Witness. The matching plain black-core deck takes Pallbearer, Vigil and Witness. Check that the plain deck is offered at the same size.
- **Files.** `python requiem_faces.py --proof --out proof` writes the seven faces and a back at 600 dpi with a 3 mm bleed (1630 × 2221 px; check the printer's own template first and use `--dpi`, `--bleed` and `--px` to match: for The Game Crafter, whose uploader requires exactly 825 × 1125 px for the Euro Poker deck (found out the hard way: the first guess, 819 × 1113 from their 1/8" cut-line rule, was wrong), `--dpi 300 --px 825x1125`). Each face carries "PROOF · NOT FOR SALE" on the strip so it can never be mistaken for a run card. `--guides` draws the trim and safe zone on, to check by eye. The back is the existing STIXX back; design a Requiem back before a real run.
- **A paper proof today.** `python requiem_sheet.py --out proof-sheet.pdf` lays the cards at true size on one US Letter page (cut lines and crop marks included). Print it at 100% on glossy photo paper or heavy cardstock at any print shop and cut it out. It checks the fine detail, colour and name strip at card size; it cannot check foil, black-core stock or edges.
- **What to look at.** On foil: do the whites turn metallic or rainbow, and do the dark stipple cards keep their depth? On plain stock: does the fine character texture hold up, and does Pallbearer keep its blacks? Hold each next to the screen. Check the name strip is legible at the printed size.
- **Counting.** The proof set sits outside the run. Keep the numbers on the page true: if a proof Seraph exists, then "one Seraph in the run" is still true but "only one Seraph exists" is not. If any proof copy is ever sold or given away, count it and say so.
- The print faces leave off the flavour captions: they don't fit at 6.5 pt or more.

## Files

- `requiem_render.py` the renderer
- `requiem_pack.py` the odds and the return
- `requiem_run.py` assemble and fingerprint a run of sealed packs for the checkout
- `requiem_faces.py` print-size faces with bleed, and the proof set
- `requiem_sheet.py` a Letter-size sheet of the proof cards at true size, to print today
- `sources/` the paintings (`PROMPTS.md` has the prompts)
- `../../cards/rq/` the cards the app loads: masters, `m/`, `s/`, `macro/`
- `../../src/js/01b-limited.js` the pack and card data; `08b-limited.js` the page
