"""Tim, the host (characters/tim): an Animal Crossing-style chibi villager as a soft vinyl toy.

Every surface is generated analytically (numpy grids -> meshes), so the forms stay smooth, the hair
is a sculpted shell split into clumps plus loose locks (items/tim_hair.py), and the build is
deterministic (seeded randomness only).  Positions in this file are
three.js coordinates (x = Tim's left, y = up, z = front) and are converted to Blender only when a
mesh or bone is created.  Actions are posed with a small FK/IK solver (hands land on their contact
points while the body moves) and baked per frame at 60 fps from eased, overlapping curves.

  ./.venv/bin/python infra/blender/build.py tim
  TIM_DEBUG=desk|sink ./.venv/bin/python infra/blender/build.py tim   # + proxy props, for previews only
"""
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

from lib import geo, mat, tex
from lib.core import B, new_mesh_object
from lib import rig as rigmod
from items import tim_hair

ITEM = {"id": "characters/tim", "out": "characters/tim.glb"}
FPS = 60
DEBUG = os.environ.get("TIM_DEBUG", "")

COL = dict(skin="#f4dcc6", hoodie="#36435e", hoodie_dark="#2c374d", drawstring="#efe7d8",
           pants="#8f8576", shoe="#ece5d8", sole="#a08d78", hair="#2b241f", wire="#3b3633")

# ---------------------------------------------------------------------------------------------
# proportions (three.js metres)
HC = np.array([0.0, 1.08, 0.0])                     # head centre
HRX, HRY_TOP, HRY_BOT, HRZ = 0.432, 0.410, 0.378, 0.415
EYE_X, EYE_Y = 0.155, -0.02                         # head-local eye centres (decals)
LEG_X = 0.086

J_REST = {
    "root": (0.0, 0.0, 0.0),
    "hips": (0.0, 0.44, 0.0),
    "torso": (0.0, 0.50, 0.0),
    "neck": (0.0, 0.80, 0.0),
    "head": (0.0, 1.08, 0.0),
}
J_PARENT = {"root": None, "hips": "root", "torso": "hips", "neck": "torso", "head": "neck"}
for _s, _x in (("L", 1.0), ("R", -1.0)):
    J_REST.update({f"upperarm_{_s}": (0.17 * _x, 0.78, 0.0), f"forearm_{_s}": (0.21 * _x, 0.62, 0.0),
                   f"hand_{_s}": (0.23 * _x, 0.47, 0.0),
                   f"thigh_{_s}": (LEG_X * _x, 0.42, 0.0), f"shin_{_s}": (LEG_X * _x, 0.23, 0.0),
                   f"foot_{_s}": (LEG_X * _x, 0.08, 0.0)})
    J_PARENT.update({f"upperarm_{_s}": "torso", f"forearm_{_s}": f"upperarm_{_s}",
                     f"hand_{_s}": f"forearm_{_s}", f"grip_{_s}": f"hand_{_s}",
                     f"thigh_{_s}": "hips", f"shin_{_s}": f"thigh_{_s}", f"foot_{_s}": f"shin_{_s}"})


def _hand_axes(side):
    """Rest frame of a mitten: fingers (down the forearm), palm normal (inward), thumb (+z, front)."""
    s = 1.0 if side == "L" else -1.0
    w, e = np.array(J_REST[f"hand_{side}"]), np.array(J_REST[f"forearm_{side}"])
    L = (w - e) / np.linalg.norm(w - e)
    P = s * np.array([L[1], -L[0], 0.0])
    return L, P, np.array([0.0, 0.0, 1.0])


HAND_SCALE = 1.15
HAND_CENTRE_OFF = 0.037      # mitten centre, along the fingers axis from the wrist joint
GRIP_PALM_OFF = 0.012        # grip = mitten centre pushed toward the palm surface
for _s in "LR":
    _L, _P, _T = _hand_axes(_s)
    J_REST[f"grip_{_s}"] = tuple(np.array(J_REST[f"hand_{_s}"]) + _L * HAND_CENTRE_OFF + _P * GRIP_PALM_OFF)

J_ORDER = ["root", "hips", "torso", "neck", "head"]
for _s in "LR":
    J_ORDER += [f"upperarm_{_s}", f"forearm_{_s}", f"hand_{_s}", f"grip_{_s}"]
for _s in "LR":
    J_ORDER += [f"thigh_{_s}", f"shin_{_s}", f"foot_{_s}"]


# ---------------------------------------------------------------------------------------------
# numeric helpers
def _n(v):
    v = np.asarray(v, float)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def sstep(e0, e1, x):
    u = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def clamp01(u):
    return min(1.0, max(0.0, u))


class Curve:
    """C1 cubic through keys [(x, y), ...].  mode 'pchip' (monotone: no overshoot, holds stay flat)
    or 'cr' (Catmull-Rom).  period=P wraps (keys in [0, P)); otherwise the ends clamp with flat slopes."""

    def __init__(self, keys, period=None, mode="pchip"):
        ks = sorted(keys)
        x = np.array([k[0] for k in ks], float)
        y = np.array([k[1] for k in ks], float)
        self.period = period
        if period:
            x = np.concatenate([[x[-1] - period], x, [x[0] + period, x[1] + period]])
            y = np.concatenate([[y[-1]], y, [y[0], y[1]]])
        h = np.diff(x)
        d = np.diff(y) / h
        m = np.zeros_like(y)
        for k in range(1, len(x) - 1):
            if mode == "cr":
                m[k] = (y[k + 1] - y[k - 1]) / (x[k + 1] - x[k - 1])
            elif d[k - 1] * d[k] > 0:
                w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
                m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
        self.x, self.y, self.m = x, y, m
        self.x0 = x[1] if period else x[0]

    def __call__(self, t):
        t = np.asarray(t, float)
        x, y, m = self.x, self.y, self.m
        if self.period:
            t = self.x0 + np.mod(t - self.x0, self.period)
        else:
            t = np.clip(t, x[0], x[-1])
        k = np.clip(np.searchsorted(x, t, side="right") - 1, 0, len(x) - 2)
        h = x[k + 1] - x[k]
        u = (t - x[k]) / h
        u2, u3 = u * u, u * u * u
        out = ((2 * u3 - 3 * u2 + 1) * y[k] + (u3 - 2 * u2 + u) * h * m[k]
               + (-2 * u3 + 3 * u2) * y[k + 1] + (u3 - u2) * h * m[k + 1])
        return float(out) if out.ndim == 0 else out


def to_blender(P):
    P = np.asarray(P, float)
    return np.stack([P[..., 0], -P[..., 2], P[..., 1]], axis=-1)


# ---------------------------------------------------------------------------------------------
# mesh construction
def make_mesh(name, verts, faces, uvs=None, mats=(), mat_idx=None, recalc=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(to_blender(verts).tolist(), [], faces)
    if uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.asarray(uvs, np.float32).ravel())
    for m in mats:
        me.materials.append(m)
    if mat_idx is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_idx, np.int32))
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return new_mesh_object(name, mesh=me)


class Grid:
    """A (R, C) grid of three.js points -> quads (tris at pole rows).  wrap_u closes the columns,
    wrap_v closes the rows (torus).  uv: (R(+1 if wrap_v), C+1 if wrap_u else C, 2)."""

    def __init__(self, P, wrap_u=True, wrap_v=False, pole0=False, pole1=False, uv=None, face_mat=None):
        self.P = np.asarray(P, float)
        self.wrap_u, self.wrap_v, self.pole0, self.pole1 = wrap_u, wrap_v, pole0, pole1
        self.uv = uv
        self.face_mat = face_mat  # fn(r, c, centre) -> material index

    def build(self, base=0):
        P = self.P
        R, C = P.shape[:2]
        verts = []
        idx = np.zeros((R, C), int)
        for r in range(R):
            if (r == 0 and self.pole0) or (r == R - 1 and self.pole1):
                idx[r, :] = base + len(verts)
                verts.append(P[r].mean(axis=0))
            else:
                idx[r, :] = base + len(verts) + np.arange(C)
                verts.extend(P[r])
        faces, uvs, mids = [], [], []
        Cf = C if self.wrap_u else C - 1
        for r in range(R if self.wrap_v else R - 1):
            r2 = (r + 1) % R
            rv2 = r + 1  # uv row (seam row when wrapping v)
            for c in range(Cf):
                c2 = (c + 1) % C
                corners = [(idx[r, c], r, c), (idx[r, c2], r, c + 1), (idx[r2, c2], rv2, c + 1),
                           (idx[r2, c], rv2, c)]
                out = []
                for k, cr in enumerate(corners):
                    if out and out[-1][0] == cr[0]:
                        continue
                    out.append(cr)
                if len(out) > 1 and out[0][0] == out[-1][0]:
                    out.pop()
                if len(out) < 3:
                    continue
                faces.append([o[0] for o in out])
                if self.uv is not None:
                    uvs.extend(self.uv[o[1], o[2]] for o in out)
                mids.append((r, c))
        mats = None
        if self.face_mat is not None:
            mats = []
            for (r, c) in mids:
                ctr = (P[r, c] + P[(r + 1) % R, (c + 1) % C]) * 0.5
                mats.append(self.face_mat(r, c, ctr))
        return np.array(verts), faces, (np.array(uvs) if self.uv is not None else None), mats


def grids_to_object(name, grids, mats=(), recalc=True):
    V, F, U, M = [], [], [], []
    base = 0
    has_uv = all(g.uv is not None for g in grids)
    for g in grids:
        v, f, u, m = g.build(base)
        V.append(v)
        F.extend(f)
        if has_uv:
            U.append(u)
        M.extend(m if m is not None else [0] * len(f))
        base += len(v)
    return make_mesh(name, np.concatenate(V), F, uvs=(np.concatenate(U) if has_uv else None), mats=mats,
                     mat_idx=M, recalc=recalc)


def frames_along(path, ref=(0.0, 0.0, 1.0), closed=False):
    """Tangent / normal / binormal (parallel transport) along a polyline."""
    path = np.asarray(path, float)
    if closed:
        T = _n(np.roll(path, -1, axis=0) - np.roll(path, 1, axis=0))
    else:
        T = _n(np.gradient(path, axis=0))
    ref = np.asarray(ref, float)
    n = ref - T[0] * np.dot(ref, T[0])
    if np.linalg.norm(n) < 1e-6:
        n = np.array([1.0, 0.0, 0.0]) - T[0] * T[0][0]
    N = [_n(n)]
    for i in range(1, len(path)):
        v = N[-1] - T[i] * np.dot(N[-1], T[i])
        N.append(_n(v))
    N = np.array(N)
    Bn = np.cross(T, N)
    return T, N, Bn


