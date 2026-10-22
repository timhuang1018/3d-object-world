"""Dish props for beats 3-4 (the engine instances these nodes).

Top-level nodes (laid out side by side along x for the preview; the engine re-parents them):
  plate_dirty  ceramic plate, d 0.222, 0.018 tall, brown smudges + crumbs.  Origin = bottom centre,
               lying flat (normal +y).  Stack pitch when nesting: >= 0.0085 m.
  plate_clean  the same plate, clean (whiter, glossy ceramic family).
  sponge       yellow sponge with a green scour pad on top (+y), 0.10 x 0.045 x 0.066 (x, y, z).
               Origin = its centre.
  suds_puff    a soft clump of many small merged foam bubbles, ~0.07 across.  Origin = bottom centre.
  suds_dab     a flatter foam clump (~0.055 across) that clings to a plate face.  Origin = bottom centre.
"""
import math

import bmesh
import numpy as np

from mathutils import Matrix

from lib.core import B, join, voxel_remesh, decimate
from lib import geo, mat, tex

ITEM = {"id": "props/dishes", "out": "props/dishes.glb"}
ANIMATIONS = False

PLATE_COLOR = "#f3eee4"
SMUDGE = "#9a6b4a"
UV_R = 0.113  # planar UV half size of the plate texture (m)

# Plate profile (radius, height), origin at the bottom centre.  Closed loop: underside centre ->
# foot ring -> underside -> lip -> top surface -> top centre.
PLATE_PROFILE = [
    (0.0, 0.0034), (0.0540, 0.0032), (0.0560, 0.0018), (0.0575, 0.0), (0.0615, 0.0), (0.0635, 0.0015),
    (0.0660, 0.0047), (0.0740, 0.0060), (0.0840, 0.0082), (0.0940, 0.0108), (0.1040, 0.0137),
    (0.1098, 0.0150), (0.1110, 0.0158), (0.1113, 0.0168), (0.1105, 0.0176), (0.1090, 0.0180),
    (0.1060, 0.0173), (0.1010, 0.0159), (0.0940, 0.0136), (0.0860, 0.0111), (0.0780, 0.0091),
    (0.0700, 0.0080), (0.0600, 0.0076), (0.0300, 0.0075), (0.0, 0.0075),
]


# ---- textures ------------------------------------------------------------------------------

def _mix(img, col, a):
    a = np.clip(a, 0, 1)[..., None]
    return img * (1 - a) + tex.rgb(col)[None, None, :] * a


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def plate_texture(dirty, size=512, seed=11, base=PLATE_COLOR):
    """Top view of the plate (planar UV, half size UV_R).  Wordless: a faint sage rim line,
    plus (dirty) brown sauce smudges and crumbs in the well."""
    h = w = size
    yy, xx = (np.mgrid[0:h, 0:w] + 0.5) / size * 2 - 1
    px, pz = xx * UV_R, yy * UV_R
    r = np.sqrt(px * px + pz * pz)
    img = np.ones((h, w, 3), np.float32) * tex.rgb(base)[None, None, :]
    # very soft glaze variation
    n0 = tex.value_noise(w, h, 6, 6, seed + 1, octaves=2)
    img *= (0.985 + 0.03 * n0)[..., None]
    # thin decorative rim line + a fainter inner one
    img = _mix(img, "#a9b897", np.clip(1 - np.abs(r - 0.0985) / 0.0011, 0, 1) * 0.6)
    img = _mix(img, "#a9b897", np.clip(1 - np.abs(r - 0.0950) / 0.0006, 0, 1) * 0.3)
    if not dirty:
        return np.clip(img, 0, 1)
    rng = np.random.default_rng(seed)
    noise = tex.value_noise(w, h, 10, 10, seed + 5, octaves=3)
    field = np.zeros((h, w), np.float32)
    # sauce: one off-centre smear (a curved chain of soft blobs), a thinner wipe streak and a small
    # drip - deliberately asymmetric (no accidental faces)
    chain = [(0.006, 0.040, 0.016, 0.011, 0.5, 1.0), (0.024, 0.030, 0.019, 0.012, 0.9, 1.1),
             (0.040, 0.012, 0.017, 0.011, 1.3, 1.0), (0.047, -0.010, 0.012, 0.009, 1.6, 0.9),
             (-0.040, -0.034, 0.0065, 0.005, 0.3, 0.75)]
    for (cx, cz, sx, sz, th, wgt) in chain:
        c, s = math.cos(th), math.sin(th)
        dx, dz = px - cx, pz - cz
        u = (dx * c + dz * s) / sx
        v = (-dx * s + dz * c) / sz
        field += np.exp(-(u * u + v * v)) * wgt
    ang = np.arctan2(pz, px)
    streak = np.exp(-((r - 0.062) / 0.0035) ** 2) * _smoothstep(-0.9, -0.5, ang) * _smoothstep(0.55, 0.2, ang)
    field += streak * 0.85
    f = field + (noise - 0.5) * 0.45
    a_out = _smoothstep(0.32, 0.52, f) * (r < 0.092)
    a_in = _smoothstep(0.75, 1.15, f) * (r < 0.092)
    img = _mix(img, SMUDGE, a_out * 0.82)
    img = _mix(img, "#6e4429", a_in * 0.62)
    # crumbs: small dots, darker toast and lighter bread
    for k in range(46):
        rr = 0.088 * math.sqrt(rng.uniform(0.02, 1.0))
        th = rng.uniform(0, 2 * math.pi)
        cx, cz = rr * math.cos(th), rr * math.sin(th)
        rad = rng.uniform(0.0006, 0.0017)
        d = np.sqrt((px - cx) ** 2 + (pz - cz) ** 2)
        a = np.clip((rad - d) / (UV_R * 2 / size) + 0.5, 0, 1)
        img = _mix(img, "#7a5236" if k % 3 else "#c49a6c", a * 0.9)
    return np.clip(img, 0, 1)


