"""GuoGuo - Tim's king-penguin hand-puppet plush (the scene easter egg).

Build / rest pose = SEATED (pyramid silhouette, ~0.50 m tall; ~0.66 m if he stood up).
Root at the bottom centre on the surface he sits on (y = 0), facing +Z.

Construction (all positions below are three.js coordinates: x = his left, y = up, z = front)
- body_mesh       head + body are ONE continuous loft with NO neck.  The loft is traced from three
                  silhouette curves (front-view half width, side-view front line, side-view back line),
                  each parametrised by arc length, with superellipse rings in between.  The colours
                  are a base-colour texture on the loft UVs (u around with the seam at the back,
                  v up the meridian) painted from the 3D surface: black head down to the flipper-top
                  line all round, white front, grey back / sides, a yellow V bib that fades to cream
                  toward its tip, and comma / teardrop orange ear patches low on the head sides.  Every
                  border is soft and tufted (noise-jittered, narrow across / long down the pile); the
                  shell fur (src/actors/fur.js) blends it further by letting each strand pick its colour
                  up from a root a few mm away.
                  `_FURLEN` = 1.0 on the body (long pile), ~0.55 on the head (short but still plush),
                  lower under the eye beads / beak root.  Material fur_body (shells added in three.js).
- beak            long slender matte felt cone (fabric_), tilted 14 deg down, decurved, orange stripe on
                  the lower mandible.
- eye_L / eye_R   glossy glass beads (blue iris, big black pupil), flush on the head sides.
- eyewide_L / _R  white rings around the beads (the engine shows them only during 'startled').
- flipper_mesh_*  chunky stuffed pillow flippers (~5 cm thick at the root) stuck out sideways, white
                  front / grey back with a soft border, fur (`_FURLEN` 0.6).
- foot_mesh_*     stubby black felt feet (fabric_) poking forward from under the belly.
"""
import math

import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from lib import mat
from lib import rig as rigmod
from lib.core import B, new_mesh_object, shade_smooth

ITEM = {"id": "characters/guoguo", "out": "characters/guoguo.glb"}
FPS = 60

# ---- palette (brief) ------------------------------------------------------------------------
WHITE, GREY, BLACK = "#f3f2ee", "#9b9da0", "#1b1b1e"
BIB, ORANGE, IRIS, PUPIL = "#f4e638", "#f56a1c", "#2f78bd", "#0b0b0d"

# ---- silhouette (traced-photo style profile tables, metres) ---------------------------------
H = 0.50  # seated height (top of the head)
# (r, y): distance from the vertical axis vs height, bottom pole -> top pole
SIDE = [  # front view, half width (x)
    (0.000, 0.000), (0.088, 0.000), (0.142, 0.004), (0.174, 0.017), (0.192, 0.042), (0.199, 0.078),
    (0.196, 0.118), (0.188, 0.160), (0.176, 0.205), (0.162, 0.245), (0.148, 0.278), (0.1375, 0.306),
    (0.1305, 0.330), (0.1265, 0.352), (0.125, 0.375), (0.1207, 0.4074), (0.1083, 0.4375),
    (0.0884, 0.4634), (0.0625, 0.4833), (0.0324, 0.4957), (0.000, 0.500)]
FRONT = [  # side view, belly / face line (+z)
    (0.000, 0.000), (0.078, 0.000), (0.128, 0.005), (0.158, 0.021), (0.172, 0.048), (0.177, 0.080),
    (0.176, 0.110), (0.169, 0.155), (0.157, 0.200), (0.142, 0.243), (0.130, 0.276), (0.121, 0.305),
    (0.116, 0.330), (0.1135, 0.352), (0.113, 0.375), (0.1091, 0.4074), (0.0979, 0.4375),
    (0.0799, 0.4634), (0.0565, 0.4833), (0.0293, 0.4957), (0.000, 0.500)]
BACK = [  # side view, back line (-z, given as a positive distance)
    (0.000, 0.000), (0.070, 0.000), (0.118, 0.005), (0.145, 0.021), (0.157, 0.048), (0.161, 0.080),
    (0.159, 0.105), (0.152, 0.150), (0.142, 0.197), (0.131, 0.240), (0.121, 0.276), (0.114, 0.305),
    (0.1095, 0.330), (0.1075, 0.352), (0.107, 0.375), (0.1034, 0.4074), (0.0927, 0.4375),
    (0.0757, 0.4634), (0.0535, 0.4833), (0.0277, 0.4957), (0.000, 0.500)]

Y_LINE, Y_LINE_BACK_DROP = 0.336, 0.018   # black head down to the flipper-top line (lower at the nape)
BIB_TIP, BIB_K = 0.214, 1.24   # V bib: tip height on the chest, slope of the V sides (dy/d|x|)
BIB_MAX_PHI = 56.0        # bib does not wrap further round than this (deg from the front)
# comma / teardrop ear patch (his left side; mirrored): (phi deg from the front, y, radius m) along the
# stroke, from the round head (behind + below the eye) down and forward to a thin tail at the bib corner
EAR_PATH = [(83.0, 0.391, 0.038), (78.0, 0.373, 0.034), (71.0, 0.359, 0.025), (64.0, 0.351, 0.016),
            (58.0, 0.347, 0.0090), (52.0, 0.345, 0.0040)]
EYE_THETA, EYE_Y, EYE_R = 35.0, 0.396, 0.0165
BEAK_Y, BEAK_TILT, BEAK_LEN = 0.368, 14.0, 0.124
FLIP_ROOT = (0.120, 0.310, -0.004)
FOOT_POS, FOOT_JOINT = (0.068, 0.006, 0.150), (0.066, 0.012, 0.118)
HEAD_JOINT_Y = 0.335
SKIN_BAND = (0.300, 0.392)  # body -> head weight blend over this height band


# ---- small maths ------------------------------------------------------------------------------
def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def srgb(h):
    return np.array(mat.hex_srgb(h), np.float32)


def rotx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], float)


def roty(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], float)


def rotz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], float)


def to_b(p):
    """three.js point -> Blender tuple."""
    return (float(p[0]), float(-p[2]), float(p[1]))


def from_b(v):
    return np.array([v[0], v[2], -v[1]], float)


def tangent_frame(n):
    up = np.array([0.0, 1.0, 0.0])
    eb = up - n * np.dot(up, n)
    eb /= np.linalg.norm(eb)
    ea = np.cross(eb, n)
    return ea, eb


