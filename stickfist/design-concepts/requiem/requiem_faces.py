#!/usr/bin/env python3
"""REQUIEM print faces: the whole card (picture + name strip) at print size with bleed, ready to upload to a printer, and the proof set.

The app draws the name strip in HTML; a printer needs one flat picture per card. This lays the same card out at 63 x 88 mm plus a bleed:
  - the picture (cards/rq/<id>.jpg) fills the top 1820/2100 of the card, like on screen, and is extended into the bleed by reflecting its edge
  - the strip below it: the name and the character count, then the card number and rarity with the grid size
  - the text is at least 6.5 pt and inside a 3 mm safe zone (PRINT_SPEC.md); flavour captions are left off the print face because they don't fit at that size
  - the card data (name, rarity, characters, grid, colour) is read from src/js/01b-limited.js, so the print faces can't drift from the app

    python requiem_faces.py --out print                    # six faces at 600 dpi, 3 mm bleed (1630 x 2220 px), plus the back
    python requiem_faces.py --proof --out proof            # the proof set: the same faces with "PROOF, NOT FOR SALE" on the strip
    python requiem_faces.py --guides --out guides          # trim (red) and safe zone (blue, dashed) drawn on, to check by eye
    python requiem_faces.py --dpi 300 --px 825x1125         # a printer's exact template size: this is what The Game Crafter's uploader requires (63 x 88 mm card centred in it)

Check the pixel size against the printer's own template before you upload anything: bleed and size rules differ a little between printers.
Needs numpy, opencv-python and Pillow; the font is JetBrains Mono.
"""
import argparse, os, re
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))                  # stickfist/
FONT_B = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf'
FONT_R = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf'
TRIM_W, TRIM_H = 63.0, 88.0                                              # mm
BLACK = (5, 5, 6); DIM = (141, 137, 127)
RARITY = {'uncommon': 'Uncommon', 'rare': 'Rare', 'epic': 'Epic', 'legendary': 'Legendary', 'mythic': 'Mythic', 'secret': 'Secret'}


def read_cards():
    src = open(os.path.join(ROOT, 'src', 'js', '01b-limited.js'), encoding='utf-8').read()
    pat = r'\{\s*no:\s*"(R\d)",\s*id:\s*"(\w+)",\s*name:\s*"([^"]+)",\s*rar:\s*"(\w+)",\s*chars:\s*(\d+),\s*cols:\s*(\d+),\s*rows:\s*(\d+),\s*val:\s*(\d+),\s*tint:\s*"(#[0-9a-fA-F]{6})"'
    cards = [dict(no=m[0], id=m[1], name=m[2], rar=m[3], chars=int(m[4]), cols=int(m[5]), rows=int(m[6]), val=int(m[7]), tint=tuple(int(m[8][i:i + 2], 16) for i in (1, 3, 5)))
             for m in re.findall(pat, src)]
    assert len(cards) == 6, 'expected six cards in 01b-limited.js, found %d' % len(cards)
    return cards


def spaced(d, x, y, text, font, fill, track):
    """text with letter-spacing; returns the right edge"""
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill, anchor='ls'); x += d.textlength(ch, font=font) + track
    return x - track


def sizes(dpi, bleed_mm, px=None):
    """(canvas W, canvas H, trim w, trim h, left margin, top margin) in pixels.
    Without px the canvas is the trim plus the bleed. With px the canvas is exactly that size (a printer's template) and the 63 x 88 mm card sits centred in it."""
    mm = dpi / 25.4
    tw, th = round(TRIM_W * mm), round(TRIM_H * mm)
    if px: return px[0], px[1], tw, th, (px[0] - tw) // 2, (px[1] - th) // 2
    b = round(bleed_mm * mm); return tw + 2 * b, th + 2 * b, tw, th, b, b


