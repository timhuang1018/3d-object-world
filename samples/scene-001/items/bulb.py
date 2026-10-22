"""Idea bulb (props/bulb.glb).

A classic upright idea bulb: frosted pear-shaped glass on a threaded screw base, with a coiled
filament inside.  The engine (src/props/bulb.js) drives the level `b`: glass colour, emissive,
glow sprite, rays, flicker, the droop when it goes out, and the smoke.

Nodes: bulb (root, origin = glass centre) > bulb_glass, bulb_filament, bulb_base, bulb_contact
Overall height ~0.25 m (glass diameter 0.15 m).
"""
import math
from mathutils import Vector
from lib.core import B, join, set_parent, empty
from lib import geo, mat

ITEM = {"id": "props/bulb", "out": "props/bulb.glb"}
ANIMATIONS = False

GLASS_C = 0.155  # glass centre height above the base bottom (Blender Z)


def build():
    root = empty("bulb", (0, 0, 0))
    z0 = -GLASS_C  # base bottom, so that the glass centre is the origin

    # frosted glass: pear profile (radius, z) bottom -> top. The neck is a Hermite curve that
    # leaves the base vertically and meets the sphere tangentially (no crease).
    R = 0.075
    a0 = math.radians(-52)
    p0 = Vector((0.031, 0.052))
    p1 = Vector((R * math.cos(a0), GLASS_C + R * math.sin(a0)))
    m0 = Vector((0.0, 1.0)) * 0.05
    m1 = Vector((-math.sin(a0), math.cos(a0))) * 0.06
    prof = [(0.0, 0.052)]
    for i in range(9):
        s = i / 9
        h00, h10, h01, h11 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, -2 * s**3 + 3 * s**2, s**3 - s**2
        p = p0 * h00 + m0 * h10 + p1 * h01 + m1 * h11
        prof.append((p.x, p.y))
    for i in range(17):
        a = a0 + (math.pi / 2 - a0) * i / 16
        prof.append((max(0.0, R * math.cos(a)), GLASS_C + R * math.sin(a)))
    prof[-1] = (0.0, GLASS_C + R)
    prof = [(r, z + z0) for r, z in prof]
    glass = geo.lathe("bulb_glass", prof, segs=48, mat=mat.material("emit_bulbglass", "#e2ddd3", roughness=0.2,
                                                                     emission="#ffe2a0", emission_strength=0.0))
    set_parent(glass, root)

    # screw base with threads
    base_prof = [(0.0, 0.0), (0.012, 0.0), (0.020, 0.006), (0.027, 0.012), (0.030, 0.016)]
    z = 0.016
    for k in range(4):  # thread ridges
        base_prof += [(0.031, z + 0.002), (0.0345, z + 0.0055), (0.031, z + 0.009)]
        z += 0.0105
    base_prof += [(0.032, 0.058), (0.0335, 0.062), (0.0315, 0.066), (0.0, 0.066)]
    base_prof = [(r, zz + z0) for r, zz in base_prof]
    base = geo.lathe("bulb_base", base_prof, segs=40, mat=mat.material("metal_screw", "#b8b2a8", roughness=0.38,
                                                                      metallic=1.0))
    set_parent(base, root)
    contact = geo.sphere("bulb_contact", 0.011, center=(0, 0, z0 + 0.002), segs=20, rings=10, scale=(1, 1, 0.55),
                         mat=mat.material("prop_contact", "#3a3532", roughness=0.5))
    set_parent(contact, root)

    # filament: two support wires + a coil between them
    fil_mat = mat.material("emit_filament", "#ffe2a0", roughness=0.4, emission="#ffe2a0", emission_strength=0.0)
    parts = []
    for sx in (-1, 1):
        parts.append(geo.tube(f"wire_{sx}", [Vector((0.006 * sx, 0, z0 + 0.06)), Vector((0.012 * sx, 0, z0 + 0.10)),
                                            Vector((0.022 * sx, 0, z0 + 0.135))], radius=0.0016, segs=6, mat=fil_mat))
    coil = []
    n = 90
    for i in range(n + 1):
        t = i / n
        x = -0.022 + 0.044 * t
        a = t * 2 * math.pi * 7
        sag = -0.010 * math.sin(t * math.pi)
        coil.append(Vector((x, 0.0045 * math.cos(a), z0 + 0.137 + sag + 0.0045 * math.sin(a))))
    parts.append(geo.tube("coil", coil, radius=0.0012, segs=5, mat=fil_mat))
    fil = join(parts, name="bulb_filament")
    set_parent(fil, root)
    return {"height_m": 0.25, "glass_radius_m": R, "origin": "glass centre"}