# ---- splines ----------------------------------------------------------------------------------
def _cr_seg(a, b, c, d, n, alpha=0.5):
    """Centripetal Catmull-Rom between b and c (n samples, c excluded)."""
    def nxt(t, p, q):
        return t + max(float(np.linalg.norm(q - p)), 1e-9) ** alpha
    t0 = 0.0
    t1 = nxt(t0, a, b)
    t2 = nxt(t1, b, c)
    t3 = nxt(t2, c, d)
    ts = np.linspace(t1, t2, n, endpoint=False)[:, None]
    a1 = (t1 - ts) / (t1 - t0) * a + (ts - t0) / (t1 - t0) * b
    a2 = (t2 - ts) / (t2 - t1) * b + (ts - t1) / (t2 - t1) * c
    a3 = (t3 - ts) / (t3 - t2) * c + (ts - t2) / (t3 - t2) * d
    b1 = (t2 - ts) / (t2 - t0) * a1 + (ts - t0) / (t2 - t0) * a2
    b2 = (t3 - ts) / (t3 - t1) * a2 + (ts - t1) / (t3 - t1) * a3
    return (t2 - ts) / (t2 - t1) * b1 + (ts - t1) / (t2 - t1) * b2


def open_profile(pts, n=48):
    """Dense profile through (r, y) points; the ends are mirrored across the axis so the curve
    leaves both poles perpendicular to the axis (smooth domes)."""
    P = np.asarray(pts, float)
    Q = np.vstack([P[1] * (-1.0, 1.0), P, P[-2] * (-1.0, 1.0)])
    out = [_cr_seg(Q[i - 1], Q[i], Q[i + 1], Q[i + 2], n) for i in range(1, len(Q) - 2)]
    out.append(P[-1:])
    return np.vstack(out)


def closed_outline(pts, n_out, per=40):
    """Closed centripetal Catmull-Rom through pts, resampled evenly by arc length (n_out points)."""
    P = np.asarray(pts, float)
    K = len(P)
    D = np.vstack([_cr_seg(P[(i - 1) % K], P[i], P[(i + 1) % K], P[(i + 2) % K], per) for i in range(K)])
    D = np.vstack([D, D[:1]])
    seg = np.linalg.norm(np.diff(D, axis=0), axis=1)
    S = np.concatenate([[0.0], np.cumsum(seg)])
    S /= S[-1]
    q = np.arange(n_out) / n_out
    return np.column_stack([np.interp(q, S, D[:, 0]), np.interp(q, S, D[:, 1])])


class Meridian:
    """A silhouette curve parametrised by normalised arc length s in [0, 1]."""

    def __init__(self, pts):
        D = open_profile(pts)
        D[:, 0] = np.maximum(D[:, 0], 0.0)
        D[:, 1] = np.maximum(D[:, 1], 0.0)
        seg = np.linalg.norm(np.diff(D, axis=0), axis=1)
        S = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(S[-1])
        self.S, self.R, self.Y = S / S[-1], D[:, 0], D[:, 1]

    def __call__(self, s):
        return np.interp(s, self.S, self.R), np.interp(s, self.S, self.Y)


class Body:
    """The one-piece loft.  theta: 0 = front (+z), +90 deg = his left (+x), +-180 = back.
    s: 0 = bottom pole ... 1 = top of the head."""

    def __init__(self):
        self.side, self.front, self.back = Meridian(SIDE), Meridian(FRONT), Meridian(BACK)

    @staticmethod
    def n_exp(y):
        return np.interp(y, [0.0, 0.12, 0.30, 0.50], [2.25, 2.2, 2.0, 2.0])

    def P(self, theta, s):
        rS, yS = self.side(s)
        rF, yF = self.front(s)
        rB, yB = self.back(s)
        c, sn = np.cos(theta), np.sin(theta)
        e = 2.0 / self.n_exp(yS)
        C = np.sign(c) * np.abs(c) ** e
        S = np.sign(sn) * np.abs(sn) ** e
        x = rS * S
        z = np.where(c >= 0, rF, rB) * C
        y = yS + np.where(c >= 0, yF - yS, yB - yS) * c * c
        return x, y, z

    def point(self, theta, s):
        x, y, z = self.P(np.float64(theta), np.float64(s))
        return np.array([float(x), float(y), float(z)])

    def frame(self, theta, s):
        p = self.point(theta, s)
        e = 1e-4
        pt = (self.point(theta + e, s) - self.point(theta - e, s)) / (2 * e)
        ps = (self.point(theta, s + e) - self.point(theta, s - e)) / (2 * e)
        n = np.cross(pt, ps)
        n /= np.linalg.norm(n)
        if np.dot(n, p - np.array([0.0, p[1] - 0.05, 0.0])) < 0:
            n = -n
        return p, n

    def at_height(self, theta, y):
        """Surface point (and outward normal) at parametric angle theta and height y (upper body)."""
        lo, hi = 0.2, 0.9999
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self.point(theta, mid)[1] < y:
                lo = mid
            else:
                hi = mid
        s = 0.5 * (lo + hi)
        p, n = self.frame(theta, s)
        return p, n, s


# ---- mesh building ----------------------------------------------------------------------------
def std_uv(V, N):
    UV = np.zeros((len(V), N + 1, 2))
    UV[..., 0] = (np.arange(N + 1) / N)[None, :]
    UV[..., 1] = np.asarray(V, float)[:, None]
    mid = (np.arange(N) + 0.5) / N
    return UV, np.column_stack([mid, np.zeros(N)]), np.column_stack([mid, np.ones(N)])


