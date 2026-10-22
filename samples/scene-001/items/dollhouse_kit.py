"""Dollhouse kit: shared builders for the Sylvanian-style dollhouse sets (office + hall, kitchen, ...).

Not a bank item (no ITEM / build()).  Import it from an item script:

    from items import dollhouse_kit as kit
    M = kit.materials()

EVERYTHING TAKES THREE.JS COORDINATES (x right, y up, z toward the open front), in metres, exactly
as written in docs/scene-spec.md.  Builders return Blender objects (already linked, transforms baked,
origin at the world origin unless stated).  The look: chunky, soft, rounded bevels, nothing razor
sharp; cream wallpaper with flower dots, sage panelled wainscot, cream trim, wooden beams, warm
plank floor, exterior colour on wall tops / cut edges.

STABLE API (signatures will not change; internals may improve)
---------------------------------------------------------------
Materials
  materials() -> dict            shared materials, created once per build (cached in lib.mat._cache)
      'wall'      prop_wallpaper   cream wallpaper + small flower dots (tile WALLPAPER_TILE m)
      'hall'      prop_hallpaper   checked wallpaper #efdcb4 (tile CHECKS_TILE m)
      'wainscot'  prop_wainscot    sage #b9c3a8
      'trim'      prop_trim        cream #f5efe3 (baseboards, chair rails, casings, sills, frames)
      'beam'      wood_beam        #b98e67 + grain (posts, top plates, beams, picture frames)
      'rod'       wood_rod         #b98e67 + grain (curtain rods)
      'exterior'  prop_exterior    #e3d5bf (wall tops, cut edges, outer faces, base slab)
      'floor'     wood_floor       #c9a47c planks (banded texture = per-board tone + grain)
      'subfloor'  prop_subfloor    dark colour seen in the gaps between planks
      'tabletop'  prop_tabletop    #d8ccba
      'door'      prop_door        #f2ebdd
      'brass'     metal_brass      #c8a66a
      'sky'       emit_sky         lib.tex.sky_window as emission colour (strength 1.0, black base)
      'curtain'   fabric_curtain   gingham (cream + dusty rose)
      'curtain_tie' fabric_curtain_tie  solid rose (curtain tie-backs)
  wood(name, color, size=256, seed=1)            wood_<name> material with its own calm straight-grain map
  emit_image(name, image, strength=1.0)          emit_<name>: image -> emission only (no bloom)
  emit_solid(name, color, strength=1.0, base=None) emit_<name>: flat self-lit colour (keep <= 1.2)
  PALETTE                                        the brief's hex colours

Primitives (three.js bounds / points)
  rbox(name, x0, x1, y0, y1, z0, z1, r=0.01, mat=None, segments=3, grain=None, tile=1.0)
        rounded box by its bounds; grain='x'|'y'|'z' writes wood UVs with the grain along that axis
  cyl(name, p0, p1, r, mat=None, r1=None, segs=24, bevel=0.0, caps=True)   cylinder p0 -> p1
  cyl_y(name, x, z, y0, y1, r, mat=None, r_top=None, segs=24, bevel=0.0)   vertical cylinder
  ball(name, x, y, z, r, mat=None, scale=(1, 1, 1), segs=24, rings=12)      (scaled) sphere
  quad(name, corners, mat=None, uvs=((0,0),(1,0),(1,1),(0,1)), facing=None) one quad; facing=(x,y,z)
        flips it so its normal points that way
  grain_uv(obj, along='x', tile=1.0, offset=(0, 0))   wood UVs (grain along a three.js axis)
  metre_uv(obj, tile=1.0)                              box-projected UVs, one repeat per `tile` m
  spot(name, x, y, z, yaw_deg=0.0, parent=None)        spot_* empty with custom prop yaw (degrees)
  anchor(name, x, y, z, parent=None, **props)          named empty (light anchors, hooks)
  parent_keep(child, parent, origin=None)              parent without moving (origin: three.js
        point to move the child's origin to first, e.g. the hinge, so its local offset is clean)

Structure
  tabletop_and_base(footprints, center=(0, 0), radius=7.0, top_y=-0.10, base_top=-0.012, margin=0.04)
        big round table (top surface y=-0.10) + one rounded base slab per footprint (x0, x1, z0, z1)
        from y=-0.10 to base_top (the planks sit on it, floor surface y = 0)
  plank_floor(name, x0, x1, z0, z1, along='z', board_w=0.15, len_range=(0.7, 1.4), seed=11, ...)
        individual boards (tiny bevels, 3 mm gaps, seeded tone/grain per board), top at y = 0
  wall(name, x0, z0, x1, z1, inner=+1, height=2.3, thickness=0.1, paper='wall', wainscot=True,
       openings=(), inner_range=None, outer=None, top_plate=True, ...)
        axis-aligned wall centred on the segment (x0, z0)-(x1, z1).  inner=+1: the decorated side
        faces +z (an x-wall) / +x (a z-wall); -1 the other way.  openings: dicts
        {'u0', 'u1', 'y0', 'y1', 'kind': 'door'|'window'|'hole'} with u along the wall (x for an
        x-wall, z for a z-wall).  Doors get jamb linings + casings (+ plinth blocks), windows get
        casings (sill/frame come from window()).  outer=dict(paper='hall', range=(u0, u1),
        wainscot=True) decorates part of the other side too.  Returns {'core','trim','wainscot','beam'}
  window(name, axis, at, u0, u1, y0, y1, inner=+1, thickness=0.1, curtains=True, ..., u_limits=None, height=2.3)
        frame + mullions + reveal lining + sill/apron + emissive sky card + gingham curtains (tie-backs)
        on a wooden rod with finials and rings.  axis='x' (wall along x at z=at) or 'z' (along z at x=at).
        The sky card lives INSIDE the wall thickness (never pokes out); pass u_limits=(wall u0, wall u1).
  door(name='door', axis='z', at=..., u0, u1, height, inner=+1, hinge_u=None, hinge_name='door_hinge')
        white raised-panel door + brass knobs, hung on an empty at the inner wall face.  The empty
        gets custom prop open_sign: rotating it about +Y by open_sign*angle swings the door INTO the
        room.  Returns the hinge empty.
  post(name, x, z, y0=0.0, y1=2.3, w=0.09, d=None, mat=None)       vertical wooden post
  beam(name, x0, x1, y0, y1, z0, z1, mat=None, r=0.008)            wooden beam (grain along its length)
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from lib import geo, mat, tex
from lib.core import B, empty, join, set_origin, shade_smooth, new_mesh_object

PALETTE = {
    'wall': '#efe5d1', 'dot_a': '#d9ad9f', 'dot_b': '#a9b897', 'wainscot': '#b9c3a8', 'trim': '#f5efe3',
    'floor': '#c9a47c', 'beam': '#b98e67', 'exterior': '#e3d5bf', 'door': '#f2ebdd', 'brass': '#c8a66a',
    'hall_wall': '#efdcb4', 'hall_check': '#e8d2a8', 'tabletop': '#d8ccba', 'subfloor': '#6e5442',
    'curtain': '#f8f2e8', 'curtain_check': (214, 132, 112),
    'plant': '#93a77f', 'plant_dark': '#7c9169', 'pot': '#c99a7a',
}
WALLPAPER_TILE = 0.6      # metres per wallpaper repeat
CHECKS_TILE = 0.64
PLANK_BANDS = 8
PLANK_TILE = 1.2          # metres of board per texture repeat (along the board)

WAINSCOT_TOP = 0.80       # top of the chair rail
BASEBOARD_H = 0.10
CASING_W = 0.07

_KIT_KEY = "__dollhouse_kit__"


# ----------------------------------------------------------------------------------------------
# materials / images
# ----------------------------------------------------------------------------------------------

def _hex(c):
    c = np.clip(np.asarray(c, np.float32), 0, 1)
    return '#%02x%02x%02x' % tuple(int(round(float(v) * 255)) for v in c)


def _img(name, fn, colorspace='sRGB'):
    img = bpy.data.images.get(name)
    if img is None:
        img = mat.image_from_array(name, fn(), colorspace=colorspace)
    return img


def wood(name, color, size=256, seed=1, rings=9.0, contrast=0.16, dark=None):
    """wood_<name> with its own seeded, calm straight-grain map (grain along image X / UV u).
    rings ~ number of grain lines per texture repeat (x1.5); contrast ~ line darkness."""
    key = f"wood_{name}"
    if key in mat._cache:
        return mat._cache[key]
    img = _img(f"tex_grain_{name}", lambda: straight_grain(color, size=size, seed=seed, lines=rings * 1.5,
                                                           contrast=contrast, wobble=1.3, streak=0.07))
    return mat.wood(name, color, image=img)


def emit_image(name, image, strength=1.0):
    """emit_<name>: the image drives the emission colour only (base colour black), so it shows the
    image colours under tone mapping and stays under the bloom threshold."""
    key = f"emit_{name}"
    if key in mat._cache:
        return mat._cache[key]
    m = mat.material(key, '#000000', roughness=0.9, emission='#ffffff', emission_strength=strength)
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = image
    t.extension = 'EXTEND'
    nt.links.new(t.outputs["Color"], bsdf.inputs["Emission Color"])
    return m


def emit_solid(name, color, strength=1.0, base=None):
    """emit_<name>: flat self-lit colour.  Keep strength <= 1.2 so it does not bloom."""
    return mat.material(f"emit_{name}", base or '#000000', roughness=0.8, emission=color,
                        emission_strength=strength)


def straight_grain(base='#c9a47c', size=512, seed=1, lines=40.0, contrast=0.13, wobble=1.2, streak=0.06):
    """Calm, nearly straight long grain (lines along image X / UV u), tileable."""
    h = w = size
    b = np.array(mat.hex_srgb(base), np.float32)
    n_low = tex.value_noise(w, h, 3, 6, seed, octaves=2)
    fine = tex.value_noise(w, h, 2, 128, seed + 1, octaves=2)
    knot = tex.value_noise(w, h, 6, 4, seed + 2, octaves=1)
    y = np.arange(h, dtype=np.float32)[:, None] / h
    ph = (y * lines + n_low * wobble) * 2 * math.pi
    ln = (0.5 + 0.5 * np.sin(ph)) ** 6
    t = np.clip(ln * contrast + (fine - 0.5) * streak + (knot - 0.5) * 0.05, -0.08, 0.5)
    img = b[None, None, :] * (1 - t[..., None])
    return np.clip(img, 0, 1)


def plank_texture(base='#c9a47c', n_bands=PLANK_BANDS, size=512, seed=21, tone=0.075):
    """Floor boards atlas: n_bands horizontal bands, each one board's worth of grain with its own
    seeded tone.  Boards map their UV v into one band (see plank_floor)."""
    rng = np.random.default_rng(seed)
    bh = size // n_bands
    out = np.zeros((size, size, 3), np.float32)
    b0 = np.array(mat.hex_srgb(base), np.float32)
    for b in range(n_bands):
        f = 1.0 + rng.uniform(-tone, tone)
        warm = rng.uniform(-0.018, 0.018)
        col = np.clip(b0 * f + np.array([warm, warm * 0.3, -warm * 0.6], np.float32), 0, 1)
        g = straight_grain(_hex(col), size=size, seed=seed + 31 * b, lines=26.0 + 4 * (b % 3), contrast=0.075,
                           wobble=1.4, streak=0.06)
        rows = g[b * bh:(b + 1) * bh]
        t = np.linspace(0, 1, bh)[:, None]
        edge = 1.0 - 0.10 * (np.clip(1 - t / 0.08, 0, 1) + np.clip(1 - (1 - t) / 0.08, 0, 1))
        out[b * bh:(b + 1) * bh] = rows * edge[..., None]
    return out


def materials():
    """Shared dollhouse materials (one set per build)."""
    M = mat._cache.get(_KIT_KEY)
    if M is not None:
        return M
    P = PALETTE
    M = {}
    M['exterior'] = mat.prop('exterior', P['exterior'])
    M['wall'] = mat.prop('wallpaper', P['wall'], image=_img(
        'tex_wallpaper', lambda: tex.dots_wallpaper(P['wall'], (P['dot_a'], P['dot_b']), size=512, seed=2, grid=4,
                                                    radius=0.075)))
    M['hall'] = mat.prop('hallpaper', P['hall_wall'], image=_img(
        'tex_hallpaper', lambda: tex.checks(P['hall_wall'], P['hall_check'], size=256, n=8)))
    M['wainscot'] = mat.prop('wainscot', P['wainscot'])
    M['trim'] = mat.prop('trim', P['trim'])
    M['door'] = mat.prop('door', P['door'])
    M['brass'] = mat.metal('brass', P['brass'], roughness=0.35)
    M['beam'] = mat.wood('beam', P['beam'], image=_img('tex_grain_beam', lambda: straight_grain(
        P['beam'], size=256, seed=5, lines=12.0, contrast=0.16, wobble=1.4, streak=0.08)))
    M['rod'] = mat.wood('rod', P['beam'], image=bpy.data.images['tex_grain_beam'])
    M['floor'] = mat.wood('floor', P['floor'], image=_img('tex_planks', lambda: plank_texture(P['floor'])))
    M['subfloor'] = mat.prop('subfloor', P['subfloor'])
    M['tabletop'] = mat.prop('tabletop', P['tabletop'])
    M['sky'] = emit_image('sky', _img('tex_sky', lambda: tex.sky_window(512, seed=6)), strength=1.0)
    M['curtain'] = mat.fabric('curtain', P['curtain'], image=_img(
        'tex_gingham', lambda: tex.gingham(P['curtain'], P['curtain_check'], 0.62, 256, 8)))
    M['curtain_tie'] = mat.fabric('curtain_tie', '#cf9481', double_sided=False)
    mat._cache[_KIT_KEY] = M
    return M


# ----------------------------------------------------------------------------------------------
# primitives
# ----------------------------------------------------------------------------------------------

_AX = {'x': 0, 'y': 1, 'z': 2}


def _t3(v):
    """Blender vector -> three.js tuple."""
    return (v[0], v[2], -v[1])


def grain_uv(obj, along='x', tile=1.0, offset=(0.0, 0.0)):
    """Planar wood UVs with u running along the three.js axis `along` (grain direction)."""
    a = _AX[along]
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    mw = obj.matrix_world
    r3 = mw.to_3x3()
    for f in bm.faces:
        n3 = _t3(r3 @ f.normal)
        dom = max(range(3), key=lambda i: abs(n3[i]))
        for loop in f.loops:
            c3 = _t3(mw @ loop.vert.co)
            if dom == a:
                o = [i for i in range(3) if i != a]
                u, v = c3[o[0]], c3[o[1]]
            else:
                u, v = c3[a], c3[3 - a - dom]
            loop[uvl].uv = (u / tile + offset[0], v / tile + offset[1])
    bm.to_mesh(me)
    bm.free()
    return obj


def metre_uv(obj, tile=1.0):
    """Box-projected UVs, one texture repeat per `tile` metres (wallpaper, fabric)."""
    return geo.box_uv(obj, scale=1.0 / tile, world=True)


def rbox(name, x0, x1, y0, y1, z0, z1, r=0.01, mat=None, segments=3, grain=None, tile=1.0, smooth=True):
    """Rounded box from three.js bounds."""
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    size = (max(x1 - x0, 1e-4), max(z1 - z0, 1e-4), max(y1 - y0, 1e-4))
    obj = geo.rounded_box(name, size, r, B((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                          segments=segments if r > 0 else 1, mat=mat, smooth=smooth and r > 0)
    if grain:
        grain_uv(obj, grain, tile)
    return obj


def _rot_to(d3):
    """Quaternion rotating Blender +Z onto the three.js direction d3."""
    d = B(*d3)
    if d.length < 1e-9:
        return None
    return d.normalized().to_track_quat('Z', 'Y')


def cyl(name, p0, p1, r, mat=None, r1=None, segs=24, bevel=0.0, caps=True, smooth=True):
    """Cylinder (or cone, r1 = radius at p1) from three.js point p0 to p1."""
    a, b = Vector(p0), Vector(p1)
    L = (b - a).length
    c = (a + b) / 2
    q = _rot_to(tuple(b - a))
    return geo.cylinder(name, r=r, depth=L, center=B(*c), segs=segs, rot=q, mat=mat, r2=r1, caps=caps,
                        bevel=bevel, smooth=smooth)


def cyl_y(name, x, z, y0, y1, r, mat=None, r_top=None, segs=24, bevel=0.0, caps=True):
    return geo.cylinder(name, r=r, depth=y1 - y0, center=B(x, (y0 + y1) / 2, z), segs=segs, mat=mat, r2=r_top,
                        bevel=bevel, caps=caps)


def ball(name, x, y, z, r, mat=None, scale=(1, 1, 1), segs=24, rings=12, rot=None):
    """Sphere at a three.js point; scale is in three.js axes (sx, sy, sz); rot = Blender Euler deg."""
    return geo.sphere(name, r, center=B(x, y, z), segs=segs, rings=rings, scale=(scale[0], scale[2], scale[1]),
                      rot=rot, mat=mat)


def quad(name, corners, mat=None, uvs=((0, 0), (1, 0), (1, 1), (0, 1)), facing=None):
    """One quad from four three.js corners (+ per-corner UVs).  facing=(x, y, z): flip the quad so its
    normal points that way."""
    bm = bmesh.new()
    vs = [bm.verts.new(B(*c)) for c in corners]
    f = bm.faces.new(vs)
    uvl = bm.loops.layers.uv.new("UVMap")
    for loop, uv in zip(f.loops, uvs):
        loop[uvl].uv = uv
    bm.normal_update()
    if facing is not None and f.normal.dot(B(*facing)) < 0:
        bmesh.ops.reverse_faces(bm, faces=[f], flip_multires=False)
    obj = new_mesh_object(name, bm=bm)
    if mat is not None:
        obj.data.materials.append(mat)
    return obj


def spot(name, x, y, z, yaw_deg=0.0, parent=None):
    """spot_<name> empty (pass the full name, e.g. 'spot_desk_seat'), custom prop yaw in degrees."""
    return empty(name, B(x, y, z), parent=parent, props={'yaw': float(yaw_deg)}, display='SINGLE_ARROW', size=0.25)


def anchor(name, x, y, z, parent=None, **props):
    return empty(name, B(x, y, z), parent=parent, props=props or None, display='SPHERE', size=0.05)


def parent_keep(child, parent, origin=None):
    """Parent `child` to `parent` without moving it.  origin: three.js point to move the child's
    origin to first (mesh children), so its local offset is clean (e.g. a hinge / pivot)."""
    bpy.context.view_layer.update()
    if origin is not None and child.type == 'MESH':
        set_origin(child, B(*origin))
        bpy.context.view_layer.update()
    mw = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse = Matrix.Identity(4)
    child.matrix_world = mw          # basis = parent^-1 @ mw (parent matrix is up to date)
    bpy.context.view_layer.update()
    return child


def _join(objs, name):
    objs = [o for o in objs if o is not None]
    if not objs:
        return None
    return join(objs, name=name)


# ----------------------------------------------------------------------------------------------
# tabletop + base, floor
# ----------------------------------------------------------------------------------------------

def tabletop_and_base(footprints, center=(0.0, 0.0), radius=7.0, top_y=-0.10, base_top=-0.012, margin=0.04,
                      table_t=0.07, name='tabletop'):
    """Round tabletop (top surface at top_y) + rounded base slabs (exterior colour) from top_y to
    base_top under each footprint (x0, x1, z0, z1), grown by `margin`.  Returns (table, base)."""
    M = materials()
    cx, cz = center
    e = 0.035
    prof = [(0.0, -table_t), (radius - e, -table_t)]
    for i in range(1, 7):
        a = -math.pi / 2 + math.pi * i / 6
        prof.append((radius - e + e * math.cos(a), -table_t / 2 + (table_t / 2) * math.sin(a)))
    prof += [(radius - e, 0.0), (0.0, 0.0)]
    table = geo.lathe(name, prof, segs=160, center=B(cx, top_y, cz), mat=M['tabletop'])
    slabs = []
    for i, (x0, x1, z0, z1) in enumerate(footprints):
        slabs.append(rbox(f"base_{i}", x0 - margin, x1 + margin, top_y - 0.001, base_top, z0 - margin, z1 + margin,
                          r=0.022, mat=M['exterior'], segments=3))
    base = _join(slabs, 'dollhouse_base')
    return table, base


def plank_floor(name, x0, x1, z0, z1, along='z', board_w=0.15, len_range=(0.7, 1.4), seed=11, y_top=0.0,
                thick=0.012, gap=0.003, bevel=0.0028, mat=None, subfloor=True):
    """Individual floor boards (top at y_top), seeded lengths/stagger/tone, + a dark subfloor seen in
    the gaps.  along='z': boards run front-to-back; 'x': left-right."""
    M = materials()
    m = mat or M['floor']
    rng = np.random.default_rng(seed)
    if along == 'z':
        a0, a1, c0, c1 = z0, z1, x0, x1
    else:
        a0, a1, c0, c1 = x0, x1, z0, z1
    nrows = max(1, int(round((c1 - c0) / board_w)))
    w = (c1 - c0) / nrows
    boards = []
    for r in range(nrows):
        cc0 = c0 + r * w
        cc1 = cc0 + w
        # seeded cut positions; merge slivers into their neighbour
        cuts = [a0]
        pos = a0 + rng.uniform(0.15, len_range[1])
        while pos < a1 - 1e-4:
            cuts.append(pos)
            pos += rng.uniform(*len_range)
        cuts.append(a1)
        if len(cuts) > 2 and cuts[-1] - cuts[-2] < 0.18:
            cuts.pop(-2)
        if len(cuts) > 2 and cuts[1] - cuts[0] < 0.18:
            cuts.pop(1)
        k = 0
        for s, e in zip(cuts[:-1], cuts[1:]):
            band = int(rng.integers(0, PLANK_BANDS))
            off = float(rng.uniform(0, 1))
            g0 = gap / 2 if s > a0 + 1e-4 else 0.0
            g1 = gap / 2 if e < a1 - 1e-4 else 0.0
            if along == 'z':
                b = rbox(f"{name}_b{r}_{k}", cc0 + gap / 2, cc1 - gap / 2, y_top - thick, y_top, s + g0, e - g1,
                         r=bevel, mat=m, segments=1)
            else:
                b = rbox(f"{name}_b{r}_{k}", s + g0, e - g1, y_top - thick, y_top, cc0 + gap / 2, cc1 - gap / 2,
                         r=bevel, mat=m, segments=1)
            _board_uv(b, along, s, cc0, cc1, band, off)
            boards.append(b)
            k += 1
    floor = _join(boards, name)
    shade_smooth(floor, angle_deg=20)
    sub = None
    if subfloor:
        yb = y_top - thick + 0.003
        sub = quad(f"{name}_gaps", [(x0, yb, z1), (x1, yb, z1), (x1, yb, z0), (x0, yb, z0)], mat=M['subfloor'],
                   facing=(0, 1, 0))
    return floor if sub is None else _join([floor, sub], name)


def _board_uv(obj, along, start, c0, c1, band, off):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    v_hi = 1.0 - band / PLANK_BANDS
    bh = 1.0 / PLANK_BANDS
    for f in bm.faces:
        for loop in f.loops:
            x, y, z = _t3(loop.vert.co)
            a, c = (z, x) if along == 'z' else (x, z)
            t = min(1.0, max(0.0, (c - c0) / (c1 - c0)))
            loop[uvl].uv = ((a - start) / PLANK_TILE + off, v_hi - bh * (0.06 + 0.88 * t))
    bm.to_mesh(me)
    bm.free()


# ----------------------------------------------------------------------------------------------
# walls
# ----------------------------------------------------------------------------------------------

class _Frame:
    """Local wall frame: u along the wall, y up, n across (normal axis)."""

    def __init__(self, axis, at):
        self.axis, self.at = axis, at

    def p(self, u, y, n):
        return (u, y, n) if self.axis == 'x' else (n, y, u)

    def box(self, name, u0, u1, y0, y1, n0, n1, r=0.0, mat=None, segments=3, grain=None):
        g = None
        if grain == 'u':
            g = 'x' if self.axis == 'x' else 'z'
        elif grain:
            g = grain
        if self.axis == 'x':
            return rbox(name, u0, u1, y0, y1, n0, n1, r, mat, segments, grain=g)
        return rbox(name, n0, n1, y0, y1, u0, u1, r, mat, segments, grain=g)

    def u_sign(self, side):
        """+1/-1 so that wallpaper u runs left->right as seen from the `side` (+1/-1 along n)."""
        return side if self.axis == 'x' else -side


def _solid_rects(ua, ub, H, holes, cuts_extra=()):
    cuts = sorted(set([ua, ub] + [h[0] for h in holes] + [h[1] for h in holes] + list(cuts_extra)))
    cuts = [c for c in cuts if ua - 1e-9 <= c <= ub + 1e-9]
    rects = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 1e-6:
            continue
        m = (a + b) / 2
        ys = sorted((h[2], h[3]) for h in holes if h[0] < m < h[1])
        y = 0.0
        for (h0, h1) in ys:
            if h0 > y + 1e-6:
                rects.append((a, b, y, h0))
            y = max(y, h1)
        if H > y + 1e-6:
            rects.append((a, b, y, H))
    return rects


def _subtract(r0, r1, cuts):
    """[r0, r1] minus the intervals in cuts -> list of runs."""
    runs = [(r0, r1)]
    for (c0, c1) in cuts:
        nxt = []
        for (a, b) in runs:
            if c1 <= a or c0 >= b:
                nxt.append((a, b))
                continue
            if c0 > a:
                nxt.append((a, c0))
            if c1 < b:
                nxt.append((c1, b))
        runs = nxt
    return [(a, b) for (a, b) in runs if b - a > 0.02]


def wall(name, x0, z0, x1, z1, inner=+1, height=2.3, thickness=0.1, paper='wall', wainscot=True, openings=(),
         inner_range=None, outer=None, top_plate=True, casing=CASING_W, wainscot_top=WAINSCOT_TOP):
    """Axis-aligned dollhouse wall centred on (x0, z0)-(x1, z1).  See the module docstring."""
    M = materials()
    if abs(z1 - z0) < 1e-9:
        axis, at, ua, ub = 'x', z0, min(x0, x1), max(x0, x1)
    elif abs(x1 - x0) < 1e-9:
        axis, at, ua, ub = 'z', x0, min(z0, z1), max(z0, z1)
    else:
        raise ValueError("wall() needs an axis-aligned segment")
    F = _Frame(axis, at)
    t = thickness
    H = height
    sides = [dict(side=inner, paper=M[paper] if isinstance(paper, str) else paper,
                  range=inner_range or (ua, ub), wainscot=wainscot, top_plate=top_plate)]
    if outer:
        op = outer.get('paper', 'wall')
        sides.append(dict(side=-inner, paper=M[op] if isinstance(op, str) else op,
                          range=outer.get('range', (ua, ub)), wainscot=outer.get('wainscot', True),
                          top_plate=outer.get('top_plate', top_plate)))
    ops = [dict(o) for o in openings]
    holes = [(o['u0'], o['u1'], o['y0'], o['y1']) for o in ops]
    extra = [s['range'][0] for s in sides] + [s['range'][1] for s in sides]
    rects = _solid_rects(ua, ub, H, holes, extra)

    # --- core: boxes with per-face materials (0 exterior, 1.. side papers)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    mats = [M['exterior']] + [s['paper'] for s in sides]
    for (a, b, y0, y1) in rects:
        vs = {}
        for iu, u in enumerate((a, b)):
            for iy, y in enumerate((y0, y1)):
                for i_n, n in enumerate((at - t / 2, at + t / 2)):
                    vs[(iu, iy, i_n)] = bm.verts.new(B(*F.p(u, y, n)))
        quads = {
            'n+': [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
            'n-': [(1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)],
            'u+': [(1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)],
            'u-': [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
            'y+': [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)],
            'y-': [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
        }
        um = (a + b) / 2
        for tag, keys in quads.items():
            f = bm.faces.new([vs[k] for k in keys])
            f.material_index = 0
            if tag in ('n+', 'n-'):
                sgn = 1 if tag == 'n+' else -1
                for si, s in enumerate(sides):
                    if s['side'] == sgn and s['range'][0] - 1e-6 <= um <= s['range'][1] + 1e-6:
                        f.material_index = 1 + si
                        us = F.u_sign(sgn)
                        tile = CHECKS_TILE if s['paper'] is M['hall'] else WALLPAPER_TILE
                        for loop in f.loops:
                            x, y, z = _t3(loop.vert.co)
                            u = x if axis == 'x' else z
                            loop[uvl].uv = (us * u / tile, y / tile)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    core = new_mesh_object(f"{name}", bm=bm)
    for m_ in mats:
        core.data.materials.append(m_)

    trim, wain, beams = [], [], []
    k = [0]

    def nm(s):
        k[0] += 1
        return f"{name}_{s}{k[0]}"

    # --- jamb linings for doors (reveal faces)
    for o in ops:
        if o.get('kind') == 'door':
            j = 0.015
            n0, n1 = at - t / 2 - 0.002, at + t / 2 + 0.002
            trim.append(F.box(nm('jamb'), o['u0'], o['u0'] + j, 0.0, o['y1'], n0, n1, r=0.003, mat=M['trim']))
            trim.append(F.box(nm('jamb'), o['u1'] - j, o['u1'], 0.0, o['y1'], n0, n1, r=0.003, mat=M['trim']))
            trim.append(F.box(nm('jamb'), o['u0'], o['u1'], o['y1'] - j, o['y1'], n0, n1, r=0.003, mat=M['trim']))
            # threshold
            trim.append(F.box(nm('sill'), o['u0'] + j, o['u1'] - j, -0.002, 0.006, at - t / 2 - 0.01, at + t / 2 + 0.01,
                              r=0.003, mat=M['beam'], grain='u'))

    # --- per side finishes
    for s in sides:
        sd = s['side']
        face = at + sd * t / 2
        r0, r1 = s['range']

        def P(d0, d1):
            a_, b_ = face + sd * d0, face + sd * d1
            return (min(a_, b_), max(a_, b_))

        door_cuts = []
        for o in ops:
            if o['u1'] <= r0 or o['u0'] >= r1:
                continue
            if o['y0'] < wainscot_top + 0.05:
                door_cuts.append((o['u0'] - casing - 0.004, o['u1'] + casing + 0.004))
        runs = _subtract(r0, r1, door_cuts)
        if s['wainscot']:
            for (a, b) in runs:
                # backing board, raised panels, chair rail, baseboard
                wain.append(F.box(nm('wb'), a, b, BASEBOARD_H - 0.01, wainscot_top - 0.03, *P(-0.002, 0.010), r=0.003,
                                  mat=M['wainscot'], segments=1))
                L = b - a
                npan = max(1, int(round(L / 0.46)))
                stile = 0.055
                pw = (L - stile * (npan + 1)) / npan
                if pw > 0.08:
                    for i in range(npan):
                        pa = a + stile + i * (pw + stile)
                        wain.append(F.box(nm('wp'), pa, pa + pw, BASEBOARD_H + 0.07, wainscot_top - 0.10,
                                          *P(0.006, 0.018), r=0.006, mat=M['wainscot'], segments=2))
                trim.append(F.box(nm('rail'), a, b, wainscot_top - 0.045, wainscot_top, *P(-0.002, 0.032), r=0.012,
                                  mat=M['trim'], segments=3))
                trim.append(F.box(nm('rail'), a, b, wainscot_top - 0.065, wainscot_top - 0.04, *P(-0.002, 0.020),
                                  r=0.007, mat=M['trim'], segments=2))
                trim.append(F.box(nm('base'), a, b, 0.0, BASEBOARD_H, *P(-0.002, 0.024), r=0.008, mat=M['trim'],
                                  segments=2))
        else:
            for (a, b) in runs:
                trim.append(F.box(nm('base'), a, b, 0.0, BASEBOARD_H, *P(-0.002, 0.022), r=0.008, mat=M['trim'],
                                  segments=2))
        if s['top_plate']:
            beams.append(F.box(nm('plate'), r0, r1, H - 0.12, H, *P(-0.002, 0.045), r=0.01, mat=M['beam'],
                               segments=2))
            grain_uv(beams[-1], 'x' if axis == 'x' else 'z', tile=0.6)
        # casings around openings on this side
        for o in ops:
            if o['u1'] <= r0 or o['u0'] >= r1 or o.get('casing', True) is False:
                continue
            cw = casing
            u0, u1, y0, y1 = o['u0'], o['u1'], o['y0'], o['y1']
            yb = 0.0 if o.get('kind') == 'door' else y0 - 0.005
            trim.append(F.box(nm('cas'), u0 - cw, u0 + 0.004, yb, y1 + cw, *P(-0.002, 0.022), r=0.008, mat=M['trim']))
            trim.append(F.box(nm('cas'), u1 - 0.004, u1 + cw, yb, y1 + cw, *P(-0.002, 0.022), r=0.008, mat=M['trim']))
            trim.append(F.box(nm('head'), u0 - cw - 0.018, u1 + cw + 0.018, y1 + cw - 0.004, y1 + cw + 0.035,
                              *P(-0.002, 0.034), r=0.012, mat=M['trim']))
            if o.get('kind') == 'door':
                for (pa, pb) in ((u0 - cw - 0.008, u0 + 0.004), (u1 - 0.004, u1 + cw + 0.008)):
                    trim.append(F.box(nm('plinth'), pa, pb, 0.0, BASEBOARD_H + 0.04, *P(-0.002, 0.032), r=0.008,
                                      mat=M['trim']))
    out = {'core': core,
           'trim': _join(trim, f"{name}_trim"),
           'wainscot': _join(wain, f"{name}_wainscot"),
           'beam': _join(beams, f"{name}_beam")}
    return out


# ----------------------------------------------------------------------------------------------
# window
# ----------------------------------------------------------------------------------------------

def _curtain_panel(name, F, n_c, ua, ub, y_top, y_bot, side_out, mat, folds=5, amp=0.016, tie=0.42,
                   pull=0.5, nu=40, nv=22, tile=0.26):
    """Gingham panel with soft folds; gathered toward its outer edge (side_out = -1 left, +1 right
    along u) at the tie-back height."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    width = ub - ua
    H = y_top - y_bot
    grid = []
    for j in range(nv + 1):
        t = j / nv                     # 0 top -> 1 bottom
        y = y_top - t * H
        # tie-back: pull the inner edge toward the outer edge around `tie` (fraction from the bottom)
        yt = 1.0 - tie
        g = math.exp(-((t - yt) / 0.22) ** 2)
        wf = 1.0 - pull * g
        flare = 1.0 + 0.10 * max(0.0, t - yt) / max(1e-6, 1 - yt) * (1 - g)
        row = []
        for i in range(nu + 1):
            s = i / nu                 # 0 at outer edge -> 1 inner edge
            ww = width * wf * min(1.15, flare)
            if side_out < 0:
                u = ua + s * ww
            else:
                u = ub - s * ww
            a = amp * (1.0 + 0.25 * g) * (0.55 + 0.45 * t)
            n = n_c + a * math.sin(2 * math.pi * folds * s + 0.6)
            p = F.p(u, y, n)
            row.append(bm.verts.new(B(*p)))
        grid.append(row)
    for j in range(nv):
        for i in range(nu):
            f = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
            for loop, (ii, jj) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                loop[uvl].uv = (ii / nu * width / tile, (1 - jj / nv) * H / tile)
    bm.normal_update()
    obj = new_mesh_object(name, bm=bm)
    obj.data.materials.append(mat)
    shade_smooth(obj)
    return obj


