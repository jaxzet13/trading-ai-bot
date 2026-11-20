"""Rebuild a cheap low-res reference as print plates at 1500 x 2100:
  K  = black ink coverage (solid linework + my own halftone dots for the tones)
  R  = red ink coverage (crisp)
Everything is classified at 2x and area-downsampled, so edges are sharp at any card size.
usage: python plates.py REF.png OUTDIR [cell_px]"""
import sys, os, cv2, numpy as np
ref, outd = sys.argv[1], sys.argv[2]
CELL = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
os.makedirs(outd, exist_ok=True)
W, H, SS = 1500, 2100, 2
im = cv2.imread(ref).astype(np.float32) / 255
h0, w0 = im.shape[:2]
k = max(W * SS / w0, H * SS / h0)
big = cv2.resize(im, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_CUBIC)
y0 = (big.shape[0] - H * SS) // 2; x0 = (big.shape[1] - W * SS) // 2
big = np.ascontiguousarray(big[y0:y0 + H * SS, x0:x0 + W * SS])
b, g, r = big[..., 0], big[..., 1], big[..., 2]
lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

# ---- red plate: strongly red pixels, edges re-sharpened ----
redness = np.clip((r - np.maximum(g, b) - 0.08) / 0.22, 0, 1)
R = cv2.GaussianBlur(redness, (0, 0), 1.6 * SS)
R = np.clip((R - 0.5) * 6 + 0.5, 0, 1)

# ---- black plate ----
lum_nr = np.where(redness > 0.3, 0.92, lum)                  # red areas read as paper for the black plate
light = cv2.GaussianBlur(lum_nr, (0, 0), 1.1 * SS)
ink = np.clip((0.17 - light) / 0.05, 0, 1)                   # solid ink = the dark linework and fills
ink = cv2.GaussianBlur(ink, (0, 0), 0.9 * SS)
ink = np.clip((ink - 0.5) * 5 + 0.5, 0, 1)
tone = cv2.GaussianBlur(lum_nr, (0, 0), 3.2 * SS)            # old dots blurred away: a clean continuous tone
tone = np.clip((tone - 0.10) / (0.88 - 0.10), 0, 1)          # 0 = solid, 1 = paper
yy, xx = np.mgrid[0:H * SS, 0:W * SS].astype(np.float32)
a = np.deg2rad(45)
u = (xx * np.cos(a) + yy * np.sin(a)) * 2 * np.pi / (CELL * SS)
v = (-xx * np.sin(a) + yy * np.cos(a)) * 2 * np.pi / (CELL * SS)
scr = (np.cos(u) + np.cos(v)) / 4 + 0.5                       # 0..1 dot field
need = 1 - tone                                               # how much ink this tone needs
dots = np.clip((need - (1 - scr)) / 0.07 + 0.5, 0, 1)
dots = np.where(need < 0.06, 0, dots)                         # pure paper stays clean
K = np.maximum(ink, dots * (1 - ink))
K = np.where(R > 0.5, np.minimum(K, 0.0), K)                  # no black dots under red

def down(m):
    return cv2.resize(m, (W, H), interpolation=cv2.INTER_AREA)
Kd, Rd = down(K), down(R)
cv2.imwrite(os.path.join(outd, 'K.png'), (np.clip(Kd, 0, 1) * 255 + .5).astype(np.uint8))
cv2.imwrite(os.path.join(outd, 'R.png'), (np.clip(Rd, 0, 1) * 255 + .5).astype(np.uint8))
# a flat proof: paper, black, red
paper = np.array([0.89, 0.86, 0.80], np.float32); blk = np.array([0.04, 0.04, 0.045], np.float32); red = np.array([0.78, 0.06, 0.09], np.float32)
proof = paper[None, None] * (1 - Kd[..., None]) + blk[None, None] * Kd[..., None]
proof = proof * (1 - Rd[..., None]) + red[None, None] * Rd[..., None]
cv2.imwrite(os.path.join(outd, 'proof.png'), (np.clip(proof[..., ::-1], 0, 1) * 255 + .5).astype(np.uint8))
print('plates', Kd.shape, 'K mean', round(float(Kd.mean()), 3), 'R mean', round(float(Rd.mean()), 3))
