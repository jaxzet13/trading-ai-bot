"""Draws stick-figure cards in code: a figure in a pose, a hat, a prop in its hand, on a backdrop. The picture is 900 x 1092, like every card.
The pictures are then turned into text (../ascii_cards.py), so what a player sees is characters; this only has to be clear at 80 characters across,
which means big shapes, thick lines and a few strong colours.

    from draw import card;  card(dict(pose='wave', hat='crown', prop='umbrella', scene='dunes', hue=30)).save('x.png')
"""
import math, random
import numpy as np, cv2
from PIL import Image, ImageDraw

W, H = 900, 1092
INK = (246, 242, 232)

def hsv(h, s, v): import colorsys; r, g, b = colorsys.hsv_to_rgb((h % 360) / 360, s, v); return (int(r * 255), int(g * 255), int(b * 255))

def gradient(top, bot, glow=None):
    t = np.linspace(0, 1, H)[:, None, None]; img = (np.array(top)[None, None, :] * (1 - t) + np.array(bot)[None, None, :] * t) * np.ones((H, W, 1))
    if glow:
        cx, cy, r, col = glow; yy, xx = np.mgrid[0:H, 0:W]; k = np.clip(1 - np.hypot(xx - cx, yy - cy) / r, 0, 1) ** 1.7
        img = img * (1 - k[..., None]) + np.array(col)[None, None, :] * k[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype('uint8'))

def blur_glow(im, rad=22, amt=.55):
    a = np.asarray(im).astype('float32'); g = cv2.GaussianBlur(a, (0, 0), rad); return Image.fromarray(np.clip(a + g * amt, 0, 255).astype('uint8'))

# ---------------------------------------------------------------- the figure
# a pose is where the hands and feet go, as fractions of the figure's height, from the middle of the body (x) and the top of the head (y)
POSES = {
    'stand':  dict(lh=(-.28, .58), rh=(.28, .58), lf=(-.15, 1), rf=(.15, 1)),
    'wave':   dict(lh=(-.28, .58), rh=(.40, .08), lf=(-.15, 1), rf=(.15, 1)),
    'cheer':  dict(lh=(-.38, -.02), rh=(.38, -.02), lf=(-.2, 1), rf=(.2, 1)),
    'run':    dict(lh=(-.34, .38), rh=(.34, .72), lf=(-.32, .96), rf=(.3, .84), lean=.06),
    'jump':   dict(lh=(-.42, .2), rh=(.42, .2), lf=(-.24, .84), rf=(.24, .9), up=-.1),
    'flex':   dict(lh=(-.36, .24), rh=(.36, .24), lf=(-.17, 1), rf=(.17, 1)),
    'point':  dict(lh=(-.28, .58), rh=(.55, .2), lf=(-.15, 1), rf=(.15, 1)),
    'dance':  dict(lh=(-.38, .06), rh=(.3, .52), lf=(-.26, 1), rf=(.12, .9), lean=-.03),
    'hold':   dict(lh=(-.26, .6), rh=(.34, .46), lf=(-.14, 1), rf=(.14, 1)),
    'carry':  dict(lh=(.16, .48), rh=(.3, .54), lf=(-.14, 1), rf=(.14, 1)),
    'lunge':  dict(lh=(-.3, .5), rh=(.46, .3), lf=(-.38, .98), rf=(.3, .96)),
    'shrug':  dict(lh=(-.4, .38), rh=(.4, .38), lf=(-.14, 1), rf=(.14, 1)),
}

def figure(d, pose, cx, top, height, col=INK, lw=22, hat=None, prop=None, pcol=(255, 190, 80)):
    P = POSES[pose]; lean = P.get('lean', 0); up = P.get('up', 0)
    X = lambda u: cx + u * height; Y = lambda v: top + (v + up) * height
    head = (X(lean), Y(.09)); r = height * .085; neck = (X(lean * .6), Y(.19)); hip = (X(0), Y(.56))
    bones = [(neck, hip)]
    for hk, sh in (('lh', -1), ('rh', 1)):
        hx, hy = P[hk]; hand = (X(hx), Y(hy)); sho = (X(lean * .5), Y(.26)); mid = ((sho[0] + hand[0]) / 2 + sh * height * .03, (sho[1] + hand[1]) / 2 + height * .05)
        bones += [(sho, mid), (mid, hand)]
    for fk, sh in (('lf', -1), ('rf', 1)):
        fx, fy = P[fk]; foot = (X(fx), Y(fy)); mid = ((hip[0] + foot[0]) / 2 + sh * height * .05, (hip[1] + foot[1]) / 2 - height * .02)
        bones += [(hip, mid), (mid, foot)]
    d.ellipse([head[0] - r - 5, head[1] - r - 5, head[0] + r + 5, head[1] + r + 5], fill=(0, 0, 0))
    for a, b in bones:
        d.line([a, b], fill=(0, 0, 0), width=lw + 10);
    for a, b in bones:
        d.line([a, b], fill=col, width=lw); d.ellipse([b[0] - lw / 2, b[1] - lw / 2, b[0] + lw / 2, b[1] + lw / 2], fill=col)
    d.ellipse([head[0] - r, head[1] - r, head[0] + r, head[1] + r], fill=col)
    d.ellipse([head[0] - r * .5, head[1] - r * .25, head[0] - r * .2, head[1] + r * .05], fill=(10, 10, 14)); d.ellipse([head[0] + r * .2, head[1] - r * .25, head[0] + r * .5, head[1] + r * .05], fill=(10, 10, 14))
    if hat: HATS[hat](d, head[0], head[1] - r, r, pcol)
    if prop: PROPS[prop](d, X(P['rh'][0]), Y(P['rh'][1]), height / 5.5, pcol, col)
    return dict(head=head, hip=hip, foot=(X(0), Y(1)))

