"""Mesh builders (bmesh based, context free).  All positions are *Blender* coordinates
(Z-up, front = -Y).  Use core.B(x, y, z) to convert from three.js / brief coordinates.
"""
import math
import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix, Euler, Quaternion

from .core import new_mesh_object, shade_smooth, apply_modifiers


def _finish(name, bm, mat=None, smooth=True, collection=None):
    obj = new_mesh_object(name, bm=bm, collection=collection)
    if mat is not None:
        obj.data.materials.append(mat)
    if smooth:
        shade_smooth(obj)
    return obj


def _mat4(center=(0, 0, 0), rot=None, scale=(1, 1, 1)):
    m = Matrix.Translation(Vector(center))
    if rot is not None:
        r = rot if isinstance(rot, (Matrix, Quaternion)) else Euler([math.radians(a) for a in rot], 'XYZ')
        m = m @ (r.to_matrix().to_4x4() if not isinstance(r, Matrix) else r.to_4x4())
    m = m @ Matrix.Diagonal((*scale, 1.0))
    return m


def sphere(name, r=0.5, center=(0, 0, 0), segs=48, rings=24, scale=(1, 1, 1), rot=None, mat=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r, calc_uvs=True)
    bm.transform(_mat4(center, rot, scale))
    return _finish(name, bm, mat)


def rounded_box(name, size=(1, 1, 1), radius=0.05, center=(0, 0, 0), segments=4, rot=None, mat=None,
                smooth=True):
    """Box with rounded edges/corners. size = full extents (x, y, z)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    bm.transform(Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    r = min(radius, min(size) * 0.499)
    if r > 1e-5:
        bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=r, segments=segments,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    bm.transform(_mat4(center, rot))
    obj = _finish(name, bm, mat, smooth=False)
    if smooth:
        shade_smooth(obj, angle_deg=35 if segments >= 2 else 20)
    return obj


def box(name, size=(1, 1, 1), center=(0, 0, 0), rot=None, mat=None):
    return rounded_box(name, size, 0.0, center, rot=rot, mat=mat, smooth=False)


def cylinder(name, r=0.1, depth=0.2, center=(0, 0, 0), segs=32, rot=None, mat=None, r2=None, caps=True,
             bevel=0.0, bevel_segments=3, smooth=True):
    """Z-axis cylinder/cone centred at center. r2 = top radius (cone)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segs, radius1=r,
                          radius2=r if r2 is None else r2, depth=depth, calc_uvs=True)
    if bevel > 0 and caps:
        rim = [e for e in bm.edges if all(abs(abs(v.co.z) - depth / 2) < 1e-6 for v in e.verts)
               and not e.is_wire and len(e.link_faces) == 2
               and any(len(f.verts) > 4 for f in e.link_faces)]
        bmesh.ops.bevel(bm, geom=rim, offset=bevel, segments=bevel_segments, profile=0.5,
                        affect='EDGES', clamp_overlap=True)
    bm.transform(_mat4(center, rot))
    obj = _finish(name, bm, mat, smooth=False)
    if smooth:
        shade_smooth(obj, angle_deg=40)
    return obj


