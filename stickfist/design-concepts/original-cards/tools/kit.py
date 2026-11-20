"""STIXX drawing kit: original stickman action art, drawn as tapered ink shapes (no film frames, no AI).
Everything is supersampled 2x. A canvas keeps the colour image plus a mask of the "foreground" objects,
so they can later be laid over the card name (frame-breaking)."""
import math, random
import numpy as np, cv2

SS = 2
W, H = 1500 * SS, 2100 * SS
BG = (212, 216, 215)                      # BGR flat paper grey
BLACK, DARK, MID, LIGHT = (8, 8, 10), (62, 62, 66), (112, 112, 116), (170, 172, 172)
RED = (24, 16, 198)                       # BGR blood red


class Canvas:
    def __init__(self, angle=0.0, scale=1.0, center=(750, 1050), shift=(0, 0)):
        """a camera: compose in local coordinates, then rotate (degrees, negative = counter-clockwise) and scale about a point"""
        self.img = np.empty((H, W, 3), np.uint8); self.img[:] = BG
        self.fg = np.zeros((H, W), np.uint8)
        a = math.radians(angle); self.ca, self.sa, self.k, self.cx, self.cy, self.sh = math.cos(a), math.sin(a), scale, center, center, shift
        self.cx, self.cy = center

    def T(self, p):
        x, y = (p[0] - self.cx) * self.k, (p[1] - self.cy) * self.k
        return (self.cx + x * self.ca - y * self.sa + self.sh[0], self.cy + x * self.sa + y * self.ca + self.sh[1])

    def poly(self, pts, color, fg=False):
        pts = [self.T(q) for q in pts]
        p = np.round(np.array(pts, np.float64) * SS).astype(np.int32)
        cv2.fillPoly(self.img, [p], color, cv2.LINE_AA)
        if fg: cv2.fillPoly(self.fg, [p], 255, cv2.LINE_AA)

    def disc(self, c, r, color, fg=False):
        c = self.T(c); r = r * self.k
        cv2.circle(self.img, (int(round(c[0] * SS)), int(round(c[1] * SS))), int(round(r * SS)), color, -1, cv2.LINE_AA)
        if fg: cv2.circle(self.fg, (int(round(c[0] * SS)), int(round(c[1] * SS))), int(round(r * SS)), 255, -1, cv2.LINE_AA)


def catmull(pts, per=18):
    P = [np.array(p, float) for p in pts]
    if len(P) < 3:
        return [P[0] + (P[-1] - P[0]) * t / per for t in range(per + 1)]
    Q = [P[0]] + P + [P[-1]]; out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1]); return out


def ribbon(c, path, widths, color, fg=False, caps=(False, False)):
    """filled shape along a path with a width at every point"""
    L, R = [], []
    n = len(path)
    if len(widths) != n:                                  # a short list of widths is spread evenly along the path
        widths = list(np.interp(np.linspace(0, len(widths) - 1, n), np.arange(len(widths)), widths))
    for i, p in enumerate(path):
        a, b = path[max(0, i - 1)], path[min(n - 1, i + 1)]
        t = np.array(b) - np.array(a); l = np.hypot(*t) or 1; nx, ny = -t[1] / l, t[0] / l
        L.append((p[0] + nx * widths[i] / 2, p[1] + ny * widths[i] / 2)); R.append((p[0] - nx * widths[i] / 2, p[1] - ny * widths[i] / 2))
    c.poly(L + R[::-1], color, fg)
    if caps[0]: c.disc(path[0], widths[0] / 2, color, fg)
    if caps[1]: c.disc(path[-1], widths[-1] / 2, color, fg)


def limb(c, pts, w0, w1, color, fg=False, bulge=0.12):
    path = catmull(pts, 14); n = len(path)
    ws = [(w0 + (w1 - w0) * i / (n - 1)) * (1 + bulge * math.sin(math.pi * i / (n - 1))) for i in range(n)]
    ribbon(c, path, ws, color, fg, caps=(True, True))


def stick(c, J, w, color, head_r=None, fg=False, ghost=False):
    hr = head_r or w * 2.15
    s = 0.62 if ghost else 1.0
    limb(c, [J['hip'], J['chest'], J['neck']], w * 1.22 * s, w * 1.0 * s, color, fg)
    for side in ('a', 'b'):
        limb(c, [J['hip'], J['knee_' + side], J['foot_' + side]], w * 1.0 * s, w * 0.62 * s, color, fg)
        limb(c, [J['neck'], J['elb_' + side], J['hand_' + side]], w * 0.84 * s, w * 0.56 * s, color, fg)
    # the head sits slightly past the neck along the body axis
    ax = np.array(J['neck']) - np.array(J['chest']); ax = ax / (np.hypot(*ax) or 1)
    hc = np.array(J['neck']) + ax * hr * 0.92
    c.disc(hc, hr * s, color, fg)
    return tuple(hc)


