"""Office + hall furniture and dressing (helper module for items/office.py).

All coordinates are three.js coordinates (x right, y up, z toward the open front), metres.
Everything is seeded / deterministic.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from items import dollhouse_kit as kit
from lib import geo, mat, tex
from lib.core import B, T, set_origin, shade_smooth

BOOK_COLORS = ['#e8b7a8', '#a8c3d9', '#c9d9a8', '#e6d29a', '#c5b3dc', '#f0c9a0', '#9fc7c0']

DESK = dict(x0=0.275, x1=1.425, z0=-0.25, z1=0.30, top=0.55, t=0.035)
CHAIR = (0.85, -0.5)
SHELF = dict(x0=-0.89, x1=-0.01, back=-1.815, depth=0.41, h=1.02, top_t=0.02)


# ----------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------

def rot3(obj, axis, deg, pivot):
    """Rotate mesh data about a three.js axis ('x'|'y'|'z') through a three.js pivot."""
    bax, sgn = {'x': ('X', 1), 'y': ('Z', 1), 'z': ('Y', -1)}[axis]
    p = B(*pivot)
    m = Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg) * sgn, 4, bax) @ Matrix.Translation(-p)
    obj.data.transform(m)
    obj.data.update()
    return obj


def leaf(name, base, az_deg, elev_deg, length, width, thick, m, dist=0.0, roll=0.0):
    """Plump leaf (scaled sphere) whose base sits `dist` out from `base` (three.js point), pointing
    along azimuth az (degrees in the Blender XY plane: 0 = +x, 90 = three -z) and elevation elev."""
    e, a = math.radians(elev_deg), math.radians(az_deg)
    d = Vector((math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))  # Blender
    c = B(*base) + d * (dist + length * 0.45)
    return geo.sphere(name, 1.0, center=c, segs=14, rings=8, scale=(length / 2, width / 2, thick / 2),
                      rot=(roll, -elev_deg, az_deg), mat=m)


def puff(obj, top_y, amount, cx, cz, hx, hz, band=0.015):
    """Inflate the top of a cushion: verts near the top rise by amount * bump(x, z)."""
    for v in obj.data.vertices:
        x, y, z = T(v.co)
        if y > top_y - band:
            fx = max(0.0, 1 - ((x - cx) / hx) ** 2)
            fz = max(0.0, 1 - ((z - cz) / hz) ** 2)
            v.co.z += amount * fx * fz * min(1.0, (y - (top_y - band)) / band)
    obj.data.update()


def puff_front(obj, front_z, amount, cx, cy, hx, hy, band=0.015):
    for v in obj.data.vertices:
        x, y, z = T(v.co)
        if z > front_z - band:
            fx = max(0.0, 1 - ((x - cx) / hx) ** 2)
            fy = max(0.0, 1 - ((y - cy) / hy) ** 2)
            v.co.y -= amount * fx * fy * min(1.0, (z - (front_z - band)) / band)  # three +z = Blender -y
    obj.data.update()


def disc_uv(obj, cx, cz, radius):
    """Top-down UVs mapping a disc of `radius` around (cx, cz) to the unit texture square."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for loop in f.loops:
            x, y, z = T(loop.vert.co)
            loop[uvl].uv = (0.5 + (x - cx) / (2 * radius), 0.5 - (z - cz) / (2 * radius))
    bm.to_mesh(me)
    bm.free()


def planar_uv_xz(obj, x0, x1, z0, z1):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for loop in f.loops:
            x, y, z = T(loop.vert.co)
            loop[uvl].uv = ((x - x0) / (x1 - x0), (z1 - z) / (z1 - z0))
    bm.to_mesh(me)
    bm.free()


# ----------------------------------------------------------------------------------------------
# textures
# ----------------------------------------------------------------------------------------------

def painting_texture(w=320, h=240, seed=41):
    """Wordless landscape: sky, sun, clouds, rolling hills with round trees."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / w, yy / h                     # v = 0 top
    top, bot = tex.rgb('#a9cbe3'), tex.rgb('#f4ead6')
    img = top[None, None, :] * (1 - v[..., None]) + bot[None, None, :] * v[..., None]
    sun = np.clip(1 - np.hypot((u - 0.74) * w, (v - 0.26) * h) / (0.075 * h), 0, 1)
    s3 = np.clip(sun * 3, 0, 1)[..., None]
    img = img * (1 - s3) + tex.rgb('#f8dfa4')[None, None, :] * s3

    def blob(cx, cy, rx, ry):
        return np.clip(1 - ((u - cx) / rx) ** 2 - ((v - cy) / ry) ** 2, 0, 1)
    cl = np.zeros_like(u)
    for (cx, cy, rx, ry) in ((0.22, 0.22, 0.1, 0.05), (0.3, 0.19, 0.08, 0.06), (0.15, 0.24, 0.07, 0.04),
                             (0.52, 0.14, 0.07, 0.035), (0.58, 0.12, 0.05, 0.04)):
        cl = np.maximum(cl, blob(cx, cy, rx, ry))
    c = np.clip(cl * 5, 0, 1)[..., None]
    img = img * (1 - c) + tex.rgb('#fbf8f1')[None, None, :] * c
    hills = [(0.58, 0.06, 4.0, 0.3, '#bcd29f'), (0.68, 0.05, 6.0, 1.7, '#a3bf88'), (0.80, 0.04, 3.2, 2.9, '#89a874')]
    for (base, amp, fr, ph, col) in hills:
        edge = base + amp * np.sin(u * fr + ph) + 0.015 * np.sin(u * 17 + ph * 3)
        m = np.clip((v - edge) * h * 0.9, 0, 1)[..., None]
        img = img * (1 - m) + tex.rgb(col)[None, None, :] * m
    rng = np.random.default_rng(seed)
    for _ in range(9):
        tx = rng.uniform(0.05, 0.95)
        ty = 0.70 + 0.05 * np.sin(tx * 6.0 + 1.7) + rng.uniform(-0.01, 0.03)
        r = rng.uniform(0.022, 0.034)
        trunk = (np.abs(u - tx) < 0.004) & (v > ty) & (v < ty + r * 1.8)
        img[trunk] = tex.rgb('#8a6a4f')
        t = np.clip(1 - np.hypot((u - tx) * w, (v - ty) * h) / (r * h), 0, 1)
        mt = np.clip(t * 6, 0, 1)[..., None]
        img = img * (1 - mt) + tex.rgb('#6f8f5e')[None, None, :] * mt
    vig = 1 - 0.06 * (((u - 0.5) * 2) ** 2 + ((v - 0.5) * 2) ** 2)
    return np.clip(img * vig[..., None], 0, 1)


def runner_texture(w=512, h=128, seed=43):
    """Hall runner: dusty-rose field, cream + sage border stripes, small diamonds, woven noise."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / w, yy / h
    img = np.ones((h, w, 3), np.float32) * tex.rgb('#d6a596')[None, None, :]
    d = np.minimum(v, 1 - v)
    for (a, b, col) in ((0.0, 0.07, '#efe3cc'), (0.10, 0.14, '#a9b897'), (0.17, 0.19, '#efe3cc')):
        img[(d >= a) & (d < b)] = tex.rgb(col)
    k = 10.0
    du = np.abs(((u * k) % 1.0) - 0.5) * 2
    dv = np.abs(v - 0.5) / 0.14
    img[(du * 0.5 + dv * 0.5) < 0.42] = tex.rgb('#efe3cc')
    img[(du * 0.5 + dv * 0.5) < 0.2] = tex.rgb('#c98f7a')
    n = tex.value_noise(w, h, 64, 16, seed, octaves=2)
    weave = 0.95 + 0.06 * n + 0.025 * np.sin(xx * 1.7) * np.sin(yy * 1.7)
    return np.clip(img * weave[..., None], 0, 1)


