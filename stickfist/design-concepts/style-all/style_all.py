"""STIXX style variants for EVERY card: the card's own art re-rendered as ASCII in the 12 chance styles.

style_deck.py (../style-deck/tools) made the 12 styles for Stitch from one source image. This script generalises it:
the 12 style definitions below are copied from its STYLES list unchanged (same engine, palette, ramp and glow for every card),
and each card brings its own source image, framing (crop / pad / thick), grid, caption and optional per-card tone.

For each card it writes  <out>/<card>-<key>.jpg  (900 x 1092, JPEG, the PICTURE AREA only, no name / id / frame):
    render the full 1500 x 2100 card with ascii2 / ascii3  ->  crop the top 1820 rows  ->  cv2.resize(900, 1092, INTER_AREA)
(the same crop umbra/umbra_final.py does). The default look <card>.jpg is never written.

Every style of a card uses the SAME grid (cols x rows), so every style prints exactly the card's character count.
Cards 3-5 (orbit, null, shogun) were drawn on a taller cell (aspect 2.0) than ascii2's default 1.73; that is what makes their
7,260 / 29,260 / 31,970 add up, so the variants use the same cell shape.

NOTE: the ten COMMONS (stitch, brick, rook, mop, pan, cone, fuse, spark, flare, bubble) and PHANTOM are no longer drawn here. Every look of those
cards, the plain one included, comes from ../commons-redo/render.py (more characters, fitted to the shape, colour, a lit backdrop).
Running this script for a common would put the old, sparse look back.

usage:
    python style_all.py                          # all 10 cards x 12 styles into ../../cards   (a few minutes for the small ones,
                                                 #  reaper and umbra take a long time: 0.7M and 1.6M characters per image)
    python style_all.py --cards phantom,null     # some cards
    python style_all.py --styles steel,kin       # some styles (keys)
    python style_all.py --out /tmp/x --tmp /tmp/y --jobs 4 --quality 80
    python style_all.py --list                   # show the cards, grids and source art
"""
import argparse, os, sys, time, json
import numpy as np, cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DC = os.path.normpath(os.path.join(HERE, '..'))                       # design-concepts/
sys.path.insert(0, os.path.join(DC, 'style-deck', 'tools'))           # ascii2.py (ramp engine) and ascii3.py (braille / edge / blocks / text)
import ascii2 as A, ascii3 as E

W, H, ART_H = A.W, A.H, A.ART_H
PIC_W, PIC_H = 900, 1092                                              # the picture area the app loads

# ---------------------------------------------------------------------------------------------------------------- styles
# key (the app's FX key), display name, engine, how to render. Identical to style_deck.STYLES except 'cols' (comes from the card)
# and the Typeset text (comes from the card). Chance / value columns are not needed here.
STYLES = [
    ('steel',   'Phosphor',     'ramp',    dict(style='classic', pal='phosphor', black=0.06, white=0.80, gamma=0.7, glow=0.35)),
    ('dots',    'Amber',        'ramp',    dict(style='classic', pal='amber', black=0.06, white=0.80, gamma=0.7, glow=0.35)),
    ('vhs',     'Glitch',       'ramp',    dict(style='glitch', pal='violet', black=0.05, white=0.85, gamma=0.8, glow=0.6)),
    ('scratch', 'Typeset',      'text',    dict(style='classic', pal='bone', font='spacemono', black=0.18, white=0.90, gamma=0.8, thr=0.16, glow=0.5)),
    ('ice',     'Stipple',      'braille', dict(style='duo', pal='blue', font='dejavu', black=0.05, white=0.60, gamma=0.55, glow=0.8)),
    ('chain',   'Linework',     'edge',    dict(style='classic', pal='bone', font='jetbrains', black=0.05, white=0.80, gamma=0.7, glow=0.6)),
    ('wire',    'Pixel',        'blocks',  dict(style='duo', pal='acid', black=0.06, white=0.85, gamma=0.8, glow=0.5)),
    ('print',   'Blood',        'ramp',    dict(style='classic', pal='blood', black=0.06, white=0.80, gamma=0.7, glow=0.5)),
    ('glass',   'Glow',         'ramp',    dict(style='duo', pal='magenta', black=0.05, white=0.75, gamma=0.7, glow=0.8)),
    ('blood',   'Toxic Glitch', 'ramp',    dict(style='glitch', pal='toxic', black=0.05, white=0.85, gamma=0.8, glow=0.6)),
    ('leaf',    'Iridescent',   'ramp',    dict(style='irid', pal='oil', black=0.06, white=0.90, gamma=0.8, glow=0.8)),
    ('kin',     'Dissolve',     'blocks',  dict(style='duo', pal='blue', smooth_until=0.46, smooth_band=0.28, black=0.05, white=0.85, gamma=0.8, glow=0.6)),
]
STYLE_KEYS = [s[0] for s in STYLES]

