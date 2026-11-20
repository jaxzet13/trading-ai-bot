"""ALREADY CUT: a drawn (Grease Pencil) illustration. Phantom has dashed through the guard;
the guard stands frozen with the slash across him. 2D art, flat camera, perspective drawn in.
usage: EGL_PLATFORM=surfaceless python gp_card.py OUT.png [scale]"""
import sys, math, random
import bpy
from mathutils import Vector

OUT = sys.argv[1]; SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
R = random.Random(19)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = int(1500 * SCALE); sc.render.resolution_y = int(2100 * SCALE)
sc.view_settings.view_transform = 'Standard'
try:
    sc.eevee.taa_render_samples = 16
except Exception:
    pass
sc.world = bpy.data.worlds.new('w')


def srgb(h, a=1.0):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c) + (a,)


# ---------- painted background (world shader, screen space): night + the slash flash ----------
W_ = sc.world; W_.use_nodes = True; n = W_.node_tree.nodes; L = W_.node_tree.links
tc = n.new('ShaderNodeTexCoord'); sep = n.new('ShaderNodeSeparateXYZ'); L.new(tc.outputs['Window'], sep.inputs[0])
FLASH = Vector((-0.52, 0.05))
FU, FV = ((FLASH.x + 2.2) / 4.4), ((FLASH.y + 2.4) / 4.8)          # flash centre in 0..1 screen space
cx = n.new('ShaderNodeMath'); cx.operation = 'SUBTRACT'; L.new(sep.outputs['X'], cx.inputs[0]); cx.inputs[1].default_value = FU
cy = n.new('ShaderNodeMath'); cy.operation = 'SUBTRACT'; L.new(sep.outputs['Y'], cy.inputs[0]); cy.inputs[1].default_value = FV
sx = n.new('ShaderNodeMath'); sx.operation = 'MULTIPLY'; L.new(cx.outputs[0], sx.inputs[0]); sx.inputs[1].default_value = 2.5
sy = n.new('ShaderNodeMath'); sy.operation = 'MULTIPLY'; L.new(cy.outputs[0], sy.inputs[0]); sy.inputs[1].default_value = 3.5 * 0.85
cmb = n.new('ShaderNodeCombineXYZ'); L.new(sx.outputs[0], cmb.inputs[0]); L.new(sy.outputs[0], cmb.inputs[1])
ln = n.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'; L.new(cmb.outputs[0], ln.inputs[0])
noise = n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 7; noise.inputs['Detail'].default_value = 8
L.new(tc.outputs['Window'], noise.inputs['Vector'])
nm = n.new('ShaderNodeMath'); nm.operation = 'MULTIPLY_ADD'; L.new(noise.outputs['Fac'], nm.inputs[0]); nm.inputs[1].default_value = 0.22; nm.inputs[2].default_value = -0.11
d2 = n.new('ShaderNodeMath'); d2.operation = 'ADD'; L.new(ln.outputs[0], d2.inputs[0]); L.new(nm.outputs[0], d2.inputs[1])
ramp = n.new('ShaderNodeValToRGB'); cr = ramp.color_ramp
cr.elements[0].position = 0.0; cr.elements[0].color = srgb('#f1ece1')
cr.elements[1].position = 1.15; cr.elements[1].color = srgb('#040405')
for pos, col in ((0.12, '#cfc8ba'), (0.3, '#6e6a63'), (0.5, '#262528'), (0.8, '#0c0c0e')):
    e = cr.elements.new(pos); e.color = srgb(col)
L.new(d2.outputs[0], ramp.inputs['Fac'])
L.new(ramp.outputs['Color'], n['Background'].inputs['Color'])

# ---------- grease pencil helpers ----------
MATS = {}


FILLCOL = {}