# ----------------------------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------------------------

def materials():
    P = dict(kit.materials())
    P['desk_top'] = kit.wood('desk_top', '#d9b68e', size=512, seed=31, rings=7.0, contrast=0.11)
    P['desk_frame'] = kit.wood('desk_frame', '#b8916b', size=256, seed=32, rings=10.0, contrast=0.11)
    P['shelf'] = kit.wood('shelf', '#cfa77f', size=256, seed=33, rings=10.0, contrast=0.11)
    P['laptop'] = mat.prop('laptop', '#ccc8c1')
    P['keys'] = mat.prop('keys', '#5a5753')
    P['bezel'] = mat.prop('bezel', '#3d3b3c')
    P['trackpad'] = mat.prop('trackpad', '#bcb7af')
    P['screen'] = mat.emit('screen', '#2f3546', strength=1.0)
    P['pad'] = mat.fabric('chair_pad', '#d2b06f', double_sided=False)
    P['frame'] = mat.prop('chair_frame', '#6c6661')
    P['column'] = mat.metal('chair_column', '#a7a29c', roughness=0.4)
    P['caster'] = mat.prop('caster', '#4a4542')
    P['pot'] = mat.prop('pot', '#c99a7a')
    P['soil'] = mat.prop('soil', '#6e5442')
    P['plant'] = mat.prop('plant', '#93a77f')
    P['plant_dark'] = mat.prop('plant_dark', '#7c9169')
    P['stem'] = mat.prop('stem', '#8a6a4f')
    P['mug'] = mat.ceramic('mug', '#e8b7a8')
    P['coffee'] = mat.prop('coffee', '#6b4a35')
    P['notebook'] = mat.prop('notebook', '#a9b897')
    P['paper'] = mat.prop('paper', '#f7f1e3')
    P['pen'] = mat.prop('pen', '#36435e')
    P['clock_face'] = mat.prop('clock_face', '#fbf6ea')
    P['ink'] = mat.ink('clock', '#2f2a27')
    P['band'] = mat.prop('book_band', '#f6efe0')
    P['books'] = [mat.prop(f'book_{i}', c) for i, c in enumerate(BOOK_COLORS)]
    P['vase_a'] = mat.ceramic('vase_mint', '#9fc7c0')
    P['vase_b'] = mat.ceramic('vase_rose', '#e8b7a8')
    P['vase_c'] = mat.ceramic('vase_sage', '#a9b897')
    P['vase_d'] = mat.ceramic('vase_cream', '#f1e6d0')
    P['blossom_a'] = mat.prop('blossom_peach', '#f0c9a0')
    P['blossom_b'] = mat.prop('blossom_rose', '#e8a898')
    P['blossom_c'] = mat.prop('blossom_cream', '#f8f1e2')
    P['painting'] = mat.prop('painting', '#ffffff', image=kit._img('tex_painting', painting_texture))
    rug_img = kit._img('tex_rug', lambda: tex.braided_rug(size=512, rings=11, seed=4)[..., :3])
    P['rug'] = mat.fabric('rug', '#ffffff', image=rug_img, double_sided=False)
    P['runner'] = mat.fabric('runner', '#ffffff', image=kit._img('tex_runner', runner_texture), double_sided=False)
    P['shade'] = kit.emit_solid('hall_shade', '#ffd9a6', strength=1.0, base='#3b2e20')
    P['bulb'] = kit.emit_solid('hall_bulb', '#fff2d8', strength=1.1)
    P['cord'] = mat.prop('cord', '#4a3f38')
    return P


# ----------------------------------------------------------------------------------------------
# desk + laptop + desk items
# ----------------------------------------------------------------------------------------------

