"""PHANTOM: "Vanish". He has already passed through the guard: both daggers opened wide, the cut still glowing,
his afterimages stretched back along the dive, cape streaming up past the name."""
import sys, math, numpy as np
from kit import *
out = sys.argv[1]
c = Canvas(angle=-25, scale=1.10, center=(700, 1150), shift=(215, -215))
FOCUS = (300, 1170)                                    # the guard's chest: where everything points

# ---- the guard, grey, thrown backwards, cut across the chest ----
G = dict(head=(150, 960), neck=(190, 1010), chest=(225, 1130), hip=(290, 1320),
         knee_a=(240, 1500), foot_a=(190, 1690), knee_b=(390, 1480), foot_b=(440, 1670),
         elb_a=(95, 930), hand_a=(40, 820), elb_b=(260, 900), hand_b=(330, 780))
stick(c, G, 32, (104, 104, 110))
# his sword spinning away
blade(c, (330, 780), (470, 600), 11, LIGHT, edge=BLACK)

# ---- the cuts through him ----
crescent(c, [(-60, 1330), (130, 1240), (300, 1170), (520, 1090)], 56, RED, fg=True, peak=0.6, seed=3)
splatter(c, (260, 1170), (-1, -0.35), 70, 15, RED, spread=0.6, reach=640, seed=4)
splatter(c, (260, 1170), (-0.5, 0.85), 26, 11, RED, spread=0.5, reach=420, seed=5)

# ---- Phantom: flying diagonal, daggers wide, cape up ----
P = dict(head=(640, 1090), neck=(720, 1130), chest=(800, 1160), hip=(960, 1190),
         knee_a=(1090, 1110), foot_a=(1240, 1010),       # trailing leg, straight, pointing back up
         knee_b=(1010, 1330), foot_b=(1130, 1440),        # tucked leg
         elb_a=(640, 1230), hand_a=(520, 1330),           # lower arm, dagger low
         elb_b=(640, 1030), hand_b=(520, 960))            # upper arm, dagger high
# afterimages along the dive (to the upper right)
ghost(c, P, 34, [(210, -110), (420, -225), (630, -340)], [LIGHT, (150, 152, 152), (190, 192, 192)])
# the two slash trails behind the daggers, each a long crescent that runs off the card
crescent(c, [(340, 900), (700, 800), (1100, 620), (1560, 470)], 130, RED, fg=True, peak=0.35, seed=7)
crescent(c, [(350, 1500), (700, 1520), (1100, 1470), (1560, 1330)], 105, RED, fg=True, peak=0.3, seed=8)
# the cape: two long ribbons that whip up and back in an S, torn into points
for k, (pts, ws) in enumerate([
        ([(735, 1115), (830, 1000), (870, 860), (800, 720), (840, 560), (980, 430)], [34, 70, 96, 84, 56, 8]),
        ([(740, 1128), (880, 1060), (1010, 930), (1010, 770), (1100, 650), (1230, 600)], [30, 62, 80, 66, 40, 6])]):
    ribbon(c, catmull(pts, 18), ws, BLACK, fg=True)
for (x, y, dx, dy) in [(840, 560, -60, -70), (840, 560, 20, -90), (980, 430, 70, -40), (1100, 650, 60, -50), (1230, 600, 90, -10)]:
    c.poly([(x - 18, y + 10), (x + dx, y + dy), (x + 22, y - 4)], BLACK, True)
stick(c, P, 34, BLACK, fg=True)
blade(c, P['hand_a'], (330, 1430), 15, LIGHT, fg=True, edge=BLACK)
blade(c, P['hand_b'], (330, 900), 15, LIGHT, fg=True, edge=BLACK)

# ---- motion smears behind the dive: a few fat tapered strokes, not hairlines ----
for i, (x0, y0, ln, w) in enumerate([(960, 1370, 520, 16), (1000, 1260, 430, 11), (1060, 1480, 460, 13), (1160, 760, 380, 12), (1120, 880, 300, 8), (1220, 1180, 260, 9)]):
    ribbon(c, [(x0, y0), (x0 + ln * 0.5, y0 - ln * 0.14), (x0 + ln, y0 - ln * 0.28)], [2, w, 2], DARK)
# red droplets that fly past him
splatter(c, (560, 1280), (1, -0.25), 40, 10, RED, spread=0.45, reach=760, seed=9)
shards(c, (280, 1150), 34, 20, BLACK, reach=600, seed=11, bias=math.pi)
shards(c, (280, 1150), 16, 15, RED, reach=500, seed=12, bias=math.pi)

save(c, out); save_mask(c, out.replace('.png', '_fgmask.png'))
fx, fy = c.T(FOCUS); open(out.replace('.png', '_focus.txt'), 'w').write(f'{fx:.0f},{fy:.0f}')
print('frame', out, 'focus', round(fx), round(fy))
