"""Kitchen set (scene 001, beats 3-4): a Sylvanian-style dollhouse kitchen cutaway.

Placed at the world origin on the same round tabletop + base slab as the office (floor y = 0).
Room x -2.2 .. 2.2, z -1.9 .. 1.25, walls 2.3 high / 0.1 thick, open at the front (+z) and right (+x).

Staging: Tim washes dishes FACING THE CAMERA at a central island sink (spot_sink), the window is
behind him, GuoGuo sits on the back counter to the right of the window (spot_guoguo).

The island is chibi height (top y 0.50, Tim's hip/wrist height) so Tim's short arms reach into the
basin; the back run stays at 0.62.  Work layout for Tim's dish cycle (all within his arm reach):
dirty stack on his left beside the basin, drying rack further left, gooseneck spout over the work patch.

Spots (empties, extras `yaw` in degrees):
  spot_sink (0.36, 0, -0.42) yaw 0 · spot_guoguo (1.05, 0.62, -1.62) yaw -15 ·
  spot_plate_stack (0.635, 0.50, -0.13) · spot_rack (0.825, 0.50, -0.10) ·
  spot_rack_1/2/3 = drying-rack slots at x 0.785 / 0.825 / 0.865, z -0.10, on the slot floor (y 0.516); an
  upright plate (facing +-x, yaw 90) lifted by its radius has its centre at y 0.627 (extra plate_centre_y).
Hooks: faucet_spout (empty at the spout tip), sink_foam (empty at the water line) with the merged foam
mesh sink_foam_base, sink_water / sink_water_deep (translucent water sheets), light_window (empty just
inside the window).
"""
import math

import bmesh
import numpy as np
from mathutils import Euler, Matrix, Vector

from lib.core import B, join, empty, apply_modifiers, remove, shade_smooth, set_origin, voxel_remesh, decimate
from lib import geo, mat, tex

try:  # shared dollhouse builders; optional
    from items import dollhouse_kit as kit  # noqa: F401
except Exception:  # pragma: no cover - fallback shell below
    kit = None

ITEM = {"id": "sets/kitchen", "out": "sets/kitchen.glb"}
ANIMATIONS = False

# ---- layout (three.js coordinates, metres) ------------------------------------------------
TOP_Y = 0.62          # counter tops (back run)
CT_T = 0.05           # countertop thickness
KICK = 0.07           # toe-kick height
ISL = (-0.55, 1.15, -0.25, 0.30)   # island top x0, x1, z0, z1
# The island is a chibi-height work island: its top sits at Tim's hip/wrist height so his short arms
# reach INTO the basin (Tim: hips 0.44, shoulders 0.78, arm ~0.36 incl. the mitten).
ISL_TOP = 0.50
TIM_X, TIM_Z = 0.36, -0.42          # spot_sink: Tim's belly (z +0.16) just behind the island edge
SINK_X, SINK_Z = 0.30, -0.05
SINK_A, SINK_B, SINK_N = 0.19, 0.15, 4.0   # inner rim half sizes, superellipse exponent
SINK_DEPTH = 0.14
RIM_Y = ISL_TOP + 0.008
WATER_Y = RIM_Y - 0.040
FAUCET_Z = -0.10                    # swing-arm faucet: base left of the basin, arm along +x
STACK_XZ = (0.635, -0.13)           # dirty stack: left of the basin, within Tim's left-hand reach
BACK_Z0, BACK_Z1 = -1.85, -1.30     # back counter (wall face .. top front edge)
BACK_X0, BACK_X1 = -2.06, 1.80     # starts after the corner post (x -2.15 .. -2.06)
ROOM = dict(x0=-2.2, x1=2.2, z0=-1.9, z1=1.25)
WALL_H, WALL_T = 2.3, 0.1
POST_W = 0.09
WIN = (0.0, 0.8, 0.95, 1.65)        # window opening x0, x1, y0, y1 (back wall)
UPPER_Y = (1.30, 1.98)
UPPER_L = (-1.00, -0.24)
UPPER_R = (1.04, 1.80)
GAP = 0.008           # gap between cabinet fronts
FT = 0.02             # front thickness

PAL = dict(
    wall="#efe5d1", dot1="#d9ad9f", dot2="#a9b897", wainscot="#b9c3a8", trim="#f5efe3", floor="#c9a47c",
    beam="#b98e67", exterior="#e3d5bf", brass="#c8a66a", wood="#d9b68e", wood_dark="#b8916b",
    plant="#93a77f", plant_dark="#7c9169", pot="#c99a7a", tabletop="#d8ccba",
    cabinet="#f2ebdd", door="#b9c3a8", kick="#a3ad92", sink="#f5f2ea", tile="#f5efe3",
    check1="#f1e8d8", check2="#b9c3a8", enamel="#f7f2e8", coral="#d9917c", fridge="#ecc8ba",
)

_names = {}


def nm(base):
    _names[base] = _names.get(base, 0) + 1
    return f"{base}_{_names[base]:02d}"


# ---- small geometry helpers (three.js coordinates in, Blender out) -------------------------

def tbox(name, x0, x1, y0, y1, z0, z1, m, r=0.0, seg=3):
    """Axis-aligned (optionally rounded) box from three.js extents."""
    size = (abs(x1 - x0), abs(z1 - z0), abs(y1 - y0))
    c = B((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    if r <= 0:
        return geo.box(name, size, center=c, mat=m)
    return geo.rounded_box(name, size, r, center=c, segments=seg, mat=m)


def tcyl(name, x, y0, y1, z, r, m, r2=None, segs=32, bevel=0.0):
    """Vertical (three.js y) cylinder from y0 to y1."""
    return geo.cylinder(name, r=r, depth=y1 - y0, center=B(x, (y0 + y1) / 2, z), r2=r2, segs=segs,
                        bevel=bevel, mat=m)


def chaikin(pts, iters=2):
    pts = [tuple(p) for p in pts]
    for _ in range(iters):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            out.append(tuple(0.75 * pa + 0.25 * pb for pa, pb in zip(a, b)))
            out.append(tuple(0.25 * pa + 0.75 * pb for pa, pb in zip(a, b)))
        out.append(pts[-1])
        pts = out
    return pts


def ttube(name, pts, r, m, segs=12, smooth_iters=2, caps=True, round_caps=True):
    """Tube along a three.js polyline (corners rounded with Chaikin)."""
    p = chaikin(pts, smooth_iters) if smooth_iters else pts
    return geo.tube(name, [B(*q) for q in p], radius=r, segs=segs, mat=m, caps=caps, round_caps=round_caps)


def se_prism(name, cx, cz, a, b, y0, y1, n=SINK_N, N=96):
    c = B(cx, 0, cz)
    r0 = geo.superellipse(c.x, c.y, y0, a, b, n, N)
    r1 = geo.superellipse(c.x, c.y, y1, a, b, n, N)
    return geo.loft(name, [r0, r1], cap_start=True, cap_end=True, smooth=False)


def bool_cut(obj, cutter, solver='EXACT'):
    m = obj.modifiers.new("cut", 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.solver = solver
    m.object = cutter
    apply_modifiers(obj)
    return obj


def orient_up(obj, below_z):
    """Make faces below Blender z `below_z` point up (+Z); flips the whole (open) mesh if needed."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    probe = [f for f in bm.faces if f.calc_center_median().z < below_z]
    if probe and sum(f.normal.z for f in probe) < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    me.update()
    return obj


def set_uv_scale(obj, su, sv, ou=0.0, ov=0.0):
    me = obj.data
    uvl = me.uv_layers.active
    for d in uvl.data:
        d.uv = (d.uv[0] * su + ou, d.uv[1] * sv + ov)
    return obj


# ---- textures ------------------------------------------------------------------------------

def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def _mix(img, col, a):
    a = np.clip(a, 0, 1)[..., None]
    return img * (1 - a) + tex.rgb(col)[None, None, :] * a


def deco_plate_texture(rim, dot, size=256, base="#f6f1e6"):
    """Decorative wall plate, top view (UV half size = plate radius): coloured rim band, a dotted
    ring and a 5-petal flower in the middle.  Wordless."""
    yy, xx = (np.mgrid[0:size, 0:size] + 0.5) / size * 2 - 1
    r = np.sqrt(xx * xx + yy * yy)
    px = 2.0 / size
    img = np.ones((size, size, 3), np.float32) * tex.rgb(base)[None, None, :]
    img = _mix(img, rim, np.clip((r - 0.80) / px, 0, 1) * np.clip((0.95 - r) / px, 0, 1))
    img = _mix(img, rim, np.clip(1 - np.abs(r - 0.72) / (px * 1.5), 0, 1) * 0.8)
    for k in range(16):
        a = 2 * math.pi * k / 16
        d = np.sqrt((xx - 0.6 * math.cos(a)) ** 2 + (yy - 0.6 * math.sin(a)) ** 2)
        img = _mix(img, dot, np.clip((0.035 - d) / px, 0, 1))
    for k in range(5):
        a = 2 * math.pi * k / 5 + 0.3
        d = np.sqrt((xx - 0.17 * math.cos(a)) ** 2 + (yy - 0.17 * math.sin(a)) ** 2)
        img = _mix(img, dot, np.clip((0.13 - d) / px, 0, 1))
    img = _mix(img, "#f3d98b", np.clip((0.075 - r) / px, 0, 1))
    return np.clip(img, 0, 1)


def drawing_texture(w=128, h=160):
    """A child's crayon drawing for the fridge door: sun, hill, little house.  Wordless."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.ones((h, w, 3), np.float32) * tex.rgb("#fdfaf2")[None, None, :]
    d = np.sqrt((xx - 38) ** 2 + (yy - 40) ** 2)
    img = _mix(img, "#f2c94c", np.clip(15 - d, 0, 1))
    for k in range(8):
        a = 2 * math.pi * k / 8
        for s in np.linspace(20, 28, 6):
            dd = np.sqrt((xx - 38 - s * math.cos(a)) ** 2 + (yy - 40 - s * math.sin(a)) ** 2)
            img = _mix(img, "#f2c94c", np.clip(2.2 - dd, 0, 1))
    hill = np.clip(yy - (118 + 10 * np.sin(xx / w * 3.2 + 0.4)), 0, 1)
    img = _mix(img, "#9cc27e", hill)
    house = (np.abs(xx - 88) < 15) & (yy > 92) & (yy < 120)
    img = _mix(img, "#e08a78", house.astype(np.float32))
    roof = (yy > 72) & (yy <= 92) & (np.abs(xx - 88) < (yy - 72) * 1.0)
    img = _mix(img, "#a67b5b", roof.astype(np.float32))
    door_ = (np.abs(xx - 88) < 4) & (yy > 106) & (yy < 120)
    img = _mix(img, "#7a5236", door_.astype(np.float32))
    edge = ((xx < 3) | (xx > w - 4) | (yy < 3) | (yy > h - 4)).astype(np.float32)
    img = _mix(img, "#efe6d2", edge * 0.8)
    return np.clip(img, 0, 1)


def butcher_block(size=512, seed=41, base="#d9b68e", strips=20):
    """Wood grain along U with glued strips (butcher block) - tileable."""
    img = tex.wood_grain(base, size=size, seed=seed, rings=13, contrast=0.13)
    rng = np.random.default_rng(seed)
    edges = np.linspace(0, size, strips + 1).astype(int)
    for i in range(strips):
        img[edges[i]:edges[i + 1]] *= rng.uniform(0.92, 1.06)
        img[edges[i]:edges[i] + 1] *= 0.84
    return np.clip(img, 0, 1)


def tiles_texture(size=512, n=4, seed=43, tile="#f5efe3", grout="#b9c3a8", grout_px=4.0):
    """Square glazed tiles with thin sage grout (n x n tiles per image)."""
    h = w = size
    yy, xx = (np.mgrid[0:h, 0:w] + 0.5) / size
    ix = np.floor(xx * n).astype(int)
    iy = np.floor(yy * n).astype(int)
    fx = (xx * n) % 1.0
    fy = (yy * n) % 1.0
    rng = np.random.default_rng(seed)
    tone = rng.uniform(0.975, 1.02, (n, n)).astype(np.float32)
    img = tex.rgb(tile)[None, None, :] * tone[iy, ix][..., None]
    cell = size / n
    edge = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy)) * cell   # px to the tile edge
    img *= (0.94 + 0.06 * _smoothstep(grout_px * 0.5, grout_px * 0.5 + 10, edge))[..., None]
    # soft glaze highlight toward the upper-left of each tile
    img *= (1.0 + 0.025 * (1 - fy) * (1 - fx))[..., None]
    g = np.clip(grout_px * 0.5 - edge + 0.5, 0, 1)[..., None]
    img = img * (1 - g) + tex.rgb(grout)[None, None, :] * g
    return np.clip(img, 0, 1)


def checker_floor(size=512, n=4, seed=45, c1="#f1e8d8", c2="#b9c3a8", line="#a3ad92"):
    h = w = size
    yy, xx = (np.mgrid[0:h, 0:w] + 0.5) / size
    ix = np.floor(xx * n).astype(int)
    iy = np.floor(yy * n).astype(int)
    m = ((ix + iy) % 2).astype(np.float32)[..., None]
    img = tex.rgb(c1)[None, None, :] * (1 - m) + tex.rgb(c2)[None, None, :] * m
    rng = np.random.default_rng(seed)
    tone = rng.uniform(0.975, 1.02, (n, n)).astype(np.float32)
    img *= tone[iy, ix][..., None]
    nz = tex.value_noise(w, h, 16, 16, seed + 1, octaves=3)
    img *= (0.975 + 0.05 * nz)[..., None]
    fx = (xx * n) % 1.0
    fy = (yy * n) % 1.0
    edge = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy)) * (size / n)
    g = np.clip(1.5 - edge, 0, 1)[..., None] * 0.55
    img = img * (1 - g) + tex.rgb(line)[None, None, :] * g
    return np.clip(img, 0, 1)