# ---------------------------------------------------------------- hats (drawn on the top of the head)
def _poly(d, pts, fill, out=(0, 0, 0), w=7): d.polygon(pts, fill=fill); d.line(pts + [pts[0]], fill=out, width=w, joint='curve')
HATS = {
    'crown':  lambda d, x, y, r, c: _poly(d, [(x - r, y), (x - r * 1.1, y - r * 1.1), (x - r * .5, y - r * .5), (x, y - r * 1.3), (x + r * .5, y - r * .5), (x + r * 1.1, y - r * 1.1), (x + r, y)], (255, 205, 60)),
    'cone':   lambda d, x, y, r, c: _poly(d, [(x - r * .9, y + r * .1), (x + r * .9, y + r * .1), (x, y - r * 1.9)], (255, 140, 40)),
    'tophat': lambda d, x, y, r, c: (d.rectangle([x - r * 1.3, y - r * .1, x + r * 1.3, y + r * .15], fill=(30, 30, 40), outline=(0, 0, 0), width=6), d.rectangle([x - r * .8, y - r * 1.6, x + r * .8, y], fill=(30, 30, 40), outline=(0, 0, 0), width=6), d.rectangle([x - r * .8, y - r * .5, x + r * .8, y - r * .2], fill=c)),
    'pot':    lambda d, x, y, r, c: (d.pieslice([x - r * 1.1, y - r * 1.2, x + r * 1.1, y + r * 1.0], 180, 360, fill=(150, 160, 175), outline=(0, 0, 0), width=6), d.line([x - r * 1.1, y - r * .1, x + r * 1.1, y - r * .1], fill=(0, 0, 0), width=6)),
    'flower': lambda d, x, y, r, c: ([d.ellipse([x + math.cos(a) * r * .55 - r * .32, y - r * .7 + math.sin(a) * r * .55 - r * .32, x + math.cos(a) * r * .55 + r * .32, y - r * .7 + math.sin(a) * r * .55 + r * .32], fill=c, outline=(0, 0, 0), width=4) for a in np.linspace(0, 6.28, 6, endpoint=False)], d.ellipse([x - r * .28, y - r * .98, x + r * .28, y - r * .42], fill=(255, 235, 90))),
    'antenna': lambda d, x, y, r, c: (d.line([x, y, x, y - r * 1.5], fill=(0, 0, 0), width=14), d.line([x, y, x, y - r * 1.5], fill=INK, width=6), d.ellipse([x - r * .3, y - r * 1.9, x + r * .3, y - r * 1.3], fill=c, outline=(0, 0, 0), width=5)),
    'halo':   lambda d, x, y, r, c: d.ellipse([x - r * 1.0, y - r * 1.2, x + r * 1.0, y - r * .55], outline=(255, 235, 120), width=11),
    'helmet': lambda d, x, y, r, c: (d.pieslice([x - r * 1.15, y - r * 1.15, x + r * 1.15, y + r * 1.0], 180, 360, fill=c, outline=(0, 0, 0), width=6), d.rectangle([x - r * .15, y - r * 1.15, x + r * .15, y - r * .1], fill=(255, 255, 255))),
    'party':  lambda d, x, y, r, c: (_poly(d, [(x - r * .6, y + r * .05), (x + r * .6, y + r * .05), (x + r * .2, y - r * 1.8)], c), d.ellipse([x + r * .05, y - r * 2.1, x + r * .45, y - r * 1.7], fill=(255, 255, 255))),
    'beanie': lambda d, x, y, r, c: (d.pieslice([x - r * 1.1, y - r * 1.1, x + r * 1.1, y + r * 1.0], 180, 360, fill=c, outline=(0, 0, 0), width=6), d.rectangle([x - r * 1.1, y - r * .25, x + r * 1.1, y + r * .1], fill=(255, 255, 255), outline=(0, 0, 0), width=5), d.ellipse([x - r * .25, y - r * 1.45, x + r * .25, y - r * .95], fill=(255, 255, 255))),
    'frog':   lambda d, x, y, r, c: ([(d.ellipse([x + s * r * .6 - r * .45, y - r * .75, x + s * r * .6 + r * .45, y + r * .15], fill=(90, 220, 110), outline=(0, 0, 0), width=5), d.ellipse([x + s * r * .6 - r * .17, y - r * .5, x + s * r * .6 + r * .17, y - r * .16], fill=(10, 10, 14))) for s in (-1, 1)]),
    'horns':  lambda d, x, y, r, c: ([_poly(d, [(x + s * r * .55, y + r * .1), (x + s * r * .95, y - r * .2), (x + s * r * 1.3, y - r * 1.4), (x + s * r * .25, y - r * .45)], (235, 70, 60)) for s in (-1, 1)]),
    'wizard': lambda d, x, y, r, c: (_poly(d, [(x - r * 1.2, y + r * .1), (x + r * 1.2, y + r * .1), (x + r * .1, y - r * 2.5)], (110, 80, 200)), d.ellipse([x - r * .15, y - r * 1.2, x + r * .25, y - r * .8], fill=(255, 235, 120))),
    'chef':   lambda d, x, y, r, c: (d.ellipse([x - r * 1.0, y - r * 1.5, x + r * 1.0, y - r * .2], fill=(250, 250, 250), outline=(0, 0, 0), width=6), d.rectangle([x - r * .75, y - r * .35, x + r * .75, y + r * .1], fill=(250, 250, 250), outline=(0, 0, 0), width=6)),
    'phones': lambda d, x, y, r, c: (d.arc([x - r * 1.25, y - r * 1.1, x + r * 1.25, y + r * 1.2], 180, 360, fill=(30, 30, 40), width=12), [d.ellipse([x + s * r * 1.12 - r * .3, y + r * .1, x + s * r * 1.12 + r * .3, y + r * .8], fill=c, outline=(0, 0, 0), width=5) for s in (-1, 1)]),
    'none':   lambda d, x, y, r, c: None,
}

