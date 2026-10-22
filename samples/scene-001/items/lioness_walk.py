"""Lioness walk cycle (1.0 s = 2 steps, loops, in place; the director drives the phase from distance).

Built from KEY POSES per step - contact -> down -> passing -> up - with eased (cubic Hermite, flat at
the extremes) interpolation, and FOOT-LOCKED legs:

  * each foot is a rocker (the ellipse of the foot sole profile, from lioness.FOOT_C / FOOT_R): it
    strikes on the heel with the toes up, rolls flat, holds flat while the body passes over it, then
    peels heel-first onto the ball and toes until toe-off.  While on the ground the contact point moves
    backward at exactly `stride` per cycle (rolling without slipping), so at the director's distance-
    driven phase the planted foot does not slide;
  * the ankle path in the air goes toe-off -> passing (lifted, under the hip) -> reach -> contact;
  * 2-bone IK (thigh / shin) in the leg plane puts the ankle on that path; the foot bone gets the rocker
    pitch; pelvis yaw / roll are cancelled in the thighs so planted feet do not twist;
  * pelvis: bob (lowest on `down`, highest on `up`), weight shift over the stance foot, yaw forward with
    the swinging leg, the swing-side hip dropping a little;
  * shoulders counter-rotate the pelvis; arms swing opposite the legs with the forearm and paw dragging
    behind (overlap); the head bob lags the hips; the tail and ears follow through with growing delay.

Rig conventions (docs/conventions.md section 5): joint axes x = her left, y = up, z = front;
(rx, ry, rz) degrees, Blender XYZ Euler (R = Rz @ Ry @ Rx); rx > 0 pitches the bone top forward.
"""
import math

import numpy as np

T = 1.0          # cycle length (s): 2 steps
FPS = 60
DUTY = 0.60      # fraction of the cycle a foot is on the ground (> 0.5: a walk, with double support)
HIPS_Y = 0.50    # hips bone head (rest)


# ---------------------------------------------------------------------------------------- curves
def _ease_curve(keys, period):
    """Periodic cubic Hermite through (t, v) keys.  Slopes: Catmull-Rom, zero at local extrema (so
    every key pose eases in and out), clamped against overshoot."""
    keys = sorted(((t % period, v) for t, v in keys), key=lambda kv: kv[0])
    ts = np.array([k[0] for k in keys], float)
    vs = np.array([k[1] for k in keys], float)
    n = len(ts)
    if n == 1:
        return lambda t: float(vs[0])
    et = np.concatenate([ts - period, ts, ts + period])
    ev = np.concatenate([vs, vs, vs])
    m = np.zeros(len(et))
    for j in range(1, len(et) - 1):
        d0 = (ev[j] - ev[j - 1]) / (et[j] - et[j - 1])
        d1 = (ev[j + 1] - ev[j]) / (et[j + 1] - et[j])
        if d0 * d1 > 0:
            mm = (ev[j + 1] - ev[j - 1]) / (et[j + 1] - et[j - 1])
            m[j] = math.copysign(min(abs(mm), 3 * min(abs(d0), abs(d1))), mm)

    def f(t):
        t = t % period
        j = int(np.searchsorted(et, t, side="right") - 1)
        h = et[j + 1] - et[j]
        s = (t - et[j]) / h
        return float((2 * s ** 3 - 3 * s ** 2 + 1) * ev[j] + (s ** 3 - 2 * s ** 2 + s) * h * m[j]
                     + (-2 * s ** 3 + 3 * s ** 2) * ev[j + 1] + (s ** 3 - s ** 2) * h * m[j + 1])
    return f