def sponge_texture(size=256, seed=21):
    h = w = size
    rng = np.random.default_rng(seed)
    n = tex.value_noise(w, h, 16, 16, seed, octaves=3)
    img = np.ones((h, w, 3), np.float32) * tex.rgb("#f2d36b")[None, None, :]
    img *= (0.94 + 0.1 * n)[..., None]
    yy, xx = np.mgrid[0:h, 0:w]
    for _ in range(260):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        rad = rng.uniform(1.0, 3.2)
        dx = (xx - cx + w / 2) % w - w / 2
        dy = (yy - cy + h / 2) % h - h / 2
        a = np.clip(rad - np.sqrt(dx * dx + dy * dy) + 0.5, 0, 1)
        img = _mix(img, "#d4ad45", a * 0.75)
    return np.clip(img, 0, 1)


def scrubber_texture(size=256, seed=23):
    h = w = size
    n1 = tex.value_noise(w, h, 64, 64, seed, octaves=2)
    n2 = tex.value_noise(w, h, 32, 128, seed + 1, octaves=2)
    img = np.ones((h, w, 3), np.float32) * tex.rgb("#8fb07a")[None, None, :]
    img = _mix(img, "#6f8f5c", _smoothstep(0.55, 0.8, n1) * 0.8)
    img = _mix(img, "#b2cc9c", _smoothstep(0.6, 0.85, n2) * 0.6)
    return np.clip(img, 0, 1)


# ---- meshes --------------------------------------------------------------------------------

def plate(name, material, at):
    """Lathed plate lying flat, origin at its bottom centre (Blender local Z = three.js y)."""
    obj = geo.lathe(name, PLATE_PROFILE, segs=72, mat=material)
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        top = f.normal.z > 0.2
        for loop in f.loops:
            co = loop.vert.co
            if top:
                loop[uvl].uv = (0.5 + co.x / (2 * UV_R), 0.5 + co.y / (2 * UV_R))
            else:  # underside / lip -> a clean texel near the edge of the image
                loop[uvl].uv = (0.5 + 0.47, 0.5)
    bm.to_mesh(me)
    bm.free()
    obj.location = at
    return obj


def crumbs(name, material, seed=31):
    """A few tiny raised crumbs on the plate well (joined into plate_dirty)."""
    rng = np.random.default_rng(seed)
    parts = []
    for i in range(7):
        rr = 0.075 * math.sqrt(rng.uniform(0.05, 1.0))
        th = rng.uniform(0, 2 * math.pi)
        x, z = rr * math.cos(th), rr * math.sin(th)
        rad = rng.uniform(0.0028, 0.0048)
        top_y = 0.0075 if rr < 0.06 else 0.0080
        c = B(x, top_y + rad * 0.25, z)
        parts.append(geo.sphere(f"{name}_{i}", rad, center=c, segs=10, rings=6,
                                scale=(1.0, rng.uniform(0.7, 1.2), 0.55), rot=(0, 0, math.degrees(th)),
                                mat=material))
    return parts