def desk(P):
    x0, x1, z0, z1, top, t = (DESK[k] for k in ('x0', 'x1', 'z0', 'z1', 'top', 't'))
    yb = top - t
    kit.rbox('desk_top', x0, x1, yb, top, z0, z1, r=0.016, mat=P['desk_top'], grain='x', tile=0.9)
    fr = []
    lw, ins = 0.054, 0.04
    for (lx, lz) in ((x0 + ins, z0 + ins), (x1 - ins, z0 + ins), (x0 + ins, z1 - ins), (x1 - ins, z1 - ins)):
        fr.append(kit.rbox('desk_leg', lx - lw / 2, lx + lw / 2, 0.012, yb + 0.002, lz - lw / 2, lz + lw / 2,
                           r=0.016, mat=P['desk_frame'], grain='y', tile=0.6))
        fr.append(kit.rbox('desk_foot', lx - lw / 2 - 0.004, lx + lw / 2 + 0.004, 0.0, 0.03, lz - lw / 2 - 0.004,
                           lz + lw / 2 + 0.004, r=0.012, mat=P['desk_frame'], grain='y', tile=0.6))
    ah = 0.085
    # apron on the camera side (+z) and the two ends; the -z side stays open (knee space)
    fr.append(kit.rbox('desk_apron', x0 + ins, x1 - ins, yb - ah, yb + 0.002, z1 - ins - 0.012, z1 - ins + 0.012,
                       r=0.008, mat=P['desk_frame'], grain='x', tile=0.6))
    fr.append(kit.rbox('desk_apron_panel', x0 + 0.13, x1 - 0.13, yb - ah + 0.02, yb - 0.018, z1 - ins + 0.01,
                       z1 - ins + 0.018, r=0.006, mat=P['desk_frame'], grain='x', tile=0.6))
    for sx in (x0 + ins, x1 - ins):
        fr.append(kit.rbox('desk_apron', sx - 0.012, sx + 0.012, yb - ah, yb + 0.002, z0 + ins, z1 - ins, r=0.008,
                           mat=P['desk_frame'], grain='z', tile=0.6))
        fr.append(kit.rbox('desk_stretcher', sx - 0.014, sx + 0.014, 0.10, 0.13, z0 + ins, z1 - ins, r=0.01,
                           mat=P['desk_frame'], grain='z', tile=0.6))
    kit._join(fr, 'desk_frame')


def laptop(P):
    cx, y0, zc, w, d, h = 0.85, 0.55, -0.12, 0.36, 0.25, 0.018
    za, zb = zc - d / 2, zc + d / 2          # -0.245 (Tim's side) .. 0.005 (hinge side)
    yt = y0 + h
    base = [kit.rbox('laptop_shell', cx - w / 2, cx + w / 2, y0, yt, za, zb, r=0.006, mat=P['laptop'], segments=3)]
    kx0, kx1, kz0, kz1 = cx - 0.158, cx + 0.158, za + 0.124, zb - 0.012
    base.append(kit.rbox('laptop_deck', kx0, kx1, yt - 0.002, yt + 0.0006, kz0, kz1, r=0.003, mat=P['keys'],
                         segments=2))
    cols, rows = 13, 5
    ax0, ax1, az0, az1 = kx0 + 0.006, kx1 - 0.006, kz0 + 0.005, kz1 - 0.004
    px, pz = (ax1 - ax0) / cols, (az1 - az0) / rows
    for r in range(rows):
        zc_ = az0 + (r + 0.5) * pz
        segs = [(0, 1.5), (1.5, 3), (3, 4.5), (4.5, 9.5), (9.5, 11), (11, 13)] if r == 0 else \
            [(i, i + 1) for i in range(cols)]
        for (a, b) in segs:
            base.append(kit.rbox('key', ax0 + a * px + 0.0016, ax0 + b * px - 0.0016, yt + 0.0002, yt + 0.0022,
                                 zc_ - pz / 2 + 0.0016, zc_ + pz / 2 - 0.0016, r=0.0, mat=P['keys']))
    base.append(kit.rbox('laptop_pad', cx - 0.06, cx + 0.06, yt - 0.0004, yt + 0.0005, za + 0.022, za + 0.102,
                         r=0.004, mat=P['trackpad'], segments=1))
    kit._join(base, 'laptop_base')

    # lid + screen, authored upright (rotation 0), then tilted back 0.26 rad about the hinge axis
    hx, hy, hz = cx, yt, zb
    lid = kit.rbox('laptop_lid_shell', hx - w / 2, hx + w / 2, hy + 0.001, hy + d, hz - 0.0065, hz + 0.0005,
                   r=0.0035, mat=P['laptop'], segments=2)
    bez = kit.rbox('laptop_bezel', hx - w / 2 + 0.0035, hx + w / 2 - 0.0035, hy + 0.0045, hy + d - 0.0035,
                   hz - 0.0071, hz - 0.004, r=0.002, mat=P['bezel'], segments=1)
    lid = kit._join([lid, bez], 'laptop_lid')
    scx, scy, scz = hx, hy + 0.126, hz - 0.0077
    sl, sr = scx + 0.175, scx - 0.175          # Tim faces +z, so HIS left is +x
    sb, st = scy - 0.11, scy + 0.11
    scr = kit.quad('laptop_screen', [(sl, sb, scz), (sr, sb, scz), (sr, st, scz), (sl, st, scz)], mat=P['screen'],
                   uvs=((0, 0), (1, 0), (1, 1), (0, 1)), facing=(0, 0, -1))
    scr['uv_note'] = "u: 0 at +x edge (Tim's left) -> 1 at -x edge; v: 0 at hinge edge -> 1 at top"
    set_origin(lid, B(hx, hy, hz))
    set_origin(scr, B(scx, scy, scz))
    kit.parent_keep(scr, lid)
    lid.rotation_euler = (0.26, 0.0, 0.0)      # Blender X == three X; +0.26 tilts the top toward +z
    bpy.context.view_layer.update()
    c = scr.matrix_world.translation.copy()
    n = (lid.matrix_world.to_3x3() @ B(0, 0, -1)).normalized()
    p = c + n * 0.15
    kit.anchor('light_laptop', *T(p))
    return T(c), T(n)


def mug(P, x=0.46, z=-0.03, y=0.55):
    prof = [(0.0, 0.0), (0.033, 0.0), (0.0375, 0.003), (0.0395, 0.012), (0.0405, 0.080), (0.042, 0.087),
            (0.0405, 0.0915), (0.0368, 0.0895), (0.0352, 0.02), (0.0, 0.016)]
    parts = [geo.lathe('mug_body', prof, segs=32, center=B(x, y, z), mat=P['mug'])]
    parts.append(geo.torus('mug_handle', R=0.025, r=0.0068, center=B(x - 0.046, y + 0.048, z), rot=(90, 0, 0),
                           major=24, minor=10, mat=P['mug']))
    parts.append(kit.cyl_y('mug_coffee', x, z, y + 0.07, y + 0.0715, 0.0356, mat=P['coffee'], segs=32))
    kit._join(parts, 'mug')


