"""Render the cards as physical objects (table row, fanned hand, pack stack seen from the side)
so the rarity tells show: cut corners, painted edges, double thickness."""
import os, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
D = os.path.dirname(os.path.abspath(__file__)); O = os.path.join(D, 'out')
DEL = os.path.join(os.path.dirname(D), 'rarity-tells'); os.makedirs(DEL, exist_ok=True)
CW, CH = 63.0, 88.0                     # card mm
PW, PH = 1500, 2100                     # face px
WHITE, RED, GOLD = (232, 228, 220), (184, 26, 34), (206, 164, 76)
TIERS = {   # face, cut corners (front view), edge colour, thickness mm
    'T0': ('card_M_T0.png', [], WHITE, .6),
    'T1': ('card_M_T1.png', ['tr'], WHITE, .6),
    'T2': ('card_M_T2.png', ['tr'], RED, .6),
    'T3': ('card_M_T3.png', ['tr', 'bl'], GOLD, 1.25),
}
CUT, RAD = 8.0, 3.2                      # mm


def card_mask(cuts, w=PW, h=PH, back=False):
    if back:  # the back is the front mirrored left-right
        cuts = [{'tr': 'tl', 'tl': 'tr', 'br': 'bl', 'bl': 'br'}[c] for c in cuts]
    m = np.full((h, w), 255, np.uint8)
    r = int(RAD / CW * w); c = int(CUT / CW * w)
    corners = {'tl': (0, 0, 1, 1), 'tr': (w, 0, -1, 1), 'bl': (0, h, 1, -1), 'br': (w, h, -1, -1)}
    for k, (x, y, sx, sy) in corners.items():
        if k in cuts:
            cv2.fillPoly(m, [np.int32([(x, y), (x + sx * c, y), (x, y + sy * c)])], 0, cv2.LINE_AA)
        else:
            cv2.rectangle(m, (x, y), (x + sx * r, y + sy * r), 0, -1)
            cv2.circle(m, (x + sx * r, y + sy * r), r, 255, -1, cv2.LINE_AA)
    return m.astype(np.float32) / 255


class Cam:
    def __init__(self, el, dist, f, W, H, look=(0, 0, 0), az=0):
        self.W, self.H, self.f = W, H, f
        e, a = np.deg2rad(el), np.deg2rad(az)
        self.C = np.array(look) + dist * np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])
        fw = np.array(look) - self.C; fw /= np.linalg.norm(fw)
        rt = np.cross(fw, [0, 0, 1]); rt /= np.linalg.norm(rt)
        self.fw, self.rt, self.up = fw, rt, np.cross(rt, fw)

    def p(self, P):
        d = np.asarray(P, float) - self.C
        x, y, z = d @ self.rt, d @ self.up, d @ self.fw
        return (self.W / 2 + self.f * x / z, self.H / 2 - self.f * y / z)


def corners_world(cx, cy, ang, z, pivot=None):
    a = np.deg2rad(ang)
    out = []
    for u, v in ((-CW / 2, CH / 2), (CW / 2, CH / 2), (CW / 2, -CH / 2), (-CW / 2, -CH / 2)):
        if pivot is not None:
            u0, v0 = u, v - pivot          # rotate about a point below the card centre
            out.append((cx + u0 * np.cos(a) - v0 * np.sin(a), cy + pivot + u0 * np.sin(a) + v0 * np.cos(a), z))
        else:
            out.append((cx + u * np.cos(a) - v * np.sin(a), cy + u * np.sin(a) + v * np.cos(a), z))
    return out


