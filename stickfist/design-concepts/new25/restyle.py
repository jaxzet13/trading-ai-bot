"""Re-treats the generated illustrations in the looks written down in ../STYLE.md, before they are turned into characters.

The generated pictures came out glossy and evenly lit. The references are the opposite: mostly black, harsh contrast, two or
three tones, coarse grain, the feel of a scan of a print. This script takes each source in sources/ and writes a treated copy
to styled/, which ../commons-redo/render.py then draws.

    python restyle.py            # all
    python restyle.py titan mars
"""
import os, sys, zlib
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.join(HERE, 'sources'); OUT = os.path.join(HERE, 'styled')

def load(name):
    im = cv2.cvtColor(cv2.imread(os.path.join(SRC, name + '.png'), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    return cv2.resize(im, (1024, 1536), interpolation=cv2.INTER_AREA)
def lum(im): return (im[..., 0] * .30 + im[..., 1] * .59 + im[..., 2] * .11)
def levels(l, lo, hi, g=1.0): return np.clip((l - lo) / max(1e-6, hi - lo), 0, 1) ** g
def noise(shape, cell, seed):
    """grain the size of a few pixels: fine noise is averaged away when the picture becomes characters, so it is made coarse"""
    r = np.random.default_rng(seed); h, w = shape; n = r.random((h // cell + 1, w // cell + 1)).astype(np.float32)
    return cv2.resize(n, (w, h), interpolation=cv2.INTER_NEAREST)
def speckle(l, cell, seed, soft=.0):
    """a stochastic two-tone: each grain is on or off, more of them on where the picture is brighter (a photocopy, a stipple)"""
    n = noise(l.shape, cell, seed); return np.clip((l - n) / max(1e-3, soft) + .5, 0, 1) if soft else (l > n).astype(np.float32)
def bloom(l, sigma, k): return np.clip(l + cv2.GaussianBlur(np.clip(l - .6, 0, 1), (0, 0), sigma) * k, 0, 1)
def ramp(l, stops):
    """luminance to colour through a list of (position, (r, g, b)) stops"""
    out = np.zeros(l.shape + (3,), np.float32)
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        m = (l >= p0) & (l <= p1); t = ((l - p0) / max(1e-6, p1 - p0))[..., None]; out = np.where(m[..., None], np.array(c0, np.float32) * (1 - t) + np.array(c1, np.float32) * t, out)
    return out
def vignette(h, w, k):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32); return 1 - k * (((xx / w - .5) / .5) ** 2 + ((yy / h - .5) / .5) ** 2)
BONE = (0.96, 0.93, 0.85)

def colossus(im, s):      # 8, the photocopied engraving: black and bone, heavy speckle, the shaft of light burned out
    l = levels(lum(im), .10, .72, 1.25) * np.clip(vignette(*im.shape[:2], .55), 0, 1); t = speckle(bloom(l, 18, .5), 3, s, .28)
    return t[..., None] * np.array(BONE, np.float32)
def leviathan(im, s):     # 10, the blown-out duotone: deep blue and white, the whale's light burned to white, coarse grain
    l = bloom(levels(lum(im), .06, .62, 1.15), 22, 1.1); l = np.clip(l + (noise(l.shape, 2, s) - .5) * .26 * (.3 + l), 0, 1)
    return ramp(l, [(0, (0, 0, .02)), (.22, (.03, .07, .26)), (.55, (.16, .30, .66)), (.8, (.72, .82, .98)), (1, (1, 1, .97))])
def titan(im, s):         # 7, the stippled statue: almost lost in black, picked out in white grain along its lit edges
    l = levels(lum(im), .12, .66, 1.3) * np.clip(vignette(*im.shape[:2], .6), 0, 1); return (speckle(l, 2, s, .3) * (.7 + .3 * l))[..., None] * np.array((.93, .95, 1.0), np.float32)
def console(im, s):       # 4, the pixelled cosmos: blue and white on black, breaking into coarse pixels towards the bottom
    l = levels(lum(im), .08, .70, 1.2); h, w = l.shape; out = l.copy()
    for y0, cell in ((int(h * .52), 10), (int(h * .68), 18), (int(h * .82), 30)):
        part = l[y0:]; small = cv2.resize(part, (max(1, w // cell), max(1, part.shape[0] // cell)), interpolation=cv2.INTER_AREA); out[y0:] = cv2.resize(small, (w, part.shape[0]), interpolation=cv2.INTER_NEAREST)
    out = np.clip(out + (noise(l.shape, 2, s) - .5) * .12, 0, 1)
    return ramp(bloom(out, 14, .5), [(0, (0, 0, .03)), (.3, (.04, .14, .46)), (.62, (.25, .55, .95)), (.85, (.80, .92, 1)), (1, (1, 1, 1))])
def suit(im, s):          # 3, the screenprint collage: cream on black posterised hard, indigo in the half-tones, paper grain
    l = levels(lum(cv2.GaussianBlur(im, (0, 0), 1.2)), .10, .66, 1.0); hi = (l > .58).astype(np.float32); mid = ((l > .24) & (l <= .58)).astype(np.float32)
    lines = (np.sin(np.mgrid[0:l.shape[0], 0:l.shape[1]][0] * .55) > .2).astype(np.float32)                       # the half-tone is ruled, like the fine lines of the reference
    out = hi[..., None] * np.array((.97, .93, .84), np.float32) + (mid * lines)[..., None] * np.array((.36, .30, .78), np.float32)
    return np.clip(out * (.9 + .2 * noise(l.shape, 2, s))[..., None], 0, 1)
def mars(im, s):          # 9 and 5: sand grain and chalky paint, black to rust to bone, most of the frame left dark
    l = levels(lum(im), .07, .58, 1.05) * np.clip(vignette(*im.shape[:2], .5), 0, 1); g = speckle(l, 2, s, .5)
    return ramp(np.clip(g * (.55 + .6 * l), 0, 1), [(0, (.02, 0, 0)), (.35, (.42, .11, .05)), (.7, (.88, .42, .20)), (1, (1, .93, .82))])
def horizon(im, s):       # 2, the oil-slick glitch: grey and black, with a rainbow smear along the bright edges and tape lines
    l = levels(lum(im), .08, .78, 1.2); h, w = l.shape; gx = cv2.Sobel(l, cv2.CV_32F, 1, 0, ksize=5); gy = cv2.Sobel(l, cv2.CV_32F, 0, 1, ksize=5)
    edge = np.clip(cv2.GaussianBlur(np.hypot(gx, gy), (0, 0), 4) / 2.6, 0, 1); yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    hue = ((np.arctan2(gy, gx) / 6.2832 + xx / w * .9 + yy / h * .6 + l * .8) % 1.0)
    hsv = np.stack([hue * 179, np.full_like(hue, 235), np.full_like(hue, 255)], 2).astype(np.uint8); rain = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).astype(np.float32) / 255
    grey = (l * .78)[..., None] * np.array((.92, .92, .95), np.float32); out = grey * (1 - edge[..., None] * .7) + rain * (edge * (.55 + .45 * l))[..., None]
    for y0 in np.random.default_rng(s).integers(0, h - 40, 14): dx = int(np.random.default_rng(s + int(y0)).integers(-46, 47)); hh = int(np.random.default_rng(s + 7 + int(y0)).integers(6, 34)); out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], dx, axis=1)   # the tape slipping
    out = out * (.86 + .14 * (np.arange(h) % 6 < 3))[:, None, None]; return np.clip(out + (noise(l.shape, 2, s)[..., None] - .5) * .10, 0, 1)

LOOKS = dict(colossus=colossus, leviathan=leviathan, titan=titan, console=console, suit=suit, mars=mars, horizon=horizon)
if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for name in (sys.argv[1:] or list(LOOKS)):
        out = LOOKS[name](load(name), zlib.crc32(name.encode())); cv2.imwrite(os.path.join(OUT, name + '.png'), cv2.cvtColor((np.clip(out, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)); print(name)
