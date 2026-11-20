"""BASE STYLE ("cut print") for Common..Signature: a film frame printed as a 2-ink halftone poster.
One layout, one script, any frame. Tier changes only the stock and the inks:
  C  bone paper, black ink only        U  bone paper, black + red ink
  R  black stock, bone + red ink       H  R + silver foil on the bone ink
  RR H + gold foil + a red glow behind the figure
usage: python base_style.py FRAME.png TIER OUT.png"""
import sys, cv2, numpy as np

W, H, SS = 1500, 2100, 2
TIERS = ('C', 'U', 'R', 'H', 'RR')


def halftone(need, cell, angle=45):
    h, w = need.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = np.deg2rad(angle)
    u = (xx * np.cos(a) + yy * np.sin(a)) * 2 * np.pi / cell
    v = (-xx * np.sin(a) + yy * np.cos(a)) * 2 * np.pi / cell
    scr = (np.cos(u) + np.cos(v)) / 4 + 0.5
    d = np.clip((need - (1 - scr)) / 0.08 + 0.5, 0, 1)
    return np.where(need < 0.05, 0, d)


def crisp(m, s):
    m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), s)
    return np.clip((m - 0.5) * 6 + 0.5, 0, 1)


def foil(h, w, kind, seed=3):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = ((xx * 0.55 + yy * 0.83) / (w * 0.55 + h * 0.83))
    band = 0.5 + 0.5 * np.sin(t * 2 * np.pi * 2.4 + 0.7) * 0.9
    brush = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigmaX=40, sigmaY=0.9)
    brush = brush / (np.abs(brush).max() + 1e-6)
    v = np.clip(band * 0.8 + 0.1 + brush * 0.10, 0, 1)
    sp = (rng.random((h, w)) > 0.9994).astype(np.float32); sp = cv2.GaussianBlur(sp, (0, 0), 1.6) * 9
    if kind == 'silver':
        lo, hi = np.array([0.30, 0.31, 0.34]), np.array([0.96, 0.97, 1.0])
    else:
        lo, hi = np.array([0.42, 0.28, 0.08]), np.array([1.0, 0.86, 0.50])
    c = lo[None, None] * (1 - v[..., None]) + hi[None, None] * v[..., None]
    return np.clip(c + sp[..., None] * 0.6, 0, 1).astype(np.float32)


