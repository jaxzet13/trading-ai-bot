"""ASCII engine library v3. One picture in, one card out; the ENGINE decides what the characters are and how they are chosen.

  braille  each character is a 2x4 dot cell (8 dots); dots are chosen stochastically -> a grain-print stipple
  edge     characters follow the outlines of the picture (| - / \\) over a sparse brightness fill -> line-art
  blocks   half-block pixels in a few quantised colours, optionally dissolving from smooth (top) to pixel (bottom)
  text     the figure is typeset from its own flavour text, words kept in order across the lit cells

usage (python): render(art, out, name, code, mark, engine, cols, S, pal=, crop=, caption=, ...)
Type strip and glow/grain are shared with ascii2."""
import math
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
import ascii2 as A

W, H, ART_H = A.W, A.H, A.ART_H
FD = '/usr/share/fonts/truetype/dejavu/'
FONTS = {
    'dejavu': FD + 'DejaVuSansMono.ttf', 'dejavu-bold': FD + 'DejaVuSansMono-Bold.ttf',
    'jetbrains': '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf',
    'freemono': '/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf',
}
import os
FDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ascii-engines', 'tools', 'fonts') + os.sep
for k, f in (('vt323', 'VT323'), ('sharetech', 'Share_Tech_Mono'), ('major', 'Major_Mono_Display'), ('spacemono', 'Space_Mono'),
             ('cutive', 'Cutive_Mono'), ('syne', 'Syne_Mono'), ('nova', 'Nova_Mono'), ('anon', 'Anonymous_Pro')):
    FONTS[k] = FDIR + f + '.ttf'


def font_for(name, cw):
    """a font sized so its advance width equals the cell width"""
    path = FONTS.get(name, name)
    adv = ImageFont.truetype(path, 100).getlength('M') / 100.0
    return ImageFont.truetype(path, max(5, int(round(cw / adv)))), adv