def _hermite(keys):
    """Open cubic Hermite through (t, v, slope-or-None) keys; None slopes are Catmull-Rom."""
    ts = np.array([k[0] for k in keys], float)
    vs = np.array([k[1] for k in keys], float)
    ms = []
    for i, k in enumerate(keys):
        if k[2] is not None:
            ms.append(k[2])
        else:
            ms.append((vs[i + 1] - vs[i - 1]) / (ts[i + 1] - ts[i - 1]))

    def f(t):
        j = int(np.clip(np.searchsorted(ts, t, side="right") - 1, 0, len(ts) - 2))
        h = ts[j + 1] - ts[j]
        s = (t - ts[j]) / h
        return float((2 * s ** 3 - 3 * s ** 2 + 1) * vs[j] + (s ** 3 - 2 * s ** 2 + s) * h * ms[j]
                     + (-2 * s ** 3 + 3 * s ** 2) * vs[j + 1] + (s ** 3 - s ** 2) * h * ms[j + 1])
    return f


def _seg_ease(t, keys):
    """Piecewise (t, v, ease) keys, ease in {'io', 'in', 'out', 'lin'} for the segment after the key."""
    E = {"io": lambda x: x * x * (3 - 2 * x), "in": lambda x: x * x, "out": lambda x: 1 - (1 - x) ** 2,
         "lin": lambda x: x}
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0, e), (t1, v1, _) in zip(keys[:-1], keys[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * E[e]((t - t0) / (t1 - t0))
    return keys[-1][1]


# ---------------------------------------------------------------------------------------- rotations
def Rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], float)


def Ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], float)


def Rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], float)


def euler_m(rx, ry, rz):
    """Degrees, Blender XYZ order -> matrix (R = Rz Ry Rx)."""
    return Rz(math.radians(rz)) @ Ry(math.radians(ry)) @ Rx(math.radians(rx))


def m_euler(R):
    ry = -math.asin(max(-1.0, min(1.0, R[2, 0])))
    rx = math.atan2(R[2, 1], R[2, 2])
    rz = math.atan2(R[1, 0], R[0, 0])
    return math.degrees(rx), math.degrees(ry), math.degrees(rz)


def dir_to_m(d):
    """World rotation (Rz(roll) @ Rx(pitch)) that maps the bone's rest 'down' (0, -1, 0) onto d."""
    d = d / np.linalg.norm(d)
    p = -math.asin(max(-1.0, min(1.0, d[2])))
    r = math.atan2(d[0], -d[1])
    return Rz(r) @ Rx(p)


# ---------------------------------------------------------------------------------------- the foot rocker
class Rocker:
    """Sole profile in the leg's (z, y) plane, relative to the ankle: ellipse centre c, semi-axes
    (az, ay).  For a foot pitch a (deg, > 0 = toes down) gives the lowest sole point and the arc length
    the sole has rolled since flat (signed: + = toward the toes)."""

    def __init__(self, c, az, ay):
        self.c, self.az, self.ay = np.asarray(c, float), az, ay
        th = np.linspace(-math.pi, math.pi, 4001)
        ds = np.sqrt((az * np.sin(th)) ** 2 + (ay * np.cos(th)) ** 2)
        S = np.concatenate([[0.0], np.cumsum(0.5 * (ds[1:] + ds[:-1]) * np.diff(th))])
        self._th, self._S = th, S - np.interp(-math.pi / 2, th, S)

    @staticmethod
    def rot(a):  # (z, y) rotation for a pitch of a degrees (toes down for a > 0)
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        return np.array([[c, s], [-s, c]])

    def contact(self, a):
        """-> (sole point relative to the ankle in the foot frame, rolled arc length)"""
        R = self.rot(a)
        best = None
        for th in np.linspace(-math.pi, 0.6, 721):
            p = self.c + np.array([self.az * math.cos(th), self.ay * math.sin(th)])
            y = (R @ p)[1]
            if best is None or y < best[0]:
                best = (y, th, p)
        _, th, p = best
        return p, float(np.interp(th, self._th, self._S))