# ---------------------------------------------------------------------------------------------------------------- cards
# count / cols / aspect: the grid of the card's default look (cols x rows = count, rows = int(1820 / (1500 / cols * aspect))).
# src: its own base image (relative to design-concepts/). Framing, either of
#   view = (cx, cy, vh): the card shows the source centred on (cx, cy) with vh = the fraction of the source HEIGHT that is visible
#          (the card is 1500 x 1820, so the width follows; anything outside the source is black). Fitted to the default card.
#   crop = (x0, y0, x1, y1) as fractions of the source and pad = black margin (ascii2's own options, used by brick / rook / umbra).
# thick = ascii2's stroke thickener (<0 fattens dark strokes, >0 bright ones). text = the Typeset line.
# tone = black / white / gamma overrides for every style of the card (except the keys in tone_except); over = per-style overrides.
CARDS = {
    'brick':   dict(src='funny-commons/sources/brick.png', count=2816, cols=64, aspect=1.73, crop=(0.01, 0, 0.99, 0.99), text='it is a colander. it works.'),
    'rook':    dict(src='funny-commons/sources/rook.png', count=2816, cols=64, aspect=1.73, crop=(0.01, 0, 1, 0.99), text='reach: floppy.'),
    'orbit':   dict(src='ascii-engines/sources/galaxy.png', count=7260, cols=110, aspect=2.0, view=(0.5, 0.37, 0.74), text='already read the ending.',
                    tone=dict(black=0.02, white=0.5, gamma=0.55), tone_except=('kin', 'wire', 'ice')),
    'phantom': dict(src='ascii-engines/sources/winged.png', count=15750, cols=150, aspect=1.73, view=(0.5, 0.42, 0.82), text='gone before the cape lands.',
                    tone=dict(black=0.01, white=0.34, gamma=0.5, thick=3), tone_except=('kin', 'wire', 'ice', 'chain', 'scratch'),
                    over=dict(scratch=dict(black=0.05, white=0.4, gamma=0.6, thr=0.2))),
    'null':    dict(src='ascii-engines/sources/star.png', count=29260, cols=220, aspect=2.0, view=(0.5, 0.38, 0.86), text='not on any record.'),
    'shogun':  dict(src='ascii-engines/sources/wings.png', count=31970, cols=230, aspect=2.0, view=(0.5, 0.40, 0.80), text='rents you the air.',
                    tone=dict(black=0.5, white=0.95), over=dict(chain=dict(white=1.2, gamma=1.0))),
    'ronin':   dict(src='stick-figures-four/sources/2-rare-ronin-71680.png', count=71680, cols=320, aspect=1.73, view=(0.43, 0.33, 0.47), text='no master. no map.',
                    tone=dict(black=0.03, white=0.42, gamma=0.6), tone_except=('kin', 'wire', 'ice', 'scratch'),
                    over=dict(wire=dict(black=0.08, white=1.0, gamma=1.1), scratch=dict(black=0.12, white=0.7, gamma=0.8, thr=0.22))),
    'grimm':   dict(src='stick-figures-four/sources/3-epic-grimm-219520.png', count=219520, cols=560, aspect=1.73, view=(0.50, 0.59, 0.62), text='the walls remember.',
                    tone=dict(black=0.03, white=0.65, gamma=0.68), tone_except=('kin', 'wire', 'ice', 'scratch', 'vhs', 'blood', 'leaf'),
                    over=dict(wire=dict(black=0.10, white=1.0, gamma=1.1), chain=dict(white=0.5, gamma=0.6, edge_k=0.22))),
    'reaper':  dict(src='stick-figures-four/sources/4-legendary-reaper-701000.png', count=701000, cols=1000, aspect=1.73, view=(0.50, 0.50, 0.33), text='still warm.',
                    tone=dict(black=0.08, white=1.0, gamma=1.0), tone_except=('wire', 'scratch'),
                    over=dict(wire=dict(black=0.12, white=1.0, gamma=1.3), scratch=dict(black=0.25, white=1.0, gamma=1.0, thr=0.25), chain=dict(white=1.3))),
    'umbra':   dict(src='umbra/eclipse.png', count=1578000, cols=1500, aspect=1.73, crop=(0.07, 0.05, 0.93, 0.985), text='the sun blinked first.'),
    # ---- Moonshot (the second pack): one launch, five altitudes. `default` is the card's own plain look: (engine, ascii2 / ascii3 arguments).
    'fuse':     dict(src='moonshot/sources/fuse.jpg', count=3600, cols=72, aspect=1.73, view=(0.5, 0.42, 0.85), text='light it and walk away.',
                     default=('ramp', dict(style='classic', pal='amber', black=0.05, white=0.85, gamma=0.8, glow=0.45))),
    'ignition': dict(src='moonshot/sources/ignition.jpg', count=10080, cols=120, aspect=1.73, view=(0.5, 0.46, 0.9), reflect=0.16, text='no turning back from here.',
                     default=('ramp', dict(style='duo', pal='amber', black=0.06, white=0.90, gamma=0.9, glow=0.7))),
    'liftoff':  dict(src='moonshot/sources/liftoff.jpg', count=40320, cols=240, aspect=1.73, view=(0.5, 0.46, 0.9), reflect=0.16, text='gravity lost the argument.',
                     default=('ramp', dict(style='duo', pal='blood', black=0.06, white=0.90, gamma=0.9, glow=0.7))),
    'apogee':   dict(src='moonshot/sources/apogee.jpg', count=123480, cols=420, aspect=1.73, view=(0.5, 0.46, 0.9), text='the top is quiet.',
                     default=('ramp', dict(style='duo', pal='blue', black=0.05, white=0.90, gamma=0.85, glow=0.7))),
    'luna':     dict(src='moonshot/sources/luna.jpg', count=448800, cols=800, aspect=1.73, view=(0.5, 0.44, 0.80), text='to the moon was never a joke.',
                     default=('ramp', dict(style='irid', pal='moon', black=0.05, white=0.90, gamma=0.8, glow=0.8))),
    # ---- more cards for both packs (sources in ../more-cards/sources): three more commons, two uncommons and a rare for First Print, three for Moonshot
    'mop':       dict(src='more-cards/sources/mop.jpg', count=2816, cols=64, aspect=1.73, view=(0.5, 0.5, 1.05), text='swab the deck.',
                      default=('ramp', dict(style='classic', pal='phosphor', black=0.06, white=0.80, gamma=0.7, glow=0.35))),
    'pan':       dict(src='more-cards/sources/pan.jpg', count=2816, cols=64, aspect=1.73, view=(0.5, 0.5, 0.97), text="it's a frying pan. it counts.",
                      default=('ramp', dict(style='classic', pal='bone', black=0.06, white=0.80, gamma=0.7, glow=0.35))),
    'cone':      dict(src='more-cards/sources/cone.jpg', count=2816, cols=64, aspect=1.73, view=(0.5, 0.5, 0.97), text='caution: confident.',
                      default=('ramp', dict(style='duo', pal='amber', black=0.06, white=0.85, gamma=0.8, glow=0.5))),
    'tempest':   dict(src='more-cards/sources/tempest.jpg', count=7260, cols=110, aspect=2.0, view=(0.5, 0.5, 0.97), text='weather is a choice.',
                      tone=dict(black=0.02, white=0.5, gamma=0.55), tone_except=('kin', 'wire', 'ice'),
                      default=('ramp', dict(style='duo', pal='blue', black=0.02, white=0.55, gamma=0.6, glow=0.8))),
    'surge':     dict(src='more-cards/sources/surge.jpg', count=15750, cols=150, aspect=1.73, view=(0.5, 0.5, 0.97), text='ride it before it breaks.',
                      tone=dict(black=0.02, white=0.55, gamma=0.6), tone_except=('kin', 'wire', 'ice', 'scratch'),
                      default=('ramp', dict(style='classic', pal='ice', black=0.02, white=0.6, gamma=0.65, glow=0.8))),
    'kraken':    dict(src='more-cards/sources/kraken.jpg', count=28000, cols=200, aspect=1.73, view=(0.5, 0.5, 0.97), text='it was always down there.',
                      tone=dict(black=0.02, white=0.6, gamma=0.6), tone_except=('kin', 'wire', 'ice', 'scratch'),
                      default=('ramp', dict(style='irid', pal='aurora', black=0.02, white=0.7, gamma=0.7, glow=0.8))),
    'spark':     dict(src='more-cards/sources/spark.jpg', count=3600, cols=72, aspect=1.73, view=(0.5, 0.5, 0.97), text='small things start fires.',
                      default=('ramp', dict(style='duo', pal='amber', black=0.06, white=0.85, gamma=0.8, glow=0.6))),
    'countdown': dict(src='more-cards/sources/countdown.jpg', count=10080, cols=120, aspect=1.73, view=(0.5, 0.5, 0.97), text='three. two. one.',
                      default=('ramp', dict(style='classic', pal='phosphor', black=0.06, white=0.85, gamma=0.8, glow=0.7))),
    'booster':   dict(src='more-cards/sources/booster.jpg', count=40320, cols=240, aspect=1.73, view=(0.5, 0.5, 0.97), text='dead weight, dropped.',
                      default=('ramp', dict(style='duo', pal='amber', black=0.06, white=0.90, gamma=0.85, glow=0.7))),
    'flare':     dict(src='more-cards/sources/flare.jpg', count=3600, cols=72, aspect=1.73, view=(0.5, 0.5, 1.0), text='the sky has been told.',
                      default=('ramp', dict(style='duo', pal='blood', black=0.06, white=0.85, gamma=0.8, glow=0.6))),
    'bubble':    dict(src='more-cards/sources/bubble.jpg', count=3600, cols=72, aspect=1.73, view=(0.5, 0.5, 1.0), text='all systems: smiling.',
                      default=('ramp', dict(style='classic', pal='bone', black=0.06, white=0.85, gamma=0.8, glow=0.5))),
    'gantry':    dict(src='more-cards/sources/gantry.jpg', count=10080, cols=120, aspect=1.73, view=(0.5, 0.5, 1.0), text='the arm lets go.',
                      default=('ramp', dict(style='classic', pal='ice', black=0.04, white=0.8, gamma=0.7, glow=0.6))),
}
HEAVY_FIRST = ['umbra', 'reaper', 'luna', 'grimm', 'apogee', 'ronin', 'shogun', 'liftoff', 'booster', 'null', 'kraken', 'phantom', 'surge', 'orbit', 'tempest', 'ignition', 'countdown', 'rook', 'brick', 'fuse', 'mop', 'pan', 'cone', 'spark', 'flare', 'bubble', 'gantry']