# ---- materials -----------------------------------------------------------------------------

def materials():
    P = PAL
    M = {}
    M["counter"] = mat.wood("counter", P["wood"], image=mat.image_from_array("butcher_block", butcher_block()))
    M["wood_dark"] = mat.wood("dark", P["wood_dark"],
                              image=mat.image_from_array("grain_dark", tex.wood_grain(P["wood_dark"], seed=47)))
    M["wood"] = mat.wood("light", P["wood"], image=mat.image_from_array("grain_light",
                                                                      tex.wood_grain(P["wood"], seed=49)))
    M["cabinet"] = mat.prop("cabinet", P["cabinet"])
    M["door"] = mat.prop("cabinet_door", P["door"])
    M["kick"] = mat.prop("toe_kick", P["kick"])
    M["trim"] = mat.prop("trim", P["trim"])
    M["brass"] = mat.metal("brass", P["brass"], roughness=0.35)
    M["faucet"] = mat.metal("faucet", P["brass"], roughness=0.25)
    M["sink"] = mat.ceramic("sink", P["sink"])
    M["water"] = mat.material("water_surface", "#a9c6cc", roughness=0.06, alpha=0.42, coat=0.6,
                              coat_roughness=0.05)
    M["water_deep"] = mat.material("water_deep", "#c9d9da", roughness=0.4, alpha=0.5)
    M["foam"] = mat.material("foam", "#f6f7f4", roughness=0.88, sheen=0.35, sheen_roughness=0.5)
    M["tiles"] = mat.ceramic("tiles", P["tile"], image=mat.image_from_array("tiles", tiles_texture()))
    M["floor"] = mat.prop("floor_checker", P["check1"], image=mat.image_from_array("checker", checker_floor()))
    M["enamel"] = mat.ceramic("enamel", P["enamel"])
    M["ink"] = mat.ink("burner", "#3b3633")
    M["oven_glass"] = mat.ink("oven_glass", "#4a4542")
    M["coral"] = mat.ceramic("coral", P["coral"])
    M["soap"] = mat.ceramic("soap", "#c9d8bf")
    M["cap_hot"] = mat.ceramic("cap_hot", "#e08a78")
    M["cap_cold"] = mat.ceramic("cap_cold", "#8fb3d1")
    M["towel"] = mat.fabric("towel", "#f7f1e6", image=mat.image_from_array(
        "towel_check", tex.gingham(base="#f7f1e6", check=(201, 139, 124), alpha=0.55, size=256, bands=8)))
    M["tabletop"] = mat.prop("tabletop", P["tabletop"])
    M["exterior"] = mat.prop("exterior", P["exterior"])
    M["tile_a"] = mat.prop("floor_tile_cream", P["check1"])
    M["tile_b"] = mat.prop("floor_tile_sage", P["check2"])
    M["grout"] = mat.prop("floor_grout", "#8f977f")
    M["fridge"] = mat.ceramic("fridge", P["fridge"])
    M["jar_cream"] = mat.ceramic("jar_cream", "#f3ead8")
    M["jar_sage"] = mat.ceramic("jar_sage", "#b9c3a8")
    M["jar_pink"] = mat.ceramic("jar_pink", "#d9ad9f")
    M["glass"] = mat.glass("jar", "#eef4f2", alpha=0.3)
    M["pasta"] = mat.prop("pasta", "#e9c98c")
    M["clock_face"] = mat.prop("clock_face", "#fbf6ea")
    M["steel"] = mat.metal("steel", "#c9c6c0", roughness=0.35)
    M["plant"] = mat.prop("leaf", P["plant"])
    M["plant_dark"] = mat.prop("leaf_dark", P["plant_dark"])
    M["pot"] = mat.ceramic("pot", P["pot"])
    M["soil"] = mat.prop("soil", "#6e5442")
    M["magnet_a"] = mat.vinyl("magnet_a", "#e08a78")
    M["magnet_b"] = mat.vinyl("magnet_b", "#8fb3d1")
    M["magnet_c"] = mat.vinyl("magnet_c", "#f2d36b")
    M["apple"] = mat.vinyl("apple", "#e07b6a")
    M["lemon"] = mat.vinyl("lemon", "#f2d36b")
    M["paper"] = mat.prop("drawing", "#ffffff", image=mat.image_from_array("drawing", drawing_texture()))
    for k, (rim, dot) in {"deco_a": ("#a9b897", "#d9ad9f"), "deco_b": ("#d9ad9f", "#a9b897"),
                          "deco_c": ("#9fb9d0", "#f2d36b")}.items():
        M[k] = mat.ceramic(f"plate_{k}", "#f6f1e6", image=mat.image_from_array(k, deco_plate_texture(rim, dot)))
    return M


# ---- cabinet parts -------------------------------------------------------------------------

KNOB_PROFILE = [(0.0, 0.0), (0.0065, 0.0), (0.0055, 0.006), (0.0085, 0.011), (0.0125, 0.0155),
                (0.0135, 0.0195), (0.011, 0.024), (0.006, 0.026), (0.0, 0.0265)]


def knob_z(x, y, zf, m, s=1.0):
    """Brass mushroom knob on a +z facing surface at z = zf."""
    prof = [(r * s, h * s) for r, h in KNOB_PROFILE]
    return geo.lathe(nm("knob"), prof, segs=20, center=B(x, y, zf), rot=(90, 0, 0), mat=m)


def knob_x(xf, y, z, m, s=1.0):
    """Knob on a +x facing surface at x = xf."""
    prof = [(r * s, h * s) for r, h in KNOB_PROFILE]
    return geo.lathe(nm("knob"), prof, segs=20, center=B(xf, y, z), rot=(0, 90, 0), mat=m)


def bar_pull(cx, cy, zf, m, half=0.04, out=0.02, r=0.0045):
    pts = [(cx - half, cy, zf), (cx - half, cy, zf + out), (cx + half, cy, zf + out), (cx + half, cy, zf)]
    return ttube(nm("pull"), pts, r, m, segs=10, smooth_iters=3)


def door(x0, x1, y0, y1, zf, M, out, inset=0.034):
    out.append(tbox(nm("door"), x0, x1, y0, y1, zf, zf + FT, M["door"], r=0.006))
    if x1 - x0 > 2 * inset + 0.04 and y1 - y0 > 2 * inset + 0.04:
        out.append(tbox(nm("door_panel"), x0 + inset, x1 - inset, y0 + inset, y1 - inset,
                        zf + FT - 0.003, zf + FT + 0.0055, M["door"], r=0.009))


def drawer(x0, x1, y0, y1, zf, M, out, hw):
    out.append(tbox(nm("drawer"), x0, x1, y0, y1, zf, zf + FT, M["door"], r=0.006))
    ins = 0.022
    if y1 - y0 > 2 * ins + 0.03:
        out.append(tbox(nm("drawer_panel"), x0 + ins, x1 - ins, y0 + ins, y1 - ins,
                        zf + FT - 0.003, zf + FT + 0.0045, M["door"], r=0.008))
    hw.append(bar_pull((x0 + x1) / 2, (y0 + y1) / 2, zf + FT + 0.0045, M["brass"],
                       half=min(0.045, (x1 - x0) * 0.2)))


DRAWER_H = 0.115


