"""Two-ink print simulation (risograph / screen print).

Splits a flat render into a black plate and a red plate, halftones the flat
greys, gives each plate its own ink texture, knocks the red plate slightly out
of register, and prints both onto paper with multiply. Every value that a real
press gets slightly wrong is seeded by the card's serial, so no two copies match.
"""
import sys, cv2, numpy as np

PAPER = np.array((241, 236, 224), np.float32) / 255
INK_K = np.array((30, 29, 33), np.float32) / 255
INK_R = np.array((200, 32, 40), np.float32) / 255


def smooth_noise(r, h, w, cell):
    n = r.normal(0, 1, (h // cell + 2, w // cell + 2)).astype(np.float32)
    return cv2.resize(n, (w, h), interpolation=cv2.INTER_CUBIC)


def halftone(k, cell=9.0, angle=45):
    h, w = k.shape
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    a = np.deg2rad(angle)
    u = (x * np.cos(a) + y * np.sin(a)) * 2 * np.pi / cell
    v = (-x * np.sin(a) + y * np.cos(a)) * 2 * np.pi / cell
    screen = (np.cos(u) + np.cos(v)) / 4 + .5           # 0..1 dot pattern
    return np.clip((k - (1 - screen)) / .08 + .5, 0, 1)


def plate_texture(cov, r, strength):
    h, w = cov.shape
    density = 1 - strength * (.5 + .5 * np.tanh(smooth_noise(r, h, w, 90)))      # big uneven areas
    speck = (r.random((h, w)) > .992).astype(np.float32)                          # dust specks in solids
    speck = cv2.GaussianBlur(speck, (0, 0), .8) * 1.6
    out = cov * density * (1 - np.clip(speck, 0, 1) * .85)
    return cv2.GaussianBlur(out, (0, 0), .55)                                     # a touch of ink spread


def shift_rot(img, dx, dy, deg):
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    M[:, 2] += (dx, dy)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)


def riso(src, dst, serial):
    r = np.random.default_rng(serial)
    im = cv2.cvtColor(cv2.imread(src), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    red = np.clip(R - np.maximum(G, B), 0, 1)
    k = np.clip(1 - np.maximum(np.maximum(R, G), B), 0, 1)
    # halftone only flat tints, keep glyph edges smooth
    flat = np.abs(k - cv2.blur(k, (7, 7))) < .02
    tone = flat & (k > .03) & (k < .8)
    k = np.where(tone, halftone(k, 9.0, 45), k)
    k = plate_texture(k, r, .10)
    red = plate_texture(red, r, .16)
    # registration: the red plate lands a little off, a different way on every copy
    dx, dy, rot = r.uniform(-5, 5), r.uniform(-4, 4), r.uniform(-.25, .25)
    red = shift_rot(red, dx, dy, rot)
    k = shift_rot(k, r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-.06, .06))
    h, w = k.shape
    paper = PAPER[None, None] * (1 + (smooth_noise(r, h, w, 3) * .012 + smooth_noise(r, h, w, 40) * .01))[..., None]
    out = paper * (1 - k[..., None] * (1 - INK_K)) * (1 - red[..., None] * (1 - INK_R))
    cv2.imwrite(dst, cv2.cvtColor(np.clip(out * 255, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    return dx, dy, rot


if __name__ == '__main__':
    print(riso(sys.argv[1], sys.argv[2], int(sys.argv[3])))
