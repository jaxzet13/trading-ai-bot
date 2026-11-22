#!/usr/bin/env python3
"""REQUIEM renderer: turns one source painting into a card made of text, at a character count you can check.

Every card is a grid of  cols x rows  glyphs (cell aspect 1.73, the same cell the other packs use).  For each cell the renderer
  1. samples the graded painting,
  2. picks the glyph whose ink matches the cell's tone (from the card's own glyph family, with a little noise so neighbours differ),
  3. draws that glyph in a colour worked out so the cell averages to the painting's colour, over a dim copy of the painting.
The glyphs are drawn on a supersampled canvas (5 x 9 px per cell) and shrunk with area averaging, so the master is clean at any size.
Then the card's finish is added at full resolution: bloom, grain, and for the glitch card an RGB split with tracking bands.

    python requiem_render.py                         # all six cards at screen size  -> out/<id>.jpg, out/s/<id>.jpg, out/macro/<id>.jpg
    python requiem_render.py --cards seraph,witness  # some cards
    python requiem_render.py --scale 2 --out print   # print master (3600 x 4368; feed it upscaled sources for the real thing)
    python requiem_render.py --list                  # the cards, their grids and exact character counts

The picture area is 1500 : 1820, like every other card; the name strip and frame are drawn by the app.
Needs numpy, opencv-python and Pillow.  Fonts: JetBrains Mono and DejaVu Sans Mono (both ship with most Linux images).
"""
import argparse, os, sys, time
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_A = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf'
FONT_B = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
ART_W, ART_H = 1500, 1820                 # the picture area every card uses
ASPECT = 1.73                             # cell height / cell width
SW, SH = 5, 9                             # supersample: pixels per cell on the glyph canvas

# glyph families: the characters a card is allowed to be made of (ordered by ink automatically)
FAMILIES = {
    'stipple': dict(chars=" .'`,:;-~=+*!oO0xX%&#$@", font=FONT_A),
    'engrave': dict(chars=" .,:;-=+*/\\|!iIlt1ocxzXZ%#@", font=FONT_A),
    'paint':   dict(chars=" .,:;'\"~-_=+*^<>?/\\|()[]{}1iltrcoxzvnuszeaCOSXZ&%#$@", font=FONT_A),
    'glitch':  dict(chars=" .:-=+*#%@0123456789ABCDEF/\\|", font=FONT_A, blocks=" ░▒▓█▀▄▌▐"),
    'blocks':  dict(chars=" .·•:+*o●░▒▓█", font=FONT_B),
}

# ------------------------------------------------------------------------------------------------------------------------ cards
# view = (cx, cy, vh): centre of the crop as fractions of the source and the fraction of the source HEIGHT shown.
# cols: the grid width. rows follow from the picture area and the cell aspect. chars = cols x rows is printed on the card.
CARDS = {
    'pallbearer': dict(no='R1', name='Pallbearer', src='pallbearer.jpg', cols=1600, view=(0.5, 0.5, 0.97), family='paint',
                       tone=dict(black=0.02, white=0.94, gamma=1.08, contrast=1.14, sat=1.0, clahe=1.5),
                       ramp=[(0, (3, 4, 7)), (0.45, (104, 118, 138)), (0.8, (205, 214, 224)), (1, (246, 246, 240))], ramp_mix=0.55,
                       macro_at=(0.4, 0.3), bgk=0.42, jitter=1.6, bloom=(0.006, 0.20), grain=0.028, sharpen=0.7),
    'vigil':      dict(no='R2', name='Vigil', src='vigil.jpg', cols=2000, view=(0.5, 0.5, 0.97), family='engrave', orient=True,
                       tone=dict(black=0.01, white=0.97, gamma=0.88, contrast=1.14, sat=1.05, clahe=1.4),
                       macro_at=(0.37, 0.6), bgk=0.46, jitter=1.4, bloom=(0.007, 0.28), grain=0.030, sharpen=0.8),
    'halation':   dict(no='R3', name='Halation', src='halation.jpg', cols=2400, view=(0.5, 0.5, 0.97), family='glitch',
                       tone=dict(black=0.01, white=0.98, gamma=0.88, contrast=1.12, sat=1.18, clahe=1.2),
                       macro_at=(0.55, 0.27), bgk=0.50, jitter=1.2, bloom=(0.006, 0.30), grain=0.030, sharpen=0.7, rgbsplit=7, scan=0.10, bands=14),
    'witness':    dict(no='R4', name='The Witness', src='witness.jpg', cols=2800, view=(0.5, 0.5, 0.97), family='stipple',
                       tone=dict(black=0.02, white=0.96, gamma=0.80, contrast=1.16, sat=0.0, clahe=1.2),
                       ramp=[(0, (2, 2, 3)), (0.5, (150, 150, 152)), (1, (250, 248, 242))], ramp_mix=1.0,
                       macro_at=(0.5, 0.115), bgk=0.40, jitter=1.0, bloom=(0.005, 0.22), grain=0.036, sharpen=0.9),
    'orrery':     dict(no='R5', name='Orrery', src='orrery.jpg', cols=3200, view=(0.5, 0.5, 0.97), family='blocks', post=14,
                       tone=dict(black=0.01, white=0.98, gamma=0.86, contrast=1.10, sat=1.12, clahe=1.0),
                       macro_at=(0.5, 0.225), bgk=0.55, jitter=0.7, bloom=(0.008, 0.38), grain=0.016, sharpen=0.4),
    'seraph':     dict(no='R6', name='Seraph', src='seraph.jpg', cols=3600, view=(0.5, 0.5, 0.97), family='stipple',
                       tone=dict(black=0.015, white=0.96, gamma=0.80, contrast=1.18, sat=1.35, clahe=1.2),
                       macro_at=(0.5, 0.405), bgk=0.36, jitter=0.9, bloom=(0.008, 0.30), grain=0.036, sharpen=0.9),
}
ORDER = ['pallbearer', 'vigil', 'halation', 'witness', 'orrery', 'seraph']


