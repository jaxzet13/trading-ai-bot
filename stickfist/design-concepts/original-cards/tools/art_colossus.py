"""COLOSSUS: "Cave In". The hammer is already coming down; the floor has not noticed yet."""
import sys, math, numpy as np
from kit import *

out = sys.argv[1]
c = Canvas(angle=8, scale=1.0, center=(750, 1050), shift=(0, 0))
FOCUS = (400, 1480)
IMP = np.array(FOCUS, float)

# ---- the ground breaking: jagged cracks radiating from the impact, the first ones already red ----
rnd = np.random.default_rng(5)
for i in range(26):
    a = rnd.uniform(-0.35, math.pi + 0.35) + math.pi * 0.0
    ln = rnd.uniform(380, 1250)
    pts = [IMP + 0]
    cur = IMP.copy(); ang = a
    steps = 6
    for k in range(steps):
        ang += rnd.uniform(-0.4, 0.4); cur = cur + np.array([math.cos(ang), math.sin(ang)]) * ln / steps; pts.append(cur.copy())
    col = RED if i % 3 == 0 else BLACK
    ribbon(c, [tuple(p) for p in pts], [rnd.uniform(26, 44)] + [rnd.uniform(8, 18)] * (steps - 1) + [2], col, fg=(col == RED))
# rubble thrown up
shards(c, tuple(IMP), 110, 34, BLACK, reach=760, seed=3, bias=-math.pi / 2)
shards(c, tuple(IMP), 40, 24, MID, reach=620, seed=4, bias=-math.pi / 2)
splatter(c, tuple(IMP), (0, -1), 60, 16, RED, spread=1.0, reach=560, seed=6)

# ---- the small one at the bottom, arms up, too late ----
T = dict(head=(640, 1660), neck=(655, 1740), chest=(670, 1830), hip=(690, 1960),
         knee_a=(600, 2060), foot_a=(560, 2160), knee_b=(790, 2050), foot_b=(830, 2150),
         elb_a=(590, 1700), hand_a=(560, 1590), elb_b=(740, 1700), hand_b=(790, 1585))
stick(c, T, 20, (96, 96, 102))

# ---- the giant: huge, dark, leaning back for the swing, hammer coming down toward the corner ----
Gj = dict(head=(1015, 470), neck=(1000, 640), chest=(1010, 840), hip=(1050, 1130),
          knee_a=(900, 1330), foot_a=(860, 1580), knee_b=(1190, 1320), foot_b=(1280, 1580),
          elb_a=(870, 590), hand_a=(800, 470), elb_b=(1010, 540), hand_b=(950, 420))
stick(c, Gj, 120, BLACK, head_r=120, fg=True)
# hammer: the handle from the hands down to the head
H0 = np.array([875, 450]); H1 = np.array([480, 1290])
ribbon(c, [H0, H1], [46, 40], BLACK, fg=True, caps=(True, True))
d = (H1 - H0) / np.hypot(*(H1 - H0)); n = np.array([-d[1], d[0]])
hc = H1 + d * 40
quad = [hc - d * 70 + n * 210, hc + d * 190 + n * 220, hc + d * 190 - n * 220, hc - d * 70 - n * 210]
c.poly([tuple(q) for q in quad], BLACK, True)
face = [hc + d * 190 + n * 220, hc + d * 190 - n * 220, hc + d * 120 - n * 170, hc + d * 120 + n * 170]
c.poly([tuple(q) for q in face], (92, 92, 98), True)
# motion: the hammer's path as red arcs behind the swing
crescent(c, [(1400, 280), (1100, 220), (700, 420), (440, 900), (330, 1260)], 120, RED, fg=True, peak=0.5, seed=21)
crescent(c, [(1480, 520), (1180, 420), (860, 560), (600, 960), (470, 1300)], 54, RED, fg=True, peak=0.5, seed=22)
for (x0, y0, ln, w) in [(1150, 1500, 460, 13), (1230, 1650, 380, 10), (60, 400, 420, 11), (170, 560, 340, 8)]:
    ribbon(c, [(x0, y0), (x0 + ln * 0.5, y0 - ln * 0.05), (x0 + ln, y0 - ln * 0.1)], [2, w, 2], DARK)

save(c, out); save_mask(c, out.replace('.png', '_fgmask.png'))
fx, fy = c.T(FOCUS); open(out.replace('.png', '_focus.txt'), 'w').write(f'{fx:.0f},{fy:.0f}')
print('frame', out, 'focus', round(fx), round(fy))
