"""ASCII print where RARITY = RESOLUTION: the picture is built from a fixed grid of monospace characters
(denser glyph = brighter). A rarer card has a finer grid, i.e. more characters, and the card prints that exact count.
count = columns x rows of the picture (spaces are characters too).
usage: python ascii_card.py ART.png OUT.png NAME CODE MARK TIER [black white gamma tint shift glow ...]"""
import sys, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1500, 2100
ART_H = 1820                                   # the picture; the strip below it is for type
FONT = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf'
FONTB = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf'
RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
TINT = {'bw': (236, 231, 220), 'blue': (214, 224, 255), 'red': (255, 214, 206), 'brass': (250, 222, 160)}
ASPECT = 1.73                                   # character cell height / width for the font

# the ladder: columns of characters across the card, per rarity
TIERS = [('C', 'Common', 56), ('U', 'Uncommon', 70), ('R', 'Rare', 86), ('H', 'Foil Rare', 106), ('RR', 'Signature', 130),
         ('UR', 'Chrome', 156), ('IR', 'Full Art', 184), ('SIR', 'Masterwork', 214), ('HR', 'Gilded', 246), ('CX', 'Completer', 280)]
COLS = {c: n for c, _, n in TIERS}


def grid(cols):
    cw = W / cols; chh = cw * ASPECT
    return cw, chh, int(ART_H / chh)


def count_for(tier):
    cols = COLS[tier]; return cols * grid(cols)[2]


def _layer(g, cols, black, white, gamma, base, gain, bold):
    """draw one grid of glyphs; returns (float image, mean tone of the grid)"""
    cw, chh, rows = grid(cols)
    small = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA)
    t = np.clip((small - black) / (white - black), 0, 1) ** gamma
    fr = max(3, int(round(260 / chh)))
    t *= np.clip((rows - np.arange(rows, dtype=np.float32)) / fr, 0, 1)[:, None] ** 1.4
    font = ImageFont.truetype(FONTB if bold else FONT, max(5, int(chh * 0.92)))
    canvas = Image.new('RGB', (W, H), (4, 4, 5)); d = ImageDraw.Draw(canvas)
    for r in range(rows):
        for c in range(cols):
            v = t[r, c]
            if v < 0.035: continue
            ch = RAMP[min(len(RAMP) - 1, int(v * (len(RAMP) - 1) + 0.5))]
            if ch == ' ': continue
            d.text((c * cw + 0.08 * cw, r * chh), ch, font=font, fill=tuple(min(255, int(x * (0.62 + 0.38 * v) * gain)) for x in base))
    return np.asarray(canvas).astype(np.float32) / 255, float(t.mean())


def render(art, out, name, code, mark, tier, black=0.04, white=0.85, gamma=0.75, tint='bw', shift=0, glow=0.5):
    cols = COLS[tier]; cw, chh, rows = grid(cols); count = cols * rows
    img = cv2.imread(art)
    h0, w0 = img.shape[:2]; k = max(W / w0, ART_H / h0)
    img = cv2.resize(img, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_AREA)
    x0 = (img.shape[1] - W) // 2; shift = min(int(shift), img.shape[0] - ART_H)
    g = cv2.cvtColor(img[shift:shift + ART_H, x0:x0 + W], cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    base = np.array(TINT[tint], np.float32)
    # brightness calibration: every tier gets the same overall tone as the coarsest one; only the detail differs
    la, ta = _layer(g, COLS['C'], black, white, gamma, base, 1.0, False)
    ratio = la[:ART_H].mean() / max(ta, 1e-6)
    bold = cols >= 106
    arr, tm = _layer(g, cols, black, white, gamma, base, 1.0, bold)
    gain = float(np.clip(ratio * tm / max(arr[:ART_H].mean(), 1e-6), 0.9, 4.0))
    if abs(gain - 1) > 0.03: arr, _ = _layer(g, cols, black, white, gamma, base, gain, bold)
    bl = cv2.GaussianBlur(arr, (0, 0), 16) * glow + cv2.GaussianBlur(arr, (0, 0), 4) * 0.18
    arr = np.clip(arr + bl, 0, 1)
    arr[ART_H + 20:] = np.minimum(arr[ART_H + 20:], 0.02)
    rng = np.random.default_rng(3)
    arr += cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 0.7)[..., None] * 0.012
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    fb = ImageFont.truetype(FONTB, 46); fn = ImageFont.truetype(FONTB, 104); fs2 = ImageFont.truetype(FONT, 24); fl = ImageFont.truetype(FONT, 22); fm = ImageFont.truetype(FONTB, 24)
    tc = TINT[tint]; dim = tuple(int(x * 0.62) for x in tc); R = W - 110
    num = f'{count:,}'; nw = d.textlength(num, font=fn)
    d.text((R - nw, H - 268), num, font=fn, fill=tc)                                              # THE NUMBER
    lab = 'C H A R A C T E R S'; d.text((R - d.textlength(lab, font=fl), H - 150), lab, font=fl, fill=dim)
    mw = d.textlength(mark, font=fm) if mark else 0
    d.text((R - mw - (14 if mark else 0) - d.textlength(code, font=fs2), H - 112), code, font=fs2, fill=dim)   # copy ID
    if mark: d.text((R - mw, H - 112), mark, font=fm, fill=(224, 32, 44))
    d.text((110, H - 138), ' '.join(name.upper()), font=fb, fill=tc)                              # name, left
    im.save(out); return count


if __name__ == '__main__':
    a = sys.argv
    kw = {}
    for s in a[7:]:
        k, v = s.split('='); kw[k] = v if k == 'tint' else float(v)
    n = render(a[1], a[2], a[3], a[4], a[5], a[6], **kw); print('ok', a[2], n)