def render(frame, tier, out):
    assert tier in TIERS
    im = cv2.imread(frame).astype(np.float32) / 255
    lum0 = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    bgv = float(np.median(np.concatenate([lum0[:20].ravel(), lum0[-20:].ravel(), lum0[:, :20].ravel(), lum0[:, -20:].ravel()])))
    m0 = np.abs(lum0 - bgv) > 0.10
    ys, xs = np.where(m0)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    mx, my = int((x1 - x0) * 0.04) + 6, int((y1 - y0) * 0.04) + 6
    x0, x1, y0, y1 = max(0, x0 - mx), min(im.shape[1], x1 + mx), max(0, y0 - my), min(im.shape[0], y1 + my)
    crop = im[y0:y1, x0:x1]
    bw, bh = x1 - x0, y1 - y0
    s = min(1380 / bw, 1500 / bh, 3.4)
    tw, th = int(bw * s * SS), int(bh * s * SS)
    crop = cv2.resize(crop, (tw, th), interpolation=cv2.INTER_CUBIC)
    cv = np.empty((H * SS, W * SS, 3), np.float32); cv[:] = bgv
    cx, cy = W * SS // 2, int(1135 * SS)
    ox, oy = cx - tw // 2, cy - th // 2
    sx0, sy0 = max(0, ox), max(0, oy); sx1, sy1 = min(W * SS, ox + tw), min(H * SS, oy + th)
    cv[sy0:sy1, sx0:sx1] = crop[sy0 - oy:sy1 - oy, sx0 - ox:sx1 - ox]
    b, g, r = cv[..., 0], cv[..., 1], cv[..., 2]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    redness = np.clip((r - np.maximum(g, b) - 0.07) / 0.25, 0, 1)
    nonred = 1 - np.clip(redness * 2, 0, 1)

    # ---- the figure's plates ----
    sm = cv2.GaussianBlur(lum, (0, 0), 1.0 * SS)
    ink = crisp(((sm < 0.22) & (redness < 0.3)).astype(np.float32), 0.9 * SS)
    mid_need = np.clip((bgv - 0.07 - cv2.GaussianBlur(lum, (0, 0), 2.2 * SS)) / (bgv - 0.07 - 0.22), 0, 1) * 0.85
    mid_need = mid_need * nonred * (1 - ink)
    mid = halftone(mid_need, 11.0 * SS)
    lightspot = crisp(((cv2.GaussianBlur(lum, (0, 0), 1.0 * SS) > bgv + 0.045) & (redness < 0.2)).astype(np.float32), 0.9 * SS)
    red_solid = crisp((redness > 0.5).astype(np.float32), 1.2 * SS)
    pink = np.clip(cv2.GaussianBlur(redness, (0, 0), 2.0 * SS), 0, 1) * (1 - red_solid)
    red_dots = halftone(np.clip(pink * 1.1, 0, 1) * 0.8, 9.0 * SS, 15)
    figmask = np.clip(np.maximum.reduce([ink, mid, red_solid, red_dots, lightspot]), 0, 1)

    # ---- the burst behind the figure: the same dots, bigger, radiating from the action ----
    fm = (np.abs(lum - bgv) > 0.10).astype(np.uint8)
    M = cv2.moments(fm, binaryImage=True)
    bx, by = (M['m10'] / max(M['m00'], 1), M['m01'] / max(M['m00'], 1))
    yy, xx = np.mgrid[0:H * SS, 0:W * SS].astype(np.float32)
    dx, dy = xx - bx, yy - by
    rr = np.hypot(dx, dy) / SS
    th_ = (np.arctan2(dy, dx) + np.pi) / (2 * np.pi)
    rng = np.random.default_rng(abs(hash(frame)) % 1000)
    ray1 = cv2.GaussianBlur(rng.normal(0, 1, (1, 900)).astype(np.float32), (0, 0), sigmaX=2.2, sigmaY=0.1)[0]
    ray1 = (ray1 - ray1.mean()) / (ray1.std() + 1e-6)
    ray = np.clip(np.interp(th_ * 900, np.arange(900), ray1, period=900) * 0.55 + 0.55, 0, 1)
    dens = np.clip(1.08 - rr / 1550.0, 0, 1) ** 1.5 * (0.22 + 0.78 * ray)
    halo = cv2.dilate((figmask > 0.3).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (28 * SS, 28 * SS)))
    dens = dens * (1 - cv2.GaussianBlur(halo.astype(np.float32), (0, 0), 6 * SS))
    burst = halftone(np.clip(dens, 0, 1) * 0.92, 20.0 * SS, 30)

    def down(a):
        return cv2.resize(a, (W, H), interpolation=cv2.INTER_AREA)
    ink_d, mid_d, red_d, rdot_d, light_d, burst_d, fig_d = map(down, (ink, mid, red_solid, red_dots, lightspot, burst, figmask))
    rng2 = np.random.default_rng(7)
    grain = cv2.GaussianBlur(rng2.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 0.7)
    PAPER, INK, BONE, STOCK = np.array([.92, .895, .83]), np.array([.07, .07, .075]), np.array([.93, .91, .86]), np.array([.045, .045, .05])
    RED = np.array([.78, .07, .10])
    img = np.zeros((H, W, 3), np.float32)
    inverse = tier in ('R', 'H', 'RR')
    if not inverse:
        K = np.clip(np.maximum.reduce([ink_d, mid_d, burst_d * 0.62]), 0, 1)
        if tier == 'C':                                  # one ink: the red prints black
            K = np.clip(np.maximum(K, np.maximum(red_d, rdot_d)), 0, 1); red_d = red_d * 0; rdot_d = rdot_d * 0
        paper = PAPER[None, None] * (1 + grain[..., None] * 0.012)
        img = paper * (1 - K[..., None]) + INK[None, None] * K[..., None]
    else:
        bone = np.clip(np.maximum.reduce([ink_d, mid_d, burst_d * 0.55, light_d]), 0, 1)
        stock = STOCK[None, None] * (1 + grain[..., None] * 0.04)
        col = BONE[None, None] * np.ones((H, W, 1), np.float32)
        if tier == 'H':
            col = foil(H, W, 'silver')
        if tier == 'RR':
            col = foil(H, W, 'gold')
            glow = np.exp(-(((np.arange(W)[None, :] - bx / SS) / 620.0) ** 2 + ((np.arange(H)[:, None] - by / SS) / 780.0) ** 2))
            stock = stock + (np.array([.34, .02, .03])[None, None] * glow[..., None] * 0.9)
        img = stock * (1 - bone[..., None]) + col * bone[..., None]
    img = img * (1 - np.clip(red_d + rdot_d * 0.85, 0, 1)[..., None]) + RED[None, None] * np.clip(red_d + rdot_d * 0.85, 0, 1)[..., None]
    img += grain[..., None] * 0.008
    cv2.imwrite(out, (np.clip(img[..., ::-1], 0, 1) * 255 + .5).astype(np.uint8))
    return out


if __name__ == '__main__':
    render(sys.argv[1], sys.argv[2], sys.argv[3]); print('ok', sys.argv[3])
