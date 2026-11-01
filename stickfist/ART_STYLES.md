# Card faces and style map

Every card's **whole face** (art, frame, name, power) is one finished image generated on Higgsfield (`gpt_image_2_5`, 2:3), saved in `art/face/<no>.jpg`. Each card wears one of the 10 frame styles from `design-concepts/`, matched to its art. Commons and Uncommons get the style's plain look, Rare to Signature get added accents, and Ultra and up get the full Mythic look (gold, chrome, holo, glow).

The site draws **only the scan ID** on top, in the blank strip each face leaves at the bottom: `IS-014-000123` (set, collector number, the copy's own serial) plus a QR code encoding `STICKFIST:IS-014-000123`. Mythics also get a live holo sheen and light sweep on screen.

Face prompt recipe: *Finished trading card front, flat and straight-on, the card fills the whole image... Use the reference image as the card artwork... {frame style with the name and power}. The only text on the card is "NAME" and "POWER", spelled exactly. Leave a plain empty strip along the bottom edge of the card with nothing on it.* The reference image is the card's art from the table below.

For print, regenerate the final faces at 2k or upscale them, and print the scan ID on its own pass (see PRINT_SPEC.md).

## Source artwork per card (used as the reference for each face)

New art lives in `art/c/<no>.jpg`. The existing comic art in `art/<fighter>.jpg` goes on that fighter's top card. Limited cards with their own art use `art/<set>_<fighter>.jpg`.

| No. | Fighter | Rarity | Style | File |
|---|---|---|---|---|
| 001 | Knuckles | C | Sumi ink on rice paper | `art/c/001.jpg` |
| 002 | Shiv | C | Swiss minimal | `art/c/002.jpg` |
| 003 | Bulwark | C | Graphite pencil sketch on faint blue graph paper | `art/c/003.jpg` |
| 004 | Pike | C | Blueprint technical drawing | `art/c/004.jpg` |
| 005 | Bo | C | Single-colour linocut print | `art/c/005.jpg` |
| 006 | Ronin | U | Two-colour Japanese woodblock print | `art/c/006.jpg` |
| 007 | Reaver | U | Risograph two-colour print | `art/c/007.jpg` |
| 008 | Breaker | U | Constructivist propaganda poster | `art/c/008.jpg` |
| 009 | Lash | U | Black-and-white manga panel | `art/c/009.jpg` |
| 010 | Snap | U | Pop-art comic | `art/c/010.jpg` |
| 011 | Arcanist | R | Cathedral stained glass window | `art/c/011.jpg` |
| 012 | Twinblade | R | Night silhouette | `art/c/012.jpg` |
| 013 | Fletch | R | Classic ukiyo-e | `art/c/013.jpg` |
| 014 | Kusari | R | Brush-strike on paper | `art/c/014.jpg` |
| 015 | Reaper | H | Art nouveau tarot | `art/c/015.jpg` |
| 016 | Colossus | H | Ancient stone relief carving | `art/c/016.jpg` |
| 017 | Shogun | H | Black lacquer folding screen | `art/c/017.jpg` |
| 018 | Null | H | Inverted negative print | `art/c/018.jpg` |
| 019 | Phantom | H | Street graffiti | `art/c/019.jpg` |
| 020 | Umbra | H | Film noir | `art/c/020.jpg` |
| 021 | Reaper | RR | Copperplate etching | `art/c/021.jpg` |
| 022 | Colossus | RR | Original comic art | `art/colossus.jpg` |
| 023 | Shogun | RR | Embroidered silk tapestry | `art/c/023.jpg` |
| 024 | Null | RR | Celestial star chart | `art/c/024.jpg` |
| 025 | Chrono | RR | Clockwork cutaway | `art/c/025.jpg` |
| 026 | Ronin | UR | Original comic art | `art/ronin.jpg` |
| 027 | Reaver | UR | Original comic art | `art/reaver.jpg` |
| 028 | Arcanist | UR | Original comic art | `art/arcanist.jpg` |
| 029 | Twinblade | UR | Original comic art | `art/twinblade.jpg` |
| 030 | Fletch | UR | Original comic art | `art/fletch.jpg` |
| 031 | Snap | UR | Original comic art | `art/snap.jpg` |
| 032 | Knuckles | IR | Original comic art | `art/knuckles.jpg` |
| 033 | Shiv | IR | Original comic art | `art/shiv.jpg` |
| 034 | Bulwark | IR | Original comic art | `art/bulwark.jpg` |
| 035 | Pike | IR | Original comic art | `art/pike.jpg` |
| 036 | Bo | IR | Original comic art | `art/bo.jpg` |
| 037 | Lash | IR | Original comic art | `art/lash.jpg` |
| 038 | Reaper | SIR | Original comic art | `art/reaper.jpg` |
| 039 | Null | SIR | Original comic art | `art/null.jpg` |
| 040 | Shogun | SIR | Mythic gold and chrome | `art/c/040.jpg` |
| 041 | Kusari | SIR | Original comic art | `art/kusari.jpg` |
| 042 | Phantom | SIR | Original comic art | `art/phantom.jpg` |
| 043 | Null | HR | Mythic gold leaf void | `art/c/043.jpg` |
| 044 | Shogun | HR | Original comic art | `art/shogun.jpg` |
| 045 | Chrono | HR | Original comic art | `art/chrono.jpg` |
| 046 | Breaker | UR | Original comic art | `art/breaker.jpg` |
| 047 | Umbra | UR | Original comic art | `art/umbra.jpg` |
| BM1 | Shiv | R | Blood-red duotone watercolour | `art/c/BM1.jpg` |
| BM2 | Lash | R | Red tattoo flash | `art/c/BM2.jpg` |
| BM3 | Umbra | R | Layered paper cut | `art/c/BM3.jpg` |
| BM4 | Kusari | UR | Original comic art (limited) | `art/bm_kusari.jpg` |
| BM5 | Chrono | UR | Original comic art (limited) | `art/bm_chrono.jpg` |
| BM6 | Phantom | SIR | Original comic art (limited) | `art/bm_phantom.jpg` |
| GS1 | Bo | R | Hand scroll painting | `art/c/GS1.jpg` |
| GS2 | Pike | R | Chinese papercut | `art/c/GS2.jpg` |
| GS3 | Bulwark | R | Heraldic woodcut crest | `art/c/GS3.jpg` |
| GS4 | Shogun | UR | Original comic art (limited) | `art/gs_shogun.jpg` |
| GS5 | Fletch | UR | Original comic art (limited) | `art/gs_fletch.jpg` |
| GS6 | Ronin | SIR | Original comic art (limited) | `art/gs_ronin.jpg` |

## Source-art prompt recipe (gpt_image_2_5, 2:3)

`<style description>. <fighter description>. Full-bleed trading card illustration, edge to edge, portrait. The character is a minimalist stickman: round head with no face, thick rounded limbs, a single torso line, no hand or foot detail. Keep the top 14% and bottom 12% of the image calm because text will be overlaid there. No text, no letters, no numbers, no logos, no signature, no card border, no frame.` Then add either `Do not use any gold, metallic, chrome, holographic or glowing effects.` (non-mythic) or `Premium mythic finish allowed.` (mythic).

Generated art is 688 × 1024 px. Upscale it before print (see PRINT_SPEC.md).