def prep(art, crop, pad, shift):
    img = cv2.imread(art)
    if crop:
        hh, ww = img.shape[:2]; x0, y0, x1, y1 = crop
        img = img[int(y0 * hh):int(y1 * hh), int(x0 * ww):int(x1 * ww)]
    if pad > 0:
        ph, pw = int(img.shape[0] * pad), int(img.shape[1] * pad * 0.8)
        img = cv2.copyMakeBorder(img, ph, int(ph * 0.6), pw, pw, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    h0, w0 = img.shape[:2]; k = max(W / w0, ART_H / h0)
    img = cv2.resize(img, (int(round(w0 * k)), int(round(h0 * k))), interpolation=cv2.INTER_AREA)
    x0 = (img.shape[1] - W) // 2; shift = min(int(shift), img.shape[0] - ART_H)
    return img[shift:shift + ART_H, x0:x0 + W]


def tone(g, black, white, gamma):
    return np.clip((g - black) / (white - black), 0, 1) ** gamma


def fade_rows(t, rows, chh, S):
    fr = max(3, int(round(260 * S / chh)))
    return t * (np.clip((rows - np.arange(rows, dtype=np.float32)) / fr, 0, 1) ** 1.4)[:, None]


def cell_colours(style, pal, t):
    return A.colours(style, t, t.shape[0], t.shape[1], pal).astype(np.uint8)


# ------------------------------------------------------------------ engines
def eng_braille(gray, cols, S, style, pal, black, white, gamma, fontname, seed=7, **_):
    cw = W * S / cols; chh = cw * A.ASPECT; rows = int(ART_H * S / chh)
    big = cv2.resize(gray, (cols * 2, rows * 4), interpolation=cv2.INTER_AREA)
    t = tone(big, black, white, gamma)
    rng = np.random.default_rng(seed)
    thr = cv2.GaussianBlur(rng.random(t.shape).astype(np.float32), (0, 0), 0.6)
    thr = (thr - thr.min()) / (thr.max() - thr.min())                                  # stochastic screen: the grain print, as dots
    dots = (t > thr).astype(np.uint8)
    weights = [[1, 8], [2, 16], [4, 32], [64, 128]]                                   # braille bit for (row in cell, col in cell)
    code = np.zeros((rows, cols), np.int32)
    for dy in range(4):
        for dx in range(2): code += dots[dy::4, dx::2][:rows, :cols] * weights[dy][dx]
    cell_t = fade_rows(cv2.resize(t, (cols, rows), interpolation=cv2.INTER_AREA), rows, chh, S)
    code = np.where(cell_t > 0.01, code, 0)
    font, adv = font_for(fontname, cw)
    col = cell_colours(style, pal, np.clip(cell_t * 1.4, 0, 1)).tolist()
    canvas = Image.new('RGB', (W * S, H * S), (4, 4, 5)); d = ImageDraw.Draw(canvas)
    for r in range(rows):
        for c in range(cols):
            if code[r, c]: d.text((c * cw, r * chh), chr(0x2800 + int(code[r, c])), font=font, fill=tuple(col[r][c]))
    return canvas, cols * rows


def eng_edge(gray, cols, S, style, pal, black, white, gamma, fontname, edge_k=0.55, **_):
    cw = W * S / cols; chh = cw * A.ASPECT; rows = int(ART_H * S / chh)
    small = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA)
    t = tone(small, black, white, gamma)
    tb = cv2.GaussianBlur(t, (0, 0), 0.8)
    gx = cv2.Sobel(tb, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(tb, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy); mag /= max(mag.max(), 1e-6)
    ang = (np.degrees(np.arctan2(gy, gx)) + 90) % 180                                 # edge direction, image coords (y down)
    edge_ch = np.where((ang < 22.5) | (ang >= 157.5), '-', np.where(ang < 67.5, '\\\\', np.where(ang < 112.5, '|', '/')))
    edge_ch = np.where(edge_ch == '\\\\', '\\\\', edge_ch)
    fill = " .:-=+*#%@"
    t = fade_rows(t, rows, chh, S); mag = fade_rows(mag, rows, chh, S)
    is_edge = mag > edge_k * 0.5
    font, adv = font_for(fontname, cw)
    col_edge = cell_colours(style, pal, np.clip(0.75 + 0.25 * mag, 0, 1)).tolist()
    col_fill = cell_colours(style, pal, np.clip(t * 0.8, 0, 1)).tolist()
    canvas = Image.new('RGB', (W * S, H * S), (4, 4, 5)); d = ImageDraw.Draw(canvas)
    for r in range(rows):
        for c in range(cols):
            if is_edge[r, c]:
                d.text((c * cw, r * chh), edge_ch[r, c].replace('\\\\', '\\'), font=font, fill=tuple(col_edge[r][c]))
            elif t[r, c] > 0.06:
                ch = fill[min(len(fill) - 1, int(t[r, c] * (len(fill) - 1) + 0.5))]
                if ch != ' ': d.text((c * cw, r * chh), ch, font=font, fill=tuple(int(v * 0.6) for v in col_fill[r][c]))
    return canvas, cols * rows


def eng_blocks(gray, cols, S, style, pal, black, white, gamma, fontname, levels=6, smooth_until=0.0, smooth_band=0.22, **_):
    cw = W * S / cols; chh = cw * A.ASPECT; rows = int(ART_H * S / chh)
    big = cv2.resize(gray, (cols, rows * 2), interpolation=cv2.INTER_AREA)
    t = tone(big, black, white, gamma)
    q = np.round(t * (levels - 1)) / (levels - 1)                                     # a few flat colours: pixel art
    q2 = fade_rows(q[::2][:rows], rows, chh, S), fade_rows(q[1::2][:rows], rows, chh, S)
    ct, cb = (cell_colours(style, pal, np.clip(x * 1.15, 0, 1)) for x in q2)
    canvas = np.zeros((H * S, W * S, 3), np.uint8); canvas[:] = (4, 4, 5)
    for r in range(rows):
        y0, ym, y1 = int(r * chh), int(r * chh + chh / 2), int((r + 1) * chh)
        for c in range(cols):
            x0, x1 = int(c * cw), int((c + 1) * cw)
            if q2[0][r, c] > 0.02: canvas[y0:ym, x0:x1] = ct[r, c]
            if q2[1][r, c] > 0.02: canvas[ym:y1, x0:x1] = cb[r, c]
    if smooth_until > 0:                                                              # smooth at the top, dissolving into blocks
        full = cv2.resize(gray, (W * S, ART_H * S), interpolation=cv2.INTER_CUBIC)
        ts = tone(full, black, white, gamma)
        sm = A.colours(style, ts, ART_H * S, W * S, pal).astype(np.float32) * np.clip(ts * 2.4, 0, 1)[..., None]    # black stays black
        yy = np.arange(ART_H * S, dtype=np.float32) / (ART_H * S)
        w = np.clip((smooth_until + smooth_band - yy) / smooth_band, 0, 1)[:, None, None]
        canvas[:ART_H * S] = (sm * w + canvas[:ART_H * S].astype(np.float32) * (1 - w)).astype(np.uint8)
    return Image.fromarray(canvas), cols * rows


def eng_text(gray, cols, S, style, pal, black, white, gamma, fontname, text='', thr=0.12, **_):
    cw = W * S / cols; chh = cw * A.ASPECT; rows = int(ART_H * S / chh)
    small = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA)
    t = fade_rows(tone(small, black, white, gamma), rows, chh, S)
    font, adv = font_for(fontname, cw)
    phrase = (text.upper() + '   ') or 'X   '
    col = cell_colours(style, pal, np.clip(t * 1.25, 0, 1)).tolist()
    canvas = Image.new('RGB', (W * S, H * S), (4, 4, 5)); d = ImageDraw.Draw(canvas)
    i = 0
    for r in range(rows):
        for c in range(cols):
            if t[r, c] < thr: continue
            ch = phrase[i % len(phrase)]; i += 1                                        # words stay in order across the lit cells
            if ch != ' ': d.text((c * cw, r * chh), ch, font=font, fill=tuple(col[r][c]))
    return canvas, cols * rows