def gmat(name, stroke=None, fill=None):
    if name in MATS:
        return MATS[name]
    if fill and not stroke:
        mt = bpy.data.materials.new(name); mt.use_nodes = True; nt = mt.node_tree
        nt.nodes.remove(nt.nodes['Principled BSDF'])
        em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Color'].default_value = srgb(fill)
        nt.links.new(em.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
        FILLCOL[name] = mt; MATS[name] = mt
        return mt
    mt = bpy.data.materials.new(name); bpy.data.materials.create_gpencil_data(mt)
    g = mt.grease_pencil
    g.show_stroke = stroke is not None; g.show_fill = fill is not None
    if stroke: g.color = srgb(*stroke) if isinstance(stroke, tuple) else srgb(stroke)
    if fill: g.fill_color = srgb(*fill) if isinstance(fill, tuple) else srgb(fill)
    MATS[name] = mt
    return mt


def gp_object(name, y):
    gd = bpy.data.grease_pencils.new(name)
    ob = bpy.data.objects.new(name, gd); sc.collection.objects.link(ob); ob.location = (0, y, 0)
    layer = gd.layers.new('L'); layer.use_lights = False; fr = layer.frames.new(1)
    return ob, fr.drawing


def mat_index(ob, mt):
    mats = ob.data.materials
    for i, x in enumerate(mats):
        if x == mt:
            return i
    mats.append(mt); return len(mats) - 1


def smooth(ctrl, per=14):
    P = [Vector(c) for c in ctrl]
    if len(P) < 3:
        return [P[0].lerp(P[-1], t / (per)) for t in range(per + 1)]
    Q = [P[0]] + P + [P[-1]]; out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1]); return out


FILL_N = [0]


def fillpoly(target, pts, mt):
    import bmesh
    ob = target[0]
    FILL_N[0] += 1
    me = bpy.data.meshes.new('f'); bm = bmesh.new()
    vs = [bm.verts.new((p.x, 0, p.y)) for p in pts]
    try:
        bm.faces.new(vs)
    except Exception:
        bm.free(); return None
    bm.to_mesh(me); bm.free()
    fo = bpy.data.objects.new('fill', me); sc.collection.objects.link(fo)
    fo.location = (0, ob.location.y + 0.02 - FILL_N[0] * 1e-5, 0)      # just behind its layer's strokes, later fills in front
    me.materials.append(mt)
    return fo


def stroke(target, pts, radius, mt, taper=(0.0, 0.0), opacity=1.0, cyclic=False, wobble=0.0, color=None, prof=None):
    if mt.name in FILLCOL:
        return fillpoly(target, [Vector(p) for p in pts], mt)
    ob, d = target
    pts = list(pts); n = len(pts)
    d.add_strokes([n]); st = d.strokes[len(d.strokes) - 1]
    ph = R.random() * 6
    for i, p in enumerate(st.points):
        t = i / max(1, n - 1)
        w = 1.0
        if taper[0] and t < taper[0]: w *= (t / taper[0]) ** 0.7
        if taper[1] and t > 1 - taper[1]: w *= ((1 - t) / taper[1]) ** 0.7
        if prof: w *= prof(t)
        jit = (math.sin(t * 13 + ph) * 0.5 + math.sin(t * 31 + ph * 2) * 0.3) * wobble
        x, z = pts[i].x, pts[i].y
        p.position = (x, 0, z + jit * 0.3)
        p.radius = max(0.0004, radius * w * (1 + jit))
        p.opacity = opacity if not callable(opacity) else opacity(t)
        if color: p.vertex_color = color(t) if callable(color) else color
    st.cyclic = cyclic
    st.material_index = mat_index(ob, mt)
    return st


def blob(target, c, r, mt, rough=0.25, n=22, squash=1.0, rot=0.0):
    pts = []
    k = R.random() * 6
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * (1 + rough * (math.sin(a * 3 + k) * 0.5 + R.uniform(-.5, .5) * 0.6))
        x, y = math.cos(a) * rr, math.sin(a) * rr * squash
        pts.append(Vector((c[0] + x * math.cos(rot) - y * math.sin(rot), c[1] + x * math.sin(rot) + y * math.cos(rot))))
    return stroke(target, pts, 0.001, mt, cyclic=True)


def circle(target, c, r, mt, n=48):
    return stroke(target, [Vector((c[0] + math.cos(2 * math.pi * i / n) * r, c[1] + math.sin(2 * math.pi * i / n) * r)) for i in range(n)], 0.001, mt, cyclic=True)


def offset_side(pts, d):
    out = []
    for i in range(len(pts)):
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        t = (b - a).normalized(); nrm = Vector((-t.y, t.x))
        out.append(pts[i] + nrm * d)
    return out


