"""A chronophotograph-style plate: one move, frame by frame, cropped on the fighter."""
import os, sys, cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from art import frame, layers, comp, grain, save

OUT = os.path.join(os.path.dirname(__file__), 'out')
BG = (215, 216, 212); INK, GREY, RED, STEEL = (8, 8, 9), (83, 84, 81), (167, 0, 0), (157, 145, 142)

def ink_box(f):
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) < 30
    g = cv2.morphologyEx(g.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(g)
    big = max(range(1, n), key=lambda i: st[i, 4])
    x, y, w, h, _ = st[big]
    return x + w / 2, y + h / 2

def plate(seq, cw, ch, name, scale=1.25, cols=3):
    cells = []
    for n in seq:
        f = frame(n)
        cx, cy = ink_box(f)
        pad = cv2.copyMakeBorder(f, 400, 400, 400, 400, cv2.BORDER_CONSTANT, value=(212, 216, 215))
        x0, y0 = int(cx + 400 - cw / 2), int(cy + 400 - ch / 2)
        L = layers(pad[y0:y0 + ch, x0:x0 + cw], scale=scale)
        cells.append(comp(L, [('red', RED, 1), ('grey', GREY, 1), ('ink', INK, 1), ('steel', STEEL, 1)], BG))
    h, w = cells[0].shape[:2]
    rows = (len(cells) + cols - 1) // cols
    gut = 10
    o = np.empty((rows * h + (rows - 1) * gut, cols * w + (cols - 1) * gut, 3), np.float32); o[:] = INK
    for i, c in enumerate(cells):
        r, k = divmod(i, cols)
        o[r * (h + gut):r * (h + gut) + h, k * (w + gut):k * (w + gut) + w] = c
    save(f'{OUT}/{name}.png', o + grain(*o.shape[:2], 3, 5))
    print(name, o.shape)

if __name__ == '__main__':
    plate([1, 6, 11, 16, 21, 26], 330, 300, 'B_run')
    plate([131, 141, 151, 161, 171, 186], 360, 330, 'B_kill')
