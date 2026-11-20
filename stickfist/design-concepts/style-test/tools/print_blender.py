"""Print the K (black) and R (red) plates onto paper in Blender (Cycles).
Matte raised black ink, glossy wet red ink, paper fibre, a raking light for relief.
usage: python print_blender.py PLATE_DIR OUT.png [scale] [samples] [sweep 0..1] [foil]"""
import sys, os, math
import bpy
from mathutils import Vector

D, OUT = sys.argv[1], sys.argv[2]
SCALE = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
SAMPLES = int(sys.argv[4]) if len(sys.argv) > 4 else 48
SWEEP = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
FOIL = len(sys.argv) > 6 and sys.argv[6] == 'foil'
CW, CH = 2.5, 3.5

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.cycles.max_bounces = 4; sc.cycles.diffuse_bounces = 1; sc.cycles.glossy_bounces = 3
sc.render.resolution_x = int(1500 * SCALE); sc.render.resolution_y = int(2100 * SCALE)
sc.view_settings.view_transform = 'Standard'
try:
    sc.view_settings.look = 'None'
except Exception:
    pass
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.0, 0.0, 0.0, 1)

# ---- the card: one plane, UV full ----
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0)); card = bpy.context.object
card.scale = (CW, CH, 1)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.subdivide(number_cuts=2); bpy.ops.object.mode_set(mode='OBJECT')
m = bpy.data.materials.new('print'); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; L = nt.links
for n in list(N):
    N.remove(n)
out = N.new('ShaderNodeOutputMaterial')


def img(path, name):
    t = N.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(path); t.image.colorspace_settings.name = 'Non-Color'
    t.interpolation = 'Cubic'; t.name = name; t.extension = 'EXTEND'
    return t


tK = img(os.path.join(D, 'K.png'), 'K'); tR = img(os.path.join(D, 'R.png'), 'R')
uv = N.new('ShaderNodeTexCoord')
L.new(uv.outputs['UV'], tK.inputs['Vector']); L.new(uv.outputs['UV'], tR.inputs['Vector'])

# paper fibre: fine noise + stretched noise
nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 900; nz.inputs['Detail'].default_value = 6
L.new(uv.outputs['Object'], nz.inputs['Vector'])
nz2 = N.new('ShaderNodeTexNoise'); nz2.inputs['Scale'].default_value = 14; nz2.inputs['Detail'].default_value = 3
L.new(uv.outputs['Object'], nz2.inputs['Vector'])

# height: paper grain + raised black ink + higher red ink
def mathn(op, a, b, clamp=False):
    n = N.new('ShaderNodeMath'); n.operation = op; n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if isinstance(v, (int, float)): n.inputs[i].default_value = v
        else: L.new(v, n.inputs[i])
    return n.outputs[0]


h_paper = mathn('MULTIPLY', nz.outputs['Fac'], 0.05)
h_ink = mathn('MULTIPLY', tK.outputs['Color'], 0.0) if False else None
sepK = N.new('ShaderNodeSeparateColor'); L.new(tK.outputs['Color'], sepK.inputs['Color'])
sepR = N.new('ShaderNodeSeparateColor'); L.new(tR.outputs['Color'], sepR.inputs['Color'])
K = sepK.outputs['Red']; R = sepR.outputs['Red']
h = mathn('ADD', h_paper, mathn('MULTIPLY', K, 0.22))
h = mathn('ADD', h, mathn('MULTIPLY', R, 0.55))
h = mathn('ADD', h, mathn('MULTIPLY', nz2.outputs['Fac'], 0.012))
bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.8; bump.inputs['Distance'].default_value = 0.012
L.new(h, bump.inputs['Height'])


def bsdf(base, rough, coat=0.0, spec=0.5, metal=0.0, coat_rough=0.03):
    b = N.new('ShaderNodeBsdfPrincipled')
    b.inputs['Base Color'].default_value = base; b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    for k in ('Specular IOR Level', 'Specular'):
        if k in b.inputs: b.inputs[k].default_value = spec; break
    for k in ('Coat Weight', 'Clearcoat'):
        if k in b.inputs: b.inputs[k].default_value = coat; break
    for k in ('Coat Roughness', 'Clearcoat Roughness'):
        if k in b.inputs: b.inputs[k].default_value = coat_rough; break
    L.new(bump.outputs['Normal'], b.inputs['Normal'])
    return b


paper = bsdf((0.80, 0.74, 0.62, 1), 0.9, spec=0.1)
# paper tone varies a little across the sheet
cr = N.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].color = (0.70, 0.64, 0.53, 1); cr.color_ramp.elements[1].color = (0.86, 0.81, 0.70, 1)
L.new(nz2.outputs['Fac'], cr.inputs['Fac']); L.new(cr.outputs['Color'], paper.inputs['Base Color'])
if FOIL:
    ink_paper = bsdf((0.88, 0.89, 0.92, 1), 0.28, spec=0.6, metal=1.0)      # the bone areas are silver foil
    mixp = N.new('ShaderNodeMixShader'); mixp.inputs['Fac'].default_value = 0.0
    luma = mathn('SUBTRACT', 1.0, K)                                          # unprinted areas
    L.new(luma, mixp.inputs['Fac']); L.new(paper.outputs[0], mixp.inputs[1]); L.new(ink_paper.outputs[0], mixp.inputs[2])
    base_shader = mixp.outputs[0]
else:
    base_shader = paper.outputs[0]
blk = bsdf((0.006, 0.006, 0.007, 1), 0.82, spec=0.08)
red = bsdf((0.62, 0.006, 0.014, 1), 0.16, coat=0.6, spec=0.45)
m1 = N.new('ShaderNodeMixShader'); L.new(K, m1.inputs['Fac']); L.new(base_shader, m1.inputs[1]); L.new(blk.outputs[0], m1.inputs[2])
m2 = N.new('ShaderNodeMixShader'); L.new(R, m2.inputs['Fac']); L.new(m1.outputs[0], m2.inputs[1]); L.new(red.outputs[0], m2.inputs[2])
L.new(m2.outputs[0], out.inputs['Surface'])
card.data.materials.append(m)

# ---- lights: a big soft raking light for relief, and a softbox that sweeps for the wet sheen ----
def area(name, loc, size, power, rot, shape='RECTANGLE', sy=None, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = power; ld.size = size; ld.shape = shape
    if sy: ld.size_y = sy
    ld.color = color
    ob = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(ob); ob.location = loc; ob.rotation_euler = rot
    return ob


area('rake', (-4.2, 3.0, 0.55), 5.0, 150, (math.radians(84), 0, math.radians(-125)), sy=5.0, color=(1.0, 0.96, 0.90))
sx = -2.4 + SWEEP * 4.8
area('sheen', (sx, 1.2, 4.2), 0.45, 70, (math.radians(10), 0, 0), sy=2.6, color=(1.0, 0.98, 0.95))
area('fill', (0, -3.0, 5.0), 6.0, 9, (math.radians(10), 0, 0), sy=6.0)

# ---- camera: straight on, a hair of perspective ----
cd = bpy.data.cameras.new('cam'); cd.lens = 120; cd.sensor_fit = 'VERTICAL'; cd.sensor_height = 36
cam = bpy.data.objects.new('cam', cd); bpy.context.collection.objects.link(cam)
dist = CH * 120 / 36 * 1.0
cam.location = (0, 0, dist); cam.rotation_euler = (0, 0, 0); sc.camera = cam
sc.render.filepath = OUT; sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
print('printed', OUT)
