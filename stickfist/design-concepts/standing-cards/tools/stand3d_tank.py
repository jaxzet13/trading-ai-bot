"""TANK: a huge stickman, hunched, both fists stacked on the end of a giant hammer planted in front of him."""
import sys, math, random
from toonlib import *

OUT = sys.argv[1]; SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0; SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 24
sc = setup(SCALE, SAMPLES)
CAM = Vector((0.1, -3.05, 0.42)); AIM = Vector((0.15, 0.0, 1.40))
BODY = toon('body', '#34353a', '#5a5b64', rim='#e6e1d6', rim_w=0.30)
BODY_D = toon('body_d', '#222327', '#3a3b41', rim='#e6e1d6', rim_w=0.26)
HAMMER = toon('hammer', '#17171a', '#2c2d32', rim='#e6e1d6', rim_w=0.28)
FACE = toon('face', '#4a4b52', '#8d8e96', rim='#ffffff', rim_w=0.3, lit_at=0.5)
RED = toon('red', '#6f0f15', '#b3141c', rim='#ff5a4f', rim_w=0.3)
SHAFT = toon('shaft', '#26231f', '#3e3a34', rim='#bdb6a6', rim_w=0.2)
VOID = flat('void', '#030304'); EYE = flat('eye', '#ff4a3f'); EYEG = flat('eyeg', '#ff3a30', alpha=0.34)

street(CAM, W=4.2)
lamp(CAM, (0.0, 0.0, 2.6), 16.0, r_core=3.8, halo=(5.2, 7.2))

# ---- the brute: a small head sunk between huge shoulders, thick limbs, planted feet ----
hip, chest, neck = (0, 0, 1.0), (0, -0.05, 1.5), (0, -0.12, 1.98)
tube('torso', [hip, chest, neck], 0.30, BODY, line=0.035, r_end=0.26)
ball('head', (0, -0.22, 2.20), 0.215, BODY, line=0.032, scale=(1.0, 1.0, 0.95))
tube('shoulders', [(-0.46, -0.08, 1.93), (0, -0.12, 2.02), (0.46, -0.08, 1.93)], 0.17, BODY, line=0.03)
tube('leg_l', [(-0.14, 0, 1.0), (-0.38, -0.04, 0.52), (-0.46, -0.08, 0.10)], 0.17, BODY, line=0.03, r_end=0.13)
tube('leg_r', [(0.14, 0, 1.0), (0.38, -0.04, 0.52), (0.46, -0.08, 0.10)], 0.17, BODY, line=0.03, r_end=0.13)
ball('foot_l', (-0.50, -0.20, 0.08), 0.14, BODY_D, line=0.025, scale=(1.3, 2.0, 0.65)); ball('foot_r', (0.50, -0.20, 0.08), 0.14, BODY_D, line=0.025, scale=(1.3, 2.0, 0.65))
tube('arm_l', [(-0.46, -0.08, 1.93), (-0.74, -0.14, 1.45), (-0.66, -0.20, 0.98)], 0.14, BODY, line=0.028, r_end=0.12)
ball('fist_l', (-0.66, -0.21, 0.90), 0.135, BODY_D, line=0.024)
tube('arm_r', [(0.46, -0.08, 1.93), (0.82, -0.16, 1.62), (0.80, -0.20, 1.38)], 0.14, BODY, line=0.028, r_end=0.12)
ball('fist_r', (0.80, -0.20, 1.34), 0.135, BODY_D, line=0.024)

# ---- the hammer: standing on its head at his right side, his fist on the handle ----
import bpy
hc = Vector((0.98, -0.20, 0.27))
tube('handle', [(0.98, -0.20, 0.30), (0.90, -0.20, 0.95), (0.82, -0.20, 1.46)], 0.05, SHAFT, line=0.02)
bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=0.78, location=hc, rotation=(0, math.pi / 2, 0)); hb = bpy.context.object
hb.data.materials.append(HAMMER); bpy.ops.object.shade_smooth(); outline(hb, 0.035)
for sx in (-1, 1):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.27, depth=0.17, location=hc + Vector((sx * 0.46, 0, 0)), rotation=(0, math.pi / 2, 0)); e = bpy.context.object
    e.data.materials.append(FACE); bpy.ops.object.shade_smooth(); outline(e, 0.022)
# a red wrap around the middle of the head
bpy.ops.mesh.primitive_cylinder_add(radius=0.262, depth=0.10, location=hc, rotation=(0, math.pi / 2, 0)); w = bpy.context.object; w.data.materials.append(RED); bpy.ops.object.shade_smooth()

# ---- face ----
ball('face_v', (0, -0.40, 2.22), 0.15, VOID, line=0.0, scale=(1.0, 0.30, 0.55))
ball('eye_l', (-0.07, -0.425, 2.235), 0.028, EYE, line=0.0, scale=(1.5, 0.4, 0.5), rot=(0, math.radians(-14), math.radians(-14)))
ball('eye_r', (0.07, -0.425, 2.235), 0.028, EYE, line=0.0, scale=(1.5, 0.4, 0.5), rot=(0, math.radians(14), math.radians(14)))
ball('eyeg_l', (-0.07, -0.42, 2.235), 0.055, EYEG, line=0.0, scale=(1.5, 0.3, 0.8)); ball('eyeg_r', (0.07, -0.42, 2.235), 0.055, EYEG, line=0.0, scale=(1.5, 0.3, 0.8))
# chain of red across the chest
ribbon3('strap', cr([(-0.34, -0.24, 2.0), (-0.05, -0.34, 1.62), (0.30, -0.30, 1.30)], 10), [0.08, 0.085, 0.08], RED, line=0.012, thick=0.02)

rain(700, area=(-4.2, 4.2, -3.5, 12, 0, 10))
camera(sc, CAM, AIM, lens=22)
render(sc, OUT); print('tank3d', OUT)
