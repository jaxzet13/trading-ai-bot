"""The ASCII style deck: the same card pulled in every style. Odds and value multipliers are the app's own FX_VAR numbers.
Writes the card images, a labelled sheet, styles.json, and a hash-roll simulation that checks the odds."""
import json, os, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
import ascii2 as A, ascii3 as E

import sys
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sources', 'frog.png')
COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 7844
S = int(sys.argv[2]) if len(sys.argv) > 2 else 2
TAG = sys.argv[3] if len(sys.argv) > 3 else 'deck'
OUT = f'./{TAG}/'; os.makedirs(OUT, exist_ok=True)
ASP = {'ramp': A.ASPECT, 'text': A.ASPECT, 'edge': A.ASPECT, 'braille': A.ASPECT, 'blocks': A.ASPECT}   # one grid per tier, for every style
def cols_for(count, aspect):
    # count = cols * rows, rows = ART_H * cols / (W * aspect)  ->  cols = sqrt(count * W * aspect / ART_H)
    return int(round((count * A.W * aspect / A.ART_H) ** 0.5))
NAME, CODE, CAP = 'Stitch', 'IS001-000012-XW8P', 'frog hat. zero regrets.'
CROP, PAD = (0.04, 0.04, 0.96, 0.96), 0.04
# id (app FX key), display name, engine, how to render, chance, value multiplier
STYLES = [
    ('base',    'Bone',          'ramp',    dict(style='classic', pal='bone', cols=106, black=0.06, white=0.80, gamma=0.7, glow=0.35),                0.0,    1),
    ('steel',   'Phosphor',      'ramp',    dict(style='classic', pal='phosphor', cols=106, black=0.06, white=0.80, gamma=0.7, glow=0.35),             .006,   3),
    ('dots',    'Amber',         'ramp',    dict(style='classic', pal='amber', cols=106, black=0.06, white=0.80, gamma=0.7, glow=0.35),                .005,   3),
    ('vhs',     'Glitch',        'ramp',    dict(style='glitch', pal='violet', cols=106, black=0.05, white=0.85, gamma=0.8, glow=0.6),                 .004,   3.5),
    ('scratch', 'Typeset',       'text',    dict(cols=70, style='classic', pal='bone', font='spacemono', text='frog hat. zero regrets.', black=0.18, white=0.90, gamma=0.8, thr=0.16, glow=0.5), .004, 3.5),
    ('ice',     'Stipple',       'braille', dict(cols=120, style='duo', pal='blue', font='dejavu', black=0.05, white=0.60, gamma=0.55, glow=0.8),        .0025,  5),
    ('chain',   'Linework',      'edge',    dict(cols=120, style='classic', pal='bone', font='jetbrains', black=0.05, white=0.80, gamma=0.7, glow=0.6),   .0025,  5),
    ('wire',    'Pixel',         'blocks',  dict(cols=64, style='duo', pal='acid', black=0.06, white=0.85, gamma=0.8, glow=0.5),                          .002,   6),
    ('print',   'Blood',         'ramp',    dict(style='classic', pal='blood', cols=106, black=0.06, white=0.80, gamma=0.7, glow=0.5),                    .002,   6),
    ('glass',   'Glow',          'ramp',    dict(style='duo', pal='magenta', cols=106, black=0.05, white=0.75, gamma=0.7, glow=0.8),                      .001,  10),
    ('blood',   'Toxic Glitch',  'ramp',    dict(style='glitch', pal='toxic', cols=106, black=0.05, white=0.85, gamma=0.8, glow=0.6),                     .001,  10),
    ('leaf',    'Iridescent',    'ramp',    dict(style='irid', pal='oil', cols=140, black=0.06, white=0.90, gamma=0.8, glow=0.8),                         .0006, 15),
    ('kin',     'Dissolve',      'blocks',  dict(cols=80, style='duo', pal='blue', smooth_until=0.46, smooth_band=0.28, black=0.05, white=0.85, gamma=0.8, glow=0.6), .0003, 25),
]

