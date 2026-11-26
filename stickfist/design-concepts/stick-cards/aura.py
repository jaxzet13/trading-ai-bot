"""Dark, grainy, aura-lit card art made in code, in the look written down in ../STYLE.md: black ground, a figure or a shape carved out of it by one big light,
visible grain, one or two colours. Mostly silhouettes against light, because that is what survives being turned into characters.

    from aura import card;  card(dict(fig='angel', comp='eclipse', pal='bone', seed=3, power=.8)).save('x.png')
"""
import math, random
import numpy as np, cv2
from PIL import Image, ImageDraw

W, H = 900, 1092
YY, XX = np.mgrid[0:H, 0:W].astype('float32')

PALS = {   # a ramp from black to white through the colour: (position, rgb)
    'bone':    [(0, (2, 2, 3)), (.35, (60, 56, 50)), (.7, (190, 182, 165)), (1, (250, 246, 232))],
    'blue':    [(0, (0, 0, 6)), (.3, (6, 14, 60)), (.62, (40, 90, 200)), (.85, (170, 205, 255)), (1, (250, 252, 255))],
    'amber':   [(0, (4, 2, 0)), (.3, (60, 22, 4)), (.6, (200, 100, 20)), (.85, (255, 200, 100)), (1, (255, 246, 215))],
    'crimson': [(0, (5, 0, 2)), (.3, (70, 6, 14)), (.62, (200, 30, 40)), (.85, (255, 140, 120)), (1, (255, 240, 230))],
    'violet':  [(0, (3, 0, 8)), (.3, (38, 10, 80)), (.62, (130, 70, 220)), (.85, (210, 170, 255)), (1, (248, 240, 255))],
    'teal':    [(0, (0, 4, 5)), (.3, (4, 44, 52)), (.62, (30, 170, 170)), (.85, (150, 240, 225)), (1, (240, 255, 250))],
    'green':   [(0, (0, 4, 1)), (.3, (6, 50, 22)), (.62, (50, 190, 90)), (.85, (170, 250, 170)), (1, (245, 255, 240))],
    'magenta': [(0, (6, 0, 6)), (.3, (70, 6, 60)), (.62, (210, 50, 170)), (.85, (255, 160, 225)), (1, (255, 240, 250))],
    'ice':     [(0, (1, 3, 8)), (.3, (14, 34, 66)), (.62, (110, 160, 205)), (.85, (205, 230, 250)), (1, (252, 254, 255))],
    'rust':    [(0, (4, 1, 0)), (.3, (50, 14, 6)), (.62, (150, 60, 24)), (.85, (225, 160, 110)), (1, (252, 236, 214))],
}
def ramp(l, stops):
    out = np.zeros(l.shape + (3,), 'float32')
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        m = (l >= p0) & (l <= p1); t = ((l - p0) / max(1e-6, p1 - p0))[..., None]; out = np.where(m[..., None], np.array(c0, 'float32') * (1 - t) + np.array(c1, 'float32') * t, out)
    return out