# ---------------------------------------------------------------- props (held in the right hand)
def _L(d, a, b, col, w): d.line([a, b], fill=(0, 0, 0), width=w + 8); d.line([a, b], fill=col, width=w)
def _E(d, box, fill, w=6): d.ellipse(box, fill=fill, outline=(0, 0, 0), width=w)
def _R(d, box, fill, w=6): d.rectangle(box, fill=fill, outline=(0, 0, 0), width=w)
PROPS = {
    'umbrella': lambda d, x, y, s, c, i: (_L(d, (x, y + s * .8), (x, y - s * 1.6), (120, 90, 60), 12), d.pieslice([x - s * 1.9, y - s * 3.2, x + s * 1.9, y - s * .1], 180, 360, fill=c, outline=(0, 0, 0), width=6)),
    'balloon':  lambda d, x, y, s, c, i: (_L(d, (x, y), (x - s * .2, y - s * 2.4), (230, 230, 230), 5), _E(d, [x - s * 1.0 - s * .2, y - s * 4.0, x + s * .8 - s * .2, y - s * 2.1], c)),
    'sword':    lambda d, x, y, s, c, i: (_L(d, (x, y + s * .3), (x, y - s * 3.2), (210, 220, 235), 14), _L(d, (x - s * .8, y - s * .1), (x + s * .8, y - s * .1), (255, 205, 60), 12)),
    'flag':     lambda d, x, y, s, c, i: (_L(d, (x, y + s), (x, y - s * 3.2), (200, 200, 205), 9), _poly(d, [(x, y - s * 3.2), (x + s * 2.3, y - s * 2.7), (x, y - s * 1.9)], c)),
    'lantern':  lambda d, x, y, s, c, i: (_L(d, (x, y), (x, y + s * .6), (60, 60, 70), 6), _R(d, [x - s * .55, y + s * .5, x + s * .55, y + s * 1.7], (255, 215, 110)), d.ellipse([x - s * 1.3, y - s * .4, x + s * 1.3, y + s * 2.3], outline=(255, 220, 120), width=5)),
    'cup':      lambda d, x, y, s, c, i: (_poly(d, [(x - s * .7, y - s * 1.0), (x + s * .7, y - s * 1.0), (x + s * .5, y + s * .5), (x - s * .5, y + s * .5)], c), d.arc([x + s * .4, y - s * .8, x + s * 1.2, y], 270, 90, fill=(0, 0, 0), width=7)),
    'fish':     lambda d, x, y, s, c, i: (_E(d, [x - s * 1.4, y - s * 2.0, x + s * .9, y - s * .9], c), _poly(d, [(x + s * .8, y - s * 1.45), (x + s * 1.7, y - s * 2.1), (x + s * 1.7, y - s * .8)], c), d.ellipse([x - s * 1.1, y - s * 1.7, x - s * .9, y - s * 1.5], fill=(0, 0, 0))),
    'book':     lambda d, x, y, s, c, i: (_R(d, [x - s * .9, y - s * 1.8, x + s * .9, y - s * .2], c), d.line([x, y - s * 1.8, x, y - s * .2], fill=(0, 0, 0), width=5), [d.line([x - s * .7, y - s * (1.4 - k * .35), x - s * .2, y - s * (1.4 - k * .35)], fill=INK, width=4) for k in range(3)]),
    'bat':      lambda d, x, y, s, c, i: _L(d, (x, y + s * .4), (x + s * .6, y - s * 3.2), (200, 150, 90), 20),
    'trophy':   lambda d, x, y, s, c, i: (_poly(d, [(x - s * .9, y - s * 2.2), (x + s * .9, y - s * 2.2), (x + s * .5, y - s * .8), (x - s * .5, y - s * .8)], (255, 205, 60)), _R(d, [x - s * .15, y - s * .8, x + s * .15, y - s * .3], (255, 205, 60)), _R(d, [x - s * .6, y - s * .3, x + s * .6, y], (255, 205, 60))),
    'scope':    lambda d, x, y, s, c, i: (_L(d, (x, y), (x + s * 2.4, y - s * 1.6), (150, 160, 175), 22), _L(d, (x + s * 2.2, y - s * 1.5), (x + s * 2.6, y - s * 1.75), c, 28)),
    'kite':     lambda d, x, y, s, c, i: (_L(d, (x, y), (x + s * 1.1, y - s * 2.6), (230, 230, 230), 4), _poly(d, [(x + s * 1.1, y - s * 4.4), (x + s * 2.0, y - s * 3.4), (x + s * 1.1, y - s * 2.5), (x + s * .2, y - s * 3.4)], c)),
    'guitar':   lambda d, x, y, s, c, i: (_L(d, (x - s * .3, y - s * .2), (x + s * 1.5, y - s * 2.6), (140, 100, 60), 11), _E(d, [x - s * 1.2, y - s * .3, x + s * .5, y + s * 1.2], c), d.ellipse([x - s * .4, y + s * .2, x - s * .1, y + s * .5], fill=(0, 0, 0))),
    'wrench':   lambda d, x, y, s, c, i: (_L(d, (x, y + s * .4), (x + s * .6, y - s * 2.4), (170, 180, 195), 15), _E(d, [x + s * .1, y - s * 3.2, x + s * 1.1, y - s * 2.2], (170, 180, 195), 5)),
    'torch':    lambda d, x, y, s, c, i: (_L(d, (x, y + s * .3), (x, y - s * 1.6), (110, 80, 50), 14), _poly(d, [(x - s * .6, y - s * 1.5), (x + s * .6, y - s * 1.5), (x + s * .3, y - s * 3.1), (x, y - s * 2.4), (x - s * .3, y - s * 3.4)], (255, 150, 50))),
    'shield':   lambda d, x, y, s, c, i: _poly(d, [(x - s * 1.1, y - s * 2.2), (x + s * 1.1, y - s * 2.2), (x + s * 1.1, y - s * 1.0), (x, y + s * .2), (x - s * 1.1, y - s * 1.0)], c),
    'magnet':   lambda d, x, y, s, c, i: (d.arc([x - s * 1.0, y - s * 2.2, x + s * 1.0, y - s * .2], 180, 360, fill=(235, 60, 60), width=int(s * .6)), _R(d, [x - s * 1.0, y - s * 1.2, x - s * .4, y - s * .6], (240, 240, 245)), _R(d, [x + s * .4, y - s * 1.2, x + s * 1.0, y - s * .6], (240, 240, 245))),
    'ladder':   lambda d, x, y, s, c, i: ([_L(d, (x + dx * s, y + s * .8), (x + dx * s, y - s * 3.2), (200, 150, 90), 9) for dx in (-.5, .5)], [_L(d, (x - s * .5, y - s * (2.9 - k * .75)), (x + s * .5, y - s * (2.9 - k * .75)), (200, 150, 90), 7) for k in range(5)]),
    'cake':     lambda d, x, y, s, c, i: (_R(d, [x - s * 1.1, y - s * 1.2, x + s * 1.1, y], c), _R(d, [x - s * 1.1, y - s * 1.9, x + s * 1.1, y - s * 1.2], (250, 240, 230)), _L(d, (x, y - s * 1.9), (x, y - s * 2.6), (255, 220, 120), 7)),
    'plant':    lambda d, x, y, s, c, i: (_poly(d, [(x - s * .8, y - s * .9), (x + s * .8, y - s * .9), (x + s * .5, y + s * .3), (x - s * .5, y + s * .3)], (190, 110, 70)), [_E(d, [x + dx * s - s * .45, y - s * (1.9 + k * .6), x + dx * s + s * .45, y - s * (1.2 + k * .6)], (90, 210, 110), 4) for k, dx in enumerate((-.5, .5, 0))]),
    'boombox':  lambda d, x, y, s, c, i: (_R(d, [x - s * 1.4, y - s * 1.5, x + s * 1.4, y], (50, 50, 62)), [_E(d, [x + dx * s - s * .45, y - s * 1.2, x + dx * s + s * .45, y - s * .3], c, 5) for dx in (-.8, .8)], _L(d, (x - s * 1.2, y - s * 1.5), (x - s * 1.2, y - s * 2.1), (230, 230, 230), 5)),
    'oar':      lambda d, x, y, s, c, i: (_L(d, (x - s * .3, y + s * .8), (x + s * .3, y - s * 3.0), (200, 150, 90), 11), _E(d, [x + s * .0, y - s * 3.6, x + s * .9, y - s * 2.5], c, 5)),
    'anchor':   lambda d, x, y, s, c, i: (_L(d, (x, y - s * .2), (x, y - s * 2.4), (200, 205, 215), 11), d.arc([x - s * 1.1, y - s * 1.6, x + s * 1.1, y + s * .2], 0, 180, fill=(200, 205, 215), width=10), _L(d, (x - s * .6, y - s * 2.0), (x + s * .6, y - s * 2.0), (200, 205, 215), 9)),
    'key':      lambda d, x, y, s, c, i: (_E(d, [x - s * .5, y - s * 2.4, x + s * .5, y - s * 1.4], (255, 205, 60), 5), _L(d, (x, y - s * 1.4), (x, y + s * .2), (255, 205, 60), 10), _L(d, (x, y - s * .1), (x + s * .4, y - s * .1), (255, 205, 60), 8)),
    'clock':    lambda d, x, y, s, c, i: (_E(d, [x - s * 1.0, y - s * 2.3, x + s * 1.0, y - s * .3], (250, 245, 235)), _L(d, (x, y - s * 1.3), (x, y - s * 2.0), (20, 20, 25), 6), _L(d, (x, y - s * 1.3), (x + s * .5, y - s * 1.1), (20, 20, 25), 6)),
    'camera':   lambda d, x, y, s, c, i: (_R(d, [x - s * 1.1, y - s * 1.5, x + s * 1.1, y - s * .2], (60, 60, 75)), _E(d, [x - s * .55, y - s * 1.35, x + s * .55, y - s * .35], c, 6)),
    'bone':     lambda d, x, y, s, c, i: (_L(d, (x, y - s * .3), (x + s * .4, y - s * 2.6), (240, 235, 220), 13), [_E(d, [x + bx * s - s * .35, y + by * s - s * .35, x + bx * s + s * .35, y + by * s + s * .35], (240, 235, 220), 4) for bx, by in ((-.2, -.1), (.2, -.25), (.6, -2.6), (.25, -2.8))]),
    'rocket':   lambda d, x, y, s, c, i: (_poly(d, [(x - s * .45, y - s * .4), (x + s * .45, y - s * .4), (x + s * .45, y - s * 2.0), (x, y - s * 2.9), (x - s * .45, y - s * 2.0)], (240, 240, 245)), _poly(d, [(x - s * .45, y - s * 1.2), (x - s * 1.1, y - s * .2), (x - s * .45, y - s * .4)], c), _poly(d, [(x + s * .45, y - s * 1.2), (x + s * 1.1, y - s * .2), (x + s * .45, y - s * .4)], c), _poly(d, [(x - s * .25, y - s * .4), (x + s * .25, y - s * .4), (x, y + s * .5)], (255, 160, 50))),
    'brush':    lambda d, x, y, s, c, i: (_L(d, (x, y + s * .3), (x + s * .3, y - s * 2.3), (160, 120, 80), 11), _poly(d, [(x + s * .1, y - s * 2.2), (x + s * .6, y - s * 2.2), (x + s * .5, y - s * 3.1), (x + s * .15, y - s * 3.1)], c)),
    'net':      lambda d, x, y, s, c, i: (_L(d, (x, y + s * .3), (x + s * .3, y - s * 2.2), (160, 120, 80), 9), d.ellipse([x - s * .7, y - s * 3.4, x + s * 1.2, y - s * 2.0], outline=(235, 235, 240), width=7), [d.line([x - s * .5 + k * s * .45, y - s * 3.2, x - s * .5 + k * s * .45, y - s * 2.2], fill=(235, 235, 240), width=3) for k in range(4)]),
    'none':     lambda d, x, y, s, c, i: None,
}

