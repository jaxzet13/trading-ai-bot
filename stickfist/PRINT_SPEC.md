# StickFist card print spec (v1)

The card face in `index.html` (`cardHTML`, `.kcard` styles) is the reference layout. In the app, open any card in the binder and press **Print guides** to see the trim (red line) and the safe zone (blue dashes) drawn on the card.

## Size

| | mm | inches | pixels at 300 dpi |
|---|---|---|---|
| Trim (finished card) | 63 × 88 | 2.48 × 3.46 | 744 × 1039 |
| With 3 mm bleed on all sides | 69 × 94 | 2.72 × 3.70 | 815 × 1110 |
| Safe zone (3 mm inside trim) | 57 × 82 | | 673 × 969 |
| Corner radius | 3 mm | | |

- Every printed element except the full-bleed art and the ink strike stays inside the safe zone. That covers the name, weapon line, power seal, rarity mark and collector line.
- Art runs into the bleed on borderless cards (Ultra and up). On bordered cards, the black border runs into the bleed.
- Ask your printer for their own template before you send files. Bleed and safe-zone rules differ slightly between printers.

## Art resolution: needs work before print

The current card art is 600 × 893 px. That is enough for the screen but **below print size**: a full-bleed card needs at least **815 × 1110 px**, and **1630 × 2220 px** is better for sharp linework. Before production:

1. Upscale each artwork 2–3× (Higgsfield `upscale_image` works) or regenerate it at a higher resolution.
2. Check every upscale at 100% for warped hands, weapons and text-like artifacts.

## Layers sent to the printer (per card)

1. **CMYK art + frame**: everything visible, flattened, at 300 dpi or more, with the bleed.
2. **Foil mask**: solid 100% black vector shapes where foil goes, aligned to the CMYK file. Foil registration is about ±0.5 mm, so foil shapes stay at least 1 mm away from fine text.
3. **Spot UV mask**: the power seal, and the strike on cards that have no foil.
4. **Holo or rainbow laminate**, where the rarity calls for it (see below).

Fonts go in as outlines. The small collector line is solid 100% K black or white, not a 4-colour build.

## Rarity = finish

| Rarity | Mark | Border | Ink strike | Special finish |
|---|---|---|---|---|
| Common | ● | Black | Black ink | None |
| Uncommon | ◆ | Black | Indigo ink | None |
| Rare | ★ | Black | Crimson ink | None |
| Foil Rare | ★ | Black | Silver foil | Holo laminate on the art window |
| Signature | ★★ | Gold | Black, gold name | Gold foil name and seal ring |
| Ultra | ★★ | Borderless | Silver foil | Etched (textured) foil and light holo |
| Illustration | ★ | Borderless | None (name in outline) | Matte art, spot UV on the name |
| Masterwork | ★★ | Borderless | Rainbow foil | Rainbow holo laminate over the full card |
| Gilded | ★★★ | Borderless | Gold foil | Gold foil and gold-toned art |
| Reverse Foil | (base mark) | Holo border | Base ink | Holo laminate on the border, art stays matte |
| Bloodmoon (limited) | ◐ / ◐◐ / ● | Black | Blood-red ink, red foil on Ultra and up | Red duotone art on base cards; serial-numbered super rare |
| Gold Scroll (limited) | ◇ / ✦✦ / ✦✦✦ | Indigo brocade | Gold foil | Gold-leaf texture on Ultra and up |

## Stock

- A black-core (or blue-core) card stock around 310 gsm, so the cards can't be seen through or easily faked, and so they shuffle like a real TCG.
- Linen or smooth finish: get a sample of each.
- Same card back for every card. Design it before the first print run, because it can never change once the set exists.

## Scan ID

Each face leaves a blank strip at the bottom. Print the scan ID there on its own black-ink pass so every physical copy is unique: `IS-014-000123` (set, collector number, serial) and a QR code that encodes `STICKFIST:IS-014-000123`. The serial is assigned at print time, so the faces themselves never change between copies.

## Before the first run

- Order a printed proof of one card per rarity and per limited set, and check foil placement, colour and text size by hand.
- Text minimum on the face is 6.5 pt (the collector line). Everything else is larger.
- Serial-number the limited super rares (for example, 0412/0500) on a dedicated foil or ink pass, which makes them harder to fake.
- Keep the print run numbers you advertise (for example, "5,000 packs") identical to what you actually print.
