# Moonshot, the second pack

One launch, five altitudes. The higher the card, the rarer it is, and the more characters it is made of. A pack holds five cards from this set
(price about $5.79 at base, it follows the market like First Print's), so the five rarities are the five heights of one rocket.

| No. | Card | Rarity | Scene | Plain look | Characters | Base worth |
|---|---|---|---|---|---|---|
| 021 | Fuse | Common | a stick figure lights a very long fuse | amber, classic ramp | 72 x 50 = 3,600 | $0.12 |
| 022 | Ignition | Uncommon | at the foot of a rocket, the first flame | amber duotone | 120 x 84 = 10,080 | $0.30 |
| 023 | Liftoff | Rare | the rocket clears the tower on a column of fire | blood duotone | 240 x 168 = 40,320 | $7.80 |
| 024 | Apogee | Epic | floating beside the nose cone at the edge of space | cyan VHS glitch | 420 x 294 = 123,480 | $12.50 |
| 025 | Luna | Legendary | planting a flag on the Moon, Earth rising behind | iridescent, a new cool `moon` palette | 800 x 561 = 448,800 | $32.00 |

Copy ids start with `MS` (`MS025-000001-XXXX`); First Print's start with `IS`.

## How the art was made
- `sources/<id>.jpg` are 1360 x 2048 images from GPT Image 2.6 (high quality, 2k, 2:3), prompted like the First Print sources: ONE stick figure (round head,
  thin line limbs) in a dark cinematic scene lit and grained like a photograph, one strong light, no text.
- `fuse` is a very coarse 72-column card, so the figure has to survive a grid of about 10 pixels per character. `sources/fuse_bold.jpg` is the same picture
  with only its thin bright strokes kept (the outline, the rope, the flame: a top-hat on the brightness, so broad glow on the ground drops out) and fattened.
- Every card's plain look and its 12 styles come from `../style-all/style_all.py`, which now knows these five cards and a `--default` option:

```
python ../style-all/style_all.py --cards fuse,ignition,liftoff,apogee,luna --default --out ../../cards
```

  That writes `cards/<id>.jpg` plus `cards/<id>-<style>.jpg` for the 12 styles (65 images, 900 x 1092). The `moon` palette (cyan to blue) was added to
  `../style-deck/tools/ascii2.py` for Luna; the existing palettes are untouched.

## The odds
Slot by slot (see `PACKS` in `src/js/01-data.js`): cards 1 and 2 are almost always a Fuse, card 3 is low altitude with a small chance of a Liftoff, card 4 is
an Ignition or better, card 5 is the best card in the pack (Liftoff about 22%, Apogee about 6%, Luna about 1 in 200). Tuned so the pack returns about 89 to
90% on average when you sell, and about 43% of packs sell back at least what they cost (First Print: 89.5% and 44%), checked across many market states.
Liftoff is worth more than a pack costs, which is what keeps the hit rate steady as the market moves.
