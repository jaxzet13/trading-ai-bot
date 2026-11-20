"""Cut a reference into stacked paper sheets (crisp masks, 1500 x 2100).
usage: python prep_paper.py REF.png OUTDIR"""
import sys, os, cv2, numpy as np
ref, outd = sys.argv[1:3]; os.makedirs(outd, exist_ok=True)
W, H = 1500, 2100
im = cv2.imread(ref).astype(np.float32) / 255
h0, w0 = im.shape[:2]; k = max(W / w0, H / h0)
im = cv2.resize(im, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_CUBIC)
y0 = (im.shape[0] - H) // 2; x0 = (im.shape[1] - W) // 2
im = np.ascontiguousarray(im[y0:y0 + H, x0:x0 + W])
b, g, r = im[..., 0], im[..., 1], im[..., 2]
lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
lum = cv2.medianBlur((lum * 255).astype(np.uint8), 9).astype(np.float32) / 255
lum = cv2.GaussianBlur(lum, (0, 0), 2.0)
red = np.clip((r - np.maximum(g, b) - 0.10) / 0.2, 0, 1)
red = cv2.GaussianBlur(red, (0, 0), 2.0)
moon = (red > 0.5).astype(np.uint8)
# keep only the big red region (the moon)
n, lab, st, _ = cv2.connectedComponentsWithStats(moon)
big = 1 + np.argmax(st[1:, 4]); moon = (lab == big)
moon = cv2.morphologyEx(moon.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (45, 45)))
# depth rank from brightness (measured on the reference): 0 sky | 1 far mist | 2 mist | 3 mid hills | 4 trees + reaper | 5 black rock + hood
rank = np.zeros(lum.shape, np.int32)
rank[lum >= 0.20] = 1
rank[(lum >= 0.155) & (lum < 0.20)] = 2
rank[(lum >= 0.095) & (lum < 0.155)] = 0
rank[(lum >= 0.07) & (lum < 0.095)] = 3
rank[(lum >= 0.034) & (lum < 0.07)] = 4
rank[lum < 0.034] = 5
rank[moon > 0] = 0
NS = 5

def crisp(m, s=1.8):
    m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), s)
    return np.clip((m - 0.5) * 7 + 0.5, 0, 1)

sheets = []
for kk in range(1, NS + 1):
    m = (rank >= kk).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros(n, bool); keep[1:] = st[1:, 4] > 60
    m = keep[lab].astype(np.uint8)
    mc = crisp(m)
    cv2.imwrite(os.path.join(outd, f'S{kk}.png'), (mc * 255 + .5).astype(np.uint8))
    sheets.append(mc)
# the sky sheet has the moon cut out; the moon sheet sits behind everything
sky_sheet = (1 - moon).astype(np.uint8)
cv2.imwrite(os.path.join(outd, 'S0.png'), (crisp(sky_sheet, 2.2) * 255 + .5).astype(np.uint8))
cv2.imwrite(os.path.join(outd, 'moon.png'), (crisp(moon, 2.2) * 255 + .5).astype(np.uint8))
# per-sheet flat paper colours: the median colour of each band in the reference
cols = {}
for kk in range(0, NS + 1):
    sel = (rank == kk)
    cols[kk] = [float(np.median(im[..., 2][sel])), float(np.median(im[..., 1][sel])), float(np.median(im[..., 0][sel]))] if sel.sum() > 500 else [0.03, 0.03, 0.03]
# colour maps: flat sheet colour + a bright cut edge on the side the light hits (top-left)
def shift(a, dx, dy):
    return cv2.warpAffine(a, np.float32([[1, 0, dx], [0, 1, dy]]), (a.shape[1], a.shape[0]))
for kk in range(0, NS + 1):
    m = crisp(sky_sheet, 2.2) if kk == 0 else sheets[kk - 1]
    base = np.array(cols[kk], np.float32) * [1.0, 2.1, 1.9, 1.7, 1.45, 1.25][kk] if kk > 0 else np.array(cols[kk], np.float32) * 1.4
    rim = np.clip(m - shift(m, 5, 5), 0, 1); rim = cv2.GaussianBlur(rim, (0, 0), 0.9)
    shade = (0.92 + 0.16 * np.linspace(1, 0, H)[:, None] * np.ones((1, W)))[..., None]       # lighter toward the top of the sheet
    col = base[None, None] * shade + rim[..., None] * np.array([0.55, 0.52, 0.48], np.float32)
    cv2.imwrite(os.path.join(outd, f'C{kk}.png'), (np.clip(col[..., ::-1], 0, 1) * 255 + .5).astype(np.uint8))
import json; json.dump(cols, open(os.path.join(outd, 'cols.json'), 'w'))
print({kk: int((rank == kk).sum()) for kk in range(NS + 1)}); print(cols)
vis = np.zeros((H, W, 3), np.uint8)
pal = [(30, 30, 30), (150, 150, 150), (120, 120, 120), (90, 90, 90), (55, 55, 55), (12, 12, 12)]
for kk in range(NS + 1): vis[rank == kk] = pal[kk]
vis[moon > 0] = (30, 30, 190)
cv2.imwrite(os.path.join(outd, 'rank.png'), vis)