def grid(cols):
    rows = int(round(cols * (ART_H / ART_W) / ASPECT))
    return cols, rows


# ------------------------------------------------------------------------------------------------------------------------ atlas
_ATLAS = {}


def atlas(family, sw=SW, sh=SH, hi=8):
    """glyph coverage bitmaps (n, sh, sw) in 0..1, sorted by ink, plus each glyph's ink and character."""
    key = (family, sw, sh)
    if key in _ATLAS: return _ATLAS[key]
    fam = FAMILIES[family]
    chars = list(dict.fromkeys(fam['chars'] + fam.get('blocks', '')))
    fonts = {}
    bm, ink, out_chars = [], [], []
    for ch in chars:
        path = FONT_B if ch in fam.get('blocks', '') or ord(ch) > 126 else fam['font']
        if path not in fonts: fonts[path] = ImageFont.truetype(path, int(sh * hi * 0.78))
        im = Image.new('L', (sw * hi, sh * hi), 0); d = ImageDraw.Draw(im)
        d.text((sw * hi / 2, sh * hi / 2), ch, font=fonts[path], fill=255, anchor='mm')
        a = np.asarray(im, np.float32) / 255
        small = cv2.resize(a, (sw, sh), interpolation=cv2.INTER_AREA)
        bm.append(small); ink.append(float(a.mean())); out_chars.append(ch)
    order = np.argsort(ink, kind='stable')
    res = (np.stack([bm[i] for i in order]), np.array([ink[i] for i in order], np.float32), ''.join(out_chars[i] for i in order))
    _ATLAS[key] = res
    return res


# ------------------------------------------------------------------------------------------------------------------------ source
def load_source(cfg, W, H):
    im = cv2.cvtColor(cv2.imread(os.path.join(HERE, 'sources', cfg['src'])), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    sh, sw = im.shape[:2]
    cx, cy, vh = cfg['view']
    ch = sh * vh; cw = ch * ART_W / ART_H
    if cw > sw: cw = sw; ch = cw * ART_H / ART_W
    x0 = int(round(min(max(cx * sw - cw / 2, 0), sw - cw))); y0 = int(round(min(max(cy * sh - ch / 2, 0), sh - ch)))
    im = im[y0:y0 + int(round(ch)), x0:x0 + int(round(cw))]
    im = cv2.resize(im, (W, H), interpolation=cv2.INTER_LANCZOS4 if W > im.shape[1] else cv2.INTER_AREA)
    a = cfg.get('sharpen', 0)
    if a: im = cv2.addWeighted(im, 1 + a, cv2.GaussianBlur(im, (0, 0), 1.3 * W / 1800), -a, 0)
    return np.clip(im, 0, 1)


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)