def notebook(P, x=1.19, z=-0.06, y=0.55, yaw=-9.0):
    w, d = 0.15, 0.21
    parts = [
        kit.rbox('nb_cover_b', x - w / 2, x + w / 2, y, y + 0.0022, z - d / 2, z + d / 2, r=0.001, mat=P['notebook']),
        kit.rbox('nb_pages', x - w / 2 + 0.003, x + w / 2 - 0.004, y + 0.0018, y + 0.0142, z - d / 2 + 0.004,
                 z + d / 2 - 0.004, r=0.0015, mat=P['paper'], segments=1),
        kit.rbox('nb_cover_t', x - w / 2, x + w / 2, y + 0.0138, y + 0.016, z - d / 2, z + d / 2, r=0.001,
                 mat=P['notebook']),
        kit.rbox('nb_spine', x - w / 2 - 0.002, x - w / 2 + 0.007, y, y + 0.016, z - d / 2, z + d / 2, r=0.0045,
                 mat=P['notebook'], segments=2),
        kit.rbox('nb_strap', x + w / 2 - 0.034, x + w / 2 - 0.026, y - 0.0006, y + 0.0168, z - d / 2 - 0.0006,
                 z + d / 2 + 0.0006, r=0.001, mat=P['stem']),
    ]
    yp = y + 0.016 + 0.0046
    parts.append(kit.cyl('pen_body', (x - 0.03, yp, z + 0.075), (x + 0.035, yp, z - 0.06), 0.0046, mat=P['pen'],
                         segs=12, bevel=0.0015))
    parts.append(kit.cyl('pen_tip', (x + 0.035, yp, z - 0.06), (x + 0.041, yp, z - 0.073), 0.0042, r1=0.0012,
                         mat=P['brass'], segs=12))
    parts.append(kit.rbox('pen_clip', x - 0.028, x - 0.010, yp + 0.0035, yp + 0.0055, z + 0.035, z + 0.071,
                          r=0.0009, mat=P['brass']))
    nb = kit._join(parts, 'notebook')
    rot3(nb, 'y', yaw, (x, y, z))


def rosette(P, x, y, z, scale=1.0, name='succulent'):
    parts = []
    rings = [(8, 0.034, 0.021, 0.013, 22, 0.020, 'plant'), (6, 0.029, 0.018, 0.012, 46, 0.012, 'plant_dark'),
             (5, 0.022, 0.015, 0.011, 66, 0.005, 'plant')]
    for ri, (n, L, W, Th, el, dist, m) in enumerate(rings):
        for i in range(n):
            az = 360.0 * i / n + ri * 23.0
            parts.append(leaf(f"{name}_leaf", (x, y, z), az, el, L * scale, W * scale, Th * scale, P[m],
                              dist=dist * scale))
    parts.append(kit.ball(f"{name}_bud", x, y + 0.012 * scale, z, 0.009 * scale, mat=P['plant_dark'], segs=12,
                          rings=8))
    return parts


def succulent(P, x=1.30, z=0.175, y=0.55):
    prof = [(0.0, 0.0), (0.032, 0.0), (0.0355, 0.003), (0.042, 0.052), (0.0475, 0.0545), (0.048, 0.066),
            (0.0445, 0.068), (0.041, 0.062), (0.0, 0.057)]
    parts = [geo.lathe('succ_pot', prof, segs=28, center=B(x, y, z), mat=P['pot'])]
    parts.append(kit.cyl_y('succ_soil', x, z, y + 0.055, y + 0.0605, 0.0415, mat=P['soil'], segs=24))
    parts += rosette(P, x, y + 0.062, z, scale=1.0)
    kit._join(parts, 'succulent')


# ----------------------------------------------------------------------------------------------
# swivel chair
# ----------------------------------------------------------------------------------------------

def chair(P):
    cx, cz = CHAIR
    bp = [kit.cyl_y('ch_hub', cx, cz, 0.062, 0.112, 0.044, mat=P['frame'], r_top=0.036, bevel=0.01, segs=24)]
    for i in range(5):
        a = math.radians(-90 + 72 * i + 36)
        dx, dz = math.cos(a), math.sin(a)
        tip = (cx + 0.275 * dx, 0.074, cz + 0.275 * dz)
        bp.append(kit.cyl('ch_arm', (cx + 0.02 * dx, 0.09, cz + 0.02 * dz), tip, 0.019, mat=P['frame'], r1=0.015,
                          segs=12))
        bp.append(kit.ball('ch_tip', *tip, 0.018, mat=P['frame'], segs=12, rings=8))
        bp.append(kit.cyl_y('ch_fork', tip[0], tip[2], 0.036, 0.07, 0.011, mat=P['caster'], segs=10))
        tx, tz = -dz, dx
        wc = (tip[0] + 0.014 * dx, 0.025, tip[2] + 0.014 * dz)
        bp.append(kit.cyl('ch_wheel', (wc[0] - 0.0125 * tx, 0.025, wc[2] - 0.0125 * tz),
                          (wc[0] + 0.0125 * tx, 0.025, wc[2] + 0.0125 * tz), 0.024, mat=P['caster'], segs=16,
                          bevel=0.007))
    bp.append(kit.cyl_y('ch_sleeve', cx, cz, 0.105, 0.225, 0.031, mat=P['frame'], bevel=0.006, segs=20))
    bp.append(kit.cyl_y('ch_column', cx, cz, 0.215, 0.318, 0.019, mat=P['column'], segs=20))
    base = kit._join(bp, 'chair_base')
    set_origin(base, B(cx, 0.0, cz))

    sw = [kit.rbox('ch_mech', cx - 0.095, cx + 0.095, 0.302, 0.334, cz - 0.11, cz + 0.085, r=0.01, mat=P['frame'])]
    seat = kit.rbox('ch_seat', cx - 0.22, cx + 0.22, 0.322, 0.39, cz - 0.20, cz + 0.20, r=0.034, mat=P['pad'],
                    segments=4)
    puff(seat, 0.39, 0.0102, cx, cz, 0.22, 0.20, band=0.02)
    sw.append(seat)
    sw.append(kit.rbox('ch_jbar_h', cx - 0.032, cx + 0.032, 0.304, 0.332, cz - 0.248, cz - 0.09, r=0.011,
                       mat=P['frame']))
    sw.append(kit.rbox('ch_jbar_v', cx - 0.032, cx + 0.032, 0.304, 0.68, cz - 0.262, cz - 0.232, r=0.012,
                       mat=P['frame']))
    shell = kit.rbox('ch_back_shell', cx - 0.208, cx + 0.208, 0.552, 0.955, cz - 0.27, cz - 0.244, r=0.012,
                     mat=P['frame'], segments=3)
    padb = kit.rbox('ch_back_pad', cx - 0.2, cx + 0.2, 0.56, 0.95, cz - 0.25, cz - 0.188, r=0.03, mat=P['pad'],
                    segments=4)
    puff_front(padb, cz - 0.188, 0.008, cx, 0.755, 0.2, 0.195, band=0.02)
    for o in (shell, padb):
        rot3(o, 'x', -7.0, (cx, 0.56, cz - 0.25))
    sw += [shell, padb]
    swivel = kit._join(sw, 'chair_swivel')
    set_origin(swivel, B(cx, 0.31, cz))
    kit.parent_keep(swivel, base)
    return base, swivel


