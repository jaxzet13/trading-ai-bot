"""Turns every painting in sources/ into a text card: crops to the card's picture ratio, then ../ascii_cards.py makes the characters (80 columns for the card, 30 for lists)."""
import glob, os, sys
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.normpath(os.path.join(HERE, '..', '..')); sys.path.insert(0, os.path.join(HERE, '..')); import ascii_cards
ids = sys.argv[1:] or [os.path.basename(f)[:-4] for f in sorted(glob.glob(os.path.join(HERE, 'sources', '*.png')))]
for i in ids:
    im = Image.open(os.path.join(HERE, 'sources', i + '.png')).convert('RGB'); w, h = im.size; th = int(w * 1092 / 900); top = max(0, (h - th) // 2)
    im = im.crop((0, top, w, min(h, top + th))).resize((900, 1092), Image.LANCZOS); im.save('/tmp/_p.png')
    ascii_cards.convert('/tmp/_p.png', os.path.join(ROOT, 'cards', i + '.jpg'), 150)
    im.resize((360, 437), Image.LANCZOS).save('/tmp/_t.png'); ascii_cards.convert('/tmp/_t.png', os.path.join(ROOT, 'cards', 's', i + '.jpg'), 54)
print(len(ids), 'cards')
