#!/usr/bin/env python3
"""A US Letter sheet of the proof cards at true size (63 x 88 mm), to print today on any printer and cut out by hand.

It checks what a quick print can check: do the fine details and the dark stipple hold up at card size, are the colours right, is the name strip readable.
It can't check foil, black-core stock or edge finish; only a real proof can.

    python requiem_sheet.py --out proof-sheet.pdf     # 8 up: the seven proof cards and the back (3 x 3, one slot empty)

Print it at 100% / "actual size" (not "fit to page") on glossy photo paper or heavy matte cardstock. Cut on the grey lines.
"""
import argparse, os
import numpy as np
from PIL import Image, ImageDraw
import requiem_faces as RF

DPI = 300


def build():
    cards = RF.read_cards(); faces = []
    for c in cards: faces.append(RF.face(c, DPI, 0.0, True, False, None))             # trim only, no bleed
    faces.insert(4, faces[3])                                                          # a second Witness (the foil comparison) next to the first
    faces.append(RF.back(DPI, 0.0, None))
    tw, th = faces[0].shape[1], faces[0].shape[0]                                      # 744 x 1039 px = 63 x 88 mm at 300 dpi
    W, H = round(8.5 * DPI), round(11 * DPI); gap = 24
    x0 = (W - (3 * tw + 2 * gap)) // 2; y0 = (H - (3 * th + 2 * gap)) // 2
    sheet = Image.new('RGB', (W, H), (255, 255, 255)); d = ImageDraw.Draw(sheet)
    for i, f in enumerate(faces):
        r, c = divmod(i, 3); x = x0 + c * (tw + gap); y = y0 + r * (th + gap)
        sheet.paste(Image.fromarray(f), (x, y))
    grey = (150, 150, 150)                                                             # cut lines, in the gaps and just outside the cards
    for c in range(4):
        x = x0 + c * (tw + gap) - (gap // 2 if 0 < c < 3 else 0) if 0 < c < 3 else (x0 - 6 if c == 0 else x0 + 3 * tw + 2 * gap + 6)
        d.line([(x, y0 - 40), (x, y0 - 8)], fill=grey, width=2); d.line([(x, y0 + 3 * th + 2 * gap + 8), (x, y0 + 3 * th + 2 * gap + 40)], fill=grey, width=2)
        if 0 < c < 3: d.line([(x - 0, y0), (x, y0 + 3 * th + 2 * gap)], fill=grey, width=1)
    for r in range(4):
        y = y0 + r * (th + gap) - (gap // 2 if 0 < r < 3 else 0) if 0 < r < 3 else (y0 - 6 if r == 0 else y0 + 3 * th + 2 * gap + 6)
        d.line([(x0 - 40, y), (x0 - 8, y)], fill=grey, width=2); d.line([(x0 + 3 * tw + 2 * gap + 8, y), (x0 + 3 * tw + 2 * gap + 40, y)], fill=grey, width=2)
        if 0 < r < 3: d.line([(x0, y), (x0 + 3 * tw + 2 * gap, y)], fill=grey, width=1)
    return sheet


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', default='proof-sheet.pdf'); a = ap.parse_args()
    s = build(); s.save(a.out, 'PDF', resolution=DPI); s.save(os.path.splitext(a.out)[0] + '.png', dpi=(DPI, DPI)); print('wrote', a.out, s.size)