def lathe(name, profile, segs=48, center=(0, 0, 0), rot=None, mat=None, scale=(1, 1, 1), smooth=True,
          close_top=True, close_bottom=True, angle=(0.0, 2 * math.pi), radial=None):
    """Revolve a (radius, z) profile (bottom -> top) around local Z.

    radial: optional f(theta) -> scale multiplier for the radius (e.g. fabric folds).
    Points with radius ~0 become poles.
    """
    bm = bmesh.new()
    full = abs((angle[1] - angle[0]) - 2 * math.pi) < 1e-6
    n = segs if full else segs + 1
    rings = []
    for (r, z) in profile:
        ring = []
        if r < 1e-6:
            ring = [bm.verts.new((0, 0, z))]
        else:
            for i in range(n):
                th = angle[0] + (angle[1] - angle[0]) * i / segs
                rr = r * (radial(th, z) if radial else 1.0)
                ring.append(bm.verts.new((rr * math.cos(th), rr * math.sin(th), z)))
        rings.append(ring)
    for a, b in zip(rings[:-1], rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for i in range(len(b) - (0 if full else 1)):
                bm.faces.new((a[0], b[i], b[(i + 1) % len(b)]))
        elif len(b) == 1:
            for i in range(len(a) - (0 if full else 1)):
                bm.faces.new((a[i], b[0], a[(i + 1) % len(a)]))
        else:
            for i in range(len(a) - (0 if full else 1)):
                j = (i + 1) % len(a)
                bm.faces.new((a[i], a[j], b[j], b[i]))
    if full:
        if close_bottom and len(rings[0]) > 2:
            bm.faces.new(list(reversed(rings[0])))
        if close_top and len(rings[-1]) > 2:
            bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.transform(_mat4(center, rot, scale))
    obj = _finish(name, bm, mat, smooth=False)
    if smooth:
        shade_smooth(obj)
    return obj


def loft(name, rings, mat=None, cap_start=True, cap_end=True, closed=True, smooth=True, uv=True):
    """Skin a list of rings (each a list of N 3D points, same N) into a surface.

    UVs: u = ring parameter (0..1 around), v = ring index / (len-1).
    """
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap") if uv else None
    vs = [[bm.verts.new(p) for p in ring] for ring in rings]
    nr = len(rings)
    N = len(rings[0])
    seg = N if closed else N - 1
    for k in range(nr - 1):
        for i in range(seg):
            j = (i + 1) % N
            f = bm.faces.new((vs[k][i], vs[k][j], vs[k + 1][j], vs[k + 1][i]))
            if uvl:
                for loop, (uu, vv) in zip(f.loops, ((i / seg, k / (nr - 1)), ((i + 1) / seg, k / (nr - 1)),
                                                    ((i + 1) / seg, (k + 1) / (nr - 1)),
                                                    (i / seg, (k + 1) / (nr - 1)))):
                    loop[uvl].uv = (uu, vv)
    if closed:
        if cap_start:
            c = bm.verts.new(sum((v.co for v in vs[0]), Vector()) / N)
            for i in range(N):
                bm.faces.new((vs[0][(i + 1) % N], vs[0][i], c))
        if cap_end:
            c = bm.verts.new(sum((v.co for v in vs[-1]), Vector()) / N)
            for i in range(N):
                bm.faces.new((vs[-1][i], vs[-1][(i + 1) % N], c))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _finish(name, bm, mat, smooth=False)
    if smooth:
        shade_smooth(obj)
    return obj


def superellipse(cx, cy, z, a, b, n=2.5, N=48, phase=0.0):
    """Ring of N points of a superellipse |x/a|^n + |y/b|^n = 1 at height z (Blender XY plane)."""
    pts = []
    for i in range(N):
        t = phase + 2 * math.pi * i / N
        c, s = math.cos(t), math.sin(t)
        x = a * math.copysign(abs(c) ** (2.0 / n), c)
        y = b * math.copysign(abs(s) ** (2.0 / n), s)
        pts.append(Vector((cx + x, cy + y, z)))
    return pts


def _frames(path):
    """Parallel-transport frames along a polyline: returns list of (T, N, B)."""
    pts = [Vector(p) for p in path]
    tans = []
    for i in range(len(pts)):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == len(pts) - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        tans.append(t.normalized())
    up = Vector((0, 0, 1)) if abs(tans[0].z) < 0.9 else Vector((1, 0, 0))
    n = tans[0].cross(up).normalized()
    frames = []
    for i, t in enumerate(tans):
        if i > 0:
            # rotate previous normal onto new tangent
            axis = tans[i - 1].cross(t)
            if axis.length > 1e-8:
                ang = math.asin(min(1.0, axis.length))
                if tans[i - 1].dot(t) < 0:
                    ang = math.pi - ang
                n = Quaternion(axis.normalized(), ang) @ n
        b = t.cross(n).normalized()
        frames.append((t, n.normalized(), b))
    return pts, frames


def tube(name, path, radius=0.01, segs=12, mat=None, caps=True, smooth=True, round_caps=False,
         twist=0.0, flatten=1.0):
    """Sweep a circle along a polyline.  radius may be a float or a list (per point).
    flatten < 1 squashes the cross-section along the frame binormal (ribbon-ish)."""
    pts, frames = _frames(path)
    rs = radius if isinstance(radius, (list, tuple)) else [radius] * len(pts)
    rings = []
    for i, (p, (t, n, b)) in enumerate(zip(pts, frames)):
        ring = []
        for k in range(segs):
            a = 2 * math.pi * k / segs + twist * i / max(1, len(pts) - 1)
            ring.append(p + (n * math.cos(a) + b * math.sin(a) * flatten) * rs[i])
        rings.append(ring)
    if round_caps:
        # add hemispherical caps
        t0, tn = frames[0][0], frames[-1][0]
        start, end = [], []
        for j in range(1, 5):
            f = math.cos(math.pi / 2 * j / 5)
            d = math.sin(math.pi / 2 * j / 5)
            start.insert(0, [pts[0] + (q - pts[0]) * f - t0 * rs[0] * d for q in rings[0]])
            end.append([pts[-1] + (q - pts[-1]) * f + tn * rs[-1] * d for q in rings[-1]])
        rings = start + rings + end
    return loft(name, rings, mat=mat, cap_start=caps, cap_end=caps, smooth=smooth)


def torus(name, R=0.1, r=0.01, center=(0, 0, 0), rot=None, major=48, minor=12, mat=None, arc=None):
    """Torus in local XY plane (axis Z).  arc=(a0, a1) radians for a partial ring."""
    a0, a1 = arc if arc else (0.0, 2 * math.pi)
    full = arc is None
    n = major if full else major + 1
    path = [Vector((R * math.cos(a0 + (a1 - a0) * i / major), R * math.sin(a0 + (a1 - a0) * i / major), 0))
            for i in range(n)]
    rings = []
    for i, p in enumerate(path):
        th = a0 + (a1 - a0) * i / major
        radial = Vector((math.cos(th), math.sin(th), 0))
        ring = [p + (radial * math.cos(2 * math.pi * k / minor) + Vector((0, 0, 1)) * math.sin(2 * math.pi * k / minor)) * r
                for k in range(minor)]
        rings.append(ring)
    if full:
        rings.append(rings[0])
    obj = loft(name, rings, mat=mat, cap_start=not full, cap_end=not full)
    if full:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bm.to_mesh(obj.data)
        bm.free()
        shade_smooth(obj)
    obj.data.transform(_mat4(center, rot))
    return obj


def extrude_outline(name, outline, depth=0.02, center=(0, 0, 0), rot=None, mat=None, bevel=0.0,
                    bevel_segments=3, plane='XZ', smooth=True):
    """Extrude a closed 2D outline [(a, b), ...] (CCW) into a slab of `depth`.
    plane='XZ': outline in X (right) / Z (up), extruded along Y (front-back) and centred."""
    bm = bmesh.new()
    if plane == 'XZ':
        vs = [bm.verts.new((a, -depth / 2, b)) for a, b in outline]
        ext = Vector((0, depth, 0))
    elif plane == 'XY':
        vs = [bm.verts.new((a, b, -depth / 2)) for a, b in outline]
        ext = Vector((0, 0, depth))
    else:  # 'YZ'
        vs = [bm.verts.new((-depth / 2, a, b)) for a, b in outline]
        ext = Vector((depth, 0, 0))
    f = bm.faces.new(vs)
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=verts, vec=ext)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # triangulate ngon caps for robust export
    caps = [fc for fc in bm.faces if len(fc.verts) > 4]
    if bevel > 0:
        edges = [e for e in bm.edges if any(len(fc.verts) > 4 for fc in e.link_faces)]
        bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=bevel_segments, profile=0.5,
                        affect='EDGES', clamp_overlap=True)
    caps = [fc for fc in bm.faces if len(fc.verts) > 4]
    bmesh.ops.triangulate(bm, faces=caps, quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.transform(_mat4(center, rot))
    obj = _finish(name, bm, mat, smooth=False)
    if smooth:
        shade_smooth(obj, angle_deg=40)
    return obj


# ---- UV helpers ---------------------------------------------------------------

def box_uv(obj, scale=1.0, world=False, offset=(0.0, 0.0)):
    """Per-face planar projection along the dominant normal axis, in metres * scale.
    Good for wood grain / wallpaper tiling (textures should be REPEAT)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    mw = obj.matrix_world if world else Matrix.Identity(4)
    for f in bm.faces:
        n = (mw.to_3x3() @ f.normal)
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in f.loops:
            co = mw @ loop.vert.co
            if ax == 0:      # X-facing -> (y, z)
                u, v = (co.y if n.x > 0 else -co.y), co.z
            elif ax == 1:    # Y-facing -> (x, z)
                u, v = (-co.x if n.y > 0 else co.x), co.z
            else:            # Z-facing -> (x, y)
                u, v = co.x, co.y
            loop[uvl].uv = (u * scale + offset[0], v * scale + offset[1])
    bm.to_mesh(me)
    bm.free()
    return obj


def planar_uv(obj, axis='Y', origin=(0, 0, 0), half_size=0.5, flip_u=False):
    """Front projection: u from X, v from Z (axis='Y'), mapped so origin -> (0.5, 0.5)
    and +-half_size -> 0 / 1.  Object-local coordinates."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    o = Vector(origin)
    for f in bm.faces:
        for loop in f.loops:
            c = loop.vert.co - o
            if axis == 'Y':
                a, b = c.x, c.z
            elif axis == 'X':
                a, b = c.y, c.z
            else:
                a, b = c.x, c.y
            u = 0.5 + a / (2 * half_size)
            v = 0.5 + b / (2 * half_size)
            loop[uvl].uv = ((1 - u) if flip_u else u, v)
    bm.to_mesh(me)
    bm.free()
    return obj


def face_shell(src, center, half_size, name="face_decal", mat=None, min_facing=0.08, offset=0.0025,
               keep=None):
    """Front-projected decal shell copied from the front of `src` (a head mesh).

    - keeps faces whose normal faces the front (-Y) by more than `min_facing`
      (and optionally `keep(face_center) -> bool`),
    - pushes vertices out along their normals by `offset`,
    - UVs: u = 0.5 + (x - cx) / (2 * half_size), v = 0.5 + (z - cz) / (2 * half_size)
      where (cx, cz) = center (Blender X/Z of the head centre, world space).
    The canvas face textures in three.js use this exact mapping.
    """
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(src.evaluated_get(dg), depsgraph=dg)
    me.transform(src.matrix_world)
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    bm.normal_update()
    kill = []
    for f in bm.faces:
        fc = f.calc_center_median()
        facing = -f.normal.y
        ok = facing > min_facing
        if keep is not None:
            ok = ok and keep(fc)
        if not ok:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * offset
    uvl = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    cx, cz = center[0], center[2]
    for f in bm.faces:
        f.smooth = True
        for loop in f.loops:
            co = loop.vert.co
            loop[uvl].uv = (0.5 + (co.x - cx) / (2 * half_size), 0.5 + (co.z - cz) / (2 * half_size))
    obj = new_mesh_object(name, bm=bm)
    if mat is not None:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        for p in obj.data.polygons:
            p.material_index = 0
    obj["decal_center"] = [center[0], center[2], -center[1]]  # three.js (x, y, z)
    obj["decal_half_size"] = half_size
    return obj


def set_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.material_index = 0
    return obj


def vertex_colors(obj, fn, name="Col"):
    """Paint a POINT colour attribute from fn(co: Vector) -> (r, g, b) linear."""
    me = obj.data
    attr = me.color_attributes.get(name) or me.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
    for i, v in enumerate(me.vertices):
        c = fn(obj.matrix_world @ v.co)
        attr.data[i].color = (c[0], c[1], c[2], 1.0)
    me.color_attributes.active_color = attr
    return attr


def point_attribute(obj, name, fn):
    """Custom float attribute (exported when the name starts with '_', e.g. '_FURLEN')."""
    me = obj.data
    attr = me.attributes.get(name) or me.attributes.new(name, 'FLOAT', 'POINT')
    for i, v in enumerate(me.vertices):
        attr.data[i].value = float(fn(obj.matrix_world @ v.co))
    return attr


def displace(obj, fn, along_normal=True):
    """Move each vertex by fn(co, normal) (a float along the normal, or a Vector)."""
    me = obj.data
    me.calc_normals_split() if hasattr(me, "calc_normals_split") else None
    for v in me.vertices:
        d = fn(v.co.copy(), v.normal.copy())
        if isinstance(d, (int, float)):
            v.co += v.normal * d
        else:
            v.co += Vector(d)
    me.update()
    return obj
