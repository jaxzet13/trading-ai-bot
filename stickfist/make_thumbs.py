"""Makes cards/s/: a 360 px wide copy of every card picture, for lists, grids and thumbnails (the full pictures are for the pack opening and the card window).
    python3 make_thumbs.py"""
from PIL import Image
import glob, os
os.makedirs("cards/s", exist_ok=True)
for f in sorted(glob.glob("cards/*.jpg")):
    im = Image.open(f).convert("RGB"); w, h = im.size
    im.resize((360, round(h * 360 / w)), Image.LANCZOS).save("cards/s/" + os.path.basename(f), quality=82, optimize=True, progressive=True)
print("done")