# materials
INK = gmat('ink', stroke='#060607'); INKF = gmat('inkf', fill='#060607')
GREY = gmat('grey', stroke='#56585b'); GREYF = gmat('greyf', fill='#56585b')
GSHAD = gmat('gshad', stroke='#34353a'); GLITE = gmat('glite', stroke='#c9c4b8')
BONE = gmat('bone', stroke='#ebe5d8'); BONEF = gmat('bonef', fill='#ebe5d8')
RED = gmat('red', stroke='#d0141e'); REDF = gmat('redf', fill='#c0121b'); DRED = gmat('dred', stroke='#7a0a10')
STEEL = gmat('steel', stroke='#d8d6d0'); STEELF = gmat('steelf', fill='#bcbab4')
CITY = gmat('city', fill='#0b0b0d'); CITY2 = gmat('city2', fill='#141416'); WIN = gmat('win', fill='#8f897d')
GROUND = gmat('ground', fill='#0b0b0d'); CRACK = gmat('crack', stroke='#2a2a30'); WHITE = gmat('white', stroke='#f2eee6')

# background card: generated coords 0..1, distance to the flash through a painted ramp
bgm = bpy.data.materials.new('bgpaint'); bgm.use_nodes = True; nt = bgm.node_tree; nn = nt.nodes; LL = nt.links
nn.remove(nn['Principled BSDF'])
tc2 = nn.new('ShaderNodeTexCoord'); sp2 = nn.new('ShaderNodeSeparateXYZ'); LL.new(tc2.outputs['Generated'], sp2.inputs[0])
def _m(op, a, b):
    m_ = nn.new('ShaderNodeMath'); m_.operation = op
    for i, v in enumerate((a, b)):
        if isinstance(v, (int, float)): m_.inputs[i].default_value = v
        else: LL.new(v, m_.inputs[i])
    return m_.outputs[0]
dx = _m('MULTIPLY', _m('SUBTRACT', sp2.outputs['X'], FU), 4.4 * 0.6)
dz = _m('MULTIPLY', _m('SUBTRACT', sp2.outputs['Z'], FV), 4.8 * 0.55)
dd = _m('SQRT', _m('ADD', _m('MULTIPLY', dx, dx), _m('MULTIPLY', dz, dz)), 0)
nz = nn.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 6; nz.inputs['Detail'].default_value = 8
LL.new(tc2.outputs['Generated'], nz.inputs['Vector'])
dd = _m('ADD', dd, _m('MULTIPLY_ADD', nz.outputs['Fac'], 0.24) if False else _m('SUBTRACT', _m('MULTIPLY', nz.outputs['Fac'], 0.24), 0.12))
rp = nn.new('ShaderNodeValToRGB'); c2 = rp.color_ramp
c2.elements[0].position = 0.0; c2.elements[0].color = srgb('#f3eee4')
c2.elements[1].position = 1.25; c2.elements[1].color = srgb('#040405')
for pos, col in ((0.1, '#d8d1c3'), (0.26, '#8a857c'), (0.45, '#3a383b'), (0.7, '#141416'), (0.95, '#09090b')):
    e_ = c2.elements.new(pos); e_.color = srgb(col)
LL.new(dd, rp.inputs['Fac'])
em2 = nn.new('ShaderNodeEmission'); LL.new(rp.outputs['Color'], em2.inputs['Color'])
LL.new(em2.outputs[0], nn['Material Output'].inputs['Surface'])
import bmesh as _bm
_me = bpy.data.meshes.new('bg'); _b = _bm.new()
_b.faces.new([_b.verts.new(v) for v in ((-2.2, 0, -2.4), (2.2, 0, -2.4), (2.2, 0, 2.4), (-2.2, 0, 2.4))])
_b.to_mesh(_me); _b.free()
_bo = bpy.data.objects.new('bg', _me); sc.collection.objects.link(_bo); _bo.location = (0, 1.95, 0); _me.materials.append(bgm)

# layers back to front (smaller y = nearer the camera)
city = gp_object('city', 1.8)
ground = gp_object('ground', 1.7)
guard = gp_object('guard', 1.2)
slash = gp_object('slash', 1.0)
dash = gp_object('dash', 0.8)
phantom = gp_object('phantom', 0.6)
front = gp_object('front', 0.3)
rain = gp_object('rain', 0.2)

HZ = -0.98                     # horizon
VP = Vector((-0.55, HZ))       # vanishing point behind the guard