def grid_object(name, P, UV, pole0=None, pole1=None, uv0=None, uv1=None, material=None, facing=None):
    """Quad grid of rings P (M, N, 3) (three.js coords, closed around) with per-corner UVs
    UV (M, N+1, 2) (column N = seam copy of column 0) and optional pole fans."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    M, N = P.shape[:2]
    vs = [[bm.verts.new(to_b(P[j, i])) for i in range(N)] for j in range(M)]
    for j in range(M - 1):
        for i in range(N):
            k = (i + 1) % N
            f = bm.faces.new((vs[j][i], vs[j][k], vs[j + 1][k], vs[j + 1][i]))
            for lp, uv in zip(f.loops, (UV[j, i], UV[j, i + 1], UV[j + 1, i + 1], UV[j + 1, i])):
                lp[uvl].uv = (float(uv[0]), float(uv[1]))
    if pole0 is not None:
        c = bm.verts.new(to_b(pole0))
        for i in range(N):
            f = bm.faces.new((c, vs[0][(i + 1) % N], vs[0][i]))
            for lp, uv in zip(f.loops, (uv0[i], UV[0, i + 1], UV[0, i])):
                lp[uvl].uv = (float(uv[0]), float(uv[1]))
    if pole1 is not None:
        c = bm.verts.new(to_b(pole1))
        for i in range(N):
            f = bm.faces.new((vs[-1][i], vs[-1][(i + 1) % N], c))
            for lp, uv in zip(f.loops, (UV[-1, i], UV[-1, i + 1], uv1[i])):
                lp[uvl].uv = (float(uv[0]), float(uv[1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if facing is not None:  # open surfaces: make the faces point along `facing` (three.js dir)
        fb = Vector(to_b(facing))
        bm.normal_update()
        avg = sum((f.normal for f in bm.faces), Vector())
        if avg.dot(fb) < 0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
    obj = new_mesh_object(name, bm=bm)
    if material is not None:
        obj.data.materials.append(material)
    shade_smooth(obj)
    return obj


def pillow(outline, center, h_pos, h_neg, n_rings=15, p=0.55, thick=None, bend=None):
    """Inflate a closed 2D outline (N, 2) in local (a, b) into a soft pillow along local c.
    Ring k sits at angle w in (-90, 90) deg: outline scaled by cos(w)^p toward `center`,
    c = h * sin(w).  The rim (w = 0) is a ring (v = 0.5).  Returns P (M, N, 3), poles, V."""
    C = np.asarray(center, float)
    ws = np.linspace(-np.pi / 2, np.pi / 2, n_rings + 2)[1:-1]
    rings = []
    for w in ws:
        ab = C + (outline - C) * (math.cos(w) ** p)
        c = np.full(len(outline), (h_pos if w > 0 else h_neg) * math.sin(w))
        if thick is not None:
            c = c * thick(ab)
        if bend is not None:
            c = c + bend(ab)
        rings.append(np.column_stack([ab, c]))
    P = np.array(rings)
    tc = float(thick(C[None])[0]) if thick is not None else 1.0
    bc = float(bend(C[None])[0]) if bend is not None else 0.0
    pole_neg = np.array([C[0], C[1], -h_neg * tc + bc])
    pole_pos = np.array([C[0], C[1], h_pos * tc + bc])
    V = (ws + np.pi / 2) / np.pi
    return P, pole_neg, pole_pos, V


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ---- textures ---------------------------------------------------------------------------------
_LATTICE = {}


def vnoise3(x, y, z, freq, seed):
    """Smooth value noise in [-1, 1] on a seeded periodic 64^3 lattice; freq = (fx, fy, fz) per metre."""
    if seed not in _LATTICE:
        _LATTICE[seed] = np.random.default_rng(seed).random((64, 64, 64)) * 2.0 - 1.0
    G = _LATTICE[seed]
    q = [np.asarray(c, float) * f + 7.3 for c, f in zip((x, y, z), freq)]
    i = [np.floor(c).astype(np.int64) for c in q]
    f = [c - ic for c, ic in zip(q, i)]
    f = [t * t * (3.0 - 2.0 * t) for t in f]
    out = 0.0
    for dx in (0, 1):
        wx = f[0] if dx else 1.0 - f[0]
        for dy in (0, 1):
            wy = f[1] if dy else 1.0 - f[1]
            for dz in (0, 1):
                wz = f[2] if dz else 1.0 - f[2]
                out = out + wx * wy * wz * G[(i[0] + dx) % 64, (i[1] + dy) % 64, (i[2] + dz) % 64]
    return out


def tufts(x, y, z, seed):
    """Fur-tuft border jitter (metres): narrow across (~5 mm), long down the pile (~16 mm)."""
    return (0.0032 * vnoise3(x, y, z, (190.0, 60.0, 190.0), seed)
            + 0.0016 * vnoise3(x, y, z, (420.0, 130.0, 420.0), seed + 1))


def ear_patch_sdf(x, y, z):
    """Signed distance (m, < 0 inside) to the comma-shaped ear patches on both head sides."""
    phi = np.degrees(np.abs(np.arctan2(x, z)))
    rh = np.sqrt(x * x + z * z) + 1e-6
    P = np.array(EAR_PATH, float)
    # dense stroke: centripetal Catmull-Rom through (phi, y, r) with mirrored end points
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    pts = np.vstack([_cr_seg(Q[i - 1], Q[i], Q[i + 1], Q[i + 2], 10) for i in range(1, len(Q) - 2)] + [P[-1:]])
    d = np.full(x.shape, 1.0)
    for ph_c, y_c, r_c in pts:
        dd = np.sqrt((np.radians(phi - ph_c) * rh) ** 2 + (y - y_c) ** 2) - r_c
        d = np.minimum(d, dd)
    return d


def body_colors(x, y, z):
    phi = np.arctan2(x, z)  # 0 = front, + = his left
    aphi = np.abs(phi)
    rh = np.sqrt(x * x + z * z) + 1e-6
    E = 0.0045  # half width of the soft edge, metres (the shell fur dissolves it further)
    jt = tufts(x, y, z, 11)  # tufted borders: a pile edge, not a cut line
    jt2 = tufts(x, y, z, 23)

    # white front / grey back + sides
    phw = np.radians(np.interp(y, [0.0, 0.10, 0.20, 0.32], [74.0, 71.0, 66.0, 60.0]))
    w_white = smoothstep(-E, E, (phw - aphi) * rh + jt2)
    # black head down to the flipper-top line, all round (a touch higher at the back); black tufts hang
    # down over the white (the pile lies downward)
    y_line = Y_LINE - Y_LINE_BACK_DROP * (1.0 - np.cos(phi)) * 0.5
    w_black = smoothstep(-E, E, y - y_line + jt - 0.0015)
    # yellow V bib on the throat: bright under the head, fading to pale cream toward the V tip
    d_v = (y - (BIB_TIP + BIB_K * np.abs(x))) / math.sqrt(1.0 + BIB_K ** 2)
    tb = np.clip((y - BIB_TIP) / (Y_LINE - BIB_TIP), 0.0, 1.0)  # 0 = tip, 1 = top
    w_bib = (smoothstep(-1.4 * E, 1.4 * E, d_v + 0.8 * jt2) * smoothstep(0.0, 0.03, z)
             * smoothstep(-2 * E, 2 * E, (math.radians(BIB_MAX_PHI) - aphi) * rh + jt2))
    w_bib = w_bib * (0.22 + 0.78 * smoothstep(0.02, 0.80, tb) ** 0.85)
    warm = 0.16 * smoothstep(0.78, 1.0, tb)  # a warmer, orange-ish yellow right under the head
    # comma-shaped orange ear patches (fur-blended edge)
    d_ear = ear_patch_sdf(x, y, z) + 0.7 * jt
    w_ear = smoothstep(E, -E, d_ear)
    ear_tail = smoothstep(0.375, 0.345, y)  # the tail runs a little lighter

    col = np.broadcast_to(srgb(GREY), x.shape + (3,)).astype(np.float32)

    def mix(col, c, w):
        w = np.asarray(w)[..., None]
        c = srgb(c) if isinstance(c, str) else np.asarray(c, np.float32)
        if c.ndim == 1:
            c = c[None, None, :]
        return col * (1.0 - w) + c * w

    bib_c = srgb(BIB)[None, None, :] * (1.0 - warm[..., None]) + srgb(ORANGE)[None, None, :] * warm[..., None]
    ear_c = (srgb(ORANGE)[None, None, :] * (1.0 - 0.28 * ear_tail[..., None])
             + srgb(BIB)[None, None, :] * (0.28 * ear_tail[..., None]))
    col = mix(col, WHITE, w_white)
    col = mix(col, bib_c, w_bib)
    col = mix(col, BLACK, w_black)
    col = mix(col, ear_c, w_ear)
    # a faint low-frequency clumping in the pile (plush, not paint)
    clump = 1.0 + 0.035 * vnoise3(x, y, z, (55.0, 35.0, 55.0), 5)
    col = col * clump[..., None]
    return np.clip(col, 0.0, 1.0)


def body_texture(body, W=1024, Hh=1024):
    u = (np.arange(W) + 0.5) / W
    v = 1.0 - (np.arange(Hh) + 0.5) / Hh  # row 0 = top of the image = v ~ 1
    UU, VV = np.meshgrid(u, v)
    x, y, z = body.P(2 * np.pi * UU - np.pi, VV)
    return body_colors(x, y, z)


def flipper_texture(n=128):
    """v > 0.5 (front pillow half) white, v < 0.5 (back half) grey."""
    v = 1.0 - (np.arange(n) + 0.5) / n
    u = (np.arange(n) + 0.5) / n
    UU, VV = np.meshgrid(u, v)
    jit = 0.03 * vnoise3(UU, VV, np.zeros_like(UU), (64.0, 12.0, 1.0), 31)
    w = smoothstep(0.455, 0.545, VV + jit)[..., None]
    img = srgb(GREY)[None, None, :] * (1 - w) + srgb(WHITE)[None, None, :] * w
    return img.astype(np.float32)


def beak_texture(n=256, q_out=None):
    """u = angle round the beak (0 = his left side, 0.25 = top, 0.5 = right, 0.75 = bottom),
    v = station (0 = buried root, 1 = tip).  Orange stripe on each side of the lower mandible."""
    u = (np.arange(n) + 0.5) / n
    v = 1.0 - (np.arange(n) + 0.5) / n
    UU, VV = np.meshgrid(u, v)
    phi = UU * 360.0
    q = q_out(VV)  # exposed fraction along the beak
    img = np.broadcast_to(srgb(BLACK), UU.shape + (3,)).astype(np.float32).copy()
    w = np.zeros_like(UU)
    hw = 19.0 * (1.0 - smoothstep(0.30, 0.74, q)) * smoothstep(0.02, 0.10, q) + 1e-3
    for c in (322.0, 218.0):  # lower-left and lower-right side of the lower mandible
        d = np.abs((phi - c + 180.0) % 360.0 - 180.0)
        w = np.maximum(w, smoothstep(-2.0, 2.0, hw - d))
    w = w * smoothstep(0.0, 0.03, q)
    img = img * (1 - w[..., None]) + srgb(ORANGE)[None, None, :] * w[..., None]
    return img


def eye_texture(n=128, pupil_r=0.60):
    yy, xx = (np.mgrid[0:n, 0:n] + 0.5) / n * 2.0 - 1.0
    r = np.sqrt(xx * xx + yy * yy)
    ang = np.arctan2(yy, xx)
    iris = srgb(IRIS)[None, None, :]
    # glass-bead depth: a touch lighter near the pupil, darker toward the rim, faint radial fibres
    shade = 1.12 - 0.30 * smoothstep(pupil_r, 1.0, r)
    fib = 1.0 + 0.05 * np.cos(ang * 23.0) * smoothstep(pupil_r, pupil_r + 0.15, r)
    img = np.clip(iris * (shade * fib)[..., None], 0, 1)
    wp = smoothstep(pupil_r + 0.025, pupil_r - 0.025, r)[..., None]
    img = img * (1 - wp) + srgb(PUPIL)[None, None, :] * wp
    return img


# ---- parts ------------------------------------------------------------------------------------
def build_body(body, material, N=96, M=78):
    S = np.arange(1, M + 1) / (M + 1)
    th = 2 * np.pi * (np.arange(N) / N) - np.pi
    TH, SS = np.meshgrid(th, S)
    x, y, z = body.P(TH, SS)
    P = np.stack([x, y, z], axis=-1)
    UV, uv0, uv1 = std_uv(S, N)
    return grid_object("body_mesh", P, UV, pole0=(0.0, 0.0, 0.0), pole1=(0.0, H, 0.0), uv0=uv0, uv1=uv1,
                       material=material)


def build_beak(body, material):
    p0, _, _ = body.at_height(0.0, BEAK_Y)
    tilt = math.radians(BEAK_TILT)
    d = np.array([0.0, -math.sin(tilt), math.cos(tilt)])
    dn = np.array([0.0, -math.cos(tilt), -math.sin(tilt)])  # 'down', perpendicular to d
    L_in, L_out = 0.022, BEAK_LEN
    total = L_in + L_out
    # stations (denser toward the tip)
    g = np.linspace(0.0, 1.0, 48)
    ts = 1.0 - (1.0 - g) ** 1.35
    q = (ts * total - L_in) / L_out  # exposed fraction (negative = buried)
    qc = np.clip(q, 0.0, 1.0)
    # decurved: the tip droops a little below the 14 deg line (reads long from the front too)
    centers = p0[None, :] + d[None, :] * (ts * total - L_in)[:, None] + dn[None, :] * (0.017 * qc ** 2.2)[:, None]
    taper = 1.0 - 0.84 * qc ** 1.12
    q_r = 0.93
    tipround = np.sqrt(np.clip(1.0 - ((qc - q_r) / (1.0 - q_r)) ** 2, 0.0, 1.0))
    tipround[qc <= q_r] = 1.0
    hh = 0.0228 * taper * tipround
    hw = 0.0172 * taper * tipround
    # drop the degenerate tip ring (the tip pole closes the tube)
    keep = hh > 1e-5
    centers, hh, hw, ts_k, q_k = centers[keep], hh[keep], hw[keep], ts[keep], q[keep]
    N = 36
    phis = 2 * np.pi * np.arange(N) / N
    n_e = 2.2
    cph, sph = np.cos(phis), np.sin(phis)
    Cx = np.sign(cph) * np.abs(cph) ** (2 / n_e)
    Sy = np.sign(sph) * np.abs(sph) ** (2 / n_e)
    rings = []
    X = np.array([1.0, 0.0, 0.0])
    for j in range(len(centers)):
        a = centers[max(j - 1, 0)]
        b = centers[min(j + 1, len(centers) - 1)]
        T = (b - a) / np.linalg.norm(b - a)
        U = np.cross(T, X)
        U /= np.linalg.norm(U)
        rings.append(centers[j][None, :] + X[None, :] * (hw[j] * Cx)[:, None] + U[None, :] * (hh[j] * Sy)[:, None])
    P = np.array(rings)
    tip = centers[-1] + (centers[-1] - centers[-2]) / np.linalg.norm(centers[-1] - centers[-2]) * 0.0012
    start = centers[0] - d * 0.002
    UV, uv0, uv1 = std_uv(ts_k, N)
    obj = grid_object("beak", P, UV, pole0=start, pole1=tip, uv0=uv0, uv1=uv1, material=material)
    q_of_v = lambda v: (np.asarray(v) * total - L_in) / L_out  # noqa: E731
    return obj, q_of_v, p0


def build_eye(name, E, n, material, R=EYE_R, apex=0.0088, embed=0.0030, N=40, K=12):
    """Glass bead: spherical cap on the head surface, axis = surface normal; planar UVs."""
    ea, eb = tangent_frame(n)
    Hc = apex + embed
    rho = (R * R + Hc * Hc) / (2 * Hc)
    zc = apex - rho
    bmax = math.asin(min(1.0, R / rho)) if Hc < rho else math.pi - math.asin(R / rho)
    betas = np.linspace(0.0, bmax, K + 1)[1:]
    phis = 2 * np.pi * np.arange(N) / N
    rings = []
    for bta in betas:
        r = rho * math.sin(bta)
        h = zc + rho * math.cos(bta)
        rings.append(E[None, :] + (np.outer(np.cos(phis), ea) + np.outer(np.sin(phis), eb)) * r + n[None, :] * h)
    # skirt down into the head so no gap shows at grazing angles
    last = rings[-1]
    rings.append(last - n[None, :] * 0.003)
    P = np.array(rings)

    def planar(pts):
        rel = pts - E
        return np.stack([0.5 + rel @ ea / (2 * R), 0.5 + rel @ eb / (2 * R)], axis=-1)

    M = len(rings)
    UV = np.zeros((M, N + 1, 2))
    UV[:, :N] = planar(P)
    UV[:, N] = UV[:, 0]
    apex_pt = E + n * apex
    base_pt = E - n * (embed + 0.003)
    uv_a = np.repeat(planar(apex_pt[None])[0][None], N, axis=0)
    uv_b = np.repeat(planar(base_pt[None])[0][None], N, axis=0)
    # rings run apex -> base, so pole0 = apex, pole1 = base
    return grid_object(name, P, UV, pole0=apex_pt, pole1=base_pt, uv0=uv_a, uv1=uv_b, material=material)


def build_eyewide(name, E, n, bvh, material, r_in=0.0095, r_out=0.0255, N=48):
    """White 'wide eye' ring around the bead, following the head surface just above it."""
    ea, eb = tangent_frame(n)
    radii = np.array([r_in, 0.0125, 0.015, 0.0175, 0.020, 0.022, 0.024, r_out, r_out + 0.0012])
    lift = np.array([0.0033, 0.0033, 0.0032, 0.0030, 0.0027, 0.0024, 0.0020, 0.0013, -0.0010])
    phis = 2 * np.pi * np.arange(N) / N
    rings = []
    for r, lf in zip(radii, lift):
        ring = []
        for ph in phis:
            q = E + (ea * math.cos(ph) + eb * math.sin(ph)) * r
            hit = bvh.ray_cast(Vector(to_b(q + n * 0.03)), Vector(to_b(-n)))
            base = from_b(hit[0]) if hit[0] is not None else q
            ring.append(base + n * lf)
        rings.append(ring)
    P = np.array(rings)
    UV, _, _ = std_uv(np.linspace(0, 1, len(radii)), N)
    return grid_object(name, P, UV, material=material, facing=n)


FLIP_L = 0.196
FLIP_OUTLINE = [  # local (a = chord across, b = along; b = 0 at the joint, tip at -FLIP_L)
    (0.030, 0.022), (0.0, 0.032), (-0.030, 0.022),
    (-0.038, 0.0), (-0.042, -0.044), (-0.040, -0.094), (-0.033, -0.138), (-0.021, -0.174),
    (0.0, -FLIP_L),
    (0.022, -0.176), (0.035, -0.138), (0.041, -0.092), (0.042, -0.044), (0.038, 0.0)]


def flipper_points(abduct=40.0, twist=12.0, sweep=14.0):
    """Chunky plush flipper: a stuffed pillow, ~5 cm thick at the root, rounded edge, softer tip."""
    out = closed_outline(FLIP_OUTLINE, 48)
    thick = lambda ab: np.interp(-ab[:, 1] / FLIP_L, [0.0, 0.5, 1.0], [1.0, 0.86, 0.55])  # noqa: E731
    bend = lambda ab: 0.012 * np.clip(-ab[:, 1] / FLIP_L, 0.0, 1.0) ** 2  # noqa: E731
    P, pn, pp, V = pillow(out, (0.0, -0.064), 0.0235, 0.0235, n_rings=17, p=0.42, thick=thick, bend=bend)
    Rm = rotz(math.radians(abduct)) @ rotx(math.radians(-sweep)) @ roty(math.radians(twist))
    root = np.array(FLIP_ROOT)
    xf = lambda pts: pts @ Rm.T + root  # noqa: E731
    return xf(P), xf(pn[None])[0], xf(pp[None])[0], V


FOOT_OUTLINE = [  # local (a = x across, b = z along; heel -, toes +), 3 soft toes
    (0.0, -0.040), (0.017, -0.035), (0.025, -0.014), (0.030, 0.012), (0.031, 0.031),
    (0.027, 0.046), (0.019, 0.051), (0.012, 0.045), (0.006, 0.055), (-0.006, 0.055),
    (-0.012, 0.045), (-0.019, 0.051), (-0.027, 0.046), (-0.031, 0.031), (-0.030, 0.012),
    (-0.025, -0.014), (-0.017, -0.035)]


def foot_points(yaw=14.0, pitch=9.0):
    out = closed_outline(FOOT_OUTLINE, 40)
    P, pn, pp, V = pillow(out, (0.0, 0.0), 0.021, 0.005, n_rings=11, p=0.6)
    # local (a, b, c) -> three (x = a, y = c, z = b)
    sw = lambda pts: pts[..., [0, 2, 1]]  # noqa: E731
    Rm = roty(math.radians(yaw)) @ rotx(math.radians(-pitch))
    pos = np.array(FOOT_POS)
    xf = lambda pts: sw(pts) @ Rm.T + pos  # noqa: E731
    return xf(P), xf(pn[None])[0], xf(pp[None])[0], V


def mirror_x(*arrs):
    return [a * np.array([-1.0, 1.0, 1.0]) for a in arrs]


# ---- animation helpers ------------------------------------------------------------------------
EASE = {
    "lin": lambda x: x,
    "in": lambda x: x * x,
    "out": lambda x: 1 - (1 - x) ** 2,
    "in3": lambda x: x ** 3,
    "out3": lambda x: 1 - (1 - x) ** 3,
    "io": lambda x: x * x * (3 - 2 * x),
    "hold": lambda x: 0.0,
}


class Tr:
    """Keyed scalar track.  keys: (t, v[, ease]) - ease applies to the segment after the key.
    'auto' segments are cubic Hermite with Blender-like auto-clamped slopes (flat at extremes,
    no overshoot); `period` makes slopes wrap for seamless loops."""

    def __init__(self, keys, period=None):
        self.t = np.array([k[0] for k in keys], float)
        self.v = np.array([k[1] for k in keys], float)
        self.e = [k[2] if len(k) > 2 else "auto" for k in keys]
        self.period = period
        n = len(keys)
        self.m = np.zeros(n)
        for i in range(n):
            if 0 < i < n - 1:
                tp, vp, tn, vn = self.t[i - 1], self.v[i - 1], self.t[i + 1], self.v[i + 1]
            elif period and n > 2:
                tp, vp = self.t[-2] - (period if i == 0 else 0.0), self.v[-2]
                tn, vn = self.t[1] + (0.0 if i == 0 else period), self.v[1]
            else:
                continue
            d0 = (self.v[i] - vp) / (self.t[i] - tp)
            d1 = (vn - self.v[i]) / (tn - self.t[i])
            if d0 * d1 <= 0:
                continue
            mm = (vn - vp) / (tn - tp)
            self.m[i] = math.copysign(min(abs(mm), 3 * min(abs(d0), abs(d1))), mm)

    def __call__(self, t):
        T = self.t
        if self.period:
            t = T[0] + (t - T[0]) % self.period
        if t <= T[0]:
            return float(self.v[0])
        if t >= T[-1]:
            return float(self.v[-1])
        i = int(np.searchsorted(T, t, side="right") - 1)
        t0, t1, v0, v1 = T[i], T[i + 1], self.v[i], self.v[i + 1]
        h = t1 - t0
        x = (t - t0) / h
        if self.e[i] == "auto":
            m0, m1 = self.m[i] * h, self.m[i + 1] * h
            x2, x3 = x * x, x * x * x
            return float((2 * x3 - 3 * x2 + 1) * v0 + (x3 - 2 * x2 + x) * m0 + (-2 * x3 + 3 * x2) * v1 + (x3 - x2) * m1)
        return float(v0 + (v1 - v0) * EASE[self.e[i]](x))


def window(t, t0, t1, t2, t3):
    """0 before t0, ramps to 1 by t1, holds, ramps back to 0 between t2 and t3."""
    return float(smoothstep(t0, t1, t) * (1.0 - smoothstep(t2, t3, t)))


def bake(r, name, dur, fn):
    """Sample fn(t) -> (rot, loc, scale) dicts at every frame (60 fps) into an action."""
    a = r.action(name)
    nf = int(round(dur * FPS))
    for f in range(nf + 1):
        t = f / FPS
        rot, loc, sca = fn(t)
        a.key(t, rot=rot, loc=loc, scale=sca, interp='LINEAR')
    a.done()


# ---- actions ----------------------------------------------------------------------------------
def make_actions(r):
    # seated_idle (loop, 3.0 s): head wander, breathing bob, flipper paddle (L/R offset)
    T = 3.0
    br = Tr([(0, 0.983), (0.62, 1.020), (1.5, 0.983), (2.12, 1.020), (3.0, 0.983)], period=T)
    sway = Tr([(0, 0.0), (0.9, 0.7), (1.6, 0.45), (2.3, -0.6), (3.0, 0.0)], period=T)
    hx = Tr([(0, 0.0), (0.55, -3.0), (1.25, -2.2), (1.85, 2.2), (2.45, 1.6), (3.0, 0.0)], period=T)
    hy = Tr([(0, 0.0), (0.55, 8.0), (1.25, 9.5), (1.85, -6.0), (2.45, -7.0), (3.0, 0.0)], period=T)
    hz = Tr([(0, 0.0), (0.6, -2.5), (1.25, -1.8), (1.9, 2.4), (2.45, 1.7), (3.0, 0.0)], period=T)
    fz = Tr([(0, 0.0), (0.4, 5.0), (1.0, -2.0), (1.5, 0.5), (1.9, 4.5), (2.5, -2.5), (3.0, 0.0)], period=T)
    fx = Tr([(0, 0.0), (0.5, -6.0), (1.1, 3.0), (1.55, 0.0), (2.0, -5.0), (2.6, 3.5), (3.0, 0.0)], period=T)

    def idle(t):
        sy = br(t)
        sxz = 1.0 + (sy - 1.0) * 0.3
        tr = t - 0.27  # right flipper lags the left (overlap)
        rot = {
            "body": (0.0, 0.0, sway(t)),
            "head": (hx(t), hy(t), hz(t)),
            "flipper_L": (fx(t), 0.0, fz(t)),
            "flipper_R": (fx(tr) * 0.9, 0.0, -fz(tr) * 1.1),
        }
        return rot, {}, {"body": (sxz, sy, sxz)}

    bake(r, "seated_idle", T, idle)

    # startled (1.6 s): hop, HARD flap, squash on landing, jelly settle + shiver, back to rest
    T = 1.6
    hop = Tr([(0, 0.0, "out"), (0.12, 0.080, "in"), (0.25, 0.0, "out"), (0.335, 0.009, "in"), (0.42, 0.0),
              (T, 0.0)])
    sy_pre = Tr([(0, 1.0, "out"), (0.05, 1.10), (0.12, 1.0), (0.215, 1.05), (0.25, 1.03, "out"), (0.265, 0.82)])
    lean = Tr([(0, 0.0, "out"), (0.10, -5.0), (0.20, -3.0), (0.28, 3.5), (0.40, -1.5), (0.52, 0.8), (0.66, 0.0),
               (T, 0.0)])
    hpx = Tr([(0, 0.0, "out"), (0.09, -12.0), (0.19, -4.0), (0.29, 9.0), (0.40, -6.0), (0.52, 2.5), (0.66, -3.5),
              (0.92, -3.0), (T, 0.0)])
    flz = Tr([(0, 0.0, "out"), (0.04, 55.0), (0.085, -8.0), (0.13, 58.0), (0.175, -6.0), (0.215, 48.0),
              (0.26, -16.0), (0.34, 16.0), (0.43, -6.0), (0.53, 5.0), (0.64, -2.0), (0.78, 0.0), (T, 0.0)])
    flx = Tr([(0, 0.0, "out"), (0.04, -10.0), (0.085, 6.0), (0.13, -12.0), (0.175, 6.0), (0.215, -9.0),
              (0.26, 8.0), (0.34, -4.0), (0.45, 1.5), (0.60, 0.0), (T, 0.0)])
    ftx = Tr([(0, 0.0, "out"), (0.08, -26.0), (0.19, -12.0), (0.26, 9.0), (0.36, -4.0), (0.48, 1.5), (0.62, 0.0),
              (T, 0.0)])

    def body_sy(t):
        if t < 0.265:
            return sy_pre(t)
        k = t - 0.265
        fade = 1.0 - smoothstep(1.15, 1.55, t)
        return 1.0 - 0.18 * math.exp(-4.3 * k) * math.cos(2 * math.pi * k / 0.235) * fade

    def shiver(t, amp, f, t0, t1, ph=0.0):
        w = window(t, t0, t0 + 0.08, t0 + 0.25, t1)
        return amp * w * math.sin(2 * math.pi * f * (t - t0) + 0.9 * math.sin(7.0 * t) + ph)

    def startled(t):
        sy = body_sy(t)
        sxz = sy ** -0.575  # 0.82 -> 1.12 (volume-ish preserving)
        tr = t - 0.012
        rot = {
            "body": (lean(t), shiver(t, 0.6, 9.0, 0.55, 1.45, 1.0), shiver(t, 1.4, 11.0, 0.5, 1.45)),
            "head": (hpx(t), shiver(t, 1.6, 8.5, 0.6, 1.45, 2.0), 0.0),
            "flipper_L": (flx(t), 0.0, flz(t) + shiver(t, 2.5, 12.0, 0.72, 1.4)),
            "flipper_R": (flx(tr), 0.0, -flz(tr) - shiver(t, 2.5, 12.0, 0.72, 1.4, 1.5)),
            "foot_L": (ftx(t), 0.0, 0.0),
            "foot_R": (ftx(t - 0.015), 0.0, 0.0),
        }
        return rot, {"root": (0.0, hop(t), 0.0)}, {"body": (sxz, sy, sxz)}

    bake(r, "startled", T, startled)

    # flinch (0.6 s): quick small recoil - body leans back, head pulls in/down, flippers in
    T = 0.6
    blx = Tr([(0, 0.0, "out3"), (0.07, -9.0), (0.20, -7.5), (0.38, 1.4), (0.50, -0.3), (T, 0.0)])
    bsy = Tr([(0, 1.0, "out3"), (0.06, 0.955), (0.20, 0.965), (0.36, 1.012), (0.48, 0.997), (T, 1.0)])
    hfx = Tr([(0, 0.0, "out3"), (0.065, 8.0), (0.20, 6.5), (0.40, -1.8), (0.52, 0.4), (T, 0.0)])
    hfy = Tr([(0, 0.0, "out3"), (0.065, -0.012), (0.22, -0.010), (0.42, 0.0015), (T, 0.0)])
    ffx = Tr([(0, 0.0, "out3"), (0.06, -14.0), (0.22, -11.0), (0.42, 3.0), (T, 0.0)])
    ffz = Tr([(0, 0.0, "out3"), (0.06, -24.0), (0.22, -20.0), (0.42, 4.0), (T, 0.0)])

    def flinch(t):
        sy = bsy(t)
        sxz = sy ** -0.5
        tf = t - 0.01
        rot = {
            "body": (blx(t), 0.0, 0.0),
            "head": (hfx(t), 0.0, 0.0),
            "flipper_L": (ffx(tf), 0.0, ffz(tf)),
            "flipper_R": (ffx(tf - 0.008), 0.0, -ffz(tf - 0.008)),
        }
        return rot, {"head": (0.0, hfy(t), 0.0)}, {"body": (sxz, sy, sxz)}

    bake(r, "flinch", T, flinch)

    # look_off (loop, 2.0 s): head turned ~35 deg to his left and slightly up, small wander
    T = 2.0
    lx = Tr([(0, -8.0), (0.7, -10.0), (1.35, -6.5), (2.0, -8.0)], period=T)
    ly = Tr([(0, 35.0), (0.7, 37.5), (1.35, 33.0), (2.0, 35.0)], period=T)
    lz = Tr([(0, -3.0), (0.7, -4.5), (1.35, -1.5), (2.0, -3.0)], period=T)

    def look_off(t):
        return {"head": (lx(t), ly(t), lz(t))}, {}, {}

    bake(r, "look_off", T, look_off)
    return {"seated_idle": 3.0, "startled": 1.6, "flinch": 0.6, "look_off": 2.0}


# ---- build ------------------------------------------------------------------------------------
def build():
    body = Body()
    s3 = lambda th, y: body.at_height(math.radians(th), y)  # noqa: E731

    # feature anchors on the loft
    eyes = [s3(sg * EYE_THETA, EYE_Y)[:2] for sg in (1, -1)]  # (point, normal) L, R

    # materials
    m_body = mat.fur("body", image=mat.image_from_array("guoguo_body_col", body_texture(body)))
    m_flip = mat.fur("flipper", image=mat.image_from_array("guoguo_flipper_col", flipper_texture()))
    m_eye = mat.material("ink_eye", "#ffffff", roughness=0.3, coat=0.5, coat_roughness=0.1,
                         image=mat.image_from_array("guoguo_eye_col", eye_texture()))
    m_wide = mat.vinyl("eyewide", "#fbfaf6")
    m_foot = mat.fabric("foot", BLACK, double_sided=False)  # felt, matte

    # body + head loft
    body_obj = build_body(body, m_body)
    me = body_obj.data
    bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])

    # beak (textured stripe)
    beak_obj, q_of_v, beak_root = build_beak(body, None)
    m_beak = mat.fabric("beak", "#ffffff", double_sided=False, image=mat.image_from_array("guoguo_beak_col", beak_texture(q_out=q_of_v)))
    beak_obj.data.materials.append(m_beak)

    # eyes + wide-eye rings (GUOGUO_NO_WIDE=1 skips the rings: preview of the neutral face only)
    import os
    no_wide = os.environ.get("GUOGUO_NO_WIDE") == "1"
    eye_objs, wide_objs = [], []
    for (p, n), sfx in zip(eyes, ("L", "R")):
        eye_objs.append(build_eye(f"eye_{sfx}", p, n, m_eye))
        if not no_wide:
            wide_objs.append(build_eyewide(f"eyewide_{sfx}", p, n, bvh, m_wide))

    # flippers (pillow paddles, two-tone texture)
    fP, fpn, fpp, fV = flipper_points()
    UV, uv0, uv1 = std_uv(fV, fP.shape[1])
    flip_L = grid_object("flipper_mesh_L", fP, UV, fpn, fpp, uv0, uv1, material=m_flip)
    fPr, fpnr, fppr = mirror_x(fP, fpn, fpp)
    flip_R = grid_object("flipper_mesh_R", fPr, UV, fpnr, fppr, uv0, uv1, material=m_flip)

    # feet
    tP, tpn, tpp, tV = foot_points()
    UVf, u0f, u1f = std_uv(tV, tP.shape[1])
    foot_L = grid_object("foot_mesh_L", tP, UVf, tpn, tpp, u0f, u1f, material=m_foot)
    tPr, tpnr, tppr = mirror_x(tP, tpn, tpp)
    foot_R = grid_object("foot_mesh_R", tPr, UVf, tpnr, tppr, u0f, u1f, material=m_foot)

    # fur length: long pile on the body, short on the head, shortest under the beads / beak root
    eye_pts = [e[0] for e in eyes]

    def furlen(co):
        p = np.array([co.x, co.z, -co.y])
        f = 1.0 - 0.45 * float(smoothstep(Y_LINE - 0.012, Y_LINE + 0.030, p[1]))
        for e in eye_pts:  # trimmed pile round the beads (keeps the beads + wide-eye rings clear)
            f = min(f, 0.14 + 0.41 * float(smoothstep(0.026, 0.046, np.linalg.norm(p - e))))
        f = min(f, 0.18 + 0.37 * float(smoothstep(0.026, 0.048, np.linalg.norm(p - beak_root))))
        f *= 0.3 + 0.7 * float(smoothstep(0.0, 0.012, p[1]))  # flat seat underneath
        return f

    from lib import geo
    geo.point_attribute(body_obj, "_FURLEN", furlen)
    for fo in (flip_L, flip_R):
        geo.point_attribute(fo, "_FURLEN", lambda co: 0.6)

    # rig
    r = rigmod.Rig("guoguo_rig")
    r.bone("root", B(0, 0, 0))
    r.bone("body", B(0, 0, 0), "root")  # pivot on the seat: squash keeps the bottom planted
    r.bone("head", B(0, HEAD_JOINT_Y, 0), "body")
    r.bone("flipper_L", B(*FLIP_ROOT), "body")
    r.bone("flipper_R", B(-FLIP_ROOT[0], FLIP_ROOT[1], FLIP_ROOT[2]), "body")
    r.bone("foot_L", B(*FOOT_JOINT), "body")
    r.bone("foot_R", B(-FOOT_JOINT[0], FOOT_JOINT[1], FOOT_JOINT[2]), "body")
    r.build()

    def w_loft(co):
        w = float(smoothstep(SKIN_BAND[0], SKIN_BAND[1], co.z))
        return {"body": 1.0 - w, "head": w}

    r.bind_fn(body_obj, w_loft)
    for o in [beak_obj] + eye_objs + wide_objs:
        r.bind_rigid(o, "head")
    r.bind_rigid(flip_L, "flipper_L")
    r.bind_rigid(flip_R, "flipper_R")
    r.bind_rigid(foot_L, "foot_L")
    r.bind_rigid(foot_R, "foot_R")

    actions = make_actions(r)

    objs = [body_obj, beak_obj, flip_L, flip_R, foot_L, foot_R] + eye_objs + wide_objs
    tris = {o.name: tri_count(o) for o in objs}
    print(f"[guoguo] triangles: {sum(tris.values())}  {tris}")
    return {
        "seated_height_m": H,
        "standing_height_m": 0.66,
        "joints": ["root", "body", "head", "flipper_L", "flipper_R", "foot_L", "foot_R"],
        "actions": actions,
        "triangles": sum(tris.values()),
        "fur": {"meshes": ["body_mesh", "flipper_mesh_L", "flipper_mesh_R"], "attribute": "_FURLEN",
                "shells": 22, "length_m": 0.015},
        "wide_eye_meshes": ["eyewide_L", "eyewide_R"],
    }