# ---------------------------------------------------------------------------------------- the walk
class Walk:
    def __init__(self, leg_h, leg_k, leg_a, foot_c, foot_r, stride, sole=0.0):
        self.H = np.array(leg_h, float)
        self.K = np.array(leg_k, float)
        self.A = np.array(leg_a, float)
        self.L1 = float(np.linalg.norm(self.K - self.H))
        self.L2 = float(np.linalg.norm(self.A - self.K))
        self.R1rest = dir_to_m(self.K - self.H)
        self.R2rest = dir_to_m(self.A - self.K)
        self.S = stride
        fc = np.array(foot_c, float) - self.A
        self.rock = Rocker((fc[2], fc[1]), foot_r[2], foot_r[1])
        self.ground = float(self.A[1] + self.rock.contact(0.0)[0][1]) + sole  # sole height at rest
        # foot pitch over the stance (deg): heel strike toes-up -> flat -> heel-off -> toe-off
        self.A0, self.A1 = -15.0, 38.0
        self.p_flat, self.p_heel = 0.11, 0.27
        # where the planted point sits at contact (centres the stance under the hips)
        self.G0 = 0.0
        self.G0 = self._centre()
        self._build_swing()

    # -- stance ------------------------------------------------------------------------------
    def stance_pitch(self, p):
        return _seg_ease(p, [(0.0, self.A0, "in"), (self.p_flat, 0.0, "lin"), (self.p_heel, 0.0, "in"),
                             (DUTY, self.A1, "lin")])

    def stance_ankle(self, p):
        """Ankle (z, y) in the root frame while the foot is on the ground (phase p in [0, DUTY])."""
        a = self.stance_pitch(p)
        sole, s = self.rock.contact(a)
        g = np.array([self.G0 - self.S * p / T + s, self.ground])
        return g - self.rock.rot(a) @ sole, a

    def _centre(self):
        z0 = self.stance_ankle(0.0)[0][0]
        z1 = self.stance_ankle(DUTY)[0][0]
        return -0.5 * (z0 + z1) - 0.012   # a touch back: the trailing heel lifts, the leading leg stays soft

    # -- swing ---------------------------------------------------------------------------------
    def _build_swing(self):
        e = 1e-3
        a0, _ = self.stance_ankle(DUTY - e)
        a1, _ = self.stance_ankle(DUTY)
        b0, _ = self.stance_ankle(0.0)
        b1, _ = self.stance_ankle(e)
        v_off = (a1 - a0) / e
        v_on = (b1 - b0) / e
        p_off, p_pass, p_reach, p_on = DUTY, DUTY + 0.42 * (1 - DUTY), DUTY + 0.80 * (1 - DUTY), 1.0
        lift = 0.055   # ankle lift above its standing height at passing
        self.zsw = _hermite([(p_off, a1[0], v_off[0] * 0.6), (p_pass, 0.5 * (a1[0] + b0[0]) - 0.01, None),
                             (p_reach, b0[0] + 0.006, None), (p_on, b0[0], v_on[0] * 0.5)])
        self.ysw = _hermite([(p_off, a1[1], v_off[1]), (p_pass, self.A[1] + lift, 0.0),
                             (p_reach, b0[1] + 0.016, None), (p_on, b0[1], v_on[1] * 0.4)])
        self.asw = _hermite([(p_off, self.A1, 40.0), (p_off + 0.12, self.A1 - 5.0, None), (p_pass, 4.0, None),
                             (p_reach, self.A0 - 5.0, 0.0), (p_on, self.A0, 0.0)])

    def ankle(self, p):
        """-> (z, y) ankle, foot pitch (deg), on_ground"""
        p = p % 1.0
        if p <= DUTY:
            za, a = self.stance_ankle(p)
            return za, a, True
        return np.array([self.zsw(p), self.ysw(p)]), self.asw(p), False