def grid(cfg):
    """(cols, rows) for a card at S=1 with its cell aspect; rows is what ascii2 / ascii3 compute"""
    cw = W / cfg['cols']; chh = cw * cfg['aspect']
    return cfg['cols'], int(ART_H / chh)


def style_args(cfg, key):
    """the style's render arguments for this card (style_deck's, with the card's tone / per-style tweaks on top)"""
    if key == 'default': return dict(cfg['default'][1])                 # a new card's own plain look
    kw = dict(dict((k, kw) for k, _, _, kw in STYLES)[key])
    if key not in cfg.get('tone_except', ()): kw.update(cfg.get('tone', {}))
    kw.update(cfg.get('over', {}).get(key, {}))
    return kw


# ---------------------------------------------------------------------------------------------------------------- rendering
class _CapFont:
    """ascii2's ramp engine sizes its font as 0.92 x the cell height, which is right for a 1.73 cell. On the taller 2.0 cell the
    glyphs would overlap sideways, so cap the font so one advance (0.6 em for JetBrains Mono) fits the cell width."""
    def __init__(self, real, cap): self.real, self.cap = real, cap
    def truetype(self, path, size, *a, **k): return self.real.truetype(path, min(int(size), self.cap), *a, **k)
    def __getattr__(self, n): return getattr(self.real, n)