# ---------------------------------------------------------------- backdrops
def stars(d, n, seed, ymax=H * .7, col=(235, 235, 255)):
    r = random.Random(seed)
    for _ in range(n): x, y = r.random() * W, r.random() * ymax; s = r.choice((3, 3, 4, 6)); d.ellipse([x, y, x + s, y + s], fill=col)
def mountains(d, y0, seed, col, amp=220, step=140):
    r = random.Random(seed); pts = [(0, H)]; x = -60
    while x < W + 100: pts.append((x, y0 - r.random() * amp)); x += step * (.6 + r.random() * .8)
    pts += [(W + 100, y0), (W + 100, H)]; d.polygon(pts, fill=col)
def sun(d, x, y, r, col): d.ellipse([x - r, y - r, x + r, y + r], fill=col)
def clouds(d, seed, col, ys=(.15, .3)):
    r = random.Random(seed)
    for _ in range(4):
        x, y = r.random() * W, H * (ys[0] + r.random() * (ys[1] - ys[0])); w = 140 + r.random() * 160
        for k in range(4): d.ellipse([x + k * w * .22, y - w * .13 * (1 + (k % 2)), x + k * w * .22 + w * .5, y + w * .16], fill=col)
def waves(d, y0, col, seed, amp=22, rows=6):
    r = random.Random(seed)
    for k in range(rows):
        y = y0 + k * 70; ph = r.random() * 6; pts = [(0, H)] + [(x, y + math.sin(x * .02 + ph + k) * amp * (1 + k * .12)) for x in range(0, W + 10, 10)] + [(W, H)]
        shade = tuple(int(c * (.55 + k * .09)) for c in col); d.polygon(pts, fill=shade)