def make_tracks(stride):
    """Upper-body key poses (per cycle; left contact at t = 0, right contact at t = 0.5).
    Step key times: contact 0.00, down 0.09, passing 0.25, up 0.35 (and +0.5 for the other step)."""
    def per_step(c, d, p, u):
        return [(0.00, c), (0.09, d), (0.25, p), (0.35, u), (0.50, c), (0.59, d), (0.75, p), (0.85, u)]

    def alt(v):  # +v on the left step, -v on the right step
        return [(0.00, v), (0.50, -v)]

    hips = {
        # bob: contact mid, down lowest, passing high, up highest
        "ly": _ease_curve(per_step(-0.030, -0.043, -0.014, -0.008), T),
        # weight shift over the stance foot (left foot plants at 0 -> hips move left until passing)
        "lx": _ease_curve([(0.05, 0.0), (0.27, 0.011), (0.55, 0.0), (0.77, -0.011)], T),
        # pelvis yaw: the left hip is forward at the left contact (ry < 0 brings +x forward)
        "ry": _ease_curve(alt(-6.0), T),
        # roll: the swing-side hip drops just after contact (left stance -> right hip drops: rz > 0 ...)
        "rz": _ease_curve([(0.10, 2.4), (0.30, 0.6), (0.60, -2.4), (0.80, -0.6)], T),
    }
    body = {
        "rx": _ease_curve(per_step(5.0, 7.0, 4.2, 4.0), T),                 # lean in, accent on down
        "ry": _ease_curve([(0.02, 9.5), (0.52, -9.5)], T),                  # shoulders counter the pelvis
        "rz": _ease_curve([(0.14, -1.6), (0.36, -0.4), (0.64, 1.6), (0.86, 0.4)], T),
    }
    # head: bob counter with a ~0.06 s lag (overlap), steady gaze
    neck = {"rx": _ease_curve([(t + 0.06, v) for t, v in per_step(-4.5, -6.5, -3.8, -3.5)], T),
            "ry": _ease_curve([(0.05, -5.0), (0.55, 5.0)], T)}
    head = {"rx": _ease_curve([(t + 0.10, v) for t, v in per_step(0.5, 2.6, -0.8, -1.4)], T),
            "rz": _ease_curve([(0.30, 1.2), (0.80, -1.2)], T)}
    # arms: opposite the legs; the upper arm leads, forearm + paw drag behind (overlap)
    arm_amp = 26.0

    def arm(side):  # side +1 = left arm (swings BACK while the left leg is forward at t = 0)
        sh = 0.0 if side > 0 else 0.5
        return {
            "upperarm": {"rx": _ease_curve([(sh + 0.03, arm_amp), (sh + 0.53, -arm_amp * 1.15)], T),
                         "rz": _ease_curve([(sh + 0.03, 7.0 * side), (sh + 0.53, 4.0 * side)], T)},
            "forearm": {"rx": _ease_curve([(sh + 0.12, -8.0), (sh + 0.62, -40.0)], T)},
            "hand": {"rx": _ease_curve([(sh + 0.18, 10.0), (sh + 0.68, -16.0)], T)},
        }
    arms = {s: arm(s) for s in (1, -1)}
    # tail: the base swings with the pelvis, each joint later and wider; a small vertical bounce
    tail = {
        "tail_1": {"ry": _ease_curve([(0.10, 8.0), (0.60, -8.0)], T),
                   "rx": _ease_curve([(t + 0.06, v) for t, v in per_step(2.0, 5.0, -2.0, -3.0)], T)},
        "tail_2": {"ry": _ease_curve([(0.22, 12.0), (0.72, -12.0)], T),
                   "rx": _ease_curve([(t + 0.13, v) for t, v in per_step(2.0, 6.0, -2.5, -4.0)], T)},
        "tail_3": {"ry": _ease_curve([(0.34, 17.0), (0.84, -17.0)], T),
                   "rx": _ease_curve([(t + 0.20, v) for t, v in per_step(3.0, 8.0, -3.5, -5.5)], T)},
    }
    ears = {"ear_L": {"rx": _ease_curve([(t + 0.08, v) for t, v in per_step(0.0, -7.0, 1.5, 2.0)], T)},
            "ear_R": {"rx": _ease_curve([(t + 0.10, v) for t, v in per_step(0.0, -7.0, 1.5, 2.0)], T)}}
    return hips, body, neck, head, arms, tail, ears


