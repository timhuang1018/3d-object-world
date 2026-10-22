"""Lioness A (scene 001): a Sylvanian Families-style flocked mother figure in a lavender dress and a
cream apron with a gingham hem, bib, pocket, crossed straps and a back bow.

Modelling approach (fixes "assembled from primitives" / "flat partial lathe"):
  * organic parts (head + muzzle, body, arms, legs, tail tuft, nose) are smooth implicit surfaces:
    smooth-unions of ellipsoids / round cones -> voxel remesh of the primitive union (topology only)
    -> every vertex projected onto the smooth SDF and tangentially relaxed.  Colour regions (muzzle,
    paws, soles) are cut exactly along iso-lines of a field, so the colour edges are clean curves.
  * clothes are parametric cloth surfaces: a bell skirt with natural uneven folds, an apron panel that
    follows the dress with flare, thickness and rounded edges, a bib/straps/waist band that are
    projected onto the body surface, a pocket patch and a bow.
All coordinates in the design tables are three.js metres (x = her left, y up, z front).
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from lib import core, geo, mat, tex
from lib import rig as rigmod
from lib.core import B

ITEM = {"id": "characters/lioness", "out": "characters/lioness.glb"}

HC = (0.0, 1.285, 0.0)      # head centre = decal centre (three.js)
S_DECAL = 0.34              # decal half size (~ head radius)

# arm (left; mirror x for the right)
ARM_S, ARM_E, ARM_W = (0.196, 0.893, 0.0), (0.262, 0.724, 0.014), (0.298, 0.586, 0.030)
PAW_C, PAW_R = (0.308, 0.546, 0.036), (0.058, 0.063, 0.060)
ARM_RAD = (0.062, 0.056, 0.051)
# leg (left)
LEG_H, LEG_K, LEG_A = (0.095, 0.47, 0.0), (0.100, 0.27, 0.006), (0.104, 0.095, 0.0)
LEG_RAD = (0.074, 0.064, 0.056)
FOOT_C, FOOT_R = (0.106, 0.050, 0.040), (0.062, 0.050, 0.090)
# tail
TAIL_PTS = [(0, 0.47, -0.10), (0, 0.43, -0.22), (0, 0.395, -0.30), (0, 0.345, -0.40), (0, 0.315, -0.49),
            (0, 0.32, -0.57), (0, 0.37, -0.635), (0, 0.445, -0.665)]
TAIL_J = [(0, 0.398, -0.285), (0, 0.33, -0.445), (0, 0.322, -0.575)]

Y_WAIST = 0.745
Y_SK_TOP, Y_HEM = 0.752, 0.165


# ============================================================================ small helpers
def bv(x, y, z):
    return np.array([x, -z, y], float)


def br(rx, ry, rz):
    return np.array([rx, rz, ry], float)


def t2b(P):
    P = np.asarray(P, float)
    return np.stack([P[..., 0], -P[..., 2], P[..., 1]], -1)


def b2t(P):
    P = np.asarray(P, float)
    return np.stack([P[..., 0], P[..., 2], -P[..., 1]], -1)


def V(a):
    return Vector((float(a[0]), float(a[1]), float(a[2])))


def mx(p, side):
    return (side * p[0], p[1], p[2])


def clamp(x, a=0.0, b=1.0):
    return a if x < a else (b if x > b else x)


def sstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


# ============================================================================ SDF toolkit (Blender coords)
class Ell:
    def __init__(self, c, r, R=None, segs=40):
        self.c, self.r = np.asarray(c, float), np.asarray(r, float)
        self.R = None if R is None else np.asarray(R, float)
        self.segs = segs

    def __call__(self, P):
        q = P - self.c
        if self.R is not None:
            q = q @ self.R
        k0 = np.linalg.norm(q / self.r, axis=1)
        k1 = np.linalg.norm(q / (self.r * self.r), axis=1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)

    def seeds(self):
        o = geo.sphere("_seed", 1.0, segs=self.segs, rings=self.segs // 2)
        M = Matrix.Translation(V(self.c))
        if self.R is not None:
            M = M @ Matrix(self.R.tolist()).to_4x4()
        o.data.transform(M @ Matrix.Diagonal((*self.r, 1.0)))
        return [o]


class Tube:
    """Polyline of round cones (radius per point)."""

    def __init__(self, pts, radii, segs=24):
        self.p = [np.asarray(p, float) for p in pts]
        self.r = [float(x) for x in radii]
        self.segs = segs

    def __call__(self, P):
        d = None
        for i in range(len(self.p) - 1):
            a, b, ra, rb = self.p[i], self.p[i + 1], self.r[i], self.r[i + 1]
            ba, pa = b - a, P - a
            h = np.clip(pa @ ba / float(ba @ ba), 0.0, 1.0)
            di = np.linalg.norm(pa - h[:, None] * ba, axis=1) - (ra + (rb - ra) * h)
            d = di if d is None else np.minimum(d, di)
        return d

    def seeds(self):
        out = []
        for i in range(len(self.p) - 1):
            out.append(geo.tube("_seed", [V(self.p[i]), V(self.p[i + 1])], radius=[self.r[i], self.r[i + 1]],
                                segs=self.segs, round_caps=True))
        return out


class U:
    """Smooth union (polynomial smin, radius k)."""

    def __init__(self, k, *kids):
        self.k, self.kids = k, kids

    def __call__(self, P):
        d = self.kids[0](P)
        for c in self.kids[1:]:
            d2 = c(P)
            if self.k <= 0:
                d = np.minimum(d, d2)
            else:
                h = np.clip(0.5 + 0.5 * (d2 - d) / self.k, 0.0, 1.0)
                d = d2 * (1 - h) + d * h - self.k * h * (1 - h)
        return d

    def seeds(self):
        return [s for c in self.kids for s in c.seeds()]


def grad(f, P, e=1e-4):
    g = np.empty_like(P)
    for i in range(3):
        d = np.zeros(3)
        d[i] = e
        g[:, i] = (f(P + d) - f(P - d)) / (2 * e)
    return g


def normals(f, P):
    g = grad(f, P)
    return g / np.maximum(np.linalg.norm(g, axis=1), 1e-12)[:, None]


def project(f, P, iters=6):
    for _ in range(iters):
        d = f(P)
        g = grad(f, P)
        P = P - (d / np.maximum((g * g).sum(1), 1e-12))[:, None] * g
    return P


def ray_out(f, o, d, tmax, iters=40):
    """Points where rays o + d t (t in [0, tmax]) leave the solid (o inside)."""
    o, d = np.atleast_2d(o).astype(float), np.atleast_2d(d).astype(float)
    lo, hi = np.zeros(len(o)), np.full(len(o), float(tmax))
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        inside = f(o + d * mid[:, None]) < 0
        lo, hi = np.where(inside, mid, lo), np.where(inside, hi, mid)
    return o + d * (0.5 * (lo + hi))[:, None]


def ray_in(f, o, d, tmax, iters=40):
    """Points where rays o + d t first enter the solid (o outside, o + d tmax inside)."""
    o, d = np.atleast_2d(o).astype(float), np.atleast_2d(d).astype(float)
    lo, hi = np.zeros(len(o)), np.full(len(o), float(tmax))
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        inside = f(o + d * mid[:, None]) < 0
        lo, hi = np.where(inside, lo, mid), np.where(inside, mid, hi)
    return o + d * (0.5 * (lo + hi))[:, None]


def mesh_co(me):
    P = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", P)
    return P.reshape(-1, 3)


def mesh_edges(me):
    E = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", E)
    return E.reshape(-1, 2)


def set_co(me, P):
    me.vertices.foreach_set("co", np.asarray(P, np.float32).ravel())
    me.update()


def relax(f, P, E, iters=3, lam=0.5):
    n = len(P)
    deg = np.maximum(np.bincount(E.ravel(), minlength=n), 1).astype(float)
    for _ in range(iters):
        acc = np.zeros_like(P)
        np.add.at(acc, E[:, 0], P[E[:, 1]])
        np.add.at(acc, E[:, 1], P[E[:, 0]])
        P = P + lam * (acc / deg[:, None] - P)
        P = project(f, P, 3)
    return P


def keep_largest(obj):
    me = obj.data
    n = len(me.vertices)
    E = mesh_edges(me)
    lab = np.arange(n)
    for _ in range(400):
        m = np.minimum(lab[E[:, 0]], lab[E[:, 1]])
        new = lab.copy()
        np.minimum.at(new, E[:, 0], m)
        np.minimum.at(new, E[:, 1], m)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    vals, counts = np.unique(lab, return_counts=True)
    if len(vals) > 1:
        keep = vals[np.argmax(counts)]
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.nonzero(lab != keep)[0]], context='VERTS')
        bm.to_mesh(me)
        bm.free()
    return obj


SDF_REG = []      # (object, field) pairs: get analytic SDF normals at the end of build()


def sdf_normals(obj, f):
    """Custom split normals from the field gradient: shading follows the smooth implicit surface instead
    of the irregular remesh/iso-cut triangulation (removes the blotchy wavy bands)."""
    me = obj.data
    N = normals(f, mesh_co(me))
    me.normals_split_custom_set_from_vertices([tuple(map(float, n)) for n in N])


def sdf_mesh(name, f, voxel, relax_iters=3, mats=()):
    obj = core.join(f.seeds(), name)
    SDF_REG.append((obj, f))
    core.voxel_remesh(obj, voxel)
    keep_largest(obj)
    me = obj.data
    P = project(f, mesh_co(me), 8)
    P = relax(f, P, mesh_edges(me), relax_iters, lam=0.6)
    set_co(me, P)
    core.shade_smooth(obj)
    for m in mats:
        me.materials.append(m)
    return obj


def iso_cut(obj, field, tau, surf=None, idx=1):
    """Split faces exactly along field == tau; faces with field < tau get material `idx`."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.verts.ensure_lookup_table()
    P = np.array([v.co[:] for v in bm.verts])
    val = field(P) - tau
    val = np.where(np.abs(val) < 1e-7, 1e-7, val)
    vv = {v: val[i] for i, v in enumerate(bm.verts)}
    cross = [e for e in bm.edges if (vv[e.verts[0]] < 0) != (vv[e.verts[1]] < 0)]
    newv = []
    for e in cross:
        v0, v1 = e.verts
        a, b = vv[v0], vv[v1]
        _, nv = bmesh.utils.edge_split(e, v0, a / (a - b))
        newv.append(nv)
    if surf is not None and newv:
        Q = project(surf, np.array([v.co[:] for v in newv]), 3)
        for v, q in zip(newv, Q):
            v.co = q
    nset = set(newv)
    for f in list(bm.faces):
        vs = [v for v in f.verts if v in nset]
        if len(vs) == 2:
            try:
                bmesh.utils.face_split(f, vs[0], vs[1])
            except Exception:
                pass
    C = np.array([f.calc_center_median()[:] for f in bm.faces])
    inside = field(C) < tau
    for f, ins in zip(bm.faces, inside):
        f.material_index = idx if ins else f.material_index
        f.smooth = True
    bm.to_mesh(me)
    bm.free()
    me.update()
    return obj


