"""Engraved black chrome: polished silver relief on a black chrome plate, red enamel in the grooves.
usage: python chrome_blender.py PLATE_DIR OUT.png [scale] [samples]"""
import sys, os, math
import bpy

D, OUT = sys.argv[1], sys.argv[2]
SCALE = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
SAMPLES = int(sys.argv[4]) if len(sys.argv) > 4 else 64
CW, CH = 2.5, 3.5

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.cycles.max_bounces = 4; sc.cycles.glossy_bounces = 3
sc.render.resolution_x = int(1500 * SCALE); sc.render.resolution_y = int(2100 * SCALE)
sc.view_settings.view_transform = 'Standard'

# ---- environment: banded studio dome. Chrome only shows what it reflects, so the bands ARE the look ----
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
N = w.node_tree.nodes; L = w.node_tree.links
bg = N['Background']; tc = N.new('ShaderNodeTexCoord'); sp = N.new('ShaderNodeSeparateXYZ')
L.new(tc.outputs['Generated'], sp.inputs[0])
ramp = N.new('ShaderNodeValToRGB'); cr = ramp.color_ramp; cr.interpolation = 'EASE'
stops = [(0.00, 0.00), (0.38, 0.02), (0.52, 0.9), (0.60, 0.05), (0.70, 0.55), (0.78, 0.02), (0.88, 0.30), (0.95, 0.85), (1.00, 0.62)]
cr.elements[0].position = stops[0][0]; cr.elements[0].color = (stops[0][1],) * 3 + (1,)
cr.elements[1].position = stops[-1][0]; cr.elements[1].color = (stops[-1][1],) * 3 + (1,)
for pos, v in stops[1:-1]:
    e = cr.elements.new(pos); e.color = (v,) * 3 + (1,)
# the dome's z (0..1) with a sideways tilt so the bands lean across the card
tilt = N.new('ShaderNodeMath'); tilt.operation = 'MULTIPLY_ADD'; tilt.inputs[1].default_value = 0.22; tilt.inputs[2].default_value = 0.0
L.new(sp.outputs['X'], tilt.inputs[0])
sm = N.new('ShaderNodeMath'); sm.operation = 'ADD'; L.new(sp.outputs['Z'], sm.inputs[0]); L.new(tilt.outputs[0], sm.inputs[1])
L.new(sm.outputs[0], ramp.inputs['Fac']); L.new(ramp.outputs['Color'], bg.inputs['Color']); bg.inputs['Strength'].default_value = 1.35

# ---- the plate ----
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0)); card = bpy.context.object; card.scale = (CW, CH, 1)
m = bpy.data.materials.new('chrome'); m.use_nodes = True; nt = m.node_tree; MN = nt.nodes; ML = nt.links
for n in list(MN): MN.remove(n)
out = MN.new('ShaderNodeOutputMaterial')


def tex(name, nc=True):
    t = MN.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(os.path.join(D, name))
    t.image.colorspace_settings.name = 'Non-Color'; t.interpolation = 'Cubic'; t.extension = 'EXTEND'
    uv = MN.new('ShaderNodeTexCoord'); ML.new(uv.outputs['UV'], t.inputs['Vector'])
    return t


tH, tM, tR = tex('H.png'), tex('M.png'), tex('R.png')
def red(t):
    s = MN.new('ShaderNodeSeparateColor'); ML.new(t.outputs['Color'], s.inputs['Color']); return s.outputs['Red']
Hh, Mm, Rr = red(tH), red(tM), red(tR)
bump = MN.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 1.0; bump.inputs['Distance'].default_value = 0.22
ML.new(Hh, bump.inputs['Height'])


def pbr(base, rough, metal=1.0, coat=0.0, coat_rough=0.02):
    b = MN.new('ShaderNodeBsdfPrincipled'); b.inputs['Base Color'].default_value = base
    b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    for k in ('Coat Weight', 'Clearcoat'):
        if k in b.inputs: b.inputs[k].default_value = coat; break
    for k in ('Coat Roughness', 'Clearcoat Roughness'):
        if k in b.inputs: b.inputs[k].default_value = coat_rough; break
    ML.new(bump.outputs['Normal'], b.inputs['Normal']); return b


plate = pbr((0.010, 0.010, 0.012, 1), 0.20)                       # black chrome
relief = pbr((0.60, 0.61, 0.65, 1), 0.22)                        # polished silver
enamel = pbr((0.62, 0.005, 0.012, 1), 0.07, metal=0.0, coat=1.0)  # red enamel in the grooves
m1 = MN.new('ShaderNodeMixShader'); ML.new(Mm, m1.inputs['Fac']); ML.new(plate.outputs[0], m1.inputs[1]); ML.new(relief.outputs[0], m1.inputs[2])
m2 = MN.new('ShaderNodeMixShader'); ML.new(Rr, m2.inputs['Fac']); ML.new(m1.outputs[0], m2.inputs[1]); ML.new(enamel.outputs[0], m2.inputs[2])
ML.new(m2.outputs[0], out.inputs['Surface'])
card.data.materials.append(m)

cd = bpy.data.cameras.new('cam'); cd.type = 'ORTHO'; cd.ortho_scale = CH
cam = bpy.data.objects.new('cam', cd); bpy.context.collection.objects.link(cam); cam.location = (0, 0, 6); sc.camera = cam
sc.render.filepath = OUT; sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True); print('chrome', OUT)
