"""Colossus as an engraved black-chrome plate: height map H, figure mask M, red inlay R (1500 x 2100).
usage: python prep_chrome.py REF.png OUTDIR"""
import sys, os, cv2, numpy as np
ref, outd = sys.argv[1:3]; os.makedirs(outd, exist_ok=True)
W, H = 1500, 2100
im = cv2.imread(ref).astype(np.float32) / 255
im = cv2.resize(im, (W, H), interpolation=cv2.INTER_CUBIC)
lum = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
bg = np.median(lum[:60, :60])
fig = (lum < bg - 0.18).astype(np.uint8)
fig = cv2.morphologyEx(fig, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
n, lab, st, _ = cv2.connectedComponentsWithStats(fig)
keep = np.zeros(n, bool); keep[1:] = st[1:, 4] > 3000; fig = keep[lab].astype(np.uint8)
fig = cv2.morphologyEx(fig, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
M = cv2.GaussianBlur(fig.astype(np.float32), (0, 0), 1.6); M = np.clip((M - .5) * 7 + .5, 0, 1)
# pillowed relief from the distance to the edge, plus the film's own inner detail lines
dist = cv2.distanceTransform(fig, cv2.DIST_L2, 5)
relief = np.tanh(dist / 46.0)
detail = np.clip((cv2.GaussianBlur(lum, (0, 0), 1.2) - cv2.GaussianBlur(lum, (0, 0), 7)), -0.2, 0.2)
dome = cv2.GaussianBlur(fig.astype(np.float32), (0, 0), 120)
Hm = 0.10 + 0.20 * relief * M + 0.50 * dome * M + detail * 0.9 * M
# impact rays engraved into the plate: they start at the hammer head and run out past the giant
ys, xs = np.where(fig > 0)
top = ys < np.percentile(ys, 18)
cx, cy = float(np.mean(xs[top])) if top.any() else W * .7, float(np.mean(ys[top])) if top.any() else H * .25
rng = np.random.default_rng(11)
rays = np.zeros((H, W), np.uint8); long_rays = np.zeros((H, W), np.uint8)
for i in range(46):
    a = rng.uniform(0, 2 * np.pi); r0 = rng.uniform(150, 380); r1 = r0 + rng.uniform(260, 1100)
    p0 = (int(cx + np.cos(a) * r0), int(cy + np.sin(a) * r0)); p1 = (int(cx + np.cos(a) * r1), int(cy + np.sin(a) * r1))
    wd = int(rng.uniform(3, 9))
    cv2.line(rays, p0, p1, 1, wd, cv2.LINE_AA)
    if r1 - r0 > 700: cv2.line(long_rays, p0, p1, 1, max(2, wd - 1), cv2.LINE_AA)
rays = (rays > 0).astype(np.float32) * (1 - M)           # grooves only in the plate, never through the figure
long_rays = (long_rays > 0).astype(np.float32) * (1 - M)
rays_s = cv2.GaussianBlur(rays, (0, 0), 1.3)
Hm = Hm - 0.28 * rays_s
# a double engraved border
bd = np.zeros((H, W), np.float32)
cv2.rectangle(bd, (46, 46), (W - 47, H - 47), 1, 5); cv2.rectangle(bd, (74, 74), (W - 75, H - 75), 1, 2)
Hm = Hm - 0.3 * cv2.GaussianBlur(bd, (0, 0), 1.0)
Hm = np.clip(Hm, 0, 1)
Rm = cv2.GaussianBlur(long_rays, (0, 0), 0.9); Rm = np.clip((Rm - .3) * 3, 0, 1)
cv2.imwrite(os.path.join(outd, 'H.png'), (Hm * 65535).astype(np.uint16))
cv2.imwrite(os.path.join(outd, 'M.png'), (M * 255 + .5).astype(np.uint8))
cv2.imwrite(os.path.join(outd, 'R.png'), (Rm * 255 + .5).astype(np.uint8))
print('chrome prep', 'fig px', int(fig.sum()), 'ray centre', int(cx), int(cy))