# ---------- floor: a faint horizon and a puddle that catches the cut (no skyline, no grid: it's an image, not a scene) ----------
stroke(ground, [Vector((-2.2, HZ)), Vector((2.2, HZ)), Vector((2.2, -2.4)), Vector((-2.2, -2.4))], 0.001, GROUND, cyclic=True)
puddle = [Vector((-0.95 + math.cos(a) * 0.62, -1.28 + math.sin(a) * 0.075)) for a in [2 * math.pi * k / 30 for k in range(30)]]
stroke(ground, puddle, 0.001, gmat('pud', fill='#1a1a1e'), cyclic=True)

# ---------- the guard: frozen, sword still up ----------
G = dict(head=(-0.50, 0.37), neck=(-0.52, 0.19), hip=(-0.56, -0.30),
         knee_l=(-0.72, -0.64), foot_l=(-0.80, -0.97), knee_r=(-0.40, -0.62), foot_r=(-0.30, -0.95),
         elb_r=(-0.30, 0.38), hand_r=(-0.42, 0.60), elb_l=(-0.74, 0.36), hand_l=(-0.48, 0.61))
G = {k: Vector(v) for k, v in G.items()}
GR = 0.05
LIGHT_FROM_LEFT = True


def limb(target, a, b, c, r, base, shade, lite, rim_side=1, rim_mt=None, rim_op=0.9):
    pts = smooth([a, b, c], 10)
    stroke(target, pts, r, base, wobble=0.04)
    stroke(target, offset_side(pts, -rim_side * r * 0.45), r * 0.45, shade, taper=(0.15, 0.15), opacity=0.9)
    if lite:
        stroke(target, offset_side(pts, rim_side * r * 0.78), r * 0.2, lite, taper=(0.2, 0.3), opacity=rim_op)


for side in ('l', 'r'):
    limb(guard, G['hip'], G['knee_' + side], G['foot_' + side], GR, GREY, GSHAD, GLITE, rim_side=1)
limb(guard, G['hip'], (G['hip'] + G['neck']) / 2, G['neck'], GR * 1.15, GREY, GSHAD, GLITE, rim_side=1)
for side in ('l', 'r'):
    limb(guard, G['neck'], G['elb_' + side], G['hand_' + side], GR * 0.95, GREY, GSHAD, GLITE, rim_side=-1)
circle(guard, G['head'], 0.125, GREYF)
stroke(guard, [G['head'] + Vector((math.cos(a) * 0.105, math.sin(a) * 0.105)) for a in [math.radians(200 + k * 6) for k in range(26)]], 0.018, GSHAD, taper=(0.3, 0.3))
stroke(guard, [G['head'] + Vector((math.cos(a) * 0.118, math.sin(a) * 0.118)) for a in [math.radians(110 + k * 5) for k in range(14)]], 0.008, GLITE, taper=(0.4, 0.4))
# sword, held high, blade catching the flash
hilt = Vector((-0.45, 0.62)); tip = Vector((0.05, 1.18))
stroke(guard, [hilt - (tip - hilt).normalized() * 0.08, hilt], 0.022, INK)
stroke(guard, [hilt + Vector((-0.07, 0.06)), hilt + Vector((0.07, -0.06))], 0.016, INK)
stroke(guard, [hilt, tip], 0.026, STEEL, taper=(0.0, 0.9))
stroke(guard, offset_side([hilt, tip], 0.012), 0.008, WHITE, taper=(0.1, 0.8))

# ---------- the slash: one huge red cut through the guard, and its echoes ----------
A, Bp, C = Vector((-1.3, 0.34)), Vector((-0.52, 0.06)), Vector((0.45, -0.34))
arc = smooth([A, Vector((-0.9, 0.24)), Bp, Vector((0.0, -0.13)), C], 18)
stroke(slash, arc, 0.05, RED, taper=(0.45, 0.35))
stroke(slash, arc, 0.016, WHITE, taper=(0.5, 0.45))
for off, r, op in ((0.07, 0.012, 0.8), (-0.06, 0.008, 0.6), (0.14, 0.005, 0.45)):
    stroke(slash, offset_side(arc, off), r, RED, taper=(0.6, 0.5), opacity=op)