def bay(kind, x0, x1, y0, y1, zf, M, fronts, hw):
    """Fill one cabinet bay (front face at z = zf, facing +z)."""
    g = GAP / 2
    xa, xb, cx = x0 + g, x1 - g, (x0 + x1) / 2
    zk = zf + FT + 0.005
    if kind == 'd':
        door(xa, xb, y0 + g, y1 - g, zf, M, fronts)
        hw.append(knob_z(xb - 0.042, y1 - 0.075, zk, M["brass"]))
    elif kind == 'dl':
        door(xa, xb, y0 + g, y1 - g, zf, M, fronts)
        hw.append(knob_z(xa + 0.042, y1 - 0.075, zk, M["brass"]))
    elif kind == '2d':
        door(xa, cx - g, y0 + g, y1 - g, zf, M, fronts)
        door(cx + g, xb, y0 + g, y1 - g, zf, M, fronts)
        hw.append(knob_z(cx - 0.042, y1 - 0.075, zk, M["brass"]))
        hw.append(knob_z(cx + 0.042, y1 - 0.075, zk, M["brass"]))
    elif kind == 'dd':
        yd = y1 - DRAWER_H
        drawer(xa, xb, yd + g, y1 - g, zf, M, fronts, hw)
        door(xa, xb, y0 + g, yd - g, zf, M, fronts)
        hw.append(knob_z(xb - 0.042, yd - 0.065, zk, M["brass"]))
    elif kind == 'ddd':
        hs = np.linspace(y0, y1, 4)
        for a, b in zip(hs[:-1], hs[1:]):
            drawer(xa, xb, a + g, b - g, zf, M, fronts, hw)
    elif kind == '2d2d':
        yd = y1 - DRAWER_H
        drawer(xa, cx - g, yd + g, y1 - g, zf, M, fronts, hw)
        drawer(cx + g, xb, yd + g, y1 - g, zf, M, fronts, hw)
        door(xa, cx - g, y0 + g, yd - g, zf, M, fronts)
        door(cx + g, xb, y0 + g, yd - g, zf, M, fronts)
        hw.append(knob_z(cx - 0.042, yd - 0.065, zk, M["brass"]))
        hw.append(knob_z(cx + 0.042, yd - 0.065, zk, M["brass"]))
    else:
        raise ValueError(kind)


# ---- island + sink -------------------------------------------------------------------------

def sink_cutter():
    return se_prism("sink_cutter", SINK_X, SINK_Z, SINK_A + 0.008, SINK_B + 0.008, ISL_TOP - 0.22, ISL_TOP + 0.08)


def island(M):
    x0, x1, z0, z1 = ISL
    ins = 0.025
    bx0, bx1, bz0, bz1 = x0 + ins, x1 - ins, z0 + ins, z1 - ins
    body = tbox("island_body", bx0, bx1, KICK, ISL_TOP - CT_T, bz0, bz1, M["cabinet"])
    kick = tbox("island_kick", bx0 + 0.035, bx1 - 0.035, 0.0, KICK + 0.002, bz0 + 0.035, bz1 - 0.035, M["kick"])
    top = tbox("island_top", x0, x1, ISL_TOP - CT_T, ISL_TOP, z0, z1, M["counter"], r=0.012)
    cut = sink_cutter()
    bool_cut(top, cut)
    bool_cut(body, cut)
    remove(cut)
    geo.box_uv(top, scale=1.0)
    fronts, hw = [], []
    yb0, yb1 = KICK + 0.012, ISL_TOP - CT_T - 0.006
    xs = [bx0, 0.035, 0.565, bx1]
    for kind, a, b in zip(['dd', '2d', 'dd'], xs[:-1], xs[1:]):
        bay(kind, a, b, yb0, yb1, bz1, M, fronts, hw)
    # Tim's side (-z): two plain recessed panels
    for a, b in ((bx0 + 0.04, 0.29), (0.31, bx1 - 0.04)):
        fronts.append(tbox(nm("island_back_panel"), a, b, yb0 + 0.02, yb1 - 0.02, bz0 - 0.012, bz0,
                           M["door"], r=0.006))
    # right end (+x): a raised end panel + brass towel bar with a gingham tea towel
    fronts.append(tbox("island_end_panel", bx1, bx1 + 0.012, yb0 + 0.02, yb1 - 0.02, bz0 + 0.05, bz1 - 0.05,
                       M["door"], r=0.006))
    xe = bx1 + 0.012
    bar_x, bar_y = xe + 0.03, ISL_TOP - 0.12
    za, zb = -0.10, 0.17
    hw.append(ttube("towel_bar", [(bar_x, bar_y, za - 0.02), (bar_x, bar_y, zb + 0.02)], 0.0055, M["brass"],
                    smooth_iters=0))
    for zz in (za - 0.02, zb + 0.02):
        hw.append(ttube(nm("towel_bar_post"), [(xe, bar_y, zz), (bar_x, bar_y, zz)], 0.0045, M["brass"],
                        smooth_iters=0))
    towel = tea_towel(bar_x, bar_y, za + 0.01, zb - 0.01, M["towel"])
    island_obj = join([body, kick] + fronts, "island")
    hw_obj = join(hw, "island_hardware")
    return [island_obj, top, hw_obj, towel]


def tea_towel(bx, by, z0, z1, m, rr=0.0095):
    """A tea towel folded over a bar along z: two layers hanging along -y (three)."""
    # cross-section path (x, y) in three coords: inner layer up, over the bar, outer layer down
    sec = [(bx - rr * 0.9, by - 0.20), (bx - rr * 0.95, by - 0.10), (bx - rr, by)]
    for i in range(1, 8):
        a = math.pi - math.pi * i / 8
        sec.append((bx + rr * math.cos(a), by + rr * math.sin(a)))
    sec += [(bx + rr, by), (bx + rr * 1.1, by - 0.10), (bx + rr * 1.25, by - 0.215)]
    nz = 14
    rings = []
    for k in range(nz + 1):
        z = z0 + (z1 - z0) * k / nz
        wav = 0.0025 * math.sin(k / nz * math.pi * 3.0)
        ring = []
        for (x, y) in sec:
            hang = max(0.0, (by - y) / 0.2)
            ring.append(B(x + wav * hang * (1 if x > bx else -1), y, z))
        rings.append(ring)
    # loft "rings" run along z; transpose so faces span the section
    obj = geo.loft("tea_towel", rings, mat=m, closed=False, cap_start=False, cap_end=False)
    # UVs: u across the section length, v along z  -> metres * 4 (gingham 8 bands per 0.25 m)
    L = sum(math.dist(a, b) for a, b in zip(sec[:-1], sec[1:]))
    set_uv_scale(obj, L * 4.0, (z1 - z0) * 4.0)
    return obj


def basin(M):
    c = B(SINK_X, 0, SINK_Z)
    a, b = SINK_A, SINK_B
    y_floor = RIM_Y - SINK_DEPTH
    T = ISL_TOP
    spec = [(-0.028, T), (-0.0268, T + 0.0042), (-0.0225, T + 0.0072), (-0.015, RIM_Y),
            (-0.007, RIM_Y - 0.0004), (-0.0022, RIM_Y - 0.0026), (0.0, T), (0.003, T - 0.020), (0.007, T - 0.045),
            (0.011, T - 0.065)]
    fr = 0.04
    yw = y_floor + fr
    spec.append((0.012, yw))
    for i in range(1, 8):
        th = math.pi / 2 * i / 8
        spec.append((0.012 + fr * (1 - math.cos(th)), yw - fr * math.sin(th)))
    rings = []
    for ins, y in spec:
        t = min(1.0, max(0.0, ins / (0.012 + fr)))
        rings.append(geo.superellipse(c.x, c.y, y, a - ins, b - ins, n=SINK_N - 0.9 * t, N=112))
    obj = geo.loft("sink_basin", rings, mat=M["sink"], cap_start=False, cap_end=True)
    orient_up(obj, y_floor + 0.002)
    # soapy water: a glossy translucent surface + a cloudier layer 2.5 cm down, so the depth reads and a
    # dipped plate shows through hazily (both thin sheets, inset to the wall at that height)
    ins = 0.0062
    surf = geo.loft("sink_water", [
        geo.superellipse(c.x, c.y, WATER_Y - 0.0015, a - ins, b - ins, n=SINK_N - 0.1, N=112),
        geo.superellipse(c.x, c.y, WATER_Y, a - ins, b - ins, n=SINK_N - 0.1, N=112)],
        mat=M["water"], cap_start=True, cap_end=True)
    ins2 = 0.0092
    deep = geo.loft("sink_water_deep", [
        geo.superellipse(c.x, c.y, WATER_Y - 0.0265, a - ins2, b - ins2, n=SINK_N - 0.2, N=112),
        geo.superellipse(c.x, c.y, WATER_Y - 0.025, a - ins2, b - ins2, n=SINK_N - 0.2, N=112)],
        mat=M["water_deep"], cap_start=True, cap_end=True)
    return [obj, surf, deep]


# Swing-arm faucet on the counter at the basin's left end (Tim's right): a short column, a low horizontal
# arm reaching in over the basin and a down-turned spout above the rinse spot.  Kept low (arm top ~0.19
# over the counter) and off to Tim's right so from the front cameras it sits beside/below his head.
FAUCET_X = SINK_X - SINK_A - 0.047
SPOUT_X = 0.215
ARM_Y = ISL_TOP + 0.175


def faucet(M):
    m = M["faucet"]
    fx, fz = FAUCET_X, FAUCET_Z
    T = ISL_TOP
    parts = [
        tcyl("faucet_base", fx, T, T + 0.012, fz, 0.026, m, r2=0.023, bevel=0.003),
        tcyl("faucet_collar", fx, T + 0.012, T + 0.045, fz, 0.0175, m, r2=0.0138),
    ]
    rc, rd = 0.035, 0.025
    path = [(fx, T + 0.04 + (ARM_Y - rc - T - 0.04) * i / 4, fz) for i in range(5)]
    for i in range(1, 9):                                   # column -> arm (turning toward +x)
        a = math.pi / 2 * i / 8
        path.append((fx + rc - rc * math.cos(a), ARM_Y - rc + rc * math.sin(a), fz))
    path.append((SPOUT_X - rd, ARM_Y, fz))
    for i in range(1, 9):                                   # arm -> spout (turning down)
        a = math.pi / 2 * i / 8
        path.append((SPOUT_X - rd + rd * math.sin(a), ARM_Y - rd + rd * math.cos(a), fz))
    path.append((SPOUT_X, ARM_Y - rd - 0.008, fz))
    parts.append(geo.tube("faucet_neck", [B(*p) for p in path], radius=0.0112, segs=20, mat=m))
    parts.append(tcyl("faucet_aerator", SPOUT_X, ARM_Y - rd - 0.026, ARM_Y - rd - 0.008, fz, 0.0145, m, r2=0.0132,
                      bevel=0.002))
    spout = B(SPOUT_X, ARM_Y - rd - 0.028, fz)
    # cross-handle taps either side of the column (hot toward Tim, cold toward the camera)
    for side, cap in ((-1, M["cap_hot"]), (1, M["cap_cold"])):
        hz = fz + side * 0.075
        hx = fx
        parts.append(tcyl(nm("tap_base"), hx, T, T + 0.010, hz, 0.017, m, r2=0.015, bevel=0.002))
        parts.append(tcyl(nm("tap_stem"), hx, T + 0.010, T + 0.030, hz, 0.0095, m, r2=0.008))
        for ang in (45, -45):
            parts.append(geo.rounded_box(nm("tap_spoke"), (0.05, 0.0085, 0.008), 0.0036,
                                         center=B(hx, T + 0.032, hz), rot=(0, 0, ang), segments=2, mat=m))
        for ang in (45, -45, 135, -135):
            a = math.radians(ang)
            parts.append(geo.sphere(nm("tap_ball"), 0.006, center=B(hx + 0.025 * math.cos(a), T + 0.032,
                                                                    hz + 0.025 * math.sin(a)),
                                    segs=12, rings=8, mat=m))
        parts.append(tcyl(nm("tap_cap"), hx, T + 0.032, T + 0.041, hz, 0.0078, cap, r2=0.0068, bevel=0.002))
    obj = join(parts, "faucet")
    empty("faucet_spout", loc=spout, size=0.03)
    return obj