def window(name, axis, at, u0, u1, y0, y1, inner=+1, thickness=0.1, curtains=True, rod=True, sky=True,
           mull_u=1, mull_y=1, frame_w=0.042, sky_margin=0.25, curtain_mat=None, rod_y=None, u_limits=None,
           height=2.3):
    """Window furniture for an opening already cut by wall(): frame + mullions, reveal lining, sill +
    apron, emissive sky card, gingham curtains (with tie-backs) on a wooden rod.
    The sky card sits INSIDE the wall thickness (6 mm in from the outer face), so it is only ever seen
    through the opening and can never poke out past a cut wall end; u_limits=(umin, umax) clamps it
    to the wall's extent along u (pass the wall's u range), height = wall height.
    Returns dict of objects."""
    M = materials()
    F = _Frame(axis, at)
    t = thickness
    sd = inner
    face = at + sd * t / 2
    back = at - sd * t / 2
    out = {}
    trim = []
    k = [0]

    def nm(s):
        k[0] += 1
        return f"{name}_{s}{k[0]}"

    def N(d0, d1, base=face):
        a_, b_ = base + sd * d0, base + sd * d1
        return (min(a_, b_), max(a_, b_))

    # reveal lining (cream) over the whole reveal depth
    j = 0.012
    n_rev = (min(back, face) - 0.001, max(back, face) + 0.001)
    trim.append(F.box(nm('rv'), u0, u0 + j, y0, y1, *n_rev, r=0.003, mat=M['trim']))
    trim.append(F.box(nm('rv'), u1 - j, u1, y0, y1, *n_rev, r=0.003, mat=M['trim']))
    trim.append(F.box(nm('rv'), u0, u1, y1 - j, y1, *n_rev, r=0.003, mat=M['trim']))
    # frame ring + mullions at the middle of the wall
    fn = (at - 0.03, at + 0.03)
    fw = frame_w
    trim.append(F.box(nm('fr'), u0 + j, u0 + j + fw, y0, y1 - j, *fn, r=0.008, mat=M['trim']))
    trim.append(F.box(nm('fr'), u1 - j - fw, u1 - j, y0, y1 - j, *fn, r=0.008, mat=M['trim']))
    trim.append(F.box(nm('fr'), u0 + j, u1 - j, y1 - j - fw, y1 - j, *fn, r=0.008, mat=M['trim']))
    trim.append(F.box(nm('fr'), u0 + j, u1 - j, y0, y0 + fw, *fn, r=0.008, mat=M['trim']))
    mn = (at - 0.02, at + 0.02)
    ia, ib, ja, jb = u0 + j + fw, u1 - j - fw, y0 + fw, y1 - j - fw
    for i in range(1, mull_u + 1):
        uc = ia + (ib - ia) * i / (mull_u + 1)
        trim.append(F.box(nm('mu'), uc - 0.012, uc + 0.012, ja, jb, *mn, r=0.006, mat=M['trim']))
    for i in range(1, mull_y + 1):
        yc = ja + (jb - ja) * i / (mull_y + 1)
        trim.append(F.box(nm('mu'), ia, ib, yc - 0.012, yc + 0.012, *mn, r=0.006, mat=M['trim']))
    # sill (stool) + apron
    trim.append(F.box(nm('sill'), u0 - 0.07, u1 + 0.07, y0 - 0.034, y0 + 0.004, *N(-(t / 2), 0.066),
                      r=0.012, mat=M['trim']))
    trim.append(F.box(nm('apron'), u0 - 0.035, u1 + 0.035, y0 - 0.034 - 0.06, y0 - 0.03, *N(-0.002, 0.022),
                      r=0.008, mat=M['trim']))
    out['trim'] = _join(trim, f"{name}_frame")

    if sky:
        nb = back + sd * 0.006                  # inside the wall solid, behind the frame
        m = sky_margin
        my = min(m, 0.15)
        us = F.u_sign(sd)
        lo, hi = u0 - m, u1 + m
        if u_limits:   # keep the card inside the wall's extent (e.g. near an open cut end)
            lo, hi = max(lo, u_limits[0] + 0.01), min(hi, u_limits[1] - 0.01)
        ya, yb = max(0.01, y0 - my), min(height - 0.01, y1 + my)
        a_, b_ = (lo, hi) if us > 0 else (hi, lo)
        corners = [F.p(a_, ya, nb), F.p(b_, ya, nb), F.p(b_, yb, nb), F.p(a_, yb, nb)]
        out['sky'] = quad(f"{name}_sky", corners, mat=M['sky'], facing=F.p(0, 0, sd))
    ry = rod_y if rod_y is not None else y1 + 0.13
    rn = face + sd * 0.095
    if rod:
        ra, rb = u0 - 0.18, u1 + 0.18
        parts = [cyl(nm('rod'), F.p(ra, ry, rn), F.p(rb, ry, rn), 0.011, mat=M['rod'], segs=16)]
        for uu, sg in ((ra, -1), (rb, 1)):
            parts.append(ball(nm('fin'), *F.p(uu + sg * 0.018, ry, rn), 0.022, mat=M['rod'], segs=18, rings=10))
            parts.append(cyl(nm('col'), F.p(uu - sg * 0.004, ry, rn), F.p(uu + sg * 0.006, ry, rn), 0.016,
                             mat=M['rod'], segs=16))
        for uu in (u0 - 0.10, u1 + 0.10):
            parts.append(F.box(nm('brk'), uu - 0.012, uu + 0.012, ry - 0.03, ry + 0.012, *N(-0.002, 0.095),
                               r=0.006, mat=M['rod'], segments=2))
        # rings
        ring_us = []
        if curtains:
            for (pa, pb) in ((u0 - 0.16, u0 + 0.13), (u1 - 0.13, u1 + 0.16)):
                for i in range(6):
                    ring_us.append(pa + 0.012 + (pb - pa - 0.024) * i / 5)
        for uu in ring_us:
            rot = (0, 90, 0) if axis == 'x' else (90, 0, 0)
            parts.append(geo.torus(nm('ring'), R=0.017, r=0.0035, center=B(*F.p(uu, ry, rn)), rot=rot, major=16,
                                   minor=6, mat=M['rod']))
        out['rod'] = _join(parts, f"{name}_rod")
    if curtains:
        cm = curtain_mat or M['curtain']
        top = ry - 0.012
        bot = y0 - 0.12
        cn = rn
        out['curtain_l'] = _curtain_panel(f"{name}_curtain_L", F, cn, u0 - 0.16, u0 + 0.13, top, bot, -1, cm)
        out['curtain_r'] = _curtain_panel(f"{name}_curtain_R", F, cn, u1 - 0.13, u1 + 0.16, top, bot, +1, cm)
        out['curtains'] = _join([out.pop('curtain_l'), out.pop('curtain_r')], f"{name}_curtains")
        # tie-back bands around the gathered waist (tie = 0.42 of the height from the bottom)
        yt = bot + 0.42 * (top - bot)
        ties = []
        for (ua, ub, so) in ((u0 - 0.16, u0 + 0.13, -1), (u1 - 0.13, u1 + 0.16, +1)):
            wg = (ub - ua) * 0.5
            a_, b_ = (ua - 0.012, ua + wg + 0.012) if so < 0 else (ub - wg - 0.012, ub + 0.012)
            ties.append(F.box(nm('tie'), a_, b_, yt - 0.02, yt + 0.02, *N(0.095 - 0.03, 0.095 + 0.03), r=0.017,
                              mat=M['curtain_tie'], segments=3))
        out['ties'] = _join(ties, f"{name}_tiebacks")
    return out


