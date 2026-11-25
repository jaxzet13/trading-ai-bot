"""The ten commons, Phantom, and the full-colour uncommons and rares, redrawn: every look of each card (the plain one and the twelve chance styles).

The old commons were 64 characters across in one flat tint on plain black, which read as "just letters on a card".
These are drawn properly, from the same source art and still made of nothing but characters:
  - more of them (96 across for First Print, 112 for Moonshot), each one CHOSEN TO FIT THE SHAPE under it
    (a slanted edge gets a slash, a curve a bracket, a solid area a heavy glyph), so outlines are crisp instead of noisy
  - the art's own colours (the plain look) and its shading, instead of one tint
  - a lit backdrop in the card's colour, a floor to stand on, a soft glow and a faint picture of the figure under the type
  - every style is its own drawing (stipple in braille, pixel in block characters, linework from the outline, typeset from
    the caption, the glitches torn and split, the dissolve melting from a smooth picture into blocks), not a recolour

Writes cards/<id>.jpg and cards/<id>-<style>.jpg (900 x 1092, the picture area only). Stitch's plain look is stitch-bone.jpg.
Every look of a card uses the same grid, so every look prints the card's character count (CARDS[id] cols x rows).

    python render.py                              # all ten commons x 13 looks into ../../cards, then run ../../make_thumbs.py
    python render.py --cards cone,brick --styles plain,ice --out /tmp/x
    python render.py --list
"""
import argparse, os, zlib, colorsys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__)); DC = os.path.normpath(os.path.join(HERE, '..'))
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
PW, PH = 900, 1092
SX, SY = 6, 10                                             # how finely a cell is looked at when a character is fitted to it
ASCII = [chr(i) for i in range(33, 127)]
DENSE = list('#%&@$8BWMX0QR')                              # the inside of a stroke: heavy glyphs, varied so it reads as texture, not a fill
LINES = list("|/\\-_()[]{}<>^~'\",.:;!+=7LJTYVvx")           # what an outline is drawn with
BLOCKS = {0: ' ', 1: '▘', 2: '▝', 3: '▀', 4: '▖', 5: '▌', 6: '▞', 7: '▛', 8: '▗', 9: '▚', 10: '▐', 11: '▜', 12: '▄', 13: '▙', 14: '▟', 15: '█'}   # bits: 1 top left, 2 top right, 4 bottom left, 8 bottom right