def noise(seed, scale, octaves=4):
    r = np.random.default_rng(seed); out = np.zeros((H, W), 'float32'); amp = 1; tot = 0
    for o in range(octaves):
        n = max(2, int(scale * 2 ** o)); g = r.random((n * H // W + 2, n + 2)).astype('float32'); out += amp * cv2.resize(g, (W, H), interpolation=cv2.INTER_CUBIC); tot += amp; amp *= .5
    out /= tot; return (out - out.min()) / (out.max() - out.min() + 1e-6)
def glow(cx, cy, r, power=1.8): return np.clip(1 - np.hypot(XX - cx, (YY - cy)) / r, 0, 1) ** power
def disc(cx, cy, r, soft=3): return np.clip((r - np.hypot(XX - cx, YY - cy)) / soft + .5, 0, 1)
def ring(cx, cy, r, w): return np.exp(-((np.hypot(XX - cx, YY - cy) - r) / w) ** 2)
def rays(cx, cy, n, seed, sharp=3.0, spin=0.0):
    r = random.Random(seed); ph = r.random() * 6.28; a = np.arctan2(YY - cy, XX - cx) + spin; m = (np.cos(a * n + ph) * .5 + .5) ** sharp
    m2 = (np.cos(a * (n * 2 + 1) + ph * 2) * .5 + .5) ** (sharp * 1.5); return np.clip(m * .75 + m2 * .4, 0, 1)

# ---------------------------------------------------------------- silhouettes (drawn in black on a mask; 255 = figure)
def P(d, pts): d.polygon(pts, fill=255)
def robed(d, cx, by, h, hood=True, staff=False):
    P(d, [(cx - h * .26, by), (cx - h * .14, by - h * .62), (cx - h * .09, by - h * .78), (cx + h * .09, by - h * .78), (cx + h * .14, by - h * .62), (cx + h * .26, by)])
    d.ellipse([cx - h * .09, by - h * .9, cx + h * .09, by - h * .72], fill=255)
    if hood: P(d, [(cx - h * .1, by - h * .74), (cx, by - h * .98), (cx + h * .1, by - h * .74)])
    if staff: d.line([cx + h * .3, by, cx + h * .26, by - h * 1.05], fill=255, width=max(4, int(h * .022)))
def wings(d, cx, y, h, span=1.0, up=.35, n=7):
    for s in (-1, 1):
        for k in range(n):
            t = k / (n - 1); ang = math.radians(-20 - 80 * t * up * 2.4 + 30); L = h * (.9 - t * .35) * span; x0, y0 = cx + s * h * .05, y + k * h * .02
            x1, y1 = x0 + s * math.cos(ang) * L, y0 + math.sin(ang) * L; nx, ny = -math.sin(ang) * h * .06 * s, math.cos(ang) * h * .06 * s
            P(d, [(x0, y0), (x0 + (x1 - x0) * .5 + nx, y0 + (y1 - y0) * .5 + ny), (x1, y1), (x0 + (x1 - x0) * .5 - nx * .6, y0 + (y1 - y0) * .5 - ny * .6)])
def angel(d, cx, by, h):
    robed(d, cx, by, h * .8, hood=False); wings(d, cx, by - h * .65, h, 1.0, .35); d.line([cx + h * .22, by - h * .1, cx + h * .34, by - h * .78], fill=255, width=max(4, int(h * .02)))
def knight(d, cx, by, h, kneel=False):
    by2 = by + (h * .12 if kneel else 0); P(d, [(cx - h * .16, by2), (cx - h * .13, by2 - h * .5), (cx + h * .13, by2 - h * .5), (cx + h * .17, by2)])
    d.rectangle([cx - h * .14, by2 - h * .58, cx + h * .14, by2 - h * .48], fill=255); d.ellipse([cx - h * .1, by2 - h * .78, cx + h * .1, by2 - h * .56], fill=255); P(d, [(cx - h * .01, by2 - h * .76), (cx + h * .07, by2 - h * .94), (cx + h * .14, by2 - h * .7)])
    d.line([cx + h * .26, by + h * .02, cx + h * .26, by - h * .72], fill=255, width=max(5, int(h * .028))); d.line([cx + h * .17, by - h * .26, cx + h * .35, by - h * .26], fill=255, width=max(5, int(h * .03)))
def horned(d, cx, by, h):
    robed(d, cx, by, h, hood=False)
    for s in (-1, 1): P(d, [(cx + s * h * .05, by - h * .88), (cx + s * h * .18, by - h * .96), (cx + s * h * .26, by - h * 1.14), (cx + s * h * .12, by - h * 1.0), (cx + s * h * .02, by - h * .93)])
def crowned(d, cx, by, h):
    robed(d, cx, by, h, hood=False); y = by - h * .9; P(d, [(cx - h * .1, y), (cx - h * .12, y - h * .12), (cx - h * .05, y - h * .06), (cx, y - h * .15), (cx + h * .05, y - h * .06), (cx + h * .12, y - h * .12), (cx + h * .1, y)])
def lone(d, cx, by, h):                                                                          # a tiny figure, as in the references: scale is the point
    d.ellipse([cx - h * .04, by - h * .2, cx + h * .04, by - h * .12], fill=255); d.line([cx, by - h * .12, cx, by - h * .03], fill=255, width=max(3, int(h * .02))); d.line([cx, by - h * .03, cx - h * .035, by], fill=255, width=max(3, int(h * .018))); d.line([cx, by - h * .03, cx + h * .035, by], fill=255, width=max(3, int(h * .018)))
def idol(d, cx, by, h):                                                                          # a huge seated statue: block shoulders, a blank head
    P(d, [(cx - h * .42, by), (cx - h * .36, by - h * .5), (cx - h * .2, by - h * .6), (cx + h * .2, by - h * .6), (cx + h * .36, by - h * .5), (cx + h * .42, by)]); d.ellipse([cx - h * .13, by - h * .86, cx + h * .13, by - h * .56], fill=255)
def monk(d, cx, by, h):
    robed(d, cx, by, h, True, staff=True)
def twin(d, cx, by, h): robed(d, cx - h * .22, by, h * .85); robed(d, cx + h * .22, by, h * .7)
def gate(d, cx, by, h):
    d.rectangle([cx - h * .36, by - h * .95, cx + h * .36, by], fill=255); d.rectangle([cx - h * .22, by - h * .78, cx + h * .22, by], fill=0); d.pieslice([cx - h * .22, by - h * .96, cx + h * .22, by - h * .6], 180, 360, fill=0)
def tower(d, cx, by, h): P(d, [(cx - h * .1, by), (cx - h * .07, by - h * .9), (cx - h * .12, by - h * .94), (cx, by - h * 1.2), (cx + h * .12, by - h * .94), (cx + h * .07, by - h * .9), (cx + h * .1, by)])
def spire(d, cx, by, h): [P(d, [(cx + o * h - h * .05, by), (cx + o * h, by - h * k), (cx + o * h + h * .05, by)]) for o, k in ((-.22, .55), (-.08, .95), (.1, .8), (.24, .5))]
def orb(d, cx, by, h): pass
def mourner(d, cx, by, h):
    robed(d, cx, by, h, True); P(d, [(cx + h * .12, by - h * .6), (cx + h * .38, by - h * .45), (cx + h * .3, by - h * .38), (cx + h * .1, by - h * .5)])
FIGS = dict(robed=robed, angel=angel, knight=knight, horned=horned, crowned=crowned, lone=lone, idol=idol, monk=monk, twin=twin, gate=gate, tower=tower, spire=spire, orb=orb, mourner=mourner)

# ---------------------------------------------------------------- the card
def card(spec):
    seed = spec.get('seed', 1); rr = random.Random(seed); power = spec.get('power', .5); comp = spec.get('comp', 'eclipse'); fig = spec.get('fig', 'robed'); pal = PALS[spec.get('pal', 'bone')]
    cx = W * (.5 + spec.get('dx', 0)); by = H * spec.get('ground', .86); fh = H * spec.get('size', .34 + .2 * power) * (.45 if fig in ('lone',) else 1)
    cy = H * spec.get('ay', .4); R = W * (.22 + .2 * power)
    L = np.zeros((H, W), 'float32'); bgn = noise(seed, 3, 5)
    if comp == 'eclipse':
        L += glow(cx, cy, R * 3.4, 2.2) * .55 + ring(cx, cy, R * 1.03, R * .06) * 1.3 + ring(cx, cy, R * 1.25, R * .22) * .55 + rays(cx, cy, 9 + int(power * 10), seed, 4) * glow(cx, cy, R * 4, 1.2) * .5
        L *= 1 - disc(cx, cy, R, 4) * .98
    elif comp == 'moon':
        L += glow(cx, cy, R * 3.2, 2.0) * .6 + disc(cx, cy, R, 5) * 1.0; L += (noise(seed + 1, 8) - .5) * .18 * disc(cx, cy, R, 5)
    elif comp == 'rift':
        w = 20 + 36 * power; L += np.exp(-((XX - cx) / w) ** 2) * np.exp(-((YY - cy) / (H * .55)) ** 2) * 1.4 + np.exp(-((XX - cx) / (w * 6)) ** 2) * .35 * glow(cx, cy, H * .8, 1.2) + rays(cx, cy, 6, seed, 5) * glow(cx, cy, H * .9, 1.0) * .35
    elif comp == 'rings':
        for k in range(3 + int(power * 4)): L += ring(cx, cy, R * (.55 + k * .42), 5 + k * 1.5) * (.9 - k * .1)
        L += glow(cx, cy, R * 1.6, 1.4) * .9; L *= 1 - disc(cx, cy, R * .38, 3) * .96
    elif comp == 'halo':
        L += ring(cx, by - fh * 1.0, fh * .34, 10) * 1.5 + glow(cx, by - fh * .85, R * 3.0, 2.0) * .7 + rays(cx, by - fh * .85, 8, seed, 5) * glow(cx, by - fh * .85, H, 1.3) * .35
    elif comp == 'sunburst':
        L += glow(cx, by - fh * .55, R * 3.8, 1.6) * .9 + rays(cx, by - fh * .55, 11 + int(power * 9), seed, 3.5) * glow(cx, by - fh * .55, H * 1.1, 1.0) * .8 + disc(cx, by - fh * .55, R * .45, 6) * .7
    elif comp == 'storm':
        c = noise(seed + 4, 4, 5); L += np.clip(c * 1.5 - .5, 0, 1) * (1 - YY / H) * .7 + glow(cx, H * .22, R * 3, 1.8) * .9
        for _ in range(2 + int(power * 3)):
            x, y = rr.random() * W, 0.0
            while y < H * .6: nx = x + (rr.random() - .5) * 90; ny = y + 40 + rr.random() * 40; cv2.line(L, (int(x), int(y)), (int(nx), int(ny)), 1.2, 5); x, y = nx, ny
    else:                                                                                       # 'void': a dim light in a very large dark, grain doing the work
        L += glow(cx, cy, R * 3.0, 2.6) * .5 + noise(seed + 9, 6, 5) * .22 * glow(cx, cy, R * 4, 1.0)
    # fog, low and cold
    fog = noise(seed + 3, 3, 4); L += (fog * (YY / H) ** 2.0 * (.35 + .4 * power)) * np.clip(1 - np.abs(XX - cx) / (W * .6), 0, 1)
    L += (bgn - .5) * .12 * (1 - YY / H * .3)
    # stars / specks
    for _ in range(int(40 + 150 * power if spec.get('stars', True) else 0)):
        x, y = int(rr.random() * W), int(rr.random() * H * .8); L[max(0, y - 1):y + 2, max(0, x - 1):x + 2] += rr.random() * .7 * (1 - L[y, x])
    # the ground, and the figure against the light
    ground = np.zeros((H, W), 'float32'); gy = by - 4 + noise(seed + 5, 6, 3) * 40; ground[YY > gy] = 1
    mask = Image.new('L', (W, H), 0); d = ImageDraw.Draw(mask); FIGS[fig](d, cx, by, fh)
    m = np.asarray(mask, 'float32') / 255; m = cv2.GaussianBlur(m, (0, 0), 1.2)
    rim = np.clip(cv2.GaussianBlur(m, (0, 0), 7) - m, 0, 1) * .5                                  # a thin edge of light, nothing more
    L = L * (1 - m) * (1 - ground * .93) + rim * (1 - ground) * L.max() * .25 + ground * fog * .05
    L = np.clip(L, 0, None); L = L / max(1e-3, np.percentile(L, 99.6)); L = np.clip(L, 0, 1) ** (spec.get('gamma', 1.15))
    # vignette, then the print: coarse speckle where it is grey, so it reads as found, not rendered
    vg = 1 - .65 * (((XX / W - .5) / .5) ** 2 + ((YY / H - .5) / .5) ** 2); L *= np.clip(vg, 0, 1)
    gr = np.random.default_rng(seed).random((H // 3 + 1, W // 3 + 1)).astype('float32'); gr = cv2.resize(gr, (W, H), interpolation=cv2.INTER_NEAREST)
    mode = spec.get('grain', 'film')
    if mode == 'speckle': L = np.clip((L - gr * .55) / .22 + .5, 0, 1) * (.65 + .35 * L)
    else: L = np.clip(L + (gr - .5) * .14 * (.3 + L), 0, 1)
    img = ramp(np.clip(L, 0, 1), pal)
    if spec.get('chroma'): img[..., 0] = np.roll(img[..., 0], 6, 1); img[..., 2] = np.roll(img[..., 2], -6, 1)
    return Image.fromarray(np.clip(img, 0, 255).astype('uint8'))

if __name__ == '__main__':
    specs = [dict(fig='angel', comp='eclipse', pal='bone', seed=3, power=.9), dict(fig='lone', comp='rift', pal='blue', seed=5, power=.7, grain='speckle'), dict(fig='knight', comp='sunburst', pal='ice', seed=8, power=.8), dict(fig='robed', comp='moon', pal='green', seed=11, power=.5),
             dict(fig='horned', comp='storm', pal='crimson', seed=2, power=.8), dict(fig='crowned', comp='halo', pal='amber', seed=4, power=.9), dict(fig='idol', comp='rings', pal='violet', seed=6, power=.7), dict(fig='gate', comp='void', pal='teal', seed=9, power=.6)]
    out = Image.new('RGB', (300 * len(specs), 364))
    for i, s in enumerate(specs): out.paste(card(s).resize((300, 364)), (i * 300, 0))
    out.save('/tmp/aura_test.png'); print('ok')
