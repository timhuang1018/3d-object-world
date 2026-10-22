"""Office + hall dollhouse set (scene 001, beats 1-2).  See docs/scene-spec.md "Sets > Office + hall".

A Sylvanian Families-style dollhouse cutaway, open at the front (+z) and on the right (+x), on a big
round tabletop.  All coordinates below are three.js coordinates (x right, y up, z to the open front).

Engine hooks (exact node names):
  door_hinge    empty at (-2.55, 0, -1.10); door_panel + door_knob are children.  Closed = rotation 0;
                a POSITIVE rotation about +Y swings the free edge toward +x (into the room), <= ~100 deg.
  chair_base    mesh (5-star base, casters, gas lift), origin (0.85, 0, -0.5); roll it along z.
  chair_swivel  child of chair_base (seat + backrest), origin on the vertical axis at y = 0.31;
                rotate it about Y.
  laptop_lid    lid mesh, origin on the hinge axis (0.85, 0.568, 0.005), rotation.x = +0.26 rad
                (tilted back, away from Tim); child mesh laptop_screen (emit_screen, UV (0,0) =
                bottom-left and (1,1) = top-right as seen by Tim, who sits at z -0.5 facing +z).
  light_hall    empty just under the hall pendant shade at (-3.5, 1.88, -0.9) (warm point light);
                light_laptop empty 0.15 in front of the screen centre: (0.85, 0.730, -0.115).
  clock_hour / clock_minute   hands pivoting at the clock centre; rotation 0 = pointing up (12),
                clockwise as seen from the room = NEGATIVE rotation about +X.
Spots: spot_desk_seat, spot_doorway_out, spot_doorway_in, spot_shelf_top, spot_turntable (yaw prop).
"""
import math
import os

import bpy
import numpy as np

from items import dollhouse_kit as kit
from items import office_props as props
from lib import mat

ITEM = {"id": "sets/office", "out": "sets/office.glb"}
ANIMATIONS = False

# --- layout (three.js coords) ---------------------------------------------------------------
ROOM = dict(x0=-2.6, x1=2.4, z0=-1.9, z1=1.25)
HALL = dict(x0=-4.3, x1=-2.6, z0=-1.75, z1=0.35)
WALL_H = 2.3
WALL_T = 0.1
DOOR = dict(u0=-1.125, u1=-0.275, y0=0.0, y1=1.75, kind='door')
WINDOW = dict(u0=1.45, u1=2.15, y0=0.95, y1=1.75, kind='window')

SPOTS = {
    'spot_desk_seat': ((0.85, 0.0, -0.5), 0.0),
    'spot_doorway_out': ((-3.25, 0.0, -0.7), 90.0),
    'spot_doorway_in': ((-1.15, 0.0, -0.1), 90.0),
    'spot_shelf_top': ((-0.26, 1.04, -1.72), 15.0),
    'spot_turntable': ((1.85, 0.0, 0.65), 0.0),
}


def build_structure():
    M = kit.materials()
    t2 = WALL_T / 2
    # tabletop + base slabs (room incl. the right-wall return, hall)
    kit.tabletop_and_base([(ROOM['x0'] - t2, ROOM['x1'] + WALL_T, ROOM['z0'] - t2, ROOM['z1']),
                           (HALL['x0'] - t2, ROOM['x0'] - t2, HALL['z0'] - t2, HALL['z1'])],
                          center=(-0.9, -0.3), radius=7.0)
    # floors
    kit.plank_floor('floor_room', ROOM['x0'], ROOM['x1'], ROOM['z0'], ROOM['z1'], along='z', seed=11)
    kit.plank_floor('floor_hall', HALL['x0'], ROOM['x0'], HALL['z0'], HALL['z1'], along='x', seed=12)
    # room walls
    kit.wall('wall_back', ROOM['x0'] - t2, ROOM['z0'], ROOM['x1'], ROOM['z0'], inner=+1, height=WALL_H,
             thickness=WALL_T, openings=[WINDOW], inner_range=(ROOM['x0'] + t2, ROOM['x1']))
    kit.wall('wall_left', ROOM['x0'], ROOM['z0'] - t2, ROOM['x0'], ROOM['z1'], inner=+1, height=WALL_H,
             thickness=WALL_T, openings=[DOOR], inner_range=(ROOM['z0'] + t2, ROOM['z1']),
             outer=dict(paper='hall', range=(HALL['z0'] + t2, HALL['z1']), wainscot=True))
    # hall walls
    kit.wall('hall_wall_back', HALL['x0'] - t2, HALL['z0'], ROOM['x0'] - t2, HALL['z0'], inner=+1, height=WALL_H,
             thickness=WALL_T, paper='hall', inner_range=(HALL['x0'] + t2, ROOM['x0'] - t2))
    kit.wall('hall_wall_left', HALL['x0'], HALL['z0'] - t2, HALL['x0'], HALL['z1'], inner=+1, height=WALL_H,
             thickness=WALL_T, paper='hall', inner_range=(HALL['z0'] + t2, HALL['z1']))
    # window + door
    kit.window('window', 'x', ROOM['z0'], WINDOW['u0'], WINDOW['u1'], WINDOW['y0'], WINDOW['y1'], inner=+1,
               thickness=WALL_T, u_limits=(ROOM['x0'], ROOM['x1'] - 0.02))
    kit.door('door', 'z', ROOM['x0'], DOOR['u0'], DOOR['u1'], DOOR['y1'], inner=+1, thickness=WALL_T,
             hinge_u=-1.10, hinge_name='door_hinge')
    # beams: corner posts, hall beam for the pendant, decorative posts
    w = 0.09
    beams = [
        kit.post('post_room_corner', ROOM['x0'] + t2 + w / 2, ROOM['z0'] + t2 + w / 2, w=w),
        kit.post('post_hall_corner', HALL['x0'] + t2 + w / 2, HALL['z0'] + t2 + w / 2, w=w),
        kit.post('post_hall_corner2', ROOM['x0'] - t2 - w / 2, HALL['z0'] + t2 + w / 2, w=w),
        kit.beam('beam_hall', HALL['x0'] + t2, ROOM['x0'] - t2, WALL_H - 0.13, WALL_H - 0.01, -0.95, -0.85),
    ]
    kit._join(beams, 'beams')
    build_frame(M)


