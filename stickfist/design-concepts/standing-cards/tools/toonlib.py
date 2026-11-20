"""The STIXX toon engine (Blender, Cycles, emission-only): flat cel tones from one light direction, hard rim, inked
outlines by inverted hull, ink-black city canyon, rain. Everything is a flat shape with an outline."""
import sys, math, random
import numpy as np, bpy, bmesh
from mathutils import Vector

LIGHT = Vector((0.30, 0.50, 0.80)).normalized()


def setup(out_scale=1.0, samples=24, mask=False, W=1500, H=2100):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
    sc.cycles.samples = samples; sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 0; sc.cycles.transparent_max_bounces = 16
    sc.render.resolution_x = int(W * out_scale); sc.render.resolution_y = int(H * out_scale)
    sc.view_settings.view_transform = 'Standard'
    sc.render.film_transparent = mask
    sc.render.filter_size = 1.2
    world = bpy.data.worlds.new('w'); sc.world = world; world.use_nodes = True
    wn = world.node_tree.nodes; wl = world.node_tree.links
    bg = wn['Background']; tc = wn.new('ShaderNodeTexCoord'); sep = wn.new('ShaderNodeSeparateXYZ'); rmp = wn.new('ShaderNodeValToRGB')
    rmp.color_ramp.elements[0].position = 0.0; rmp.color_ramp.elements[0].color = (0.004, 0.004, 0.005, 1)
    rmp.color_ramp.elements[1].position = 1.0; rmp.color_ramp.elements[1].color = (0.022, 0.022, 0.025, 1)
    wl.new(tc.outputs['Window'], sep.inputs['Vector']); wl.new(sep.outputs['Y'], rmp.inputs['Fac']); wl.new(rmp.outputs['Color'], bg.inputs['Color'])
    return sc


def srgb(h):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c) + (1,)


def toon(name, shadow, lit, rim=None, rim_w=0.0, lit_at=0.62, bands=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; n = nt.nodes; l = nt.links
    n.remove(n['Principled BSDF'])
    geo = n.new('ShaderNodeNewGeometry')
    dot = n.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'; dot.inputs[1].default_value = LIGHT
    l.new(geo.outputs['Normal'], dot.inputs[0])
    ramp = n.new('ShaderNodeValToRGB'); ramp.color_ramp.interpolation = 'CONSTANT'
    ramp.color_ramp.elements[0].color = srgb(shadow)
    ramp.color_ramp.elements[1].position = lit_at; ramp.color_ramp.elements[1].color = srgb(lit)
    mr = n.new('ShaderNodeMapRange'); mr.inputs['From Min'].default_value = -1; mr.inputs['From Max'].default_value = 1
    l.new(dot.outputs['Value'], mr.inputs['Value']); l.new(mr.outputs['Result'], ramp.inputs['Fac'])
    col = ramp.outputs['Color']
    if rim:
        lw = n.new('ShaderNodeLayerWeight'); lw.inputs['Blend'].default_value = 0.5
        side = n.new('ShaderNodeVectorMath'); side.operation = 'DOT_PRODUCT'; side.inputs[1].default_value = LIGHT
        l.new(geo.outputs['Normal'], side.inputs[0])
        gt = n.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = -0.15
        l.new(side.outputs['Value'], gt.inputs[0])
        rr = n.new('ShaderNodeMath'); rr.operation = 'GREATER_THAN'; rr.inputs[1].default_value = 1 - rim_w
        l.new(lw.outputs['Facing'], rr.inputs[0])
        both = n.new('ShaderNodeMath'); both.operation = 'MULTIPLY'
        l.new(rr.outputs['Value'], both.inputs[0]); l.new(gt.outputs['Value'], both.inputs[1])
        mix = n.new('ShaderNodeMix'); mix.data_type = 'RGBA'
        l.new(both.outputs['Value'], mix.inputs['Factor']); l.new(col, mix.inputs[6]); mix.inputs[7].default_value = srgb(rim)
        col = mix.outputs[2]
    em = n.new('ShaderNodeEmission'); l.new(col, em.inputs['Color'])
    l.new(em.outputs['Emission'], n['Material Output'].inputs['Surface'])
    return m


def flat(name, hexc, alpha=1.0, strength=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; n = nt.nodes
    n.remove(n['Principled BSDF'])
    em = n.new('ShaderNodeEmission'); em.inputs['Color'].default_value = srgb(hexc); em.inputs['Strength'].default_value = strength
    if alpha < 1:
        tr = n.new('ShaderNodeBsdfTransparent'); mx = n.new('ShaderNodeMixShader'); mx.inputs['Fac'].default_value = alpha
        nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(em.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], n['Material Output'].inputs['Surface'])
    else:
        nt.links.new(em.outputs[0], n['Material Output'].inputs['Surface'])
    return m


def _ink():
    m = bpy.data.materials.new('ink_line'); m.use_nodes = True; nt = m.node_tree; n = nt.nodes
    n.remove(n['Principled BSDF'])
    geo = n.new('ShaderNodeNewGeometry'); tr = n.new('ShaderNodeBsdfTransparent')
    em = n.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (0, 0, 0, 1)
    mx = n.new('ShaderNodeMixShader')
    nt.links.new(geo.outputs['Backfacing'], mx.inputs['Fac']); nt.links.new(em.outputs[0], mx.inputs[1]); nt.links.new(tr.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], n['Material Output'].inputs['Surface'])
    return m