# ---- soap foam -----------------------------------------------------------------------------
# One merged mass of many small bubbles (spheres unioned by a voxel remesh), floating on the water:
# flat-topped and lumpy, tallest at the far-right end of the basin (Tim's right), lower toward the
# camera side, and parted around the work patch where Tim's plate has pushed the suds aside (the
# translucent water shows there).  Matte white, no separate balls.
FOAM_CLEAR = (TIM_X - 0.015, TIM_Z + 0.29, 0.12, 0.085)     # work patch: centre x, z, radii x, z
FOAM_FLOAT = 0.016                                          # mean foam thickness above the water


def foam_top(x, z):
    """Target top (three y) of the foam layer at (x, z); <= WATER_Y means no foam there."""
    u = (x - SINK_X) / SINK_A
    v = (z - SINK_Z) / SINK_B
    d = (abs(u) ** SINK_N + abs(v) ** SINK_N) ** (1 / SINK_N)
    h = WATER_Y + FOAM_FLOAT
    h += 0.020 * float(_smoothstep(0.0, -0.75, u))              # a heap at Tim's right end (-x)
    h += 0.008 * float(_smoothstep(0.35, 0.9, u))               # a smaller one at the left end
    h -= 0.006 * float(_smoothstep(0.1, 0.8, v)) * float(_smoothstep(-0.3, 0.2, u))   # camera side: low
    h += 0.006 * float(_smoothstep(0.75, 1.0, d))               # suds climb the wall a little
    cx, cz, rx, rz = FOAM_CLEAR
    e = math.sqrt(((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2)
    k = float(_smoothstep(0.75, 1.35, e))                       # parted around the work patch
    return WATER_Y + (h - WATER_Y) * k - 0.006 * (1 - k)


def spheres_object(name, balls, m, segs=10, rings=7):
    """One mesh object holding many low-poly UV spheres [(x, y, z, r) three.js] (built in one go with
    numpy + from_pydata; bmesh.ops.create_uvsphere per ball is quadratic on a big bmesh)."""
    import bpy
    th = np.linspace(0, np.pi, rings + 1)[1:-1]
    ph = np.linspace(0, 2 * np.pi, segs, endpoint=False)
    ring = np.stack([np.sin(th)[:, None] * np.cos(ph)[None, :], np.cos(th)[:, None] * np.ones_like(ph)[None, :],
                     np.sin(th)[:, None] * np.sin(ph)[None, :]], -1).reshape(-1, 3)
    unit = np.concatenate([[[0, 1, 0]], ring, [[0, -1, 0]]])           # three.js axes
    nv = len(unit)
    faces = []
    for j in range(segs):
        faces.append((0, 1 + (j + 1) % segs, 1 + j))
    for i in range(rings - 2):
        a, b = 1 + i * segs, 1 + (i + 1) * segs
        for j in range(segs):
            k = (j + 1) % segs
            faces.append((a + j, a + k, b + k, b + j))
    last = 1 + (rings - 2) * segs
    for j in range(segs):
        faces.append((last + j, last + (j + 1) % segs, nv - 1))
    verts, allf = [], []
    for n, (x, y, z, r) in enumerate(balls):
        v = unit * r + np.array([x, y, z])
        verts.append(np.stack([v[:, 0], -v[:, 2], v[:, 1]], -1))      # three -> blender
        allf.extend(tuple(i + n * nv for i in f) for f in faces)
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.concatenate(verts).tolist(), [], allf)
    me.update()
    from lib.core import new_mesh_object
    obj = new_mesh_object(name, mesh=me)
    obj.data.materials.append(m)
    return obj


def foam_mass(M, seed=17):
    rng = np.random.default_rng(seed)
    balls = []

    def blob(x, y, z, r):
        balls.append((x, y, z, r))

    a_in, b_in = SINK_A - 0.002, SINK_B - 0.002

    def inside(x, z, r):
        uu = (abs(x - SINK_X) + r * 0.8) / a_in
        vv = (abs(z - SINK_Z) + r * 0.8) / b_in
        return uu ** SINK_N + vv ** SINK_N <= 1.0

    # pass 1: a continuous floating sheet (jittered grid) so no dark holes open between the clumps
    step = 0.011
    for gx in np.arange(SINK_X - a_in, SINK_X + a_in, step):
        for gz in np.arange(SINK_Z - b_in, SINK_Z + b_in, step):
            x = float(gx + rng.uniform(-0.3, 0.3) * step)
            z = float(gz + rng.uniform(-0.3, 0.3) * step)
            r = float(rng.uniform(0.0085, 0.0115))
            top = foam_top(x, z)
            if top < WATER_Y + 0.004 or not inside(x, z, r):
                continue
            blob(x, min(WATER_Y + 0.002, top - r * 0.9), z, r)
    # pass 2: the bubbly crown - small bubbles whose tops sit close to the local top (flat-topped mound)
    placed = 0
    tries = 0
    while placed < 1300 and tries < 30000:
        tries += 1
        u, v = rng.uniform(-1, 1, 2)
        r = float(rng.uniform(0.005, 0.009) if rng.random() < 0.65 else rng.uniform(0.009, 0.0135))
        x = SINK_X + u * a_in
        z = SINK_Z + v * b_in
        if not inside(x, z, r):
            continue
        top = foam_top(x, z)
        if top < WATER_Y + 0.004:
            continue
        yc = max(WATER_Y + r * 0.3, top - r * float(rng.uniform(0.75, 1.15)))
        blob(x, yc, z, r)
        placed += 1
    # a few suds spilled on the counter by the basin (small merged clusters)
    for (sx, sz, n, rr) in ((SINK_X - SINK_A - 0.05, 0.06, 5, 0.008), (SINK_X + SINK_A + 0.045, 0.05, 4, 0.0065),
                            (SINK_X + SINK_A + 0.03, -0.205, 3, 0.006)):
        for i in range(n):
            r = rr * float(rng.uniform(0.7, 1.15))
            blob(sx + float(rng.uniform(-0.012, 0.012)), ISL_TOP + r * 0.55, sz + float(rng.uniform(-0.012, 0.012)), r)
    obj = spheres_object("sink_foam_base", balls, M["foam"])
    voxel_remesh(obj, voxel=0.0026, smooth_iters=2)
    decimate(obj, 0.4)
    shade_smooth(obj)
    return obj


def suds(M):
    """Foam: one merged bubble mass, child of the empty `sink_foam` (the engine breathes it gently)."""
    foam = empty("sink_foam", loc=B(SINK_X, WATER_Y, SINK_Z), size=0.08)
    obj = foam_mass(M)
    obj.parent = foam                      # local offset from the foam empty (no parent inverse)
    obj.location = -foam.location
    return [obj]


RACK_X = (0.785, 0.825, 0.865)          # drying-rack slot centres (upright plates facing +-x)
RACK_Z = -0.10


def drying_rack(M):
    m = M["wood_dark"]
    y0 = ISL_TOP
    zc = RACK_Z
    parts = [tbox("rack_base", 0.753, 0.897, y0, y0 + 0.016, zc - 0.12, zc + 0.12, m, r=0.006)]
    for zr in (-0.085, 0.085):
        parts.append(tbox(nm("rack_rail"), 0.747, 0.903, y0 + 0.014, y0 + 0.036, zc + zr - 0.012, zc + zr + 0.012,
                          m, r=0.007))
        for xd in (0.765, 0.805, 0.845, 0.885):
            parts.append(ttube(nm("rack_dowel"), [(xd, y0 + 0.03, zc + zr), (xd, y0 + 0.135, zc + zr * 1.07)], 0.0055,
                               m, segs=10, smooth_iters=0))
    # little feet
    for xf in (0.77, 0.88):
        for zf in (-0.10, 0.10):
            parts.append(tcyl(nm("rack_foot"), xf, y0 - 0.0, y0 + 0.004, zc + zf, 0.012, m))
    obj = join(parts, "drying_rack")
    geo.box_uv(obj, scale=3.0)
    return obj


RACK_FLOOR_Y = ISL_TOP + 0.016        # top of the rack base, where an upright plate's rim rests
PLATE_R = 0.1113                      # props/dishes.glb plate radius
# spot_rack_N sit on the slot floor (the engine stands plate_clean up and lifts it by its radius);
# the upright plate centre is then at RACK_FLOOR_Y + PLATE_R
RACK_SLOTS = [(x, RACK_FLOOR_Y, RACK_Z) for x in RACK_X]


def soap_bottle(M, x=0.035, z=0.13):
    T = ISL_TOP
    prof = [(0.0, 0.0), (0.026, 0.0), (0.029, 0.004), (0.030, 0.012), (0.030, 0.080), (0.027, 0.094),
            (0.016, 0.104), (0.011, 0.108), (0.011, 0.114), (0.0, 0.114)]
    body = geo.lathe("soap_body", prof, segs=32, center=B(x, T, z), mat=M["soap"])
    neck = tcyl("soap_neck", x, T + 0.112, T + 0.135, z, 0.0055, M["brass"])
    head = tbox("soap_head", x - 0.009, x + 0.009, T + 0.132, T + 0.146, z - 0.03, z + 0.009, M["brass"],
                r=0.004)
    return join([body, neck, head], "soap_bottle")


# ---- back counter run, oven, kettle, upper cabinets ---------------------------------------

def back_run(M):
    x0, x1 = BACK_X0, BACK_X1
    zb, zf = BACK_Z0, BACK_Z1 + 0.03
    body = tbox("back_body", x0, x1, KICK, TOP_Y - CT_T, zb, zf, M["cabinet"])
    kick = tbox("back_kick", x0, x1 - 0.035, 0.0, KICK + 0.002, zb, zf - 0.035, M["kick"])
    top = tbox("back_top", x0, x1 + 0.012, TOP_Y - CT_T, TOP_Y, zb, BACK_Z1, M["counter"], r=0.01)
    geo.box_uv(top, scale=1.0, offset=(0.37, 0.21))
    fronts, hw, extra = [], [], []
    yb0, yb1 = KICK + 0.012, TOP_Y - CT_T - 0.006
    bays = [('ddd', 0.41), ('oven', 0.62), ('dd', 0.50), ('d', 0.45), ('2d2d', 0.96), ('dd', 0.46), ('ddd', 0.46)]
    x = x0
    oven_x = None
    for kind, w in bays:
        if kind == 'oven':
            oven_x = (x, x + w)
            extra += oven(x, x + w, yb0, yb1, zf, M)
        else:
            bay(kind, x, x + w, yb0, yb1, zf, M, fronts, hw)
        x += w
    # end panel on the open (+x) side
    fronts.append(tbox("back_end_panel", x1, x1 + 0.012, yb0 + 0.02, yb1 - 0.02, zb + 0.05, zf - 0.04,
                       M["door"], r=0.006))
    run = join([body, kick] + fronts, "back_counter")
    hw_obj = join(hw, "back_hardware")
    return [run, top, hw_obj] + extra, oven_x


def oven(x0, x1, y0, y1, zf, M):
    g = GAP / 2
    cx = (x0 + x1) / 2
    en = M["enamel"]
    parts = [tbox("oven_front", x0 + g, x1 - g, y0 + g, y1 - g, zf, zf + 0.012, en, r=0.008),
             tbox("oven_door", x0 + 0.03, x1 - 0.03, y0 + 0.02, 0.432, zf + 0.012, zf + 0.032, en, r=0.016)]
    win = tbox("oven_window", x0 + 0.085, x1 - 0.085, 0.165, 0.345, zf + 0.030, zf + 0.0365, M["oven_glass"],
               r=0.03, seg=4)
    hwp = [ttube("oven_handle", [(x0 + 0.075, 0.405, zf + 0.032), (x0 + 0.075, 0.405, zf + 0.056),
                                 (x1 - 0.075, 0.405, zf + 0.056), (x1 - 0.075, 0.405, zf + 0.032)],
                 0.0075, M["brass"], smooth_iters=3)]
    for kx in np.linspace(x0 + 0.13, x1 - 0.13, 3):
        knob = geo.cylinder(nm("oven_knob"), r=0.021, depth=0.022, center=B(kx, 0.50, zf + 0.012 + 0.011),
                            rot=(90, 0, 0), r2=0.018, bevel=0.004, mat=M["coral"])
        tick = tbox(nm("oven_tick"), kx - 0.0025, kx + 0.0025, 0.505, 0.517, zf + 0.0335, zf + 0.0365, M["ink"],
                    r=0.001)
        hwp += [knob, tick]
    # cooktop on the counter: enamel plate + 2 burners
    zc = (BACK_Z0 + BACK_Z1) / 2 + 0.01
    top = [tbox("hob_plate", x0 + 0.025, x1 - 0.025, TOP_Y, TOP_Y + 0.012, BACK_Z0 + 0.04, BACK_Z1 - 0.035, en,
                r=0.01)]
    burners = []
    for bx in (cx - 0.145, cx + 0.145):
        burners.append(geo.torus(nm("burner_ring"), 0.058, 0.0075, center=B(bx, TOP_Y + 0.016, zc), mat=M["ink"]))
        burners.append(tcyl(nm("burner_cap"), bx, TOP_Y + 0.012, TOP_Y + 0.024, zc, 0.026, M["ink"], r2=0.022,
                            bevel=0.003))
        for k in range(4):
            a = math.radians(45 + 90 * k)
            burners.append(ttube(nm("burner_grate"), [(bx + 0.03 * math.cos(a), TOP_Y + 0.026, zc + 0.03 * math.sin(a)),
                                                      (bx + 0.075 * math.cos(a), TOP_Y + 0.026, zc + 0.075 * math.sin(a))],
                                 0.0045, M["ink"], segs=8, smooth_iters=0))
    oven_obj = join(parts + top, "oven")
    oven_hw = join(hwp + burners + [win], "oven_details")
    kettle_obj = kettle(cx - 0.145, TOP_Y + 0.03, zc, M)
    return [oven_obj, oven_hw, kettle_obj]


def kettle(x, y, z, M):
    m = M["coral"]
    prof = [(0.0, 0.0), (0.062, 0.0), (0.074, 0.006), (0.084, 0.026), (0.087, 0.05), (0.083, 0.075),
            (0.072, 0.096), (0.056, 0.110), (0.040, 0.116), (0.0, 0.117)]
    body = geo.lathe("kettle_body", prof, segs=40, center=B(x, y, z), mat=m)
    lid = geo.lathe("kettle_lid", [(0.0, 0.0), (0.042, 0.0), (0.040, 0.006), (0.030, 0.014), (0.0, 0.017)],
                    segs=32, center=B(x, y + 0.112, z), mat=m)
    lid_knob = geo.sphere("kettle_lid_knob", 0.012, center=B(x, y + 0.135, z), segs=16, rings=10,
                          scale=(1, 1, 0.8), mat=M["wood_dark"])
    spout = ttube("kettle_spout", [(x + 0.07, y + 0.035, z), (x + 0.105, y + 0.065, z), (x + 0.125, y + 0.105, z)],
                  0.011, m, segs=14, smooth_iters=2)
    handle = ttube("kettle_handle", [(x - 0.055, y + 0.10, z), (x - 0.045, y + 0.175, z), (x + 0.045, y + 0.175, z),
                                     (x + 0.055, y + 0.10, z)], 0.008, M["wood_dark"], segs=12, smooth_iters=3)
    return join([body, lid, lid_knob, spout, handle], "kettle")


def upper_cabinets(M):
    out, hw = [], []
    y0, y1 = UPPER_Y
    zb, zf = BACK_Z0, -1.56
    g = GAP / 2
    for (x0, x1) in (UPPER_L, UPPER_R):
        cx = (x0 + x1) / 2
        out.append(tbox(nm("upper_body"), x0, x1, y0, y1, zb, zf, M["cabinet"]))
        out.append(tbox(nm("upper_crown"), x0 - 0.022, x1 + 0.022, y1, y1 + 0.03, zb, zf + 0.03, M["trim"], r=0.006))
        out.append(tbox(nm("upper_crown2"), x0 - 0.012, x1 + 0.012, y1 + 0.03, y1 + 0.045, zb, zf + 0.018, M["trim"],
                        r=0.005))
        out.append(tbox(nm("upper_sill"), x0 - 0.008, x1 + 0.008, y0 - 0.014, y0, zb, zf + 0.012, M["trim"], r=0.004))
        door(x0 + g, cx - g, y0 + g, y1 - g, zf, M, out)
        door(cx + g, x1 - g, y0 + g, y1 - g, zf, M, out)
        hw.append(knob_z(cx - 0.042, y0 + 0.075, zf + FT + 0.005, M["brass"]))
        hw.append(knob_z(cx + 0.042, y0 + 0.075, zf + FT + 0.005, M["brass"]))
    return [join(out, "upper_cabinets"), join(hw, "upper_hardware")]


def backsplash(M):
    """Cream tiles with sage grout between the back counter and the upper cabinets (window cut out)."""
    zb = BACK_Z0
    t = 0.006
    wx0, wx1, wy0, _ = WIN
    fw = 0.06  # window frame/trim width
    y_top = UPPER_Y[0]
    pieces = [
        tbox("splash_l", BACK_X0, wx0 - fw + 0.005, TOP_Y, y_top, zb, zb + t, M["tiles"]),
        tbox("splash_r", wx1 + fw - 0.005, BACK_X1, TOP_Y, y_top, zb, zb + t, M["tiles"]),
        tbox("splash_c", wx0 - fw + 0.005, wx1 + fw - 0.005, TOP_Y, wy0 - 0.03, zb, zb + t, M["tiles"]),
    ]
    obj = join(pieces, "backsplash")
    geo.box_uv(obj, scale=2.5, offset=(0.0, -TOP_Y * 2.5))
    # a slim wooden ledge capping the tiles
    cap = tbox("splash_cap_l", BACK_X0, wx0 - fw, y_top - 0.0, y_top + 0.014, zb, zb + 0.022, M["trim"], r=0.004)
    cap2 = tbox("splash_cap_r", wx1 + fw, BACK_X1, y_top, y_top + 0.014, zb, zb + 0.022, M["trim"], r=0.004)
    return [obj, join([cap, cap2], "backsplash_cap")]


# ---- dressing: fridge, clock, shelves, utensils, plants, plate rail -----------------------

def leaf(name, base, direction, length, width, m, droop=0.35, thick=0.006, n=9):
    """Lens-shaped leaf from `base` along `direction` (three.js), drooping under gravity."""
    d = Vector(direction).normalized()
    side = d.cross(Vector((0, 1, 0)))
    if side.length < 1e-4:
        side = Vector((1, 0, 0))
    side.normalize()
    rings = []
    for i in range(n + 1):
        t = 0.02 + 0.96 * i / n
        c = Vector(base) + d * (length * t) + Vector((0, -droop * length * t * t, 0))
        tang = (d * length + Vector((0, -2 * droop * length * t, 0))).normalized()
        up = side.cross(tang).normalized()
        w = width * math.sin(math.pi * t) ** 0.75
        th = thick * math.sin(math.pi * t) ** 0.5
        rings.append([B(*(c + side * w)), B(*(c + up * th)), B(*(c - side * w)), B(*(c - up * th * 0.6))])
    return geo.loft(name, rings, mat=m, cap_start=True, cap_end=True)


def fridge(M):
    """Rounded retro fridge against the left wall, door facing +x."""
    x0, x1 = -2.11, -1.54
    z0, z1 = -1.06, -0.44
    y0, y1 = 0.075, 1.45
    m = M["fridge"]
    split = 1.04
    parts = [kit.rbox("fridge_body", x0, x1 - 0.03, y0, y1, z0, z1, r=0.08, mat=m, segments=6),
             kit.rbox("fridge_door_top", x1 - 0.05, x1, split + 0.007, y1 - 0.03, z0 + 0.014, z1 - 0.014, r=0.045,
                      mat=m, segments=5),
             kit.rbox("fridge_door_main", x1 - 0.05, x1, y0 + 0.035, split - 0.007, z0 + 0.014, z1 - 0.014, r=0.045,
                      mat=m, segments=5)]
    hw = []
    zh = z1 - 0.075
    for (ya, yb) in ((split + 0.09, split + 0.30), (split - 0.40, split - 0.09)):
        hw.append(ttube(nm("fridge_handle"), [(x1 - 0.005, ya, zh), (x1 + 0.032, ya, zh), (x1 + 0.032, yb, zh),
                                              (x1 - 0.005, yb, zh)], 0.0095, M["brass"], smooth_iters=3))
    for xf in (x0 + 0.09, x1 - 0.11):
        for zf in (z0 + 0.09, z1 - 0.09):
            hw.append(kit.cyl_y(nm("fridge_foot"), xf, zf, 0.0, y0 + 0.012, 0.024, mat=M["brass"], r_top=0.017))
    # a crayon drawing held by a magnet + two loose magnets
    xd = x1 + 0.0015
    dz0, dz1, dy0, dy1 = -0.86, -0.70, 0.60, 0.80
    hw.append(kit.quad("fridge_drawing", [(xd, dy0, dz1), (xd, dy0, dz0), (xd, dy1, dz0), (xd, dy1, dz1)],
                       mat=M["paper"], facing=(1, 0, 0)))
    for (yy, zz, mm) in ((dy1 - 0.012, (dz0 + dz1) / 2, "magnet_a"), (0.93, -0.58, "magnet_b"),
                         (0.45, -0.82, "magnet_c")):
        hw.append(kit.ball(nm("fridge_magnet"), xd + 0.004, yy, zz, 0.017, mat=M[mm], scale=(0.45, 1, 1),
                           segs=16, rings=10))
    return [join(parts, "fridge"), join(hw, "fridge_details")]


def wall_clock(M):
    """Round clock on the left wall above the fridge.  Hands are separate nodes clock_hour /
    clock_minute pivoting at the centre (rotation 0 = 12; clockwise seen from the room = negative
    rotation about +X), set to 10:10."""
    K = kit.materials()
    xf = ROOM['x0'] + WALL_T / 2
    cy, cz, R = 1.80, -0.75, 0.13
    parts = [geo.cylinder("clock_back", r=R + 0.008, depth=0.022, center=B(xf + 0.011, cy, cz), rot=(0, 90, 0),
                          bevel=0.006, mat=K['beam']),
             geo.torus("clock_rim", R=R, r=0.017, center=B(xf + 0.026, cy, cz), rot=(0, 90, 0), major=64, minor=12,
                       mat=K['beam']),
             geo.cylinder("clock_face", r=R - 0.008, depth=0.008, center=B(xf + 0.026, cy, cz), rot=(0, 90, 0),
                          segs=64, mat=M["clock_face"])]
    for k in range(12):
        a = 2 * math.pi * k / 12
        rr = 0.0085 if k % 3 == 0 else 0.0048
        parts.append(kit.ball(nm("clock_dot"), xf + 0.0305, cy + 0.096 * math.cos(a), cz - 0.096 * math.sin(a), rr,
                              mat=M["ink"], scale=(0.4, 1, 1), segs=12, rings=8))
    parts.append(kit.ball("clock_pin", xf + 0.039, cy, cz, 0.008, mat=M["brass"], segs=12, rings=8))
    face = join(parts, "wall_clock")
    hands = []
    for nm_, L, w, xo, ang in (("clock_hour", 0.062, 0.0065, 0.033, 60.0), ("clock_minute", 0.092, 0.0045, 0.036, -60.0)):
        h = kit.rbox(nm_, xf + xo - 0.0018, xf + xo + 0.0018, cy - 0.016, cy + L, cz - w, cz + w, r=0.0015,
                     mat=M["ink"], segments=1)
        set_origin(h, B(xf + xo, cy, cz))
        h.rotation_euler = Euler((math.radians(ang), 0, 0), 'XYZ')
        hands.append(h)
    return [face] + hands


def canister(name, x, y, z, r, h, m_body, m_lid):
    body = geo.lathe(f"{name}_body", [(0.0, 0.0), (r - 0.004, 0.0), (r, 0.005), (r, h - 0.01), (r - 0.004, h),
                                      (0.0, h)], segs=32, center=B(x, y, z), mat=m_body)
    lid = geo.lathe(f"{name}_lid", [(0.0, 0.0), (r + 0.004, 0.0), (r + 0.004, 0.012), (r * 0.7, 0.019),
                                    (0.0, 0.021)], segs=32, center=B(x, y + h - 0.004, z), mat=m_lid)
    knob = geo.sphere(f"{name}_knob", 0.011, center=B(x, y + h + 0.022, z), segs=14, rings=8, scale=(1, 1, 0.8),
                      mat=m_lid)
    return [body, lid, knob]


def mug(name, x, y, z, m, yaw=0.0, r=0.034, h=0.075):
    body = geo.lathe(f"{name}_body", [(0.0, 0.0), (r - 0.004, 0.0), (r, 0.006), (r, h), (r - 0.004, h),
                                      (r - 0.004, 0.008), (0.0, 0.008)], segs=28, center=B(x, y, z), mat=m)
    a = math.radians(yaw)
    hx, hz = math.cos(a), -math.sin(a)
    handle = ttube(f"{name}_handle", [(x + hx * (r - 0.004), y + h * 0.8, z + hz * (r - 0.004)),
                                      (x + hx * (r + 0.024), y + h * 0.7, z + hz * (r + 0.024)),
                                      (x + hx * (r + 0.024), y + h * 0.3, z + hz * (r + 0.024)),
                                      (x + hx * (r - 0.004), y + h * 0.22, z + hz * (r - 0.004))], 0.0065, m,
                   segs=10, smooth_iters=2)
    return [body, handle]


def teapot(x, y, z, M):
    m = M["jar_sage"]
    body = geo.lathe("teapot_body", [(0.0, 0.0), (0.05, 0.0), (0.072, 0.02), (0.08, 0.05), (0.072, 0.085),
                                     (0.05, 0.105), (0.0, 0.108)], segs=36, center=B(x, y, z), mat=m)
    lid = geo.lathe("teapot_lid", [(0.0, 0.0), (0.042, 0.0), (0.03, 0.014), (0.0, 0.018)], segs=28,
                    center=B(x, y + 0.102, z), mat=m)
    knob = geo.sphere("teapot_knob", 0.011, center=B(x, y + 0.126, z), segs=14, rings=8, mat=M["jar_cream"])
    spout = ttube("teapot_spout", [(x + 0.06, y + 0.035, z), (x + 0.10, y + 0.06, z), (x + 0.118, y + 0.095, z)],
                  0.01, m, segs=12, smooth_iters=2)
    handle = ttube("teapot_handle", [(x - 0.065, y + 0.085, z), (x - 0.105, y + 0.08, z), (x - 0.105, y + 0.03, z),
                                     (x - 0.07, y + 0.025, z)], 0.008, m, segs=10, smooth_iters=2)
    return [body, lid, knob, spout, handle]


def bowl_stack(x, y, z, M, n=3):
    out = []
    for i in range(n):
        r = 0.062 - 0.006 * i
        prof = [(0.0, 0.0), (r * 0.55, 0.0), (r * 0.85, 0.012), (r, 0.038), (r - 0.004, 0.040), (r * 0.8, 0.014),
                (r * 0.5, 0.005), (0.0, 0.005)]
        out.append(geo.lathe(nm("bowl"), prof, segs=32, center=B(x, y + 0.012 * i, z),
                             mat=M["jar_cream"] if i != 1 else M["jar_pink"]))
    return out


def herb_pot(name, x, y, z, M, r=0.045, h=0.07, seed=3, n=11, spread=1.0):
    rng = np.random.default_rng(seed)
    parts = [geo.lathe(f"{name}_pot", [(0.0, 0.0), (r * 0.75, 0.0), (r * 0.8, 0.004), (r, h - 0.012),
                                       (r + 0.006, h - 0.01), (r + 0.006, h), (0.0, h)], segs=28, center=B(x, y, z),
                       mat=M["pot"])]
    parts.append(tcyl(f"{name}_soil", x, y + h - 0.012, y + h + 0.001, z, r - 0.002, M["soil"]))
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.3, 0.3)
        el = rng.uniform(0.35, 1.15)
        L = rng.uniform(0.045, 0.075) * spread
        d = (math.cos(a) * math.cos(el), math.sin(el), math.sin(a) * math.cos(el))
        parts.append(leaf(nm(f"{name}_leaf"), (x + d[0] * 0.01, y + h, z + d[2] * 0.01), d, L, L * 0.38,
                          M["plant"] if i % 2 else M["plant_dark"], droop=0.25))
    return parts


