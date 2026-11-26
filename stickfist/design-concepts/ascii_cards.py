"""Turns every card picture into text: the picture is read as a grid of cells, and each cell becomes the one character whose ink matches
its brightness, in that cell's colour, on black. Nothing is left of the picture but characters.

    python3 ascii_cards.py              # all cards (cards/*.jpg and cards/s/*.jpg)
    python3 ascii_cards.py reaper       # one card, with its styles
    python3 ascii_cards.py --check      # sizes only, nothing written (writes to /tmp)

The originals stay in git history. Run it on the picture files in cards/ once; running it again on its own output only re-reads text.
"""
import glob, os, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); CARDS = os.path.join(ROOT, 'cards')
RAMP = " .,:;-=+*xo%#&@"; FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'; MAXB = 230 * 1024
_fonts = {}
def font(px):
    k = round(px * 4) / 4
    if k not in _fonts: _fonts[k] = ImageFont.truetype(FONT, k)
    return _fonts[k]

def convert(src, dst, cols, quality=80):
    im = Image.open(src).convert('RGB'); W, H = im.size; cw = W / cols; ch = cw * 1.7; rows = int(H / ch + .5)
    small = im.resize((cols, rows), Image.BOX)
    lo, hi = sorted(small.convert('L').get_flattened_data())[len(small.get_flattened_data()) // 50], sorted(small.convert('L').get_flattened_data())[-len(small.get_flattened_data()) // 50]; span = max(40, hi - lo)         # stretch the picture so its darkest part is black and its brightest is full
    small = small.point(lambda v: max(0, min(255, int((v - lo * .6) * 255 / (span + lo * .4)))))
    px = small.load(); out = Image.new('RGB', (W, H), (3, 3, 4)); d = ImageDraw.Draw(out); f = font(cw / .602)
    for y in range(rows):
        for x in range(cols):
            r, g, b = px[x, y]; l = (r * .299 + g * .587 + b * .114) / 255
            if l < .03: continue
            m = max(r, g, b) or 1; k = min(1, .72 + l * .6) * 255 / m; col = (min(255, int(r * k)), min(255, int(g * k)), min(255, int(b * k)))
            d.text(((x + .5) * cw, (y + .55) * ch), RAMP[min(len(RAMP) - 1, int((l ** .62) * (len(RAMP) - 1) + .5))], font=f, fill=col, anchor='mm')
    q = quality
    while True:
        out.save(dst, 'JPEG', quality=q, optimize=True, subsampling=2)
        if os.path.getsize(dst) <= MAXB or q <= 45: break
        q -= 5
    return os.path.getsize(dst)

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]; check = '--check' in sys.argv; tot = 0; n = 0; big = 0
    for big_dir, cols in ((CARDS, 80), (os.path.join(CARDS, 's'), 30)):
        for f in sorted(glob.glob(os.path.join(big_dir, '*.jpg'))):
            name = os.path.basename(f)[:-4]
            if args and name.split('-')[0] not in args: continue
            dst = os.path.join('/tmp/ascii_check', os.path.relpath(f, CARDS)) if check else f
            os.makedirs(os.path.dirname(dst), exist_ok=True); sz = convert(f, dst, cols); tot += sz; n += 1; big = max(big, sz)
    print(n, 'pictures,', round(tot / 1e6, 1), 'MB, largest', round(big / 1024), 'KB')
