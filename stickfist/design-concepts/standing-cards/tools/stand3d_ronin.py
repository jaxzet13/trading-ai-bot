"""RONIN: a bare stickman, standing, head low, red headband, both hands on a katana at his hip. Nothing happens."""
import sys, math, random
from toonlib import *

OUT = sys.argv[1]; SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0; SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 24
sc = setup(SCALE, SAMPLES)
CAM = Vector((0.0, -2.45, 0.40)); AIM = Vector((0.0, 0.0, 1.20))
BODY = toon('body', '#2a2b2f', '#4a4b52', rim='#e6e1d6', rim_w=0.32)
BODY_D = toon('body_d', '#1c1c1f', '#323338', rim='#e6e1d6', rim_w=0.28)
RED = toon('red', '#6f0f15', '#b3141c', rim='#ff5a4f', rim_w=0.3)
VOID = flat('void', '#030304')
EYE = flat('eye', '#ff4a3f'); EYEC = flat('eyec', '#fff1ea'); EYEG = flat('eyeg', '#ff3a30', alpha=0.34)
SAYA = toon('saya', '#0d0d0f', '#1f1f23', rim='#e6e1d6', rim_w=0.3)
WRAP = toon('wrap', '#a89f8c', '#e3dccb', rim='#ffffff', rim_w=0.3)
STEELM = toon('steel', '#5e6066', '#ece8df', rim='#ffffff', rim_w=0.35, lit_at=0.45)

street(CAM)
lamp(CAM, (-0.45, 0.0, 2.35), 15.0, r_core=3.5, halo=(4.8, 6.6))

# ---- the stickman: thin, tall, a long head ----
hip, chest, neck = (0, 0, 0.95), (0, 0.0, 1.27), (0, -0.01, 1.56)
ball('head', (0, -0.05, 1.77), 0.185, BODY, line=0.026, scale=(0.95, 1.0, 1.04))
tube('torso', [hip, chest, neck], 0.070, BODY, line=0.02, r_end=0.058)
tube('leg_l', [hip, (-0.19, -0.02, 0.52), (-0.27, -0.05, 0.07)], 0.066, BODY, line=0.02, r_end=0.052)
tube('leg_r', [hip, (0.17, 0.00, 0.52), (0.29, 0.02, 0.07)], 0.066, BODY, line=0.02, r_end=0.052)
ball('foot_l', (-0.30, -0.10, 0.045), 0.06, BODY_D, line=0.016, scale=(1.3, 2.0, 0.7))
ball('foot_r', (0.32, -0.06, 0.045), 0.06, BODY_D, line=0.016, scale=(1.3, 2.0, 0.7))
# shoulders and arms
tube('arm_l', [(-0.07, 0, 1.52), (-0.31, -0.07, 1.22), (-0.17, -0.20, 1.04)], 0.056, BODY, line=0.018, r_end=0.046)
tube('arm_r', [(0.07, 0, 1.52), (0.31, -0.05, 1.22), (0.12, -0.17, 0.96)], 0.056, BODY, line=0.018, r_end=0.046)
ball('hand_l', (-0.17, -0.21, 1.03), 0.052, BODY_D, line=0.015)
ball('hand_r', (0.11, -0.18, 0.95), 0.052, BODY_D, line=0.015)

# ---- katana: sheathed at the hip, left hand on the hilt, right hand on the sheath ----
sa, sb = Vector((-0.16, -0.21, 1.04)), Vector((0.60, -0.10, 0.74))
d = (sb - sa).normalized()
tube('hilt', [tuple(sa - d * 0.22), tuple(sa + d * 0.04)], 0.028, WRAP, line=0.012)
ball('tsuba', tuple(sa + d * 0.06), 0.075, SAYA, line=0.012, scale=(1, 0.18, 1), rot=(0, math.atan2(d.z, d.x) * -1 + math.pi / 2, 0))
tube('saya', [tuple(sa + d * 0.10), tuple(sb)], 0.034, SAYA, line=0.012)
tube('wrap', [tuple(sa + d * 0.16), tuple(sa + d * 0.40)], 0.037, RED, line=0.0)

# ---- headband: a red band round the head, two long tails ----
ribbon3('band', cr([(-0.19, -0.10, 1.84), (0.0, -0.215, 1.86), (0.19, -0.10, 1.84)], 10), [0.065, 0.07, 0.065], RED, line=0.01, thick=0.02)
ribbon3('band_tail1', cr([(0.19, -0.05, 1.85), (0.38, 0.02, 1.78), (0.58, 0.10, 1.84), (0.80, 0.14, 1.77)], 12), [0.06, 0.065, 0.055, 0.008], RED, line=0.01)
ribbon3('band_tail2', cr([(0.19, -0.04, 1.83), (0.36, 0.04, 1.69), (0.50, 0.12, 1.70), (0.68, 0.20, 1.60)], 12), [0.05, 0.055, 0.045, 0.008], RED, line=0.01)
# waist sash
ribbon3('sash', cr([(-0.17, -0.07, 0.97), (0.0, -0.10, 0.95), (0.17, -0.07, 0.97)], 8), [0.05, 0.05, 0.05], RED, line=0.01, thick=0.02)

# ---- face: a dark slot with two red slits ----
ball('face', (0, -0.205, 1.78), 0.145, VOID, line=0.0, scale=(1.0, 0.30, 0.52))
ball('eye_l', (-0.060, -0.229, 1.785), 0.025, EYE, line=0.0, scale=(1.5, 0.4, 0.5), rot=(0, math.radians(-14), math.radians(-10)))
ball('eye_r', (0.060, -0.229, 1.785), 0.025, EYE, line=0.0, scale=(1.5, 0.4, 0.5), rot=(0, math.radians(14), math.radians(10)))
ball('eyeg_l', (-0.060, -0.226, 1.785), 0.05, EYEG, line=0.0, scale=(1.5, 0.3, 0.8)); ball('eyeg_r', (0.060, -0.226, 1.785), 0.05, EYEG, line=0.0, scale=(1.5, 0.3, 0.8))

rain(650, area=(-3.2, 3.2, -3.2, 12, 0, 10))
camera(sc, CAM, AIM, lens=22)
render(sc, OUT); print('ronin3d', OUT)