# ----------------------------------------------------------------------------------------------
# bookshelf + books + top dressing
# ----------------------------------------------------------------------------------------------

def bookshelf(P, seed=7):
    x0, x1, back, depth, h, tt = (SHELF[k] for k in ('x0', 'x1', 'back', 'depth', 'h', 'top_t'))
    front = back + depth
    st, sh = 0.025, 0.022
    m = P['shelf']
    parts = [
        kit.rbox('sh_side', x0, x0 + st, 0.0, h, back, front, r=0.008, mat=m, grain='y', tile=0.7),
        kit.rbox('sh_side', x1 - st, x1, 0.0, h, back, front, r=0.008, mat=m, grain='y', tile=0.7),
        kit.rbox('sh_back', x0 + st - 0.002, x1 - st + 0.002, 0.05, h - 0.01, back, back + 0.012, r=0.003, mat=m,
                 grain='y', tile=0.7),
        kit.rbox('sh_kick', x0 + st - 0.002, x1 - st + 0.002, 0.0, 0.062, front - 0.03, front - 0.012, r=0.006,
                 mat=m, grain='x', tile=0.7),
        kit.rbox('sh_bottom', x0 + st - 0.002, x1 - st + 0.002, 0.055, 0.077, back + 0.01, front - 0.004, r=0.005,
                 mat=m, grain='x', tile=0.7),
        kit.rbox('sh_carcass_top', x0 + st - 0.002, x1 - st + 0.002, h - 0.022, h, back + 0.01, front - 0.002,
                 r=0.005, mat=m, grain='x', tile=0.7),
        kit.rbox('sh_top', x0 - 0.012, x1 + 0.012, h - 0.001, h + tt, back, front + 0.014, r=0.009, mat=m,
                 grain='x', tile=0.7, segments=3),
    ]
    comps = [(0.077, 0.385), (0.407, 0.715), (0.737, h - 0.022)]
    for (ya, yb) in comps[:-1]:
        parts.append(kit.rbox('sh_shelf', x0 + st - 0.002, x1 - st + 0.002, yb, yb + sh, back + 0.01, front - 0.006,
                              r=0.005, mat=m, grain='x', tile=0.7))
    kit._join(parts, 'bookshelf')
    books(P, comps, x0 + st, x1 - st, back + 0.012, front, seed)
    shelf_top_dressing(P, h + tt, back, front)


def _book(P, name, xa, xb, ya, yb, za, zb, ci, rng):
    m = P['books'][ci]
    parts = [kit.rbox(name, xa, xb, ya, yb, za, zb, r=0.0035, mat=m, segments=2)]
    hgt = yb - ya
    nb = int(rng.choice([0, 1, 1, 2]))
    if xb - xa > 0.02 and nb:
        ys = [ya + hgt * 0.13] if nb == 1 else [ya + hgt * 0.11, ya + hgt * 0.84]
        bw = 0.006 if nb == 1 else 0.0055
        for yy in ys:
            parts.append(kit.rbox(name + '_band', xa + 0.0015, xb - 0.0015, yy, yy + bw, zb - 0.004, zb + 0.0012,
                                  r=0.0, mat=P['band']))
    return kit._join(parts, name)