def city(d, y0, seed, col, wcol):
    r = random.Random(seed); x = -20
    while x < W:
        w = 70 + r.random() * 90; h = 160 + r.random() * 420; d.rectangle([x, y0 - h, x + w, H], fill=col)
        for wy in range(int(y0 - h + 22), int(y0), 40):
            for wx in range(int(x + 12), int(x + w - 14), 28):
                if r.random() < .55: d.rectangle([wx, wy, wx + 12, wy + 18], fill=wcol)
        x += w + r.random() * 10
def dunes(d, y0, seed, cols):
    for k, c in enumerate(cols):
        ph = k * 1.7 + seed; pts = [(0, H)] + [(x, y0 + k * 90 + math.sin(x * .006 + ph) * 90 + math.sin(x * .017 + ph) * 28) for x in range(0, W + 10, 10)] + [(W, H)]; d.polygon(pts, fill=c)
def aurora(img, seed, hues):
    a = np.asarray(img).astype('float32'); yy, xx = np.mgrid[0:H, 0:W]; r = random.Random(seed)
    for k, h in enumerate(hues):
        ph = r.random() * 6; cy = H * (.2 + k * .1) + np.sin(xx * .007 + ph) * 90 + np.sin(xx * .019 + ph * 2) * 30; band = np.exp(-((yy - cy) / (55 + k * 12)) ** 2); col = np.array(hsv(h, .7, 1.0), dtype='float32')
        a += band[..., None] * col[None, None, :] * (.75 - k * .12)
    return Image.fromarray(np.clip(a, 0, 255).astype('uint8'))
