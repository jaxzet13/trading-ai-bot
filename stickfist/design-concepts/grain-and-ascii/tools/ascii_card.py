"""ASCII print: the figure rebuilt from monospace glyphs (denser glyph = brighter), bone on black, with a soft glow.
The name and copy ID are set in the same monospace so the type belongs to the picture.
usage: python ascii_card.py ART.png OUT.png NAME CODE MARK [black white gamma tint crop]"""
import sys, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1500, 2100
FONT = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf'
FONTB = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf'
RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
TINT = {'bw': (236, 231, 220), 'blue': (214, 224, 255), 'red': (255, 214, 206), 'brass': (250, 222, 160)}


def render(art, out, name, code, mark='', black=0.04, white=0.85, gamma=0.75, tint='bw', crop=0.5, cw=15, chh=26, glow=0.55):
    img = cv2.imread(art)
    h0, w0 = img.shape[:2]; k = max(W / w0, H / h0)
    img = cv2.resize(img, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_AREA)
    y0 = int((img.shape[0] - H) * crop); x0 = (img.shape[1] - W) // 2
    img = img[y0:y0 + H, x0:x0 + W]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    cols, rows = W // cw, (H - 150) // chh
    small = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA)
    t = np.clip((small - black) / (white - black), 0, 1) ** gamma
    font = ImageFont.truetype(FONT, int(chh * 0.92))
    base = np.array(TINT[tint], np.float32)
    canvas = Image.new('RGB', (W, H), (4, 4, 5)); d = ImageDraw.Draw(canvas)
    oy = 20
    for r in range(rows):
        for c in range(cols):
            v = t[r, c]
            if v < 0.035: continue
            ch = RAMP[min(len(RAMP) - 1, int(v * (len(RAMP) - 1) + 0.5))]
            if ch == ' ': continue
            col = tuple(int(x * (0.62 + 0.38 * v)) for x in base)
            d.text((c * cw + 1, oy + r * chh), ch, font=font, fill=col)
    arr = np.asarray(canvas).astype(np.float32) / 255
    bl = cv2.GaussianBlur(arr, (0, 0), 16) * glow + cv2.GaussianBlur(arr, (0, 0), 4) * 0.18
    arr = np.clip(arr + bl, 0, 1)
    rng = np.random.default_rng(3)
    arr += cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 0.7)[..., None] * 0.012
    # the type: same mono, spaced wide, small
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)); d = ImageDraw.Draw(im)
    fb = ImageFont.truetype(FONTB, 46); fs = ImageFont.truetype(FONT, 26)
    label = ' '.join(name.upper()); tw = d.textlength(label, font=fb)
    d.rectangle([(W - tw) / 2 - 24, H - 168, (W + tw) / 2 + 24, H - 100], fill=(4, 4, 5))
    d.text(((W - tw) / 2, H - 160), label, font=fb, fill=TINT[tint])
    idt = code + ('  ' + mark if mark else ''); iw = d.textlength(idt, font=fs)
    d.text(((W - iw) / 2, H - 72), code, font=fs, fill=tuple(int(x * 0.72) for x in TINT[tint]))
    if mark: d.text(((W + iw) / 2 - d.textlength(mark, font=fs), H - 72), mark, font=ImageFont.truetype(FONTB, 26), fill=(224, 32, 44))
    im.save(out); return out


if __name__ == '__main__':
    a = sys.argv
    kw = {}
    for s in a[6:]:
        k, v = s.split('='); kw[k] = v if k == 'tint' else (int(v) if k in ('cw', 'chh') else float(v))
    render(a[1], a[2], a[3], a[4], a[5], **kw); print('ok', a[2])