def sponge(name, m_body, m_scrub, at):
    """Kitchen sponge, chunky enough to read at plate scale: a yellow pillowy body with a green scour pad
    on top (+y).  0.10 x 0.045 x 0.066 (x, y, z), origin = its centre."""
    body = geo.rounded_box(f"{name}_body", (0.10, 0.066, 0.032), 0.009, center=B(0, -0.0065, 0), segments=3,
                           mat=m_body)
    scrub = geo.rounded_box(f"{name}_scrub", (0.10, 0.066, 0.0125), 0.004, center=B(0, 0.0155, 0),
                            segments=2, mat=m_scrub)
    geo.box_uv(body, scale=6.0)
    geo.box_uv(scrub, scale=6.0)
    obj = join([body, scrub], name)
    obj.location = at
    return obj


def suds_puff(name, material, at, seed=5, n=34, size=0.034, height=0.018):
    """A soft clump of foam: many small bubbles merged into one lumpy, flat-topped mass (voxel union),
    ~2*size across.  Origin = bottom centre."""
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    for i in range(n):
        rr = size * math.sqrt(rng.uniform(0.0, 1.0))
        th = rng.uniform(0, 2 * math.pi)
        x, z = rr * math.cos(th), rr * math.sin(th)
        r = rng.uniform(0.0045, 0.0085) * (1.0 - 0.35 * rr / size)
        top = height * (1.0 - 0.55 * (rr / size) ** 2)
        y = rng.uniform(r * 0.6, max(r * 0.6, top - r * 0.8))
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=r,
                                  matrix=Matrix.Translation(B(x, y, z)))
    obj = geo._finish(name, bm, material)
    voxel_remesh(obj, voxel=0.0016, smooth_iters=1)
    decimate(obj, 0.5)
    # origin at the bottom centre
    me = obj.data
    zmin = min(v.co.z for v in me.vertices)
    for v in me.vertices:
        v.co.z -= zmin
    obj.location = at
    return obj


def build():
    m_dirty = mat.ceramic("plate_dirty", PLATE_COLOR,
                          image=mat.image_from_array("plate_dirty", plate_texture(True)))
    m_clean = mat.ceramic("plate_clean", "#f6f3ec",
                          image=mat.image_from_array("plate_clean", plate_texture(False, base="#f6f3ec")))
    m_crumb = mat.prop("crumb", "#b88a5c")
    m_sponge = mat.prop("sponge", "#f2d36b", image=mat.image_from_array("sponge", sponge_texture()))
    m_scrub = mat.fabric("scrubber", "#8fb07a", image=mat.image_from_array("scrubber", scrubber_texture()),
                         double_sided=False)
    m_suds = mat.material("foam", "#f6f7f4", roughness=0.88, sheen=0.35, sheen_roughness=0.5)

    pd = plate("plate_dirty", m_dirty, (0, 0, 0))
    pd = join([pd] + crumbs("crumb", m_crumb), "plate_dirty")
    pd.location = B(-0.15, 0, 0)
    plate("plate_clean", m_clean, B(0.10, 0, 0))
    sponge("sponge", m_sponge, m_scrub, B(0.30, 0.0225, 0))
    suds_puff("suds_puff", m_suds, B(0.43, 0, 0))
    suds_puff("suds_dab", m_suds, B(0.53, 0, 0), seed=9, n=22, size=0.028, height=0.011)
    return {
        "nodes": {
            "plate_dirty": "d 0.222, h 0.018, origin bottom centre, flat (normal +y)",
            "plate_clean": "same plate, clean",
            "sponge": "0.10 x 0.045 x 0.066 (x, y, z), scour pad on +y, origin centre",
            "suds_puff": "merged foam clump ~0.07 across, 0.018 tall, origin bottom centre",
            "suds_dab": "flatter foam clump ~0.055 across, 0.011 tall (clings to a plate face), origin bottom centre",
        },
        "plate_stack_pitch": 0.0085,
    }