def spiral(d, cx, cy, seed, col, arms=3):
    for a in range(arms):
        pts = [(cx + math.cos(t * .25 + a * 6.283 / arms) * t * 7, cy + math.sin(t * .25 + a * 6.283 / arms) * t * 3.2) for t in np.linspace(2, 60, 120)]
        d.line(pts, fill=col, width=18)
def crystals(d, y0, seed, hue):
    r = random.Random(seed)
    for _ in range(9):
        x = r.random() * W; h = 160 + r.random() * 380; w = 50 + r.random() * 70; c = hsv(hue + r.random() * 40, .55, .6 + r.random() * .4)
        d.polygon([(x - w, H), (x - w * .5, H - h * .8), (x, H - h), (x + w * .5, H - h * .75), (x + w, H)], fill=c, outline=(255, 255, 255), width=4)
def trees(d, y0, seed, col):
    r = random.Random(seed); x = -20
    while x < W + 40:
        h = 220 + r.random() * 380; w = 90 + r.random() * 60; d.polygon([(x, y0 + 40), (x + w / 2, y0 - h), (x + w, y0 + 40)], fill=col); x += w * (.5 + r.random() * .5)
def rain(d, seed, col=(170, 200, 255), n=160):
    r = random.Random(seed)
    for _ in range(n): x, y = r.random() * W, r.random() * H * .8; d.line([x, y, x - 14, y + 44], fill=col, width=4)