def blade(c, hand, tip, w, color, fg=False, edge=None):
    """a dagger or sword: a tapered kite from the hand to the tip"""
    h, t = np.array(hand, float), np.array(tip, float); d = t - h; l = np.hypot(*d); u = d / l; n = np.array([-u[1], u[0]])
    c.poly([h - u * w * 1.6 + n * w * 0.5, h + n * w * 0.9, h + u * l * 0.7 + n * w * 0.75, t, h + u * l * 0.7 - n * w * 0.5, h - n * w * 0.9, h - u * w * 1.6 - n * w * 0.5], color, fg)
    if edge: ribbon(c, [h + u * l * 0.12, t - u * l * 0.04], [w * 0.28, w * 0.04], edge, fg)
    # guard
    ribbon(c, [h + u * w * 0.2 - n * w * 2.2, h + u * w * 0.2 + n * w * 2.2], [w * 0.7, w * 0.7], BLACK, fg, caps=(True, True))


def crescent(c, pts, wmax, color, fg=False, peak=0.42, ragged=0.0, seed=0):
    path = catmull(pts, 22); n = len(path); rnd = random.Random(seed)
    ws = []
    for i in range(n):
        t = i / (n - 1)
        prof = (t / peak) ** 0.85 if t < peak else ((1 - t) / (1 - peak)) ** 1.35
        ws.append(max(1.5, wmax * prof * (1 + ragged * (rnd.random() - .5))))
    ribbon(c, path, ws, color, fg)


def splatter(c, origin, direction, n, size, color, spread=0.7, reach=520, seed=0, fg=False):
    rnd = random.Random(seed); d = np.array(direction, float); d /= np.hypot(*d)
    for i in range(n):
        ang = math.atan2(d[1], d[0]) + rnd.gauss(0, spread)
        dist = reach * rnd.random() ** 1.6
        p = np.array(origin) + np.array([math.cos(ang), math.sin(ang)]) * dist
        r = size * (1.1 - dist / reach) * (0.35 + rnd.random())
        if rnd.random() < 0.45 and r > 4:
            u = np.array([math.cos(ang), math.sin(ang)]); L = r * rnd.uniform(3, 8)
            ribbon(c, [p - u * L * 0.1, p + u * L], [r * 1.6, r * 0.2], color, fg)
        c.disc(p, max(1.5, r), color, fg)


def shards(c, center, n, size, color, reach=600, seed=0, fg=False, bias=None):
    rnd = random.Random(seed)
    for _ in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        if bias is not None: a = bias + rnd.gauss(0, 0.9)
        d = reach * rnd.random() ** 0.8; p = np.array(center) + np.array([math.cos(a), math.sin(a)]) * d
        s = size * rnd.uniform(0.4, 1.3); r0 = rnd.uniform(0, 6.28)
        pts = [p + np.array([math.cos(r0 + k * 2.1 + rnd.uniform(-.5, .5)), math.sin(r0 + k * 2.1 + rnd.uniform(-.5, .5))]) * s * rnd.uniform(.5, 1.5) for k in range(3)]
        c.poly(pts, color, fg)


def ghost(c, J, w, offsets, shades, fg=False):
    """afterimages: the same pose, earlier along the motion, fading into the paper"""
    for off, col in zip(offsets, shades):
        K = {k: (v[0] + off[0], v[1] + off[1]) for k, v in J.items()}
        stick(c, K, w, col, fg=fg, ghost=True)


def lines(c, focus, n, r0, r1, wmax, color, seed=0, arc=(0, 2 * math.pi), keep=None):
    """focus lines converging on a point"""
    rnd = random.Random(seed)
    for _ in range(n):
        a = rnd.uniform(*arc)
        if keep and not keep(a): continue
        ra, rb = rnd.uniform(r0, r0 * 1.8), rnd.uniform(r1 * 0.6, r1)
        p0 = np.array(focus) + np.array([math.cos(a), math.sin(a)]) * ra
        p1 = np.array(focus) + np.array([math.cos(a), math.sin(a)]) * rb
        ribbon(c, [p0, (p0 + p1) / 2, p1], [wmax * 0.15, wmax * rnd.uniform(.5, 1), 1.5], color)


def save(c, path):
    cv2.imwrite(path, cv2.resize(c.img, (W // SS, H // SS), interpolation=cv2.INTER_AREA))


def save_mask(c, path):
    cv2.imwrite(path, cv2.resize(c.fg, (W // SS, H // SS), interpolation=cv2.INTER_AREA))