def open_shelves(M):
    """Two open wooden shelves above the hob: canisters + a glass jar + bowls; teapot + mugs + herb."""
    x0, x1 = BACK_X0 + 0.01, -1.12
    zb = BACK_Z0
    out = []
    for ys in (1.44, 1.80):
        out.append(kit.rbox(nm("shelf"), x0, x1, ys - 0.026, ys, zb, zb + 0.21, r=0.007, mat=M["wood_dark"],
                            segments=2, grain='x'))
        for xb in (x0 + 0.13, x1 - 0.13):
            out.append(kit.rbox(nm("shelf_bracket"), xb - 0.013, xb + 0.013, ys - 0.15, ys - 0.026, zb, zb + 0.03,
                                r=0.006, mat=M["wood_dark"], grain='y'))
            out.append(kit.cyl(nm("shelf_brace"), (xb, ys - 0.14, zb + 0.022), (xb, ys - 0.035, zb + 0.165), 0.009,
                               mat=M["wood_dark"], segs=12))
    yl, zj = 1.44, zb + 0.105
    out += canister("canister_a", -1.95, yl, zj, 0.056, 0.165, M["jar_cream"], M["wood"])
    out += canister("canister_b", -1.80, yl, zj, 0.050, 0.13, M["jar_sage"], M["jar_cream"])
    out += canister("canister_c", -1.675, yl, zj, 0.043, 0.105, M["jar_pink"], M["wood"])
    # glass jar of pasta
    out.append(geo.lathe("jar_glass", [(0.0, 0.0), (0.046, 0.0), (0.049, 0.006), (0.049, 0.14), (0.04, 0.152),
                                       (0.0, 0.152)], segs=32, center=B(-1.535, yl, zj), mat=M["glass"]))
    out.append(tcyl("jar_pasta", -1.535, yl + 0.004, yl + 0.10, zj, 0.043, M["pasta"], segs=24))
    out.append(tcyl("jar_lid", -1.535, yl + 0.148, yl + 0.166, zj, 0.043, M["wood"], bevel=0.004, segs=24))
    out += bowl_stack(-1.33, yl, zj, M)
    yu = 1.80
    out += teapot(-1.90, yu, zj, M)
    out += mug("mug_a", -1.70, yu, zj, M["jar_cream"], yaw=30)
    out += mug("mug_b", -1.59, yu, zj + 0.01, M["jar_pink"], yaw=-35)
    out += herb_pot("shelf_herb", -1.30, yu, zj, M, r=0.05, h=0.075, seed=5, n=13, spread=1.2)
    return join(out, "open_shelves")