def uv_const(obj, uv=(0.5, 0.8)):
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    lay = me.uv_layers.active
    arr = np.tile(np.array(uv, np.float32), len(lay.data))
    lay.data.foreach_set("uv", arr)
    return obj


def cr_path(pts, n_per=6, closed=False):
    P = [np.asarray(p, float) for p in pts]
    N, out = len(P), []
    for i in (range(N) if closed else range(N - 1)):
        p1, p2 = P[i], P[(i + 1) % N]
        p0 = P[(i - 1) % N] if (closed or i > 0) else 2 * P[0] - P[1]
        p3 = P[(i + 2) % N] if (closed or i + 2 < N) else 2 * P[-1] - P[-2]
        for k in range(n_per):
            s = k / n_per
            out.append(0.5 * (2 * p1 + (-p0 + p2) * s + (2 * p0 - 5 * p1 + 4 * p2 - p3) * s * s
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * s ** 3))
    if not closed:
        out.append(P[-1])
    return out


def ribbon(name, pts, nrms, width, thick, segs=12, closed=False, notch=0.0, mat_=None):
    """Strip with a rounded-rectangle section along pts (Blender); nrms = thickness direction."""
    pts = [np.asarray(p, float) for p in pts]
    N = len(pts)
    W = list(width) if hasattr(width, "__len__") else [width] * N
    Tk = list(thick) if hasattr(thick, "__len__") else [thick] * N
    rings = []
    for i in range(N):
        if closed:
            t = pts[(i + 1) % N] - pts[(i - 1) % N]
        else:
            t = pts[min(i + 1, N - 1)] - pts[max(i - 1, 0)]
        t = unit(t)
        n = np.asarray(nrms[i], float)
        n = unit(n - t * (n @ t))
        w = np.cross(t, n)
        ring = []
        for k in range(segs):
            a = 2 * math.pi * (k + 0.5) / segs
            c, s = math.cos(a), math.sin(a)
            x = W[i] / 2 * math.copysign(abs(c) ** 0.5, c)
            y = Tk[i] / 2 * math.copysign(abs(s) ** 0.5, s)
            p = pts[i] + w * x + n * y
            if notch and i == N - 1:
                p = p + t * notch * (abs(x) / (W[i] / 2) - 0.5)
            ring.append(V(p))
        rings.append(ring)
    if closed:
        rings.append(rings[0])
        obj = geo.loft(name, rings, mat=mat_, cap_start=False, cap_end=False)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bm.to_mesh(obj.data)
        bm.free()
        core.shade_smooth(obj)
    else:
        obj = geo.loft(name, rings, mat=mat_)
    return obj


