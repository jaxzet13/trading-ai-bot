"""STIXX "grain print": a photo or illustration turned into a stochastic-grain xerox print.
Tones come from dot density (threshold against random noise), not from shading.
Steps: local contrast -> crushed blacks + blown highlights -> bloom -> grain threshold -> ink on paper.
usage: python grain_style.py IN.png OUT.png [mode] [grain_px] [seed]
modes: bw | blue | red | olive | brass   (the tint colours the highlights, the blacks stay black)"""
import sys, cv2, numpy as np

W, H = 1500, 2100
INK = np.array([0.030, 0.030, 0.036], np.float32)
TINTS = {   # (shadow, highlight) in RGB 0..1
    'bw':    ((0.030, 0.030, 0.036), (0.93, 0.915, 0.88)),
    'blue':  ((0.030, 0.050, 0.150), (0.95, 0.94, 0.86)),
    'red':   ((0.060, 0.010, 0.012), (0.95, 0.90, 0.84)),
    'olive': ((0.035, 0.040, 0.020), (0.88, 0.90, 0.70)),
    'brass': ((0.045, 0.034, 0.014), (0.97, 0.86, 0.58)),
}


def tone(img, black=0.10, white=0.92, gamma=0.85, clahe=2.2, bloom=0.55, bloom_r=46, bloom_thr=0.55):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if clahe:
        g = cv2.createCLAHE(clipLimit=clahe, tileGridSize=(6, 8)).apply(g)
    t = g.astype(np.float32) / 255
    t = np.clip((t - black) / (white - black), 0, 1) ** gamma
    if bloom:
        hi = np.clip((t - bloom_thr) / (1 - bloom_thr), 0, 1) ** 1.4
        t = np.clip(t + bloom * cv2.GaussianBlur(hi, (0, 0), bloom_r) + 0.35 * bloom * cv2.GaussianBlur(hi, (0, 0), bloom_r * 0.3), 0, 1)
    return t


def grain(t, g_px=2, seed=1, clump=0.7, bleed=0.6):
    """binary stochastic screen; g_px = size of one grain in output pixels"""
    h, w = t.shape
    rng = np.random.default_rng(seed)
    lw, lh = max(1, w // g_px), max(1, h // g_px)
    small = cv2.resize(t, (lw, lh), interpolation=cv2.INTER_AREA)
    n = rng.random((lh, lw)).astype(np.float32)
    if clump:                                              # slightly clumped noise = ink that pools
        n = cv2.GaussianBlur(n, (0, 0), clump)
        order = np.argsort(n.ravel()); r = np.empty(n.size, np.float32); r[order] = np.linspace(0, 1, n.size); n = r.reshape(n.shape)
    b = (small > n).astype(np.float32)
    big = cv2.resize(b, (w, h), interpolation=cv2.INTER_CUBIC)
    if bleed:                                              # a photocopier's edge: soften, then re-threshold
        big = cv2.GaussianBlur(big, (0, 0), bleed * g_px * 0.5)
        big = np.clip((big - 0.5) * 3.2 + 0.5, 0, 1)
    return big


def render(src, mode='bw', g_px=2, seed=1, out=None, crop=None, **kw):
    img = cv2.imread(src)
    h0, w0 = img.shape[:2]
    k = max(W / w0, H / h0)
    img = cv2.resize(img, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_LANCZOS4)
    y0 = int((img.shape[0] - H) * (crop if crop is not None else 0.35)); x0 = (img.shape[1] - W) // 2
    img = np.ascontiguousarray(img[y0:y0 + H, x0:x0 + W])
    t = tone(img, **kw)
    b = grain(t, g_px, seed)
    sh, hi = (np.array(c, np.float32) for c in TINTS[mode])
    paper_noise = cv2.GaussianBlur(np.random.default_rng(seed + 7).normal(0, 1, (H, W)).astype(np.float32), (0, 0), 1.0)
    col = sh[None, None] * (1 - b[..., None]) + hi[None, None] * b[..., None]
    col = col * (1 + paper_noise[..., None] * 0.012)
    res = np.clip(col[..., ::-1], 0, 1)
    if out: cv2.imwrite(out, (res * 255 + .5).astype(np.uint8))
    return res


if __name__ == '__main__':
    a = sys.argv
    render(a[1], a[3] if len(a) > 3 else 'bw', int(a[4]) if len(a) > 4 else 2, int(a[5]) if len(a) > 5 else 1, a[2]); print('ok', a[2])