_prep0 = E.prep
_THICK = [0]
def _prep_thick(art, crop, pad, shift):
    """E.prep plus ascii2's `thick` option, so the braille / edge / blocks / text engines can fatten a thin figure too"""
    img = _prep0(art, crop, pad, shift)
    if _THICK[0]:
        kk = int(abs(_THICK[0])) | 1; ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kk, kk))
        img = cv2.dilate(img, ker) if _THICK[0] > 0 else cv2.erode(img, ker)
    return img
E.prep = _prep_thick


def place_source(cfg, png):
    """cfg['view'] -> a 1500 x 1820 PNG of exactly what the card's picture area shows (black outside the source)"""
    img = cv2.imread(os.path.join(DC, cfg['src']))
    if cfg.get('reflect'): k = int(img.shape[1] * cfg['reflect']); img = cv2.copyMakeBorder(img, 0, 0, k, k, cv2.BORDER_REFLECT_101)   # a source narrower than the card: carry its edge (smoke, sky) on sideways instead of stopping at a line
    H0, W0 = img.shape[:2]
    cx, cy, vh = cfg['view']; scale = ART_H / (vh * H0)
    s = cv2.resize(img, (int(round(W0 * scale)), int(round(H0 * scale))), interpolation=cv2.INTER_AREA)
    ox = int(round(W / 2 - cx * s.shape[1])); oy = int(round(ART_H / 2 - cy * s.shape[0]))
    canvas = np.zeros((ART_H, W, 3), np.uint8)
    sx, sy, dx, dy = max(0, -ox), max(0, -oy), max(0, ox), max(0, oy)
    w, h = min(s.shape[1] - sx, W - dx), min(s.shape[0] - sy, ART_H - dy)
    canvas[dy:dy + h, dx:dx + w] = s[sy:sy + h, sx:sx + w]
    cv2.imwrite(png, canvas)


