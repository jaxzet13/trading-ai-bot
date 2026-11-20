# Grain print and ASCII

Base art: Figma GPT Image 2.5 Sunburst, prompted for one lone figure in a big black-and-white scene (sources/). Both styles are deterministic filters on top:

- grain: tone curve + bloom, then a stochastic threshold against clumped random noise (grain_style.py). The name is rendered first (name_mask.js) and printed THROUGH the grain (grain_card.py); the copy ID and corner cuts go on top (grain_cards.js).
- ascii: the figure rebuilt from monospace glyphs, denser = brighter (ascii_card.py).

Tints: bw, blue, red, olive, brass (map to the limited sets: Frostbite blue, Venom olive, Gold Scroll brass, Bloodmoon red).