_INK = None


def outline(ob, w):
    global _INK
    if _INK is None or _INK.name not in bpy.data.materials:
        _INK = _ink()
    ob.data.materials.append(_INK)
    md = ob.modifiers.new('ink', 'SOLIDIFY'); md.thickness = w; md.offset = 1
    md.use_flip_normals = True; md.material_offset = len(ob.data.materials) - 1; md.use_rim = False


def to_mesh(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects: o.select_set(False)
    ob.select_set(True); bpy.ops.object.convert(target='MESH')
    return bpy.context.object


def tube(name, pts, r, mat, line=0.02, r_end=None):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = r; cu.bevel_resolution = 6; cu.use_fill_caps = True
    sp = cu.splines.new('NURBS'); sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts): sp.points[i].co = (*p, 1)
    if r_end is not None:
        for i, p in enumerate(sp.points): p.radius = 1 + (r_end / r - 1) * i / max(1, len(pts) - 1)
    sp.use_endpoint_u = True; sp.order_u = min(3, len(pts))
    ob = bpy.data.objects.new(name, cu); bpy.context.collection.objects.link(ob); ob.data.materials.append(mat)
    ob = to_mesh(ob); outline(ob, line); return ob


def ball(name, c, r, mat, line=0.025, scale=(1, 1, 1), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=c, segments=48, ring_count=24)
    ob = bpy.context.object; ob.scale = scale; ob.rotation_euler = rot; ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth(); outline(ob, line); return ob


def flatshape(name, pts, mat, line=0.0, thick=0.0):
    """a flat polygon in 3D (list of Vectors)"""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    vs = [bm.verts.new(p) for p in pts]; bm.faces.new(vs); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob); ob.data.materials.append(mat)
    if thick: md = ob.modifiers.new('th', 'SOLIDIFY'); md.thickness = thick
    if line: outline(ob, line)
    return ob


def ribbon3(name, path, widths, mat, line=0.012, up=Vector((0, -1, 0)), thick=0.01):
    """a flat ribbon following a 3D path, facing 'up' (towards the camera by default)"""
    pts = [Vector(p) for p in path]; n = len(pts)
    if len(widths) != n: widths = list(np.interp(np.linspace(0, len(widths) - 1, n), np.arange(len(widths)), widths))
    L, R = [], []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized(); s = t.cross(up).normalized()
        L.append(p + s * widths[i] / 2); R.append(p - s * widths[i] / 2)
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    vL = [bm.verts.new(v) for v in L]; vR = [bm.verts.new(v) for v in R]
    for i in range(n - 1): bm.faces.new((vL[i], vL[i + 1], vR[i + 1], vR[i]))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob); ob.data.materials.append(mat)
    md = ob.modifiers.new('th', 'SOLIDIFY'); md.thickness = thick
    if line: outline(ob, line)
    return ob


def cr(pts, per=14):
    P = [Vector(p) for p in pts]
    if len(P) < 3: return P
    Q = [P[0]] + P + [P[-1]]; out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1]); return out


def robe(name, profile, mat, ragged=0.1, line=0.025, n_ang=56, seed=1, squash=0.78, hem_pts=11):
    """a lathe: profile = [(z, rx)], bottom first. The bottom ring is torn."""
    rnd = random.Random(seed); me = bpy.data.meshes.new(name); bm = bmesh.new(); rings = []
    for ri, (z, rx) in enumerate(profile):
        ring = []
        for k in range(n_ang):
            a = 2 * math.pi * k / n_ang
            zz = z
            if ri == 0:
                tooth = (k * hem_pts / n_ang) % 1.0
                zz = z + ragged * (abs(tooth - 0.5) * 2) + rnd.uniform(-0.02, 0.03)
            ring.append(bm.verts.new((math.sin(a) * rx, -math.cos(a) * rx * squash, zz)))
        rings.append(ring)
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for k in range(n_ang): bm.faces.new((r0[k], r0[(k + 1) % n_ang], r1[(k + 1) % n_ang], r1[k]))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob); ob.data.materials.append(mat)
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.shade_smooth()
    md = ob.modifiers.new('th', 'SOLIDIFY'); md.thickness = 0.012
    outline(ob, line); return ob


