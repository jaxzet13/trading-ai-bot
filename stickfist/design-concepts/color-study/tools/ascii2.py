"""ASCII cards, one STYLE per rarity. Rarity = resolution (the card prints its exact character count) and each tier
has its own character set and colour treatment:
  classic  (Common)    bold, chunky, 10 symbols, bone on black
  duo      (Rare)      glowing blue-to-white duotone, 14 characters
  glitch   (Epic)      VHS: digits only, torn rows, magenta/cyan split, scanlines
  irid     (Legendary) oil-slick iridescence, all 70 characters, tiny
usage: python ascii2.py ART.png OUT NAME CODE MARK STYLE COLS SCALE [black white gamma shift glow]"""
import sys, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, ART_H = 1500, 2100, 1820
ASPECT = 1.73
FONT = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf'
FONTB = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf'
R70 = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
RAMPS = {'classic': " .:-=+*#%@", 'duo': " .,:;i1tfLCG08@", 'glitch': " .:1l7I4Z9O6B8@", 'irid': R70}
BONE = np.array([236, 231, 220], np.float32)


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)


PALETTES = {
    # classic: one ink colour (RGB), brightest glyphs go toward white
    'classic': {'bone': (236, 231, 220), 'phosphor': (92, 255, 140), 'amber': (255, 176, 40), 'blood': (255, 62, 56), 'ice': (120, 226, 255)},
    # duo: (shadow colour, highlight colour)
    'duo': {'blue': ((40, 120, 255), (226, 238, 255)), 'magenta': ((255, 20, 150), (255, 214, 240)), 'acid': ((60, 255, 40), (226, 255, 190)),
            'amber': ((255, 120, 0), (255, 236, 190)), 'blood': ((235, 10, 36), (255, 226, 220))},
    # glitch: base colour (the RGB split adds the fringes around it)
    'glitch': {'violet': ((150, 70, 255), (246, 242, 255)), 'red': ((255, 40, 50), (255, 236, 230)), 'toxic': ((70, 255, 90), (232, 255, 226)),
               'cyan': ((20, 220, 255), (232, 252, 255)), 'hot': ((255, 40, 180), (255, 232, 246))},
    # irid: (hue start, hue span) on the colour wheel, 0..1
    'irid': {'oil': (0.60, 1.25), 'fire': (0.97, 0.20), 'toxic': (0.20, 0.30), 'aurora': (0.38, 0.50), 'candy': (0.80, 0.45)},
}
DEFAULT_PAL = {'classic': 'bone', 'duo': 'blue', 'glitch': 'violet', 'irid': 'oil'}


