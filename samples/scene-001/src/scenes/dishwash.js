// Dishwashing choreography for the kitchen beats (Scene 001 beats 3-4), a pure function of t.
//
// One plate cycle per stack step (period P = the stack-step spacing, ~1.17 s; u = t - the time the plate
// leaves the stack):
//   u 0.00-0.17  the left hand lifts the top dirty plate off the stack and carries it over the basin
//   u 0.17-0.30  dips it into the soapy water (splash ring + droplets), brings it up to the work height
//   u 0.30-0.68  the right hand scrubs circles on it with the sponge; the smudges fade, suds build up
//   u 0.68-0.86  rinse: the plate goes under the spout, the tap runs, the suds wash off
//   u 0.86-1.00  stands it upright in the drying rack; the hand then reaches for the next plate
// The SAME plate object travels stack -> hand -> rack (kitchen.washPlates).  Beat 3 opens mid-cycle on a
// plate already in his hands.  On the deflate the plate in hand slides back into the water (splash), the
// tap goes off, the sponge plops in and both mittens come to rest on the counter edge.
// Arms: analytic two-bone IK (same construction as items/tim.py arm_ik) so the mittens land on
// the plate rim / the plate face; the plate then follows the actual mitten so contact never breaks.
import * as THREE from 'three';
import { DEG, clamp, cue, ease, fbm1, lerp, smoothstep } from '@infra/math.js';

const T_LIFT = 0.17, T_DIP = 0.215, T_SCRUB = 0.3, T_RINSE = 0.68, T_HOLD = 0.74, T_RACK = 0.86, T_PLACED = 1.0;
const SCRUB_HZ = 4.2;
const PLATE_R = 0.1113;
const GRIP = new THREE.Vector3(0.103, 0.013, 0); // plate-local rim point the left mitten pinches
const FACE_Y = 0.0075; // plate well surface above the frame origin
const SPONGE_HALF = 0.0225;

const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const AX = { x: V(1, 0, 0), y: V(0, 1, 0), z: V(0, 0, 1) };
/** Rotations applied in the listed order (world axes): rot(['x', 14], ['z', 6]) = tilt, then roll. */
function rot(...steps) {
  const q = new THREE.Quaternion();
  for (const [a, deg] of steps) q.premultiply(new THREE.Quaternion().setFromAxisAngle(AX[a], deg * DEG));
  return q;
}
const slerpQ = (a, b, k) => a.clone().slerp(b, clamp(k));
const lerpV = (a, b, k) => a.clone().lerp(b, k);

// ---------------------------------------------------------------- two-bone IK on the Tim rig
const _m0 = new THREE.Matrix4(), _m1 = new THREE.Matrix4();
/** World hand rotation whose mitten fingers point along `fingers` and palm faces `palm` (world vectors). */
export function handQuat(actor, side, fingers, palm) {
  const fa = actor.rig.joint(`forearm_${side}`), hd = actor.rig.joint(`hand_${side}`);
  const s = side === 'L' ? 1 : -1;
  const L0 = hd.position.clone().normalize();
  const P0 = V(s * L0.y, -s * L0.x, 0).normalize();
  const T0 = side === 'L' ? P0.clone().cross(L0) : L0.clone().cross(P0);
  const rootQ = actor.root.getWorldQuaternion(new THREE.Quaternion());
  const L0w = L0.applyQuaternion(rootQ), P0w = P0.applyQuaternion(rootQ), T0w = T0.applyQuaternion(rootQ);
  const Lt = fingers.clone().normalize();
  const Pt = palm.clone().addScaledVector(Lt, -palm.dot(Lt)).normalize();
  const Tt = side === 'L' ? Pt.clone().cross(Lt) : Lt.clone().cross(Pt);
  _m0.makeBasis(L0w, P0w, T0w);
  _m1.makeBasis(Lt, Pt, Tt);
  const R = new THREE.Quaternion().setFromRotationMatrix(_m1.multiply(_m0.transpose()));
  void fa;
  return R.multiply(rootQ);
}

/** Put the grip point of `side`'s mitten at world `target` with world hand rotation `handQ`; the elbow
 *  bends toward world direction `pole`.  Returns the reach ratio (>1 = out of reach, arm straight). */
