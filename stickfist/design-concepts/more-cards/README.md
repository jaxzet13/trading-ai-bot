# More cards for both packs

Twelve new cards so the packs repeat less. Each one joins a card of the **same rarity and the same worth**, and takes half of that card's chance in every slot, so what a pack returns (First Print 89.1%, Moonshot 90.8%) and how often it sells back at least its price (50.7%, 49.3%) are exactly what they were. Only the variety changed: a First Print pack now shows 4.5 different cards on average (was 4.0) and ten packs show about 12 different cards (was 7); a Moonshot pack shows 4.1 (was 2.4) and ten packs show about 9 (was 3.5).

| No. | Card | Pack | Rarity | Picture | Characters | Worth (joins) |
|---|---|---|---|---|---|---|
| 026 | Mop | First Print | Common | stick figure, bucket helmet, mop for a sword | 64 x 44 = 2,816 | like Stitch |
| 027 | Pan | First Print | Common | frying pan shield, spatula sword | 2,816 | like Brick |
| 028 | Cone | First Print | Common | arms crossed, traffic cone hat | 2,816 | like Rook |
| 029 | Tempest | First Print | Uncommon | a storm vortex and one lightning bolt | 110 x 66 = 7,260 (cell 2.0) | like Orbit |
| 030 | Surge | First Print | Uncommon | one huge curling wave, a tiny surfer | 150 x 105 = 15,750 | like Phantom |
| 031 | Kraken | First Print | Rare | tentacles out of black water, a lantern in a rowboat | 200 x 140 = 28,000 | like Shogun |
| 032 | Spark | Moonshot | Common | a sparkler held high | 72 x 50 = 3,600 | like Fuse |
| 033 | Countdown | Moonshot | Uncommon | a big "3" and a launch button | 120 x 84 = 10,080 | like Ignition |
| 034 | Booster | Moonshot | Rare | side boosters splitting away | 240 x 168 = 40,320 | like Liftoff |
| 035 | Flare | Moonshot | Common | a signal flare thrown at the sky | 3,600 | like Fuse |
| 036 | Bubble | Moonshot | Common | fishbowl helmet, thumbs up | 3,600 | like Fuse |
| 037 | Gantry | Moonshot | Uncommon | the tower arm swinging off a rocket | 10,080 | like Ignition |

The pictures are in `sources/` (1024 x 1536 or 688 x 1024, black background, thick simple shapes: if you cannot see what is happening at 150 pixels wide, it is too busy). They were generated with GPT Image 2.6 (Higgsfield) and GPT Image 2.5 Sunburst (Figma), prompts in the style of `../moonshot/README.md`. Each card is rendered by `../style-all/style_all.py`, the same script and the same twelve style definitions as every other card, so the plain look and the 12 chance styles (900 x 1092, JPEG, 170 KB at most) match:

```
python ../style-all/style_all.py --cards mop,pan,cone,tempest,surge,kraken,spark,countdown,booster,flare,bubble,gantry --default
python ../../make_thumbs.py        # the small copies in cards/s/
```

Kraken's plain look is the `aurora` iridescent palette; Surge's is `classic / ice`; the rest follow their pack's family (commons phosphor, bone or amber, Moonshot amber and phosphor).
