# Rarity = resolution

Every card's picture is built from a fixed grid of monospace characters. A rarer card has a finer grid, and the card prints
its exact character count (columns x rows of the picture; spaces are characters too). The number IS the rarity mark.

| Rarity | Columns | Rows | Characters on the card | Corner cuts |
|---|---|---|---|---|
| Common | 56 | 39 | 2,184 | 0 |
| Uncommon | 70 | 49 | 3,430 | 0 |
| Rare | 86 | 60 | 5,160 | 1 |
| Foil Rare | 106 | 74 | 7,844 | 1 |
| Signature | 130 | 91 | 11,830 | 2 |
| Chrome | 156 | 109 | 17,004 | 2 |
| Full Art | 184 | 129 | 23,736 | 2 |
| Masterwork | 214 | 150 | 32,100 | 2 |
| Gilded | 246 | 172 | 42,312 | 3 |
| Completer | 280 | 196 | 54,880 | 3 |

Brightness is calibrated so every tier has the same overall tone: only the detail changes.
Tiers from Signature up use a bold typeface so the thin strokes survive. Code: tools/ascii_card.py (the TIERS table).