def books(P, comps, xl, xr, zb, zf, seed):
    rng = np.random.default_rng(seed)
    out = []
    k = 0
    for ci, (ya, yb) in enumerate(comps):
        H = yb - ya
        stack = ci == 2
        x = xl + 0.006
        x_end = xr - (0.205 if stack else 0.004)
        leaned = 0
        last_col = -1
        count = 0
        while True:
            w = float(rng.uniform(0.022, 0.044))
            hgt = H * float(rng.uniform(0.6, 0.9))
            dpt = float(rng.uniform(0.15, 0.205))
            col = int(rng.integers(0, len(BOOK_COLORS)))
            if col == last_col:
                col = (col + 3) % len(BOOK_COLORS)
            last_col = col
            ze = zf - 0.012 - float(rng.uniform(0.0, 0.012))
            if count >= 5 and leaned < 1 and rng.random() < 0.35:
                # a gap, then a book leaning left onto its neighbour
                a = float(rng.uniform(11.0, 17.0))
                ar = math.radians(a)
                xbl = x + hgt * math.sin(ar)
                if xbl + w * math.cos(ar) + 0.01 > x_end:
                    break
                b = _book(P, f"book{k}", xbl, xbl + w, ya, ya + hgt, ze - dpt, ze, col, rng)
                rot3(b, 'z', a, (xbl, ya, 0.0))
                out.append(b)
                x = xbl + w * math.cos(ar) + float(rng.uniform(0.004, 0.02))
                leaned += 1
                k += 1
                count = 0
                continue
            if x + w > x_end:
                break
            out.append(_book(P, f"book{k}", x, x + w, ya, ya + hgt, ze - dpt, ze, col, rng))
            x += w + float(rng.uniform(0.0006, 0.0035))
            k += 1
            count += 1
        if stack:
            yy = ya
            for j in range(3):
                L = float(rng.uniform(0.15, 0.185))
                th = float(rng.uniform(0.026, 0.036))
                dpt = float(rng.uniform(0.15, 0.19))
                cxs = xr - 0.012 - 0.095 + float(rng.uniform(-0.008, 0.008))
                col = int(rng.integers(0, len(BOOK_COLORS)))
                ze = zf - 0.014
                b = kit.rbox(f"bookstack{j}", cxs - L / 2, cxs + L / 2, yy, yy + th, ze - dpt, ze, r=0.0035,
                             mat=P['books'][col], segments=2)
                rot3(b, 'y', float(rng.uniform(-5, 5)), (cxs, yy, ze - dpt / 2))
                out.append(b)
                yy += th
    kit._join(out, 'books')


def shelf_top_dressing(P, y, back, front):
    zc = (back + front) / 2
    # pot plant (right end of the top; GuoGuo sits at the left end, x -0.66, so keep >= 0.22 m clear of him)
    px, pz = -0.14, zc - 0.01
    prof = [(0.0, 0.0), (0.045, 0.0), (0.05, 0.004), (0.058, 0.085), (0.064, 0.09), (0.0645, 0.104),
            (0.059, 0.106), (0.055, 0.098), (0.0, 0.094)]
    parts = [geo.lathe('top_pot', prof, segs=28, center=B(px, y, pz), mat=P['pot'])]
    parts.append(kit.cyl_y('top_soil', px, pz, y + 0.09, y + 0.098, 0.056, mat=P['soil'], segs=24))
    for i in range(15):
        az = i * 137.5
        el = 18 + (i % 5) * 13
        yy = y + 0.10 + 0.012 * (i % 4)
        parts.append(leaf('top_leaf', (px, yy, pz), az, el, 0.07, 0.05, 0.013,
                          P['plant'] if i % 2 else P['plant_dark'], dist=0.012 + 0.006 * (i % 3)))
    parts.append(kit.ball('top_leaf_c', px, y + 0.15, pz, 0.03, mat=P['plant'], scale=(1, 0.8, 1), segs=14, rings=8))
    kit._join(parts, 'shelf_plant')
    # vase with three blossoms (between GuoGuo and the plant)
    vx, vz = -0.36, zc - 0.03
    vprof = [(0.0, 0.0), (0.03, 0.0), (0.042, 0.02), (0.047, 0.06), (0.04, 0.105), (0.022, 0.14), (0.017, 0.16),
             (0.022, 0.172), (0.0175, 0.175), (0.0, 0.165)]
    vparts = [geo.lathe('top_vase', vprof, segs=28, center=B(vx, y, vz), mat=P['vase_a'])]
    for (dx, dz, hh, m) in ((-0.03, 0.01, 0.30, 'blossom_a'), (0.025, -0.005, 0.27, 'blossom_b'),
                            (0.002, 0.02, 0.33, 'blossom_c')):
        tip = (vx + dx, y + hh, vz + dz)
        vparts.append(geo.tube('top_stem', [B(vx, y + 0.15, vz), B(vx + dx * 0.4, y + hh * 0.75, vz + dz * 0.4),
                                            B(*tip)], radius=0.0028, segs=6, mat=P['stem']))
        vparts.append(kit.ball('top_blossom', *tip, 0.02, mat=P[m], segs=14, rings=8))
        vparts.append(leaf('top_sleaf', (vx + dx * 0.5, y + hh * 0.72, vz + dz * 0.5), 40 + dx * 3000, 30, 0.04, 0.02,
                           0.008, P['plant']))
    kit._join(vparts, 'shelf_vase')


# ----------------------------------------------------------------------------------------------
# floor plant, rug, clock, painting
# ----------------------------------------------------------------------------------------------

def floor_plant(P, x=-2.15, z=-1.55):
    prof = [(0.0, 0.0), (0.105, 0.0), (0.118, 0.012), (0.142, 0.255), (0.158, 0.265), (0.162, 0.30),
            (0.15, 0.306), (0.145, 0.285), (0.0, 0.28)]
    parts = [geo.lathe('fplant_pot', prof, segs=36, center=B(x, 0.0, z), mat=P['pot'])]
    parts.append(kit.cyl_y('fplant_soil', x, z, 0.27, 0.284, 0.146, mat=P['soil'], segs=28))
    rng = np.random.default_rng(23)
    stems = [((0.02, -0.01), 0.98, (0.05, 0.03)), ((-0.03, 0.02), 0.82, (-0.07, 0.05)),
             ((0.015, 0.035), 0.70, (0.06, 0.09))]
    for si, ((ox, oz), top, (lx, lz)) in enumerate(stems):
        path = [(x + ox, 0.28, z + oz), (x + ox + lx * 0.4, 0.28 + (top - 0.28) * 0.5, z + oz + lz * 0.4),
                (x + ox + lx, top, z + oz + lz)]
        parts.append(geo.tube('fplant_stem', [B(*p) for p in path], radius=[0.011, 0.009, 0.006], segs=8,
                              mat=P['stem']))
        nlv = 7 if si == 0 else 6
        for j in range(nlv):
            t = 0.35 + 0.65 * j / (nlv - 1)
            sx = x + ox + lx * t
            sz = z + oz + lz * t
            sy = 0.28 + (top - 0.28) * t
            az = si * 120 + j * 137.5
            el = 20 + 30 * t + float(rng.uniform(-8, 8))
            L = 0.15 + 0.03 * math.sin(j)
            parts.append(leaf('fplant_leaf', (sx, sy, sz), az, el, L, L * 0.72, 0.022,
                              P['plant'] if (j + si) % 2 else P['plant_dark'], dist=0.0,
                              roll=float(rng.uniform(-20, 20))))
        parts.append(leaf('fplant_tip', (x + ox + lx, top, z + oz + lz), si * 70, 78, 0.12, 0.085, 0.02, P['plant']))
    kit._join(parts, 'floor_plant')