# src (relative to design-concepts), grid, view = (centre x, centre y, visible fraction of the source height), accent = the plain look's backdrop
FP = dict(cols=96, cw=18, rows=67, ch=31); MS = dict(cols=112, cw=16, rows=78, ch=28); UN = dict(cols=150, cw=12, rows=105, ch=21)
CARDS = {
    'stitch': dict(FP, src='funny-commons/sources/frog.png',  view=(0.50, 0.49, 1.04), accent=(110, 255, 150), text='frog hat. zero regrets.', plain='stitch-bone'),
    'brick':  dict(FP, src='funny-commons/sources/brick.png', view=(0.50, 0.50, 1.02), accent=(130, 180, 255), text='it is a colander. it works.'),
    'rook':   dict(FP, src='funny-commons/sources/rook.png',  view=(0.50, 0.52, 0.92), accent=(90, 235, 215),  text='reach: floppy.'),
    'mop':    dict(FP, src='more-cards/sources/mop.jpg',      view=(0.50, 0.50, 0.98), accent=(185, 150, 255), text='swab the deck.'),
    'pan':    dict(FP, src='more-cards/sources/pan.jpg',      view=(0.50, 0.50, 1.02), accent=(255, 120, 95),  text="it's a frying pan. it counts."),
    'cone':   dict(FP, src='more-cards/sources/cone.jpg',     view=(0.50, 0.50, 1.02), accent=(255, 150, 50),  text='caution: confident.'),
    'fuse':   dict(MS, src='moonshot/sources/fuse.jpg',       view=(0.50, 0.53, 0.86), accent=(255, 190, 70),  text='light it and walk away.'),
    'spark':  dict(MS, src='more-cards/sources/spark.jpg',    view=(0.50, 0.50, 1.02), accent=(255, 200, 100), text='small things start fires.'),
    'flare':  dict(MS, src='more-cards/sources/flare.jpg',    view=(0.52, 0.48, 0.92), accent=(255, 90, 75),   text='the sky has been told.'),
    # an uncommon whose old look was thin grey linework; its source is dark, so it is lifted (gain, gamma) before it is drawn
    'phantom': dict(UN, src='ascii-engines/sources/winged.png', view=(0.50, 0.44, 0.84), accent=(170, 160, 255), text='gone before the cape lands.', gain=2.7, gamma=0.72, floor=False),
    'bubble': dict(MS, src='more-cards/sources/bubble.jpg',   view=(0.50, 0.50, 1.02), accent=(110, 210, 255), text='all systems: smiling.'),
}
# ---- the uncommons and rares whose source art is a full-colour scene. Their old looks flattened it to one tint; here the plain look
# keeps the art's own colours. Same grids as before (cols x rows = the count printed on the card), no dotted backdrop or floor (the
# scene is the backdrop), and a stronger picture under the type because the characters are small.
def G(cols, rows): cw = max(3, round(1800 / cols)); return dict(cols=cols, rows=rows, cw=cw, ch=max(4, round(cols * cw * PH / PW / rows)), floor=False, dots=False, under=0.34, wash=0.05)
CARDS.update({
    'orbit':     dict(G(110, 66),  src='ascii-engines/sources/galaxy.png', view=(0.5, 0.37, 0.74), accent=(120, 170, 255), text='already read the ending.', gain=1.25),
    'tempest':   dict(G(110, 66),  src='more-cards/sources/tempest.jpg',   view=(0.5, 0.50, 0.97), accent=(120, 170, 255), text='weather is a choice.', gain=1.2),
    'surge':     dict(G(150, 105), src='more-cards/sources/surge.jpg',     view=(0.5, 0.50, 0.97), accent=(110, 230, 220), text='ride it before it breaks.', gain=1.2),
    'null':      dict(G(220, 133), src='ascii-engines/sources/star.png',   view=(0.5, 0.38, 0.86), accent=(150, 180, 255), text='not on any record.', gain=1.3),
    'shogun':    dict(G(230, 139), src='ascii-engines/sources/wings.png',  view=(0.5, 0.40, 0.80), accent=(255, 210, 120), text='rents you the air.', tint=(1.0, 0.84, 0.50)),
    'kraken':    dict(G(200, 140), src='more-cards/sources/kraken.jpg',    view=(0.5, 0.50, 0.97), accent=(120, 230, 200), text='it was always down there.', gain=1.3),
    'ignition':  dict(G(120, 84),  src='moonshot/sources/ignition.jpg',    view=(0.5, 0.46, 0.90), accent=(255, 160, 70),  text='no turning back from here.'),
    'countdown': dict(G(120, 84),  src='more-cards/sources/countdown.jpg', view=(0.5, 0.50, 0.97), accent=(255, 80, 70),   text='three. two. one.'),
    'gantry':    dict(G(120, 84),  src='more-cards/sources/gantry.jpg',    view=(0.5, 0.50, 1.00), accent=(255, 190, 110), text='the arm lets go.', gain=1.15),
    'liftoff':   dict(G(240, 168), src='moonshot/sources/liftoff.jpg',     view=(0.5, 0.46, 0.90), accent=(255, 170, 90),  text='gravity lost the argument.'),
    'booster':   dict(G(240, 168), src='more-cards/sources/booster.jpg',   view=(0.5, 0.50, 0.97), accent=(255, 180, 90),  text='dead weight, dropped.'),
    'apogee':    dict(G(420, 294), src='moonshot/sources/apogee.jpg',      view=(0.5, 0.46, 0.90), accent=(110, 200, 255), text='the top is quiet.'),
})
# ---- new designs (2026-11): generated illustrations, first re-treated by ../new25/restyle.py in the looks of ../STYLE.md (grain, two-tone,
# duotone, glitch), then drawn the same way as the full-colour scenes above
CARDS.update({
    'colossus':  dict(G(210, 140), src='new25/styled/colossus.png',  view=(0.5, 0.50, 0.82), accent=(255, 190, 90),  text='it was here before the sand.'),
    'leviathan': dict(G(224, 138), src='new25/styled/leviathan.png', view=(0.5, 0.48, 0.82), accent=(90, 200, 255),  text='the sky has tides too.'),
    'titan':     dict(G(330, 220), src='new25/styled/titan.png',     view=(0.5, 0.50, 0.82), accent=(140, 180, 255), text='it knelt first.'),
    'console':   dict(G(128, 86),  src='new25/styled/console.png',   view=(0.5, 0.48, 0.82), accent=(110, 255, 140), text='all stations: go.'),
    'suit':      dict(G(124, 84),  src='new25/styled/suit.png',      view=(0.5, 0.50, 0.82), accent=(150, 210, 255), text='one size fits nobody.'),
    'mars':      dict(G(420, 280), src='new25/styled/mars.png',      view=(0.5, 0.50, 0.86), accent=(255, 130, 80),  text='second flag. first footprint.'),
    'horizon':   dict(G(520, 346), src='new25/styled/horizon.png',   view=(0.5, 0.50, 0.86), accent=(255, 200, 100), text='nothing leaves. you looked anyway.', gain=1.15),
})
# key (the app's style key), how it is drawn, its colour (dark end, bright end), extras
STYLES = {
    'plain':   dict(mode='ascii'),
    'steel':   dict(mode='ascii',   lo=(0.42, 1.00, 0.62), hi=(0.86, 1.00, 0.90), scan=True),                     # Phosphor
    'dots':    dict(mode='ascii',   lo=(1.00, 0.66, 0.18), hi=(1.00, 0.93, 0.68), scan=True),                     # Amber
    'vhs':     dict(mode='ascii',   lo=(0.66, 0.48, 1.00), hi=(0.95, 0.90, 1.00), glitch=1),                      # Glitch
    'scratch': dict(mode='text',    lo=(0.86, 0.82, 0.74), hi=(1.00, 0.98, 0.93)),                                # Typeset
    'ice':     dict(mode='braille', lo=(0.40, 0.66, 1.00), hi=(0.92, 0.97, 1.00), bloom=1.25),                    # Stipple
    'chain':   dict(mode='edge',    lo=(0.86, 0.82, 0.74), hi=(1.00, 0.98, 0.93)),                                # Linework
    'wire':    dict(mode='block',   lo=(0.62, 1.00, 0.20), hi=(0.95, 1.00, 0.80)),                                # Pixel
    'print':   dict(mode='ascii',   lo=(1.00, 0.16, 0.14), hi=(1.00, 0.74, 0.62)),                                # Blood
    'glass':   dict(mode='ascii',   lo=(1.00, 0.26, 0.76), hi=(1.00, 0.90, 1.00), bloom=1.7),                     # Glow
    'blood':   dict(mode='ascii',   lo=(0.55, 1.00, 0.10), hi=(0.96, 1.00, 0.55), glitch=2),                      # Toxic Glitch
    'leaf':    dict(mode='ascii',   irid=True, bloom=1.25),                                                       # Iridescent
    'kin':     dict(mode='dissolve', lo=(0.34, 0.60, 1.00), hi=(0.92, 0.97, 1.00), bloom=1.2),                    # Dissolve
}

