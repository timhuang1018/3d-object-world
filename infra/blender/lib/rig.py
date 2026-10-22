"""Rig + action helpers.

Bones always point straight UP (+Z in Blender) with roll 0.  With the glTF exporter's
Y-up conversion this gives every joint an IDENTITY rest rotation in three.js, so joint-local
axes == character axes:   x = character's LEFT (+X),  y = up,  z = character's FRONT.

Pose rotations are given in DEGREES as (rx, ry, rz) about those axes, composed in Blender
'XYZ' Euler order (== three.js Euler order 'ZYX'):
  rx > 0  pitches the bone's top toward the FRONT  (head nods down, arm swings forward)
  ry > 0  yaws toward the character's LEFT          (turn left, seen from above: CCW)
  rz > 0  rolls the bone's top toward the character's RIGHT;
          for an arm hanging down: left arm (+X side) abducts with rz > 0, right arm with rz < 0.
Locations are offsets in metres in (x=left, y=up, z=front) character axes (three.js axes).
"""
import math
import bpy
from mathutils import Vector, Matrix, Euler, Quaternion

from .core import link, B


def q_from_deg(rx, ry, rz):
    return Euler((math.radians(rx), math.radians(ry), math.radians(rz)), 'XYZ').to_quaternion()


def _three_to_bone(v):
    """three.js-axes offset (x, y, z) -> bone-local offset.

    Bone local axes for an up-pointing roll-0 bone, in Blender world terms:
    X = +X, Y = +Z (up), Z = -Y (front).  three.js axes: x = +X, y = up, z = front.
    So three (x, y, z) == bone-local (x, y, z)."""
    return Vector(v)


class Rig:
    """Build an armature whose bones all point up with roll 0."""

    def __init__(self, name, bone_length=0.04):
        self.name = name
        self.bone_length = bone_length
        self.defs = []  # (name, head_blender, parent)
        self.obj = None

    def bone(self, name, head, parent=None):
        """head in Blender coordinates (use core.B for three.js coords)."""
        self.defs.append((name, Vector(head), parent))
        return name

    def head(self, name):
        for n, h, p in self.defs:
            if n == name:
                return h
        raise KeyError(name)

    def build(self):
        data = bpy.data.armatures.new(self.name)
        obj = bpy.data.objects.new(self.name, data)
        link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        eb = data.edit_bones
        for n, h, p in self.defs:
            b = eb.new(n)
            b.head = h
            b.tail = h + Vector((0, 0, self.bone_length))
            b.roll = 0.0
            b.use_connect = False
            b.use_deform = True
            if p:
                b.parent = eb[p]
        bpy.ops.object.mode_set(mode='OBJECT')
        for pb in obj.pose.bones:
            pb.rotation_mode = 'QUATERNION'
        self.obj = obj
        return obj

    # ---- skinning -------------------------------------------------------------
    def _attach(self, mesh_obj):
        if not any(m.type == 'ARMATURE' for m in mesh_obj.modifiers):
            mod = mesh_obj.modifiers.new("Armature", 'ARMATURE')
            mod.object = self.obj
        mw = mesh_obj.matrix_world.copy()
        mesh_obj.parent = self.obj
        mesh_obj.matrix_world = mw

    def bind_rigid(self, mesh_obj, bone):
        """Every vertex 100% on one bone."""
        vg = mesh_obj.vertex_groups.get(bone) or mesh_obj.vertex_groups.new(name=bone)
        vg.add(list(range(len(mesh_obj.data.vertices))), 1.0, 'REPLACE')
        self._attach(mesh_obj)
        return mesh_obj

    def bind_fn(self, mesh_obj, fn):
        """fn(world_co: Vector) -> {bone: weight}.  Weights are normalised; max 4 kept."""
        groups = {}
        mw = mesh_obj.matrix_world
        for v in mesh_obj.data.vertices:
            w = fn(mw @ v.co)
            items = sorted(((b, x) for b, x in w.items() if x > 1e-4), key=lambda bx: -bx[1])[:4]
            s = sum(x for _, x in items) or 1.0
            for b, x in items:
                groups.setdefault(b, []).append((v.index, x / s))
        for b, lst in groups.items():
            vg = mesh_obj.vertex_groups.get(b) or mesh_obj.vertex_groups.new(name=b)
            for idx, x in lst:
                vg.add([idx], x, 'REPLACE')
        self._attach(mesh_obj)
        return mesh_obj

    def bind_chain(self, mesh_obj, chain, blend=0.03):
        """Smooth weights along a joint chain, e.g. [('upperarm_L', shoulder), ('forearm_L', elbow),
        ('hand_L', wrist)] with joint positions in Blender coords.  Each vertex is projected onto
        the chain polyline; around each inner joint the weights cross-fade over +-blend metres."""
        names = [c[0] for c in chain]
        pts = [Vector(c[1]) for c in chain]
        nseg = len(pts) - 1

        def smooth(u):
            u = max(0.0, min(1.0, u))
            return u * u * (3 - 2 * u)

        def fn(co):
            if nseg < 1:
                return {names[0]: 1.0}
            best = None
            for i in range(nseg):
                a, b = pts[i], pts[i + 1]
                ab = b - a
                L = ab.length or 1e-9
                t = (co - a).dot(ab) / (L * L)
                tc = max(0.0, min(1.0, t))
                d = (a + ab * tc - co).length
                if best is None or d < best[0] - 1e-9:
                    best = (d, i, t * L, L)
            d, i, s, L = best
            # joint at the END of segment i sits between names[i] and names[i+1]
            if s > L - blend and i + 1 < len(names):
                w1 = smooth((s - (L - blend)) / (2 * blend))
                return {names[i]: 1 - w1, names[i + 1]: w1}
            # joint at the START of segment i sits between names[i-1] and names[i]
            if s < blend and i > 0:
                w1 = smooth((s + blend) / (2 * blend))
                return {names[i - 1]: 1 - w1, names[i]: w1}
            return {names[i]: 1.0}

        return self.bind_fn(mesh_obj, fn)

    # ---- actions ----------------------------------------------------------------
    def action(self, name, fps=None):
        return ActionBuilder(self, name, fps)