def tube_grid(path, radius, segs=16, cap0=None, cap1=None, ref=(0.0, 0.0, 1.0), ncap=5, squash=(1.0, 1.0),
              face_mat=None):
    """Sweep a circle along `path`.  radius: float or per-point list.  cap0/cap1 = axial depth of a rounded
    end cap (radius -> hemisphere, small -> flattened dome).  squash = (scale along N, scale along B)."""
    path = np.asarray(path, float)
    N_ = len(path)
    rad = np.broadcast_to(np.asarray(radius, float), (N_,)).astype(float)
    T, Nn, Bn = frames_along(path, ref)
    a = 2 * np.pi * np.arange(segs) / segs
    ca, sa = np.cos(a), np.sin(a)
    def ring(p, r, i):
        return p[None, :] + r * (ca[:, None] * Nn[i][None, :] * squash[0] + sa[:, None] * Bn[i][None, :] * squash[1])
    rings = [ring(path[i], rad[i], i) for i in range(N_)]
    pre, post = [], []
    if cap0 is not None:
        for j in range(ncap, 0, -1):
            al = 0.5 * np.pi * j / ncap
            pre.append(ring(path[0] - T[0] * cap0 * np.sin(al), rad[0] * np.cos(al), 0))
    if cap1 is not None:
        for j in range(1, ncap + 1):
            al = 0.5 * np.pi * j / ncap
            post.append(ring(path[-1] + T[-1] * cap1 * np.sin(al), rad[-1] * np.cos(al), N_ - 1))
    P = np.array(pre + rings + post)
    return Grid(P, wrap_u=True, pole0=cap0 is not None, pole1=cap1 is not None, face_mat=face_mat)


def resample(points, n, mode="cr"):
    """Smooth resample of a polyline through `points` (Catmull-Rom per coordinate, by chord length)."""
    pts = np.asarray(points, float)
    d = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    tt = np.linspace(0, d[-1], n)
    return np.stack([Curve(list(zip(d, pts[:, k])), mode=mode)(tt) for k in range(3)], axis=1)


# ---------------------------------------------------------------------------------------------
# head surface (ellipsoid, rounder on top, a little flatter underneath)
def head_dir(theta, phi):
    st = np.sin(theta)
    return np.stack([st * np.sin(phi), np.cos(theta), st * np.cos(phi)], axis=-1)


def head_surface(d):
    d = np.asarray(d, float)
    ry = np.where(d[..., 1] >= 0, HRY_TOP, HRY_BOT)
    r = 1.0 / np.sqrt((d[..., 0] / HRX) ** 2 + (d[..., 1] / ry) ** 2 + (d[..., 2] / HRZ) ** 2)
    p = d * r[..., None]
    n = np.stack([p[..., 0] / HRX ** 2, p[..., 1] / ry ** 2, p[..., 2] / HRZ ** 2], axis=-1)
    return HC + p, _n(n)


def head_radius_along(d):
    d = _n(d)
    ry = np.where(d[..., 1] >= 0, HRY_TOP, HRY_BOT)
    return 1.0 / np.sqrt((d[..., 0] / HRX) ** 2 + (d[..., 1] / ry) ** 2 + (d[..., 2] / HRZ) ** 2)


def head_clearance(p_local):
    """Signed radial distance of head-local points (relative to the head centre) from the skin."""
    p = np.asarray(p_local, float)
    return np.linalg.norm(p, axis=-1) - head_radius_along(p)


def skin(theta, phi):
    return head_surface(head_dir(theta, phi))


def solve_theta(phi, y_rel):
    """Polar angle (from the top) of the skin point at azimuth phi whose height above HC is y_rel."""
    phi = np.asarray(phi, float)
    y_rel = np.broadcast_to(np.asarray(y_rel, float), phi.shape)
    lo, hi = np.zeros_like(phi), np.full_like(phi, np.pi)
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        y = skin(mid, phi)[0][..., 1] - HC[1]
        above = y > y_rel
        lo = np.where(above, mid, lo)
        hi = np.where(above, hi, mid)
    return 0.5 * (lo + hi)


