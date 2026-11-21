# Style variants for every card

`style_all.py` renders the 12 ASCII "chance" styles (Phosphor, Amber, Glitch, Typeset, Stipple, Linework, Pixel, Blood, Glow, Toxic Glitch,
Iridescent, Dissolve) for each card, the way `style-deck/tools/style_deck.py` did for Stitch. The 12 style definitions (engine, palette, ramp,
glow) are copied from that script unchanged, so every card's Phosphor is the same green, Amber the same amber, and so on.

Output: `cards/<cardId>-<key>.jpg`, 900 x 1092, the picture area only (no name, id or frame), keys `steel dots vhs scratch ice chain wire print glass
blood leaf kin`. The default look `cards/<cardId>.jpg` is never written. Each image is a full 1500 x 2100 card from `ascii2` / `ascii3`, cropped to the
top 1820 rows and resized with `cv2.INTER_AREA` (the same as `umbra/umbra_final.py`), saved as JPEG at quality 80, stepped down only when the file
passes 170 KB (dense, bright, photographic cards need quality 56 to 70 for that).

```
python style_all.py                        # 10 cards x 12 styles into ../../cards
python style_all.py --cards phantom,null   # some cards
python style_all.py --styles steel,kin     # some styles
python style_all.py --out DIR --tmp DIR    # elsewhere (the scratch PNGs are 1500 x 2100)
python style_all.py --list                 # grids and source art
```

It needs `ascii2.py` / `ascii3.py` from `../style-deck/tools` and the fonts in `../ascii-engines/tools/fonts`; nothing is copied here.
reaper (701,000 characters) and umbra (1,578,000) take 1.5 to 3 minutes per ramp-style image; the rest are seconds.

## What is per card

| card | source art | grid (cols x rows) | cell aspect | framing | Typeset line |
|---|---|---|---|---|---|
| brick | funny-commons/sources/brick.png | 64 x 44 = 2,816 | 1.73 | crop | it is a colander. it works. |
| rook | funny-commons/sources/rook.png | 64 x 44 = 2,816 | 1.73 | crop | reach: floppy. |
| orbit | ascii-engines/sources/galaxy.png | 110 x 66 = 7,260 | 2.0 | view | already read the ending. |
| phantom | ascii-engines/sources/winged.png | 150 x 105 = 15,750 | 1.73 | view | gone before the cape lands. |
| null | ascii-engines/sources/star.png | 220 x 133 = 29,260 | 2.0 | view | not on any record. |
| shogun | ascii-engines/sources/wings.png | 230 x 139 = 31,970 | 2.0 | view | rents you the air. |
| ronin | stick-figures-four/sources/2-rare-ronin-71680.png | 320 x 224 = 71,680 | 1.73 | view | no master. no map. |
| grimm | stick-figures-four/sources/3-epic-grimm-219520.png | 560 x 392 = 219,520 | 1.73 | view | the walls remember. |
| reaper | stick-figures-four/sources/4-legendary-reaper-701000.png | 1000 x 701 = 701,000 | 1.73 | view | still warm. |
| umbra | umbra/eclipse.png | 1500 x 1052 = 1,578,000 | 1.73 | crop (umbra_final.py) | the sun blinked first. |

- Every style of a card uses the same grid, so every style prints the same character count as the default. `rows = int(1820 / (1500 / cols * aspect))`.
  orbit, null and shogun were drawn on a taller cell (aspect 2.0), which is the only way 7,260 / 29,260 / 31,970 come out as cols x rows, so their variants
  use it too (ramp glyphs are capped to the cell width there so they do not overlap).
- `view = (cx, cy, vh)` frames the card like the default look: centred on (cx, cy) of the source with `vh` of the source height visible. The numbers were
  fitted by correlating the source against the existing `cards/<id>.jpg`. `crop` / `pad` are ascii2's own options (brick, rook, umbra).
- `tone` (black / white / gamma, and `thick`) is a per-card exposure for the styles that need it: a dark, thin or photographic source (orbit, phantom,
  ronin, grimm, reaper) reads far too dim or too blown out at Stitch's tone. `tone_except` lists the styles that keep the stock numbers, `over` is a per-style
  tweak (Pixel on a bright photo, Typeset threshold, Linework fill on shogun).

## Known limits

- brick and rook are 64 x 44 grids, so Pixel and Dissolve read as pixel art, not text (same as Stitch).
- Typeset on umbra (1 px cells) is a texture of overlapping letters that reads as a white high-contrast silhouette, not legible text.
- Stipple (braille) is the engine the null and shogun defaults already use, so those two variants are close to the default look.
- Linework (edge engine) on shogun is a dim grey wing outline (the wings are a flat bright area, so only the rim has edges); on grimm it needed `edge_k=0.22` to show any lines.
- Typeset on shogun shows diagonal stripes (the 230-column rows are not a multiple of the 21-character line).
- Pixel (blocks) on the bright photographic cards (shogun, reaper) loses the sky detail to flat bright areas by design.
- Dense full-frame styles on ronin and shogun end up at 165 to 205 KB at quality 56 (the floor), over the 170 KB target; everything else is under it.