def _hip_w(walk, side, lx, ly, ry, rz):
    Rh = euler_m(0.0, ry, rz)
    Hrest = walk.H * np.array([side, 1.0, 1.0])
    return np.array([lx, HIPS_Y + ly, 0.0]) + Rh @ (Hrest - np.array([0.0, HIPS_Y, 0.0]))


def hip_height(walk, tracks, track_x, n=240, ext=0.985):
    """Hips bob: the key-pose design curve, kept low enough that the planted legs (and the leg about to
    land) reach the ground with a soft knee; smoothed so the limit never kinks the motion.
    -> periodic f(t)."""
    hips = tracks[0]
    ts = np.arange(n) / n * T
    design = np.array([hips["ly"](t) for t in ts])
    limit = np.full(n, 1.0)
    for k, t in enumerate(ts):
        for side, off in ((1, 0.0), (-1, 0.5)):
            p = (t - off) % 1.0
            (az, ay), _, on = walk.ankle(p)
            w_ext = ext if on else (1.0 if p > 0.94 else None)
            if w_ext is None:
                continue
            Hw = _hip_w(walk, side, hips["lx"](t), 0.0, hips["ry"](t), hips["rz"](t))
            A = np.array([track_x * side, ay, az])
            r2 = (w_ext * (walk.L1 + walk.L2)) ** 2 - (A[0] - Hw[0]) ** 2 - (A[2] - Hw[2]) ** 2
            limit[k] = min(limit[k], A[1] - Hw[1] + math.sqrt(max(r2, 0.0)))
    ly = np.minimum(design, limit)
    sig = 0.022 * n / T
    kk = np.arange(-int(3 * sig), int(3 * sig) + 1)
    g = np.exp(-0.5 * (kk / sig) ** 2)
    g /= g.sum()
    for _ in range(4):
        ly = np.minimum(np.array([np.dot(g, ly[(k + kk) % n]) for k in range(n)]), limit)
    ly = np.array([np.dot(g, ly[(k + kk) % n]) for k in range(n)]) - 0.0015
    tt = np.concatenate([ts, [T]])
    yy = np.concatenate([ly, ly[:1]])
    walk.hip_design, walk.hip_limit = design, limit
    return lambda t: float(np.interp(t % T, tt, yy))