def revolve(name, prof, segs, M, seg_mats=None, radial=None, mats=()):
    """Revolve (r, h) profile about local Z; M = local->world 4x4 (Blender)."""
    bm = bmesh.new()
    rings = []
    for k, (r, h) in enumerate(prof):
        if r < 1e-7:
            rings.append([bm.verts.new((0.0, 0.0, h))])
            continue
        ring = []
        for i in range(segs):
            th = 2 * math.pi * i / segs
            rr = r * (radial(th, k) if radial else 1.0)
            ring.append(bm.verts.new((rr * math.cos(th), rr * math.sin(th), h)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            fl = [bm.faces.new((a[0], b[(i + 1) % segs], b[i])) for i in range(segs)]
        elif len(b) == 1:
            fl = [bm.faces.new((a[i], a[(i + 1) % segs], b[0])) for i in range(segs)]
        else:
            fl = [bm.faces.new((a[i], a[(i + 1) % segs], b[(i + 1) % segs], b[i])) for i in range(segs)]
        for f in fl:
            f.material_index = seg_mats[k] if seg_mats else 0
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.transform(M)
    obj = core.new_mesh_object(name, bm=bm)
    for m in mats:
        obj.data.materials.append(m)
    core.shade_smooth(obj)
    return obj


def frame_matrix(origin, x, y, z, scale=(1, 1, 1)):
    """Blender local->world from orthonormal axes (Blender vectors)."""
    M = Matrix((
        (x[0] * scale[0], y[0] * scale[1], z[0] * scale[2], origin[0]),
        (x[1] * scale[0], y[1] * scale[1], z[1] * scale[2], origin[1]),
        (x[2] * scale[0], y[2] * scale[1], z[2] * scale[2], origin[2]),
        (0, 0, 0, 1)))
    return M


def grid_obj(name, Pb, face_uv=None, mats=(), flip=False):
    """Quad grid from (nv, nu, 3) Blender points; rows bottom->top, columns -> her left."""
    nv, nu = Pb.shape[:2]
    bm = bmesh.new()
    vs = [[bm.verts.new(Pb[j, i].tolist()) for i in range(nu)] for j in range(nv)]
    uvl = bm.loops.layers.uv.new("UVMap") if face_uv else None
    for j in range(nv - 1):
        for i in range(nu - 1):
            quad = (vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i])
            uvs = face_uv(j, i) if face_uv else None
            if flip:
                quad, uvs = quad[::-1], (uvs[::-1] if uvs else None)
            f = bm.faces.new(quad)
            if uvl:
                for loop, uv in zip(f.loops, uvs):
                    loop[uvl].uv = uv
    obj = core.new_mesh_object(name, bm=bm)
    for m in mats:
        obj.data.materials.append(m)
    core.shade_smooth(obj)
    return obj


def thicken(obj, t, offset=1.0, bevel=0.0):
    core.add_solidify(obj, thickness=t, offset=offset, even=True, rim=True)
    core.apply_modifiers(obj)
    if bevel:
        core.add_bevel(obj, width=bevel, segments=2, limit='ANGLE', angle_deg=55)
        core.apply_modifiers(obj)
    core.shade_smooth(obj)
    return obj


# ============================================================================ materials
def apron_image():
    plain = np.ones((256, 256, 3), np.float32) * tex.rgb('#f7f1e6')[None, None, :]
    ging = tex.gingham(base='#f7f1e6', check=(201, 139, 124), alpha=0.5, size=256, bands=4)
    # rows 0..255 (top, v 0.5..1) plain cream; rows 256..511 (v 0..0.5) gingham, 4 x 4 periods
    return mat.image_from_array("apron_gingham", np.concatenate([plain, ging], axis=0))


TILE = 0.12          # metres per gingham texture width (4 periods of 3 cm)


def band_uv(s, h):
    """Gingham UV for arc position s and height h above the band's base line (metres)."""
    return (s / TILE, 0.04 + h / (TILE * 2.0))


PLAIN_UV = (0.5, 0.78)


def make_materials():
    return {
        "fur": mat.vinyl("fur", "#d5b186"),
        "fur_light": mat.vinyl("fur_light", "#e3c6a0"),
        "muzzle": mat.vinyl("muzzle", "#f3e7d2"),
        "nose": mat.vinyl("nose", "#b27c6c"),
        "inner_ear": mat.vinyl("inner_ear", "#efd9c0"),
        "ear_back": mat.vinyl("ear_back", "#6e5442"),
        "tuft": mat.vinyl("tail_tuft", "#7a5a40"),
        "dress": mat.vinyl("dress", "#a8a8c6"),
        "apron": mat.material("vinyl_apron", "#f7f1e6", roughness=0.5, coat=0.22, coat_roughness=0.5,
                              sheen=0.15, sheen_roughness=0.8, image=apron_image()),
        "whisker": mat.ink("whisker", "#6e5442"),
        "decal": mat.decal("face"),
    }


# ============================================================================ head
def rot3(axis, deg):
    """Rotation (three.js axis 'x'|'y'|'z', degrees) expressed in Blender coords, for Ell(R=...)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    R = {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
         "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
         "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]
    C = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)    # three -> Blender
    return C @ np.array(R, float) @ C.T


def HP(x, y, z):
    """Head-relative three.js offset -> Blender point."""
    return bv(HC[0] + x, HC[1] + y, HC[2] + z)


def head_sdfs():
    """Feline head: wide, flat-crowned skull, full cheeks with soft ruff scallops, and a real muzzle
    (two whisker pads with a cleft, a chin and a nose bridge).  Returns (head, muzzle, light) fields."""
    cran = Ell(HP(0, 0.036, -0.035), br(0.300, 0.258, 0.268), segs=48)
    brow = Ell(HP(0, 0.050, 0.055), br(0.236, 0.168, 0.200))
    cheeks = [Ell(HP(s * 0.150, -0.072, 0.072), br(0.176, 0.150, 0.172)) for s in (1, -1)]
    jaw = Ell(HP(0, -0.118, 0.050), br(0.205, 0.138, 0.198))
    face = U(0.07, cran, brow, cheeks[0], cheeks[1], jaw)
    tufts = []
    for s in (1, -1):
        # soft plush cheek ruffs swept back and down, blended into the cheek
        for (c, d, rl, rs, rt) in (((0.282, -0.090, 0.010), (0.84, -0.42, -0.26), 0.080, 0.050, 0.062),
                                   ((0.236, -0.168, 0.026), (0.58, -0.74, -0.24), 0.070, 0.045, 0.056)):
            dd = unit(np.array([s * d[0], d[1], d[2]]))
            ww = unit(np.cross(dd, np.array([0.0, 0.0, 1.0])))
            uu = np.cross(ww, dd)
            R = np.stack([t2b(dd), t2b(ww), t2b(uu)], 1)
            tufts.append(Ell(HP(s * c[0], c[1], c[2]), np.array([rl, rs, rt]), R=R, segs=32))
    ruff = U(0.03, *tufts)
    face = U(0.045, face, ruff)
    pads = [Ell(HP(s * 0.052, -0.092, 0.262), br(0.066, 0.055, 0.064)) for s in (1, -1)]
    chin = Ell(HP(0, -0.158, 0.228), br(0.050, 0.037, 0.048))
    bridge = Tube([HP(0, -0.002, 0.236), HP(0, -0.050, 0.290)], [0.031, 0.040])
    muzzle = U(0.012, pads[0], pads[1], chin)
    head = U(0.028, face, U(0.022, bridge, muzzle))
    low = Ell(HP(0, -0.262, 0.090), br(0.26, 0.105, 0.26))
    light = low
    return head, muzzle, light


def front_hit(f, x, y, zfront=0.6):
    """Surface point (Blender) hit by a ray from the front at three.js (x, y)."""
    o = bv(x, y, zfront)[None]
    return ray_in(f, o, np.array([[0.0, 1.0, 0.0]]), zfront + 0.2)[0]


def build_head(M):
    hsdf, msdf, lsdf = head_sdfs()
    head = sdf_mesh("lion_head", hsdf, voxel=0.0128, relax_iters=8,
                    mats=(M["fur"], M["muzzle"], M["fur_light"]))
    iso_cut(head, lsdf, 0.008, surf=hsdf, idx=2)
    iso_cut(head, msdf, 0.0075, surf=hsdf, idx=1)
    cx, cy, cz = HC
    parts = {"head": head, "hsdf": hsdf}

    # nose: soft rounded triangle sitting on the end of the bridge, above the whisker pads
    hit = front_hit(hsdf, 0.0, cy - 0.046)
    n = normals(hsdf, hit[None])[0]
    nc = hit + n * 0.005
    nsdf = U(0.02,
             Ell(nc + np.array([0.018, 0, 0.004]), br(0.022, 0.016, 0.016)),
             Ell(nc + np.array([-0.018, 0, 0.004]), br(0.022, 0.016, 0.016)),
             Ell(nc + np.array([0.0, 0.003, -0.016]), br(0.012, 0.014, 0.012)))
    nose = sdf_mesh("lion_nose", nsdf, voxel=0.0052, relax_iters=2, mats=(M["nose"],))
    # tilt the nose back so it lies on the muzzle's upper slope
    R = Matrix.Rotation(math.radians(-18), 4, 'X')
    nose.data.transform(Matrix.Translation(V(nc)) @ R @ Matrix.Translation(-V(nc)))
    parts["nose"] = nose
    parts["nose_top_y"] = float(max((nose.matrix_world @ v.co).z for v in nose.data.vertices))

    # philtrum: a short ink groove from the nose down the cleft between the pads
    ph = [front_hit(hsdf, 0.0, cy + y) for y in (-0.062, -0.078, -0.094, -0.106)]
    ph = [p + normals(hsdf, p[None])[0] * 0.0006 for p in ph]
    philtrum = geo.tube("_ph", [V(p) for p in ph], radius=[0.0030, 0.0030, 0.0028, 0.0024], segs=8,
                        round_caps=True)

    # whisker dots (3 per side) + 3 whiskers per side
    dots, wh = [philtrum], []
    for sx in (1, -1):
        lx = sx * 0.040
        for dx, dy in ((0.008, 0.012), (0.030, 0.004), (0.016, -0.014)):
            p = front_hit(hsdf, lx + sx * dx, cy - 0.092 + dy)
            nn = normals(hsdf, p[None])[0]
            d = geo.sphere("_dot", 1.0, segs=12, rings=6)
            q = Vector((0, 0, 1)).rotation_difference(V(nn))
            d.data.transform(Matrix.Translation(V(p - nn * 0.0012)) @ q.to_matrix().to_4x4()
                             @ Matrix.Diagonal((0.0068, 0.0068, 0.003, 1)))
            dots.append(d)
        for k, (dy, ang) in enumerate(((0.012, 13.0), (0.0, 1.0), (-0.012, -11.0))):
            p0 = front_hit(hsdf, sx * 0.090, cy - 0.094 + dy)
            nn = normals(hsdf, p0[None])[0]
            a = math.radians(ang)
            d3 = unit(np.array([sx * math.cos(a), 0.0, math.sin(a) + 0.0]) + np.array([0, -0.22, 0]))
            path = []
            L = 0.15 - 0.012 * abs(k - 1)
            for i in range(6):
                s = i / 5
                path.append(V(p0 - nn * 0.006 + d3 * L * s + np.array([0, 0, -0.012 * s * s])))
            wh.append(geo.tube("_wh", path, radius=[0.0030, 0.0028, 0.0025, 0.0021, 0.0017, 0.0012],
                               segs=6, round_caps=True))
    parts["dots"] = core.join(dots, "lion_whisker_dots")
    parts["dots"].data.materials.append(M["whisker"])
    parts["whiskers"] = core.join(wh, "lion_whiskers")
    parts["whiskers"].data.materials.clear()
    parts["whiskers"].data.materials.append(M["whisker"])
    for o in (parts["dots"], parts["whiskers"]):
        core.shade_smooth(o)

    # ears: side-set rounded triangles, cupped forward; dark backs, fur rim, cream inside
    ears = {}

    def tri_radial(th, k):
        ph = (th - math.pi / 2) % (2 * math.pi)            # 0 = tip (away from the head)
        seg = 2 * math.pi / 3
        tri = math.cos(math.pi / 3) / math.cos((ph % seg) - math.pi / 3)
        return (0.62 + 0.38 * tri) * 1.10

    for side, tag in ((1, "L"), (-1, "R")):
        a = math.radians(60)
        dirt = unit(np.array([side * math.sin(a), math.cos(a), -0.14]))
        o = bv(*HC)[None]
        A = ray_out(hsdf, o, t2b(dirt)[None], 0.6)[0]
        up = normals(hsdf, A[None])[0]
        up = unit(up + t2b(np.array([0.0, 0.25, 0.0])))       # stand a little more upright
        fwd = t2b(unit(np.array([side * 0.55, 0.0, 1.0])))
        fwd = unit(fwd - up * (fwd @ up))
        xax = np.cross(up, fwd)
        C = A + up * 0.030
        prof = [(0.0, -0.020), (0.034, -0.019), (0.062, -0.014), (0.081, -0.006), (0.091, 0.003),
                (0.093, 0.011), (0.088, 0.017), (0.077, 0.018), (0.063, 0.011), (0.043, 0.003),
                (0.021, -0.002), (0.0, -0.003)]
        seg_mats = [0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 2]
        Mx = frame_matrix(C, xax, up, fwd, scale=(0.92, 1.0, 1.0))
        ear = revolve(f"lion_ear_{tag}", prof, 48, Mx, seg_mats=seg_mats, radial=tri_radial,
                      mats=(M["ear_back"], M["fur"], M["inner_ear"]))
        ears[tag] = (ear, A)
        P = b2t(np.array([ear.matrix_world @ v.co for v in ear.data.vertices]))
        ears[tag + "_minx"] = float(np.min(np.abs(P[:, 0])))
    parts["ears"] = ears
    return parts


# ============================================================================ body
def torso_sdf():
    chest = Ell(bv(0, 0.828, 0.0), br(0.185, 0.152, 0.158), segs=40)
    belly = Ell(bv(0, 0.585, 0.0), br(0.192, 0.215, 0.176), segs=40)
    sh = Tube([bv(-0.135, 0.898, -0.004), bv(0.135, 0.898, -0.004)], [0.066, 0.066])
    return U(0.07, U(0.08, chest, belly), sh)


def waist_radii(tsdf, y, n=96):
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    dirs = t2b(np.stack([np.sin(th), np.zeros(n), np.cos(th)], -1))
    o = np.repeat(bv(0, y, 0)[None], n, 0)
    hits = ray_out(tsdf, o, dirs, 0.5)
    return th, np.linalg.norm(hits - o, axis=1)


# ---- skirt shape
class Skirt:
    def __init__(self, r_top, dz_top):
        self.r_top, self.dz_top = r_top, dz_top
        self.r_hem = 0.352

    def t(self, y):
        return clamp((Y_SK_TOP - y) / (Y_SK_TOP - Y_HEM), 0.0, 1.2)

    def r0(self, y):
        t = self.t(y)
        return self.r_top + (self.r_hem - self.r_top) * (1 - (1 - min(t, 1.0)) ** 1.25) + 0.05 * max(0, t - 1)

    def dz(self, y):
        return self.dz_top + (0.93 - self.dz_top) * min(self.t(y), 1.0)

    def amp(self, y):
        return 0.046 * min(self.t(y), 1.0) ** 1.35

    @staticmethod
    def fold(th):
        return (math.cos(13 * th + 0.9 * math.sin(2 * th + 0.4) + 0.5 * math.sin(5 * th + 1.7))
                * (0.72 + 0.28 * math.cos(3 * th + 0.8)))

    def point(self, th, y, extra=0.0):
        r = self.r0(y) * (1 + self.amp(y) * self.fold(th)) + extra
        return (r * math.sin(th), y, r * math.cos(th) * self.dz(y))

    def outer_max(self, y):
        return self.r0(y) * (1 + self.amp(y))


def build_skirt(M, sk):
    nu, nv = 112, 18
    P = np.zeros((nv, nu + 1, 3))
    for j in range(nv):
        for i in range(nu + 1):
            th = 2 * math.pi * i / nu - math.pi
            yb = Y_HEM + 0.006 * Skirt.fold(th)
            s = j / (nv - 1)
            y = yb + (Y_SK_TOP - yb) * (s ** 1.1)
            P[j, i] = sk.point(th, y)
    obj = grid_obj("dress_skirt", t2b(P), mats=(M["dress"],))
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    # make sure normals point outward
    f0 = bm.faces[0]
    c = f0.calc_center_median()
    if f0.normal.dot(Vector((c.x, c.y, 0))) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data)
    bm.free()
    return thicken(obj, 0.011, offset=-1.0)


# ---- apron
AP_TOP, AP_BOT, AP_WT, AP_WB, AP_RC, HEM_H, AP_T = 0.745, 0.262, 0.196, 0.262, 0.042, 0.062, 0.0075


def apron_R(sk, s, y):
    tt = clamp((AP_TOP - y) / (AP_TOP - AP_BOT))
    return (sk.outer_max(y) + 0.0045 + 0.016 * tt ** 2
            + 0.0055 * tt * math.cos(2 * math.pi * s / 0.17 + 0.6))


def apron_pt(sk, s, y, extra=0.0):
    R = apron_R(sk, s, y) + extra
    th = s / R
    return (R * math.sin(th), y, R * math.cos(th) * sk.dz(y))


def rounded_lift(u, W, rc):
    e = abs(u) * W - (W - rc)
    return rc - math.sqrt(max(0.0, rc * rc - e * e)) if e > 0 else 0.0


def build_apron_panel(M, sk):
    nu, nb, nbody = 57, 3, 19
    us = np.linspace(-1, 1, nu)
    rows = nb + nbody + 1
    P = np.zeros((rows, nu, 3))
    S = np.zeros((rows, nu))
    Y = np.zeros((rows, nu))
    for i, u in enumerate(us):
        yb = AP_BOT + rounded_lift(u, AP_WB, AP_RC)
        for j in range(rows):
            if j <= nb:
                y = yb + (AP_BOT + HEM_H - yb) * j / nb
            else:
                y = AP_BOT + HEM_H + (AP_TOP - AP_BOT - HEM_H) * (j - nb) / nbody
            W = AP_WB + (AP_WT - AP_WB) * (y - AP_BOT) / (AP_TOP - AP_BOT)
            s = u * W
            P[j, i], S[j, i], Y[j, i] = apron_pt(sk, s, y), s, y

    def fuv(j, i):
        idx = ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i))
        if j < nb:
            return [band_uv(S[a, b], Y[a, b] - AP_BOT) for a, b in idx]
        return [PLAIN_UV] * 4

    obj = grid_obj("apron_skirt", t2b(P), face_uv=fuv, mats=(M["apron"],))
    return thicken(obj, AP_T, offset=1.0, bevel=0.0028)


def build_pocket(M, sk):
    s0, yt, yb0, W, rc, bh = 0.075, 0.548, 0.43, 0.068, 0.03, 0.024
    nu, nbody, nb = 21, 12, 3
    us = np.linspace(-1, 1, nu)
    rows = nbody + nb + 1
    P, S, Y = np.zeros((rows, nu, 3)), np.zeros((rows, nu)), np.zeros((rows, nu))
    for i, u in enumerate(us):
        yb = yb0 + rounded_lift(u, W, rc)
        for j in range(rows):
            if j <= nbody:
                y = yb + (yt - bh - yb) * j / nbody
            else:
                y = yt - bh + bh * (j - nbody) / nb
            gape = 0.006 * (1 - u * u) * sstep(yt - 0.05, yt, y)
            s = s0 + u * W
            P[j, i] = apron_pt(sk, s, y, extra=AP_T + 0.0015 + gape)
            S[j, i], Y[j, i] = s, y

    def fuv(j, i):
        idx = ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i))
        if j >= nbody:
            return [band_uv(S[a, b], Y[a, b] - (yt - bh)) for a, b in idx]
        return [PLAIN_UV] * 4

    obj = grid_obj("apron_pocket", t2b(P), face_uv=fuv, mats=(M["apron"],))
    return thicken(obj, 0.005, offset=1.0, bevel=0.002)


def build_bib(M, tsdf):
    yb, yt, wt, wb, rc, bh = Y_WAIST - 0.01, 0.925, 0.098, 0.112, 0.03, 0.022
    nu, nbody, nb = 25, 13, 3
    us = np.linspace(-1, 1, nu)
    rows = nbody + nb + 1
    XY = np.zeros((rows, nu, 2))
    for i, u in enumerate(us):
        ytop = yt - rounded_lift(u, wt, rc)
        ybb = min(yt - bh, ytop - 0.008)     # band base never crosses the rounded top corner
        for j in range(rows):
            if j <= nbody:
                y = yb + (ybb - yb) * j / nbody
            else:
                y = ybb + (ytop - ybb) * (j - nbody) / nb
            w = wb + (wt - wb) * (y - yb) / (yt - yb)
            XY[j, i] = (u * w, y)
    flat = XY.reshape(-1, 2)
    o = t2b(np.stack([flat[:, 0], flat[:, 1], np.full(len(flat), 0.5)], -1))
    hit = ray_in(tsdf, o, np.repeat(np.array([[0.0, 1.0, 0.0]]), len(o), 0), 0.6)
    nn = normals(tsdf, hit)
    Pb = (hit + nn * 0.0045).reshape(rows, nu, 3)

    def fuv(j, i):
        idx = ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i))
        if j >= nbody:
            return [band_uv(XY[a, b, 0], XY[a, b, 1] - (yt - bh)) for a, b in idx]
        return [PLAIN_UV] * 4

    obj = grid_obj("apron_bib", Pb, face_uv=fuv, mats=(M["apron"],))
    return thicken(obj, 0.0055, offset=1.0, bevel=0.002)


def surface_path(tsdf, guesses, n_per=5, offset=0.006, extra=None):
    pts = np.array(cr_path([t2b(np.array(g)) for g in guesses], n_per))
    for _ in range(3):
        pts = project(tsdf, pts, 6)
        sm = pts.copy()
        sm[1:-1] = 0.25 * pts[:-2] + 0.5 * pts[1:-1] + 0.25 * pts[2:]
        pts = sm
    pts = project(tsdf, pts, 6)
    nn = normals(tsdf, pts)
    off = np.full(len(pts), offset)
    if extra is not None:
        off = off + np.array([extra(b2t(p)) for p in pts])
    return pts + nn * off[:, None], nn


def build_straps(M, tsdf):
    objs = []
    for side in (1, -1):
        g = [(0.088, 0.900, 0.20), (0.098, 0.945, 0.14), (0.108, 0.985, 0.05), (0.104, 0.982, -0.05),
             (0.090, 0.935, -0.14), (0.055, 0.870, -0.17), (0.0, 0.820, -0.18), (-0.05, 0.78, -0.18),
             (-0.088, 0.738, -0.17)]
        g = [mx(p, side) for p in g]

        def extra(p, side=side):
            e = 0.0
            if p[2] > 0 and p[1] < 0.93:
                e += 0.0055 * (1 - sstep(0.905, 0.93, p[1]))      # rides on top of the bib
            if side > 0 and p[2] < 0:
                e += 0.0065 * (1 - sstep(0.03, 0.07, abs(p[0])))   # left strap crosses over the right
            return e

        pts, nn = surface_path(tsdf, g, offset=0.0075, extra=extra)
        objs.append(ribbon(f"_strap{side}", pts, nn, 0.034, 0.0055, segs=12))
    o = core.join(objs, "apron_straps")
    o.data.materials.clear()
    o.data.materials.append(M["apron"])
    return uv_const(o, PLAIN_UV)


def build_waistband(M, tsdf, sk):
    th, rt = waist_radii(tsdf, Y_WAIST, 96)
    r_inner = []
    for a, r in zip(th, rt):
        rs = sk.r_top * math.hypot(math.sin(a), math.cos(a) * sk.dz_top)
        front = math.cos(a) > 0 and abs(math.sin(a)) * rs < AP_WT * 1.1
        ra = (apron_R(sk, 0.0, AP_TOP) + AP_T) * math.hypot(math.sin(a), math.cos(a) * sk.dz(AP_TOP)) if front else 0
        r_inner.append(max(r + 0.0105, rs + 0.003, ra + 0.0015) + 0.001)
    r_inner = np.array(r_inner)
    r_inner = np.convolve(np.concatenate([r_inner[-3:], r_inner, r_inner[:3]]), np.ones(7) / 7, 'valid')
    BT = 0.013
    rc = r_inner + BT / 2
    P3 = np.stack([rc * np.sin(th), np.full(len(th), Y_WAIST), rc * np.cos(th)], -1)
    N3 = np.stack([np.sin(th), np.zeros(len(th)), np.cos(th)], -1)
    band = ribbon("apron_waistband", t2b(P3), t2b(N3), 0.042, BT, segs=10, closed=True, mat_=M["apron"])
    uv_const(band, PLAIN_UV)
    back_r = float(rc[np.argmin(np.abs(th - math.pi))] + BT / 2)
    return band, back_r


def build_bow(M, back_r, sk):
    K = np.array([0.0, Y_WAIST, -(back_r + 0.010)])
    parts = []
    knot = geo.sphere("_knot", 1.0, segs=20, rings=10)
    knot.data.transform(Matrix.Translation(V(bv(*K))) @ Matrix.Diagonal((0.034, 0.019, 0.031, 1)))
    parts.append(knot)

    def zb(x):
        return -math.sqrt(max(back_r ** 2 - x * x, 0.0))

    for side in (1, -1):
        pts, nrm = [], []
        n = 44
        for k in range(n):
            ph = 2 * math.pi * k / n
            x = 0.128 * (1 - math.cos(ph)) / 2
            y = 0.050 * math.sin(ph) * (0.5 + 0.5 * (1 - math.cos(ph)) / 2)
            a = math.radians(-15)
            x2, y2 = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
            z = zb(x2) - 0.018 - 0.012 * (1 - math.cos(ph)) / 2
            pts.append(bv(side * x2, Y_WAIST + y2, z))
        cen = np.mean(pts, axis=0)
        for p in pts:
            nrm.append(p - cen)
        parts.append(ribbon(f"_loop{side}", pts, nrm, 0.044, 0.011, segs=12, closed=True))
        tail_g = [(0.010, 0.735), (0.030, 0.690), (0.047, 0.635), (0.060, 0.585), (0.068, 0.555)]
        tp, tn = [], []
        for x, y in cr_path([np.array(p) for p in tail_g], 4):
            r = sk.outer_max(y) * sk.dz(y) if y < Y_SK_TOP else back_r
            zz = -math.sqrt(max((max(r, back_r if y > 0.72 else r) + 0.012) ** 2 - x * x, 0.0))
            tp.append(bv(side * x, y, zz))
            tn.append(t2b(np.array([side * x, 0.0, zz])))
        parts.append(ribbon(f"_tail{side}", tp, tn, 0.046, 0.0085, segs=12, notch=0.022))
    o = core.join(parts, "apron_bow")
    o.data.materials.clear()
    o.data.materials.append(M["apron"])
    core.shade_smooth(o)
    return uv_const(o, PLAIN_UV)


def build_sleeve(M, side):
    S, E = np.array(mx(ARM_S, side)), np.array(mx(ARM_E, side))
    a = t2b(unit(E - S))
    ref = np.array([0.0, -1.0, 0.0])
    xax = unit(np.cross(ref, a)) if abs(ref @ a) < 0.95 else np.array([1.0, 0, 0])
    yax = np.cross(a, xax)
    Mx = frame_matrix(t2b(S), xax, yax, a)
    prof = [(0.0, -0.078), (0.036, -0.072), (0.070, -0.052), (0.091, -0.022), (0.099, 0.016),
            (0.095, 0.054), (0.083, 0.084), (0.070, 0.104), (0.064, 0.114), (0.066, 0.120),
            (0.066, 0.134), (0.060, 0.140), (0.046, 0.143)]

    def radial(th, k):
        g = [0.05, 0.06, 0.05, 0.03, 0.022, 0.026, 0.04, 0.055, 0.03, 0.0, 0.0, 0.0, 0.0][k]
        return 1.0 + g * math.cos(9 * th + 0.7 * math.sin(2 * th + side))

    return revolve(f"dress_sleeve_{'L' if side > 0 else 'R'}", prof, 36, Mx, radial=radial, mats=(M["dress"],))


# ============================================================================ limbs / tail
def paw_frame(side):
    """Paw axes (three.js): a = down the forearm, f = front, inner = toward the body."""
    E, W = np.array(mx(ARM_E, side)), np.array(mx(ARM_W, side))
    a = unit(W - E)
    f = unit(np.array([0.0, 0.0, 1.0]) - a * a[2])
    inner = side * np.cross(a, f)
    return a, f, inner


def paw_sdf(side):
    """Mitten paw: a flattened palm, finger lobes at the tip (soft grooves between them) and a thumb.
    The right paw leaves the front lobe out: the pointing finger lives there."""
    a, f, inner = paw_frame(side)
    Pc = np.array(mx(PAW_C, side))
    R = np.stack([t2b(inner), t2b(a), t2b(f)], 1)
    kids = [Ell(t2b(Pc), np.array([0.045, 0.064, 0.058]), R)]
    offs = (-0.031, 0.0, 0.031) if side > 0 else (-0.031, 0.0)
    for off in offs:
        c = Pc + a * 0.050 + f * off + inner * 0.002
        kids.append(Ell(t2b(c), np.array([0.031, 0.026, 0.021]), R, segs=24))
    palm = U(0.010, *kids)
    thumb = Pc + f * 0.040 + inner * 0.013 + a * 0.004
    return U(0.018, palm, Ell(t2b(thumb), np.array([0.026, 0.033, 0.024]), R, segs=24))


def build_arm(M, side):
    S, E, W = (bv(*mx(p, side)) for p in (ARM_S, ARM_E, ARM_W))
    tube = Tube([S, E, W], ARM_RAD)
    f = U(0.03, tube, paw_sdf(side))
    arm = sdf_mesh(f"lion_arm_{'L' if side > 0 else 'R'}", f, voxel=0.0095, relax_iters=3,
                   mats=(M["fur"], M["fur_light"]))
    d = unit(W - E)
    iso_cut(arm, lambda P: -((P - W) @ d) + 0.006, 0.0, surf=f)
    return arm


FINGER_CURL = 172.0
FINGER_LEN = 0.078


def finger_geometry():
    """Right index finger, modelled curled back into the paw (rest); finger_R rz = -FINGER_CURL
    straightens it so it sticks out of the paw tip along the forearm.  Returns (mesh, knuckle)."""
    a, f, inner = paw_frame(-1)
    Pc = np.array(mx(PAW_C, -1))
    K = Pc + a * 0.030 + f * 0.010
    c = math.radians(FINGER_CURL)
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    d_curl = Rz @ a
    L = FINGER_LEN
    ss = (0.0, 0.35, 0.7, 1.0)
    path = [V(bv(*(K + d_curl * L * s))) for s in ss]
    fin = geo.tube("lion_finger_R", path, radius=[0.0205, 0.0200, 0.0195, 0.0195], segs=16, round_caps=True)
    return fin, K, a


def build_leg(M, side):
    H, K, A, Fc = (bv(*mx(p, side)) for p in (LEG_H, LEG_K, LEG_A, FOOT_C))
    f = U(0.035, Tube([H, K, A], LEG_RAD), Ell(Fc, br(*FOOT_R)))
    leg = sdf_mesh(f"lion_leg_{'L' if side > 0 else 'R'}", f, voxel=0.0145, relax_iters=3,
                   mats=(M["fur"], M["fur_light"]))
    iso_cut(leg, lambda P: P[:, 2] - 0.014, 0.0, surf=f)
    return leg


def build_tail(M):
    path3 = cr_path([np.array(p, float) for p in TAIL_PTS], 6)
    n = len(path3)
    rad = [0.029 - 0.010 * (i / (n - 1)) for i in range(n)]
    tail = geo.tube("lion_tail", [V(bv(*p)) for p in path3], radius=rad, segs=18, round_caps=True,
                    mat=M["fur"])
    end, prev = np.array(path3[-1]), np.array(path3[-3])
    tdir = unit(end - prev)
    zl = t2b(tdir)
    xl = np.array([1.0, 0, 0])
    yl = np.cross(zl, xl)
    R = np.stack([xl, yl, zl], 1)
    c0 = bv(*(end + tdir * 0.034))
    kids = [Ell(c0, np.array([0.043, 0.041, 0.064]), R)]
    # hair clumps fanned around the tip direction -> a soft lumpy brush tuft
    for k, (ang, tilt, ln) in enumerate(((0.3, 15, 0.040), (1.55, 17, 0.038), (2.8, 15, 0.040),
                                        (4.05, 17, 0.037), (5.3, 15, 0.039), (0.9, 4, 0.046))):
        rad = xl * math.cos(ang) + yl * math.sin(ang)
        dk = unit(zl * math.cos(math.radians(tilt)) + rad * math.sin(math.radians(tilt)))
        xk = unit(np.cross(dk, rad)) if abs(dk @ rad) < 0.99 else xl
        yk = np.cross(dk, xk)
        Rk = np.stack([xk, yk, dk], 1)
        kids.append(Ell(c0 + dk * (0.036 + 0.005 * (k % 2)) + rad * 0.014, np.array([0.023, 0.021, ln]), Rk))
    tuft_f = U(0.024, *kids)
    tuft = sdf_mesh("lion_tail_tuft", tuft_f, voxel=0.0068, relax_iters=2, mats=(M["tuft"],))
    return tail, tuft, path3


# ============================================================================ build
def build_collar(M):
    """High rounded dress neckline + a small cream ruffle: hides the bare neck (no 'lollipop')."""
    Mz = Matrix.Diagonal((1.0, 0.92, 1.0, 1.0))           # a touch shallower front-to-back
    prof = [(0.0, 0.905), (0.152, 0.905), (0.150, 0.925), (0.141, 0.952), (0.126, 0.982), (0.115, 1.010),
            (0.110, 1.026), (0.0, 1.026)]
    band = revolve("dress_collar", prof, 40, Mz, mats=(M["dress"],))
    rprof = [(0.104, 1.010), (0.118, 1.026), (0.132, 1.034), (0.143, 1.030), (0.146, 1.020), (0.138, 1.010),
             (0.118, 1.004), (0.104, 1.004)]

    def ripple(th, k):
        return 1.0 + (0.045 if 2 <= k <= 5 else 0.0) * math.cos(18 * th)

    ruffle = revolve("apron_collar_ruffle", rprof, 144, Mz, radial=ripple, mats=(M["apron"],))
    bm = bmesh.new()
    bm.from_mesh(ruffle.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.contextual_create(bm, geom=[e for e in bm.edges if e.is_boundary])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ruffle.data)
    bm.free()
    core.shade_smooth(ruffle)
    return band, uv_const(ruffle, PLAIN_UV)


def build():
    SDF_REG.clear()
    M = make_materials()
    hp = build_head(M)
    head = hp["head"]
    shell = geo.face_shell(head, B(*HC), S_DECAL, mat=M["decal"])

    tsdf = torso_sdf()
    torso = sdf_mesh("dress_bodice", tsdf, voxel=0.019, relax_iters=3, mats=(M["dress"],))
    neck = geo.cylinder("lion_neck", r=0.100, depth=0.15, center=B(0, 1.0, -0.005), segs=24, mat=M["fur"])

    th, rt = waist_radii(tsdf, Y_SK_TOP, 96)
    rx = float(max(rt[np.argmin(np.abs(th - math.pi / 2))], rt[np.argmin(np.abs(th - 3 * math.pi / 2))]))
    rz = float(max(rt[np.argmin(np.abs(th))], rt[np.argmin(np.abs(th - math.pi))]))
    sk = Skirt(rx + 0.006, (rz + 0.006) / (rx + 0.006))
    skirt = build_skirt(M, sk)
    apron = build_apron_panel(M, sk)
    pocket = build_pocket(M, sk)
    bib = build_bib(M, tsdf)
    straps = build_straps(M, tsdf)
    band, back_r = build_waistband(M, tsdf, sk)
    bow = build_bow(M, back_r, sk)
    sleeves = {s: build_sleeve(M, s) for s in (1, -1)}
    arms = {s: build_arm(M, s) for s in (1, -1)}
    collar, ruffle = build_collar(M)
    finger, knuckle, _ = finger_geometry()
    finger.data.materials.append(M["fur_light"])
    legs = {s: build_leg(M, s) for s in (1, -1)}
    tail, tuft, tail_path = build_tail(M)

    for o, f in SDF_REG:
        sdf_normals(o, f)
    sdf_normals(shell, hp["hsdf"])

    r = build_rig(hp, knuckle)
    # ---- skinning
    for o in (head, shell, hp["nose"], hp["dots"], hp["whiskers"]):
        r.bind_rigid(o, "head")
    for tag in ("L", "R"):
        r.bind_rigid(hp["ears"][tag][0], f"ear_{tag}")
    waist = lambda co: {"hips": 1 - sstep(0.712, 0.785, co.z), "body": sstep(0.712, 0.785, co.z)}  # noqa
    r.bind_fn(torso, waist)
    r.bind_fn(neck, lambda co: {"neck": 1 - sstep(0.97, 1.04, co.z), "head": sstep(0.97, 1.04, co.z)})
    for o in (collar, ruffle):
        r.bind_rigid(o, "neck")
    for o in (skirt, apron, pocket, band, bow):
        r.bind_rigid(o, "hips")
    for o in (bib, straps):   # same waist blend as the bodice so hems stay tucked under the band
        r.bind_fn(o, waist)
    for s, tag in ((1, "L"), (-1, "R")):
        r.bind_rigid(sleeves[s], f"upperarm_{tag}")
        r.bind_chain(arms[s], [(f"upperarm_{tag}", B(*mx(ARM_S, s))), (f"forearm_{tag}", B(*mx(ARM_E, s))),
                               (f"hand_{tag}", B(*mx(ARM_W, s)))], blend=0.035)
        r.bind_chain(legs[s], [(f"thigh_{tag}", B(*mx(LEG_H, s))), (f"shin_{tag}", B(*mx(LEG_K, s))),
                               (f"foot_{tag}", B(*mx(LEG_A, s)))], blend=0.035)
    r.bind_rigid(finger, "finger_R")
    tj = [B(*p) for p in TAIL_J]
    r.bind_chain(tail, [("tail_1", tj[0]), ("tail_2", tj[1]), ("tail_3", tj[2])], blend=0.045)
    r.bind_rigid(tuft, "tail_3")

    build_actions(r)
    stride = measure_stride(r)
    a_dir = paw_frame(-1)[0]
    c = math.radians(FINGER_CURL)
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    report_poses(r, {"finger_R": knuckle + (Rz @ a_dir) * FINGER_LEN,
                     "hand_R": np.array(mx(PAW_C, -1)), "hand_L": np.array(mx(PAW_C, 1)),
                     "forearm_L": np.array(mx(ARM_E, 1)), "forearm_R": np.array(mx(ARM_E, -1))},
                 [("point", 0.0), ("point", 0.20), ("point", 0.42), ("point", 0.53), ("point", 0.9),
                  ("akimbo", 0.35)])

    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
    verts = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == 'MESH')
    hb = [o for o in bpy.data.objects if o.type == 'MESH']
    print("[lioness] tris", sorted(((sum(len(p.vertices) - 2 for p in o.data.polygons), o.name) for o in hb), reverse=True)[:8])
    zmax = max(max((o.matrix_world @ v.co).z for v in o.data.vertices) for o in hb)
    cy = HC[1]
    meta = {
        "height_m": round(zmax, 3),
        "triangles": tris,
        "vertices": verts,
        "decal": {"center": list(HC), "half_size": S_DECAL,
                  "nose_top_v": round(0.5 + (hp["nose_top_y"] - cy) / (2 * S_DECAL), 3),
                  "ear_inner_u": round(0.5 + min(hp["ears"]["L_minx"], hp["ears"]["R_minx"]) / (2 * S_DECAL), 3)},
        "walk_stride_per_cycle_m": stride,
        "actions": {a.name: round((a.frame_range[1] - a.frame_range[0]) / 60.0, 3) for a in bpy.data.actions},
    }
    print("[lioness]", meta)
    return meta


# ============================================================================ rig
def build_rig(hp, knuckle):
    r = rigmod.Rig("lioness_rig")
    r.bone("root", B(0, 0, 0))
    r.bone("hips", B(0, 0.50, 0), "root")
    r.bone("body", B(0, Y_WAIST, 0), "hips")
    r.bone("neck", B(0, 0.955, -0.005), "body")
    r.bone("head", B(0, 1.035, 0.0), "neck")
    for tag in ("L", "R"):
        r.bone(f"ear_{tag}", V(hp["ears"][tag][1]), "head")
    for s, tag in ((1, "L"), (-1, "R")):
        r.bone(f"upperarm_{tag}", B(*mx(ARM_S, s)), "body")
        r.bone(f"forearm_{tag}", B(*mx(ARM_E, s)), f"upperarm_{tag}")
        r.bone(f"hand_{tag}", B(*mx(ARM_W, s)), f"forearm_{tag}")
    r.bone("finger_R", B(*knuckle), "hand_R")
    for s, tag in ((1, "L"), (-1, "R")):
        r.bone(f"thigh_{tag}", B(*mx(LEG_H, s)), "hips")
        r.bone(f"shin_{tag}", B(*mx(LEG_K, s)), f"thigh_{tag}")
        r.bone(f"foot_{tag}", B(*mx(LEG_A, s)), f"shin_{tag}")
    r.bone("tail_1", B(*TAIL_J[0]), "hips")
    r.bone("tail_2", B(*TAIL_J[1]), "tail_1")
    r.bone("tail_3", B(*TAIL_J[2]), "tail_2")
    r.build()
    return r


# ============================================================================ actions
def pspline(ctrl, T):
    """Periodic cubic Hermite spline through (t, v) keys; tangents are Catmull-Rom except at local
    extrema (zero slope -> ease in/out).  Returns f(t)."""
    ctrl = sorted(ctrl, key=lambda kv: kv[0])
    ts = np.array([c[0] % T for c in ctrl], float)
    order = np.argsort(ts)
    ts = ts[order]
    vs = np.array([float(ctrl[i][1]) for i in order])
    if len(ts) == 1:
        return lambda t: vs[0]
    et = np.concatenate([ts - T, ts, ts + T, ts + 2 * T])
    ev = np.concatenate([vs, vs, vs, vs])
    m = np.zeros_like(ev)
    for j in range(1, len(et) - 1):
        if (ev[j] - ev[j - 1]) * (ev[j + 1] - ev[j]) > 0:
            m[j] = (ev[j + 1] - ev[j - 1]) / (et[j + 1] - et[j - 1])

    def f(t):
        t = t % T
        j = int(np.searchsorted(et, t, side='right') - 1)
        h = et[j + 1] - et[j]
        s = (t - et[j]) / h
        return ((2 * s ** 3 - 3 * s ** 2 + 1) * ev[j] + (s ** 3 - 2 * s ** 2 + s) * h * m[j]
                + (-2 * s ** 3 + 3 * s ** 2) * ev[j + 1] + (s ** 3 - s ** 2) * h * m[j + 1])
    return f


def sh(ctrl, dt, scale=1.0):
    return [(t + dt, v * scale) for t, v in ctrl]


def loop_action(r, name, T, tracks, fps=60):
    """tracks = {bone: {'rx': ctrl, 'ry': ..., 'rz': ..., 'lx': ..., 'ly': ..., 'lz': ...}};
    sampled every frame from periodic splines -> seamless loops with continuous velocity."""
    fs = {b: {c: pspline(k, T) for c, k in ch.items()} for b, ch in tracks.items()}
    a = r.action(name)
    n = int(round(T * fps))
    for i in range(n + 1):
        t = (i % n) / fps
        rot, loc = {}, {}
        for b, ch in fs.items():
            if any(c in ch for c in ("rx", "ry", "rz")):
                rot[b] = tuple(float(ch[c](t)) if c in ch else 0.0 for c in ("rx", "ry", "rz"))
            if any(c in ch for c in ("lx", "ly", "lz")):
                loc[b] = tuple(float(ch[c](t)) if c in ch else 0.0 for c in ("lx", "ly", "lz"))
        a.key(i / fps, rot=rot, loc=loc)
    a.done()


def shot_action(r, name, keys, interp='BEZIER'):
    """keys = [(t, {bone: (rx, ry, rz)}, {bone: (x, y, z)}), ...]"""
    a = r.action(name)
    for k in keys:
        t, rot = k[0], k[1]
        loc = k[2] if len(k) > 2 else None
        a.key(t, rot=rot, loc=loc, interp=interp)
    a.done()


# walk: key poses per step + foot-locked IK legs (items/lioness_walk.py).  The planted foot moves
# back WALK_STRIDE metres per cycle (1.0 s, 2 steps); the director's distance-driven phase should use the
# same stride (meta "walk_stride_per_cycle_m") so the feet do not slide.
WALK_STRIDE = 0.66


def build_actions(r):
    # ---------------------------------------------------------------- walk (1.0 s, 2 steps, in place)
    from items.lioness_walk import build_walk
    build_walk(r, LEG_H, LEG_K, LEG_A, FOOT_C, FOOT_R, WALK_STRIDE)

    # ---------------------------------------------------------------- stand (2.0 s loop)
    stand = {
        "body": {"rx": [(0.0, 0.0), (0.95, 1.3), (1.55, 0.4)], "ly": [(0.0, 0.0), (0.95, 0.004), (1.55, 0.0012)]},
        "neck": {"rx": [(0.1, 0.0), (1.05, -0.8), (1.65, -0.25)]},
        "head": {"rz": [(0.0, 0.6), (0.7, 1.9), (1.4, -0.4)], "rx": [(0.2, 0.0), (0.9, -1.2), (1.5, 0.7)]},
        "upperarm_L": {"rz": [(0.05, 0.0), (1.0, 1.4)], "rx": [(0.3, 0.0), (1.3, -1.6)]},
        "upperarm_R": {"rz": [(0.05, 0.0), (1.0, -1.4)], "rx": [(0.4, 0.0), (1.4, -1.4)]},
        "tail_1": {"ry": [(0.0, 7.0), (0.85, -7.0)], "rx": [(0.5, 2.0), (1.5, -2.5)]},
        "tail_2": {"ry": [(0.22, 11.0), (1.07, -11.0)], "rx": [(0.7, 3.0), (1.7, -3.0)]},
        "tail_3": {"ry": [(0.45, 16.0), (1.30, -16.0)], "rx": [(0.9, 5.0), (1.9, -4.0)]},
        "ear_L": {"rz": [(0.0, 0.0), (1.16, 0.0), (1.22, -16.0), (1.29, 6.0), (1.37, -3.0), (1.47, 0.6), (1.6, 0.0)],
                  "rx": [(0.0, 0.0), (1.16, 0.0), (1.22, -10.0), (1.31, 3.0), (1.42, -0.8), (1.55, 0.0)]},
    }
    loop_action(r, "stand", 2.0, stand)

    # ---------------------------------------------------------------- listen (0.6 s)
    lk = [(0.00, (0, 0, 0)), (0.07, (-24, 7, -8)), (0.16, (12, -3, 3)), (0.25, (-10, 2, -4)),
          (0.34, (5, -0.5, 1.5)), (0.44, (-2, 0, -0.5)), (0.60, (0, 0, 0))]
    a = r.action("listen")
    for t, (x, y, z) in lk:
        a.key(t, rot={"ear_L": (x, y, z)})
        a.key(min(0.6, t + (0.02 if 0 < t < 0.6 else 0.0)), rot={"ear_R": (x * 0.95, -y, -z)})
    a.done()

    # ---------------------------------------------------------------- brace (0.35 s -> hold) / upright (0.3 s)
    brace_peak = {"hips": (4, 0, 0), "body": (19, 0, 0), "neck": (-7, 0, 0), "head": (-8, 0, 0),
                  "upperarm_L": (-82, 0, 15), "upperarm_R": (-82, 0, -15),
                  "forearm_L": (-26, 0, 0), "forearm_R": (-26, 0, 0),
                  "hand_L": (-32, 0, 0), "hand_R": (-32, 0, 0),
                  "ear_L": (-22, 0, 0), "ear_R": (-22, 0, 0), "tail_1": (14, 0, 0)}
    brace_hold = {"hips": (3, 0, 0), "body": (15, 0, 0), "neck": (-5, 0, 0), "head": (-6, 0, 0),
                  "upperarm_L": (-72, 0, 12), "upperarm_R": (-72, 0, -12),
                  "forearm_L": (-20, 0, 0), "forearm_R": (-20, 0, 0),
                  "hand_L": (-26, 0, 0), "hand_R": (-26, 0, 0),
                  "ear_L": (-16, 0, 0), "ear_R": (-16, 0, 0), "tail_1": (10, 0, 0)}
    zero = {b: (0, 0, 0) for b in brace_hold}
    shot_action(r, "brace", [(0.0, zero), (0.17, brace_peak), (0.35, brace_hold)])
    up_over = {"hips": (-0.5, 0, 0), "body": (-3, 0, 0), "neck": (1, 0, 0), "head": (1.5, 0, 0),
               "upperarm_L": (5, 0, 2), "upperarm_R": (5, 0, -2), "forearm_L": (-4, 0, 0), "forearm_R": (-4, 0, 0),
               "hand_L": (3, 0, 0), "hand_R": (3, 0, 0), "ear_L": (5, 0, 0), "ear_R": (5, 0, 0), "tail_1": (-3, 0, 0)}
    shot_action(r, "upright", [(0.0, brace_hold), (0.18, up_over), (0.30, zero)])

    # ---------------------------------------------------------------- akimbo (0.35 s -> hold): LEFT paw on hip
    ak_hold = {"upperarm_L": AKIMBO["upperarm_L"], "forearm_L": AKIMBO["forearm_L"], "hand_L": AKIMBO["hand_L"],
               "hips": (0, 0, 2.5)}
    ak_peak = {"upperarm_L": tuple(v * 1.07 for v in AKIMBO["upperarm_L"]),
               "forearm_L": tuple(v * 1.05 for v in AKIMBO["forearm_L"]),
               "hand_L": AKIMBO["hand_L"], "hips": (0, 0, 3.0)}
    ak_zero = {b: (0, 0, 0) for b in ak_hold}
    shot_action(r, "akimbo", [(0.0, ak_zero, {"hips": (0, 0, 0)}), (0.21, ak_peak, {"hips": (0.017, 0, 0)}),
                              (0.35, ak_hold, {"hips": (0.014, 0, 0)})])

    # ---------------------------------------------------------------- point (0.9 s): RIGHT arm, two jabs
    ua = lambda x: (x + 7, 6, -2)   # noqa: E731  (aim ~shoulder height, slightly down toward a seated Tim)
    pk = [
        (0.00, {"upperarm_R": (0, 0, 0), "forearm_R": (0, 0, 0), "hand_R": (0, 0, 0), "finger_R": (0, 0, 0), "head": (0, 0, 0)}),
        (0.12, {"upperarm_R": (-52, 4, -8), "forearm_R": (-32, 0, 0), "hand_R": (-6, 25, 0), "finger_R": (0, 0, -40)}),
        (0.20, {"upperarm_R": ua(-97), "forearm_R": (-20, 0, 0), "hand_R": (-10, 55, 0), "finger_R": (0, 0, -FINGER_CURL)}),
        (0.25, {"head": (7, 0, 0)}),
        (0.27, {"upperarm_R": ua(-87), "forearm_R": (-6, 0, 0), "hand_R": (-6, 55, 0)}),
        (0.34, {"upperarm_R": ua(-82), "forearm_R": (-34, 0, 0), "hand_R": (6, 55, 0), "head": (6, 0, 0)}),
        (0.42, {"upperarm_R": ua(-91), "forearm_R": (2, 0, 0), "hand_R": (-12, 55, 0), "head": (10, 0, 0)}),
        (0.53, {"upperarm_R": ua(-83), "forearm_R": (-26, 0, 0), "hand_R": (4, 55, 0), "head": (7, 0, 0)}),
        (0.58, {"upperarm_R": ua(-82), "forearm_R": (-32, 0, 0), "hand_R": (6, 55, 0)}),
        (0.66, {"upperarm_R": ua(-91), "forearm_R": (2, 0, 0), "hand_R": (-12, 55, 0), "head": (10, 0, 0)}),
        (0.78, {"upperarm_R": ua(-86), "forearm_R": (-9, 0, 0), "hand_R": (-4, 55, 0), "head": (7.5, 0, 0)}),
        (0.90, {"upperarm_R": ua(-87), "forearm_R": (-7, 0, 0), "hand_R": (-5, 55, 0), "finger_R": (0, 0, -FINGER_CURL),
                "head": (7, 0, 0)}),
    ]
    shot_action(r, "point", pk)


AKIMBO = {"upperarm_L": (12, -4, 52), "forearm_L": (-6, 0, -108), "hand_L": (0, 0, -18)}


def report_poses(r, pts, samples):
    """Print where rest-pose points (three.js) bound to a bone end up in posed frames."""
    arm = r.obj
    sc = bpy.context.scene
    for act_name, t in samples:
        arm.animation_data.action = bpy.data.actions[act_name]
        sc.frame_set(int(round(t * 60)))
        out = {}
        for bone, p in pts.items():
            pb = arm.pose.bones[bone]
            D = arm.matrix_world @ pb.matrix @ pb.bone.matrix_local.inverted()
            q = D @ V(t2b(p))
            out[bone] = tuple(round(v, 3) for v in b2t(np.array(q[:])))
        print(f"[lioness] pose {act_name}@{t}:", out)
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    sc.frame_set(0)


def measure_stride(r):
    """Walk check: speed of the planted left foot while it is flat (phase 0.13 .. 0.25) -> metres per
    cycle (should equal WALK_STRIDE), and its drift from a straight constant-speed line (foot slide)."""
    arm = r.obj
    act = bpy.data.actions["walk"]
    arm.animation_data.action = act
    sc = bpy.context.scene
    zs, ys = [], []
    for i in range(61):
        sc.frame_set(i)
        pb = arm.pose.bones["foot_L"]
        p = arm.matrix_world @ pb.head
        zs.append(-p.y)   # three.js z (front)
        ys.append(p.z)
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    sc.frame_set(0)
    f = np.arange(8, 16)
    z = np.array(zs)[f]
    k, c = np.polyfit(f / 60.0, z, 1)
    slide = float(np.max(np.abs(z - (k * f / 60.0 + c))))
    print("[lioness] foot_L ankle z(t)", [round(v, 3) for v in zs[::6]], "y(t)", [round(v, 3) for v in ys[::6]],
          f"flat-foot stride {-k:.3f} m/cycle (target {WALK_STRIDE}), max slide {slide * 1000:.1f} mm")
    return round(-k, 3)