cells = []
for fid, name, kind, kw, chance, mult in STYLES:
    out = f'{OUT}{fid}.jpg'
    kw = dict(kw); kw.pop('cols', None)
    cols = cols_for(COUNT, ASP[kind if kind in ASP else 'ramp'])
    if kind == 'ramp':
        style = kw.pop('style')
        n = A.render(SRC, out, NAME, CODE, '', style, cols, S, crop=CROP, pad=PAD, caption=CAP, typo='line', **kw)
    else:
        n = E.render(SRC, out, NAME, CODE, '', kind, cols, S, crop=CROP, pad=PAD, caption=CAP, **kw)
    odds = '' if chance == 0 else f'1 in {round(1 / chance):,}'
    cells.append((fid, name, odds, mult, n, out)); print(fid, name, odds, f'{n:,}')

# ---- the sheet: 7 x 2 thumbnails with name, odds and multiplier burned into a strip above each
TW, TH, G, LH = 300, 420, 14, 74
F = lambda s: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf', s)
Fr = lambda s: ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', s)
cols_n = 7; rows_n = 2
sheet = Image.new('RGB', (cols_n * (TW + G) + G, rows_n * (TH + LH + G) + G), (14, 14, 15)); d = ImageDraw.Draw(sheet)
for i, (fid, name, odds, mult, n, out) in enumerate(cells):
    x = G + (i % cols_n) * (TW + G); y = G + (i // cols_n) * (TH + LH + G)
    d.text((x, y + 4), name.upper(), font=F(17), fill=(236, 231, 220))
    d.text((x, y + 28), (odds + '  x' + (f'{mult:g}')) if odds else 'default  x1', font=Fr(14), fill=(160, 156, 148))
    d.text((x, y + 48), f'{n:,} chars', font=Fr(13), fill=(100, 98, 94))
    sheet.paste(Image.open(out).convert('RGB').resize((TW, TH), Image.LANCZOS), (x, y + LH))
sheet.save(f'./{TAG}_sheet.jpg', quality=90); sheet.save(OUT + '_sheet.jpg', quality=92)

# ---- styles.json + a roll that mirrors the app: roll(fnv("fx:" + code) / 2^32) over the same cumulative odds
def fnv(s):
    h = 0x811c9dc5
    for ch in s.encode('utf-8'): h ^= ch; h = (h * 0x01000193) & 0xffffffff
    return h
order = [s for s in STYLES if s[0] != 'base']
def roll(code):
    u = fnv('fx:' + code) / 4294967296; acc = 0
    for fid, name, kind, kw, chance, mult in order:
        acc += chance
        if u < acc: return fid
    return 'base'
import random
rng = random.Random(5); N = 400000; cnt = {}
B32 = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
for i in range(N):
    code = f'IS{rng.randint(1, 47):03d}-{rng.randint(1, 99999):06d}-' + ''.join(rng.choice(B32) for _ in range(4))
    r = roll(code); cnt[r] = cnt.get(r, 0) + 1
rows = []
for fid, name, kind, kw, chance, mult in STYLES:
    obs = cnt.get(fid, 0) / N
    rows.append(dict(id=fid, name=name, engine=kind, palette=kw.get('pal'), chance=chance if chance else None, odds=(f'1 in {round(1 / chance):,}' if chance else 'default'), value_x=mult, observed=round(obs, 5)))
json.dump(rows, open(OUT + 'styles.json', 'w'), indent=2)
print('default share', round(cnt.get('base', 0) / N, 4), '| total styled', round(1 - cnt.get('base', 0) / N, 4), '| target', round(sum(s[4] for s in STYLES), 4))
for r in rows: print(f"{r['name']:<13}{r['odds']:>11}  x{r['value_x']:<5} target {r['chance'] or 0:.4f}  seen {r['observed']:.4f}")