def snow(d, seed, n=120):
    r = random.Random(seed)
    for _ in range(n): x, y = r.random() * W, r.random() * H * .85; s = r.choice((5, 7, 9)); d.ellipse([x, y, x + s, y + s], fill=(245, 248, 255))
def lighthouse(d, x, y0, col):
    d.polygon([(x - 60, H), (x - 36, y0), (x + 36, y0), (x + 60, H)], fill=col); d.rectangle([x - 48, y0 - 70, x + 48, y0], fill=(255, 215, 110)); d.polygon([(x - 62, y0 - 70), (x + 62, y0 - 70), (x, y0 - 150)], fill=(200, 60, 60))
def bolts(d, seed, n=2):
    r = random.Random(seed)
    for _ in range(n):
        x, y = r.random() * W * .8 + 60, 0; pts = [(x, y)]
        while y < H * .55: x += (r.random() - .5) * 120; y += 60 + r.random() * 50; pts.append((x, y))
        d.line(pts, fill=(255, 255, 210), width=14)

SCENES = ['plain', 'night', 'dunes', 'sea', 'city', 'mountains', 'aurora', 'cave', 'forest', 'snow', 'storm', 'sunset', 'lighthouse', 'nebula', 'volcano', 'canyon']

def backdrop(scene, seed, hue):
    r = random.Random(seed); P = lambda s=.5, v=.5, o=0: hsv(hue + o, s, v)
    if scene == 'plain':
        img = gradient(P(.5, .5), P(.6, .12), glow=(W / 2, H * .45, 620, P(.5, .8))); d = ImageDraw.Draw(img); d.rectangle([0, H * .84, W, H], fill=P(.4, .16))
    elif scene == 'night':
        img = gradient(P(.6, .28), P(.7, .06)); d = ImageDraw.Draw(img); stars(d, 90, seed); sun(d, W * (.25 + r.random() * .5), H * .2, 86, (245, 245, 230)); mountains(d, H * .8, seed, P(.5, .1), 170)
    elif scene == 'dunes':
        img = gradient(P(.5, .95, 15), P(.6, .7, -10), glow=(W * .7, H * .3, 480, (255, 240, 190))); d = ImageDraw.Draw(img); sun(d, W * .7, H * .27, 100, (255, 245, 210)); dunes(d, H * .6, seed, [P(.6, .75, 5), P(.65, .6, 0), P(.7, .42, -8)])
    elif scene == 'sea':
        img = gradient(P(.5, .55), P(.55, .2)); d = ImageDraw.Draw(img); clouds(d, seed, P(.3, .7)); sun(d, W * .3, H * .22, 78, (250, 245, 220)); waves(d, H * .55, hsv(hue + 10, .7, .85), seed)
    elif scene == 'city':
        img = gradient(P(.6, .3, 20), P(.6, .1), glow=(W / 2, H * .72, 520, P(.6, .6, 20))); d = ImageDraw.Draw(img); stars(d, 40, seed, H * .4); city(d, H * .93, seed, (10, 10, 20), (255, 215, 120))
    elif scene == 'mountains':
        img = gradient(P(.45, .8, 10), P(.4, .55, -10)); d = ImageDraw.Draw(img); sun(d, W * .5, H * .3, 120, (255, 245, 215)); mountains(d, H * .62, seed, P(.35, .55), 300, 200); mountains(d, H * .8, seed + 1, P(.4, .3), 240, 160)
    elif scene == 'aurora':
        img = gradient((6, 10, 28), (4, 6, 14)); d = ImageDraw.Draw(img); stars(d, 110, seed); img = aurora(img, seed, [hue, hue + 50, hue + 100]); d = ImageDraw.Draw(img); mountains(d, H * .84, seed, (6, 10, 18), 200)
    elif scene == 'cave':
        img = gradient(P(.5, .14), P(.55, .04), glow=(W / 2, H * .6, 520, P(.6, .5))); d = ImageDraw.Draw(img); crystals(d, H, seed, hue)
    elif scene == 'forest':
        img = gradient(P(.5, .3, 40), P(.6, .08, 40)); d = ImageDraw.Draw(img); sun(d, W * .75, H * .2, 70, (240, 255, 210)); trees(d, H * .9, seed, P(.5, .16, 40)); trees(d, H * .98, seed + 3, P(.55, .08, 40))
        for _ in range(40): x, y = r.random() * W, H * (.35 + r.random() * .55); d.ellipse([x, y, x + 8, y + 8], fill=(255, 255, 140))
    elif scene == 'snow':
        img = gradient(P(.2, .85, 10), P(.15, .6, 10)); d = ImageDraw.Draw(img); mountains(d, H * .75, seed, (225, 235, 250), 280, 220); d.rectangle([0, H * .84, W, H], fill=(240, 246, 255)); snow(d, seed)
    elif scene == 'storm':
        img = gradient(P(.45, .22), P(.5, .08)); d = ImageDraw.Draw(img); clouds(d, seed, P(.25, .38), (.05, .35)); bolts(d, seed); rain(d, seed); waves(d, H * .72, hsv(hue + 10, .6, .5), seed, 30, 4)
    elif scene == 'sunset':
        img = gradient(hsv(hue + 330, .75, .95), hsv(hue + 270, .6, .3), glow=(W / 2, H * .62, 520, (255, 210, 120))); d = ImageDraw.Draw(img); sun(d, W / 2, H * .6, 130, (255, 235, 170)); waves(d, H * .66, hsv(hue + 300, .6, .5), seed, 14, 5)
    elif scene == 'lighthouse':
        img = gradient(P(.55, .3), P(.6, .1)); d = ImageDraw.Draw(img); stars(d, 60, seed, H * .5); waves(d, H * .78, hsv(hue + 10, .6, .4), seed, 16, 3); lighthouse(d, W * .76, H * .5, (225, 225, 230))
    elif scene == 'nebula':
        img = gradient((8, 4, 22), (3, 2, 10), glow=(W * .35, H * .38, 540, hsv(hue, .8, .7))); a = np.asarray(img).astype('float32'); yy, xx = np.mgrid[0:H, 0:W]
        for k in range(3): a += (np.exp(-(((xx - W * (.2 + .3 * k)) / 300) ** 2 + ((yy - H * (.3 + .12 * k)) / 200) ** 2))[..., None] * np.array(hsv(hue + 70 * k, .8, .9), dtype='float32') * .6)
        img = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(img); stars(d, 160, seed, H); d.rectangle([0, H * .86, W, H], fill=(4, 3, 10))
    elif scene == 'volcano':
        img = gradient(P(.7, .3, 340), P(.75, .08, 340), glow=(W / 2, H * .45, 520, (255, 130, 40))); d = ImageDraw.Draw(img); d.polygon([(W * .1, H), (W * .42, H * .42), (W * .58, H * .42), (W * .9, H)], fill=(24, 14, 16)); d.polygon([(W * .42, H * .42), (W * .5, H * .38), (W * .58, H * .42)], fill=(255, 120, 30))
        for _ in range(26): x, y = W * (.38 + r.random() * .24), H * (.1 + r.random() * .3); d.ellipse([x, y, x + 12, y + 12], fill=(255, 160, 60))
    else:                                                                                           # canyon
        img = gradient(P(.5, .9, 20), P(.6, .65, 0)); d = ImageDraw.Draw(img); sun(d, W * .5, H * .22, 90, (255, 245, 215)); mountains(d, H * .66, seed, P(.7, .5, -10), 200, 150); mountains(d, H * .84, seed + 2, P(.75, .3, -15), 180, 120)
    return img