def draw_card(canvas, cam, face, mask, edge, cx, cy, ang, z0, t, pivot=None, light=None, shadow=True):
    W, H = cam.W, cam.H
    src = np.float32([(0, 0), (PW, 0), (PW, PH), (0, PH)])
    small = cv2.resize(mask, (PW // 3, PH // 3), interpolation=cv2.INTER_AREA)
    srcs = src / 3
    if shadow:
        Hm = cv2.getPerspectiveTransform(srcs, np.float32([cam.p(P) for P in corners_world(cx, cy, ang, z0, pivot)]))
        sh = cv2.warpPerspective(small, Hm, (W, H))
        sh = np.roll(cv2.GaussianBlur(sh, (0, 0), 14), (10, 6), (0, 1))
        canvas *= (1 - sh[..., None] * .7)
    steps = max(3, int(t * 22))
    ec = np.array(edge, np.float32) / 255
    for i, z in enumerate(np.linspace(z0, z0 + t, steps)):
        Hm = cv2.getPerspectiveTransform(srcs, np.float32([cam.p(P) for P in corners_world(cx, cy, ang, z, pivot)]))
        a = cv2.warpPerspective(small, Hm, (W, H))[..., None]
        shade = .55 + .45 * i / (steps - 1)
        canvas[:] = canvas * (1 - a) + ec * shade * a
    Hm = cv2.getPerspectiveTransform(src, np.float32([cam.p(P) for P in corners_world(cx, cy, ang, z0 + t, pivot)]))
    f = cv2.warpPerspective(face, Hm, (W, H))
    a = cv2.warpPerspective(mask, Hm, (W, H))[..., None]
    if light is not None:
        f = f * light[..., None]
    canvas[:] = canvas * (1 - a) + f * a
    # the thin light edge where the top face meets the side
    rim = np.clip(a[..., 0] - cv2.erode(a[..., 0], np.ones((3, 3), np.uint8)), 0, 1)[..., None]
    canvas[:] = canvas * (1 - rim * .5) + ec * rim * .5


def table(W, H, cx=.5, cy=.45, k=.13):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = np.exp(-(((xx - W * cx) / (W * .55)) ** 2 + ((yy - H * cy) / (H * .6)) ** 2)) * k + .02
    t += np.random.default_rng(4).normal(0, .004, (H, W))
    return np.dstack([t] * 3).astype(np.float32)


def face_light(W, H):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return np.clip(.86 + .2 * np.exp(-(((xx - W * .45) / (W * .5)) ** 2 + ((yy - H * .3) / (H * .5)) ** 2)), 0, 1.06)


def load(n):
    return cv2.cvtColor(cv2.imread(f'{O}/{n}'), cv2.COLOR_BGR2RGB).astype(np.float32) / 255


def save(path, img, labels=()):
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for (x, y, txt, size, col) in labels:
        d.text((x, y), txt, fill=col, font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', size), anchor='mm')
    im.save(path, quality=93)


# 1. the four tiers on a table
W, H = 2600, 1500
cam = Cam(el=50, dist=520, f=4300, W=W, H=H, look=(0, -10, 0))
canvas = table(W, H); L = face_light(W, H)
xs, angs = (-105, -35, 35, 105), (-4, 2, -2, 5)
for (k, (fn, cuts, edge, t)), x, a in zip(TIERS.items(), xs, angs):
    draw_card(canvas, cam, load(fn), card_mask(cuts), edge, x, 0, a, 0, t, light=L)
labs = [('COMMON', ['no tell']), ('RARE', ['one corner cut']), ('TOP', ['corner cut', 'blood-red edge']), ('1 OF 1', ['two corners cut', 'gold edge · double thick'])]
lab = []
for x, (a, b) in zip(xs, labs):
    u, v = cam.p((x, -CH / 2 - 6, 0))
    lab += [(u, v + 14, a, 40, (236, 232, 222))] + [(u, v + 62 + j * 34, line, 26, (160, 155, 146)) for j, line in enumerate(b)]
save(f'{DEL}/1-four-tiers.jpg', canvas, lab)

# 2. a fanned hand of backs: the rare's red edge and cut corner show before you get to it
W, H = 2000, 1600
cam = Cam(el=72, dist=470, f=3500, W=W, H=H, look=(0, -2, 0))
canvas = table(W, H, .5, .5, .12)
back = load('card_M_back.png'); L = face_light(W, H)
plain = card_mask([], back=True)
deck = [('T0', None)] * 7
deck[2] = ('T2', None); deck[5] = ('T1', None)
for i, (k, _) in enumerate(deck):
    fn, cuts, edge, t = TIERS[k]
    ang = 27 - i * 8.5
    draw_card(canvas, cam, back, card_mask(cuts, back=True), edge, 0, -10, ang, i * .5, t, pivot=-46, light=L, shadow=(i == 0))
save(f'{DEL}/2-fanned-hand.jpg', canvas, [(W / 2, H - 70, "a red edge and a cut corner, before you've even turned it over", 30, (200, 196, 186))])

# 3. a pack's stack from the side: one red line, one thick gold line
W, H = 2400, 1100
cam = Cam(el=10, dist=330, f=7600, W=W, H=H, look=(0, 0, 3.4), az=5)
canvas = table(W, H, .5, .6, .10)
order = ['T0', 'T0', 'T0', 'T1', 'T0', 'T0', 'T2', 'T0', 'T0', 'T3', 'T0']
rng = np.random.default_rng(9); z = 0
for k in order:
    fn, cuts, edge, t = TIERS[k]
    draw_card(canvas, cam, back, card_mask(cuts, back=True), edge, rng.uniform(-.8, .8), rng.uniform(-.6, .6), rng.uniform(-1.2, 1.2), z, t, light=None, shadow=(z == 0))
    z += t + .02
save(f'{DEL}/3-pack-from-the-side.jpg', canvas, [(W / 2, H - 80, 'the pack, edge on: the hits are already showing', 32, (200, 196, 186))])

# flat faces with their real shape, for close looks
for k, (fn, cuts, edge, t) in TIERS.items():
    f = load(fn); m = card_mask(cuts)[..., None]
    out = f * m + np.array((14, 14, 15), np.float32) / 255 * (1 - m)
    save(f'{DEL}/face-{k}.jpg', out)
print(sorted(os.listdir(DEL)))