def colours(style, t, rows, cols, pal=None, seed=4):
    pal = pal or DEFAULT_PAL[style]; v = t[..., None]
    if style == 'classic':
        ink = np.array(PALETTES['classic'][pal], np.float32)
        return np.clip(ink * (0.62 + 0.38 * v) + 255 * 0.14 * (v ** 4), 0, 255)
    if style == 'duo':
        lo, hi = (np.array(c, np.float32) for c in PALETTES['duo'][pal])
        m = smooth(t, 0.62, 1.0)[..., None]                    # only the very brightest glyphs go pale; the rest keep the colour
        return np.clip((lo * (1 - m) + hi * m) * (0.62 + 0.38 * v) * 1.08, 0, 255)
    if style == 'glitch':
        lo, hi = (np.array(c, np.float32) for c in PALETTES['glitch'][pal])
        m = smooth(t, 0.25, 0.85)[..., None]
        return np.clip((lo * (1 - m) + hi * m) * (0.6 + 0.4 * v), 0, 255)
    h0, span = PALETTES['irid'][pal]                       # iridescent: hue follows brightness + a warped noise field + height
    rng = np.random.default_rng(seed)
    n = cv2.resize(rng.normal(0, 1, (rows // 14 + 3, cols // 14 + 3)).astype(np.float32), (cols, rows), interpolation=cv2.INTER_CUBIC)
    y = np.linspace(0, 1, rows, dtype=np.float32)[:, None]
    k = span / 1.25
    hue = (h0 + span * t + 0.30 * k * n + 0.45 * k * y) % 1.0
    hsv = np.dstack([hue * 360, np.full_like(t, 0.82), np.clip(0.70 + 0.30 * t, 0, 1)]).astype(np.float32)
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return np.clip(rgb * 255 * (0.62 + 0.38 * np.clip(t * 1.4, 0, 1))[..., None] + BONE * 0.30 * (t[..., None] ** 3), 0, 255)


def glitch_post(arr, S, seed=9):
    """VHS: tear rows sideways, split the channels, smear, and lay scanlines"""
    h, w, _ = arr.shape; rng = np.random.default_rng(seed)
    base = cv2.resize(rng.normal(0, 1, (h // (50 * S) + 3, 1)).astype(np.float32), (1, h), interpolation=cv2.INTER_CUBIC)[:, 0] * 10 * S
    dx = base.copy()
    for _ in range(14):                                            # hard tears
        y0 = int(rng.integers(0, h - 80 * S)); hh = int(rng.integers(5 * S, 38 * S))
        dx[y0:y0 + hh] += rng.choice([-1, 1]) * rng.uniform(25, 95) * S
    out = np.empty_like(arr)
    for ch, off in ((0, 9 * S), (1, 0), (2, -9 * S)):             # R, G, B drift apart
        for y in range(h):
            out[y, :, ch] = np.roll(arr[y, :, ch], int(dx[y] + off))
    out[..., 0] = cv2.GaussianBlur(out[..., 0], (0, 0), sigmaX=2.6 * S, sigmaY=0.4 * S)
    out[..., 2] = cv2.GaussianBlur(out[..., 2], (0, 0), sigmaX=2.6 * S, sigmaY=0.4 * S)
    yy = np.arange(h)
    out *= (1 - 0.24 * ((yy % (3 * S)) < S))[:, None, None]
    return out


def render(art, out, name, code, mark, style, cols, S=1, black=0.05, white=0.9, gamma=0.8, shift=0, glow=0.5, pad=0.0, pal=None):
    cols, S, shift = int(cols), int(S), int(shift)
    cw = W * S / cols; chh = cw * ASPECT; rows = int(ART_H * S / chh); count = cols * rows
    img = cv2.imread(art)
    if pad > 0:                                                    # a black margin so the figure never touches the edge
        ph, pw = int(img.shape[0] * pad), int(img.shape[1] * pad * 0.8)
        img = cv2.copyMakeBorder(img, ph, int(ph * 0.6), pw, pw, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    h0, w0 = img.shape[:2]; k = max(W / w0, ART_H / h0)
    img = cv2.resize(img, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_AREA)
    x0 = (img.shape[1] - W) // 2; shift = min(shift, img.shape[0] - ART_H)
    g = cv2.cvtColor(img[shift:shift + ART_H, x0:x0 + W], cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    small = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA)
    t = np.clip((small - black) / (white - black), 0, 1) ** gamma
    fr = max(3, int(round(260 * S / chh)))
    t *= np.clip((rows - np.arange(rows, dtype=np.float32)) / fr, 0, 1)[:, None] ** 1.4
    ramp = RAMPS[style]; col = colours(style, t, rows, cols, pal).astype(np.uint8).tolist()
    idx = np.minimum(len(ramp) - 1, (t * (len(ramp) - 1) + 0.5).astype(int))
    font = ImageFont.truetype(FONTB if (style != 'duo' or cols > 200) else FONT, max(5, int(chh * 0.92)))
    canvas = Image.new('RGB', (W * S, H * S), (4, 4, 5)); d = ImageDraw.Draw(canvas)
    for r in range(rows):
        y = r * chh; ri = idx[r]; rc = col[r]; tr = t[r]
        for c in range(cols):
            i = ri[c]
            if i == 0 or tr[c] < 0.035: continue
            d.text((c * cw + 0.08 * cw, y), ramp[i], font=font, fill=tuple(rc[c]))
    arr = np.asarray(canvas).astype(np.float32) / 255
    sm = cv2.resize(arr, (arr.shape[1] // 4, arr.shape[0] // 4), interpolation=cv2.INTER_AREA)
    gl = cv2.resize(cv2.GaussianBlur(sm, (0, 0), 16 * S / 4 * 4 / 4) * glow + cv2.GaussianBlur(sm, (0, 0), 3 * S) * 0.15, (arr.shape[1], arr.shape[0]))
    arr = np.clip(arr + gl, 0, 1)
    if style == 'glitch': arr = np.clip(glitch_post(arr, S), 0, 1)
    arr[(ART_H + 20) * S:] = np.minimum(arr[(ART_H + 20) * S:], 0.02)
    rng = np.random.default_rng(3)
    arr += cv2.GaussianBlur(rng.normal(0, 1, arr.shape[:2]).astype(np.float32), (0, 0), 0.7 * S)[..., None] * 0.012
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    f = lambda p, s: ImageFont.truetype(p, int(s * S))
    pn_ = pal or DEFAULT_PAL[style]
    if style == 'classic': tint = tuple(int(0.55 * c + 0.45 * 255) for c in PALETTES['classic'][pn_])
    elif style in ('duo', 'glitch'): tint = tuple(int(0.55 * c + 0.45 * 255) for c in PALETTES[style][pn_][0])
    else: tint = (236, 231, 220)
    dim = tuple(int(x * 0.62) for x in tint); R_ = (W - 110) * S
    num = f'{count:,}'; fn = f(FONTB, 104); nw = d.textlength(num, font=fn)
    d.text((R_ - nw, (H - 268) * S), num, font=fn, fill=tint)
    lab = 'C H A R A C T E R S'; fl = f(FONT, 22); d.text((R_ - d.textlength(lab, font=fl), (H - 150) * S), lab, font=fl, fill=dim)
    fs2 = f(FONT, 24); fm = f(FONTB, 24); mw = d.textlength(mark, font=fm) if mark else 0
    d.text((R_ - mw - (14 * S if mark else 0) - d.textlength(code, font=fs2), (H - 112) * S), code, font=fs2, fill=dim)
    if mark: d.text((R_ - mw, (H - 112) * S), mark, font=fm, fill=(224, 32, 44))
    d.text((110 * S, (H - 138) * S), ' '.join(name.upper()), font=f(FONTB, 46), fill=tint)
    if out.lower().endswith('.png'): im.save(out)
    else: im.save(out, quality=94)
    return count


if __name__ == '__main__':
    a = sys.argv
    kw = {k: (v if k == 'pal' else float(v)) for k, v in (s.split('=') for s in a[9:])}
    n = render(a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8], **kw); print('ok', a[2], f'{n:,}')