export function solveArm(actor, side, target, handQ, pole) {
  const rig = actor.rig;
  const ua = rig.joint(`upperarm_${side}`), fa = rig.joint(`forearm_${side}`), hd = rig.joint(`hand_${side}`);
  const gp = rig.joint(`grip_${side}`);
  if (!ua || !fa || !hd) return 0;
  actor.root.updateMatrixWorld(true);
  const Qt = ua.parent.getWorldQuaternion(new THREE.Quaternion());
  const S = ua.getWorldPosition(V());
  const U0 = fa.position.clone(), F0 = hd.position.clone();
  const L1 = U0.length(), L2 = F0.length();
  const gl = gp ? gp.position.clone() : V();
  const wrist = target.clone().sub(gl.applyQuaternion(handQ));
  const d = wrist.sub(S);
  const D = d.length();
  const Dc = clamp(D, Math.abs(L1 - L2) + 1e-4, L1 + L2 - 1e-4);
  const dh = d.normalize();
  const a = (L1 * L1 - L2 * L2 + Dc * Dc) / (2 * Dc);
  const h = Math.sqrt(Math.max(0, L1 * L1 - a * a));
  const pv = pole.clone().addScaledVector(dh, -pole.dot(dh)).normalize();
  const E = S.clone().addScaledVector(dh, a).addScaledVector(pv, h);
  const Wc = S.clone().addScaledVector(dh, Dc);
  const QtI = Qt.clone().invert();
  const qua = new THREE.Quaternion().setFromUnitVectors(U0.normalize(), E.clone().sub(S).applyQuaternion(QtI).normalize());
  ua.quaternion.copy(qua);
  const Qu = Qt.clone().multiply(qua);
  const qfa = new THREE.Quaternion().setFromUnitVectors(F0.normalize(), Wc.clone().sub(E).applyQuaternion(Qu.clone().invert()).normalize());
  fa.quaternion.copy(qfa);
  const Qf = Qu.multiply(qfa);
  hd.quaternion.copy(Qf.invert().multiply(handQ));
  actor.root.updateMatrixWorld(true);
  return D / (L1 + L2);
}