def render_full(card_id, key, out_png):
    """render one style of one card as the full 1500 x 2100 card; returns the printed character count"""
    cfg = CARDS[card_id]; kw = style_args(cfg, key)
    kind = cfg['default'][0] if key == 'default' else dict((k, e) for k, _, e, _ in STYLES)[key]
    cols, rows = grid(cfg)
    A.ASPECT = cfg['aspect']
    if cfg['aspect'] > 1.8: A.ImageFont = _CapFont(A.ImageFont if not isinstance(A.ImageFont, _CapFont) else A.ImageFont.real, int(W / cols / 0.6))
    art = os.path.join(DC, cfg['src']); crop, pad = cfg.get('crop'), cfg.get('pad', 0.0)
    if 'view' in cfg:
        art = out_png[:-4] + '-src.png'; place_source(cfg, art); crop, pad = None, 0.0
    thick = kw.pop('thick', cfg.get('thick', 0)); _THICK[0] = thick
    name = card_id.title(); code = 'IS000-000000-XXXX'; cap = cfg['text']
    if kind == 'ramp':
        style = kw.pop('style')
        n = A.render(art, out_png, name, code, '', style, cols, 1, crop=crop, pad=pad, caption=cap, typo='line', thick=thick, shift=cfg.get('shift', 0), **kw)
    else:
        if kind == 'text': kw['text'] = cap
        n = E.render(art, out_png, name, code, '', kind, cols, 1, crop=crop, pad=pad, caption=cap, shift=cfg.get('shift', 0), **kw)
    assert n == cfg['count'], f'{card_id}: grid prints {n:,}, the card prints {cfg["count"]:,}'
    return n