def utensil_rail(M, oven_x):
    """Brass rail on the tiles above the hob with a ladle, spatula, whisk and wooden spoon."""
    xa, xb = oven_x[0] + 0.05, oven_x[1] - 0.05
    ry, rz = 1.16, BACK_Z0 + 0.045
    parts = [ttube("rail_bar", [(xa, ry, rz), (xb, ry, rz)], 0.0065, M["brass"], smooth_iters=0)]
    for xx in (xa + 0.02, xb - 0.02):
        parts.append(ttube(nm("rail_post"), [(xx, ry, BACK_Z0 + 0.006), (xx, ry, rz)], 0.005, M["brass"],
                           smooth_iters=0))
        parts.append(kit.cyl(nm("rail_rose"), (xx, ry, BACK_Z0 + 0.004), (xx, ry, BACK_Z0 + 0.012), 0.012,
                             mat=M["brass"], segs=16))
    xs = np.linspace(xa + 0.08, xb - 0.08, 4)
    for x in xs:   # S-hooks
        parts.append(geo.torus(nm("rail_hook"), R=0.009, r=0.0018, center=B(x, ry, rz), rot=(0, 90, 0), major=16,
                               minor=6, mat=M["brass"]))
    top = ry - 0.012
    # ladle (steel)
    x = xs[0]
    parts.append(ttube("ladle_handle", [(x, top, rz), (x, top - 0.17, rz + 0.004)], 0.0045, M["steel"], smooth_iters=0))
    parts.append(geo.lathe("ladle_bowl", [(0.0, 0.0), (0.02, 0.003), (0.032, 0.014), (0.036, 0.028), (0.0, 0.028)],
                           segs=24, center=B(x, top - 0.21, rz + 0.012), rot=(75, 0, 0), mat=M["steel"]))
    # spatula (wood)
    x = xs[1]
    parts.append(ttube("spatula_handle", [(x, top, rz), (x, top - 0.12, rz + 0.003)], 0.0058, M["wood_dark"],
                       smooth_iters=0))
    parts.append(kit.rbox("spatula_blade", x - 0.03, x + 0.03, top - 0.20, top - 0.115, rz - 0.002, rz + 0.007,
                          r=0.0035, mat=M["wood"], segments=2))
    # whisk (steel loops + wooden handle)
    x = xs[2]
    parts.append(ttube("whisk_handle", [(x, top, rz), (x, top - 0.085, rz)], 0.0085, M["wood_dark"], smooth_iters=0))
    for k in range(3):
        a = math.pi * k / 3
        loop = []
        for i in range(25):
            t = math.pi * i / 24
            s = math.sin(t) * 0.028 * (1 + 0.35 * math.sin(t))
            loop.append((x + s * math.cos(a), top - 0.085 - (1 - math.cos(t)) * 0.06, rz + s * math.sin(a)))
        parts.append(ttube(nm("whisk_wire"), loop, 0.0016, M["steel"], segs=6, smooth_iters=0, round_caps=False))
    # wooden spoon
    x = xs[3]
    parts.append(ttube("spoon_handle", [(x, top, rz), (x, top - 0.15, rz + 0.003)], 0.0055, M["wood"], smooth_iters=0))
    parts.append(kit.ball("spoon_bowl", x, top - 0.18, rz + 0.006, 0.024, mat=M["wood"], scale=(0.9, 1.4, 0.35),
                          segs=18, rings=10))
    return join(parts, "utensil_rail")