def rug(P, cx=0.85, cz=-0.35, r=0.85):
    prof = [(0.0, 0.0005), (r - 0.012, 0.0005), (r - 0.002, 0.0018), (r, 0.0034), (r - 0.003, 0.0052),
            (r - 0.012, 0.0062), (0.0, 0.0062)]
    o = geo.lathe('rug', prof, segs=96, center=B(cx, 0.0, cz), mat=P['rug'])
    disc_uv(o, cx, cz, r / 0.985)
    return o


def clock(P, z=0.45, y=1.65, wall_x=-2.55):
    """Wall clock on the left wall, facing +x.  Hands rotate about +X around the centre."""
    cxp = wall_x
    parts = []
    rim_prof = [(0.0, 0.0), (0.148, 0.0), (0.155, 0.008), (0.156, 0.03), (0.15, 0.042), (0.138, 0.046),
                (0.13, 0.04), (0.128, 0.03), (0.0, 0.03)]
    parts.append(geo.lathe('clock_rim', rim_prof, segs=48, center=B(cxp, y, z), rot=(0, 90, 0), mat=P['beam']))
    face_x = cxp + 0.031
    parts.append(kit.cyl('clock_face', (cxp + 0.02, y, z), (face_x, y, z), 0.129, mat=P['clock_face'], segs=48))
    kit._join(parts, 'clock')
    ticks = []
    for i in range(12):
        a = 2 * math.pi * i / 12
        major = i % 3 == 0
        L, W = (0.022, 0.0075) if major else (0.013, 0.0045)
        rr = 0.108
        b = kit.rbox('clock_tick', face_x - 0.001, face_x + 0.0022, y + rr - L / 2, y + rr + L / 2, z - W / 2,
                     z + W / 2, r=0.0009, mat=P['ink'])
        rot3(b, 'x', -math.degrees(a), (face_x, y, z))
        ticks.append(b)
    ticks.append(kit.cyl('clock_cap', (face_x, y, z), (face_x + 0.012, y, z), 0.0075, mat=P['brass'], segs=16))
    kit._join(ticks, 'clock_ticks')
    hands = {}
    for nm_, L, W, dx, tail in (('clock_hour', 0.068, 0.0115, 0.0035, 0.016),
                                ('clock_minute', 0.098, 0.0075, 0.0065, 0.02)):
        bm_parts = [kit.rbox(nm_ + '_bar', face_x + dx - 0.0012, face_x + dx + 0.0012, y - tail, y + L, z - W / 2,
                             z + W / 2, r=0.0011, mat=P['ink'], segments=1),
                    kit.cyl(nm_ + '_hub', (face_x + dx - 0.0012, y, z), (face_x + dx + 0.0012, y, z), W * 0.9,
                            mat=P['ink'], segs=16)]
        hnd = kit._join(bm_parts, nm_)
        set_origin(hnd, B(face_x, y, z))
        hands[nm_] = hnd
    # default display time 10:10 (rotation 0 = 12 o'clock; clockwise = negative about +X)
    hands['clock_hour'].rotation_euler = (-math.radians((10 + 10 / 60) * 30), 0, 0)
    hands['clock_minute'].rotation_euler = (-math.radians(10 * 6), 0, 0)
    return hands


def painting(P, x=-1.6, y=1.5, wall_z=-1.85, w=0.6, h=0.46):
    fw, fd = 0.045, 0.032
    zf = wall_z + fd
    m = P['beam']
    parts = [
        kit.rbox('pf', x - w / 2, x + w / 2, y + h / 2 - fw, y + h / 2, wall_z, zf, r=0.009, mat=m, grain='x',
                 tile=0.6),
        kit.rbox('pf', x - w / 2, x + w / 2, y - h / 2, y - h / 2 + fw, wall_z, zf, r=0.009, mat=m, grain='x',
                 tile=0.6),
        kit.rbox('pf', x - w / 2, x - w / 2 + fw, y - h / 2 + 0.01, y + h / 2 - 0.01, wall_z, zf, r=0.009, mat=m,
                 grain='y', tile=0.6),
        kit.rbox('pf', x + w / 2 - fw, x + w / 2, y - h / 2 + 0.01, y + h / 2 - 0.01, wall_z, zf, r=0.009, mat=m,
                 grain='y', tile=0.6),
        kit.rbox('pf_back', x - w / 2 + 0.01, x + w / 2 - 0.01, y - h / 2 + 0.01, y + h / 2 - 0.01, wall_z,
                 wall_z + 0.012, r=0.0, mat=P['trim']),
    ]
    kit._join(parts, 'painting_frame')
    ix0, ix1 = x - w / 2 + fw - 0.004, x + w / 2 - fw + 0.004
    iy0, iy1 = y - h / 2 + fw - 0.004, y + h / 2 - fw + 0.004
    zc = wall_z + 0.0135
    kit.quad('painting_canvas', [(ix0, iy0, zc), (ix1, iy0, zc), (ix1, iy1, zc), (ix0, iy1, zc)], mat=P['painting'],
             uvs=((0, 0), (1, 0), (1, 1), (0, 1)), facing=(0, 0, 1))


# ----------------------------------------------------------------------------------------------
# hall
# ----------------------------------------------------------------------------------------------