def card(spec):
    """spec: pose, hat, prop, scene, hue, seed, size (figure height, 0..1), x (figure position, -.2..+.2)"""
    seed = spec.get('seed', 1); hue = spec.get('hue', 200); img = backdrop(spec.get('scene', 'plain'), seed, hue); d = ImageDraw.Draw(img)
    pcol = hsv(hue + spec.get('pshift', 160), .75, 1.0); fh = H * spec.get('size', .5); cx = W / 2 + spec.get('x', 0) * W; top = H * .8 - fh + H * spec.get('lift', 0)
    figure(d, spec.get('pose', 'stand'), cx, top, fh, lw=int(fh * .052), hat=spec.get('hat'), prop=spec.get('prop'), pcol=pcol)
    return blur_glow(img, 26, .22)

if __name__ == '__main__':
    import sys
    out = Image.new('RGB', (W * 4 // 3, H // 3 * 2)); specs = [dict(pose='wave', hat='crown', prop='umbrella', scene='dunes', hue=30), dict(pose='cheer', hat='party', prop='balloon', scene='night', hue=260), dict(pose='run', hat='helmet', prop='flag', scene='sunset', hue=20), dict(pose='flex', hat='horns', prop='sword', scene='volcano', hue=0)]
    for i, s in enumerate(specs): out.paste(card(s).resize((W // 3, H // 3)), (i * W // 3, 0))
    out.save('/tmp/stick_test.png'); print('ok')
