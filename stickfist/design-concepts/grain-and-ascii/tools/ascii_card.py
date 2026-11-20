"""ASCII print: the figure rebuilt from monospace glyphs (denser glyph = brighter), bone on black, with a soft glow.
The picture fades out before the bottom; the name (left) and copy ID (right) live in the clear black strip,
set in the same monospace so the type belongs to the picture.
usage: python ascii_card.py ART.png OUT.png NAME CODE MARK [black white gamma tint shift art_h cw chh glow ...]"""
import sys, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1500, 2100
FONT = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf'
FONTB = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf'
RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
TINT = {'bw': (236, 231, 220), 'blue': (214, 224, 255), 'red': (255, 214, 206), 'brass': (250, 222, 160)}


def render(art, out, name, code, mark='', black=0.04, white=0.85, gamma=0.75, tint='bw', shift=0, art_h=1820,
           cw=11, chh=19, glow=0.5, fade_rows=12):
    art_h, shift = int(art_h), int(shift)
    img = cv2.imread(art)
    h0, w0 = img.shape[:2]; k = max(W / w0, art_h / h0)
    img = cv2.resize(img, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_AREA)
    x0 = (img.shape[1] - W) // 2; shift = min(shift, img.shape[0] - art_h)
    win = img[shift:shift + art_h, x0:x0 + W]
    g = cv2.cvtColor(win, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    cols, rows = W // cw, art_h // chh
    small = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA)
    t = np.clip((small - black) / (white - black), 0, 1) ** gamma
    fr = int(fade_rows)                                           # the last rows thin out into the black strip
    t *= np.clip((rows - np.arange(rows, dtype=np.float32)) / fr, 0, 1)[:, None] ** 1.4
    font = ImageFont.truetype(FONT, int(chh * 0.92))
    base = np.array(TINT[tint], np.float32)
    canvas = Image.new('RGB', (W, H), (4, 4, 5)); d = ImageDraw.Draw(canvas)
    for r in range(rows):
        for c in range(cols):
            v = t[r, c]
            if v < 0.035: continue
            ch = RAMP[min(len(RAMP) - 1, int(v * (len(RAMP) - 1) + 0.5))]
            if ch == ' ': continue
            d.text((c * cw + 1, r * chh), ch, font=font, fill=tuple(int(x * (0.62 + 0.38 * v)) for x in base))
    arr = np.asarray(canvas).astype(np.float32) / 255
    bl = cv2.GaussianBlur(arr, (0, 0), 16) * glow + cv2.GaussianBlur(arr, (0, 0), 4) * 0.18
    arr = np.clip(arr + bl, 0, 1)
    arr[art_h + 20:] = np.minimum(arr[art_h + 20:], 0.02)         # nothing glows into the strip
    rng = np.random.default_rng(3)
    arr += cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 0.7)[..., None] * 0.012
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    fb = ImageFont.truetype(FONTB, 46); fs = ImageFont.truetype(FONT, 25); fm = ImageFont.truetype(FONTB, 25)
    base_y = H - 92
    d.text((110, base_y - 46), ' '.join(name.upper()), font=fb, fill=TINT[tint])                 # name, left
    idc = tuple(int(x * 0.72) for x in TINT[tint]); gap = 14
    mw = d.textlength(mark, font=fm) if mark else 0
    cx = W - 110 - mw - (gap if mark else 0) - d.textlength(code, font=fs)
    d.text((cx, base_y - 25), code, font=fs, fill=idc)                                          # ID, right, same baseline
    if mark: d.text((W - 110 - mw, base_y - 25), mark, font=fm, fill=(224, 32, 44))
    im.save(out); return out


if __name__ == '__main__':
    a = sys.argv
    kw = {}
    for s in a[6:]:
        k, v = s.split('='); kw[k] = v if k == 'tint' else (int(v) if k in ('cw', 'chh', 'fade_rows') else float(v))
    render(a[1], a[2], a[3], a[4], a[5], **kw); print('ok', a[2])
