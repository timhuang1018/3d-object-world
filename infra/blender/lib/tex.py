"""Deterministic procedural textures (numpy).  Every function takes an explicit seed.
Arrays are HxWx3 float in [0,1], row 0 = top.  Wrap with mat.image_from_array()."""
import math
import numpy as np

from .mat import hex_srgb


def rgb(h):
    return np.array(hex_srgb(h), np.float32)


def value_noise(w, h, cells_x, cells_y, seed, octaves=1, persistence=0.5):
    """Tileable smooth value noise in [0,1]."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    cx, cy = cells_x, cells_y
    for _ in range(octaves):
        grid = rng.random((cy, cx)).astype(np.float32)
        ys = np.arange(h) / h * cy
        xs = np.arange(w) / w * cx
        y0 = np.floor(ys).astype(int); x0 = np.floor(xs).astype(int)
        fy = ys - y0; fx = xs - x0
        fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
        y1 = (y0 + 1) % cy; x1 = (x0 + 1) % cx
        y0 %= cy; x0 %= cx
        a = grid[np.ix_(y0, x0)]; b = grid[np.ix_(y0, x1)]
        c = grid[np.ix_(y1, x0)]; d = grid[np.ix_(y1, x1)]
        top = a + (b - a) * fx[None, :]
        bot = c + (d - c) * fx[None, :]
        out += amp * (top + (bot - top) * fy[:, None])
        total += amp
        amp *= persistence
        cx *= 2; cy *= 2
    return out / total


def wood_grain(base='#c9a47c', dark=None, size=512, seed=1, rings=9.0, streaks=40, contrast=0.16):
    """Tileable long-grain wood (grain runs along U / image X)."""
    h = w = size
    base_c = rgb(base)
    dark_c = rgb(dark) if dark else base_c * 0.72
    n1 = value_noise(w, h, 4, 16, seed, octaves=3)
    n2 = value_noise(w, h, 2, 64, seed + 7, octaves=2)
    y = np.arange(h)[:, None] / h
    grain = np.sin((y * rings + n1 * 1.6) * 2 * math.pi) * 0.5 + 0.5
    grain = grain ** 3
    fine = (n2 - 0.5) * 0.6
    t = np.clip(grain * contrast * 3 + fine * contrast, 0, 1)
    img = base_c[None, None, :] * (1 - t[..., None]) + dark_c[None, None, :] * t[..., None]
    # subtle streaks
    s = value_noise(w, h, 1, streaks, seed + 3)[..., None]
    img *= (0.94 + 0.08 * s)
    return np.clip(img, 0, 1)


def dots_wallpaper(base='#efe5d1', dot_colors=('#d9ad9f', '#a9b897'), size=512, seed=2, grid=4,
                   radius=0.035, jitter=0.0):
    """Small flower-dot wallpaper on a half-drop grid (tileable)."""
    h = w = size
    img = np.ones((h, w, 3), np.float32) * rgb(base)[None, None, :]
    yy, xx = np.mgrid[0:h, 0:w] / size
    cell = 1.0 / grid
    k = 0
    for gy in range(grid):
        for gx in range(grid):
            for (ox, oy, ci) in ((0.25, 0.25, 0), (0.75, 0.75, 1)):
                cxp = (gx + ox) * cell
                cyp = (gy + oy) * cell
                col = rgb(dot_colors[(ci + gy) % len(dot_colors)])
                # 5-petal flower = centre + petals
                for p in range(6):
                    if p == 0:
                        px, py, rr = cxp, cyp, radius * cell * 0.55
                        cc = rgb('#f3e3b5') if len(dot_colors) > 1 else col
                    else:
                        a = 2 * math.pi * (p - 1) / 5 + 0.3
                        px = cxp + math.cos(a) * radius * cell * 0.9
                        py = cyp + math.sin(a) * radius * cell * 0.9
                        rr = radius * cell * 0.62
                        cc = col
                    dx = (xx - px + 0.5) % 1.0 - 0.5
                    dy = (yy - py + 0.5) % 1.0 - 0.5
                    d = np.sqrt(dx * dx + dy * dy)
                    a_ = np.clip((rr - d) * size * 1.5, 0, 1)[..., None]
                    img = img * (1 - a_) + cc[None, None, :] * a_
                k += 1
    return img


def gingham(base='#f7f1e6', check=(201, 139, 124), alpha=0.5, size=256, bands=8):
    """Gingham: horizontal + vertical translucent bands; overlaps darker."""
    h = w = size
    yy, xx = np.mgrid[0:h, 0:w] / size
    bx = ((xx * bands) % 1.0) < 0.5
    by = ((yy * bands) % 1.0) < 0.5
    c = np.array(check, np.float32) / 255.0
    base_c = rgb(base)
    a = (bx.astype(np.float32) + by.astype(np.float32)) * (alpha * 0.55)
    a = np.clip(a, 0, 0.9)[..., None]
    return base_c[None, None, :] * (1 - a) + c[None, None, :] * a


def checks(c1='#efdcb4', c2='#e4caa0', size=256, n=8, line=None, line_w=0.04):
    h = w = size
    yy, xx = np.mgrid[0:h, 0:w] / size
    m = ((np.floor(xx * n) + np.floor(yy * n)) % 2).astype(np.float32)[..., None]
    img = rgb(c1)[None, None, :] * (1 - m) + rgb(c2)[None, None, :] * m
    if line:
        fx = (xx * n) % 1.0
        fy = (yy * n) % 1.0
        l = ((fx < line_w) | (fy < line_w)).astype(np.float32)[..., None] * 0.6
        img = img * (1 - l) + rgb(line)[None, None, :] * l
    return img


def braided_rug(colors=('#d9b58f', '#c98f7a', '#b9c3a8', '#efe3cc'), size=1024, rings=11, seed=4):
    """Round braided rug, top view. Concentric braided coils; outside the disc = transparent."""
    h = w = size
    yy, xx = (np.mgrid[0:h, 0:w] + 0.5) / size * 2 - 1
    r = np.sqrt(xx * xx + yy * yy)
    th = np.arctan2(yy, xx)
    ring_f = r * rings
    ring_i = np.floor(ring_f)
    fr = ring_f - ring_i
    cols = np.array([hex_srgb(c) for c in colors], np.float32)
    ci = (ring_i.astype(int) * 3 + 1) % len(colors)
    base = cols[ci]
    # braid chevrons along the ring
    nb = np.maximum(6, np.floor(2 * math.pi * (ring_i + 0.5) / rings * size * 0.035)).astype(np.float32)
    ph = (th / (2 * math.pi) * nb + np.where(fr < 0.5, fr, 1 - fr) * 1.2) % 1.0
    shade = 0.82 + 0.18 * np.sin(ph * math.pi) * np.sin(fr * math.pi)
    groove = np.clip(np.sin(fr * math.pi) * 1.6, 0, 1) ** 0.6
    img = base * (shade * (0.75 + 0.25 * groove))[..., None]
    a = np.clip((1.0 - r) * size * 0.5, 0, 1)[..., None]
    return np.concatenate([img, a], axis=2)


def stripes_normal(size=512, freq=60, seed=5, strength=0.6, wobble=0.15):
    """Tangent-space normal map of fine grooves running along V (image Y) - hair strands."""
    h = w = size
    n = value_noise(w, h, 8, 4, seed, octaves=2)
    xx = np.arange(w)[None, :] / w
    phase = (xx * freq + n * freq * wobble) * 2 * math.pi
    dh = np.cos(phase) * strength  # derivative of sin
    nx = -dh
    ny = np.zeros_like(nx)
    nz = np.ones_like(nx)
    L = np.sqrt(nx * nx + ny * ny + nz * nz)
    out = np.stack([nx / L * 0.5 + 0.5, ny / L * 0.5 + 0.5, nz / L * 0.5 + 0.5], axis=2)
    return out.astype(np.float32)


def sky_window(size=512, seed=6):
    """Window view: soft sky gradient, two clouds, rolling green hills.  Wordless."""
    h = w = size
    yy, xx = np.mgrid[0:h, 0:w] / size
    top = rgb('#a9cbe6'); bot = rgb('#e6f0f2')
    img = top[None, None, :] * (1 - yy[..., None]) + bot[None, None, :] * yy[..., None]
    def blob(cx, cy, rx, ry):
        return np.clip(1 - ((xx - cx) / rx) ** 2 - ((yy - cy) / ry) ** 2, 0, 1)
    cloud = np.zeros((h, w), np.float32)
    for (cx, cy, rx, ry) in ((0.28, 0.22, 0.12, 0.05), (0.36, 0.2, 0.09, 0.06), (0.2, 0.24, 0.08, 0.04),
                             (0.72, 0.34, 0.1, 0.04), (0.79, 0.32, 0.07, 0.05)):
        cloud = np.maximum(cloud, blob(cx, cy, rx, ry))
    c = np.clip(cloud * 4, 0, 1)[..., None]
    img = img * (1 - c) + np.ones(3, np.float32)[None, None, :] * c
    hill1 = 0.70 + 0.06 * np.sin(xx * 5.0 + 0.5) + 0.03 * np.sin(xx * 11 + 1.0)
    hill2 = 0.80 + 0.05 * np.sin(xx * 3.5 + 2.0) + 0.02 * np.sin(xx * 9 + 0.3)
    m1 = np.clip((yy - hill1) * size * 0.8, 0, 1)[..., None]
    img = img * (1 - m1) + rgb('#b5cf9a')[None, None, :] * m1
    m2 = np.clip((yy - hill2) * size * 0.8, 0, 1)[..., None]
    img = img * (1 - m2) + rgb('#93b07c')[None, None, :] * m2
    return img
