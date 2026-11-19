"""Phantom on a real lit set, rendered in Blender (Cycles).
The figure, blades, bodies and blood come from the owner's daggers film (frame 246):
their outlines are traced and extruded into solid cut-outs, so the shapes are his drawing.
usage: python blender_card.py OUT.png [scale] [samples] [mask]"""
import sys, os, math, random
import numpy as np, cv2, bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from noir_light import layers
from art import frame

OUT = sys.argv[1]
SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 128
MASK = len(sys.argv) > 4 and sys.argv[4] == 'mask'

# ---------- trace the film ----------
FX0, FY0, FX1, FY1 = 280, 150, 1180, 722
UP = 3.0
L = layers(frame(246)[FY0:FY1, FX0:FX1], UP)
S = 0.0045            # metres per film pixel: the figure stands ~1.8 m
FEET_Y, MID_X = 618, 850


def contours(mask, eps=0.6):
    m = (mask > .5).astype(np.uint8)
    cs, _ = cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cs:
        if cv2.contourArea(c) < 30 * UP * UP:
            continue
        c = cv2.approxPolyDP(c, eps, True)[:, 0, :].astype(float)
        out.append(c)
    return out


def film_xy(c):
    fx = c[:, 0] / UP + FX0
    fy = c[:, 1] / UP + FY0
    return fx, fy


def curve_obj(name, polys, extrude, bevel, mat, upright=True, y=0.0, z=0.0):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '2D'; cu.fill_mode = 'BOTH'
    cu.extrude = extrude; cu.bevel_depth = bevel; cu.bevel_resolution = 3
    for pts in polys:
        sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
        for i, (a, b) in enumerate(pts):
            sp.points[i].co = (a, b, 0, 1)
        sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    if upright:
        ob.rotation_euler = (math.radians(90), 0, 0)
    ob.location = (0, y, z)
    ob.data.materials.append(mat)
    return ob


def upright_polys(mask):
    polys = []
    for c in contours(mask):
        fx, fy = film_xy(c)
        polys.append(list(zip((fx - MID_X) * S, (FEET_Y - fy) * S)))
    return polys


# ---------- scene ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6; sc.cycles.volume_bounces = 1
sc.render.resolution_x = int(1500 * SCALE); sc.render.resolution_y = int(2100 * SCALE)
sc.render.film_transparent = MASK
for vt, lk in (('AgX', 'AgX - Punchy'), ('AgX', 'Punchy'), ('Filmic', 'High Contrast')):
    try:
        sc.view_settings.view_transform = vt; sc.view_settings.look = lk; break
    except Exception:
        pass
sc.view_settings.exposure = -0.6
world = bpy.data.worlds.new('w'); sc.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)


def mat(name, base, rough, metal=0.0, coat=0.0, spec=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*base, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    for k in ('Coat Weight', 'Clearcoat'):
        if k in b.inputs:
            b.inputs[k].default_value = coat; break
    for k in ('Specular IOR Level', 'Specular'):
        if k in b.inputs:
            b.inputs[k].default_value = spec; break
    return m


def concrete(name, base, rough_lo, rough_hi, bump=0.25, scale=6.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    n = nt.nodes.new('ShaderNodeTexNoise'); n.inputs['Scale'].default_value = scale; n.inputs['Detail'].default_value = 12
    n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.inputs['Scale'].default_value = scale * 9; n2.inputs['Detail'].default_value = 8
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (base * .55, base * .55, base * .55, 1)
    ramp.color_ramp.elements[1].color = (base * 1.5, base * 1.45, base * 1.4, 1)
    nt.links.new(n.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    rr = nt.nodes.new('ShaderNodeMapRange')
    rr.inputs['To Min'].default_value = rough_lo; rr.inputs['To Max'].default_value = rough_hi
    rr.inputs['From Min'].default_value = .42; rr.inputs['From Max'].default_value = .58
    nt.links.new(n.outputs['Fac'], rr.inputs['Value'])
    nt.links.new(rr.outputs['Result'], b.inputs['Roughness'])
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = bump
    nt.links.new(n2.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return m


INK = mat('ink', (0.0015, 0.0015, 0.0018), 0.42, spec=0.22)
STEEL = mat('steel', (0.8, 0.82, 0.86), 0.18, metal=1.0)
BODY = mat('body', (0.004, 0.004, 0.005), 0.7, spec=0.12)
BLOOD = mat('blood', (0.16, 0.0, 0.004), 0.04, coat=1.0, spec=0.7)
WALL = concrete('wall', 0.045, 0.75, 0.95, bump=0.35, scale=3.5)
FLOOR = concrete('floor', 0.03, 0.04, 0.55, bump=0.12, scale=2.2)

fig = curve_obj('phantom', upright_polys(L['ink']), 0.035, 0.010, INK)
blades = curve_obj('blades', upright_polys(L['steel']), 0.012, 0.004, STEEL, y=-0.05)
bodies = curve_obj('bodies', upright_polys(L['grey']), 0.06, 0.012, BODY, y=0.25)

# blood: the film draws the pool in perspective; lay it flat on the floor around his feet
pool = []
for c in contours(L['red']):
    fx, fy = film_xy(c)
    pool.append(list(zip((fx - MID_X) * S, -(fy - FEET_Y) * S * 3.2 + 0.1)))
blood = curve_obj('blood', pool, 0.0015, 0.0, BLOOD, upright=False, z=0.002)

bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0)); floor = bpy.context.object; floor.data.materials.append(FLOOR)
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 1.7, 0), rotation=(math.radians(90), 0, 0)); wall = bpy.context.object; wall.data.materials.append(WALL)

