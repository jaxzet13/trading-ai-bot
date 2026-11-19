"""The Blender card as a physical object: cut corner, blood-red edge, on a black table next to its back."""
import os, numpy as np
D = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(D, 'physical.py')).read().split('# 1. the four tiers')[0]
exec(src)
OUTD = os.path.join(os.path.dirname(D), 'blender-card'); os.makedirs(OUTD, exist_ok=True)
face = load('card_BL.png'); back = load('card_M_back.png')

# hero shot: the card on the table, its back beside it
W, H = 2400, 1700
cam = Cam(el=52, dist=430, f=4300, W=W, H=H, look=(-4, -4, 0))
canvas = table(W, H, .5, .45, .12); L = face_light(W, H)
draw_card(canvas, cam, back, card_mask(['tr'], back=True), RED, 44, 10, 9, 0, .6, light=L)
draw_card(canvas, cam, face, card_mask(['tr']), RED, -30, -4, -5, 0, .6, light=L)
save(f'{OUTD}/2-on-the-table.jpg', canvas)

# flat face with its real shape
m = card_mask(['tr'])[..., None]
save(f'{OUTD}/1-phantom-blender.jpg', face * m + np.array((14, 14, 15), np.float32) / 255 * (1 - m))
print('ok')