def hall(P):
    # console table against the hall back wall
    x0, x1, zb, zf, top = -3.95, -3.05, -1.665, -1.375, 0.76
    m, mt = P['desk_frame'], P['desk_top']
    parts = [kit.rbox('con_top', x0, x1, top - 0.032, top, zb, zf, r=0.014, mat=mt, grain='x', tile=0.9)]
    lw = 0.04
    for lx in (x0 + 0.035, x1 - 0.035):
        for lz in (zb + 0.03, zf - 0.03):
            parts.append(kit.rbox('con_leg', lx - lw / 2, lx + lw / 2, 0.0, top - 0.03, lz - lw / 2, lz + lw / 2,
                                  r=0.012, mat=m, grain='y', tile=0.6))
    parts.append(kit.rbox('con_apron', x0 + 0.03, x1 - 0.03, top - 0.11, top - 0.03, zf - 0.045, zf - 0.025, r=0.007,
                          mat=m, grain='x', tile=0.6))
    parts.append(kit.rbox('con_shelf', x0 + 0.03, x1 - 0.03, 0.17, 0.19, zb + 0.02, zf - 0.02, r=0.007, mat=mt,
                          grain='x', tile=0.9))
    parts.append(kit.rbox('con_drawer', x0 + 0.14, x1 - 0.14, top - 0.1, top - 0.04, zf - 0.03, zf - 0.019, r=0.006,
                          mat=m, grain='x', tile=0.6))
    parts.append(kit.ball('con_knob', (x0 + x1) / 2, top - 0.07, zf - 0.012, 0.011, mat=P['brass'], segs=12, rings=8))
    kit._join(parts, 'hall_console')
    # vases (2 + a little jug) with blossoms
    zc = (zb + zf) / 2
    vp = []
    tall = [(0.0, 0.0), (0.035, 0.0), (0.042, 0.03), (0.045, 0.12), (0.035, 0.2), (0.024, 0.25), (0.022, 0.28),
            (0.027, 0.3), (0.022, 0.302), (0.0, 0.29)]
    vp.append(geo.lathe('vase_tall', tall, segs=28, center=B(-3.78, top, zc - 0.01), mat=P['vase_c']))
    belly = [(0.0, 0.0), (0.04, 0.0), (0.07, 0.04), (0.078, 0.085), (0.062, 0.14), (0.034, 0.17), (0.03, 0.19),
             (0.037, 0.2), (0.031, 0.203), (0.0, 0.19)]
    vp.append(geo.lathe('vase_belly', belly, segs=32, center=B(-3.48, top, zc + 0.01), mat=P['vase_b']))
    jug = [(0.0, 0.0), (0.03, 0.0), (0.045, 0.03), (0.047, 0.07), (0.036, 0.11), (0.04, 0.13), (0.034, 0.133),
           (0.0, 0.12)]
    vp.append(geo.lathe('vase_jug', jug, segs=28, center=B(-3.24, top, zc + 0.03), mat=P['vase_d']))
    vp.append(geo.torus('jug_handle', R=0.03, r=0.006, center=B(-3.24 + 0.046, top + 0.075, zc + 0.03),
                        rot=(90, 0, 0), major=20, minor=8, mat=P['vase_d']))
    for (vx, vy, vz, stems) in ((-3.78, top + 0.29, zc - 0.01, [(-0.04, 0.2, 'blossom_c'), (0.035, 0.24, 'blossom_a')]),
                                (-3.48, top + 0.19, zc + 0.01, [(-0.05, 0.16, 'blossom_b'), (0.0, 0.2, 'blossom_a'),
                                                                (0.05, 0.15, 'blossom_c')])):
        for (dx, hh, mm) in stems:
            tip = (vx + dx, vy + hh, vz + dx * 0.3)
            vp.append(geo.tube('hall_stem', [B(vx, vy - 0.02, vz), B(vx + dx * 0.5, vy + hh * 0.6, vz + dx * 0.15),
                                             B(*tip)], radius=0.003, segs=6, mat=P['stem']))
            vp.append(kit.ball('hall_blossom', *tip, 0.024, mat=P[mm], segs=14, rings=8))
            vp.append(leaf('hall_leaf', (vx + dx * 0.45, vy + hh * 0.5, vz), 90 + dx * 2000, 25, 0.05, 0.024, 0.008,
                           P['plant']))
    kit._join(vp, 'hall_vases')
    # pendant light hanging from the hall beam (beam bottom y = 2.17 at z = -0.9)
    lx, lz = -3.5, -0.9
    lp = [kit.cyl_y('pend_canopy', lx, lz, 2.145, 2.172, 0.035, mat=P['brass'], r_top=0.03, bevel=0.005, segs=20),
          kit.cyl_y('pend_cord', lx, lz, 2.03, 2.15, 0.004, mat=P['cord'], segs=8),
          kit.cyl_y('pend_cap', lx, lz, 2.0, 2.04, 0.022, mat=P['brass'], r_top=0.014, segs=16)]
    kit._join(lp, 'hall_pendant')
    shade_prof = [(0.0, 0.0), (0.022, 0.0), (0.05, -0.02), (0.09, -0.07), (0.112, -0.115), (0.116, -0.125),
                  (0.11, -0.127), (0.106, -0.118), (0.084, -0.074), (0.046, -0.026), (0.02, -0.006), (0.0, -0.004)]
    geo.lathe('hall_shade', shade_prof, segs=32, center=B(lx, 2.005, lz), mat=P['shade'])
    kit.ball('hall_bulb', lx, 1.9, lz, 0.03, mat=P['bulb'], segs=16, rings=10)
    kit.anchor('light_hall', lx, 1.88, lz)
    # runner rug along the lioness's path
    rx0, rx1, rz0, rz1 = -4.12, -2.78, -1.02, -0.38
    rr = kit.rbox('hall_runner', rx0, rx1, 0.0005, 0.0055, rz0, rz1, r=0.0024, mat=P['runner'], segments=2)
    planar_uv_xz(rr, rx0, rx1, rz0, rz1)


def build_all():
    P = materials()
    desk(P)
    laptop(P)
    mug(P)
    notebook(P)
    succulent(P)
    chair(P)
    bookshelf(P)
    floor_plant(P)
    rug(P)
    clock(P)
    painting(P)
    hall(P)
