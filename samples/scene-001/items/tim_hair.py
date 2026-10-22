"""Tim's hair H3, the textured crop (helper for items/tim.py).

One sculpted shell over the scalp, designed rather than lumpy:
  * the hairline is the H3 curve (high near-straight fringe, soft M at the temples, sideburns, the line
    over the ears, nape) and every clump ends in a soft pointed tip past it, so the edge is broken into
    clumps instead of a flat ledge;
  * the shell is split into clumps by grooves that start at the crown and deepen toward the tips; each
    clump has a rounded cross-section (a ridge), so the silhouette is gently scalloped;
  * volume sits on top; the sides and the back are short and tight and thin out to the edge (no bowl);
  * a few loose locks lie over the shell (fringe pieces, crown flicks) for depth;
  * strand grain comes from a normal map along the flow (crown -> tips).
All positions are three.js coordinates (x = Tim's left, y = up, z = front); the head centre is T.HC.
"""
import math

import numpy as np


def _T():
    from items import tim as T
    return T


def wrapdeg(phd):
    return (np.asarray(phd, float) + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------------------------------------
# clumps: boundaries (deg, 0 = front, + = Tim's left) going round the head.  Each clump owns the arc
# between two boundaries; its tip drop (m, below the base hairline) and groove depth are listed per clump.
_LEFT_BOUNDS = [30.5, 41.0, 51.0, 61.0, 71.0, 80.0, 89.0, 99.0, 110.0, 123.0, 137.0, 151.0, 165.0]
# per clump on the left, in order: (30.5..41), (41..51), ... (151..165).  Only the temple clumps keep a
# (tiny) tip; the sides and the back end on a smooth, soft hairline.
_LEFT_DROP = [0.004, 0.003, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
_LEFT_DEP = [0.60, 0.50, 0.40, 0.34, 0.30, 0.26, 0.24, 0.24, 0.22, 0.20, 0.20, 0.20]
# fringe: (centre deg, half-width deg, tip drop m, groove depth, tip skew) - deliberately irregular
FRINGE = [(-27.0, 3.6, 0.007, 0.70, -0.25), (-19.6, 4.2, 0.016, 0.78, -0.30), (-9.6, 6.0, 0.011, 0.80, -0.10),
          (1.2, 5.0, 0.020, 0.82, 0.15), (10.2, 4.0, 0.009, 0.80, 0.25), (19.6, 5.6, 0.017, 0.78, 0.30),
          (28.0, 3.0, 0.006, 0.70, 0.20)]

# H3 hairline (y above the head centre by |azimuth|): high near-straight fringe, soft M at the temples,
# short sideburns, well up over and behind the ears, then down to a tapered nape.
HAIRLINE_KEYS = [(0, 0.220), (14, 0.220), (24, 0.218), (30, 0.214), (34, 0.216), (39, 0.234), (44, 0.255),
                 (50, 0.262), (55, 0.250), (60, 0.212), (65, 0.150), (71, 0.082), (76, 0.036), (80, 0.014),
                 (84, 0.020), (88, 0.040), (93, 0.056), (98, 0.054), (104, 0.036), (112, -0.004),
                 (122, -0.058), (135, -0.118), (150, -0.168), (166, -0.196), (180, -0.204)]


def _clumps(seed=7):
    """[(centre_deg, half_width_deg, drop_m, groove_depth)] around the full circle, slightly asymmetric."""
    rng = np.random.default_rng(seed)
    out = list(FRINGE)
    for side in (1.0, -1.0):
        b = np.array(_LEFT_BOUNDS)
        jit = rng.uniform(-1.4, 1.4, len(b))
        b = b + jit
        b[0] = 31.5
        for k in range(len(b) - 1):
            c = side * 0.5 * (b[k] + b[k + 1])
            hw = 0.5 * (b[k + 1] - b[k])
            drop = _LEFT_DROP[k] * float(rng.uniform(0.85, 1.15))
            skew = side * 0.30 if k < 2 else 0.0          # temple tips lean outward a little
            out.append((c, hw, drop, _LEFT_DEP[k], skew))
    # nape centre clump
    out.append((180.0, 15.0, 0.0, 0.20, 0.0))
    return out


CLUMPS = _clumps()
_CC = np.array([c[0] for c in CLUMPS])
_CW = np.array([c[1] for c in CLUMPS])
_CD = np.array([c[2] for c in CLUMPS])
_CG = np.array([c[3] for c in CLUMPS])
_CS = np.array([c[4] for c in CLUMPS])


def clump_coord(phd):
    """(index of the owning clump, u in [-1, 1] across it) for azimuths phd (deg)."""
    phd = np.asarray(phd, float)
    d = wrapdeg(phd[..., None] - _CC[None, :]) / _CW[None, :]
    k = np.argmin(np.abs(d), axis=-1)
    u = np.take_along_axis(d, k[..., None], axis=-1)[..., 0]
    return k, np.clip(u, -1.0, 1.0)


def tip_profile(u, skew=0.0):
    """1 at the clump's tip, 0 at its boundaries: clumps taper to soft points (concave flanks, a rounded
    tip), and the notch between two clumps is a wide rounded valley.  skew moves the tip off-centre."""
    u = np.asarray(u, float)
    skew = np.asarray(skew, float)
    u = np.where(u < skew, (u - skew) / (1.0 + skew), (u - skew) / (1.0 - skew))
    au = np.sqrt(u ** 2 + 0.32 ** 2) - 0.32
    v = np.clip(1.0 - au / (math.sqrt(1.0 + 0.32 ** 2) - 0.32), 0.0, 1.0)
    return v ** 1.15


def edge_drop(phd):
    k, u = clump_coord(phd)
    return _CD[k] * tip_profile(u, _CS[k])


def edge_y(phd):
    """Hair edge height above the head centre (tips included)."""
    return CV_HL()(np.abs(wrapdeg(phd))) - edge_drop(phd)


_HL = None


def CV_HL():
    global _HL
    if _HL is None:
        _HL = _T().Curve(HAIRLINE_KEYS)
    return _HL


# ---------------------------------------------------------------------------------------------
# thickness
def _curves():
    T = _T()
    C = T.Curve
    return dict(
        parting=C([(0, 0.08), (22, 0.08), (40, 0.14), (58, 0.215), (75, 0.255), (100, 0.265), (140, 0.235),
                   (180, 0.215)]),
        top=C([(0, 0.040), (60, 0.036), (100, 0.030), (140, 0.024), (180, 0.022)]),
        thin=C([(0, 0.010), (60, 0.009), (90, 0.0075), (130, 0.0065), (180, 0.0065)]),
        lip=C([(0, 0.0125), (24, 0.0125), (34, 0.010), (44, 0.0060), (60, 0.0028), (100, 0.0020),
               (180, 0.0018)]),
    )


CV = None
HAIR_TOP = 0.040
HAIR_IN = 0.004
SWIRL = 14.0          # deg: clump lines curl a little round the crown


def thickness(phd, s, y_rel):
    """Shell thickness over the skin point at azimuth phd (deg), crown->edge parameter s, height y_rel."""
    T = _T()
    global CV
    if CV is None:
        CV = _curves()
    phd = np.asarray(phd, float)
    s = np.asarray(s, float)
    a = np.abs(wrapdeg(phd))
    w_front = 1.0 - T.sstep(24.0, 50.0, a)
    k, u = clump_coord(phd + SWIRL * (1.0 - s) ** 2 * np.sign(wrapdeg(phd) + 1e-9))
    tipf = tip_profile(u, _CS[k])
    te = CV["lip"](a) * (1.0 - 0.45 * tipf)
    yp = CV["parting"](a)
    thin = CV["thin"](a)
    core = thin + (CV["top"](a) - thin) * T.sstep(yp - 0.08, yp + 0.07, y_rel)
    # front: the volume rolls down into the fringe; elsewhere it thins out over the last stretch
    e = w_front * s ** 3.0 + (1.0 - w_front) * T.sstep(0.62, 1.0, s)
    t = core * (1.0 - e) + te * e
    # clump ridges / grooves
    dep = _CG[k] * T.sstep(0.18, 0.85, s) * (0.55 + 0.45 * T.sstep(0.0, 0.5, s))
    ridge = np.sqrt(np.clip(1.0 - u * u, 0.0, 1.0))
    t = t * (1.0 - dep * (1.0 - ridge))
    # sides / back: the shell feathers out over the last couple of centimetres (a taper, not a ledge)
    w_sb = T.sstep(40.0, 60.0, a)
    t = t * (1.0 - 0.6 * w_sb * T.sstep(0.93, 1.0, s))
    return np.maximum(t, 0.0022 - 0.0010 * w_sb)


def build_shell(hair_m, cols=208, k_u=6):
    T = _T()
    u = np.linspace(-np.pi, np.pi, cols, endpoint=False)
    phi = u - 0.40 * np.sin(u)                       # denser columns across the fringe
    phd = np.degrees(phi)
    th_h = T.solve_theta(phi, edge_y(phd))
    s_out = np.concatenate([np.linspace(0.0, 0.86, 25), np.linspace(0.89, 1.0, 5)])
    rows, vtex = [], []
    for s in s_out:
        p, n = T.skin(s * th_h, phi)
        rows.append(p + n * thickness(phd, np.full_like(phd, s), p[:, 1] - T.HC[1])[:, None])
        vtex.append(s)
    # rounded lip from the outer edge down under the skin line
    H, n1 = T.skin(th_h, phi)
    H0, _ = T.skin(th_h * 0.985, phi)
    m = T._n(H - H0)
    m = T._n(m - n1 * np.sum(m * n1, axis=1, keepdims=True))
    te = thickness(phd, np.ones_like(phd), H[:, 1] - T.HC[1])
    c, h = (te - HAIR_IN) * 0.5, (te + HAIR_IN) * 0.5
    w = 0.30 * h + 0.0008
    K = 5
    for j in range(1, K + 1):
        al = np.pi * j / (K + 1)
        cs = np.sign(np.cos(al)) * abs(np.cos(al)) ** 0.75
        sn = abs(np.sin(al)) ** 0.75
        rows.append(H + n1 * (c + h * cs)[:, None] + m * (w * sn)[:, None])
        vtex.append(1.0 + 0.02 * j)
    for s in (1.0, 0.5, 0.0):
        p, n = T.skin(s * th_h, phi)
        rows.append(p - n * HAIR_IN)
        vtex.append(1.2 + 0.1 * (1 - s))
    P = np.array(rows)
    ut = (np.concatenate([phi, [np.pi]]) + np.pi) / (2 * np.pi) * k_u
    UV = np.zeros((len(rows), cols + 1, 2))
    UV[..., 0] = ut[None, :]
    UV[..., 1] = np.array(vtex)[:, None]
    return T.Grid(P, pole0=True, pole1=True, uv=UV)


def shell_outer(phd, s):
    """Outer shell point (three.js) at azimuth phd (deg) and parameter s (edge = 1)."""
    T = _T()
    phi = np.radians(np.asarray(phd, float))
    th_h = T.solve_theta(phi, edge_y(phd))
    p, n = T.skin(np.asarray(s, float) * th_h, phi)
    t = thickness(phd, s, p[..., 1] - T.HC[1])
    return p + n * t[..., None], n


# ---------------------------------------------------------------------------------------------
# loose locks lying over the shell: tapered leaf-shaped clumps with a rounded back
LOCKS = [
    # (phd at root, s root, phd at tip, s tip, width m, height m, lift m)
    # fringe pieces, layered over the shell's own fringe clumps, slightly off-beat
    # fringe piece layered over the shell's centre clump (ends on the clump, no needle tip past it)
    (2.0, 0.50, 0.0, 0.93, 0.040, 0.0075, 0.0030),
    (-23.0, 0.58, -24.5, 0.92, 0.030, 0.0060, 0.0024),
    # crown / top flicks, so the top is not one smooth dome
    (-35.0, 0.08, -18.0, 0.62, 0.050, 0.0100, 0.0040),
    (25.0, 0.10, 10.0, 0.64, 0.046, 0.0095, 0.0040),
    (150.0, 0.06, 115.0, 0.50, 0.040, 0.0080, 0.0030),
    (-160.0, 0.06, -128.0, 0.52, 0.040, 0.0080, 0.0030),
    (80.0, 0.20, 62.0, 0.66, 0.040, 0.0080, 0.0030),
    (-85.0, 0.22, -66.0, 0.66, 0.040, 0.0080, 0.0030),
    # temple pieces sweeping into the M
    (48.0, 0.45, 40.0, 0.98, 0.022, 0.0050, 0.0018),
    (-47.0, 0.45, -39.0, 0.98, 0.022, 0.0050, 0.0018),
]


def _back_locks(seed=23):
    """Two staggered rows of clumps over the back and the sides, falling toward the nape, so the back
    reads as layered short hair instead of one smooth bowl."""
    rng = np.random.default_rng(seed)
    out = []
    for row, (s0, s1, W, Hh, n, ph0, ph1) in enumerate((
            (0.08, 0.40, 0.056, 0.0080, 7, 104.0, 256.0),
            (0.34, 0.62, 0.048, 0.0064, 8, 96.0, 264.0),
            (0.56, 0.84, 0.042, 0.0050, 7, 108.0, 252.0),
            (0.30, 0.70, 0.040, 0.0055, 4, 58.0, 84.0))):
        for i in range(n):
            if row == 3:
                c = (ph0 + (ph1 - ph0) * (i % 2)) * (1 if i < 2 else -1)
            else:
                c = ph0 + (ph1 - ph0) * (i + 0.5 * (row == 1)) / (n - (0 if row == 1 else 1))
            c = float(wrapdeg(c + rng.uniform(-5.0, 5.0)))
            # curl a little toward the centre line of the back
            curl = -np.sign(wrapdeg(c)) * rng.uniform(1.0, 6.0) if abs(wrapdeg(c)) > 100 else rng.uniform(-3, 3)
            a0 = s0 + rng.uniform(-0.05, 0.05)
            a1 = a0 + (s1 - s0) * rng.uniform(0.6, 1.1)
            out.append((c, a0, c + curl, a1, W * rng.uniform(0.75, 1.2), 0.7 * Hh * rng.uniform(0.75, 1.15), 0.0,
                        0.45))
    return out


LOCKS = LOCKS + _back_locks()


def lock_grid(phd0, s0, phd1, s1, W, Hh, lift, root=0.22, nl=15, nc=9):
    T = _T()
    uu = np.linspace(0.0, 1.0, nl)
    ease = uu * uu * (3 - 2 * uu)
    phd = phd0 + (phd1 - phd0) * (0.35 * uu + 0.65 * ease)
    s = s0 + (s1 - s0) * uu
    # along the surface: the shell (inside the hair) or, past the edge, the skin
    s_in = np.minimum(s, 1.0)
    base, n = shell_outer(phd, s_in)
    if np.any(s > 1.0):
        phi = np.radians(phd)
        th_h = T.solve_theta(phi, edge_y(phd))
        p2, n2 = T.skin(s * th_h, phi)
        over = s > 1.0
        te = thickness(phd, np.ones_like(phd), p2[:, 1] - T.HC[1])
        p2 = p2 + n2 * (te * 0.6)[:, None]
        base = np.where(over[:, None], p2, base)
        n = np.where(over[:, None], n2, n)
    Tg = T._n(np.gradient(base, axis=0))
    Wd = T._n(np.cross(n, Tg))
    # profiles: a rounded root, the widest part at ~30 %, a soft point
    wprof = np.sin(np.clip(uu / root, 0, 1) * np.pi / 2) ** (0.6 if root < 0.3 else 1.4) * (1.0 - T.sstep(0.30, 1.0, uu) * 0.94)
    hprof = np.sin(np.clip(uu / (root * 0.82), 0, 1) * np.pi / 2) ** (0.7 if root < 0.3 else 1.5) * (1.0 - T.sstep(0.25, 1.0, uu) * 0.85)
    lprof = lift * np.sin(np.pi * np.clip(uu, 0, 1)) ** 0.8 + 0.0006
    g = np.linspace(0.0, 2 * np.pi, nc, endpoint=False)
    cg, sg = np.cos(g), np.sin(g)
    sq = np.sign(cg) * np.abs(cg) ** 0.8
    top = np.where(sg > 0, np.abs(sg) ** 0.65, -0.55 * np.abs(sg))
    rows = []
    for i in range(nl):
        ctr = base[i] + n[i] * (lprof[i] + 0.10 * Hh * hprof[i] - 0.0012)
        ring = (ctr[None, :] + (0.5 * W * wprof[i]) * sq[:, None] * Wd[i][None, :]
                + (Hh * hprof[i]) * top[:, None] * n[i][None, :])
        rows.append(ring)
    tip = base[-1] + n[-1] * (lprof[-1] + 0.0008) + Tg[-1] * 0.002
    root = base[0] - Tg[0] * 0.004 + n[0] * 0.001
    P = np.array([np.repeat(root[None], nc, 0)] + rows + [np.repeat(tip[None], nc, 0)])
    UV = np.zeros((P.shape[0], nc + 1, 2))
    UV[..., 0] = (np.arange(nc + 1) / nc * 0.35)[None, :] + (phd0 % 60.0) / 60.0
    UV[..., 1] = np.concatenate([[s0 - 0.01], s, [s1 + 0.01]])[:, None]
    return T.Grid(P, pole0=True, pole1=True, uv=UV)


def build(hair_m, hair_hex="#2b241f", fade_hex="#7d6656"):
    T = _T()
    grids = [build_shell(hair_m)]
    for L in LOCKS:
        grids.append(lock_grid(*L))
    obj = T.grids_to_object("tim_hair", grids, mats=[hair_m])
    paint(obj, hair_hex, fade_hex)
    return obj


def paint(obj, hair_hex, fade_hex):
    """Vertex colour (the material base colour is white): the hair colour, darker down in the clump grooves
    (sculpted read even in flat light), lifting toward a warm mid-brown over the short sides and the nape
    (the taper / fade of a crop, so the back is not a hard-edged bowl)."""
    T = _T()
    from lib import mat as M
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    p = np.stack([co[:, 0], co[:, 2], -co[:, 1]], axis=1) - T.HC
    phi = np.arctan2(p[:, 0], p[:, 2])
    phd = np.degrees(phi)
    d = T._n(p)
    theta = np.arccos(np.clip(d[:, 1], -1, 1))
    ey = edge_y(phd)
    th_h = T.solve_theta(phi, ey)
    s = np.clip(theta / th_h, 0.0, 1.0)
    k, u = clump_coord(phd + SWIRL * (1.0 - s) ** 2 * np.sign(wrapdeg(phd) + 1e-9))
    dep = _CG[k] * T.sstep(0.18, 0.85, s)
    ridge = np.sqrt(np.clip(1.0 - u * u, 0.0, 1.0))
    ao = 1.0 - 0.75 * dep * (1.0 - ridge) ** 1.5
    # loose locks (standing above the shell) keep their own colour: no groove shading on them
    r_skin = T.head_radius_along(d)
    t_sh = thickness(phd, s, d[:, 1] * r_skin)
    above = np.linalg.norm(p, axis=1) - r_skin - t_sh
    ao = np.maximum(ao, 0.80 + 0.20 * T.sstep(0.0015, 0.005, above))
    a = np.abs(wrapdeg(phd))
    w_side = T.sstep(52.0, 78.0, a)
    f = T.sstep(0.0, 1.0, 1.0 - (p[:, 1] - ey) / (0.10 + 0.08 * T.sstep(100.0, 160.0, a)))
    amt = 0.50 * w_side * f ** 1.2
    h = np.array(M.hex_rgb(hair_hex))
    fc = np.array(M.hex_rgb(fade_hex))
    col = (h[None] * (1 - amt[:, None]) + fc[None] * amt[:, None]) * ao[:, None]
    # the last ~2 cm before the side / back edge: blend through a warm stubble tone to a skin-dark tone at
    # the very edge, so the hairline fades instead of cutting
    dy = p[:, 1] - ey
    w_e = T.sstep(42.0, 62.0, a)[:, None]
    stub = np.array(M.hex_rgb("#8e705e"))
    edge = np.array(M.hex_rgb("#c9a690"))
    g1 = T.sstep(0.024, 0.008, dy)[:, None]
    g2 = T.sstep(0.008, -0.001, dy)[:, None]
    tone = stub[None] * (1 - g2) + edge[None] * g2
    col = col * (1 - g1 * w_e) + tone * (g1 * w_e)
    attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    rgba = np.concatenate([col, np.ones((n, 1))], axis=1).astype(np.float32)
    attr.data.foreach_set("color", rgba.ravel())
    me.color_attributes.active_color = attr


# ---------------------------------------------------------------------------------------------
def normal_map(size=512, seed=11):
    """Strand grain along V (crown -> tips): several irregular groove families, fading at the crown pole."""
    T = _T()
    rng = np.random.default_rng(seed)
    xx = (np.arange(size)[None, :] + 0.5) / size
    yy = (np.arange(size)[:, None] + 0.5) / size
    h = np.zeros((size, size))
    for freq, amp in ((18, 0.55), (31, 0.40), (53, 0.20)):
        ph = rng.uniform(0, 2 * np.pi)
        wob = rng.uniform(0.01, 0.025)
        k2 = rng.integers(1, 3)
        h += amp * np.sin(2 * np.pi * (freq * (xx + wob * np.sin(2 * np.pi * (k2 * yy + rng.uniform())))) + ph)
    # d/du of the height field -> tangent-space normal (x only); strength fades toward the crown
    gx = np.gradient(h, axis=1) * size / (2 * np.pi * 60.0)
    v = 1.0 - yy
    gx = gx * T.sstep(0.04, 0.22, v) * 0.38
    L = np.sqrt(gx * gx + 1.0)
    out = np.stack([np.broadcast_to(gx / L, (size, size)) * 0.5 + 0.5, np.full((size, size), 0.5),
                    np.broadcast_to(1.0 / L, (size, size)) * 0.5 + 0.5], axis=2)
    return out.astype(np.float32)
