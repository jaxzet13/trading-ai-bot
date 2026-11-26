"""Every card picture -> a card made of characters, in the Ronin look (ronin_render.py). Sources: sources/<id>.png (painted), orig/<id>.jpg (the first illustrated cards),
../stick-cards/sources/<id>.png (code-drawn stand-ins for cards that are not painted yet). A painted card wins over a stand-in.
    python3 convert.py            # all
    python3 convert.py ms078 ...  # some"""
import glob, os, sys
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, '..', '..')); sys.path.insert(0, HERE); from ronin_render import render
def src(i):
    for p in (os.path.join(HERE, 'sources', i + '.png'), os.path.join(HERE, 'orig', i + '.jpg'), os.path.join(HERE, '..', 'stick-cards', 'sources', i + '.png')):
        if os.path.exists(p): return p
ids = sys.argv[1:] or sorted({os.path.basename(f)[:-4] for d, e in (('sources', 'png'), ('orig', 'jpg')) for f in glob.glob(os.path.join(HERE, d, '*.' + e))} | {os.path.basename(f)[:-4] for f in glob.glob(os.path.join(HERE, '..', 'stick-cards', 'sources', '*.png'))})
for i in ids:
    p = src(i)
    if not p: continue
    render(p, os.path.join(ROOT, 'cards', i + '.jpg'), 96)
    im = Image.open(os.path.join(HERE, 'sources' if p.endswith('.png') and 'stick-cards' not in p else '.', '')) if False else None
    render(p, os.path.join(ROOT, 'cards', 's', i + '.jpg'), 44, W=360, H=437, maxb=90 * 1024)
print(len(ids), 'cards')