// ---------------------------------------------------------------- choreography
export function createDishwash(world, cfg) {
  const { kitchen } = world.sets;
  const { tim } = world.actors;
  const held = world.held || {};
  const C = cfg.cues;
  if (!C.stackSteps || !kitchen.washPlates?.length) return null;
  const P = C.stackSteps[1] - C.stackSteps[0];
  const leave = [C.stackSteps[0] - P, ...C.stackSteps]; // plate in hand at the start, stack 5, 4, 3
  const D = C.timDeflate;
  const sink = cfg.sinkSpot; // { position, yaw }
  const O = sink.position.clone();
  const qYaw = new THREE.Quaternion().setFromAxisAngle(AX.y, sink.yaw || 0);
  const local = (x, y, z) => V(x, y, z).applyQuaternion(qYaw).add(O);
  const toLocal = (p) => p.clone().sub(O).applyQuaternion(qYaw.clone().invert());
  const wy = kitchen.waterY;
  const topY = kitchen.spot('plate_stack')?.position.y ?? 0.5;
  const spout = V();
  if (kitchen.spout) kitchen.spout.getWorldPosition(spout);
  else spout.copy(local(-0.06, 0.65, 0.31));
  const fwd = V(0, 0, 1).applyQuaternion(qYaw), left = V(1, 0, 0).applyQuaternion(qYaw);

  // key plate poses (frame = plate bottom centre, +y = face normal)
  const shoulderL = local(0.17, 0.77, 0.09);
  const stackC = kitchen.stackBase[0] ?? local(0.275, topY, 0.29);
  const sd = shoulderL.clone().sub(stackC).setY(0).normalize();
  const Q_STACK = rot(['y', Math.atan2(-sd.z, sd.x) / DEG]); // grip rim faces Tim's left shoulder
  const Q_FLAT = new THREE.Quaternion();
  const Q_SCRUB = rot(['x', 14], ['z', 6]).premultiply(qYaw); // face tipped toward the camera, held rim up
  const Q_RINSE = rot(['x', 8], ['z', 24]).premultiply(qYaw);
  const Q_RACK = rot(['y', 45], ['z', 90]).premultiply(qYaw); // upright, face to -x, grip rim up-and-near
  const Q_SUNK = rot(['y', 28], ['x', 5]).premultiply(qYaw);
  const W = local(0.0, wy + 0.022, 0.27); // scrub pose
  const ABOVE = W.clone().add(V(0, 0.05, 0)).addScaledVector(fwd, -0.01);
  const LOW = W.clone().add(V(0, -0.03, 0));
  const RINSE = V(spout.x, wy + 0.062, spout.z).addScaledVector(left, 0.058); // stream lands on the plate's low side
  const SUNK = W.clone().add(V(0, -0.046, 0)).addScaledVector(left, 0.02).addScaledVector(fwd, 0.035);
  const rackPose = (j) => {
    const sp = kitchen.spot(`rack_${j + 1}`);
    const p = sp ? sp.position.clone() : local(0.43 + 0.04 * j, topY + 0.016, 0.32);
    return p.add(V(0, PLATE_R, 0)).addScaledVector(left, 0.009);
  };
  const stackPose = (i) => kitchen.stackBase[6 - i] ?? stackC; // plate i = 1, 2, 3 -> stack index 5, 4, 3

  function platePose(i, t, noDeflate = false) {
    const u = t - leave[i];
    const out = { pos: null, quat: null, dirt: 1, suds: 0, held: false, u };
    if (i > 0 && u < 0) {
      out.pos = stackPose(i).clone();
      out.quat = Q_STACK.clone();
      return out;
    }
    const uu = i === 0 ? Math.max(u, T_SCRUB) : u;
    out.held = uu < T_PLACED;
    if (uu < T_LIFT) {
      const k = ease.inOutCubic(uu / T_LIFT);
      out.pos = lerpV(stackPose(i), ABOVE, k).add(V(0, 0.045 * Math.sin(Math.PI * k), 0));
      out.quat = slerpQ(Q_STACK, Q_FLAT.clone().premultiply(qYaw), ease.inOutSine(uu / T_LIFT));
    } else if (uu < T_DIP) {
      out.pos = lerpV(ABOVE, LOW, ease.inQuad((uu - T_LIFT) / (T_DIP - T_LIFT)));
      out.quat = qYaw.clone();
    } else if (uu < T_SCRUB) {
      const k = ease.outCubic((uu - T_DIP) / (T_SCRUB - T_DIP));
      out.pos = lerpV(LOW, W, k);
      out.quat = slerpQ(qYaw, Q_SCRUB, k);
    } else if (uu < T_RINSE) {
      const ph = 2 * Math.PI * SCRUB_HZ * (uu - T_SCRUB);
      // the plate gives a little against the sponge (reaction, opposite the stroke)
      out.pos = W.clone().addScaledVector(left, -0.003 * Math.cos(ph)).addScaledVector(fwd, -0.0025 * Math.sin(ph)).add(V(0, -0.0015 * Math.sin(ph), 0));
      out.quat = Q_SCRUB.clone().multiply(rot(['x', 1.5 * Math.sin(ph - 0.6)]));
    } else if (uu < T_HOLD) {
      const k = ease.inOutCubic((uu - T_RINSE) / (T_HOLD - T_RINSE));
      out.pos = lerpV(W, RINSE, k).add(V(0, 0.012 * Math.sin(Math.PI * k), 0));
      out.quat = slerpQ(Q_SCRUB, Q_RINSE, k);
    } else if (uu < T_RACK) {
      const k = (uu - T_HOLD) / (T_RACK - T_HOLD);
      // turned under the stream so the water runs over the whole face
      out.pos = RINSE.clone().addScaledVector(left, 0.006 * Math.sin(k * Math.PI * 2)).addScaledVector(fwd, 0.006 * Math.sin(k * Math.PI * 2 + 1.2));
      out.quat = Q_RINSE.clone().multiply(rot(['x', 7 * Math.sin(k * Math.PI * 2)]));
    } else if (uu < T_PLACED) {
      const k = (uu - T_RACK) / (T_PLACED - T_RACK);
      const R = rackPose(Math.min(i, 2));
      const above = R.clone().add(V(0, 0.07, 0)).addScaledVector(fwd, -0.015);
      if (k < 0.72) {
        const kk = ease.inOutCubic(k / 0.72);
        out.pos = lerpV(RINSE, above, kk).add(V(0, 0.06 * Math.sin(Math.PI * kk), 0));
      } else out.pos = lerpV(above, R, ease.inOutQuad((k - 0.72) / 0.28));
      out.quat = slerpQ(Q_RINSE, Q_RACK, ease.inOutCubic(Math.min(1, k / 0.72)));
    } else {
      out.pos = rackPose(Math.min(i, 2));
      out.quat = Q_RACK.clone();
    }
    out.dirt = uu < T_SCRUB ? 1 : uu < T_RINSE ? 1 - 0.9 * smoothstep(T_SCRUB + 0.02, T_RINSE - 0.03, uu) : 0.1 * (1 - smoothstep(T_HOLD - 0.02, T_RACK - 0.03, uu));
    out.suds = (0.55 * smoothstep(T_DIP, T_SCRUB, uu) + 0.45 * smoothstep(T_SCRUB, T_RINSE, uu)) * (1 - smoothstep(T_HOLD, T_RACK - 0.02, uu));
    // the deflate: the plate in hand is let go and slides back into the water
    if (!noDeflate && i === leave.length - 1 && t >= D + 0.04) {
      const rel = platePose(i, D + 0.04, true);
      const s = clamp((t - D - 0.04) / 0.42);
      out.pos = lerpV(rel.pos, SUNK, ease.inQuad(s));
      out.quat = slerpQ(rel.quat, Q_SUNK, ease.inOutSine(s));
      out.dirt = rel.dirt;
      out.suds = rel.suds * (1 - smoothstep(0.2, 0.9, s));
      out.held = false;
    }
    return out;
  }
  const releaseT = D + 0.04;
  // the splash when the slid plate's face goes under (the ease-in crossing time, solved once)
  const kCross = clamp((W.y + FACE_Y - wy) / (W.y - SUNK.y));
  const plateSplashT = releaseT + 0.42 * Math.sqrt(kCross);
  const spongeDropT = D + 0.12;
  const spongeSplashT = spongeDropT + 0.2;

  const splashes = [];
  leave.forEach((L, i) => {
    const p = LOW.clone().setY(wy);
    splashes.push({ t0: L + T_DIP - 0.01, pos: p, size: 1 });
    void i;
  });
  splashes.push({ t0: plateSplashT, pos: SUNK.clone().setY(wy), size: 1.15 });
  const spongeRest = local(-0.16, wy + 0.03, 0.30);
  splashes.push({ t0: spongeSplashT, pos: spongeRest.clone().setY(wy), size: 0.7 });
  splashes.sort((a, b) => a.t0 - b.t0);

  // the tap: on just before each rinse, off as the plate leaves for the rack (or on the deflate)
  // (the last plate never gets rinsed: the tap is already running at the beat-4 cut and goes off on the deflate)
  const runs = leave.map((L, i) => ({ on: i === leave.length - 1 ? Math.min(L + 0.66, D - 0.14) : L + 0.66, off: Math.min(L + T_RACK - 0.005, D + 0.05) })).filter((r) => r.on < r.off);
  function stream(t) {
    let r = null;
    for (const x of runs) if (t >= x.on) r = x;
    return r;
  }

  function current(t) {
    let i = 0;
    for (let k = 0; k < leave.length; k++) if (t >= leave[k]) i = k;
    return i;
  }

  // ------------- hand targets (world)
  const poleL = V(1, -0.6, -0.4).applyQuaternion(qYaw).normalize();
  const poleR = V(-1, -0.6, -0.4).applyQuaternion(qYaw).normalize();
  const xAxis = (q) => V(1, 0, 0).applyQuaternion(q);
  const yAxis = (q) => V(0, 1, 0).applyQuaternion(q);
  function gripOf(pose) {
    const pos = GRIP.clone().applyQuaternion(pose.quat).add(pose.pos);
    const out = xAxis(pose.quat); // rim outward
    const n = yAxis(pose.quat);
    const palm = out.clone().negate().addScaledVector(n, -0.25);
    const fingers = fwd.clone().addScaledVector(n, -0.45).addScaledVector(left, 0.1);
    return { pos, q: handQuat(tim, 'L', fingers, palm) };
  }
  function leftTarget(t) {
    const i = current(t);
    const u = t - leave[i];
    if (u >= T_PLACED && i < leave.length - 1) {
      // released in the rack: reach for the next plate on the stack
      const a = gripOf(platePose(i, leave[i] + T_PLACED));
      const b = gripOf(platePose(i + 1, leave[i + 1] - 0.001));
      const k = ease.inOutCubic(clamp((u - T_PLACED) / (P - T_PLACED - 0.03)));
      return { pos: lerpV(a.pos, b.pos, k).add(V(0, 0.035 * Math.sin(Math.PI * k), 0)), q: slerpQ(a.q, b.q, k) };
    }
    return gripOf(platePose(i, Math.min(t, i === leave.length - 1 ? releaseT : Infinity)));
  }
  const idleR = (t) => local(-0.215 + 0.004 * fbm1(t * 0.7, 61), wy + 0.066 + 0.004 * fbm1(t * 0.9, 62), 0.215);
  function rightTarget(t) {
    const i = current(t);
    const u = t - leave[i];
    const uu = i === 0 ? Math.max(u, T_SCRUB - 0.001) : u;
    const pose = platePose(i, Math.min(t, i === leave.length - 1 ? releaseT : Infinity));
    const n = yAxis(pose.quat);
    const ph = 2 * Math.PI * SCRUB_HZ * (uu - T_SCRUB);
    const r = 0.03;
    const onFace = V(-0.012 + r * Math.cos(ph), FACE_Y, 0.012 + 0.8 * r * Math.sin(ph)).applyQuaternion(pose.quat).add(pose.pos);
    const press = 0.0015 * Math.sin(2 * ph);
    const scrubPos = onFace.addScaledVector(n, SPONGE_HALF * 2 + 0.006 - press);
    const fingers = fwd.clone().addScaledVector(left, 0.35 + 0.18 * Math.sin(ph + 0.6));
    const scrubQ = handQuat(tim, 'R', fingers.addScaledVector(n, -fingers.dot(n)), n.clone().negate());
    const idleQ = handQuat(tim, 'R', fwd.clone().addScaledVector(left, 0.3).add(V(0, -0.35, 0)), V(0, -1, 0).addScaledVector(fwd, 0.15));
    const w = smoothstep(T_LIFT + 0.03, T_SCRUB, uu) * (1 - smoothstep(T_RINSE - 0.01, T_RINSE + 0.08, uu));
    return { pos: lerpV(idleR(t), scrubPos, w), q: slerpQ(idleQ, scrubQ, w), scrub: w };
  }
  const restL = local(0.125, topY + 0.016, 0.205), restR = local(-0.15, topY + 0.016, 0.205);
  const restQ = (side) => handQuat(tim, side, fwd.clone().addScaledVector(left, side === 'L' ? -0.25 : 0.25).add(V(0, -0.4, 0)), V(0, -1, 0).addScaledVector(fwd, 0.25));

  return {
    leave,
    splashes,
    workPatch: [W.x, W.z],
    avoid: [W.x, W.z, 0.13, 0.1],

    /** Called inside tim.pose()'s post callback, after every other body layer (torso lean for reach,
     *  then IK on both arms). */
    poseArms(rig, t) {
      let lt = leftTarget(Math.min(t, releaseT));
      let rt = rightTarget(Math.min(t, spongeDropT));
      const wl = cue(t, D + 0.08, 0.45, ease.inOutCubic);
      const wr = cue(t, D + 0.16, 0.45, ease.inOutCubic);
      if (wl > 0) lt = { pos: lerpV(lt.pos, restL, wl), q: slerpQ(lt.q, restQ('L'), wl) };
      if (wr > 0) rt = { pos: lerpV(rt.pos, restR, wr), q: slerpQ(rt.q, restQ('R'), wr) };
      // lean into far reaches (the rack, the rinse): a side bend to the left and a little more pitch
      const ll = toLocal(lt.pos);
      const side = clamp((ll.x - 0.33) / 0.18) * (1 - wl);
      const deep = clamp((ll.z - 0.26) / 0.1) * (1 - wl);
      rig.addRot('torso', 5 * deep * DEG, 0, -9 * side * DEG);
      rig.addRot('neck', -3 * deep * DEG, 0, 6 * side * DEG);
      tim.root.updateMatrixWorld(true);
      solveArm(tim, 'L', lt.pos, lt.q, poleL);
      solveArm(tim, 'R', rt.pos, rt.q, poleR);
    },

    /** Place the plates, sponge, suds, tap stream and splashes (after Tim is posed). */
    update(t) {
      const gl = tim.rig.joint('grip_L');
      const gpos = gl ? gl.getWorldPosition(V()) : null;
      const i0 = current(t);
      kitchen.washPlates.forEach((_, i) => {
        const pose = platePose(i, t);
        // the held plate follows the actual mitten (keeps contact if the IK is clamped)
        if (pose.held && gpos && i === i0) {
          const want = GRIP.clone().applyQuaternion(pose.quat).add(pose.pos);
          const u = pose.u;
          const w = i === 0 ? 1 : smoothstep(0, 0.05, u) * (1 - smoothstep(T_PLACED - 0.06, T_PLACED, u));
          pose.pos.addScaledVector(gpos.clone().sub(want), w);
        }
        kitchen.setPlate(i, { position: pose.pos, quaternion: pose.quat, dirt: pose.dirt, suds: pose.suds });
      });
      // sponge in the right mitten (scour pad facing out of the palm), dropped into the water on the deflate
      const { sponge, spongeSuds, plate } = held;
      if (plate) plate.visible = false;
      if (sponge) {
        const gr = tim.rig.joint('grip_R');
        const hd = tim.rig.joint('hand_R');
        const L0 = hd.position.clone().normalize();
        const P0 = V(-L0.y, L0.x, 0).normalize();
        const T0 = L0.clone().cross(P0);
        const off = new THREE.Matrix4().makeBasis(L0, P0, T0).setPosition(P0.clone().multiplyScalar(SPONGE_HALF + 0.006));
        const inHand = (m) => {
          const M = m.clone().multiply(off);
          const p = V(), q = new THREE.Quaternion(), s = V();
          M.decompose(p, q, s);
          return { p, q };
        };
        let sp;
        if (t < spongeDropT) {
          gr.updateWorldMatrix(true, false);
          sp = inHand(gr.matrixWorld);
        } else {
          const rt = rightTarget(spongeDropT);
          const r0 = inHand(new THREE.Matrix4().compose(rt.pos, rt.q, V(1, 1, 1)));
          const s = clamp((t - spongeDropT) / 0.2);
          const bob = t > spongeSplashT ? 0.004 * Math.exp(-(t - spongeSplashT) * 4) * Math.cos((t - spongeSplashT) * 16) + 0.0012 * fbm1(t * 0.8, 71) : 0;
          sp = { p: lerpV(r0.p, spongeRest, ease.inQuad(s)).add(V(0, bob, 0)), q: slerpQ(r0.q, rot(['y', -20]).premultiply(qYaw), ease.inOutSine(s)) };
        }
        sponge.position.copy(sp.p);
        sponge.quaternion.copy(sp.q);
        sponge.scale.setScalar(1);
        sponge.visible = true;
        if (spongeSuds) {
          // foam on the sponge's front end, puffing up while he scrubs
          const sc = t < spongeDropT ? rightTarget(t).scrub : 0;
          spongeSuds.position.copy(V(0.047, -0.006, 0.004).applyQuaternion(sp.q).add(sp.p));
          spongeSuds.quaternion.copy(sp.q);
          spongeSuds.scale.setScalar(0.75 + 0.45 * sc + 0.05 * Math.sin(t * 9));
          spongeSuds.visible = true;
        }
      }
      // tap stream: falls onto the plate face when the plate is under it, else into the water
      const r = stream(t);
      let hitY = wy;
      const pose = platePose(i0, t);
      const n = yAxis(pose.quat);
      const c = pose.pos.clone().addScaledVector(n, FACE_Y);
      const dx = spout.x - c.x, dz = spout.z - c.z;
      if (Math.hypot(dx, dz) < PLATE_R * 0.92 && n.y > 0.3) hitY = c.y - (n.x * dx + n.z * dz) / n.y;
      kitchen.setStream({ t, on: r ? r.on : Infinity, off: r ? r.off : Infinity, hitY });
      kitchen.setSplashes(t, splashes);
    },
  };
}
