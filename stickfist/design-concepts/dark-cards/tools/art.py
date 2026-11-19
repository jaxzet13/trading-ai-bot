"""Pull clean, print-resolution layers out of the owner's own film frames.

Each frame is flat colour (bg grey, black ink, grey bodies, red blood, steel blades),
so we classify every pixel to that palette at a supersampled size, smooth the
edges and downsample: the result is crisp like a vector trace, at any scale.
"""
import os, cv2, numpy as np

FULL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'full', 'proto_all_%03d.png')
# make the frames first: ffmpeg -i ../../../films/daggers.mp4 full/proto_all_%03d.png

# BGR palette sampled from the film (k-means on frame 246)
PAL = np.array([
    (212, 216, 215),  # 0 bg
    (0, 0, 0),        # 1 ink
    (81, 84, 83),     # 2 grey bodies
    (0, 0, 167),      # 3 blood
    (27, 26, 128),    # 4 dark blood
    (142, 145, 157),  # 5 blade steel
    (240, 242, 242),  # 6 blade shine
], np.float32)
GROUPS = {'ink': [1], 'grey': [2], 'red': [3, 4], 'steel': [5, 6]}


def frame(n):
    return cv2.imread(FULL % n)


def layers(img, scale=2.0, ss=2):
    """Return {name: float32 mask 0..1} at `scale` x the input size."""
    img = cv2.bilateralFilter(img, 5, 30, 5)
    big = cv2.resize(img, None, fx=scale * ss, fy=scale * ss, interpolation=cv2.INTER_CUBIC).astype(np.float32)
    d = ((big[:, :, None, :] - PAL[None, None]) ** 2).sum(-1)
    lab = d.argmin(-1)
    out = {}
    h, w = img.shape[:2]
    size = (int(round(w * scale)), int(round(h * scale)))
    for k, ids in GROUPS.items():
        m = np.isin(lab, ids).astype(np.float32)
        m = cv2.GaussianBlur(m, (0, 0), 1.2 * ss)
        m = (m > 0.5).astype(np.float32)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        out[k] = cv2.resize(m, size, interpolation=cv2.INTER_AREA)
    return out


def comp(L, colours, bg):
    """Paint layers in order onto a bg colour. colours: [(name, rgb, alpha)]."""
    h, w = next(iter(L.values())).shape
    o = np.empty((h, w, 3), np.float32); o[:] = bg
    for name, rgb, a in colours:
        m = (L[name] * a)[..., None]
        o = o * (1 - m) + np.array(rgb, np.float32) * m
    return o


def grain(h, w, amt=6, seed=1):
    r = np.random.default_rng(seed)
    g = r.normal(0, 1, (h, w)).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 0.7)
    big = cv2.resize(r.normal(0, 1, (h // 24 + 2, w // 24 + 2)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    return (g * amt + big * amt * 0.25)[..., None]


def save(path, rgb):
    cv2.imwrite(path, cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
