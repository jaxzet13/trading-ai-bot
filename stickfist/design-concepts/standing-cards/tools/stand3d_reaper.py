"""REAPER: standing in the street in the rain. Hood, long torn robe, red sash, scythe planted beside him. Nothing happens."""
import sys, math, random
from toonlib import *

OUT = sys.argv[1]; SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0; SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 24
sc = setup(SCALE, SAMPLES)
CAM = Vector((0.0, -2.45, 0.40)); AIM = Vector((0.0, 0.0, 1.30))

CLOAK = toon('cloak', '#232428', '#41424a', rim='#e6e1d6', rim_w=0.30)
CLOAK_D = toon('cloak_d', '#17171a', '#2b2c31', rim='#e6e1d6', rim_w=0.26)
VOID = flat('void', '#030304')
SASH = toon('sash', '#6f0f15', '#b3141c', rim='#ff5a4f', rim_w=0.3)
STEEL = toon('steel', '#5e6066', '#ece8df', rim='#ffffff', rim_w=0.35, lit_at=0.45)
SHAFT = toon('shaft', '#26231f', '#3e3a34', rim='#bdb6a6', rim_w=0.2)
EYE = flat('eye', '#ff4a3f', strength=1.0); EYEC = flat('eyec', '#fff1ea')

street(CAM)
lamp(CAM, (0.55, 0.0, 2.45), 15.0, r_core=3.5, halo=(4.8, 6.6))

# ---- robe: long, flaring, torn ----
robe('robe', [(0.0, 0.66), (0.35, 0.58), (0.8, 0.43), (1.2, 0.32), (1.45, 0.255), (1.58, 0.20)], CLOAK, ragged=0.16, seed=4)
# a second, shorter mantle over the shoulders
robe('mantle', [(1.02, 0.42), (1.3, 0.36), (1.52, 0.26), (1.62, 0.2)], CLOAK_D, ragged=0.10, seed=8, hem_pts=9, line=0.022)

# ---- hood: tall, pointed, a black void for a face ----
ball('hood', (0, 0.02, 1.80), 0.235, CLOAK_D, line=0.028, scale=(0.95, 1.0, 1.15))
# the point of the hood, swept back
cone_pts = cr([(0, 0.0, 1.95), (0.01, 0.0, 2.16), (0.06, -0.02, 2.40)], 8)
tube('hood_tip', [tuple(p) for p in cone_pts], 0.15, CLOAK_D, line=0.024, r_end=0.012)
ball('face', (0, -0.125, 1.75), 0.150, VOID, line=0.0, scale=(1.0, 0.55, 1.12))
# the eyes
ball('eye_l', (-0.066, -0.190, 1.765), 0.028, EYE, line=0.0, scale=(1.5, 0.4, 0.55), rot=(0, math.radians(-14), math.radians(-12)))
ball('eye_r', (0.066, -0.190, 1.765), 0.028, EYE, line=0.0, scale=(1.5, 0.4, 0.55), rot=(0, math.radians(14), math.radians(12)))
ball('eyec_l', (-0.066, -0.200, 1.765), 0.012, EYEC, line=0.0, scale=(1.6, 0.4, 0.5))
# glow around the eyes
EYEG = flat('eyeg', '#ff3a30', alpha=0.38)
ball('eyeg_l', (-0.066, -0.186, 1.765), 0.052, EYEG, line=0.0, scale=(1.5, 0.3, 0.9))
ball('eyeg_r', (0.066, -0.186, 1.765), 0.052, EYEG, line=0.0, scale=(1.5, 0.3, 0.9))
ball('eyec_r', (0.066, -0.200, 1.765), 0.012, EYEC, line=0.0, scale=(1.6, 0.4, 0.5))

# ---- ink folds down the robe ----
INKF = flat('inkf', '#040405')
prof = [(0.0, 0.66), (0.35, 0.58), (0.8, 0.43), (1.2, 0.32), (1.45, 0.255)]
def rx(z):
    for (z0, r0), (z1, r1) in zip(prof[:-1], prof[1:]):
        if z0 <= z <= z1: return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return prof[-1][1]
import random as _r; _rr = _r.Random(2)
for off in (-0.72, -0.46, -0.2, 0.06, 0.32, 0.58, 0.8):
    pts = []
    for z in np.linspace(1.38, 0.2, 9):
        r = rx(z); x = off * r + _rr.uniform(-0.01, 0.01); y = -math.sqrt(max(0.0, 1 - off * off)) * r * 0.78 - 0.014
        pts.append((x, y, z))
    ribbon3('fold', pts, [0.004, 0.022, 0.026, 0.02, 0.012], INKF, line=0.0, thick=0.004)

# ---- arms: long sleeves ----
tube('arm_l', [(-0.20, -0.02, 1.54), (-0.43, -0.05, 1.22), (-0.50, -0.09, 0.92)], 0.085, CLOAK, line=0.022, r_end=0.055)
ball('hand_l', (-0.50, -0.10, 0.86), 0.055, CLOAK_D, line=0.016)
tube('arm_r', [(0.20, -0.02, 1.54), (0.45, -0.07, 1.30), (0.55, -0.15, 1.12)], 0.085, CLOAK, line=0.022, r_end=0.055)
ball('hand_r', (0.55, -0.16, 1.08), 0.056, CLOAK_D, line=0.016)

# ---- scythe: shaft held in the right hand, planted at his side, blade hooked above his head ----
tube('shaft', [(0.55, -0.16, 0.0), (0.55, -0.16, 1.2), (0.55, -0.15, 2.34)], 0.032, SHAFT, line=0.014)
blade_path = cr([(0.55, -0.15, 2.36), (0.42, -0.15, 2.52), (0.16, -0.15, 2.58), (-0.12, -0.15, 2.50), (-0.36, -0.15, 2.32)], 14)
ribbon3('blade', blade_path, [0.15, 0.22, 0.20, 0.12, 0.014], STEEL, line=0.014, up=Vector((0, -1, 0)), thick=0.02)
ball('socket', (0.55, -0.155, 2.36), 0.05, CLOAK_D, line=0.012)

# ---- red sash with two torn tails ----
ribbon3('sash', cr([(-0.32, -0.25, 1.02), (0.0, -0.37, 1.0), (0.32, -0.25, 1.02)], 10), [0.075, 0.08, 0.075], SASH, line=0.012, thick=0.02)
ribbon3('tail1', cr([(0.12, -0.37, 1.0), (0.17, -0.39, 0.75), (0.13, -0.40, 0.48), (0.16, -0.41, 0.30)], 10), [0.07, 0.075, 0.06, 0.008], SASH, line=0.011)
ribbon3('tail2', cr([(0.03, -0.37, 1.0), (0.0, -0.39, 0.8), (-0.05, -0.40, 0.62), (-0.04, -0.41, 0.5)], 10), [0.06, 0.06, 0.05, 0.008], SASH, line=0.011)

rain(650, area=(-3.2, 3.2, -3.2, 12, 0, 10))
camera(sc, CAM, AIM, lens=22)
render(sc, OUT)
print('reaper3d', OUT)
