"""Papercut shadowbox: sheets S0..S5 stacked with real gaps, cast shadows, and a red moon that lights the paper.
usage: python papercut_blender.py PLATE_DIR OUT.png [scale] [samples] [cam_x]"""
import sys, os, math, json
import bpy

D, OUT = sys.argv[1], sys.argv[2]
SCALE = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
SAMPLES = int(sys.argv[4]) if len(sys.argv) > 4 else 64
CAMX = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
CW, CH = 2.5, 3.5
cols = json.load(open(os.path.join(D, 'cols.json')))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.cycles.max_bounces = 3; sc.cycles.diffuse_bounces = 1; sc.cycles.transparent_max_bounces = 16
sc.render.resolution_x = int(1500 * SCALE); sc.render.resolution_y = int(2100 * SCALE)
sc.view_settings.view_transform = 'Standard'
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
w.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)

GAP = 0.085


def load(name):
    im = bpy.data.images.load(os.path.join(D, name)); im.colorspace_settings.name = 'Non-Color'
    return im


def sheet(name, z, rgb, alpha_img=None, emit=0.0, rough=0.95, color_img=None):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, z)); ob = bpy.context.object
    ob.scale = (CW, CH, 1); ob.name = name
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; L = nt.links
    for n in list(N): N.remove(n)
    out = N.new('ShaderNodeOutputMaterial')
    b = N.new('ShaderNodeBsdfPrincipled'); b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough
    for k in ('Specular IOR Level', 'Specular'):
        if k in b.inputs: b.inputs[k].default_value = 0.12; break
    if color_img:
        ct = N.new('ShaderNodeTexImage'); ct.image = color_img; ct.interpolation = 'Linear'; ct.extension = 'EXTEND'
        ct.image.colorspace_settings.name = 'sRGB'
        cu = N.new('ShaderNodeTexCoord'); L.new(cu.outputs['UV'], ct.inputs['Vector']); L.new(ct.outputs['Color'], b.inputs['Base Color'])
    # paper tooth
    uv = N.new('ShaderNodeTexCoord'); nz = N.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 700; nz.inputs['Detail'].default_value = 6
    L.new(uv.outputs['Object'], nz.inputs['Vector'])
    bp = N.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.35; bp.inputs['Distance'].default_value = 0.004
    L.new(nz.outputs['Fac'], bp.inputs['Height']); L.new(bp.outputs['Normal'], b.inputs['Normal'])
    surf = b.outputs[0]
    if emit:
        e = N.new('ShaderNodeEmission'); e.inputs['Color'].default_value = (*rgb, 1); e.inputs['Strength'].default_value = emit
        mx = N.new('ShaderNodeMixShader'); mx.inputs['Fac'].default_value = 0.35
        L.new(b.outputs[0], mx.inputs[1]); L.new(e.outputs[0], mx.inputs[2]); surf = mx.outputs[0]
    if alpha_img:
        t = N.new('ShaderNodeTexImage'); t.image = alpha_img; t.interpolation = 'Linear'; t.extension = 'EXTEND'
        L.new(uv.outputs['UV'], t.inputs['Vector'])
        sp = N.new('ShaderNodeSeparateColor'); L.new(t.outputs['Color'], sp.inputs['Color'])
        tr = N.new('ShaderNodeBsdfTransparent'); mx2 = N.new('ShaderNodeMixShader')
        L.new(sp.outputs['Red'], mx2.inputs['Fac']); L.new(tr.outputs[0], mx2.inputs[1]); L.new(surf, mx2.inputs[2])
        surf = mx2.outputs[0]
    L.new(surf, out.inputs['Surface'])
    ob.data.materials.append(m)
    return ob


# back: red moon sheet, then the dark sky sheet with the moon cut out, then five stacked sheets
sheet('moon', 0.0, (0.50, 0.012, 0.02), load('moon.png'), emit=0.9)
sheet('S0', GAP * 1, tuple(cols['0']), load('S0.png'), color_img=load('C0.png'))
for k in range(1, 6):
    c = cols[str(k)]
    # paper sheets are flat colours: nudge each darker/cooler than the reference so the stack reads as black paper
    sheet(f'S{k}', GAP * (k + 1), (c[0], c[1], c[2]), load(f'S{k}.png'), color_img=load(f'C{k}.png'))

# lights: soft key from upper left throws shadows down-right on the sheet below; the moon glows red onto everything in front
def area(name, loc, size, power, rot, color, sy=None):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = power; ld.size = size; ld.color = color
    if sy: ld.shape = 'RECTANGLE'; ld.size_y = sy
    ob = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(ob); ob.location = loc; ob.rotation_euler = rot
    return ob


area('key', (-2.6, 3.4, 1.9), 0.7, 950, (math.radians(52), math.radians(-18), math.radians(-24)), (1.0, 0.95, 0.88))
area('moonglow', (0.0, 0.55, 0.9), 2.2, 6, (0, 0, 0), (1.0, 0.04, 0.03), sy=2.2)
area('fill', (0.0, -1.5, 3.0), 4.0, 22, (math.radians(10), 0, 0), (0.85, 0.9, 1.0), sy=4.0)

cd = bpy.data.cameras.new('cam'); cd.type = 'ORTHO'; cd.ortho_scale = CH; cd.sensor_fit = 'VERTICAL'
cam = bpy.data.objects.new('cam', cd); bpy.context.collection.objects.link(cam)
cam.location = (0, 0, 6); cam.rotation_euler = (0, 0, 0); sc.camera = cam
# look at the card centre
sc.render.filepath = OUT; sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
print('built', OUT)