def build_head(skin_m):
    R, C = 43, 88
    th = np.linspace(0.0, np.pi, R)
    ph = np.pi + np.linspace(0.0, 2 * np.pi, C, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")
    P, _ = skin(TH, PH)
    return grids_to_object("tim_head", [Grid(P, pole0=True, pole1=True)], mats=[skin_m])


EAR_Y, EAR_A, EAR_BH, EAR_CW = -0.034, 0.024, 0.052, 0.037
EAR_TOP = EAR_Y + EAR_BH * 0.98


def ear_grid(side):
    s = 1.0 if side == "L" else -1.0
    yr, zr = EAR_Y, -0.006
    xr = s * HRX * math.sqrt(1 - (yr / HRY_BOT) ** 2 - (zr / HRZ) ** 2)
    p = HC + np.array([xr, yr, zr])
    nrm = _n(np.array([xr / HRX ** 2, yr / HRY_BOT ** 2, zr / HRZ ** 2]))
    a = _n(nrm + np.array([0.0, 0.02, 0.24]))           # faces a little forward
    b = _n(np.array([0.0, 1.0, -0.10]) - a * np.dot(a, [0.0, 1.0, -0.10]))   # top leans back
    c = s * np.cross(a, b)                                 # toward the face
    A, Bh, Cw = EAR_A, EAR_BH, EAR_CW
    centre = p + nrm * 0.004
    R_, C_ = 17, 28
    al = np.linspace(0.0, np.pi, R_)
    be = np.linspace(0.0, 2 * np.pi, C_, endpoint=False)
    AL, BE = np.meshgrid(al, be, indexing="ij")
    ua, ub, uc = np.cos(AL), np.sin(AL) * np.cos(BE), np.sin(AL) * np.sin(BE)
    la, lb, lc = A * ua, Bh * ub, Cw * uc
    # C-shaped bowl on the outer face, centred toward the face -> the rim reads as a "C"
    q = (lb / (0.60 * Bh)) ** 2 + ((lc - 0.30 * Cw) / (0.56 * Cw)) ** 2
    bowl = np.clip(1.0 - q, 0.0, 1.0) ** 1.4
    la = la - 0.0135 * bowl * sstep(-0.1, 0.5, ua)
    P = centre + la[..., None] * a + lb[..., None] * b + lc[..., None] * c
    return Grid(P, pole0=True, pole1=True)


# ---------------------------------------------------------------------------------------------
# hair H3, textured crop: one smooth shell over the scalp
HAIRLINE = Curve([(0, 0.206), (14, 0.206), (24, 0.205), (30, 0.204), (34, 0.210), (39, 0.232),
                  (44, 0.255), (50, 0.262), (55, 0.246), (60, 0.200), (65, 0.132), (71, 0.056),
                  (76, 0.004), (80, -0.024), (84, -0.016), (88, 0.012), (92, 0.026), (96, 0.022),
                  (101, 0.000), (107, -0.030), (116, -0.058), (130, -0.082), (150, -0.096),
                  (166, -0.101), (180, -0.102)])
LIP = Curve([(0, 0.024), (27, 0.024), (33, 0.019), (39, 0.011), (48, 0.0075), (72, 0.0058),
             (95, 0.0050), (130, 0.0042), (180, 0.0038)])
NOTCHES = [(-26.5, 0.0016, 3.4), (-18.8, 0.0024, 3.8), (-10.9, 0.0017, 3.4), (-3.2, 0.0026, 4.0),
           (5.1, 0.0019, 3.6), (13.2, 0.0025, 3.8), (21.0, 0.0017, 3.4)]
HAIR_TOP = 0.048
HAIR_IN = 0.004


def _wrapdeg(phd):
    return (np.asarray(phd, float) + 180.0) % 360.0 - 180.0


def notch_profile(phd):
    phd = _wrapdeg(phd)
    out = np.zeros_like(phd)
    for c, a, w in NOTCHES:
        u = (phd - c) / w
        v = np.clip(1.0 - np.sqrt(u * u + 0.15 ** 2), 0.0, None) / (1.0 - 0.15)
        out += a * v * v * (3 - 2 * v)
    return out


def groove_profile(phd):
    phd = _wrapdeg(phd)
    out = np.zeros_like(phd)
    for c, a, w in NOTCHES:
        out += (a / 0.0035) * np.exp(-((phd - c) / (w * 1.35)) ** 2)
    return out


def hair_edge_y(phd):
    return HAIRLINE(np.abs(_wrapdeg(phd))) + notch_profile(phd)


PARTING_Y = Curve([(0, 0.08), (22, 0.08), (40, 0.15), (58, 0.235), (75, 0.27), (100, 0.275), (140, 0.235),
                   (180, 0.205)])
THIN = Curve([(0, 0.012), (100, 0.012), (140, 0.0105), (180, 0.0100)])


def hair_thickness(phd, s, y_rel):
    """Shell thickness over the skin point at azimuth phd (deg), crown->hairline parameter s and height
    y_rel above the head centre.  The top keeps a uniform, gently rounded volume; below a soft 'parting'
    height the sides and back sit tight to the scalp; the front volume runs down into the fringe lip."""
    phd = np.asarray(phd, float)
    s = np.asarray(s, float)
    a = np.abs(_wrapdeg(phd))
    w_front = 1.0 - sstep(22.0, 48.0, a)
    te = LIP(a) * (1.0 - 0.18 * groove_profile(phd) * w_front)
    yp = PARTING_Y(a)
    core = THIN(a) + (HAIR_TOP - THIN(a)) * sstep(yp - 0.075, yp + 0.075, y_rel)
    e = w_front * s ** 3.2 + (1.0 - w_front) * sstep(0.84, 1.0, s)
    t = core * (1.0 - e) + te * e
    t = t - 0.0012 * groove_profile(phd) * sstep(0.60, 0.97, s) * w_front
    return t


def hair_t_at(theta, phi):
    """Hair thickness over a skin point (0 outside the hair)."""
    phd = np.degrees(phi)
    th_h = solve_theta(np.asarray(phi, float), hair_edge_y(phd))
    s = np.asarray(theta, float) / th_h
    y_rel = skin(np.asarray(theta, float), np.asarray(phi, float))[0][..., 1] - HC[1]
    return np.where(s <= 1.0, hair_thickness(phd, np.clip(s, 0, 1), y_rel), 0.0)


# (the hair itself is built in items/tim_hair.py: sculpted shell + clump locks)


# ---------------------------------------------------------------------------------------------
# glasses: thin round wire rings, bridge, temple arms
WIRE_R = 0.0055
RING_R = 0.092


def eye_surface(side):
    s = 1.0 if side == "L" else -1.0
    x, y = s * EYE_X, EYE_Y
    z = HRZ * math.sqrt(1 - (x / HRX) ** 2 - (y / HRY_BOT) ** 2)
    p = HC + np.array([x, y, z])
    n = _n(np.array([x / HRX ** 2, y / HRY_BOT ** 2, z / HRZ ** 2]))
    return p, n


def ring_frame(side):
    p, n = eye_surface(side)
    a = _n(0.85 * n + 0.15 * np.array([0.0, 0.0, 1.0]))
    a = _n(a * np.array([1.0, 0.35, 1.0]))          # keep the ring nearly upright
    e1 = _n(np.cross([0.0, 1.0, 0.0], a))
    e2 = np.cross(a, e1)
    ts = np.linspace(0, 2 * np.pi, 96, endpoint=False)
    d0 = 0.004
    for _ in range(200):
        c = p + a * d0
        pts = c + RING_R * (np.cos(ts)[:, None] * e1 + np.sin(ts)[:, None] * e2)
        clr = head_clearance(pts - HC) - WIRE_R
        if clr.min() >= 0.0065:
            break
        d0 += 0.0005
    return c, a, e1, e2, d0, clr.min()


def torus_grid(c, axis, e1, e2, R, r, major=72, minor=8):
    t = np.linspace(0, 2 * np.pi, major, endpoint=False)
    g = np.linspace(0, 2 * np.pi, minor, endpoint=False)
    T_, G_ = np.meshgrid(t, g, indexing="ij")
    radial = np.cos(T_)[..., None] * e1 + np.sin(T_)[..., None] * e2
    P = c + R * radial + r * (np.cos(G_)[..., None] * radial + np.sin(G_)[..., None] * axis)
    return Grid(P, wrap_u=True, wrap_v=True)


def skin_offset_point(phd, y_rel, off, add_hair=True):
    phi = np.radians(phd)
    th = solve_theta(np.array([phi]), np.array([y_rel]))[0]
    p, n = skin(th, phi)
    extra = float(hair_t_at(np.array([th]), np.array([phi]))[0]) if add_hair else 0.0
    return p + n * (off + extra)


def _surface_bvh(objs):
    """BVH over the given mesh objects (Blender coords; the objects are still unparented, identity)."""
    from mathutils.bvhtree import BVHTree
    verts, polys = [], []
    for o in objs:
        base = len(verts)
        verts.extend(o.matrix_world @ v.co for v in o.data.vertices)
        polys.extend([base + i for i in p.vertices] for p in o.data.polygons)
    return BVHTree.FromPolygons(verts, polys)


def _outer_hit(bvh, p, n, far=0.12):
    """Outermost surface point along the line p + n*t (three.js coords), cast inward from outside."""
    o = to_blender(p + n * far)
    d = to_blender(-n)
    hit = bvh.ray_cast(Vector(o.tolist()), Vector(d.tolist()), far * 2)
    if hit[0] is None:
        return None
    h = np.array(hit[0])
    return np.array([h[0], h[2], -h[1]])


def build_glasses(wire_m, info, surface_objs=()):
    grids = []
    bvh = _surface_bvh(surface_objs) if surface_objs else None
    frames = {}
    for side in "LR":
        c, a, e1, e2, d0, clr = ring_frame(side)
        frames[side] = (c, a, e1, e2)
        info[f"ring_{side}"] = dict(centre=[round(float(v), 4) for v in c], plane_offset=round(d0, 4),
                                    min_clear=round(float(clr), 4))
        grids.append(torus_grid(c, a, e1, e2, RING_R, WIRE_R))
    # bridge: inner ring points, arched up over the nose line
    cL, aL, e1L, e2L = frames["L"]
    cR, aR, e1R, e2R = frames["R"]
    ang = math.radians(14)
    pL = cL + RING_R * (-math.cos(ang) * e1L + math.sin(ang) * e2L)
    pR = cR + RING_R * (math.cos(ang) * e1R + math.sin(ang) * e2R)
    ymid = EYE_Y + 0.040
    zmid = HRZ * math.sqrt(1 - (ymid / HRY_TOP) ** 2) + 0.012
    mid = HC + np.array([0.0, ymid, zmid])
    br = resample([pL, 0.5 * (pL + mid) + np.array([0, 0.004, 0.002]), mid,
                   0.5 * (pR + mid) + np.array([0, 0.004, 0.002]), pR], 24)
    grids.append(tube_grid(br, WIRE_R * 0.92, segs=8, cap0=WIRE_R, cap1=WIRE_R, ncap=3))
    # temple arms: from the outer ring point straight back, hugging the side of the head (over the hair)
    # to the ear root, passing above the ear and hooking down behind it.  The path is pushed onto the
    # real outer surface (head + hair meshes) so it never floats off the head or sinks into the hair.
    clear = WIRE_R + 0.0014
    for side, (c, a, e1, e2) in frames.items():
        s = 1.0 if side == "L" else -1.0
        hang = math.radians(12)
        hinge = c + RING_R * (s * math.cos(hang) * e1 + math.sin(hang) * e2)
        ph_h = math.degrees(math.atan2(abs(hinge[0] - HC[0]), hinge[2] - HC[2]))
        y_h = float(hinge[1] - HC[1])
        y_ear = EAR_TOP + 0.001            # rests in the crease where the top of the ear meets the head
        keys = [(ph_h + 7, y_h + 0.002), (ph_h + 16, y_h + 0.005), (66, 0.5 * (y_h + y_ear) + 0.003),
                (78, y_ear + 0.003), (87, y_ear + 0.001), (94, y_ear - 0.002), (99.0, y_ear - 0.012),
                (102.5, y_ear - 0.030), (104.5, y_ear - 0.046)]
        pts = [hinge + a * 0.002]
        for phd, yr in keys:
            if phd <= ph_h + 2:
                continue
            pts.append(skin_offset_point(s * phd, yr, clear, add_hair=False))
        path = resample(pts, 44)
        # hinge gap: the first stretch eases from the hinge (in front of the skin) onto the surface
        ph_path = np.degrees(np.arctan2(np.abs(path[:, 0] - HC[0]), path[:, 2] - HC[2]))
        if bvh is not None:
            for it in range(6):
                for i in range(1, len(path)):
                    q = path[i] - HC
                    nq = _n(q * np.array([1.0 / HRX ** 2, 1.0 / HRY_TOP ** 2, 1.0 / HRZ ** 2]))
                    h = _outer_hit(bvh, path[i], nq)
                    if h is None:
                        continue
                    want = float(np.dot(h - HC, nq)) + clear
                    have = float(np.dot(q, nq))
                    w_free = float(sstep(ph_h + 14.0, ph_h + 2.0, ph_path[i]))   # near the hinge: no pull
                    if have < want:
                        path[i] = path[i] + nq * (want - have)
                    elif it < 5:
                        path[i] = path[i] - nq * (have - want) * (1.0 - w_free)
                sm = path.copy()
                sm[1:-1] = 0.5 * path[1:-1] + 0.25 * (path[:-2] + path[2:])
                path = sm
            # final guarantee: nothing under the surface; log the gap (wire centre - surface) per side
            gaps = []
            for i in range(1, len(path)):
                q = path[i] - HC
                nq = _n(q * np.array([1.0 / HRX ** 2, 1.0 / HRY_TOP ** 2, 1.0 / HRZ ** 2]))
                h = _outer_hit(bvh, path[i], nq)
                if h is not None:
                    want = float(np.dot(h - HC, nq)) + clear * 0.92
                    have = float(np.dot(q, nq))
                    if have < want:
                        path[i] = path[i] + nq * (want - have)
                        have = want
                    if i > len(path) // 4:
                        gaps.append(have - want + clear * 0.92)
            info[f"temple_{side}_gap"] = [round(min(gaps), 4), round(max(gaps), 4)]
        grids.append(tube_grid(path, WIRE_R, segs=8, cap0=WIRE_R * 0.8, cap1=WIRE_R, ncap=3))
        # hinge knuckle
        grids.append(tube_grid(resample([hinge - a * 0.003, hinge + a * 0.006], 4), WIRE_R * 1.35, segs=8,
                               cap0=WIRE_R * 1.3, cap1=WIRE_R * 1.3, ncap=3))
    return grids_to_object("tim_glasses", grids, mats=[wire_m])


# ---------------------------------------------------------------------------------------------
# hoodie body (superellipse loft) + kangaroo pocket
TORSO_PROFILE = [  # y, half-width, half-depth, z-centre
    (0.4010, 0.000, 0.000, 0.000), (0.4012, 0.070, 0.052, 0.000), (0.4025, 0.118, 0.087, 0.001),
    (0.4055, 0.146, 0.107, 0.001), (0.4110, 0.161, 0.118, 0.002), (0.4200, 0.1665, 0.1225, 0.002),
    (0.4400, 0.1675, 0.1235, 0.002), (0.4555, 0.1655, 0.1215, 0.002), (0.4630, 0.1690, 0.1255, 0.003),
    (0.4760, 0.1740, 0.1305, 0.004), (0.5200, 0.1770, 0.1335, 0.004), (0.5800, 0.1755, 0.1325, 0.003),
    (0.6400, 0.1705, 0.1290, 0.002), (0.7000, 0.1625, 0.1230, 0.000), (0.7600, 0.1505, 0.1150, -0.002),
    (0.8100, 0.1330, 0.1030, -0.003), (0.8450, 0.1050, 0.0830, -0.003), (0.8680, 0.0650, 0.0520, -0.002),
    (0.8780, 0.0250, 0.0200, -0.001), (0.8800, 0.000, 0.000, 0.000)]
HEM_TOP = 0.4575
_TP = np.array(TORSO_PROFILE)
_TU = np.arange(len(_TP), dtype=float)
TORSO_Y = Curve(list(zip(_TU, _TP[:, 0])))
TORSO_A = Curve(list(zip(_TU, _TP[:, 1])))
TORSO_B = Curve(list(zip(_TU, _TP[:, 2])))
TORSO_ZC = Curve(list(zip(_TU, _TP[:, 3])))
TORSO_N = Curve([(0.40, 2.5), (0.45, 2.75), (0.60, 2.65), (0.80, 2.4), (0.88, 2.2)])
# profile parameter for a given height (sides region, for surface queries)
_uu = np.linspace(0, len(_TP) - 1, 4000)
_yy = TORSO_Y(_uu)
_side = (_uu >= 5) & (_uu <= 16)
TORSO_U_OF_Y = Curve(list(zip(_yy[_side][::20], _uu[_side][::20])), mode="cr")

POCKET = np.array([(-0.118, 0.468), (0.118, 0.468), (0.118, 0.540), (0.068, 0.600), (-0.068, 0.600),
                   (-0.118, 0.540)])
POCKET_H = 0.0095


def _pocket_lines():
    ctr = POCKET.mean(axis=0)
    out = []
    for i in range(len(POCKET)):
        a, b = POCKET[i], POCKET[(i + 1) % len(POCKET)]
        d = _n(b - a)
        nrm = np.array([d[1], -d[0]])
        if np.dot(nrm, ctr - a) > 0:
            nrm = -nrm
        out.append((a, nrm))
    return out


_PL = _pocket_lines()


def pocket_sdf(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ds = np.stack([(x - a[0]) * nr[0] + (y - a[1]) * nr[1] for a, nr in _PL], axis=0)
    k = 0.0035
    mx = ds.max(axis=0)
    return mx + k * np.log(np.sum(np.exp((ds - mx) / k), axis=0))


def pocket_disp(x, y, z=None):
    d = pocket_sdf(x, y)
    out = POCKET_H * sstep(-0.0005, 0.0065, -d)
    if z is not None:
        out = out * (np.asarray(z) > 0)
    return out


def superellipse_xz(a, b, zc, n, psi):
    s_, c_ = np.sin(psi), np.cos(psi)
    x = a * np.sign(s_) * np.abs(s_) ** (2.0 / n)
    z = zc + b * np.sign(c_) * np.abs(c_) ** (2.0 / n)
    gx = np.sign(x) * np.abs(x / np.maximum(a, 1e-9)) ** (n - 1) / np.maximum(a, 1e-9)
    gz = np.sign(z - zc) * np.abs((z - zc) / np.maximum(b, 1e-9)) ** (n - 1) / np.maximum(b, 1e-9)
    g = _n(np.stack([gx, np.zeros_like(gx), gz], axis=-1))
    return x, z, g


def torso_front(x, y):
    """Front surface point + normal of the (undisplaced) hoodie body at (x, y)."""
    u = TORSO_U_OF_Y(y)
    a, b, zc, n = TORSO_A(u), TORSO_B(u), TORSO_ZC(u), TORSO_N(y)
    xx = np.clip(np.abs(x) / a, 0, 0.999)
    z = zc + b * (1 - xx ** n) ** (1.0 / n)
    gx = np.sign(x) * xx ** (n - 1) / a
    gz = ((z - zc) / b) ** (n - 1) / b
    nrm = _n(np.stack([gx, np.zeros_like(np.asarray(gx, float)), gz], axis=-1))
    return np.stack([np.asarray(x, float) * np.ones_like(z), np.asarray(y, float) * np.ones_like(z), z], -1), nrm


def build_hoodie(navy, dark, cream):
    # rows by arc length along the profile, denser across the pocket band
    uu = np.linspace(0, len(_TP) - 1, 3000)
    ys, As = TORSO_Y(uu), TORSO_A(uu)
    ds = np.sqrt(np.diff(As) ** 2 + np.diff(ys) ** 2)
    ym = 0.5 * (ys[1:] + ys[:-1])
    dens = 1.0 + 1.3 * sstep(0.445, 0.465, ym) * (1.0 - sstep(0.605, 0.625, ym)) - 0.45 * sstep(0.74, 0.80, ym)
    cum = np.concatenate([[0.0], np.cumsum(ds * dens)])
    nrows = 62
    targets = np.linspace(0, cum[-1], nrows)
    urow = np.interp(targets, cum, uu)
    C = 120
    uc = np.linspace(-np.pi, np.pi, C, endpoint=False)
    psi = uc - 0.38 * np.sin(uc)
    rows = []
    for u in urow:
        y = float(TORSO_Y(u))
        a, b, zc, n = float(TORSO_A(u)), float(TORSO_B(u)), float(TORSO_ZC(u)), float(TORSO_N(y))
        x, z, g = superellipse_xz(a, b, zc, n, psi)
        P = np.stack([x, np.full_like(x, y), z], axis=-1)
        if 0.44 < y < 0.63:
            P = P + g * pocket_disp(x, y, z)[:, None]
        rows.append(P)
    P = np.array(rows)
    body = Grid(P, pole0=True, pole1=True, face_mat=lambda r, c, ctr: 1 if ctr[1] < HEM_TOP else 0)
    grids = [body]
    # pocket trims along the two slanted openings (dark), lying on the raised lip
    for (i0, i1) in ((2, 3), (5, 4)):
        a2, b2 = POCKET[i0], POCKET[i1]
        dirv = _n(b2 - a2)
        inward = -_PL[i0][1] if i0 == 2 else -_PL[4][1]
        pts = []
        for t in np.linspace(-0.004, 1.004, 14):
            xy = a2 + (b2 - a2) * t + inward * 0.0028
            p, nrm = torso_front(xy[0], xy[1])
            dsp = float(pocket_disp(xy[0], xy[1]))
            pts.append(p + nrm * (dsp + 0.0016))
        pts = np.array(pts)
        _, nrm0 = torso_front(float(pts[0][0]), float(pts[0][1]))
        grids.append(tube_grid(pts, 0.0043, segs=10, cap0=0.004, cap1=0.004, ncap=3, ref=nrm0,
                               squash=(0.62, 1.0), face_mat=lambda r, c, ctr: 1))
    # drawstrings: from the hood ring front, splayed outward over the chest, with aglets
    for s in (1.0, -1.0):
        pts = []
        for t in np.linspace(0.0, 1.0, 16):
            x = s * (0.027 + 0.036 * t ** 0.85 + 0.004 * math.sin(math.pi * t))
            y = 0.684 - 0.112 * t
            p, nrm = torso_front(x, y)
            pts.append(p + nrm * (float(pocket_disp(x, y)) + 0.0072 + 0.004 * (1 - t) ** 2))
        pts = np.array(pts)
        grids.append(tube_grid(pts, 0.0063, segs=10, cap0=0.006, cap1=0.006, ncap=3,
                               face_mat=lambda r, c, ctr: 2))
        tip = pts[-1]
        d = _n(pts[-1] - pts[-3])
        ag = np.array([tip - d * 0.004, tip + d * 0.020])
        grids.append(tube_grid(resample(ag, 6), 0.0082, segs=10, cap0=0.007, cap1=0.008, ncap=3,
                               face_mat=lambda r, c, ctr: 2))
    return grids_to_object("tim_hoodie", grids, mats=[navy, dark, cream])


HOOD_Y = Curve([(0, 0.676), (40, 0.684), (90, 0.700), (140, 0.700), (180, 0.694), (220, 0.700), (270, 0.700),
                (320, 0.684)], period=360.0, mode="cr")
HOOD_R = Curve([(0, 0.020), (35, 0.025), (90, 0.034), (135, 0.046), (180, 0.054), (225, 0.046), (270, 0.034),
                (325, 0.025)], period=360.0, mode="cr")


def build_hood(navy):
    nb, ns = 120, 18
    beta = np.linspace(0, 2 * np.pi, nb, endpoint=False)
    bd = np.degrees(beta)
    back = sstep(100, 180, np.abs(_wrapdeg(bd)))
    ax = 0.153
    az = 0.117 + 0.006 * back
    r = HOOD_R(bd)
    out = 0.45 * r * back
    centre = np.stack([(ax + 0.012 * back) * np.sin(beta), HOOD_Y(bd) - 0.012 * back,
                       -0.004 + az * np.cos(beta)], axis=-1)
    T = _n(np.roll(centre, -1, axis=0) - np.roll(centre, 1, axis=0))
    radial = _n(np.stack([np.sin(beta), np.zeros_like(beta), np.cos(beta)], -1))
    O = _n(radial - T * np.sum(radial * T, axis=1, keepdims=True))
    U = np.cross(T, O)
    U = U * np.sign(U[:, 1:2])
    centre = centre + O * out[:, None]
    g = np.linspace(0, 2 * np.pi, ns, endpoint=False)
    P = (centre[:, None, :] + (r[:, None, None]) * (np.cos(g)[None, :, None] * O[:, None, :] * 1.0
                                                    + np.sin(g)[None, :, None] * U[:, None, :] * 1.18))
    return grids_to_object("tim_hood", [Grid(P, wrap_u=True, wrap_v=True)], mats=[navy])


def torso_back(x, y):
    """Back surface point + outward normal of the (undisplaced) hoodie body at (x, y)."""
    u = TORSO_U_OF_Y(y)
    a, b, zc, n = TORSO_A(u), TORSO_B(u), TORSO_ZC(u), TORSO_N(y)
    xx = np.clip(np.abs(x) / a, 0, 0.999)
    zz = b * (1 - xx ** n) ** (1.0 / n)
    z = zc - zz
    gx = np.sign(x) * xx ** (n - 1) / a
    gz = -(zz / b) ** (n - 1) / b
    nrm = _n(np.stack([gx, np.zeros_like(np.asarray(gx, float)), gz], axis=-1))
    return np.stack([np.asarray(x, float) * np.ones_like(z), np.asarray(y, float) * np.ones_like(z), z], -1), nrm


POUCH_TOP, POUCH_BOT, POUCH_HW, POUCH_H = 0.715, 0.528, 0.100, 0.019


def build_hood_pouch(navy):
    """The folded-down hood lying on the upper back: a soft pillow, wide under the collar ring, narrowing to
    a rounded point, with a centre seam dip.  Each cross-section conforms to the back surface."""
    nr, nc = 22, 30
    ys = np.linspace(POUCH_TOP, POUCH_BOT, nr)
    v = (POUCH_TOP - ys) / (POUCH_TOP - POUCH_BOT)
    hw = POUCH_HW * (1.0 - v ** 2.2) ** 0.55 * (1.0 + 0.06 * np.sin(np.pi * v))
    hh = POUCH_H * (1.0 - v ** 3.0) ** 0.5 * (0.85 + 0.15 * np.sin(np.pi * np.clip(v * 1.4, 0, 1)))
    g = np.linspace(0, 2 * np.pi, nc, endpoint=False)
    cg, sg = np.cos(g), np.sin(g)
    xs = np.sign(cg) * np.abs(cg) ** 0.7
    rows = []
    for i, y in enumerate(ys):
        x = hw[i] * xs
        p, nrm = torso_back(x, np.full_like(x, y))
        seam = 1.0 - 0.22 * np.exp(-(x / 0.012) ** 2)
        out = np.where(sg > 0, hh[i] * np.abs(sg) ** 0.55 * seam, -0.006 * np.abs(sg))
        rows.append(p + nrm * (out[:, None] + 0.001))
    p0, n0 = torso_back(np.array([0.0]), np.array([POUCH_TOP + 0.01]))
    p1, n1 = torso_back(np.array([0.0]), np.array([POUCH_BOT - 0.004]))
    P = np.array([np.repeat(p0 - n0 * 0.004, nc, 0)] + rows + [np.repeat(p1 + n1 * 0.002, nc, 0)])
    return grids_to_object("tim_hood_pouch", [Grid(P, pole0=True, pole1=True)], mats=[navy])


# ---------------------------------------------------------------------------------------------
# sleeves, mittens, legs, seat, shoes
def arm_path(side, ext=0.012):
    S, E, W = (np.array(J_REST[f"{j}_{side}"]) for j in ("upperarm", "forearm", "hand"))
    dW = _n(W - E)
    raw = np.concatenate([np.linspace(S, E, 18, endpoint=False), np.linspace(E, W, 18, endpoint=False),
                          np.linspace(W, W + dW * ext, 3)])
    sm = raw.copy()
    for _ in range(25):
        sm[1:-1] = 0.5 * sm[1:-1] + 0.25 * (sm[:-2] + sm[2:])
    return sm, S, E, W


def build_sleeve(side, navy, dark):
    path, S, E, W = arm_path(side)
    sl = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    Ltot = sl[-1]
    cuff0 = Ltot - 0.037
    rad = Curve([(0.0, 0.058), (0.07, 0.0565), (0.165, 0.0515), (0.25, 0.0478), (cuff0 - 0.004, 0.0468),
                 (cuff0 + 0.004, 0.0497), (Ltot - 0.012, 0.0505), (Ltot, 0.0492)])(sl)
    g = tube_grid(path, rad, segs=24, cap0=0.058, cap1=0.010, ncap=6, ref=(0.0, 0.0, 1.0))
    # soft fabric: a gentle bunching above the cuff (two diagonal rolls) and a slight elbow crease
    T_, N_, B_ = frames_along(path, (0.0, 0.0, 1.0))
    pre = 6
    ang = 2 * np.pi * np.arange(24) / 24
    for i in range(len(path)):
        r = pre + i
        ctr = path[i]
        rel = g.P[r] - ctr
        L = np.linalg.norm(rel, axis=1, keepdims=True)
        d = rel / np.maximum(L, 1e-9)
        x = sl[i]
        band = float(sstep(cuff0 - 0.085, cuff0 - 0.06, x) * (1 - sstep(cuff0 - 0.012, cuff0 - 0.002, x)))
        roll = np.cos(2 * np.pi * (x - cuff0) / 0.030 + 0.9 * np.cos(ang - 0.6))
        bump = 0.0024 * band * (0.5 + 0.5 * roll)
        el = float(np.exp(-((x - 0.165) / 0.022) ** 2))
        crease = -0.0028 * el * np.clip(np.cos(ang), 0, None) ** 3   # front of the elbow
        g.P[r] = ctr + d * (L + (bump + crease)[:, None])
    # material per face by arc position along the sleeve
    P = g.P
    R_ = P.shape[0]
    centres = P.mean(axis=1)
    def fm(r, c, ctr):
        # project onto the path
        i = int(np.argmin(np.linalg.norm(path - ctr, axis=1)))
        return 1 if sl[i] > cuff0 else 0
    g.face_mat = fm
    return grids_to_object(f"tim_sleeve_{side}", [g], mats=[navy, dark])


def mitten_grid(side):
    """A soft mitten: a flattened paddle for the fingers plus a separate rounded thumb on the front / palm
    side near the wrist (returns a list of grids)."""
    Lx, Px, Tx = _hand_axes(side)
    W = np.array(J_REST[f"hand_{side}"])
    ctr = W + Lx * HAND_CENTRE_OFF
    R_, C_ = 21, 32
    al = np.linspace(0, np.pi, R_)
    be = np.linspace(0, 2 * np.pi, C_, endpoint=False)
    AL, BE = np.meshgrid(al, be, indexing="ij")
    ul, up, ut = np.cos(AL), np.sin(AL) * np.cos(BE), np.sin(AL) * np.sin(BE)
    n_ = 2.4
    f = lambda v: np.sign(v) * np.abs(v) ** (2.0 / n_)
    k = HAND_SCALE
    aL = k * (0.0395 + 0.0018 * ul)
    aP = k * 0.0200 * (1.0 - 0.12 * ul) * np.where(up > 0, 0.88, 1.0)
    aT = k * 0.0315 * (1.0 + 0.08 * ul) * np.where(ut > 0, 0.94, 1.0)
    xl, xp, xt = aL * f(ul), aP * f(up), aT * f(ut)
    # fingertip end slightly rounder / fuller than the heel of the hand
    xp = xp * (1.0 + 0.10 * sstep(0.2, 0.9, ul))
    P = ctr + xl[..., None] * Lx + xp[..., None] * Px + xt[..., None] * Tx
    paddle = Grid(P, pole0=True, pole1=True)
    # thumb: from inside the heel of the paddle, out to the front and down toward the fingers
    root = ctr + k * (-Lx * 0.013 + Tx * 0.016 + Px * 0.003)
    d1 = _n(Lx * 0.30 + Tx * 0.90 + Px * 0.22)
    d2 = _n(Lx * 0.80 + Tx * 0.50 + Px * 0.30)
    pts = resample([root, root + d1 * 0.016 * k, root + (d1 * 0.016 + d2 * 0.017) * k], 10)
    thumb = tube_grid(pts, k * np.linspace(0.0120, 0.0106, 10), segs=14, cap0=0.006 * k, cap1=0.0106 * k, ncap=4,
                      ref=tuple(Px))
    return [paddle, thumb]


LEG_RAD = Curve([(0.10, 0.0590), (0.112, 0.0592), (0.125, 0.0578), (0.16, 0.0570), (0.23, 0.0592), (0.30, 0.0620),
                 (0.36, 0.0642), (0.42, 0.0660)])


def build_leg(side, pants):
    x = LEG_X * (1 if side == "L" else -1)
    ys = np.linspace(0.42, 0.10, 34)
    path = np.stack([np.full_like(ys, x), ys, np.zeros_like(ys)], -1)
    g = tube_grid(path, LEG_RAD(ys), segs=24, cap0=0.066, cap1=0.010, ncap=6, ref=(0.0, 0.0, 1.0))
    # pants bunching softly over the shoe
    ang = 2 * np.pi * np.arange(24) / 24
    for i, y in enumerate(ys):
        r = 6 + i
        ctr = path[i]
        rel = g.P[r] - ctr
        L = np.linalg.norm(rel, axis=1, keepdims=True)
        band = float(sstep(0.10, 0.115, y) * (1 - sstep(0.15, 0.175, y)))
        roll = np.cos(2 * np.pi * (y - 0.10) / 0.028 + 0.8 * np.cos(ang + 0.4))
        g.P[r] = ctr + rel / np.maximum(L, 1e-9) * (L + (0.0022 * band * (0.5 + 0.5 * roll))[:, None])
    return grids_to_object(f"tim_leg_{side}", [g], mats=[pants])


def build_seat(pants):
    R_, C_ = 17, 40
    al = np.linspace(0, np.pi, R_)
    be = np.linspace(0, 2 * np.pi, C_, endpoint=False)
    AL, BE = np.meshgrid(al, be, indexing="ij")
    d = np.stack([np.sin(AL) * np.sin(BE), np.cos(AL), np.sin(AL) * np.cos(BE)], -1)
    n_ = 2.3
    f = lambda v: np.sign(v) * np.abs(v) ** (2.0 / n_)
    P = np.array([0.0, 0.425, -0.012]) + np.stack([0.150 * f(d[..., 0]), 0.070 * f(d[..., 1]),
                                                   0.112 * f(d[..., 2])], -1)
    return grids_to_object("tim_seat", [Grid(P, pole0=True, pole1=True)], mats=[pants])


SHOE_ZC, SHOE_HL = 0.038, 0.100


def shoe_outline(psi, grow=0.0):
    zrel = np.cos(psi)
    hw = 0.0505 + 0.0055 * zrel + grow
    hl = SHOE_HL + grow
    n_ = 2.35
    x = hw * np.sign(np.sin(psi)) * np.abs(np.sin(psi)) ** (2.0 / n_)
    z = SHOE_ZC + hl * np.sign(zrel) * np.abs(zrel) ** (2.0 / n_)
    return x, z


def toe_spring(P):
    P = P.copy()
    P[..., 1] += 0.010 * sstep(0.06, 0.145, P[..., 2])
    return P


def build_shoe(side, shoe_m, sole_m):
    x0 = LEG_X * (1 if side == "L" else -1)
    C_ = 48
    psi = np.linspace(0, 2 * np.pi, C_, endpoint=False)
    # upper: a chunky dome from the sole top to a crown at the ankle
    ox, oz = shoe_outline(psi)
    top = np.array([0.0, 0.106, -0.010])
    rows = []
    for v in np.linspace(0, 1, 17):
        hf = np.cos(v * np.pi / 2) ** 0.85
        x = top[0] + (ox - top[0]) * hf
        z = top[2] + (oz - top[2]) * hf
        y = 0.021 + (top[1] - 0.021) * np.sin(v * np.pi / 2) ** 0.95
        y = 0.021 + (y - 0.021) * (1.0 - 0.28 * sstep(0.03, 0.13, z) * (1 - v) ** 0.5)
        rows.append(np.stack([x + x0, y, z], -1))
    upper = Grid(toe_spring(np.array(rows)), pole1=True, face_mat=lambda r, c, ctr: 0)
    # close the upper's bottom: add a pole at the base centre
    base = np.stack([np.full(C_, x0), np.full(C_, 0.021), np.full(C_, SHOE_ZC)], -1)
    upper.P = np.concatenate([toe_spring(base[None]), upper.P], axis=0)
    upper.pole0 = True
    # sole: rounded slab, a touch larger than the upper
    e, Hs = 0.0085, 0.027
    sx, sz = shoe_outline(psi, grow=0.0035)
    cx, cz = 0.0, SHOE_ZC
    def ring(delta, y):
        vx, vz = sx - cx, sz - cz
        L = np.sqrt(vx * vx + vz * vz)
        k = (L + delta) / L
        return np.stack([cx + vx * k + x0, np.full(C_, y), cz + vz * k], -1)
    srows = [np.stack([np.full(C_, x0), np.zeros(C_), np.full(C_, cz)], -1)]
    for f in (0.45, 0.8):
        vx, vz = (sx - cx) * f, (sz - cz) * f
        srows.append(np.stack([cx + vx + x0, np.zeros(C_), cz + vz], -1))
    for j in range(0, 5):
        a = 0.5 * np.pi * j / 4
        srows.append(ring(-e + e * np.sin(a), e - e * np.cos(a)))
    for j in range(1, 5):
        a = 0.5 * np.pi * j / 4
        srows.append(ring(-e + e * np.cos(a), Hs - e + e * np.sin(a)))
    srows.append(ring(-0.025, Hs))
    srows.append(np.stack([np.full(C_, x0), np.full(C_, Hs), np.full(C_, cz)], -1))
    sole = Grid(toe_spring(np.array(srows)), pole0=True, pole1=True, face_mat=lambda r, c, ctr: 1)
    return grids_to_object(f"tim_shoe_{side}", [upper, sole], mats=[shoe_m, sole_m])


# ---------------------------------------------------------------------------------------------
# FK / IK pose solver (three.js axes; Blender XYZ Euler == three.js 'ZYX')
def V(t):
    return Vector((float(t[0]), float(t[1]), float(t[2])))


def qd(rx=0.0, ry=0.0, rz=0.0):
    return Euler((math.radians(rx), math.radians(ry), math.radians(rz)), "XYZ").to_quaternion()


class Pose:
    def __init__(self):
        self.q = {}
        self.l = {}

    def rot(self, j, rx=0.0, ry=0.0, rz=0.0):
        self.q[j] = qd(rx, ry, rz)
        return self

    def loc(self, j, x=0.0, y=0.0, z=0.0):
        self.l[j] = Vector((x, y, z))
        return self

    def copy(self):
        p = Pose()
        p.q = {k: v.copy() for k, v in self.q.items()}
        p.l = {k: v.copy() for k, v in self.l.items()}
        return p

    def world(self):
        W = {}
        for j in J_ORDER:
            par = J_PARENT[j]
            q = self.q.get(j, Quaternion())
            l = self.l.get(j, Vector())
            if par is None:
                W[j] = (q.copy(), V(J_REST[j]) + l)
            else:
                Qp, Pp = W[par]
                W[j] = (Qp @ q, Pp + Qp @ (V(J_REST[j]) - V(J_REST[par]) + l))
        return W


HAND_FR = {s: tuple(V(v) for v in _hand_axes(s)) for s in "LR"}


def hand_q(side, fingers, palm):
    L0, P0, T0 = HAND_FR[side]
    Lt = V(fingers).normalized()
    Pt = V(palm)
    Pt = (Pt - Lt * Pt.dot(Lt)).normalized()
    Tt = Pt.cross(Lt) if side == "L" else Lt.cross(Pt)
    M0 = Matrix((L0, P0, T0)).transposed()
    M1 = Matrix((Lt, Pt, Tt)).transposed()
    return (M1 @ M0.transposed()).to_quaternion()


def hand_local(side, along, palm):
    """A point on the mitten in its rest frame, as an offset from the wrist joint."""
    L0, P0, T0 = HAND_FR[side]
    return L0 * along + P0 * palm


GRIP_LOCAL = {s: V(J_REST[f"grip_{s}"]) - V(J_REST[f"hand_{s}"]) for s in "LR"}
U0 = {s: V(J_REST[f"forearm_{s}"]) - V(J_REST[f"upperarm_{s}"]) for s in "LR"}
F0 = {s: V(J_REST[f"hand_{s}"]) - V(J_REST[f"forearm_{s}"]) for s in "LR"}
IK_LOG = {}


def arm_ik(pose, side, target, hq, pole, local=None):
    """Place the mitten point `local` (rest offset from the wrist) at world `target` with world hand
    rotation `hq`; elbow bends toward `pole`.  Writes upperarm/forearm/hand local rotations."""
    W = pose.world()
    Qt, Pt = W["torso"]
    S = Pt + Qt @ (V(J_REST[f"upperarm_{side}"]) - V(J_REST["torso"]) + pose.l.get(f"upperarm_{side}", Vector()))
    local = GRIP_LOCAL[side] if local is None else local
    wrist = V(target) - hq @ local
    L1, L2 = U0[side].length, F0[side].length
    d = wrist - S
    D = d.length
    Dc = min(max(D, abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4)
    dh = d.normalized()
    wrist_c = S + dh * Dc
    a = (L1 * L1 - L2 * L2 + Dc * Dc) / (2 * Dc)
    h = math.sqrt(max(0.0, L1 * L1 - a * a))
    pv = V(pole)
    pv = (pv - dh * pv.dot(dh)).normalized()
    E = S + dh * a + pv * h
    q_ua = U0[side].rotation_difference(Qt.inverted() @ (E - S))
    Qu = Qt @ q_ua
    q_fa = F0[side].rotation_difference(Qu.inverted() @ (wrist_c - E))
    Qf = Qu @ q_fa
    q_h = Qf.inverted() @ hq
    pose.q[f"upperarm_{side}"] = q_ua
    pose.q[f"forearm_{side}"] = q_fa
    pose.q[f"hand_{side}"] = q_h
    fdir = (wrist_c - E).normalized()
    bend = math.degrees(fdir.angle(hq @ HAND_FR[side][0]))
    key = side
    lg = IK_LOG.setdefault(key, [0.0, 0.0, 0.0])
    lg[0] = max(lg[0], D / (L1 + L2))
    lg[1] = max(lg[1], bend)
    lg[2] = max(lg[2], (D - Dc))
    return D / (L1 + L2), bend


def qlerp_ex(q0, q1, f):
    """Rotation from q0 toward q1 by fraction f (f > 1 overshoots)."""
    d = q0.inverted() @ q1
    if d.w < 0:
        d.negate()
    axis, ang = d.to_axis_angle()
    return q0 @ Quaternion(axis, ang * f)


def ease_out_back(u, s=1.70158):
    u = clamp01(u) - 1.0
    return 1.0 + (s + 1.0) * u ** 3 + s * u ** 2


def ease_io(u):
    u = clamp01(u)
    return u * u * u * (u * (6 * u - 15) + 10)


def bake(rig, name, T, pose_fn, keys_rot, keys_loc, loop=True):
    a = rig.action(name)
    n = int(round(T * FPS))
    prev = {}
    first = None
    for i in range(n + 1):
        t = i / FPS
        if loop and i == n:
            p = first
        else:
            p = pose_fn(min(t, T))
        if i == 0:
            first = p
        rd, ld = {}, {}
        for j in keys_rot:
            q = p.q.get(j, Quaternion())
            e = q.to_euler("XYZ", prev[j]) if j in prev else q.to_euler("XYZ")
            prev[j] = e
            rd[j] = tuple(math.degrees(v) for v in e)
        for j in keys_loc:
            ld[j] = tuple(p.l.get(j, Vector()))
        a.key(t, rot=rd, loc=ld, interp="LINEAR")
    a.done()


# ---------------------------------------------------------------------------------------------
# actions
SIT_DY = 0.046            # hips loc y when seated: thigh / bottom underside on the seat top (y = 0.40)
SIT_HIPS_RX = 4.0
KEYS_SIT = ["hips", "torso", "neck", "upperarm_L", "forearm_L", "hand_L", "upperarm_R", "forearm_R", "hand_R",
            "thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R"]
LOCS_SIT = ["hips", "upperarm_L", "upperarm_R"]
KEYS_STAND = ["torso", "neck", "upperarm_L", "forearm_L", "hand_L", "upperarm_R", "forearm_R", "hand_R"]
LOCS_STAND = ["upperarm_L", "upperarm_R"]
SGN = {"L": 1.0, "R": -1.0}

# --- sit_type ---------------------------------------------------------------------------------
TYPE_T = 1.6
HOME = {"L": (0.07, 0.585, 0.37), "R": (-0.07, 0.585, 0.37)}
TAPS = {
    "L": ([0.00, 0.38, 0.80, 1.18], [0.017, 0.012, 0.019, 0.011],
          [(0.000, 0.000), (0.011, 0.009), (-0.006, -0.004), (0.008, 0.011)]),
    "R": ([0.19, 0.58, 0.97, 1.38], [0.013, 0.018, 0.011, 0.016],
          [(0.000, 0.000), (-0.010, 0.010), (0.006, -0.003), (-0.004, 0.012)]),
}
TYPE_CONTACT = {s: hand_local(s, 0.068, 0.0205) for s in "LR"}
TYPE_BREATH = Curve([(0.0, 0.0), (0.55, 1.0), (0.75, 0.92), (1.35, 0.08)], period=TYPE_T)
TYPE_BOB = Curve([(0.0, -0.15), (0.24, 1.0), (0.58, -0.55), (0.80, -0.05), (1.04, 0.85), (1.40, -0.70)],
                 period=TYPE_T)
TYPE_LOOK = Curve([(0.1, -1.0), (0.9, 1.0)], period=TYPE_T)
TYPE_SWAY = Curve([(0.05, -1.0), (0.45, 0.4), (0.85, 1.0), (1.25, -0.3)], period=TYPE_T)
LEG_SWING = Curve([(0.0, -1.0), (0.42, 1.0)], period=1.0)


def _lift(u, up=0.30):
    if u < up:
        v = u / up
        return 1.0 - (1.0 - v) ** 2
    v = (u - up) / (1.0 - up)
    return 1.0 - v ** 2.6


def tap_state(side, t):
    cs, hs, offs = TAPS[side]
    n = len(cs)
    tt = t % TYPE_T
    k = -1
    for i in range(n):
        if cs[i] <= tt + 1e-9:
            k = i
    if k == -1:
        k, c0, c1 = n - 1, cs[n - 1] - TYPE_T, cs[0]
    else:
        c0 = cs[k]
        c1 = cs[k + 1] if k + 1 < n else cs[0] + TYPE_T
    u = (tt - c0) / (c1 - c0)
    k2 = (k + 1) % n
    m = ease_io((u - 0.12) / 0.58)
    dx = offs[k][0] + (offs[k2][0] - offs[k][0]) * m
    dz = offs[k][1] + (offs[k2][1] - offs[k][1]) * m
    return hs[k] * _lift(u), dx, dz


def seated_legs(p, t_swing_L, t_swing_R, amp, foot_base, foot_amp, lag=0.12, splay=4.0):
    for side, ph in (("L", t_swing_L), ("R", t_swing_R)):
        sw = LEG_SWING(ph % 1.0)
        swl = LEG_SWING((ph - lag) % 1.0)
        p.rot(f"thigh_{side}", -90.0 - p_hips_rx(p), SGN[side] * splay, 0.0)
        p.rot(f"shin_{side}", 90.0 - amp * sw, 0.0, 0.0)
        p.rot(f"foot_{side}", foot_base + foot_amp * swl, 0.0, 0.0)


def p_hips_rx(p):
    q = p.q.get("hips", Quaternion())
    return math.degrees(q.to_euler("XYZ").x)


def pose_sit_type(t):
    p = Pose()
    p.loc("hips", 0.0, SIT_DY, 0.0).rot("hips", SIT_HIPS_RX)
    br = TYPE_BREATH(t)
    p.rot("torso", 8.0 + 0.8 * br, 1.3 * TYPE_SWAY(t), -0.6 * TYPE_SWAY(t + 0.25))
    for s in "LR":
        p.loc(f"upperarm_{s}", 0.0, 0.0025 * br, 0.024)
    p.rot("neck", -6.0 + 2.6 * TYPE_BOB(t), 1.6 * TYPE_LOOK(t), 0.9 * TYPE_SWAY(t + 0.5))
    seated_legs(p, t / TYPE_T, t / TYPE_T + 0.5, 11.0, 15.0, 7.0)
    for s in "LR":
        h, dx, dz = tap_state(s, t)
        tgt = Vector(HOME[s]) + Vector((dx * SGN[s], h + 0.003, dz))
        lift = h / 0.019
        f = Vector((-0.16 * SGN[s], -0.50 + 0.30 * lift, 0.84))
        hq = hand_q(s, f, (0.0, -1.0, -0.30 - 0.15 * lift))
        arm_ik(p, s, tgt, hq, (SGN[s] * 0.9, -0.6, -0.45), TYPE_CONTACT[s])
    return p


# --- sit_shock --------------------------------------------------------------------------------
SHOCK_T = 0.6


def _shock_target(hold=False):
    p = Pose()
    p.loc("hips", 0.0, SIT_DY, 0.0)
    k = 0.75 if hold else 1.0
    p.rot("hips", -2.0 * k)
    p.rot("torso", -8.0 * k + (1.0 if hold else 0.0))
    for s in "LR":
        p.loc(f"upperarm_{s}", 0.0, 0.013 * k, -0.004)
    p.rot("neck", -9.0 * k, 0.0, 0.0)
    hrx = p_hips_rx(p)
    for s in "LR":
        p.rot(f"thigh_{s}", (-104.0 if not hold else -99.0) - hrx, SGN[s] * 7.0, 0.0)
        p.rot(f"shin_{s}", 62.0 if not hold else 70.0, 0.0, 0.0)
        p.rot(f"foot_{s}", -14.0 if not hold else -6.0, 0.0, 0.0)
    for s in "LR":
        g = SGN[s]
        tgt = (g * 0.425, 0.935 - (0.022 if hold else 0.0), 0.080)
        hq = hand_q(s, (g * 0.30, 1.0, 0.18), (g * 0.15, -0.05, 1.0))
        arm_ik(p, s, tgt, hq, (g * 0.55, -1.0, -0.55))
    return p


SHOCK_TIMING = {  # joint group -> (delay, duration, overshoot)
    "hips": (0.0, 0.15, 1.3), "torso": (0.0, 0.16, 1.5), "neck": (0.03, 0.17, 1.6),
    "upperarm": (0.012, 0.17, 1.6), "forearm": (0.03, 0.17, 1.6), "hand": (0.045, 0.17, 1.7),
    "thigh": (0.0, 0.13, 1.5), "shin": (0.01, 0.14, 1.6), "foot": (0.03, 0.15, 1.8),
}
SHOCK_SETTLE_END = 0.48


def make_pose_sit_shock():
    p0 = pose_sit_type(0.0)
    p1 = _shock_target(False)
    p2 = _shock_target(True)

    def fn(t):
        p = Pose()
        for j in set(KEYS_SIT) | set(LOCS_SIT):
            grp = j.split("_")[0]
            dl, du, ov = SHOCK_TIMING[grp]
            q0, q1, q2 = (pp.q.get(j, Quaternion()) for pp in (p0, p1, p2))
            l0, l1, l2 = (pp.l.get(j, Vector()) for pp in (p0, p1, p2))
            if t <= dl:
                q, l = q0, l0
            elif t <= dl + du:
                f = ease_out_back((t - dl) / du, ov)
                q, l = qlerp_ex(q0, q1, f), l0.lerp(l1, f) if f <= 1 else l1 + (l1 - l0) * (f - 1)
            else:
                f = ease_io((t - dl - du) / (SHOCK_SETTLE_END - dl - du))
                q, l = qlerp_ex(q1, q2, f), l1.lerp(l2, f)
            if j in KEYS_SIT:
                p.q[j] = q
            if j in LOCS_SIT:
                p.l[j] = l
        return p
    return fn


# --- sit_idle ---------------------------------------------------------------------------------
IDLE_T = 2.4
BREATH = Curve([(0.0, 0.0), (0.95, 1.0), (1.2, 0.94), (2.05, 0.04)], period=2.4)
IDLE_LOOK = Curve([(0.2, -1.0), (0.7, -0.8), (1.4, 1.0), (1.9, 0.8)], period=2.4)
IDLE_NOD = Curve([(0.0, 0.0), (0.6, 0.6), (1.3, -0.4), (1.9, 0.3)], period=2.4)


def pose_sit_idle(t):
    p = Pose()
    p.loc("hips", 0.0, SIT_DY, 0.0).rot("hips", 2.0)
    br = BREATH(t)
    brl = BREATH(t - 0.15)
    p.rot("torso", 6.0 - 1.4 * br, 0.8 * IDLE_LOOK(t - 0.3), 0.0)
    for s in "LR":
        p.loc(f"upperarm_{s}", 0.0, 0.004 * brl, 0.010)
    p.rot("neck", -3.0 + 1.0 * brl + 1.4 * IDLE_NOD(t), 5.0 * IDLE_LOOK(t), 1.5 * IDLE_NOD(t + 0.6))
    seated_legs(p, t / IDLE_T, t / IDLE_T + 0.5, 3.5, 13.0, 3.0, lag=0.10)
    for s in "LR":
        g = SGN[s]
        hq = hand_q(s, (-g * 0.22, -0.18, 1.0), (g * 0.10, -1.0, 0.0))
        arm_ik(p, s, (g * 0.090, 0.537, 0.168), hq, (g * 1.0, -0.25, -0.55))
    return p


# --- stand_idle -------------------------------------------------------------------------------
STAND_SWAY = Curve([(0.0, 0.0), (0.8, 1.0), (1.6, -0.2), (2.0, -0.6)], period=2.4)


def pose_stand_idle(t):
    p = Pose()
    br = BREATH(t)
    brl = BREATH(t - 0.18)
    p.rot("torso", 1.0 - 1.1 * br, 0.6 * STAND_SWAY(t), 0.5 * STAND_SWAY(t - 0.6))
    for s in "LR":
        p.loc(f"upperarm_{s}", 0.0, 0.0045 * br, 0.0)
    p.rot("neck", 1.5 + 0.9 * brl, -1.5 * STAND_SWAY(t - 0.4), 0.8 * STAND_SWAY(t - 1.0))
    for s in "LR":
        g = SGN[s]
        p.rot(f"upperarm_{s}", 1.0 + 1.2 * STAND_SWAY(t - 0.3), 0.0, g * (-3.0 + 1.3 * brl))
        p.rot(f"forearm_{s}", -7.0 - 1.6 * BREATH(t - 0.32), g * 2.0, g * -2.0)
        p.rot(f"hand_{s}", -5.0 - 1.0 * BREATH(t - 0.45), g * -4.0, g * 3.0)
    return p


# --- stand_wash -------------------------------------------------------------------------------
# Base body for the dish cycle at the chibi-height island (top y 0.50, edge 0.17 in front of Tim): a
# forward lean so the short arms reach into the basin, breathing and a small scrub rhythm.  The engine
# drives the arms with procedural IK during the cycle (grab -> dip -> scrub -> rinse -> rack), so the
# baked arms here are only a plausible scrub loop (left hand on the plate rim, right hand scrubbing).
WASH_T = 1.0
WASH_GRIP_L = (0.104, 0.522, 0.270)
PLATE_TILT = -14.0                                     # plate face tips toward the camera (+z)
PLATE_CENTRE = (0.0, 0.497, 0.270)
SCRUB_R = 0.03


def plate_axes():
    tl = math.radians(PLATE_TILT)
    nrm = Vector((0.0, math.cos(tl), -math.sin(tl)))
    e1 = Vector((1.0, 0.0, 0.0))
    e2 = nrm.cross(e1)
    return nrm, e1, e2


def pose_stand_wash(t):
    p = Pose()
    ph = 2 * math.pi * 4.0 * t / WASH_T                 # four circles per loop
    lagc = math.cos(ph - 1.1)
    lags = math.sin(ph - 1.1)
    br = BREATH(t * 2.4)
    p.rot("torso", 14.0 + 0.4 * lags - 0.8 * br, -2.0 + 1.0 * lagc, 0.5 * lags)
    for s in "LR":
        p.loc(f"upperarm_{s}", 0.0, -0.006 + 0.002 * br, 0.018)
    p.loc("upperarm_R", 0.0, -0.006 + 0.002 * math.sin(ph - 0.5), 0.018 + 0.003 * math.cos(ph - 0.5))
    p.rot("neck", 8.0 + 0.6 * math.sin(2 * ph - 1.6), -3.0 + 0.6 * lagc, 0.4 * lags)
    nrm, e1, e2 = plate_axes()
    jig = Vector((0.0015 * math.cos(ph - 2.0), 0.002 * math.sin(ph - 2.0), 0.0))
    hqL = hand_q("L", (-0.10, -0.45, 1.0), (-1.0, 0.1, 0.0))
    arm_ik(p, "L", Vector(WASH_GRIP_L) + jig, hqL, (1.0, -0.6, -0.4))
    c = Vector(PLATE_CENTRE) + jig + nrm * 0.045
    tgt = c + e1 * (SCRUB_R * math.cos(ph) - 0.02) + e2 * (SCRUB_R * 0.8 * math.sin(ph))
    fR = Vector((0.35 + 0.15 * math.sin(ph + 0.6), -0.55, 1.0))
    hqR = hand_q("R", fR, -nrm)
    arm_ik(p, "R", tgt, hqR, (-1.0, -0.6, -0.4))
    return p


# --- stand_sink_idle --------------------------------------------------------------------------
# Deflated: both mittens resting on the island's front edge (y 0.50, z 0.17), shoulders dropped.
SINK_T = 2.4
SINK_BREATH = Curve([(0.0, 0.0), (1.0, 1.0), (1.25, 0.96), (2.1, 0.03)], period=2.4)
SINK_GRIP = {"L": (0.150, 0.514, 0.205), "R": (-0.150, 0.514, 0.205)}


def pose_stand_sink_idle(t):
    p = Pose()
    br = SINK_BREATH(t)
    brl = SINK_BREATH(t - 0.2)
    p.rot("torso", 13.0 - 1.4 * br, 0.4 * math.sin(2 * math.pi * t / SINK_T), 0.0)
    for s in "LR":
        p.loc(f"upperarm_{s}", 0.0, -0.016 + 0.008 * br, 0.016 - 0.004 * br)
    p.rot("neck", 14.0 - 1.6 * brl, -1.0, 0.8 * math.sin(2 * math.pi * (t - 0.6) / SINK_T))
    for s in "LR":
        g = SGN[s]
        hq = hand_q(s, (-g * 0.25, -0.40, 1.0), (g * 0.05, -1.0, 0.25))
        arm_ik(p, s, SINK_GRIP[s], hq, (g * 1.0, -0.3, -0.7))
    return p


# ---------------------------------------------------------------------------------------------
# skinning weights
def hoodie_weights(co):
    y = co.z
    w = float(sstep(0.455, 0.545, y))
    return {"hips": 1.0 - w, "torso": w}


def check_clearance(name, T, fn, n=24):
    """Debug: worst clearance of hands / forearms vs the head ellipsoid during an action."""
    worst = (9.0, 0.0, "")
    for i in range(n + 1):
        t = T * i / n
        p = fn(t)
        W = p.world()
        Qh, Ph = W["head"]
        for s in "LR":
            Qhd, Phd = W[f"hand_{s}"]
            Qf, Pf = W[f"forearm_{s}"]
            pts = {"hand": Phd + Qhd @ (HAND_FR[s][0] * HAND_CENTRE_OFF),
                   "wrist": Phd, "elbow": Pf, "midfore": (Pf + Phd) * 0.5}
            rad = {"hand": 0.03, "wrist": 0.048, "elbow": 0.052, "midfore": 0.05}
            for k, pt in pts.items():
                loc = Qh.inverted() @ (pt - Ph)
                c = float(head_clearance(np.array(loc))) - rad[k]
                if c < worst[0]:
                    worst = (c, t, f"{k}_{s}")
    print(f"[tim] clearance {name}: worst {worst[0]:+.3f} m at t={worst[1]:.2f} ({worst[2]})")


# ---------------------------------------------------------------------------------------------
def debug_props(r):
    pm = mat.prop("debug", "#c9b9a6")
    red = mat.prop("debug_red", "#d0402a")
    objs = []
    if DEBUG == "desk":
        objs.append(geo.rounded_box("dbg_seat", (0.44, 0.42, 0.04), 0.01, center=B(0, 0.38, -0.01), mat=pm))
        objs.append(geo.rounded_box("dbg_desk", (1.2, 0.55, 0.03), 0.005, center=B(0, 0.535, 0.525), mat=pm))
        objs.append(geo.rounded_box("dbg_kbd", (0.34, 0.15, 0.02), 0.004, center=B(0, 0.565, 0.375), mat=pm))
        for s in (1, -1):
            objs.append(geo.sphere(f"dbg_home_{'L' if s > 0 else 'R'}", 0.006, center=B(0.07 * s, 0.585, 0.37),
                                   segs=12, rings=8, mat=red))
    if DEBUG == "sink":
        objs.append(geo.rounded_box("dbg_counter", (1.2, 0.55, 0.50), 0.005, center=B(0, 0.25, 0.445), mat=pm))
        nrm, e1, e2 = plate_axes()
        ang = math.degrees(math.atan2(nrm.z, nrm.y))
        plate = geo.cylinder("dbg_plate", r=0.095, depth=0.012, center=B(*PLATE_CENTRE), segs=32,
                             rot=(ang, 0, 0), mat=mat.ceramic("debug_plate", "#f3eee4"))
        # bind the plate to grip_L in the wash pose (t = 0): store it in grip_L's rest frame
        Wp = pose_stand_wash(0.0).world()
        Qg, Pg = Wp["grip_L"]
        M = (Matrix.Translation(B(*J_REST["grip_L"])) @ _bl_rot(Qg.inverted()) @ Matrix.Translation(-B(*Pg)))
        plate.data.transform(M)
        r.bind_rigid(plate, "grip_L")
    return objs


def _bl_rot(q3):
    """three.js-axes quaternion -> Blender-axes 4x4 rotation."""
    C = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))     # three -> blender
    return (C @ q3.to_matrix() @ C.inverted()).to_4x4()


def tri_count():
    n = 0
    for o in bpy.data.objects:
        if o.type == "MESH":
            n += sum(len(p.vertices) - 2 for p in o.data.polygons)
    return n


# ---------------------------------------------------------------------------------------------
def build():
    info = {}
    m_skin = mat.vinyl("skin", COL["skin"])
    m_hood = mat.vinyl("hoodie", COL["hoodie"])
    m_dark = mat.vinyl("hoodie_dark", COL["hoodie_dark"])
    m_cord = mat.vinyl("drawstring", COL["drawstring"])
    m_pants = mat.vinyl("pants", COL["pants"])
    m_shoe = mat.vinyl("shoe", COL["shoe"])
    m_sole = mat.vinyl("sole", COL["sole"])
    m_wire = mat.metal("wire", COL["wire"])
    strands = mat.image_from_array("tim_hair_strands", tim_hair.normal_map(), colorspace="Non-Color")
    m_hair = mat.hair("main", "#ffffff", normal_image=strands)   # colour lives in the vertex colours

    # --- head group (rides on the "head" joint)
    head = build_head(m_skin)
    shell = geo.face_shell(head, center=B(*HC), half_size=0.42, mat=mat.decal("face"))
    ears = grids_to_object("tim_ears", [ear_grid("L"), ear_grid("R")], mats=[m_skin])
    hair = tim_hair.build(m_hair, COL["hair"])
    glasses = build_glasses(m_wire, info, surface_objs=(head, hair))

    # --- body
    hoodie = build_hoodie(m_hood, m_dark, m_cord)
    hood = build_hood(m_hood)
    pouch = build_hood_pouch(m_hood)
    sleeves = {s: build_sleeve(s, m_hood, m_dark) for s in "LR"}
    mittens = {s: grids_to_object(f"tim_mitten_{s}", mitten_grid(s), mats=[m_skin]) for s in "LR"}
    legs = {s: build_leg(s, m_pants) for s in "LR"}
    seat = build_seat(m_pants)
    shoes = {s: build_shoe(s, m_shoe, m_sole) for s in "LR"}

    # --- rig
    r = rigmod.Rig("tim_rig")
    for j in J_ORDER:
        r.bone(j, B(*J_REST[j]), J_PARENT[j])
    r.build()
    for o in (head, shell, ears, hair, glasses):
        r.bind_rigid(o, "head")
    r.bind_fn(hoodie, hoodie_weights)
    r.bind_rigid(hood, "torso")
    r.bind_rigid(pouch, "torso")
    for s in "LR":
        S, E, W = (B(*J_REST[f"{j}_{s}"]) for j in ("upperarm", "forearm", "hand"))
        r.bind_chain(sleeves[s], [(f"upperarm_{s}", S), (f"forearm_{s}", E), (f"forearm_{s}", W)], blend=0.045)
        r.bind_rigid(mittens[s], f"hand_{s}")
        Hh, K, A = (B(*J_REST[f"{j}_{s}"]) for j in ("thigh", "shin", "foot"))
        r.bind_chain(legs[s], [(f"thigh_{s}", Hh), (f"shin_{s}", K), (f"shin_{s}", A)], blend=0.05)
        r.bind_rigid(shoes[s], f"foot_{s}")
    r.bind_rigid(seat, "hips")
    if DEBUG:
        debug_props(r)

    # --- actions
    bake(r, "sit_type", TYPE_T, pose_sit_type, KEYS_SIT, LOCS_SIT)
    bake(r, "sit_idle", IDLE_T, pose_sit_idle, KEYS_SIT, LOCS_SIT)
    shock = make_pose_sit_shock()
    bake(r, "sit_shock", SHOCK_T, shock, KEYS_SIT, LOCS_SIT, loop=False)
    bake(r, "stand_idle", 2.4, pose_stand_idle, KEYS_STAND, LOCS_STAND)
    bake(r, "stand_wash", WASH_T, pose_stand_wash, KEYS_STAND, LOCS_STAND)
    bake(r, "stand_sink_idle", SINK_T, pose_stand_sink_idle, KEYS_STAND, LOCS_STAND)

    if DEBUG:
        for nm, T, fn in (("sit_type", TYPE_T, pose_sit_type), ("sit_idle", IDLE_T, pose_sit_idle),
                          ("sit_shock", SHOCK_T, shock), ("stand_wash", WASH_T, pose_stand_wash),
                          ("stand_sink_idle", SINK_T, pose_stand_sink_idle)):
            check_clearance(nm, T, fn)
        print("[tim] ik (reach ratio, wrist bend deg, overreach m):",
              {k: [round(x, 3) for x in v] for k, v in IK_LOG.items()})
        print("[tim] glasses:", info)
    print(f"[tim] triangles: {tri_count()}")

    wash0 = pose_stand_wash(0.0).world()
    return {
        "joints": J_ORDER,
        "actions": {"sit_type": TYPE_T, "sit_idle": IDLE_T, "sit_shock": SHOCK_T, "stand_idle": 2.4,
                    "stand_wash": WASH_T, "stand_sink_idle": SINK_T},
        "head_centre": [0.0, 1.08, 0.0],
        "seat": {"seat_top_y": 0.40, "hips_loc": [0.0, SIT_DY, 0.0], "hips_rx_deg": SIT_HIPS_RX},
        "grip_rest": {s: [round(v, 4) for v in J_REST[f"grip_{s}"]] for s in "LR"},
        "stand_wash_grip_L_t0": [round(v, 4) for v in wash0["grip_L"][1]],
        "keyboard_home_row": [list(HOME["L"]), list(HOME["R"])],
    }
