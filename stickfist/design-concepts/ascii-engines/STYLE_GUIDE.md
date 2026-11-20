# STIXX ASCII style guide (what works, so it does not have to be rediscovered)

The picture is turned into characters by an ENGINE. Rarity = how many characters (the card prints the count). `tools/ascii3.py` has the engines
(plus the classic brightness-ramp engine in ascii2.py); the type strip (name, hairline, count, ID, caption) is shared.

| Engine | What the characters are | Best for | Notes |
|---|---|---|---|
| classic (ascii2) | brightness ramp, 10 to 70 symbols | bold bright figures; Common | the count ladder: 2,816 up to 700,000 |
| braille | 2x4 dot cells chosen stochastically (8 dots per character) | glowing shapes on black, grain-print look | count is characters; dots = 8x |
| edge | `\| - / \` following outlines over a faint fill | winged / feathered / ragged silhouettes, line art | needs rim light or strong edges |
| blocks | half-block pixels in 6 flat colours | pixel-art look; `smooth_until` dissolves from smooth (top) to pixel (bottom) | the galaxy-head effect |
| text | the figure typeset from its own caption, words kept in order | BRIGHT figures on black | a dark figure disappears: text only prints where the picture is bright |

Lessons
- Thin dark figures vanish at low character counts. Use bold bright silhouettes for low tiers; `thick=` thickens strokes; `crop=` zooms on the subject.
- Tune the black point per image: a bright scene needs `black` around 0.4, a dark one around 0.03.
- Colour: `pal=` per style (classic: bone phosphor amber blood ice; duo: blue magenta acid amber blood; glitch: violet red toxic cyan hot; irid: oil fire toxic aurora candy).
- Never draw type over the picture: the art ends at 1820 px and fades into a clear strip; the type sits there (name, hairline, count, ID, optional caption).
- Print sizes at 600 dpi: name and count 46 px (about 5.5 pt), ID 30 px (about 3.6 pt).
- Fonts (tools/fonts): vt323, sharetech, major, spacemono, cutive, syne, nova, anon (Google Fonts, OFL), plus DejaVu Sans Mono (braille and block glyphs), JetBrains Mono, FreeMono.
- Humor ladder: Common = serious stick figure with ridiculous gear (frog hat, colander); rarer = pure badass.
- Base images: Figma GPT Image 2.5 Sunburst, prompted for ONE stick figure (round head, thin line limbs) in a dark cinematic scene with strong light; avoid film frames; no AI image should carry text.
