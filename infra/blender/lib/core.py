"""Core scene / object helpers for the bank build scripts.

Coordinate conventions (see docs/conventions.md):
  Blender is Z-up and a character faces -Y.  The glTF exporter converts to three.js
  (Y-up, character faces +Z):  three(x, y, z) = blender(x, z, -y).
  Use `B(x, y, z)` to write positions in *three.js* coordinates (as in docs/scene-spec.md)
  and get Blender coordinates back.
"""
import math
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler, Quaternion


def B(x, y, z):
    """three.js (x, y-up, z-front) -> Blender (x, y, z-up)."""
    return Vector((x, -z, y))


def T(v):
    """Blender vector -> three.js tuple."""
    return (v[0], v[2], -v[1])


def reset_scene(fps=60):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import addon_utils
    addon_utils.enable("io_scene_gltf2", default_set=True)
    sc = bpy.context.scene
    sc.render.fps = fps
    sc.unit_settings.system = 'METRIC'
    sc.frame_start = 0
    sc.frame_end = 0
    return sc


def link(obj, collection=None):
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def new_mesh_object(name, bm=None, mesh=None, collection=None):
    if mesh is None:
        mesh = bpy.data.meshes.new(name)
        if bm is not None:
            bm.to_mesh(mesh)
            bm.free()
    obj = bpy.data.objects.new(name, mesh)
    return link(obj, collection)


def empty(name, loc=(0, 0, 0), parent=None, props=None, display='PLAIN_AXES', size=0.1, rot=None):
    """Create an empty. `loc` is in Blender coordinates (use B() for three.js coords).
    `props` become glTF extras (exported with export_extras=True)."""
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = display
    e.empty_display_size = size
    e.location = Vector(loc)
    if rot is not None:
        e.rotation_euler = Euler(rot, 'XYZ')
    if parent is not None:
        e.parent = parent
    for k, v in (props or {}).items():
        e[k] = v
    return link(e)


def set_parent(child, parent, keep_world=True):
    mw = child.matrix_world.copy()
    child.parent = parent
    if keep_world:
        child.matrix_world = mw
    return child


def select_only(objs, active=None):
    bpy.ops.object.select_all(action='DESELECT') if bpy.context.mode == 'OBJECT' else None
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def apply_modifiers(obj):
    """Apply all modifiers on obj (evaluated mesh -> new mesh data)."""
    if not obj.modifiers:
        return obj
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def apply_transform(obj, location=True, rotation=True, scale=True):
    """Bake the object's transform into its mesh data."""
    m = Matrix.Identity(4)
    loc, rot, sca = obj.matrix_basis.decompose()
    basis = Matrix.Identity(4)
    if location:
        basis = Matrix.Translation(loc) @ basis
    if rotation:
        basis = basis @ rot.to_matrix().to_4x4()
    if scale:
        basis = basis @ Matrix.Diagonal((*sca, 1.0))
    if obj.type == 'MESH':
        obj.data.transform(basis)
        obj.data.update()
    new_loc = Vector((0, 0, 0)) if location else loc
    new_rot = Quaternion() if rotation else rot
    new_sca = Vector((1, 1, 1)) if scale else sca
    obj.matrix_basis = Matrix.LocRotScale(new_loc, new_rot, new_sca)
    return obj


def shade_smooth(obj, angle_deg=None):
    """Smooth shading; optional sharp edges above angle_deg."""
    me = obj.data
    me.shade_smooth()
    if angle_deg is not None:
        me.set_sharp_from_angle(angle=math.radians(angle_deg))
    return obj


def shade_flat(obj):
    obj.data.shade_flat()
    return obj


def add_subsurf(obj, levels=2, apply=False):
    m = obj.modifiers.new("Subsurf", 'SUBSURF')
    m.levels = levels
    m.render_levels = levels
    if apply:
        apply_modifiers(obj)
    return obj


def add_solidify(obj, thickness=0.01, offset=-1.0, apply=False, even=True, rim=True):
    m = obj.modifiers.new("Solidify", 'SOLIDIFY')
    m.thickness = thickness
    m.offset = offset
    m.use_even_offset = even
    m.use_rim = rim
    if apply:
        apply_modifiers(obj)
    return obj


def add_bevel(obj, width=0.01, segments=3, apply=False, limit='ANGLE', angle_deg=30):
    m = obj.modifiers.new("Bevel", 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = limit
    if limit == 'ANGLE':
        m.angle_limit = math.radians(angle_deg)
    m.harden_normals = False
    if apply:
        apply_modifiers(obj)
    return obj


def join(objs, name=None):
    """Join mesh objects into the first one (materials are merged)."""
    objs = [o for o in objs if o is not None]
    if len(objs) == 1:
        if name:
            objs[0].name = name
        return objs[0]
    target = objs[0]
    # Bake transforms so joining is purely data-level and context free
    for o in objs:
        if o.parent is not None:
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
        apply_transform(o)
    bm = bmesh.new()
    mats = []
    for o in objs:
        me = o.data
        # material remap
        remap = []
        for m in me.materials:
            if m not in mats:
                mats.append(m)
            remap.append(mats.index(m))
        tmp = bmesh.new()
        tmp.from_mesh(me)
        for f in tmp.faces:
            if remap:
                f.material_index = remap[f.material_index] if f.material_index < len(remap) else 0
        tmp_me = bpy.data.meshes.new("__tmp")
        tmp.to_mesh(tmp_me)
        tmp.free()
        bm.from_mesh(tmp_me)
        bpy.data.meshes.remove(tmp_me)
    new_me = bpy.data.meshes.new(name or target.name)
    bm.to_mesh(new_me)
    bm.free()
    for m in mats:
        new_me.materials.append(m)
    # keep smooth flags (from_mesh keeps per-face smooth)
    for o in objs[1:]:
        bpy.data.objects.remove(o, do_unlink=True)
    old = target.data
    target.data = new_me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    if name:
        target.name = name
    return target


def set_origin(obj, origin_blender):
    """Move the object origin to `origin_blender` (world coords) without moving geometry."""
    origin = Vector(origin_blender)
    mw = obj.matrix_world.copy()
    local = mw.inverted() @ origin
    obj.data.transform(Matrix.Translation(-local))
    obj.matrix_world = mw @ Matrix.Translation(local)
    return obj


def remove(obj):
    bpy.data.objects.remove(obj, do_unlink=True)


def bounds(obj):
    """World-space AABB (Blender coords) of a mesh object."""
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def voxel_remesh(obj, voxel=0.006, smooth_iters=0, adaptivity=0.0):
    """Union overlapping parts into one seamless 'sculpted' surface (voxel remesh)."""
    m = obj.modifiers.new("Remesh", 'REMESH')
    m.mode = 'VOXEL'
    m.voxel_size = voxel
    m.adaptivity = adaptivity
    m.use_smooth_shade = True
    apply_modifiers(obj)
    if smooth_iters:
        s = obj.modifiers.new("Smooth", 'CORRECTIVE_SMOOTH') if False else obj.modifiers.new("Smooth", 'SMOOTH')
        s.factor = 0.5
        s.iterations = smooth_iters
        apply_modifiers(obj)
    shade_smooth(obj)
    return obj


def decimate(obj, ratio=0.5):
    m = obj.modifiers.new("Decimate", 'DECIMATE')
    m.ratio = ratio
    apply_modifiers(obj)
    return obj