def face(card, dpi=600, bleed_mm=3.0, proof=False, guides=False, px=None):
    W, H, tw, th, bx, by = sizes(dpi, bleed_mm, px)
    cqw = tw / 100.0                                                      # 1% of the trim width, the unit the app's card uses
    art_h = round(th * 1820 / 2100)                                       # the picture area is 1500 : 1820 of a 1500 : 2100 card
    im = cv2.cvtColor(cv2.imread(os.path.join(ROOT, 'cards', 'rq', card['id'] + '.jpg')), cv2.COLOR_BGR2RGB)
    art = cv2.resize(im, (tw, art_h), interpolation=cv2.INTER_AREA if im.shape[1] > tw else cv2.INTER_LANCZOS4)
    art = cv2.copyMakeBorder(art, by, 0, bx, W - tw - bx, cv2.BORDER_REFLECT_101)     # into the bleed on top, left and right
    canvas = np.empty((H, W, 3), np.uint8); canvas[:] = BLACK
    canvas[0:art.shape[0], 0:W] = art
    pil = Image.fromarray(canvas); d = ImageDraw.Draw(pil, 'RGBA')
    fs1, fs2 = 4.4 * cqw, 3.7 * cqw                                      # 7.9 pt and 6.7 pt on a 63 mm card
    f1b = ImageFont.truetype(FONT_B, round(fs1)); fsm = ImageFont.truetype(FONT_R, round(fs1 * 0.52)); f2 = ImageFont.truetype(FONT_R, round(fs2))
    tint = card['tint']; x0 = bx + 7.3 * cqw; x1 = bx + 92.7 * cqw
    y1 = by + th * 0.885 + fs1                                            # baseline of the name line
    # the character count, right-aligned: the number, then a small "chars"
    num = f"{card['chars']:,}"; unit = 'chars'
    wu = d.textlength(unit, font=fsm) + 0.08 * fs1 * 0.52 * (len(unit) - 1); wn = d.textlength(num, font=f1b)
    d.text((x1 - wu, y1), unit, font=fsm, fill=tint + (140,), anchor='ls'); d.text((x1 - wu - 0.55 * fs1 * 0.52 - wn, y1), num, font=f1b, fill=tint + (255,), anchor='ls')
    xr = x1 - wu - 0.55 * fs1 * 0.52 - wn - 2.4 * cqw
    # the name, letter-spaced, then a hairline to the count
    name = card['name'].upper(); xe = spaced(d, x0, y1, name, f1b, tint + (255,), 0.2 * fs1)
    d.line([(xe + 2.4 * cqw, y1 - 0.32 * fs1), (xr, y1 - 0.32 * fs1)], fill=tint + (77,), width=max(1, round(cqw * 0.12)))
    # the second line: number and rarity on the left, the grid (or PROOF) on the right
    y2 = y1 + fs2 * 0.92 + 1.5 * cqw
    d.text((x0, y2), f"{card['no']} \u00b7 {RARITY[card['rar']]}", font=f2, fill=DIM + (255,), anchor='ls')
    right = 'PROOF \u00b7 NOT FOR SALE' if proof else f"{card['cols']:,} \u00d7 {card['rows']:,}"
    d.text((x1, y2), right, font=f2, fill=(DIM + (255,)) if not proof else (255, 90, 80, 255), anchor='rs')
    if guides: draw_guides(d, W, H, bx, by, tw, th, dpi, px is not None)
    return np.asarray(pil.convert('RGB'))


def dashed(d, x0, y0, x1, y1, dash, color, width):
    for x in range(x0, x1, dash * 2): d.line([(x, y0), (min(x + dash, x1), y0)], fill=color, width=width); d.line([(x, y1), (min(x + dash, x1), y1)], fill=color, width=width)
    for y in range(y0, y1, dash * 2): d.line([(x0, y), (x0, min(y + dash, y1))], fill=color, width=width); d.line([(x1, y), (x1, min(y + dash, y1))], fill=color, width=width)