def seed(*a): return zlib.crc32('/'.join(map(str, a)).encode())

def frame(src, view, w, h, gain=1.0, gamma=1.0):
    """the source seen through the card: centred on (cx, cy), `vh` of its height visible, black outside it"""
    im = cv2.imread(src, cv2.IMREAD_COLOR); im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB); sh, sw = im.shape[:2]; cx, cy, vh = view
    vis_h = sh * vh; vis_w = vis_h * (PW / PH); x0 = cx * sw - vis_w / 2; y0 = cy * sh - vis_h / 2
    big = 4; M = np.float32([[w * big / vis_w, 0, -x0 * w * big / vis_w], [0, h * big / vis_h, -y0 * h * big / vis_h]])
    out = cv2.warpAffine(im, M, (w * big, h * big), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
    out = cv2.resize(out, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    return np.clip(out * gain, 0, 1) ** gamma if (gain != 1 or gamma != 1) else out

_atlas = {}
def atlas(cw, ch):
    """every glyph as a cell-sized mask, and as the small blurred vector a patch of the picture is compared with"""
    if (cw, ch) in _atlas: return _atlas[(cw, ch)]
    size = int(round(cw / 0.602)); f = ImageFont.truetype(FONT, size); asc, desc = f.getmetrics(); chars = set(ASCII) | set(BLOCKS.values()) | {chr(0x2800 + i) for i in range(256)} | {'░', '▒', '▓', '·'}
    mask = {}
    for c in chars:
        im = Image.new('L', (cw, ch), 0); d = ImageDraw.Draw(im); d.text(((cw - f.getlength(c)) / 2, (ch - (asc + desc)) / 2), c, font=f, fill=255); mask[c] = np.asarray(im, np.float32) / 255
    def vec(c): return cv2.resize(cv2.GaussianBlur(mask[c], (0, 0), cw * 0.16), (SX, SY), interpolation=cv2.INTER_AREA).reshape(-1)
    V = np.stack([vec(c) for c in ASCII]); gain = 0.82 / max(V.mean(axis=1))                 # so the heaviest glyph counts as (nearly) solid
    _atlas[(cw, ch)] = (mask, V * gain, np.stack([vec(c) for c in LINES]) * (0.9 / max(np.stack([vec(c) for c in LINES]).max(axis=1).mean(), 1e-3)))
    return _atlas[(cw, ch)]

def fit(P, V, names, rng, slack=0.035):
    """for each patch (n x SX*SY) the glyph whose shape is nearest, picking at random among the near ties"""
    d = (P * P).sum(1)[:, None] - 2 * P @ V.T + (V * V).sum(1)[None, :]
    best = d.min(1, keepdims=True); ok = d <= best + slack * SX * SY; pick = (rng.random(d.shape) * ok).argmax(1)
    return [names[i] for i in pick]

def paint(canvas, mask, g, x, y, cw, ch, col):
    canvas[y:y + ch, x:x + cw] += mask[g][:, :, None] * col

def render(cid, key, out_dir, quality=84):
    cfg = CARDS[cid]; st = STYLES[key]; cols, rows, cw, ch = cfg['cols'], cfg['rows'], cfg['cw'], cfg['ch']; W, H = cols * cw, rows * ch
    rng = np.random.default_rng(seed(cid, key)); mask, V, VL = atlas(cw, ch); mode = st['mode']
    tone = (cfg.get('gain', 1.0), cfg.get('gamma', 1.0)); fine = frame(os.path.join(DC, cfg['src']), cfg['view'], cols * SX, rows * SY, *tone); L = fine.max(axis=2)                       # the picture, SX x SY samples per cell
    P = L.reshape(rows, SY, cols, SX).transpose(0, 2, 1, 3).reshape(rows * cols, SY * SX)                                    # one patch per cell
    C = fine.reshape(rows, SY, cols, SX, 3).transpose(0, 2, 1, 3, 4).reshape(rows * cols, SY * SX, 3)
    wsum = P.sum(1, keepdims=True) + 1e-4; hue = (C * P[:, :, None]).sum(1) / wsum; hue = hue / np.maximum(hue.max(1, keepdims=True), 1e-3)   # the colour of the lit part of the cell
    mean = P.mean(1); top = np.percentile(P, 88, axis=1); ink = top > 0.16                                                    # cells the picture touches
    plain = 'lo' not in st and not st.get('irid'); accent = np.array(cfg['accent'], np.float32) / 255 if plain else np.array(st.get('lo', (0.8, 0.7, 1.0)), np.float32)
    lo, hi = np.array(st.get('lo', (1, 1, 1)), np.float32), np.array(st.get('hi', (1, 1, 1)), np.float32)
    ys, xs = np.divmod(np.arange(rows * cols), cols); u = (xs + .5) / cols; v = (ys + .5) / rows

    def colour(i, b=None):
        b = float(top[i]) if b is None else b
        if st.get('irid'):
            h = (u[i] * 0.9 + v[i] * 1.5 + b * 0.25 + 0.04 * np.sin(v[i] * 37)) % 1.0; return np.array(colorsys.hsv_to_rgb(h, 0.52, 1.0), np.float32) * (0.5 + 0.5 * b)
        if plain:
            c = hue[i]; sat = float(c.max() - c.min())
            return (c * 0.92 + 0.08 if sat > 0.22 else tint) * (0.42 + 0.58 * b ** 0.8)   # props keep their colour; the figure is a warm white
        return (lo + (hi - lo) * b ** 2.2) * (0.42 + 0.58 * b ** 0.8)

    canvas = np.zeros((H, W, 3), np.float32); under = 0.20; tint = np.array(cfg.get('tint', (1.0, 0.975, 0.91)), np.float32)
    # ---- the figure
    if mode in ('ascii', 'text'):
        solid = mean > 0.90; g = fit(np.clip(P, 0, 1), V, ASCII, rng); t = [c if c != ' ' else '·' for c in cfg['text'].upper()] + ['·']; k = 0
        for i in np.flatnonzero(ink):
            if mode == 'text':
                if mean[i] < 0.30: continue
                c = t[k % len(t)]; k += 1; paint(canvas, mask, c, xs[i] * cw, ys[i] * ch, cw, ch, colour(i, max(float(top[i]), 0.8)) * (0.8 + 0.6 * min(1, mean[i] * 1.3)))
            else: paint(canvas, mask, DENSE[int(rng.integers(len(DENSE)))] if solid[i] else g[i], xs[i] * cw, ys[i] * ch, cw, ch, colour(i))
        if mode == 'text': under = 0.16
    elif mode == 'braille':
        dots = frame(os.path.join(DC, cfg['src']), cfg['view'], cols * 2, rows * 4, *tone).max(axis=2); bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16
        thr = 0.16 + 0.62 * np.tile(bayer, (rows, cols // 2 + 1))[:, :cols * 2]; on = (dots > thr).reshape(rows, 4, cols, 2).transpose(0, 2, 1, 3).reshape(rows * cols, 4, 2)
        bit = np.array([[1, 8], [2, 16], [4, 32], [64, 128]]); code = (on * bit[None]).sum((1, 2))
        for i in np.flatnonzero(code): paint(canvas, mask, chr(0x2800 + int(code[i])), xs[i] * cw, ys[i] * ch, cw, ch, colour(i, max(float(top[i]), 0.35)) * 1.15)
        under = 0.16
    elif mode == 'edge':
        blur = cv2.GaussianBlur(L, (0, 0), 1.0); gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3); E = np.clip(np.hypot(gx, gy) / 1.3, 0, 1)
        PE = E.reshape(rows, SY, cols, SX).transpose(0, 2, 1, 3).reshape(rows * cols, SY * SX); g = fit(PE, VL, LINES, rng, 0.02); em = PE.max(1)
        for i in range(rows * cols):
            if em[i] > 0.34: paint(canvas, mask, g[i], xs[i] * cw, ys[i] * ch, cw, ch, colour(i, 1.0) * 1.5)
            elif mean[i] > 0.55 and (xs[i] + ys[i]) % 2 == 0: paint(canvas, mask, '.' if mean[i] > 0.85 else ':', xs[i] * cw, ys[i] * ch, cw, ch, colour(i, 0.9) * 0.5)   # the inside of a stroke, barely there
        under = 0.10
    elif mode in ('block', 'dissolve'):
        q = L.reshape(rows, 2, SY // 2, cols, 2, SX // 2).mean((2, 5)).transpose(0, 2, 1, 3).reshape(rows * cols, 4); bits = ((q > 0.42) * np.array([1, 2, 4, 8])).sum(1)
        smooth = cv2.resize(fine, (W, H), interpolation=cv2.INTER_CUBIC); sl = np.clip(smooth.max(axis=2), 0, 1)
        for i in range(rows * cols):
            f = v[i]; x, y = xs[i] * cw, ys[i] * ch
            if mode == 'dissolve':
                p = np.clip((0.70 - f) / 0.30, 0, 1)                                                                          # 1 = still a smooth picture, 0 = all blocks
                if rng.random() < p:
                    if top[i] > 0.1: s = sl[y:y + ch, x:x + cw, None]; canvas[y:y + ch, x:x + cw] += (lo + (hi - lo) * s ** 2.0) * s * 0.95
                    continue
                if bits[i] and rng.random() < 0.22 * np.clip((f - 0.62) / 0.38, 0, 1): continue                             # pieces missing towards the bottom
                if not bits[i]:
                    if p < 0.9 and mean[max(0, i - cols)] > 0.25 and rng.random() < 0.10: paint(canvas, mask, BLOCKS[int(rng.choice([1, 2, 4, 8]))], x, y, cw, ch, colour(i, 0.7) * 0.8)   # crumbs falling off
                    continue
            if not bits[i]: continue
            b = float(top[i]); c = BLOCKS[int(bits[i])]
            if bits[i] == 15 and mean[i] < 0.80: c = '▓' if mean[i] > 0.6 else '▒'
            paint(canvas, mask, c, x, y, cw, ch, colour(i, b))
        under = 0.0 if mode == 'dissolve' else 0.10
    # ---- a faint picture of the figure under the type, so it reads as one solid drawing from across the room
    if under: under = max(under, cfg.get('under', 0)) if mode in ('ascii', 'text', 'braille', 'edge') else under
    if under:
        smooth = np.clip(cv2.GaussianBlur(cv2.resize(fine, (W, H), interpolation=cv2.INTER_CUBIC), (0, 0), cw * 0.35), 0, 1); sl = smooth.max(axis=2, keepdims=True)
        if st.get('irid'):
            yy, xx = np.mgrid[0:H, 0:W]; hh = ((xx / W) * 0.9 + (yy / H) * 1.5) % 1.0; hsv = np.stack([hh * 179, np.full_like(hh, 133), np.full_like(hh, 255)], 2).astype(np.uint8); tint = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).astype(np.float32) / 255
            canvas += tint * sl * under
        elif plain: canvas += smooth * tint * under
        else: canvas += (lo + (hi - lo) * sl ** 2.2) * sl * under
    # ---- the backdrop: a dotted glow behind the figure and a floor of lines under its feet, in the card's colour
    figure = (mean > 0.2).reshape(rows, cols); lit = np.flatnonzero(figure.sum(1) >= 3); foot = int(lit.max()) if len(lit) else rows - 4; floor_y = min(rows - 3, max(int(rows * 0.80), foot - 1))
    occupied = (top > 0.10).reshape(rows, cols); cyv = 0.46
    for i in range(rows * cols):
        y, x = ys[i], xs[i]
        if occupied[y, x]: continue
        du, dv = u[i] - 0.5, v[i] - cyv; b = float(np.exp(-((du / 0.50) ** 2 + (dv / 0.42) ** 2) * 1.5))
        if y >= floor_y and cfg.get('floor', True):
            t = (y - floor_y) / max(1, rows - 1 - floor_y); k = (0.85 - 0.70 * min(1, abs(du) * 2.0)) * (1.0 - 0.5 * t)
            if k > 0.03: paint(canvas, mask, '_' if (y - floor_y) % 2 == 0 else '=', x * cw, y * ch, cw, ch, accent * k)
        elif (x + y) % 2 == 0 and b > 0.06 and cfg.get('dots', True):
            paint(canvas, mask, '.' if b < 0.34 else (':' if b < 0.60 else '+'), x * cw, y * ch, cw, ch, accent * (0.10 + 0.52 * b))
    # ---- light: bloom, a wash of the accent so it is never a black void, tears for the glitches, scanlines, vignette
    bloom = st.get('bloom', 1.0); glow = cv2.GaussianBlur(canvas, (0, 0), cw * 0.55) * 0.50 + cv2.GaussianBlur(canvas, (0, 0), cw * 2.6) * 0.42
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); halo = np.exp(-(((xx / W - 0.5) / 0.50) ** 2 + ((yy / H - cyv) / 0.42) ** 2) * 1.5)
    img = canvas + glow * bloom + halo[:, :, None] * accent * cfg.get('wash', 0.17)
    if st.get('glitch'):
        g2 = np.random.default_rng(seed(cid, key, 'tear')); out = img.copy(); n = 9 if st['glitch'] == 1 else 13
        for _ in range(n):
            y0 = int(g2.integers(0, rows - 2)) * ch; hh = int(g2.integers(1, 4)) * ch; dx = int(g2.integers(-6, 7)) * cw
            if dx: out[y0:y0 + hh] = np.roll(img[y0:y0 + hh], dx, axis=1)
        s = max(2, cw // 5); img = np.stack([np.roll(out[:, :, 0], -s, axis=1), out[:, :, 1], np.roll(out[:, :, 2], s, axis=1)], 2)   # the colours pulled apart
        if st['glitch'] == 2:
            for _ in range(4):
                y0 = int(g2.integers(0, rows - 1)) * ch; img[y0:y0 + ch] = img[y0:y0 + ch][:, :, [1, 0, 1]] * np.array([1.0, 0.55, 1.0], np.float32)   # a few lines flip to magenta
    if st.get('scan'): img = img * (0.86 + 0.14 * (np.arange(H) % 4 < 2))[:, None, None]
    vig = 1 - 0.40 * (((xx / W - 0.5) / 0.5) ** 2 + ((yy / H - 0.5) / 0.5) ** 2) ** 1.2
    img = np.clip(np.clip(img, 0, 4) * vig[:, :, None], 0, 1) ** (1 / 1.08)
    out = cv2.resize((img * 255).astype(np.uint8), (PW, PH), interpolation=cv2.INTER_AREA)
    name = (cfg.get('plain', cid) if key == 'plain' else f'{cid}-{key}') + '.jpg'; path = os.path.join(out_dir, name); q = quality
    while True:
        Image.fromarray(out).save(path, 'JPEG', quality=q, optimize=True, progressive=True)
        if os.path.getsize(path) <= 166 * 1024 or q <= 56: break            # the app holds every card picture to 170 KB
        q -= 4
    return path, q, os.path.getsize(path) // 1024

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--cards', default=','.join(CARDS)); ap.add_argument('--styles', default=','.join(STYLES)); ap.add_argument('--out', default=os.path.join(DC, '..', 'cards')); ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    if a.list:
        for cid, c in CARDS.items(): print(f"{cid:8s} {c['cols']} x {c['rows']} = {c['cols'] * c['rows']:,} characters   {c['src']}")
        raise SystemExit
    os.makedirs(a.out, exist_ok=True)
    for cid in a.cards.split(','):
        for key in a.styles.split(','):
            p, q, kb = render(cid, key, a.out); print(f'{cid:8s} {key:8s} q{q} {kb:4d} KB  {os.path.basename(p)}', flush=True)