# blood bursting from the cut, thrown the way he went
for _ in range(110):
    t = R.uniform(0.32, 0.62); p = arc[int(t * (len(arc) - 1))]
    dirv = Vector((R.uniform(0.6, 1.6), R.uniform(-0.25, 0.55))).normalized()
    dist = R.uniform(0.02, 0.55) ** 1.2
    q = p + dirv * dist
    if R.random() < 0.55:
        blob(slash, q, R.uniform(0.006, 0.02) * (1 - dist), REDF, rough=0.22, n=18)
    else:
        stroke(slash, [q, q + dirv * R.uniform(0.03, 0.12)], R.uniform(0.004, 0.012), RED, taper=(0.0, 1.0))
# the cut reflected in the puddle
refl = [Vector((p.x, -1.28 - (p.y + 0.1) * 0.12)) for p in arc[len(arc) // 4: len(arc) * 3 // 4]]
stroke(ground, refl, 0.01, RED, taper=(0.5, 0.5), opacity=0.55)

# ---------- the dash: streaks along his path from the guard to where he landed ----------
for _ in range(70):
    zz = R.uniform(-1.5, -0.25); x0 = R.uniform(-0.55, 0.1); ln = R.uniform(0.2, 0.75)
    stroke(dash, [Vector((x0, zz)), Vector((x0 + ln, zz - ln * 0.08))], R.uniform(0.002, 0.008), WHITE, taper=(0.9, 0.05), opacity=R.uniform(0.15, 0.6))
# sparks off the sliding foot
for _ in range(60):
    p = Vector((-0.2 + R.uniform(-.08, .1), -1.52 + R.uniform(-.02, .03)))
    dv = Vector((R.uniform(-1.4, -0.3), R.uniform(0.05, 0.6))).normalized()
    stroke(dash, [p, p + dv * R.uniform(0.04, 0.22)], R.uniform(0.002, 0.006), BONE if R.random() < .7 else RED, taper=(0.0, 1.0), opacity=R.uniform(.5, 1))

# ---------- Phantom: landed low, daggers out, cape still flying ----------
P = dict(head=(0.92, -0.30), neck=(0.74, -0.46), chest=(0.56, -0.66), hip=(0.34, -1.00),
         knee_f=(0.86, -1.12), foot_f=(1.02, -1.56), knee_b=(0.02, -1.30), foot_b=(-0.40, -1.54),
         elb_b=(0.44, -0.50), hand_b=(0.16, -0.40), elb_f=(1.02, -0.66), hand_f=(1.22, -0.92))
P = {k: Vector(v) for k, v in P.items()}
PR = 0.075
# cape first (behind him): from the neck, thrown up and forward
cape_top = smooth([P['neck'] + Vector((0.0, 0.03)), Vector((0.46, -0.30)), Vector((0.20, -0.22)), Vector((-0.06, -0.30)), Vector((-0.26, -0.22))], 12)
cape_bot = smooth([P['neck'] + Vector((-0.05, -0.06)), Vector((0.44, -0.46)), Vector((0.18, -0.44)), Vector((-0.08, -0.50)), Vector((-0.28, -0.46))], 12)
tip = Vector((-0.52, -0.16))
cape_top = smooth([P['neck'] + Vector((0.0, 0.03)), Vector((0.50, -0.26)), Vector((0.24, -0.15)), Vector((-0.10, -0.20)), tip], 12)
cape_bot = smooth([P['neck'] + Vector((-0.06, -0.08)), Vector((0.46, -0.50)), Vector((0.18, -0.38)), Vector((-0.16, -0.34)), tip], 12)
outline = cape_top + list(reversed(cape_bot))[1:]
stroke(phantom, outline, 0.001, INKF, cyclic=True)
for t0 in (0.25, 0.5, 0.72):   # folds
    a = cape_top[int(t0 * (len(cape_top) - 1))]; b = cape_bot[int(t0 * (len(cape_bot) - 1))]
    stroke(phantom, smooth([a.lerp(b, .2), a.lerp(b, .55) + Vector((0.05, 0.02)), a.lerp(b, .85)], 6), 0.007, gmat('fold', stroke='#1f1f23'), taper=(0.4, 0.4))
stroke(phantom, cape_top, 0.009, RED, taper=(0.1, 0.5), opacity=0.9)
stroke(phantom, offset_side(cape_top, 0.014), 0.005, BONE, taper=(0.2, 0.5), opacity=0.85)


def plimb(a, b, c, r):
    pts = smooth([a, b, c], 10)
    stroke(phantom, pts, r, INK, wobble=0.035)
    nrm_side = 1 if (c - a).x * 1 >= 0 else -1
    stroke(phantom, offset_side(pts, r * 0.82 * nrm_side), r * 0.16, RED, taper=(0.25, 0.3), opacity=0.9)
    stroke(phantom, offset_side(pts, r * 1.02 * nrm_side), r * 0.07, BONE, taper=(0.35, 0.4), opacity=0.8)


plimb(P['hip'], P['knee_b'], P['foot_b'], PR)
plimb(P['neck'], P['elb_b'], P['hand_b'], PR * 0.92)
plimb(P['hip'], P['chest'], P['neck'], PR * 1.2)
plimb(P['hip'], P['knee_f'], P['foot_f'], PR)
plimb(P['neck'], P['elb_f'], P['hand_f'], PR * 0.92)
circle(phantom, P['head'], 0.19, INKF)
stroke(phantom, [P['head'] + Vector((math.cos(a) * 0.2, math.sin(a) * 0.2)) for a in [math.radians(110 + k * 5) for k in range(22)]], 0.011, RED, taper=(0.4, 0.4))
stroke(phantom, [P['head'] + Vector((math.cos(a) * 0.212, math.sin(a) * 0.212)) for a in [math.radians(118 + k * 5) for k in range(18)]], 0.005, BONE, taper=(0.4, 0.4), opacity=0.85)

# daggers, reverse grip; the back one still wet
for hand, tipd in ((P['hand_b'], Vector((-0.34, 0.04))), (P['hand_f'], Vector((0.10, -0.30)))):
    tip = hand + tipd
    stroke(phantom, [hand - tipd.normalized() * 0.05, hand], 0.02, INK)
    stroke(phantom, [hand, tip], 0.024, STEEL, taper=(0.0, 0.95))
    stroke(phantom, offset_side([hand, tip], 0.01), 0.006, WHITE, taper=(0.1, 0.9))
back_tip = P['hand_b'] + Vector((-0.34, 0.04))
stroke(phantom, [P['hand_b'] + Vector((-0.1, 0.0)), back_tip], 0.012, RED, taper=(0.2, 0.9))
for k in range(5):
    q = back_tip.lerp(P['hand_b'], k / 5) + Vector((0, -0.03 - k * 0.012))
    blob(phantom, q, 0.008 + 0.003 * R.random(), REDF, rough=0.2, n=8, squash=1.6)

# ---------- front chaos: ink splatter in the corners, rain ----------
for corner, n_ in (((-1.15, 1.55), 18), ((1.15, -1.6), 14), ((1.2, 1.2), 8)):
    for _ in range(n_):
        q = Vector(corner) + Vector((R.gauss(0, .12), R.gauss(0, .12)))
        blob(front, q, R.uniform(0.004, 0.035), INKF if R.random() < .7 else REDF, rough=0.28, n=26)
for _ in range(260):
    x0, z0 = R.uniform(-1.4, 1.5), R.uniform(-1.8, 1.9); ln = R.uniform(0.08, 0.3)
    stroke(rain, [Vector((x0, z0)), Vector((x0 - ln * 0.22, z0 - ln))], R.uniform(0.0015, 0.0035), WHITE, taper=(0.5, 0.2), opacity=R.uniform(0.12, 0.45))

# ---------- glow on the slash ----------
try:
    fx = slash[0].shader_effects.new('glow', 'FX_GLOW')
    fx.mode = 'LUMINANCE'; fx.threshold = 0.05; fx.size = (40 * SCALE, 40 * SCALE); fx.glow_color = (1, 0.1, 0.1); fx.opacity = 0.9
except Exception as ex:
    print('glow unavailable', ex)

cd = bpy.data.cameras.new('cam'); cd.type = 'ORTHO'; cd.ortho_scale = 3.5; cd.sensor_fit = 'VERTICAL'
cam = bpy.data.objects.new('cam', cd); sc.collection.objects.link(cam)
cam.location = (0.26, -5, 0); cam.rotation_euler = (math.pi / 2, 0, 0); sc.camera = cam
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print('rendered', OUT)