# ----------------------------------------------------------------------------------------------
# door
# ----------------------------------------------------------------------------------------------

def _axis_rot(axis3, sign):
    """Blender Euler (deg) turning local +Z to the three.js axis ('x'|'z') * sign."""
    if axis3 == 'x':
        return (0, 90 * sign, 0)
    return (90 * sign, 0, 0)  # three +z == Blender -Y: R_x(+90) maps +Z -> -Y


def door(name='door', axis='z', at=-2.6, u0=-1.125, u1=-0.275, height=1.75, inner=+1, thickness=0.1,
         hinge_u=None, hinge_name='door_hinge', leaf_t=0.04, jamb=0.015, knob_h=0.92):
    """Raised-panel door hung on an empty at the inner wall face (see module docstring)."""
    M = materials()
    F = _Frame(axis, at)
    face = at + inner * thickness / 2
    hu = (u0 + 0.025) if hinge_u is None else hinge_u
    d = 1 if (u1 - hu) > (hu - u0) else -1
    free_u = (u1 - jamb - 0.006) if d > 0 else (u0 + jamb + 0.006)
    la, lb = sorted((hu + d * 0.004, free_u))
    yb, yt = 0.01, height - jamb - 0.005
    n_room, n_back = face, face - inner * leaf_t
    nlo, nhi = min(n_room, n_back), max(n_room, n_back)
    parts = [F.box(f"{name}_leaf", la, lb, yb, yt, nlo, nhi, r=0.008, mat=M['door'], segments=3)]
    # raised panels on both faces (2 columns x 2 rows)
    W = lb - la
    mg, gp = 0.085, 0.07
    pw = (W - 2 * mg - gp) / 2
    rows = [(yb + 0.13, yb + 0.68), (yb + 0.80, yt - 0.11)]
    for side in (+1, -1):
        nf = n_room if side == +1 else n_back
        sgn = inner * side
        pn = sorted((nf - sgn * 0.002, nf + sgn * 0.009))
        fn = sorted((nf - sgn * 0.002, nf + sgn * 0.004))
        for c in range(2):
            pa = la + mg + c * (pw + gp)
            for (ya, yb_) in rows:
                parts.append(F.box(f"{name}_pf", pa - 0.018, pa + pw + 0.018, ya - 0.018, yb_ + 0.018, *fn, r=0.004,
                                   mat=M['door'], segments=2))
                parts.append(F.box(f"{name}_pn", pa, pa + pw, ya, yb_, *pn, r=0.007, mat=M['door'], segments=2))
    leaf = _join(parts, f"{name}_panel")
    # knobs (both faces)
    ku = free_u - d * 0.075
    prof_rose = [(0.0, 0.0), (0.03, 0.0), (0.03, 0.004), (0.024, 0.009), (0.0, 0.009)]
    prof_knob = [(0.0, 0.0), (0.009, 0.0), (0.008, 0.025), (0.016, 0.03), (0.026, 0.045), (0.027, 0.055),
                 (0.022, 0.066), (0.012, 0.071), (0.0, 0.072)]
    kparts = []
    for side in (+1, -1):
        nf = n_room if side == +1 else n_back
        sgn = inner * side
        ax = 'x' if axis == 'z' else 'z'
        rot = _axis_rot(ax, sgn)
        c = B(*F.p(ku, knob_h, nf - sgn * 0.001))
        kparts.append(geo.lathe(f"{name}_rose", prof_rose, segs=24, center=c, rot=rot, mat=M['brass']))
        kparts.append(geo.lathe(f"{name}_knob", prof_knob, segs=24, center=c, rot=rot, mat=M['brass']))
    # hinge pins on the axis
    for yy in (0.28, height - 0.32):
        p = F.p(hu, yy, face)
        kparts.append(cyl_y(f"{name}_pin", p[0], p[2], yy - 0.05, yy + 0.05, 0.009, mat=M['brass'], segs=12))
    knob = _join(kparts, f"{name}_knob")
    hp = F.p(hu, 0.0, face)
    if axis == 'z':
        open_sign = d * inner
    else:
        open_sign = -d * inner
    hinge = empty(hinge_name, B(*hp), props={'open_sign': int(open_sign), 'max_open_deg': 100.0},
                  display='ARROWS', size=0.2)
    parent_keep(leaf, hinge, origin=hp)
    parent_keep(knob, hinge, origin=hp)
    return hinge


# ----------------------------------------------------------------------------------------------
# beams
# ----------------------------------------------------------------------------------------------

def post(name, x, z, y0=0.0, y1=2.3, w=0.09, d=None, mat=None, r=0.01):
    d = d or w
    return rbox(name, x - w / 2, x + w / 2, y0, y1, z - d / 2, z + d / 2, r=r, mat=mat or materials()['beam'],
                segments=2, grain='y', tile=0.6)


def beam(name, x0, x1, y0, y1, z0, z1, mat=None, r=0.008):
    ext = {'x': abs(x1 - x0), 'y': abs(y1 - y0), 'z': abs(z1 - z0)}
    g = max(ext, key=ext.get)
    return rbox(name, x0, x1, y0, y1, z0, z1, r=r, mat=mat or materials()['beam'], segments=2, grain=g, tile=0.6)