def floor_plant(M, x=1.97, z=-1.58, seed=9):
    """Potted floor plant at the open end of the back wall."""
    rng = np.random.default_rng(seed)
    h = 0.30
    parts = [geo.lathe("floor_pot", [(0.0, 0.0), (0.12, 0.0), (0.135, 0.015), (0.155, h - 0.03), (0.168, h - 0.025),
                                     (0.168, h), (0.0, h)], segs=40, center=B(x, 0.0, z), mat=M["pot"]),
             tcyl("floor_pot_soil", x, h - 0.02, h + 0.002, z, 0.155, M["soil"], segs=32)]
    for i in range(15):
        a = 2 * math.pi * i / 15 + rng.uniform(-0.25, 0.25)
        el = rng.uniform(0.75, 1.35)
        stem_l = rng.uniform(0.18, 0.55)
        sx, sz = math.cos(a), math.sin(a)
        base = (x + sx * 0.02, h, z + sz * 0.02)
        tip = (x + sx * stem_l * math.cos(el), h + stem_l * math.sin(el), z + sz * stem_l * math.cos(el))
        parts.append(ttube(nm("plant_stem"), [base, tip], 0.005, M["plant_dark"], segs=8, smooth_iters=0))
        L = rng.uniform(0.16, 0.24)
        d = (sx * math.cos(el * 0.55), math.sin(el * 0.55), sz * math.cos(el * 0.55))
        parts.append(leaf(nm("plant_leaf"), tip, d, L, L * 0.42, M["plant"] if i % 3 else M["plant_dark"],
                          droop=0.45, thick=0.008))
    return join(parts, "floor_plant")


DECO_PROFILE = [(0.0, 0.0035), (0.074, 0.0035), (0.078, 0.0012), (0.083, 0.0012), (0.086, 0.004), (0.104, 0.009),
                (0.117, 0.0135), (0.1215, 0.0150), (0.1225, 0.0172), (0.1205, 0.0188), (0.1155, 0.0182),
                (0.103, 0.0148), (0.085, 0.0098), (0.072, 0.0080), (0.0, 0.0078)]


def deco_plate(name, center, m, lean_deg=12.0):
    """Decorative plate standing on a rail against the left wall (face toward +x, leaning back)."""
    obj = geo.lathe(name, DECO_PROFILE, segs=56, mat=m)
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        top = f.normal.z > 0.2
        for loop in f.loops:
            co = loop.vert.co
            loop[uvl].uv = (0.5 + co.x / 0.25, 0.5 + co.y / 0.25) if top else (0.5, 0.97)
    bm.to_mesh(me)
    bm.free()
    # local +Z (plate normal) -> three (cos lean, sin lean, 0); rotate the motif upright first
    rot = Euler((0.0, math.radians(90 - lean_deg), 0.0), 'XYZ').to_matrix().to_4x4() @ \
        Euler((0.0, 0.0, math.radians(90)), 'XYZ').to_matrix().to_4x4()
    me.transform(Matrix.Translation(B(*center)) @ rot)
    me.update()
    return obj


def plate_rail(M):
    """A little plate rail on the left wall with three decorative plates."""
    xf = ROOM['x0'] + WALL_T / 2
    za, zb_, ys = -0.28, 0.76, 1.40
    parts = [kit.rbox("plate_rail_shelf", xf, xf + 0.15, ys - 0.024, ys, za, zb_, r=0.006, mat=M["wood_dark"],
                      segments=2, grain='z'),
             kit.rbox("plate_rail_back", xf, xf + 0.018, ys, ys + 0.07, za, zb_, r=0.005, mat=M["wood_dark"], grain='z'),
             kit.cyl("plate_rail_lip", (xf + 0.128, ys + 0.022, za), (xf + 0.128, ys + 0.022, zb_), 0.0065,
                     mat=M["wood_dark"], segs=12)]
    for zz in (za + 0.07, zb_ - 0.07):
        parts.append(kit.rbox(nm("plate_rail_bracket"), xf, xf + 0.024, ys - 0.13, ys - 0.024, zz - 0.012, zz + 0.012,
                              r=0.005, mat=M["wood_dark"], grain='y'))
        parts.append(kit.cyl(nm("plate_rail_brace"), (xf + 0.02, ys - 0.12, zz), (xf + 0.12, ys - 0.03, zz), 0.008,
                             mat=M["wood_dark"], segs=12))
    lean = 12.0
    ra = 0.1225
    cy = ys + ra * math.cos(math.radians(lean)) + 0.002
    cx = xf + 0.105 - ra * math.sin(math.radians(lean)) - 0.012
    plates = [deco_plate(f"deco_plate_{i + 1}", (cx, cy, zz), M[k], lean)
              for i, (zz, k) in enumerate(((za + 0.18, "deco_a"), ((za + zb_) / 2, "deco_b"), (zb_ - 0.18, "deco_c")))]
    return join(parts + plates, "plate_rail")


def counter_dressing(M):
    """Right part of the back counter (GuoGuo's spot x 0.85 .. 1.25 stays clear): a fruit bowl and a
    wooden cutting board leaning on the tiles."""
    parts = []
    # cutting board with a handle tab, leaning back 10 deg against the backsplash
    W, H, T = 0.21, 0.25, 0.018
    out = []
    for i in range(16):
        a = -math.pi / 2 + math.pi / 2 * i / 15
        out.append((W / 2 - 0.03 + 0.03 * math.cos(a), 0.03 + 0.03 * math.sin(a)))
    for i in range(16):
        a = math.pi / 2 * i / 15
        out.append((W / 2 - 0.03 + 0.03 * math.cos(a), H - 0.03 + 0.03 * math.sin(a)))
    for i in range(13):   # handle tab (rounded top)
        a = math.pi * i / 12
        out.append((0.035 * math.cos(a), H + 0.045 + 0.035 * math.sin(a)))
    for i in range(16):
        a = math.pi / 2 + math.pi / 2 * i / 15
        out.append((-W / 2 + 0.03 + 0.03 * math.cos(a), H - 0.03 + 0.03 * math.sin(a)))
    for i in range(16):
        a = math.pi + math.pi / 2 * i / 15
        out.append((-W / 2 + 0.03 + 0.03 * math.cos(a), 0.03 + 0.03 * math.sin(a)))
    cleaned = []
    for p in out:
        if not cleaned or math.dist(p, cleaned[-1]) > 1e-4:
            cleaned.append(p)
    board = geo.extrude_outline("cutting_board", cleaned, depth=T, mat=M["wood"], bevel=0.004, bevel_segments=2)
    lean = 10.0
    zc = BACK_Z0 + 0.006 + T / 2 + (H + 0.08) * math.sin(math.radians(lean)) + 0.004
    board.data.transform(Matrix.Translation(B(1.62, TOP_Y, zc)) @
                         Euler((math.radians(-lean), 0, 0), 'XYZ').to_matrix().to_4x4())
    board.data.update()
    kit.grain_uv(board, 'y', tile=0.5)
    hole = geo.torus("cutting_board_hole", R=0.012, r=0.0035, center=(0, 0, 0), rot=(90, 0, 0), major=20, minor=6,
                     mat=M["wood_dark"])
    hole.data.transform(Matrix.Translation(B(1.62, TOP_Y, zc)) @
                        Euler((math.radians(-lean), 0, 0), 'XYZ').to_matrix().to_4x4() @
                        Matrix.Translation(B(0, H + 0.045, T / 2 + 0.001)))
    parts += [board, hole]
    # fruit bowl
    bx, bz = 1.42, -1.56
    prof = [(0.0, 0.0), (0.05, 0.0), (0.085, 0.02), (0.105, 0.058), (0.099, 0.062), (0.078, 0.026),
            (0.045, 0.010), (0.0, 0.010)]
    parts.append(geo.lathe("fruit_bowl", prof, segs=40, center=B(bx, TOP_Y, bz), mat=M["jar_cream"]))
    fruit = [(-0.035, 0.040, -0.02, "apple", 0.037), (0.038, 0.042, 0.015, "apple", 0.035),
             (0.0, 0.038, 0.045, "lemon", 0.034), (0.005, 0.085, -0.005, "lemon", 0.033)]
    for (dx, dy, dz, kind, r) in fruit:
        if kind == "apple":
            parts.append(kit.ball(nm("apple"), bx + dx, TOP_Y + dy, bz + dz, r, mat=M["apple"], scale=(1, 0.9, 1),
                                  segs=24, rings=14))
            parts.append(kit.cyl(nm("apple_stem"), (bx + dx, TOP_Y + dy + r * 0.8, bz + dz),
                                 (bx + dx + 0.004, TOP_Y + dy + r * 0.8 + 0.018, bz + dz), 0.003, mat=M["wood_dark"],
                                 segs=8))
        else:
            parts.append(kit.ball(nm("lemon"), bx + dx, TOP_Y + dy, bz + dz, r, mat=M["lemon"],
                                  scale=(1.25, 0.9, 0.9), segs=24, rings=14, rot=(0, 0, 25)))
    return join(parts, "counter_dressing")


