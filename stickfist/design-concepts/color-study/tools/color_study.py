"""Render every style x palette combination at S=1 and build one comparison sheet."""
import os, cv2, numpy as np
import ascii2 as A

F = '../four/'; O = '../colors/'
os.makedirs(O, exist_ok=True)
ROWS = [  # style, art, name, code, mark, cols, tone kwargs, palettes, row label
    ('classic', 'stitch.png', 'Stitch', 'IS001-000012-XW8P', '', 64, dict(black=0.06, white=0.80, gamma=0.7, glow=0.35, pad=0.08), ['bone', 'phosphor', 'amber', 'blood', 'ice'], 'COMMON · classic'),
    ('duo', 'ronin.png', 'Ronin', 'IS006-000041-4G9Y', '', 320, dict(black=0.04, white=0.80, gamma=0.75, glow=0.6, pad=0.06), ['blue', 'magenta', 'acid', 'amber', 'blood'], 'RARE · duotone'),
    ('glitch', 'grimm.png', 'Grimm', 'IS011-000005-YLLU', '/', 560, dict(black=0.05, white=0.85, gamma=0.8, glow=0.6, pad=0.04), ['violet', 'red', 'toxic', 'cyan', 'hot'], 'EPIC · glitch'),
    ('irid', 'reaper.png', 'Reaper', 'IS015-000003-A2JM', '/', 1000, dict(black=0.01, white=0.20, gamma=0.5, shift=330, glow=0.9), ['oil', 'fire', 'toxic', 'aurora', 'candy'], 'LEGENDARY · iridescent'),
]
rows = []
for style, art, name, code, mark, cols, kw, pals, label in ROWS:
    cells = []
    for pn in pals:
        out = f'{O}{style}_{pn}.png'
        A.render(F + art, out, name, code, mark, style, cols, 1, pal=pn, **kw)
        im = cv2.resize(cv2.imread(out), (420, 588), interpolation=cv2.INTER_AREA)
        cv2.putText(im, pn.upper(), (14, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cells.append(im)
    rows.append(np.hstack(cells)); print(label, 'done')
cv2.imwrite('../look/colors_sheet.jpg', np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
print(np.vstack(rows).shape)