# Camera framing extension (beat 1 wide start): a right wall (full depth, so the open front becomes a
# proscenium), a ceiling with joists and a wooden fascia across the open front, so the wide start never
# looks past the dollhouse into the void.
# None of it casts shadows (custom prop noShadow), so the established lighting is unchanged.
RIGHT_RETURN_Z = ROOM['z1']  # the right wall runs from the back corner to here (full depth)
CEIL_Y = WALL_H            # ceiling underside, flush with the wall tops


def _no_shadow(*objs):
    for o in objs:
        if o is not None:
            o['noShadow'] = True


def build_frame(M):
    t2 = WALL_T / 2
    x1w = ROOM['x1'] + WALL_T          # outer face of the right return
    parts = kit.wall('wall_right', ROOM['x1'] + t2, ROOM['z0'] - t2, ROOM['x1'] + t2, RIGHT_RETURN_Z, inner=-1,
                     height=WALL_H, thickness=WALL_T, inner_range=(ROOM['z0'] + t2, RIGHT_RETURN_Z))
    _no_shadow(*parts.values())
    w = 0.09
    frame = [
        # posts capping the side walls' cut ends at the front, and the back-right corner
        kit.post('post_right_return', ROOM['x1'] + t2, RIGHT_RETURN_Z - w / 2 + 0.005, w=WALL_T + 0.02, d=w),
        kit.post('post_left_front', ROOM['x0'], ROOM['z1'] - w / 2 + 0.005, w=WALL_T + 0.02, d=w),
        kit.post('post_room_corner_r', ROOM['x1'] - w / 2, ROOM['z0'] + t2 + w / 2, w=w),
        # front fascia across the open front (the dollhouse's top rail)
        kit.beam('ceil_fascia', ROOM['x0'] - t2 - 0.02, x1w + 0.02, CEIL_Y - 0.14, CEIL_Y + 0.12,
                 ROOM['z1'] - 0.10, ROOM['z1'] + 0.015),
    ]
    if RIGHT_RETURN_Z < ROOM['z1'] - 0.2:
        # side rail over the open right side, from the return to the front
        frame.append(kit.beam('ceil_rail_r', ROOM['x1'] - 0.02, x1w + 0.02, CEIL_Y - 0.12, CEIL_Y + 0.12,
                              RIGHT_RETURN_Z, ROOM['z1'] - 0.10))
    # joists running front-to-back under the ceiling
    for i, x in enumerate((-1.55, -0.35, 1.25)):
        frame.append(kit.beam(f'ceil_joist{i}', x - 0.05, x + 0.05, CEIL_Y - 0.09, CEIL_Y + 0.001,
                              ROOM['z0'] + t2, ROOM['z1'] - 0.10))
    beams = kit._join(frame, 'frame_beams')
    ceiling = kit.rbox('ceiling', ROOM['x0'] - t2, x1w, CEIL_Y, CEIL_Y + 0.08, ROOM['z0'] - t2, ROOM['z1'],
                       r=0.01, mat=M['exterior'], segments=2)
    _no_shadow(beams, ceiling)


def _debug_hooks():
    """Preview-only poses (env vars; never set for bank builds): OFFICE_DOOR_OPEN=<deg>,
    OFFICE_CHAIR_YAW=<deg>, OFFICE_DEBUG_SCREEN=1 (UV test card: red block bottom-left, blue bar top)."""
    if os.environ.get('OFFICE_DOOR_OPEN'):
        bpy.data.objects['door_hinge'].rotation_euler.z = math.radians(float(os.environ['OFFICE_DOOR_OPEN']))
    if os.environ.get('OFFICE_CHAIR_YAW'):
        bpy.data.objects['chair_swivel'].rotation_euler.z = math.radians(float(os.environ['OFFICE_CHAIR_YAW']))
    if os.environ.get('OFFICE_DEBUG_SCREEN'):
        h, w = 44, 70
        a = np.ones((h, w, 3), np.float32) * np.array([0.18, 0.2, 0.27], np.float32)
        a[int(h * 0.62):, :int(w * 0.3)] = (0.95, 0.15, 0.1)     # bottom-left (row 0 = top)
        a[:int(h * 0.14), :] = (0.15, 0.35, 0.95)                # top bar
        img = mat.image_from_array('tex_screen_dbg', a)
        m = kit.emit_image('screen_dbg', img)
        o = bpy.data.objects['laptop_screen']
        o.data.materials.clear()
        o.data.materials.append(m)


def build():
    build_structure()
    props.build_all()
    for name, ((x, y, z), yaw) in SPOTS.items():
        kit.spot(name, x, y, z, yaw)
    _debug_hooks()
    return {"spots": {k: [*v[0], v[1]] for k, v in SPOTS.items()},
            "hooks": ["door_hinge", "chair_base", "chair_swivel", "laptop_lid", "laptop_screen", "light_hall",
                      "light_laptop", "clock_hour", "clock_minute"]}