def solve(walk, tracks, t, track_x):
    """All joint rotations / locations at time t -> (rot dict, loc dict, report)."""
    hips, body, neck, head, arms, tail, ears = tracks
    rot, loc = {}, {}
    h_loc = np.array([hips["lx"](t), walk.hip_y(t), 0.0])
    h_rot = (0.0, hips["ry"](t), hips["rz"](t))
    rot["hips"] = h_rot
    loc["hips"] = tuple(h_loc)
    Rh = euler_m(*h_rot)
    hip_origin = np.array([0.0, HIPS_Y, 0.0]) + h_loc
    rep = {}
    for side, tag, off in ((1, "L", 0.0), (-1, "R", 0.5)):
        Hrest = walk.H * np.array([side, 1.0, 1.0])
        Hw = hip_origin + Rh @ (Hrest - np.array([0.0, HIPS_Y, 0.0]))
        (az, ay), pitch, on = walk.ankle(t - off)
        Aw = np.array([track_x * side, ay, az])
        D = Aw - Hw
        d = float(np.linalg.norm(D))
        L1, L2 = walk.L1, walk.L2
        dmax = (L1 + L2) * 0.9995
        rep[tag] = (d / (L1 + L2), on)
        dc = min(d, dmax)
        u = D / d
        # knee bends forward: rotate u toward the forward pole by the hip angle
        fwd = np.array([0.0, 0.0, 1.0])
        pole = fwd - u * float(fwd @ u)
        pole /= np.linalg.norm(pole)
        ca = (L1 * L1 + dc * dc - L2 * L2) / (2 * L1 * dc)
        alpha = math.acos(max(-1.0, min(1.0, ca)))
        thigh_d = u * math.cos(alpha) + pole * math.sin(alpha)
        Kw = Hw + thigh_d * L1
        shin_d = (Hw + u * dc) - Kw
        # map the bones' actual rest vectors (not exactly vertical) onto the solved directions
        R1 = dir_to_m(thigh_d) @ walk.R1rest.T
        R2 = dir_to_m(shin_d) @ walk.R2rest.T
        R3 = Rx(math.radians(pitch))  # foot: pure pitch in the root frame (planted feet do not twist)
        rot[f"thigh_{tag}"] = m_euler(Rh.T @ R1)
        rot[f"shin_{tag}"] = m_euler(R1.T @ R2)
        rot[f"foot_{tag}"] = m_euler(R2.T @ R3)
    rot["body"] = (body["rx"](t), body["ry"](t), body["rz"](t))
    rot["neck"] = (neck["rx"](t), neck["ry"](t), 0.0)
    rot["head"] = (head["rx"](t), 0.0, head["rz"](t))
    for side, tag in ((1, "L"), (-1, "R")):
        a = arms[side]
        rot[f"upperarm_{tag}"] = (a["upperarm"]["rx"](t), 0.0, a["upperarm"]["rz"](t))
        rot[f"forearm_{tag}"] = (a["forearm"]["rx"](t), 0.0, 0.0)
        rot[f"hand_{tag}"] = (a["hand"]["rx"](t), 0.0, 0.0)
    for b, ch in tail.items():
        rot[b] = (ch["rx"](t), ch["ry"](t), 0.0)
    for b, ch in ears.items():
        rot[b] = (ch["rx"](t), 0.0, 0.0)
    return rot, loc, rep


def build_walk(r, leg_h, leg_k, leg_a, foot_c, foot_r, stride, name="walk"):
    """Bake the walk into rig action `name` (every frame, 60 fps, seamless loop)."""
    walk = Walk(leg_h, leg_k, leg_a, foot_c, foot_r, stride)
    tracks = make_tracks(stride)
    track_x = float(leg_a[0])
    walk.hip_y = hip_height(walk, tracks, track_x)
    a = r.action(name)
    n = int(round(T * FPS))
    worst = 0.0
    for i in range(n + 1):
        t = (i % n) / FPS
        rot, loc, rep = solve(walk, tracks, t, track_x)
        worst = max(worst, max(v[0] for v in rep.values() if v[1]))
        a.key(i / FPS, rot=rot, loc=loc, interp='LINEAR')
    a.done()
    print(f"[lioness] walk: stride {stride} m/cycle, duty {DUTY}, max stance leg extension {worst:.3f}")
    return walk


if __name__ == "__main__":  # quick numeric check without Blender
    import sys
    S = float(sys.argv[1]) if len(sys.argv) > 1 else 0.7
    w = Walk((0.095, 0.47, 0.0), (0.100, 0.27, 0.006), (0.104, 0.095, 0.0), (0.106, 0.050, 0.040),
             (0.062, 0.050, 0.090), S)
    tr = make_tracks(S)
    w.hip_y = hip_height(w, tr, 0.104)
    print("ground", round(w.ground, 4), "G0", round(w.G0, 3), "L", round(w.L1 + w.L2, 3))
    for i in range(0, 61, 3):
        t = i / 60
        rot, loc, rep = solve(w, tr, t, 0.104)
        (az, ay), a, on = w.ankle(t)
        print(f"t={t:.2f} L ankle z={az:+.3f} y={ay:.3f} a={a:+5.1f} {'G' if on else ' '} ext L={rep['L'][0]:.3f} "
              f"R={rep['R'][0]:.3f}  thighL={rot['thigh_L'][0]:+6.1f} shinL={rot['shin_L'][0]:+6.1f} "
              f"footL={rot['foot_L'][0]:+6.1f} hipsY={loc['hips'][1]:+.3f}")