def street(focus, sky_pts=None, seed=3, depth=26, lit=0.38, W=3.0, tilt_in=0.0):
    """two walls of ink-black buildings with a few lit windows, a dark ground"""
    BLD_D = toon('bld_d', '#060607', '#0d0d0f', lit_at=0.66); BLD_L = toon('bld_l', '#0b0b0d', '#18181b', lit_at=0.56)
    WIN = flat('win', '#c9c2b2'); WIN_D = flat('win_d', '#34322e'); GROUND = toon('ground', '#08080a', '#101013')
    rnd = random.Random(seed); objs = []
    for side in (-1, 1):
        y = -2.0
        while y < depth:
            w = rnd.uniform(2.6, 5.0); h = rnd.uniform(10, 28); x = side * rnd.uniform(W, W + 1.4)
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x + side * 2.5, y + w / 2, h / 2))
            b = bpy.context.object; b.scale = (5, w * 0.96, h); b.data.materials.append(BLD_L if side > 0 else BLD_D); outline(b, 0.05); objs.append(b)
            for _ in range(rnd.randint(2, 8)):
                wy, wz = y + rnd.uniform(0.4, w - 0.4), rnd.uniform(2.2, h - 1)
                bpy.ops.mesh.primitive_plane_add(size=1, location=(x - side * 0.02, wy, wz), rotation=(0, math.radians(90), 0))
                wo = bpy.context.object; wo.scale = (0.9, 0.45, 1); wo.data.materials.append(WIN if rnd.random() < lit else WIN_D); objs.append(wo)
            y += w
    bpy.ops.mesh.primitive_plane_add(size=120, location=(0, 20, 0)); g = bpy.context.object; g.data.materials.append(GROUND); objs.append(g)
    return objs


def lamp(cam, aim, dist, r_core=1.6, halo=(2.6, 4.2)):
    LAMP = flat('lamp', '#f1ede3'); HALO = flat('halo', '#a8a398', alpha=0.20)
    d = (Vector(aim) - Vector(cam)).normalized()
    for rad, mt, off in ((r_core, LAMP, 0.0), (halo[0], HALO, 0.02), (halo[1], HALO, 0.04)):
        bpy.ops.mesh.primitive_circle_add(vertices=96, radius=rad, fill_type='NGON', location=Vector(cam) + d * (dist + off))
        o = bpy.context.object; o.rotation_euler = (-d).to_track_quat('Z', 'Y').to_euler(); o.data.materials.append(mt)


def rain(n=700, area=(-4, 4, -2.5, 14, 0, 12), seed=9, length=(0.35, 1.1), alpha=0.28):
    RAIN = flat('rain', '#e6e1d6', alpha=alpha); rnd = random.Random(seed)
    me = bpy.data.meshes.new('rain'); bm = bmesh.new()
    x0, x1, y0, y1, z0, z1 = area
    for _ in range(n):
        x, y, z = rnd.uniform(x0, x1), rnd.uniform(y0, y1), rnd.uniform(z0, z1)
        ln, w = rnd.uniform(*length), 0.006
        vs = [bm.verts.new(v) for v in ((x, y, z), (x + w, y, z), (x + w + 0.03, y, z + ln), (x + 0.03, y, z + ln))]; bm.faces.new(vs)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('rain', me); bpy.context.collection.objects.link(ob); ob.data.materials.append(RAIN)
    return ob


def camera(sc, loc, target, lens=22, sensor=36):
    cd = bpy.data.cameras.new('cam'); cd.lens = lens; cd.sensor_fit = 'VERTICAL'; cd.sensor_height = sensor
    cam = bpy.data.objects.new('cam', cd); bpy.context.collection.objects.link(cam)
    cam.location = loc; d = Vector(target) - Vector(loc); cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler(); sc.camera = cam
    return cam


def render(sc, path):
    sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGBA' if sc.render.film_transparent else 'RGB'
    sc.render.filepath = path; bpy.ops.render.render(write_still=True)