def grade(im, cfg):
    t = cfg['tone']
    lab = cv2.cvtColor((np.clip(im, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2LAB)
    if t.get('clahe'):
        lab[..., 0] = cv2.createCLAHE(clipLimit=t['clahe'], tileGridSize=(8, 8)).apply(lab[..., 0])
    im = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB).astype(np.float32) / 255
    y = (im * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    im = y + (im - y) * t['sat']
    im = np.clip((im - t['black']) / (t['white'] - t['black']), 0, 1) ** t['gamma']
    m = im.mean(-1, keepdims=True); im = np.clip(m + (im - m) * 1 + (im - m) * 0, 0, 1)
    im = np.clip((im - 0.5) * t['contrast'] + 0.5, 0, 1)
    ramp = cfg.get('ramp')
    if ramp:                                                             # a toned monochrome: map luminance through the card's colour ramp
        y = (im * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1)
        xs = np.array([p for p, _ in ramp]); cs = np.array([c for _, c in ramp], np.float32) / 255
        toned = np.stack([np.interp(y, xs, cs[:, k]) for k in range(3)], -1).astype(np.float32)
        mix = cfg.get('ramp_mix', 1.0)
        sat = np.clip((im.max(-1) - im.min(-1)) * 3.0, 0, 1)[..., None]   # keep strong colour (a lantern) where the painting has it
        w = mix * (1 - sat * (1 - 0.0))
        im = toned * w + im * (1 - w)
    return np.clip(im, 0, 1)


# ------------------------------------------------------------------------------------------------------------------------ render
def hash2(r, c, seed):
    x = (r.astype(np.uint32) * np.uint32(73856093)) ^ (c.astype(np.uint32) * np.uint32(19349663)) ^ np.uint32(seed * 83492791 + 1)
    x ^= x >> np.uint32(13); x *= np.uint32(0x5bd1e995); x ^= x >> np.uint32(15)
    return (x & np.uint32(0xFFFFFF)).astype(np.float32) / 0xFFFFFF


def pick_glyphs(Y, edge_dir, edge_mag, cfg, chars, ink):
    """glyph index per cell from the tone, with noise; with orient=True strong edges use a stroke glyph that follows the edge."""
    rows, cols = Y.shape
    rr, cc = np.mgrid[0:rows, 0:cols]
    n = len(chars)
    noise = hash2(rr, cc, 7) - 0.5
    # target ink: map tone onto the ramp's own ink range
    t = np.interp(Y, [0, 1], [ink[0], ink[-1] * 0.98])
    idx = np.searchsorted(ink, t).astype(np.float32) + noise * 2 * cfg.get('jitter', 1.0)
    idx = np.clip(np.round(idx), 0, n - 1).astype(np.int32)
    if cfg.get('orient'):
        strokes = {k: chars.index(g) for k, g in (('h', '-'), ('d1', '/'), ('v', '|'), ('d2', '\\')) if g in chars}
        thr = np.percentile(edge_mag, 74)
        ang = (np.degrees(edge_dir) % 180)
        sel = np.full(Y.shape, -1, np.int32)
        sel[(ang < 22.5) | (ang >= 157.5)] = strokes['v']                # gradient horizontal -> edge vertical
        sel[(ang >= 22.5) & (ang < 67.5)] = strokes['d2']
        sel[(ang >= 67.5) & (ang < 112.5)] = strokes['h']
        sel[(ang >= 112.5) & (ang < 157.5)] = strokes['d1']
        use = (edge_mag > thr) & (Y > 0.10) & (hash2(rr, cc, 11) < 0.82)
        idx = np.where(use, sel, idx)
    if cfg.get('family') == 'glitch':                                    # tracking bands: whole rows go blocky for a few cells
        bandy = (hash2(rr[:, :1] // 3, cc[:, :1] * 0, 5) < 0.06)
        blk = np.array([chars.index(g) for g in FAMILIES['glitch']['blocks'] if g in chars])
        pick = blk[np.minimum((Y * (len(blk) - 1) + 0.5).astype(np.int32), len(blk) - 1)]
        idx = np.where(bandy & (hash2(rr, cc, 13) < 0.5), pick, idx)
    return idx


def build_cells(cfg, W, H):
    cols, rows = grid(cfg['cols'])
    work = grade(load_source(cfg, W, H), cfg)
    interp = cv2.INTER_AREA if cols <= W else cv2.INTER_CUBIC
    G = cv2.resize(work, (cols, rows), interpolation=interp)
    if cfg.get('rgbsplit'):                                              # VHS: each colour channel is read from a slightly different place, band by band
        rr = np.arange(rows)[:, None]
        band = (hash2(rr // cfg.get('bands', 14), np.zeros_like(rr), 3) - 0.5) * 2
        off = (band * cfg['rgbsplit'] * (hash2(rr // 2, np.zeros_like(rr), 9) > 0.55)).astype(np.int32)
        base = np.full((rows, 1), cfg['rgbsplit'] // 2 + 1, np.int32)
        idx_c = np.arange(cols)[None, :]
        out = np.empty_like(G)
        for k, s in enumerate((-1, 0, 1)):
            src_c = np.clip(idx_c + s * (base + np.abs(off)) + off * (k != 1), 0, cols - 1)
            out[..., k] = np.take_along_axis(G[..., k], src_c, axis=1)
        G = out
    if cfg.get('post'):                                                  # pixel art: snap the colours to a small palette
        q = cfg['post']; G = np.round(G * q) / q
    Y = (G * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1).astype(np.float32)
    L = cv2.GaussianBlur(Y, (0, 0), 0.9)
    gx = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)
    return G.astype(np.float32), Y.astype(np.float32), np.arctan2(gy, gx), np.hypot(gx, gy), work


def render_cells(cfg, G, Y, ed, em, c0, r0, c1, r1, sw, sh, W, H, rows_total, chars, bm, ink, out_hw=None):
    """draw cells [r0:r1, c0:c1]; returns a float image. With out_hw=None the strip is shrunk to its share of the W x H master."""
    cols_total = G.shape[1]
    idx_all = pick_glyphs(Y, ed, em, cfg, chars, ink)
    bgk = cfg['bgk']
    R = 24
    pieces = []
    for a in range(r0, r1, R):
        b = min(r1, a + R)
        g = idx_all[a:b, c0:c1]; col = G[a:b, c0:c1]
        cov = bm[g]                                                      # (R, C, sh, sw)
        f = ink[g][..., None]
        bg = col * bgk
        fg = np.clip(bg + (col - bg) / np.maximum(f * 2.2, 0.12), 0, 1)
        strip = bg[:, :, None, None, :] + cov[..., None] * (fg - bg)[:, :, None, None, :]
        strip = strip.transpose(0, 2, 1, 3, 4).reshape((b - a) * sh, (c1 - c0) * sw, 3)
        if out_hw is None:
            y0 = int(round(a * H / rows_total)); y1 = int(round(b * H / rows_total))
            strip = cv2.resize(strip, (W, y1 - y0), interpolation=cv2.INTER_AREA)
        pieces.append(strip)
    return np.concatenate(pieces, 0)


def tone_lock(img, target, sigma):
    """make the card's tone and colour match the painting exactly at the scale of a few cells, and keep the glyph texture on top of it."""
    sigma = max(1.0, sigma)
    tl = cv2.GaussianBlur(target.astype(np.float32), (0, 0), sigma); rl = cv2.GaussianBlur(img, (0, 0), sigma)
    gain = np.clip((tl + 0.015) / (rl + 0.015), 0.55, 3.2)
    return np.clip(img * gain, 0, 1)


def finish(img, cfg, W):
    s = W / 1800
    bl, bs = cfg['bloom']
    hi = np.clip(img - 0.55, 0, 1)
    glow = cv2.GaussianBlur(hi, (0, 0), max(1.0, bl * W * 2.2)) * 1.0 + cv2.GaussianBlur(hi, (0, 0), max(1.0, bl * W * 7)) * 0.6
    img = 1 - (1 - img) * (1 - np.clip(glow * bs * 2.2, 0, 1))
    if cfg.get('scan'):
        yy = np.arange(img.shape[0])[:, None, None]; img = img * (1 - cfg['scan'] * (np.sin(yy * np.pi / (1.6 * s + 0.6)) * 0.5 + 0.5))
    rng = np.random.default_rng(5)
    n = rng.normal(0, 1, img.shape[:2]).astype(np.float32); n = cv2.GaussianBlur(n, (0, 0), 0.55 * s) * 1.9
    lum = img.mean(-1, keepdims=True)
    img = img + n[..., None] * cfg['grain'] * (0.35 + 1.1 * lum * (1 - lum) * 2.2)
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]].astype(np.float32)
    v = 1 - 0.13 * ((((xx / img.shape[1] - 0.5) * 2) ** 2 + ((yy / img.shape[0] - 0.5) * 2) ** 2) ** 1.2) / 2
    return np.clip(img * v[..., None], 0, 1)


def render_card(key, W=1800, H=2184, macro_px=None):
    cfg = CARDS[key]
    t0 = time.time()
    G, Y, ed, em, work = build_cells(cfg, W, H)
    rows, cols = Y.shape
    bm, ink, chars = atlas(cfg['family'])
    img = render_cells(cfg, G, Y, ed, em, 0, 0, cols, rows, SW, SH, W, H, rows, list(chars), bm, ink)
    img = finish(tone_lock(img, work, W / cols * 2.6), cfg, W)
    return img, dict(cols=cols, rows=rows, chars=cols * rows, secs=round(time.time() - t0, 1), glyphs=chars)


def render_macro(key, W=1800, H=2184, win=(58, 32), at=None, px=(18, 31)):
    """a window of real glyphs at reading size: win = (cells wide, cells tall), at = where on the card (x, y fractions)."""
    cfg = CARDS[key]
    at = at or cfg.get('macro_at', (0.5, 0.36))
    G, Y, ed, em, work = build_cells(cfg, W, H)
    rows, cols = Y.shape
    sw, sh = px
    bm, ink, chars = atlas(cfg['family'], sw, sh, hi=4)
    c0 = int(min(max(at[0] * cols - win[0] / 2, 0), cols - win[0])); r0 = int(min(max(at[1] * rows - win[1] / 2, 0), rows - win[1]))
    img = render_cells(cfg, G, Y, ed, em, c0, r0, c0 + win[0], r0 + win[1], sw, sh, W, H, rows, list(chars), bm, ink, out_hw=True)
    tgt = cv2.resize(G[r0:r0 + win[1], c0:c0 + win[0]], (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)
    img = tone_lock(img, tgt, sw * 2.6)
    cfg2 = dict(cfg); cfg2['grain'] = cfg['grain'] * 0.4
    return finish(img, cfg2, win[0] * sw * 1.0)


def save(img, path, q=90):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path, quality=q, subsampling=0, optimize=True)


def derive(key, out, img=None):
    """the small copies the app loads: m/ (720 wide, tiles and the card window) and s/ (360 wide, lists), made from the master."""
    if img is None:
        img = np.asarray(Image.open(os.path.join(out, key + '.jpg')).convert('RGB'), np.float32) / 255
    save(cv2.resize(img, (720, 874), interpolation=cv2.INTER_AREA), os.path.join(out, 'm', key + '.jpg'), 84)
    save(cv2.resize(img, (360, 437), interpolation=cv2.INTER_AREA), os.path.join(out, 's', key + '.jpg'), 82)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cards', default=','.join(ORDER)); ap.add_argument('--out', default=os.path.join(HERE, 'out'))
    ap.add_argument('--scale', type=float, default=1.0); ap.add_argument('--quality', type=int, default=85)
    ap.add_argument('--list', action='store_true'); ap.add_argument('--no-macro', action='store_true'); ap.add_argument('--derive', action='store_true', help='only rebuild m/ and s/ from the masters in --out')
    a = ap.parse_args()
    if a.list:
        for k in ORDER:
            c, r = grid(CARDS[k]['cols']); print(f"{CARDS[k]['no']} {CARDS[k]['name']:<12} {c} x {r} = {c * r:,} characters   ({CARDS[k]['src']})")
        return
    if a.derive:
        for k in a.cards.split(','): derive(k, a.out); print('derived', k)
        return
    W, H = int(1800 * a.scale), int(2184 * a.scale)
    for k in a.cards.split(','):
        img, info = render_card(k, W, H)
        save(img, os.path.join(a.out, k + '.jpg'), a.quality)
        if a.scale == 1.0: derive(k, a.out, img)
        if not a.no_macro and a.scale == 1.0:
            save(render_macro(k), os.path.join(a.out, 'macro', k + '.jpg'), 86)
        print(f"{k}: {info['cols']} x {info['rows']} = {info['chars']:,} characters in {info['secs']} s  ->  {os.path.join(a.out, k + '.jpg')}")


if __name__ == '__main__':
    main()