def to_picture(png, out_jpg, quality=80, max_kb=170, floor=56):
    """crop the picture area (top 1820 rows), 900 x 1092 with INTER_AREA, JPEG; step the quality down only if the file passes max_kb"""
    im = cv2.imread(png)[:ART_H]
    im = cv2.resize(im, (PIC_W, PIC_H), interpolation=cv2.INTER_AREA)
    rgb = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)); q = quality
    while True:
        rgb.save(out_jpg, quality=q, optimize=True, subsampling=2)
        kb = os.path.getsize(out_jpg) / 1024
        if kb <= max_kb or q <= floor: return q, kb
        q -= 3


def job(args):
    card_id, key, out_dir, tmp, quality, max_kb = args
    t0 = time.time(); png = os.path.join(tmp, f'{card_id}-{key}.png'); jpg = os.path.join(out_dir, f'{card_id}.jpg' if key == 'default' else f'{card_id}-{key}.jpg')
    n = render_full(card_id, key, png)
    q, kb = to_picture(png, jpg, quality, max_kb)
    for f in (png, png[:-4] + '-src.png'):
        if os.path.exists(f): os.remove(f)
    return card_id, key, n, q, kb, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cards', default=','.join(CARDS)); ap.add_argument('--styles', default=','.join(STYLE_KEYS))
    ap.add_argument('--out', default=os.path.normpath(os.path.join(DC, '..', 'cards'))); ap.add_argument('--tmp', default='/tmp/style-all')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 0)); ap.add_argument('--quality', type=int, default=80)
    ap.add_argument('--max-kb', type=float, default=170); ap.add_argument('--list', action='store_true'); ap.add_argument('--default', action='store_true', help="also render each card's own plain look (cards that define `default`)"); ap.add_argument('--only-default', action='store_true')
    a = ap.parse_args()
    cards = [c for c in HEAVY_FIRST if c in a.cards.split(',')]; styles = [s for s in STYLE_KEYS if s in a.styles.split(',')]
    if a.list:
        for c in HEAVY_FIRST:
            cfg = CARDS[c]; cols, rows = grid(cfg)
            print(f'{c:8s} {cols:5d} x {rows:<5d} = {cols * rows:>9,}  aspect {cfg["aspect"]}  {cfg["src"]}')
        return
    os.makedirs(a.out, exist_ok=True); os.makedirs(a.tmp, exist_ok=True)
    if a.only_default: styles = []
    tasks = [(c, s, a.out, a.tmp, a.quality, a.max_kb) for c in cards for s in styles]
    if a.default or a.only_default: tasks += [(c, 'default', a.out, a.tmp, a.quality, a.max_kb) for c in cards if 'default' in CARDS[c]]
    print(f'{len(tasks)} images -> {a.out}', flush=True)
    from concurrent.futures import ProcessPoolExecutor, as_completed
    log = []
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(job, t) for t in tasks]
        for f in as_completed(futs):
            c, k, n, q, kb, dt = f.result(); log.append(dict(card=c, key=k, chars=n, quality=q, kb=round(kb, 1), seconds=round(dt, 1)))
            print(f'{c}-{k}.jpg  {n:,} chars  q{q}  {kb:.0f} KB  {dt:.0f}s', flush=True)
    json.dump(sorted(log, key=lambda r: (r['card'], r['key'])), open(os.path.join(a.tmp, 'style_all_log.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
