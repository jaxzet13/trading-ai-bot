"""Grain print WITH the name printed through the same grain.
usage: python grain_card.py ART.png NAME_MASK.png OUT.png mode grain seed [tone kwargs as k=v ...]"""
import sys, cv2, numpy as np
import grain_style as G


def render_card(art, mask_path, out, mode='bw', g_px=2, seed=1, crop=0.5, halo=0.82, halo_r=34, text_bleed=0.5, **kw):
    img = cv2.imread(art)
    h0, w0 = img.shape[:2]; k = max(G.W / w0, G.H / h0)
    img = cv2.resize(img, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_LANCZOS4)
    y0 = int((img.shape[0] - G.H) * crop); x0 = (img.shape[1] - G.W) // 2
    img = np.ascontiguousarray(img[y0:y0 + G.H, x0:x0 + G.W])
    t = G.tone(img, **kw)
    m = cv2.imread(mask_path, 0).astype(np.float32) / 255
    # a dark halo behind the letters so they read on bright art, then the letters at full white
    t = t * (1 - halo * np.clip(cv2.GaussianBlur(m, (0, 0), halo_r) * 3.2, 0, 1))
    t = np.maximum(t, np.clip(m * 1.15, 0, 1))
    b = G.grain(t, g_px, seed, bleed=text_bleed)
    sh, hi = (np.array(c, np.float32) for c in G.TINTS[mode])
    pn = cv2.GaussianBlur(np.random.default_rng(seed + 7).normal(0, 1, (G.H, G.W)).astype(np.float32), (0, 0), 1.0)
    col = (sh[None, None] * (1 - b[..., None]) + hi[None, None] * b[..., None]) * (1 + pn[..., None] * 0.012)
    cv2.imwrite(out, (np.clip(col[..., ::-1], 0, 1) * 255 + .5).astype(np.uint8))


if __name__ == '__main__':
    a = sys.argv
    kw = {}
    for s in a[7:]:
        k, v = s.split('='); kw[k] = float(v)
    render_card(a[1], a[2], a[3], a[4], int(a[5]), int(a[6]), **kw); print('ok', a[3])
