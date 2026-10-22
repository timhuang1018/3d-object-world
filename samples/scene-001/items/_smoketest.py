"""Smoke test for the helper library (not a bank item)."""
import math
from lib.core import B, shade_smooth
from lib import geo, mat, rig as rigmod, tex

ITEM = {"id": "test/smoketest", "out": "test/smoketest.glb"}


def build():
    skin = mat.vinyl("skin", "#f4dcc6")
    navy = mat.vinyl("hoodie", "#36435e")
    woodm = mat.wood("desk", "#d9b68e", image=mat.image_from_array("grain", tex.wood_grain("#d9b68e", seed=3)))
    head = geo.sphere("head", 0.42, center=B(0, 1.08, 0), mat=skin)
    torso = geo.rounded_box("torso", (0.36, 0.26, 0.42), 0.1, center=B(0, 0.63, 0), mat=navy)
    shell = geo.face_shell(head, B(0, 1.08, 0), 0.42, mat=mat.decal("face"))
    arm_path = [B(0.2, 0.8, 0), B(0.24, 0.63, 0), B(0.26, 0.47, 0)]
    arm = geo.tube("arm_L", arm_path, radius=0.05, segs=16, mat=navy, round_caps=True)
    desk = geo.rounded_box("desk", (1.15, 0.55, 0.04), 0.01, center=B(1.2, 0.55, 0), mat=woodm)
    geo.box_uv(desk, scale=1.0)
    lamp = geo.lathe("vase", [(0.0, 0.0), (0.06, 0.0), (0.09, 0.1), (0.05, 0.22), (0.04, 0.25), (0.0, 0.25)],
                     center=B(1.0, 0.57, 0), mat=mat.ceramic("vase", "#c99a7a"))
    ring = geo.torus("ring", 0.092, 0.006, center=B(0.155, 1.08, 0.45), rot=(90, 0, 0), mat=mat.metal("wire", "#3b3633"))
    r = rigmod.Rig("smoke_rig")
    r.bone("root", B(0, 0, 0))
    r.bone("torso", B(0, 0.45, 0), "root")
    r.bone("head", B(0, 0.84, 0), "torso")
    r.bone("upperarm_L", arm_path[0], "torso")
    r.bone("forearm_L", arm_path[1], "upperarm_L")
    r.bone("hand_L", arm_path[2], "forearm_L")
    r.build()
    r.bind_rigid(head, "head")
    r.bind_rigid(shell, "head")
    r.bind_rigid(ring, "head")
    r.bind_rigid(torso, "torso")
    r.bind_chain(arm, [("upperarm_L", arm_path[0]), ("forearm_L", arm_path[1]), ("hand_L", arm_path[2])], blend=0.04)
    a = r.action("wave")
    a.key(0.0, rot={"upperarm_L": (0, 0, 0), "forearm_L": (0, 0, 0)})
    a.key(0.5, rot={"upperarm_L": (0, 0, 120), "forearm_L": (0, 0, 40)}, interp='BACK', easing='EASE_OUT')
    a.key(1.0, rot={"upperarm_L": (0, 0, 0), "forearm_L": (0, 0, 0)})
    a.done()
    b = r.action("nod")
    b.key(0.0, rot={"head": (0, 0, 0)})
    b.key(0.4, rot={"head": (20, 0, 0)})
    b.key(0.8, rot={"head": (0, 0, 0)})
    b.done()
    return {"note": "smoke test"}