# haze, so the light beams read
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.75, 3)); vol = bpy.context.object
vol.scale = (14, 1.9, 6.0)
vm = bpy.data.materials.new('haze'); vm.use_nodes = True; nt = vm.node_tree
nt.nodes.remove(nt.nodes['Principled BSDF'])
pv = nt.nodes.new('ShaderNodeVolumePrincipled'); pv.inputs['Density'].default_value = 0.05
pv.inputs['Anisotropy'].default_value = 0.35
nt.links.new(pv.outputs['Volume'], nt.nodes['Material Output'].inputs['Volume'])
vol.data.materials.append(vm)

# rain: thin streaks that only show where light hits them
import bmesh
rm = bpy.data.meshes.new('rain'); bm = bmesh.new(); rnd = random.Random(7)
for _ in range(900):
    x, y, z = rnd.uniform(-3.2, 3.4), rnd.uniform(-3.0, 1.5), rnd.uniform(0, 5.2)
    ln, w, sl = rnd.uniform(.10, .28), .0011, math.radians(rnd.uniform(6, 10))
    dx, dz = math.sin(sl) * ln, -math.cos(sl) * ln
    vs = [bm.verts.new(p) for p in ((x, y, z), (x + w, y, z), (x + w + dx, y, z + dz), (x + dx, y, z + dz))]
    bm.faces.new(vs)
bm.to_mesh(rm); bm.free()
rain = bpy.data.objects.new('rain', rm); bpy.context.collection.objects.link(rain)
rmat = bpy.data.materials.new('rainm'); rmat.use_nodes = True
rb = rmat.node_tree.nodes['Principled BSDF']
rb.inputs['Base Color'].default_value = (0.8, 0.8, 0.82, 1); rb.inputs['Roughness'].default_value = 0.15
for k in ('Transmission Weight', 'Transmission'):
    if k in rb.inputs:
        rb.inputs[k].default_value = 0.85; break
rain.data.materials.append(rmat)


def spot(name, loc, target, power, color, size, blend, radius=0.05, vol=1.0):
    ld = bpy.data.lights.new(name, 'SPOT'); ld.energy = power; ld.color = color
    try:
        ld.volume_factor = vol
    except Exception:
        pass
    ld.spot_size = math.radians(size); ld.spot_blend = blend; ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(ob); ob.location = loc
    d = np.array(target) - np.array(loc)
    ob.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)
    ob.rotation_euler = (math.acos(-d[2] / np.linalg.norm(d)), 0, math.atan2(-d[0], d[1]))
    return ob


# key: low front left, throws his shadow huge up the wall
key = spot('key', (-1.9, -3.6, 0.55), (0.5, 1.7, 1.75), 3900, (1.0, 0.93, 0.84), 46, 0.3, 0.04, vol=0.7)
# rim: behind, high right, blood red
rim = spot('rim', (3.0, 0.9, 4.0), (0.0, 0.0, 1.2), 5200, (1.0, 0.06, 0.05), 36, 0.25, 0.06, vol=0.08)
# a hard top beam on the floor: wet concrete, the pool and the rain catch it
spot('top', (-0.3, -0.9, 5.4), (-0.4, -0.5, 0.0), 1700, (0.95, 0.95, 1.0), 24, 0.3, 0.05, vol=0.5)

# the key throws his shadow but doesn't light him: he stays a matte black silhouette
excl = bpy.data.collections.new('not_key')
for o in (fig, blades, bodies):
    excl.objects.link(o)
key.light_linking.receiver_collection = excl
for item in excl.collection_objects:
    item.light_linking.link_state = 'EXCLUDE'
# the red rim touches only the fighter, the bodies and the blood, never the wall
inc = bpy.data.collections.new('rim_only')
for o in (fig, blades, bodies, blood):
    inc.objects.link(o)
rim.light_linking.receiver_collection = inc
cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 62; cam_d.sensor_fit = 'VERTICAL'; cam_d.sensor_height = 36
cam = bpy.data.objects.new('cam', cam_d); bpy.context.collection.objects.link(cam)
cam.location = (-0.15, -5.6, 0.95)
t = np.array((-0.05, 0.0, 1.12)) - np.array(cam.location)
cam.rotation_euler = (math.acos(-t[2] / np.linalg.norm(t)), 0, math.atan2(-t[0], t[1]))
sc.camera = cam

if MASK:   # figure and blades only, everything else cut out
    for ob in (bodies, blood, floor, wall, vol, rain):
        ob.is_holdout = True
    vol.hide_render = True; rain.hide_render = True
    for o in sc.objects:
        if o.type == 'LIGHT':
            o.data.energy *= 1

sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGBA' if MASK else 'RGB'
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print('rendered', OUT)
