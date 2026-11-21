# Umbra: the Secret card

The rarest card in First Print: 1 pack in about 2,500. A stick figure on a cliff under a total eclipse.

- `eclipse.png`: the base image (Figma, GPT Image 2.5 Sunburst). One stick figure with a round head and thin line limbs, a black sun with a
  blazing corona, nothing else. No text in the picture.
- `umbra_final.py`: renders it. Uses `ascii-engines/tools/ascii2.py` (copy `ascii2.py` and its `fonts/` next to this script, or run it from there).
  Duotone amber ramp, 1,500 columns x 1,052 rows.
- `umbra_card.jpg`: the full print card (1500 x 2100) with the type strip.
- `test_sheet.jpg`: the six styles tried before choosing amber (bone, aurora, edge, braille blue, amber, fire).

## The number

1,500 columns x 1,052 rows = **1,578,000 characters**: one character per pixel at print size. That is 2.25x the Mythic card (Reaper, 701,000).
Rarity is the printed character count; the red slashes after the copy id are the rarity cuts (Secret = four).

## In the app

`cards/umbra.jpg` is the picture area only (900 x 1092); the name, count, copy id and caption are drawn live so every copy carries its own id.
Rarity `secret` (4 cuts), worth $400.00, found in 0.04% of the slot-five draws.
