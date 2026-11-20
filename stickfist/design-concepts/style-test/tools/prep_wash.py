"""Ronin as sumi-e: continuous ink density with bleeding edges and dry-brush, plus red ink (1500 x 2100).
usage: python prep_wash.py REF.png OUTDIR"""
import sys, os, cv2, numpy as np
ref, outd = sys.argv[1:3]; os.makedirs(outd, exist_ok=True)
W, H = 1500, 2100
im = cv2.imread(ref).astype(np.float32) / 255
im = cv2.resize(im, (W, H), interpolation=cv2.INTER_CUBIC)
b, g, r = im[..., 0], im[..., 1], im[..., 2]
lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
bg = float(np.median(lum[:80, :80]))
redness = np.clip((r - np.maximum(g, b) - 0.04) / 0.30, 0, 1)             # strong red = full, pale pink halo = a faint wash
rng = np.random.default_rng(5)
def noise(cell, amp=1.0):
    n = rng.normal(0, 1, (H // cell + 2, W // cell + 2)).astype(np.float32)
    return cv2.resize(n, (W, H), interpolation=cv2.INTER_CUBIC) * amp
# ink density: darker than the paper = more ink (red areas excluded), warped a little like wet fibre
dens = np.clip((bg - lum) / bg, 0, 1) * (1 - np.clip(redness * 1.4, 0, 1))
dens = np.clip(dens * 1.25, 0, 1)
warp = noise(60, 6.0); warp2 = noise(60, 6.0)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
dens = cv2.remap(dens, xx + warp, yy + warp2, cv2.INTER_LINEAR)
core = cv2.GaussianBlur(dens, (0, 0), 1.4)
halo = cv2.GaussianBlur(dens, (0, 0), 9.0)                                  # ink bleeds into the paper
edge_noise = noise(14, 0.5) + noise(5, 0.3)
bleed = np.clip(core * 1.0 + halo * (0.55 + 0.35 * edge_noise), 0, 1)
bleed = np.maximum(bleed, core * 0.95)
# dry brush: along the sweep direction the ink breaks into streaks where it is thin
streak = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), sigmaX=30, sigmaY=0.8)
streak = (streak - streak.min()) / (np.ptp(streak) + 1e-6)
dry = np.clip((bleed - 0.20) / 0.5, 0, 1) * 0.0 + bleed
thin = (bleed > 0.08) & (bleed < 0.7)
bleed = np.where(thin, bleed * (0.55 + 0.7 * streak), bleed)
K = np.clip(bleed, 0, 1) ** 0.9
# red ink: flat disc/crescent with a slight bleed, pink halo as a thin wash
R = cv2.remap(redness, xx + warp * 0.6, yy + warp2 * 0.6, cv2.INTER_LINEAR)
R = np.clip(cv2.GaussianBlur(R, (0, 0), 1.2) * 1.05 + cv2.GaussianBlur(R, (0, 0), 6) * (0.35 + 0.25 * edge_noise), 0, 1)
cv2.imwrite(os.path.join(outd, 'K.png'), (K * 255 + .5).astype(np.uint8))
cv2.imwrite(os.path.join(outd, 'R.png'), (R * 255 + .5).astype(np.uint8))
paper = np.array([0.90, 0.87, 0.80], np.float32)
proof = paper[None, None] * (1 - K[..., None] * 0.97) + 0.0
proof = proof * (1 - R[..., None]) + np.array([0.74, 0.07, 0.09], np.float32)[None, None] * R[..., None]
cv2.imwrite(os.path.join(outd, 'proof.png'), (np.clip(proof[..., ::-1], 0, 1) * 255 + .5).astype(np.uint8))
print('wash prep K mean', round(float(K.mean()), 3), 'R mean', round(float(R.mean()), 3))
