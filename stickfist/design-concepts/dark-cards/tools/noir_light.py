"""Light a flat film figure like a set: matte black stage, one hard key light that
throws a giant shadow on the wall, a back light that rims the figure, wet blood,
fine grain. Everything comes from the figure masks; nothing is generated."""
import cv2, numpy as np

PAL = np.array([(212, 216, 215), (0, 0, 0), (81, 84, 83), (0, 0, 167), (27, 26, 128), (142, 145, 157), (240, 242, 242)], np.float32)
GROUPS = {'ink': [1], 'grey': [2], 'red': [3, 4], 'steel': [5, 6]}


def layers(img, scale, ss=2, pal=PAL, groups=GROUPS):
    img = cv2.bilateralFilter(img, 5, 30, 5)
    big = cv2.resize(img, None, fx=scale * ss, fy=scale * ss, interpolation=cv2.INTER_CUBIC).astype(np.float32)
    best = np.full(big.shape[:2], 1e9, np.float32); lab = np.zeros(big.shape[:2], np.uint8)
    for i, c in enumerate(pal):
        d = ((big - c) ** 2).sum(-1)
        m = d < best; best[m] = d[m]; lab[m] = i
    del big, best
    h, w = img.shape[:2]; size = (int(round(w * scale)), int(round(h * scale)))
    out = {}
    k_open = int(2 * scale * ss) | 1
    for k, ids in groups.items():
        m = np.isin(lab, ids).astype(np.uint8)
        if k in ('grey', 'steel'):
            # anti-aliased film edges sort into grey/steel as thin fringes: open them away, drop crumbs
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k_open, k_open), np.uint8))
            n, cl, st, _ = cv2.connectedComponentsWithStats(m)
            keep = np.zeros(n, bool); keep[1:] = st[1:, 4] > (60 if k == 'steel' else 400) * (scale * ss) ** 2 / 4
            m = keep[cl].astype(np.uint8)
        m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), (2.2 if k == 'steel' else 1.3) * ss)
        m = (m > 0.5).astype(np.uint8)
        if k == 'ink':
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k_open, k_open), np.uint8))
        out[k] = cv2.resize(m.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    # where a fringe was removed from ink's edge, give it back to ink
    return out


def place(m, W, H, x0, y0):
    o = np.zeros((H, W), np.float32)
    h, w = m.shape
    xs, ys = max(0, x0), max(0, y0); xe, ye = min(W, x0 + w), min(H, y0 + h)
    o[ys:ye, xs:xe] = m[ys - y0:ye - y0, xs - x0:xe - x0]
    return o


def fbm(H, W, rng, octaves=((60, 1), (22, .5), (8, .25))):
    t = np.zeros((H, W), np.float32)
    for cell, amp in octaves:
        n = rng.normal(0, 1, (H // cell + 2, W // cell + 2)).astype(np.float32)
        t += cv2.resize(n, (W, H), interpolation=cv2.INTER_CUBIC) * amp
    return t / sum(a for _, a in octaves)


def shift(m, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(m, M, (m.shape[1], m.shape[0]))


def render(L, W, H, x0, y0, horizon, feet, *, wall_c, wall_r, floor_r, shadow_scale=1.55, shadow_off=(0, 0),
           rim_dir=(1, -1), rim_px=5, light_tint=(226, 218, 204), wall_i=.42, floor_i=.30, rain=0, seed=3,
           blood=(118, 6, 9), red_rim=False, haze=.10, rim_src=(0, 0), rim_reach=1400):
    rng = np.random.default_rng(seed)
    fig = place(L['ink'], W, H, x0, y0); vic = place(L['grey'], W, H, x0, y0)
    red = place(L['red'], W, H, x0, y0); steel = place(L['steel'], W, H, x0, y0)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    tint = np.array(light_tint, np.float32) / 255

    # key light on the wall and on the floor
    d2 = ((xx - wall_c[0]) / wall_r[0]) ** 2 + ((yy - wall_c[1]) / wall_r[1]) ** 2
    wall = np.exp(-d2 ** 1.7) * .85 + np.exp(-d2 * .45) * .15      # a hard spotlight edge with a soft spill
    wall = wall * wall_i * (1 + .10 * fbm(H, W, rng))        # plaster isn't perfectly even
    floor = np.exp(-(((xx - feet[0]) / floor_r[0]) ** 2 + ((yy - feet[1]) / floor_r[1]) ** 2)) * floor_i
    t = np.clip((yy - horizon) / 6 + .5, 0, 1)
    light = wall * (1 - t) + floor * t
    # the corner where wall meets floor catches a thin line of light
    light += np.exp(-((yy - horizon) / 2.2) ** 2) * wall * .35

    # giant cast shadow on the wall (figure scaled up from the feet), short one on the floor
    occ = np.clip(fig + vic + steel, 0, 1)
    fx, fy = feet
    s = shadow_scale
    M = np.float32([[s, 0, fx - s * fx + shadow_off[0]], [0, s, fy - s * fy + shadow_off[1]]])
    sh_wall = cv2.warpAffine(occ, M, (W, H))
    sh_wall = cv2.GaussianBlur(sh_wall, (0, 0), 5) * (1 - t)
    Mf = np.float32([[1, -.9, .9 * fy], [0, .22, fy - .22 * fy]])       # flattened, raked to the left on the floor
    sh_floor = cv2.GaussianBlur(cv2.warpAffine(occ, Mf, (W, H)), (0, 0), 7) * t
    light = light * (1 - np.clip(sh_wall * .93 + sh_floor * .85, 0, 1))

    # haze in the key beam: dust you can only see where light passes
    beam = np.clip(light * 2.2, 0, 1) * (np.clip(fbm(H, W, rng, ((90, 1), (30, .6))) * .5 + .5, 0, 1))
    light = light + beam * haze * .25

    base = np.array((9, 9, 10), np.float32) / 255
    img = base + light[..., None] * tint * (1 - base)

    # rain, visible only where the light hits it
    if rain:
        rl = np.zeros((H, W), np.float32)
        for _ in range(rain):
            x, y = rng.uniform(-200, W), rng.uniform(-200, H)
            ln = rng.uniform(40, 120); a = np.deg2rad(rng.uniform(100, 106))
            cv2.line(rl, (int(x), int(y)), (int(x + np.cos(a) * ln), int(y + np.sin(a) * ln)), float(rng.uniform(.35, 1)), 1, cv2.LINE_AA)
        rl = cv2.GaussianBlur(rl, (0, 0), .6)
        img += (rl * np.clip(light * 3, 0, 1))[..., None] * .55

    # blood: deep, with darker body, lighter where the key hits, and wet specular hits
    lit = cv2.GaussianBlur(light, (0, 0), 3)
    bl = np.array(blood, np.float32) / 255
    rb = red[..., None]
    edge = np.clip(red - cv2.erode(red, np.ones((7, 7), np.uint8)), 0, 1)
    blood_col = bl * (.55 + 1.6 * lit[..., None]) * (1 - .35 * edge[..., None])
    spec = np.clip(red - shift(red, 0, 3), 0, 1) * np.clip(lit * 2.5, 0, 1)
    spec = cv2.GaussianBlur(spec, (0, 0), .9) * .55
    img = img * (1 - rb) + blood_col * rb
    img += spec[..., None] * np.array((1, .55, .5), np.float32)

    # bodies: charcoal lumps that catch a little of the floor light
    vb = vic[..., None]
    img = img * (1 - vb) + (np.array((15, 15, 17), np.float32) / 255 + lit[..., None] * .12 * tint) * vb

    # the fighter: matte black, rimmed by the back light
    img = img * (1 - fig[..., None]) + np.array((6, 6, 7), np.float32) / 255 * fig[..., None]
    dx, dy = rim_dir
    rim = np.clip(fig - shift(fig, dx * rim_px, dy * rim_px), 0, 1)
    rim = cv2.GaussianBlur(rim, (0, 0), 1.1)
    fade = np.clip(1.15 - np.hypot(xx - rim_src[0], yy - rim_src[1]) / rim_reach, .15, 1)
    rim = rim * fade
    rim_c = np.array((.86, .10, .12) if red_rim else (.93, .91, .87), np.float32)
    img = img * (1 - rim[..., None] * .8) + rim_c * rim[..., None] * .8
    glow = cv2.GaussianBlur(rim, (0, 0), 9) * (1 - fig)
    img += glow[..., None] * rim_c * .18
    vrim = cv2.GaussianBlur(np.clip(vic - shift(vic, dx * 3, dy * 3), 0, 1), (0, 0), 1) * .5
    img += vrim[..., None] * tint * .5

    # steel: cold, bright, with a hard glint
    st = steel[..., None]
    hi = np.clip(steel - shift(steel, 3, 3), 0, 1)                       # bright edge toward the back light
    lo = np.clip(steel - shift(steel, -3, -3), 0, 1)
    body = np.array((.50, .52, .56), np.float32) + (yy / H * -.08)[..., None]
    img = img * (1 - st) + body * st
    img += cv2.GaussianBlur(hi, (0, 0), .7)[..., None] * .55
    img -= cv2.GaussianBlur(lo, (0, 0), .7)[..., None] * .25

    # vignette and fine grain
    vg = np.clip(1 - (((xx - W / 2) / (W * .75)) ** 2 + ((yy - H * .48) / (H * .7)) ** 2) * .9, .12, 1)
    img *= vg[..., None]
    g = rng.normal(0, 1, (H, W)).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), .55)
    img += g[..., None] * (.012 + .02 * np.clip(img.mean(-1, keepdims=True) * 2, 0, 1))
    img = np.clip(img, 0, 1)
    fg = np.clip(fig + steel + rim * .8, 0, 1)
    return img, fg


def save(path, img, q=None):
    cv2.imwrite(path, cv2.cvtColor((img * 255 + .5).astype(np.uint8), cv2.COLOR_RGB2BGR))
