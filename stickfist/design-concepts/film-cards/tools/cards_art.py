import os, sys, cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from art import frame, layers, comp, grain, save
from plate import plate

OUT = os.path.join(os.path.dirname(__file__), 'out'); os.makedirs(OUT, exist_ok=True)
BG = (215, 216, 212); INK, GREY, RED, STEEL = (8, 8, 9), (83, 84, 81), (167, 0, 0), (157, 145, 142)
W, H = 1200, 1680

# A: whole card face in the film's grey, the fighter standing on it (no art box)
f = frame(246)[188:722, 330:1080]
L = layers(f, scale=1.5)
h, w = L['ink'].shape
card = np.empty((H, W, 3), np.float32); card[:] = BG
art = comp(L, [('red', RED, 1), ('grey', GREY, 1), ('ink', INK, 1), ('steel', STEEL, 1)], BG)
y0, x0 = 392, 40
card[y0:y0 + h, x0:x0 + w] = art[:, :W - x0]
save(f'{OUT}/A_card.png', card + grain(H, W, 3.2, 7))

# B: frame-by-frame plate of the run (Muybridge's running man, in STIXX ink)
plate([11, 14, 17, 20, 23, 26], 470, 420, 'B_plate', scale=1.0)

# C: booking-photo figure, ink only (no blood pool), as a transparent PNG
f = frame(296)[150:616, 717:1137]
L = layers(f, scale=2.0)
a = np.clip(L['ink'] + L['steel'], 0, 1)
rgb = np.zeros(a.shape + (3,), np.float32)
rgb[:] = 0
rgb = rgb * (1 - L['steel'][..., None]) + np.array((140, 140, 140), np.float32) * L['steel'][..., None]
rgba = np.dstack([rgb, a * 255]).astype(np.uint8)
cv2.imwrite(f'{OUT}/C_fig.png', cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))


# C: a thumbprint, generated per copy from the card's serial
def thumbprint(seed, size=420):
    r = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    cx, cy = size * (.5 + r.uniform(-.05, .05)), size * (.56 + r.uniform(-.05, .05))
    X, Y = (x - cx) / size, (y - cy) / size
    # domain warp with smooth noise, so ridges wander like skin
    def smooth(sc):
        n = r.normal(0, 1, (sc, sc)).astype(np.float32)
        return cv2.resize(n, (size, size), interpolation=cv2.INTER_CUBIC)
    wx, wy = smooth(5) * .035 + smooth(11) * .008, smooth(5) * .035 + smooth(11) * .008
    X2, Y2 = X + wx, Y + wy
    kind = seed % 3
    if kind == 0:   # whorl
        fld = np.sqrt((X2 / 1.0) ** 2 + (Y2 / 1.25) ** 2)
    elif kind == 1:  # loop: rings that open to one side
        fld = np.sqrt(X2 ** 2 + (Y2 / 1.3) ** 2) + .35 * np.clip(X2 * (1 if r.random() > .5 else -1), 0, None) + .25 * np.clip(Y2, 0, None)
    else:            # arch
        fld = Y2 * 1.1 + .55 * np.exp(-(X2 / .22) ** 2) * (Y2 < .1) * -.2 + .35 * (X2 ** 2)
    ridges = np.sin(fld * 2 * np.pi * 34 + smooth(7) * .6)
    ink = (ridges > .15).astype(np.float32)
    # breaks and pores
    breaks = smooth(40) > 1.6
    ink[breaks] = 0
    # fingertip shape with a pressure falloff
    tip = ((X / .36) ** 2 + (Y / .46) ** 2)
    press = np.clip(1.25 - tip ** 2.2, 0, 1) * (0.75 + .25 * smooth(4))
    ink = ink * (press > r.uniform(.25, .4)) * np.clip(press * 1.6, 0, 1)
    ink = cv2.GaussianBlur(ink, (0, 0), .9)
    return np.clip(ink * 1.15, 0, 1)

for s in (19, 4072, 88314):
    p = thumbprint(s)
    cv2.imwrite(f'{OUT}/C_thumb_{s}.png', ((1 - p) * 255).astype(np.uint8))
print('ok')