def left_backsplash(M):
    """Tiles on the left wall over the counter return (behind the corner post .. counter front)."""
    xf = ROOM['x0'] + WALL_T / 2
    obj = tbox("splash_left", xf, xf + 0.006, TOP_Y, UPPER_Y[0], BACK_Z0 + POST_W, BACK_Z1, M["tiles"])
    geo.box_uv(obj, scale=2.5, offset=(0.0, -TOP_Y * 2.5))
    cap = tbox("splash_left_cap", xf, xf + 0.022, UPPER_Y[0], UPPER_Y[0] + 0.014, BACK_Z0 + POST_W, BACK_Z1,
               M["trim"], r=0.004)
    return [obj, cap]


# ---- shell (dollhouse_kit) -----------------------------------------------------------------

def tile_floor(M, nx=14, nz=10, gap=0.003, thick=0.012, bevel=0.0028):
    """Soft checker floor of individual glazed tiles (cream / sage), top at y = 0, 3 mm grout gaps."""
    R = ROOM
    x0, x1, z0, z1 = R['x0'], R['x1'], R['z0'], R['z1']
    w, d = (x1 - x0) / nx, (z1 - z0) / nz
    tiles = []
    for i in range(nx):
        for j in range(nz):
            a0 = x0 + i * w + (gap / 2 if i > 0 else 0.0)
            a1 = x0 + (i + 1) * w - (gap / 2 if i < nx - 1 else 0.0)
            c0 = z0 + j * d + (gap / 2 if j > 0 else 0.0)
            c1 = z0 + (j + 1) * d - (gap / 2 if j < nz - 1 else 0.0)
            m = M["tile_a"] if (i + j) % 2 == 0 else M["tile_b"]
            tiles.append(kit.rbox(f"floor_t{i}_{j}", a0, a1, -thick, 0.0, c0, c1, r=bevel, mat=m, segments=1))
    floor = join(tiles, "floor_tiles")
    shade_smooth(floor, angle_deg=20)
    yb = -thick + 0.003
    grout = kit.quad("floor_grout", [(x0, yb, z1), (x1, yb, z1), (x1, yb, z0), (x0, yb, z0)], mat=M["grout"],
                     facing=(0, 1, 0))
    return join([floor, grout], "floor_tiles")


def shell_kit(M):
    K = kit.materials()
    R = ROOM
    t2 = WALL_T / 2
    fb = R['z0'] + t2      # back wall inner face  z = -1.85
    fl = R['x0'] + t2      # left wall inner face  x = -2.15
    kit.tabletop_and_base([(R['x0'] - t2, R['x1'], R['z0'] - t2, R['z1'])], center=(-0.9, -0.3), radius=7.0)
    tile_floor(M)
    win = dict(u0=WIN[0], u1=WIN[1], y0=WIN[2], y1=WIN[3], kind='window')
    # Back wall: papered (+ baseboard) behind the counter run, sage wainscot only past the counter end.
    kit.wall('wall_back', R['x0'] - t2, R['z0'], BACK_X1, R['z0'], inner=+1, height=WALL_H, thickness=WALL_T,
             wainscot=False, openings=[win], inner_range=(fl, BACK_X1), top_plate=False)
    kit.wall('wall_back_r', BACK_X1, R['z0'], R['x1'], R['z0'], inner=+1, height=WALL_H, thickness=WALL_T,
             wainscot=True, inner_range=(BACK_X1, R['x1']), top_plate=False)
    # Left wall: tiles over the counter return, wainscot in front of it.
    kit.wall('wall_left', R['x0'], R['z0'] - t2, R['x0'], BACK_Z1, inner=+1, height=WALL_H, thickness=WALL_T,
             wainscot=False, inner_range=(fb, BACK_Z1), top_plate=False)
    kit.wall('wall_left_f', R['x0'], BACK_Z1, R['x0'], R['z1'], inner=+1, height=WALL_H, thickness=WALL_T,
             wainscot=True, inner_range=(BACK_Z1, R['z1']), top_plate=False)
    # continuous top plates (same profile as the kit's top_plate)
    kit.rbox('wall_back_plate', fl, R['x1'], WALL_H - 0.12, WALL_H, fb - 0.002, fb + 0.045, r=0.01, mat=K['beam'],
             segments=2, grain='x')
    kit.rbox('wall_left_plate', fl - 0.002, fl + 0.045, WALL_H - 0.12, WALL_H, fb, R['z1'], r=0.01, mat=K['beam'],
             segments=2, grain='z')
    kit.window('window', 'x', R['z0'], WIN[0], WIN[1], WIN[2], WIN[3], inner=+1, thickness=WALL_T)
    kit.post('post_room_corner', fl + POST_W / 2, fb + POST_W / 2, w=POST_W)


# ---- temporary / fallback shell ------------------------------------------------------------

def shell_fallback(M):
    out = []
    top = tcyl("tabletop", 0.0, -0.16, -0.10, -0.3, 3.4, M["tabletop"], segs=96, bevel=0.02)
    out.append(top)
    out.append(tbox("base_slab", -2.32, 2.32, -0.10, -0.003, -2.02, 1.33, M["exterior"], r=0.012))
    fl = tbox("floor", -2.2, 2.2, -0.004, 0.0, -1.9, 1.25, M["floor"])
    geo.box_uv(fl, scale=1.0 / 1.28)
    out.append(fl)
    wall = mat.prop("wall_tmp", PAL["wall"])
    bw = tbox("wall_back", -2.25, 2.25, 0.0, 2.3, -1.95, -1.85, wall)
    wx0, wx1, wy0, wy1 = WIN
    cut = tbox("win_cut", wx0, wx1, wy0, wy1, -2.0, -1.8, wall)
    bool_cut(bw, cut)
    remove(cut)
    out.append(bw)
    out.append(tbox("wall_left", -2.25, -2.15, 0.0, 2.3, -1.85, 1.25, wall))
    sky = mat.emit("sky", "#ffffff", strength=1.0,
                   image=mat.image_from_array("sky_window", tex.sky_window(seed=6)))
    sk = tbox("window_sky", wx0 - 0.1, wx1 + 0.1, wy0 - 0.1, wy1 + 0.1, -2.10, -2.09, sky)
    geo.planar_uv(sk, axis='Y', origin=B((wx0 + wx1) / 2, (wy0 + wy1) / 2, -2.1), half_size=0.5)
    out.append(sk)
    return out


# ---- spots ---------------------------------------------------------------------------------

def spot(name, x, y, z, yaw=0.0, **extra):
    """spot_* empty with custom prop yaw (degrees) - same convention as dollhouse_kit.spot."""
    props = {"yaw": float(yaw)}
    props.update(extra)
    return empty(name, loc=B(x, y, z), props=props, display='SINGLE_ARROW', size=0.2)


def build():
    _names.clear()
    M = materials()
    if kit is not None:
        shell_kit(M)
    else:
        shell_fallback(M)
    island(M)
    basin(M)
    faucet(M)
    suds(M)
    drying_rack(M)
    soap_bottle(M)
    _, oven_x = back_run(M)
    upper_cabinets(M)
    backsplash(M)
    left_backsplash(M)
    fridge(M)
    wall_clock(M)
    open_shelves(M)
    utensil_rail(M, oven_x)
    floor_plant(M)
    counter_dressing(M)
    join(herb_pot("sill_herb", 0.68, WIN[2] + 0.004, ROOM['z0'] + WALL_T / 2 + 0.034, M, r=0.032, h=0.055,
                  seed=13, n=12, spread=0.9), "sill_herb")
    plate_rail(M)

    sx, sz = STACK_XZ
    spot("spot_sink", TIM_X, 0.0, TIM_Z, 0)
    spot("spot_guoguo", 1.05, TOP_Y, -1.62, -15, clear_w=0.40, clear_d=0.36)
    spot("spot_plate_stack", sx, ISL_TOP, sz, 0)
    spot("spot_rack", sum(RACK_X) / 3, ISL_TOP, RACK_Z, 0)
    for i, (x, y, z) in enumerate(RACK_SLOTS):
        spot(f"spot_rack_{i + 1}", x, y, z, 90, upright=1, plate_centre_y=round(y + PLATE_R, 4))
    empty("light_window", loc=B((WIN[0] + WIN[1]) / 2, (WIN[2] + WIN[3]) / 2, -1.72), size=0.1)
    return {"spots": {"spot_sink": [TIM_X, 0.0, TIM_Z, 0], "spot_guoguo": [1.05, TOP_Y, -1.62, -15],
                      "spot_plate_stack": [sx, ISL_TOP, sz, 0], "spot_rack": [sum(RACK_X) / 3, ISL_TOP, RACK_Z, 0],
                      **{f"spot_rack_{i + 1}": [x, y, z, 90] for i, (x, y, z) in enumerate(RACK_SLOTS)}},
            "island_top_y": ISL_TOP, "water_y": WATER_Y, "work_patch": list(FOAM_CLEAR),
            "hooks": ["faucet_spout", "sink_foam", "sink_foam_base", "light_window", "clock_hour",
                      "clock_minute"]}