def draw_guides(d, W, H, bx, by, tw, th, dpi, template):
    """red: the 63 x 88 mm card. blue dashed: the safe zone. With a template size, orange: a printer's own cut line (1/8 inch in from the image edge, as The Game Crafter states)."""
    mm = dpi / 25.4; wd = max(1, round(mm * 0.15))
    d.rectangle([bx, by, bx + tw - 1, by + th - 1], outline=(255, 40, 40, 255), width=wd)
    if template:
        c = round(dpi / 8); d.rectangle([c, c, W - c - 1, H - c - 1], outline=(255, 160, 40, 255), width=wd)
        s = round(dpi / 4); dashed(d, s, s, W - s, H - s, round(mm * 2), (70, 150, 255, 255), wd)
    else:
        s = round(3 * mm); dashed(d, bx + s, by + s, bx + tw - s, by + th - s, round(mm * 2), (70, 150, 255, 255), wd)


def back(dpi=600, bleed_mm=3.0, px=None):
    """the existing STIXX back (exports/card-back), fitted to the same canvas. Design a Requiem back before a real run: the back can never change."""
    W, H = sizes(dpi, bleed_mm, px)[:2]
    im = cv2.cvtColor(cv2.imread(os.path.join(ROOT, 'exports', 'card-back', 'STIXX_back_MPC_63.5x88.9_bleed.png')), cv2.COLOR_BGR2RGB)
    return cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA if im.shape[1] > W else cv2.INTER_LANCZOS4)


def save(arr, path, fmt, dpi):
    os.makedirs(os.path.dirname(path), exist_ok=True); im = Image.fromarray(arr)
    if fmt == 'png': im.save(path, dpi=(dpi, dpi), optimize=True)
    else: im.save(path, quality=95, subsampling=0, dpi=(dpi, dpi))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', default=os.path.join(HERE, 'print')); ap.add_argument('--cards', default='')
    ap.add_argument('--dpi', type=int, default=600); ap.add_argument('--bleed', type=float, default=3.0, help='bleed in mm on every side')
    ap.add_argument('--px', default='', help='exact canvas size, e.g. 825x1125 (what The Game Crafter requires for its Euro Poker deck: use with --dpi 300)')
    ap.add_argument('--proof', action='store_true'); ap.add_argument('--guides', action='store_true'); ap.add_argument('--format', default='png', choices=['png', 'jpg'])
    a = ap.parse_args()
    px = tuple(int(v) for v in a.px.lower().split('x')) if a.px else None
    cards = read_cards(); want = set(a.cards.split(',')) - {''}
    sheet = []
    for c in cards:
        if want and c['id'] not in want and c['no'] not in want: continue
        arr = face(c, a.dpi, a.bleed, a.proof, a.guides, px); _, _, tw, th, bx, by = sizes(a.dpi, a.bleed, px); sheet.append(arr[by:by + th, bx:bx + tw])
        save(arr, os.path.join(a.out, f"{c['no']}-{c['id']}.{a.format}"), a.format, a.dpi); print(f"{c['no']} {c['name']}: {arr.shape[1]} x {arr.shape[0]} px")
    bk = back(a.dpi, a.bleed, px); save(bk, os.path.join(a.out, f'back.{a.format}'), a.format, a.dpi); sheet.append(bk[by:by + th, bx:bx + tw])  # the contact sheet shows the cut cards, without the bleed
    h = 900; row = [cv2.resize(x, (round(x.shape[1] * h / x.shape[0]), h), interpolation=cv2.INTER_AREA) for x in sheet]
    save(np.hstack([np.pad(x, ((0, 0), (0, 12), (0, 0)), constant_values=12) for x in row[:4]]) if len(row) <= 4 else
         np.vstack([np.hstack([np.pad(x, ((0, 12), (0, 12), (0, 0)), constant_values=12) for x in row[:4]]), np.hstack([np.pad(x, ((0, 12), (0, 12), (0, 0)), constant_values=12) for x in (row[4:] + [np.zeros_like(row[0])] * 4)[:4]])]),
         os.path.join(a.out, 'sheet.jpg'), 'jpg', 150)


if __name__ == '__main__':
    main()
