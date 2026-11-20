"""REAPER: "Harvest". One swing, one enormous crescent. Four men are still falling when the card begins."""
import sys, math, numpy as np
from kit import *


def flail(cx, cy, rot, s, color, c, fg=False, w=26):
    base = dict(hip=(0, 0), chest=(0, -45), neck=(0, -92), knee_a=(-26, 62), foot_a=(-50, 126), knee_b=(30, 60), foot_b=(56, 120),
                elb_a=(-48, -102), hand_a=(-72, -152), elb_b=(46, -98), hand_b=(76, -146))
    r = math.radians(rot); ca, sa = math.cos(r), math.sin(r)
    J = {k: (cx + (x * ca - y * sa) * s, cy + (x * sa + y * ca) * s) for k, (x, y) in base.items()}
    stick(c, J, w * s, color, fg=fg)
    return J


out = sys.argv[1]
c = Canvas(angle=-12, scale=1.06, center=(750, 1100), shift=(-30, -240))
FOCUS = (420, 1180)

# the four men, mid-fall, getting darker the further from the blade
flail(250, 1560, 62, 1.55, (116, 116, 120), c)
flail(520, 1000, -118, 1.35, (96, 96, 102), c)
flail(190, 880, 24, 1.2, (150, 150, 152), c)
flail(660, 1650, -54, 1.2, (104, 104, 110), c)

# the cut through them: the whole sweep, a crescent as big as the card
crescent(c, [(1500, 1750), (1280, 1420), (900, 1160), (470, 1090), (-60, 1180)], 210, RED, fg=True, peak=0.42, seed=2)
crescent(c, [(1500, 1520), (1250, 1190), (860, 940), (420, 880), (-60, 940)], 88, RED, fg=True, peak=0.4, seed=3)
splatter(c, (430, 1130), (-1, -0.4), 90, 18, RED, spread=0.8, reach=620, seed=4)
splatter(c, (700, 1020), (0.4, -1), 50, 14, RED, spread=0.8, reach=520, seed=5)

# ---- the reaper: leaning into the follow-through ----
R = dict(head=(990, 1130), neck=(960, 1195), chest=(935, 1290), hip=(900, 1500),
         knee_a=(1010, 1650), foot_a=(1110, 1810), knee_b=(790, 1670), foot_b=(690, 1840),
         elb_a=(850, 1245), hand_a=(745, 1195), elb_b=(880, 1345), hand_b=(790, 1275))
# cloak: tattered, streaming back to the right
for k, (pts, ws) in enumerate([([(965, 1200), (1120, 1210), (1290, 1290), (1470, 1260)], [70, 150, 170, 20]),
                               ([(955, 1300), (1130, 1380), (1300, 1500), (1470, 1560)], [60, 140, 150, 16]),
                               ([(930, 1400), (1060, 1520), (1180, 1650), (1300, 1760)], [50, 110, 110, 12])]):
    ribbon(c, catmull(pts, 16), ws, BLACK, fg=True)
for (x, y, dx, dy) in [(1470, 1260, 70, -40), (1470, 1260, 80, 30), (1470, 1560, 70, -30), (1470, 1560, 60, 50), (1300, 1760, 40, 70)]:
    c.poly([(x - 30, y - 12), (x + dx, y + dy), (x - 24, y + 16)], BLACK, True)
stick(c, R, 36, BLACK, fg=True)
# hood: a long point swept back
c.poly([(940, 1050), (1190, 1115), (1005, 1175), (922, 1150), (916, 1085)], BLACK, True)
# the scythe: shaft through both hands, blade hooked at the far end
S0, S1 = np.array([1010, 1370]), np.array([430, 1010])
ribbon(c, [S0, S1], [20, 15], BLACK, fg=True, caps=(True, True))
blade_pts = [S1 + (-20, 14), S1 + (-120, 80), S1 + (-190, 190), S1 + (-210, 330)]
ribbon(c, catmull([tuple(p) for p in [S1 + (10, -6)] + blade_pts], 14), [40, 60, 54, 30, 2], LIGHT, fg=True)
ribbon(c, catmull([tuple(p) for p in [S1 + (4, -2)] + blade_pts], 14), [18, 26, 20, 10, 1], BLACK, fg=True)

# smears and debris
for (x0, y0, ln, w) in [(1020, 700, 520, 14), (1090, 820, 440, 10), (1180, 1760, 360, 12), (980, 1930, 420, 9)]:
    ribbon(c, [(x0, y0), (x0 + ln * 0.5, y0 + ln * 0.1), (x0 + ln, y0 + ln * 0.2)], [2, w, 2], DARK)
shards(c, (430, 1130), 50, 22, BLACK, reach=640, seed=11, bias=math.pi)
shards(c, (430, 1130), 22, 16, RED, reach=520, seed=12, bias=math.pi)

save(c, out); save_mask(c, out.replace('.png', '_fgmask.png'))
fx, fy = c.T(FOCUS); open(out.replace('.png', '_focus.txt'), 'w').write(f'{fx:.0f},{fy:.0f}')
print('frame', out, 'focus', round(fx), round(fy))