ENGINES = {'braille': eng_braille, 'edge': eng_edge, 'blocks': eng_blocks, 'text': eng_text}


def render(art, out, name, code, mark, engine, cols, S=1, pal='blue', style='duo', crop=None, pad=0.0, shift=0,
           caption='', black=0.05, white=0.85, gamma=0.8, glow=0.5, font='dejavu', typo='line', tint=None, **kw):
    cols, S = int(cols), int(S)
    img = prep(art, crop, pad, shift)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    canvas, count = ENGINES[engine](gray, cols, S, style, pal, black, white, gamma, font, **kw)
    arr = np.asarray(canvas).astype(np.float32) / 255
    sm = cv2.resize(arr, (arr.shape[1] // 4, arr.shape[0] // 4), interpolation=cv2.INTER_AREA)
    gl = cv2.resize(cv2.GaussianBlur(sm, (0, 0), 4 * S) * glow + cv2.GaussianBlur(sm, (0, 0), 0.8 * S) * 0.12, (arr.shape[1], arr.shape[0]))
    arr = np.clip(arr + gl, 0, 1)
    arr[(ART_H + 20) * S:] = np.minimum(arr[(ART_H + 20) * S:], 0.02)
    rng = np.random.default_rng(3)
    arr += cv2.GaussianBlur(rng.normal(0, 1, arr.shape[:2]).astype(np.float32), (0, 0), 0.7 * S)[..., None] * 0.012
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
    if tint is None:
        pn = pal
        if style == 'classic': tint = tuple(int(0.55 * c + 0.45 * 255) for c in A.PALETTES['classic'][pn])
        elif style in ('duo', 'glitch'): tint = tuple(int(0.55 * c + 0.45 * 255) for c in A.PALETTES[style][pn][0])
        else: tint = (236, 231, 220)
    A.draw_type(im, S, name, code, mark, count, tint, typo, caption)
    im.save(out, quality=94) if not out.lower().endswith('.png') else im.save(out)
    return count