class ActionBuilder:
    """Author an action with times in seconds.

    a = rig.action("sit_type")
    a.key(0.0, rot={"upperarm_L": (40, 0, 10)}, loc={"hips": (0, 0, 0.01)})
    a.key(0.5, rot={...}, interp='BEZIER')            # interp applies to the segment AFTER this key
    a.key(1.0, rot={...}, interp='BACK', easing='EASE_OUT')
    a.done(loop=True)  # loop=True copies the first key's values to the end time if missing

    Only bones mentioned in a key are keyed (so clips can be layered in three.js).
    Rotations: degrees (rx, ry, rz) - see module docstring.  Scale: (sx, sy, sz).
    """

    def __init__(self, rig, name, fps=None):
        self.rig = rig
        self.name = name
        self.fps = fps or bpy.context.scene.render.fps
        self.keys = []  # (t, rot, loc, scale, interp, easing)
        arm = rig.obj
        if arm.animation_data is None:
            arm.animation_data_create()
        self.act = bpy.data.actions.new(name)
        self.act.use_fake_user = True
        arm.animation_data.action = self.act

    def key(self, t, rot=None, loc=None, scale=None, interp='BEZIER', easing='AUTO'):
        self.keys.append((t, rot or {}, loc or {}, scale or {}, interp, easing))
        return self

    def done(self, loop=False, end=None):
        arm = self.rig.obj
        arm.animation_data.action = self.act
        keys = sorted(self.keys, key=lambda k: k[0])
        if loop and end is not None and abs(keys[-1][0] - end) > 1e-6:
            first = keys[0]
            keys.append((end, first[1], first[2], first[3], first[4], first[5]))
        frame_of = lambda t: round(t * self.fps, 3)
        for (t, rot, loc, sca, interp, easing) in keys:
            f = frame_of(t)
            for b, r in rot.items():
                pb = arm.pose.bones[b]
                pb.rotation_quaternion = q_from_deg(*r)
                pb.keyframe_insert("rotation_quaternion", frame=f, group=b)
            for b, l in loc.items():
                pb = arm.pose.bones[b]
                pb.location = _three_to_bone(l)
                pb.keyframe_insert("location", frame=f, group=b)
            for b, s in sca.items():
                pb = arm.pose.bones[b]
                pb.scale = Vector(s)
                pb.keyframe_insert("scale", frame=f, group=b)
        # interpolation per key
        from bpy_extras import anim_utils
        cb = anim_utils.action_get_channelbag_for_slot(self.act, arm.animation_data.action_slot)
        interp_at = {frame_of(k[0]): (k[4], k[5]) for k in keys}
        for fc in cb.fcurves:
            # keep quaternion hemispheres consistent
            for kp in fc.keyframe_points:
                it = interp_at.get(round(kp.co.x, 3))
                if it:
                    kp.interpolation = it[0]
                    if it[1] != 'AUTO':
                        kp.easing = it[1]
                kp.handle_left_type = 'AUTO_CLAMPED'
                kp.handle_right_type = 'AUTO_CLAMPED'
            fc.update()
        # reset pose so the next action / export starts from rest
        for pb in arm.pose.bones:
            pb.rotation_quaternion = Quaternion()
            pb.location = Vector()
            pb.scale = Vector((1, 1, 1))
        arm.animation_data.action = None
        return self.act


def export_settings_note():
    return "Actions are exported with export_animation_mode='ACTIONS', force sampling, optimised size."
