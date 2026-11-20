"""Sumi-e on cold-press rice paper: ink soaked into the fibre (no relief), a soft raking light for tooth.
usage: python wash_blender.py PLATE_DIR OUT.png [scale] [samples]"""
import sys, os, math
import bpy

D, OUT = sys.argv[1], sys.argv[2]
SCALE = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
SAMPLES = int(sys.argv[4]) if len(sys.argv) > 4 else 48
CW, CH = 2.5, 3.5

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.cycles.max_bounces = 3
sc.render.resolution_x = int(1500 * SCALE); sc.render.resolution_y = int(2100 * SCALE)
sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.02, 0.02, 0.02, 1)

bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0)); card = bpy.context.object; card.scale = (CW, CH, 1)
m = bpy.data.materials.new('wash'); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; L = nt.links
for n in list(N): N.remove(n)
out = N.new('ShaderNodeOutputMaterial')
uv = N.new('ShaderNodeTexCoord')


def tex(name):
    t = N.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(os.path.join(D, name))
    t.image.colorspace_settings.name = 'Non-Color'; t.interpolation = 'Cubic'; t.extension = 'EXTEND'
    L.new(uv.outputs['UV'], t.inputs['Vector']); s = N.new('ShaderNodeSeparateColor'); L.new(t.outputs['Color'], s.inputs['Color'])
    return s.outputs['Red']


K, R = tex('K.png'), tex('R.png')
# cold-press tooth: big soft grain + fine fibre, and long fibres
n1 = N.new('ShaderNodeTexNoise'); n1.inputs['Scale'].default_value = 140; n1.inputs['Detail'].default_value = 8
n2 = N.new('ShaderNodeTexNoise'); n2.inputs['Scale'].default_value = 1100; n2.inputs['Detail'].default_value = 4
n3 = N.new('ShaderNodeTexNoise'); n3.inputs['Scale'].default_value = 6; n3.inputs['Detail'].default_value = 3
for n in (n1, n2, n3): L.new(uv.outputs['Object'], n.inputs['Vector'])


def mth(op, a, b):
    x = N.new('ShaderNodeMath'); x.operation = op
    for i, v in enumerate((a, b)):
        if isinstance(v, (int, float)): x.inputs[i].default_value = v
        else: L.new(v, x.inputs[i])
    return x.outputs[0]


h = mth('ADD', mth('MULTIPLY', n1.outputs['Fac'], 0.7), mth('MULTIPLY', n2.outputs['Fac'], 0.3))
bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.55; bump.inputs['Distance'].default_value = 0.02
L.new(h, bump.inputs['Height'])
paper = N.new('ShaderNodeBsdfPrincipled'); paper.inputs['Roughness'].default_value = 0.95
for k in ('Specular IOR Level', 'Specular'):
    if k in paper.inputs: paper.inputs[k].default_value = 0.05; break
cr = N.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].color = (0.80, 0.74, 0.62, 1); cr.color_ramp.elements[1].color = (0.94, 0.90, 0.80, 1)
L.new(n3.outputs['Fac'], cr.inputs['Fac'])
# the paper is a little darker where the tooth is deep: ink pools in it
dark = mth('MULTIPLY', n1.outputs['Fac'], 0.0)
L.new(cr.outputs['Color'], paper.inputs['Base Color']); L.new(bump.outputs['Normal'], paper.inputs['Normal'])
ink = N.new('ShaderNodeBsdfPrincipled'); ink.inputs['Base Color'].default_value = (0.012, 0.012, 0.015, 1); ink.inputs['Roughness'].default_value = 0.92
L.new(bump.outputs['Normal'], ink.inputs['Normal'])
rink = N.new('ShaderNodeBsdfPrincipled'); rink.inputs['Base Color'].default_value = (0.55, 0.012, 0.03, 1); rink.inputs['Roughness'].default_value = 0.85
L.new(bump.outputs['Normal'], rink.inputs['Normal'])
# ink density is modulated by the paper tooth: pools in the valleys, skips on the peaks (that is the dry-brush look)
Kt = mth('MULTIPLY', K, mth('ADD', 0.78, mth('MULTIPLY', n1.outputs['Fac'], 0.5)))
mk = N.new('ShaderNodeMixShader'); L.new(Kt, mk.inputs['Fac']); L.new(paper.outputs[0], mk.inputs[1]); L.new(ink.outputs[0], mk.inputs[2])
mr = N.new('ShaderNodeMixShader'); L.new(R, mr.inputs['Fac']); L.new(mk.outputs[0], mr.inputs[1]); L.new(rink.outputs[0], mr.inputs[2])
L.new(mr.outputs[0], out.inputs['Surface'])
card.data.materials.append(m)


def area(name, loc, size, power, rot):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = power; ld.size = size
    ob = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(ob); ob.location = loc; ob.rotation_euler = rot


area('rake', (-3.6, 2.6, 0.9), 4.0, 260, (math.radians(76), 0, math.radians(-126)))
area('fill', (0, 0, 5.0), 6.0, 75, (0, 0, 0))
cd = bpy.data.cameras.new('cam'); cd.type = 'ORTHO'; cd.ortho_scale = CH
cam = bpy.data.objects.new('cam', cd); bpy.context.collection.objects.link(cam); cam.location = (0, 0, 6); sc.camera = cam
sc.render.filepath = OUT; sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True); print('wash', OUT)
