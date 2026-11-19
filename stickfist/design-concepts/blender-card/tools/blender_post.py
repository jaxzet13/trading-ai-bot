"""Grade the Blender render (vignette, fine grain), cut the figure foreground, find the head."""
import sys, cv2, numpy as np
src, mask, out_bg, out_fg = sys.argv[1:5]
img = cv2.imread(src).astype(np.float32) / 255
H, W = img.shape[:2]
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
# lift the lit wall and the red, leave the blacks alone
lum = img.mean(-1, keepdims=True)
img = img * (1 + 1.1 * np.clip(lum * 6, 0, 1))
r = np.clip(img[..., 2:3] - img[..., :2].max(-1, keepdims=True), 0, 1)
img[..., 2:3] += r * .8
vg = np.clip(1 - (((xx - W * .5) / (W * .8)) ** 2 + ((yy - H * .45) / (H * .75)) ** 2) * .7, .15, 1)
img *= vg[..., None]
# matte blacks: lift nothing, crush a touch, keep the red
img = np.clip((img - .008) / (1 - .008), 0, 1) ** 1.06
g = np.random.default_rng(5).normal(0, 1, (H, W)).astype(np.float32)
img += cv2.GaussianBlur(g, (0, 0), .6)[..., None] * (.010 + .018 * np.clip(img.mean(-1, keepdims=True) * 3, 0, 1))
img = np.clip(img, 0, 1)
cv2.imwrite(out_bg, (img * 255 + .5).astype(np.uint8))
m = cv2.imread(mask, cv2.IMREAD_UNCHANGED)[..., 3].astype(np.float32) / 255
cv2.imwrite(out_fg, np.dstack([(img * 255 + .5).astype(np.uint8), (m * 255).astype(np.uint8)]))
ys, xs = np.where(m > .5)
print('head_top_px', int(ys.min()), 'x', int(xs[ys.argmin()]))
