"""The Ronin look: a picture read as a grid of real characters, one glyph per cell, chosen from a long ladder of ink densities, white on black.
Big enough that you can read the letters when you look closely, and the picture still appears when you step back.

    python3 ronin_render.py in.png out.jpg [cols]
"""
import sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'

def render(src, dst, cols=96, W=900, H=1092, tint=(238, 238, 232), gamma=.85, quality=82, maxb=260 * 1024):
    im = Image.open(src).convert('L'); w, h = im.size; th = int(w * H / W); top = max(0, (h - th) // 2)
    im = im.crop((0, top, w, min(h, top + th))); cw = W / cols; ch = cw * 1.95; rows = int(H / ch)
    a = np.asarray(im.resize((cols * 4, rows * 4), Image.LANCZOS), 'float32') / 255
    a = cv2.resize(a, (cols, rows), interpolation=cv2.INTER_AREA)
    rgb = np.asarray(Image.open(src).convert('RGB').crop((0, top, w, min(h, top + th))).resize((cols, rows), Image.BOX), 'float32')
    lo, hi = np.percentile(a, 3), np.percentile(a, 99.5); a = np.clip((a - lo) / max(.05, hi - lo), 0, 1) ** gamma
    out = Image.new('RGB', (W, H), (5, 5, 6)); d = ImageDraw.Draw(out); f = ImageFont.truetype(FONT, cw / .602)
    for y in range(rows):
        for x in range(cols):
            v = a[y, x]
            if v < .035: continue
            g = RAMP[min(len(RAMP) - 1, int(v * (len(RAMP) - 1) + .5))]
            c = rgb[y, x]; m = max(c.max(), 1); k = min(1.0, .72 + v * .6) * 255 / m; col = tuple(int(min(255, c[i] * k)) for i in range(3))   # the picture's own colour, brightened so every glyph reads
            d.text(((x + .5) * cw, (y + .55) * ch), g, font=f, fill=col, anchor='mm')
    q = quality
    while True:
        out.save(dst, 'JPEG', quality=q, optimize=True)
        import os
        if os.path.getsize(dst) <= maxb or q <= 50: break
        q -= 5
    return out

if __name__ == '__main__':
    render(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 96)
