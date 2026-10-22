// Director: drives the whole world from a scene config as a pure function of t.
// A config supplies the cue times, bulb curve, set per time and the camera; the choreography here is
// shared by Scene 001 (13 s) and the beat-2 locked clip (8 s).
import * as THREE from 'three';
import { DEG, clamp, cue, ease, fbm1, lerp, noise1, smoothstep, spring, wobble } from '@infra/math.js';
import { setFace } from '../actors/faces.js';
import { createDishwash } from './dishwash.js';

const V3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);
export const blinking = (t, times = [], dur = 0.13) => times.some((b) => t >= b && t < b + dur);

export function orbit(target, azDeg, elDeg, dist) {
  const a = azDeg * DEG, e = elDeg * DEG;
  return [target[0] + dist * Math.cos(e) * Math.sin(a), target[1] + dist * Math.sin(e), target[2] + dist * Math.cos(e) * Math.cos(a)];
}
export const mix3 = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];

/** door: swings open in ~0.25 s, overshoots, rings on its spring (step response, pure in lt). */
export function doorSpring(lt) {
  if (lt <= 0) return 0;
  const w = 2 * Math.PI * 2.2, z = 0.42, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * lt) * (Math.cos(wd * lt) + ((z * w) / wd) * Math.sin(wd * lt));
}

const _lionHeadUp = new THREE.Vector3(0, 1.0, 0);
const _coolA = new THREE.Color();
const _coolB = new THREE.Color();
const _qa = new THREE.Quaternion();
const _qb = new THREE.Quaternion();
const _qc = new THREE.Quaternion();
const _va = new THREE.Vector3();
const _vb = new THREE.Vector3();
const _vc = new THREE.Vector3();
/** Swing `jointName` (in world space) so that the joint→tip vector turns toward `target` by `weight`.
 *  Cheap one-bone aim used to make a pointing arm actually aim; pure (reads only the current pose). */
export function aimJoint(actor, jointName, tipName, target, weight = 1) {
  const j = actor.rig.joint(jointName), tip = actor.rig.joint(tipName);
  if (!j || !tip || weight <= 0) return;
  actor.root.updateMatrixWorld(true);
  j.getWorldPosition(_va);
  tip.getWorldPosition(_vb);
  const from = _vb.sub(_va).normalize();
  const to = _vc.copy(target).sub(_va).normalize();
  _qa.setFromUnitVectors(from, to);
  _qa.slerp(_qc.identity(), 1 - weight); // partial swing
  j.parent.getWorldQuaternion(_qb);
  // local' = parent^-1 * swing * parent * local
  const swingLocal = _qb.clone().invert().multiply(_qa).multiply(_qb);
  j.quaternion.premultiply(swingLocal);
  actor.root.updateMatrixWorld(true);
}

export function createDirector(world, cfg) {
  const { sets, actors, bulb, fx, held } = world;
  const { office, kitchen } = sets;
  const { tim, lioness, guoguo } = actors;
  const C = cfg.cues;
  const spot = (set, name, fallback, yawDeg = 0) => set.spot(name) || { position: V3(fallback), yaw: yawDeg * DEG };
  const S = {
    deskSeat: spot(office, 'desk_seat', [0.85, 0, -0.5]),
    doorOut: spot(office, 'doorway_out', [-3.25, 0, -0.7], 90),
    doorIn: spot(office, 'doorway_in', [-1.15, 0, -0.1], 90),
    shelfTop: spot(office, 'shelf_top', [-0.26, 1.04, -1.72], 15),
    sink: spot(kitchen, 'sink', [0.3, 0, -0.48]),
    ggKitchen: spot(kitchen, 'guoguo', [1.05, 0.62, -1.62], -15),
  };
  // staging cheat: GuoGuo sits further along the shelf top so he peeks out beside Tim in the office shots
  if (cfg.ggOfficeNudge) S.shelfTop = { ...S.shelfTop, position: S.shelfTop.position.clone().add(V3(cfg.ggOfficeNudge)) };
  // staging cheat: nudge Tim along the sink so the scrubbed plate is not hidden behind the faucet
  const sinkSpot = S.sink;
  if (cfg.sinkNudge) S.sink = { ...sinkSpot, position: sinkSpot.position.clone().add(V3(cfg.sinkNudge)) };
  // beat 4 (after a camera cut): Tim has slumped a step along the counter, clear of the faucet
  S.sink4 = cfg.sinkNudge4 ? { ...sinkSpot, position: sinkSpot.position.clone().add(V3(cfg.sinkNudge4)) } : S.sink;
  const sinkAt = (t) => (cfg.sink4Start !== undefined && t >= cfg.sink4Start ? S.sink4 : S.sink);
  const STRIDE = world.lionStride ?? 0.66; // metres per walk cycle (2 steps) — lioness meta walk_stride_per_cycle_m
  const hingeWorld = new THREE.Vector3();
  if (office.door) office.door.node.getWorldPosition(hingeWorld);
  else hingeWorld.set(-2.55, 0, -1.1);
  const pathDir = S.doorIn.position.clone().sub(S.doorOut.position).normalize();
  const doorSwingAt = (lt) => 92 * DEG * doorSpring(lt); // door angle (rad) vs time since it bursts open

  const tmp = new THREE.Vector3();
  const tmp2 = new THREE.Vector3();
  const timHead = new THREE.Vector3();
  const lionHead = new THREE.Vector3();
  // canonical head positions (pose at a reference time) used to steady the bulb anchor — computed
  // once here so no frame depends on which frame was rendered before it (determinism)
  const restHead = {};
  {
    const d = S.deskSeat.position, k = S.sink.position;
    tim.place(d.x, d.y, d.z, S.deskSeat.yaw);
    tim.pose([{ clip: 'sit_type', time: 0, loop: true }]);
    restHead.office = tim.headWorld(new THREE.Vector3());
    tim.place(k.x, k.y, k.z, S.sink.yaw);
    tim.pose([{ clip: 'stand_wash', time: 0, loop: true }]);
    restHead.kitchen = tim.headWorld(new THREE.Vector3());
    restHead.kitchen4 = restHead.kitchen.clone().add(S.sink4.position.clone().sub(S.sink.position));
  }
  // the dish cycle (beats 3-4): plates stack -> hand -> rack, IK arms, tap, splashes (pure in t)
  const dish = C.stackSteps ? createDishwash(world, { cues: C, sinkSpot: S.sink }) : null;

  function update(t, camera) {
    const inOffice = cfg.setAt(t) === 'office';
    if (cfg.mood && world.look?.setMood) world.look.setMood(cfg.mood(t));
    // ---------------- sets
    const doorAngle = 92 * DEG * doorSpring(t - C.doorOpen);
    const seatRy = (cfg.seatTurnDeg ?? -30) * DEG * cue(t, C.timTurn, 0.24, (x) => ease.outBack(x, 1.6));
    const seatPz = -0.1 * cue(t, C.timShock + 0.05, 0.35, ease.outCubic);
    const tt = Math.min(t, C.timShock);
    const typed = 90 + 16 * tt + 3 * Math.sin(tt * 7);
    office.update({ t, visible: inOffice, doorAngle, seatRy, seatPz, typed });
    // kitchen: foam, bubbles (the dish cycle itself is placed in updateHeld, after Tim is posed)
    if (C.stackSteps) kitchen.update({ t, visible: !inOffice, avoid: dish?.avoid });
    else kitchen.update({ t, visible: false });

    // ---------------- Tim
    let timExpr;
    if (inOffice) {
      const base = S.deskSeat.position;
      const yaw = S.deskSeat.yaw + seatRy;
      tim.root.position.set(base.x, base.y, base.z + seatPz);
      tim.root.rotation.set(0, yaw, 0);
      const shockW = cue(t, C.timShock, 0.06, ease.linear);
      tim.pose(
        [
          { clip: 'sit_type', time: t, loop: true, weight: 1 },
          { clip: 'sit_shock', time: t - C.timShock, weight: shockW },
        ],
        (rig) => {
          if (t >= C.timShock + 0.15) {
            const k = 1 - 0.45 * clamp((t - C.timShock - 0.2) / 2.2);
            const n = (f, s) => noise1(t * f, s);
            rig.addRot('torso', n(9, 1) * 1.4 * DEG * k, 0, n(8, 2) * 1.6 * DEG * k);
            rig.addRot('neck', n(11, 3) * 2.0 * DEG * k, n(7, 4) * 2.5 * DEG * k, 0);
            for (const s of ['L', 'R']) {
              rig.addRot(`forearm_${s}`, 0, 0, n(12, s === 'L' ? 5 : 6) * 7 * DEG * k);
              rig.addRot(`hand_${s}`, 0, 0, n(15, s === 'L' ? 7 : 8) * 14 * DEG * k);
            }
          }
          if (cfg.shockHop && t >= C.timShock) {
            // the "take": a quick hop off the seat with a lean back, landing with a damped settle
            const lt = t - C.timShock;
            const hop = lt < 0.2 ? Math.sin((lt / 0.2) * Math.PI) : -0.35 * wobble(lt - 0.2, 3.2, 7);
            rig.addPos('hips', 0, cfg.shockHop * hop, 0);
            rig.addRot('torso', -7 * DEG * spring(lt, 2.4, 0.4) * (1 - 0.5 * cue(t, C.timShock + 0.9, 0.8)), 0, 0);
          }
          if (t >= C.timTurn) {
            // look toward the lioness (her head ~1.0 m above her path position at this t)
            tmp.copy(lionPathAt(t).pos).add(_lionHeadUp);
            const want = clamp(tim.yawTo(tmp), -70 * DEG, 70 * DEG);
            rig.addRot('neck', 0, 0.45 * want * cue(t, C.timTurn + 0.05, 0.3), 0);
          } else {
            // focused: tiny glances at the screen; the face is lifted toward the lens (cfg.focusLift)
            rig.addRot('neck', (2 + 1.5 * fbm1(t * 0.8, 9) - (cfg.focusLift ?? 0)) * DEG, 2 * fbm1(t * 0.5, 10) * DEG, 0);
            if (cfg.focusLean) rig.addRot('torso', cfg.focusLean * DEG, 0, 0);
          }
        },
      );
      timExpr = t < C.timShock ? (t >= C.timTurn ? 'deadfish' : 'focused') : 'shock';
    } else {
      const sk = sinkAt(t);
      const p = sk.position;
      tim.root.position.set(p.x, p.y, p.z);
      tim.root.rotation.set(0, sk.yaw, 0);
      const deflate = cue(t, C.timDeflate, 0.4, ease.inOutCubic);
      tim.pose(
        [
          { clip: 'stand_wash', time: t - cfg.kitchenStart, loop: true, weight: 1 },
          { clip: 'stand_sink_idle', time: t - C.timDeflate, loop: true, weight: deflate },
        ],
        (rig) => {
          rig.addRot('neck', 2 * fbm1(t * 0.4, 21) * DEG, 3 * fbm1(t * 0.3, 22) * DEG, 0);
          // glum while scrubbing: face lifted a little toward the lens so the expression reads
          rig.addRot('neck', -(cfg.washLift ?? 0) * DEG * (1 - deflate), 0, 0);
          // keep the deflated face readable: the body slumps, the head lifts a little
          rig.addRot('neck', -(cfg.slumpLift ?? 12) * DEG * deflate, 0, 0);
          if (cfg.slump) {
            // the deflate "sigh": a small inhale lift (anticipation), then the drop with a soft overshoot
            const st = t - C.timDeflate;
            const inhale = st > 0 && st < 0.35 ? Math.sin((st / 0.35) * Math.PI) : 0;
            const drop = st > 0.2 ? spring(st - 0.2, 1.6, 0.45) : 0;
            const settle = 1 + 0.04 * fbm1(t * 0.35, 31); // slow breathing, not a sine
            const s = cfg.slump;
            rig.addRot('torso', (s.torso * drop * settle - 3 * inhale) * DEG, 0, 0);
            rig.addRot('neck', -s.torso * 0.7 * drop * DEG, 0, 0);
            rig.addPos('hips', 0, -s.sink * drop, 0);
            for (const side of ['L', 'R']) {
              const sgn = side === 'L' ? 1 : -1;
              rig.addRot(`upperarm_${side}`, 0, 0, sgn * (s.arms * drop - 4 * inhale) * DEG);
            }
          }
          // the dish cycle: reach lean + IK arms onto the plate / sponge / counter edge (last layer)
          if (dish) dish.poseArms(rig, t);
        },
      );
      timExpr = t < C.timDeflate ? 'glum' : 'deflated';
    }
    const timBlink = timExpr !== 'shock' && blinking(t, C.timBlinks);
    setFace(tim.model, 'tim', timExpr + (timBlink ? '_blink' : ''));
    fx.sweat.update({ lt: inOffice ? t - C.timShock : -1, head: tim.head });
    tim.headWorld(timHead);
    const anchor = restHead[inOffice ? 'office' : sinkAt(t) === S.sink ? 'kitchen' : 'kitchen4'].clone().lerp(timHead, 0.65);

    updateHeld(t, inOffice);

    // ---------------- bulb
    bulb.update({ t, anchor, level: cfg.bulbLevel(t), outT: t >= C.bulbOut ? t - C.bulbOut : null, camera, visible: true });

    updateLioness(t, inOffice);
    updateGuoGuo(t, inOffice);

    // ---------------- FX
    const chest = tim.jointWorld('torso', tmp2).lerp(timHead, cfg.glowOnHead ?? 0.55);
    const G = cfg.fxLook || {};
    const warm = cfg.glow && inOffice ? (G.warm ?? 0.3) * cue(t, 0, 0.5) * (1 - cue(t, C.doorOpen, 0.3)) : 0;
    fx.warmGlow.update({ center: chest, camera, color: G.warmColor ?? '#ffcf8a', amount: warm, size: G.warmSize ?? 2.5, t });
    const cool = cfg.glow && !inOffice ? (G.cool ?? 0.22) * cue(t, cfg.kitchenStart, 0.6) * (t > C.bulbOut ? 1 - 0.3 * cue(t, C.bulbOut, 1.0) : 1) : 0;
    // the idea fading: across beats 3-4 the cool halo shrinks and greys out
    const coolK = inOffice ? 0 : smoothstep(0.3, 1, clamp((t - cfg.kitchenStart) / Math.max(0.01, cfg.duration - cfg.kitchenStart)));
    const coolCol = _coolA.set(G.coolColor ?? '#9fbde6').lerp(_coolB.set(G.coolColorEnd ?? G.coolColor ?? '#9fbde6'), coolK);
    const coolSize = lerp(G.coolSize ?? 2.4, G.coolSizeEnd ?? G.coolSize ?? 2.4, coolK);
    fx.coolGlow.update({ center: chest, camera, color: coolCol, amount: cool, size: coolSize, t, blend: G.coolBlend ?? 'additive', back: G.coolBack ?? 0.75, ring: !!G.coolRing });
    lioness.headCenter(lionHead);
    const hideFx = cfg.kitchenStart ?? Infinity;
    fx.bubble.update({ t, t0: C.bubble, head: lionHead, camera, jabs: C.jabs, hideAt: hideFx });
    fx.anger.update({ t, t0: C.anger ?? Infinity, head: lionHead, camera, hideAt: hideFx });
    lioness.root.getWorldPosition(tmp);
    fx.speed.update({ t, t0: C.speedLines ?? Infinity, dur: G.speedDur ?? 0.55, origin: tmp.clone(), dir: pathDir, camera });
    // dust: a floor burst swept along the door's swing arc + a gust through the doorway + motes in the air
    const into = pathDir.clone().setY(0).normalize();
    const across = new THREE.Vector3(-into.z, 0, into.x);
    const doorMid = hingeWorld.clone().setY(0);
    const toOut = S.doorOut.position.clone().sub(doorMid);
    const sgn = Math.sign(toOut.dot(across) || 1);
    doorMid.addScaledVector(across, 0.425 * sgn);
    // closed door: hinge -> free edge (snapped to the wall axis); a +Y rotation swings it into the room
    const doorDir = across.clone().multiplyScalar(sgn);
    if (Math.abs(doorDir.z) >= Math.abs(doorDir.x)) doorDir.set(0, 0, Math.sign(doorDir.z));
    else doorDir.set(Math.sign(doorDir.x), 0, 0);
    const swingInto = new THREE.Vector3(doorDir.z, 0, -doorDir.x);
    fx.dust.update({ lt: inOffice ? t - C.doorOpen : -1, hinge: hingeWorld.clone().setY(0), doorDir, into: swingInto, center: doorMid, along: across, swingAt: doorSwingAt });
    fx.card.update({ t, t0: C.card ?? Infinity, x: 0.64, y: 0.3 });
  }

  // the lioness's walk along her path, as a pure function of t (also used by Tim's look, which is posed
  // before her: reading her posed head there would depend on the previously rendered frame)
  function lionPathAt(t) {
    const P1 = S.doorIn.position;
    const P0 = cfg.lionPath ? P1.clone().addScaledVector(pathDir, -cfg.lionPath) : S.doorOut.position;
    const mt = clamp((t - C.lionMove) / C.lionMoveDur);
    const along = cfg.lionPath ? smoothstep(0, 1, mt) : ease.outCubic(mt);
    return { pos: P0.clone().lerp(P1, along), dist: P0.distanceTo(P1) * along };
  }

  function updateLioness(t, inOffice) {
    lioness.root.visible = inOffice;
    if (!inOffice) return;
    // cfg.lionPath: walk only this far (m) to doorway_in, starting just outside the door (a shorter,
    // slower move so the planted-foot walk reads); default: the full doorway_out -> doorway_in path
    const { pos, dist } = lionPathAt(t);
    const yaw = lerp(90 * DEG, (cfg.lionCheatDeg ?? 45) * DEG, cue(t, C.lionTurn, 0.3, (x) => ease.outBack(x, 1.3)));
    lioness.root.position.copy(pos);
    lioness.root.rotation.set(0, yaw, 0);
    const walkW = t < C.lionMove ? 0 : 1 - cue(t, C.lionMove + C.lionMoveDur * (cfg.lionPath ? 0.8 : 0.75), cfg.lionPath ? 0.25 : 0.3, ease.inOutSine);
    const walkTime = (dist / STRIDE) * (lioness.rig.clipDuration('walk') || 1);
    const braceW = cue(t, C.lionBrace, 0.12) * (1 - cue(t, C.lionBrace + 0.3, 0.35));
    lioness.pose(
      [
        { clip: 'stand', time: t, loop: true, weight: 1 },
        { clip: 'listen', time: t - C.lionListen, weight: t >= C.lionListen ? 1 : 0 },
        { clip: 'walk', time: walkTime, loop: true, weight: walkW },
        { clip: 'brace', time: t - C.lionBrace, weight: braceW * 0.9 },
        { clip: 'akimbo', time: t - C.lionAkimbo, weight: t >= C.lionAkimbo ? 1 : 0 },
        { clip: 'point', time: t - C.lionPoint, weight: t >= C.lionPoint ? 1 : 0 },
      ],
      (rig) => {
        const st = t - (C.lionMove + C.lionMoveDur);
        if (st > 0 && st < 0.8) rig.addPos('hips', 0, -0.018 * Math.exp(-6 * st) * Math.cos(st * 18), 0);
        tim.headWorld(tmp);
        const want = clamp(lioness.yawTo(tmp), -60 * DEG, 60 * DEG);
        // cheated toward the camera: only a slight head turn toward Tim (the point does the aiming)
        rig.addRot('neck', 0, ((cfg.lionNeckTurn ?? 0.12) * want + (cfg.lionNeckYaw ?? 0) * DEG) * cue(t, C.lionTurn, 0.3), 0);
        if (cfg.lionAim && t >= C.lionPoint) {
          const pt = t - C.lionPoint;
          const A = cfg.lionAim;
          // anticipation (pull back + lean away) -> thrust (lean in, overshoot) -> jabs (sharp impulses)
          const wind = pt < 0.12 ? Math.sin((pt / 0.12) * Math.PI * 0.5) : Math.max(0, 1 - (pt - 0.12) / 0.08);
          const thrust = pt > 0.12 ? spring(pt - 0.12, 2.4, 0.42) : 0;
          let jab = 0;
          for (const j of C.jabs || []) {
            const d = t - j;
            if (d > -0.06 && d < 0.5) jab += d < 0 ? 1 + d / 0.06 : Math.exp(-d * 10) * Math.cos(d * 22);
          }
          rig.addRot('body', (A.lean * thrust + A.jabLean * jab - 4 * wind) * DEG, 0, 0);
          rig.addRot('neck', (-A.lean * 0.6 * thrust - 2 * jab) * DEG, 0, 0);
          // aim the arm at Tim's head: two CCD passes (shoulder, elbow, shoulder) eased in with the thrust,
          // so the arm straightens into a clear point; each jab flicks the finger up and back down
          const aimAt = tmp.clone().add(new THREE.Vector3(0, (A.up ?? 0.05) + (A.jabFlick ?? 0) * jab, 0));
          const w = clamp(thrust * 1.05) * (A.weight ?? 1);
          const tip = A.tip || 'finger_R';
          aimJoint(lioness, 'upperarm_R', tip, aimAt, w);
          aimJoint(lioness, 'forearm_R', tip, aimAt, w * 0.85);
          aimJoint(lioness, 'upperarm_R', tip, aimAt, w);
        }
      },
    );
    const expr = t < C.lionPoint ? 'stern' : 'angry';
    setFace(lioness.model, 'lioness', expr + (blinking(t, C.lionBlinks, 0.12) ? '_blink' : ''));
  }

  function updateGuoGuo(t, inOffice) {
    const sp = inOffice ? S.shelfTop : S.ggKitchen;
    guoguo.root.position.copy(sp.position);
    guoguo.root.rotation.set(0, sp.yaw, 0);
    const startledT = t - C.doorOpen;
    const startledW = inOffice && startledT >= 0 ? 1 - cue(t, C.doorOpen + 1.55, 0.3) : 0;
    const flinchT = inOffice ? t - (C.timShock + 0.03) : t - (C.bulbOut + 0.04);
    const flinchW = flinchT >= 0 && flinchT < 0.8 ? 0.65 : 0;
    tim.headWorld(tmp);
    let lookYaw = guoguo.yawTo(tmp);
    if (inOffice && t >= C.doorOpen) {
      const doorYaw = guoguo.yawTo(hingeWorld);
      const lionYaw = guoguo.yawTo(lioness.root.position);
      lookYaw = lerp(lerp(lookYaw, doorYaw, cue(t, C.doorOpen, 0.25)), lionYaw, cue(t, C.lionMove + 0.5, 0.4));
      lookYaw = lerp(lookYaw, guoguo.yawTo(tmp), cue(t, C.timShock + 0.1, 0.5) * 0.6);
    }
    lookYaw = clamp(lookYaw, -55 * DEG, 55 * DEG);
    guoguo.pose(
      [
        { clip: 'seated_idle', time: t, loop: true, weight: 1 },
        { clip: 'startled', time: startledT, weight: startledW },
        { clip: 'flinch', time: flinchT, weight: flinchW },
      ],
      (rig) => rig.addRot('head', inOffice ? 0 : 6 * DEG, lookYaw * 0.6, inOffice ? 0 : -9 * DEG),
    );
    const wide = inOffice && t >= C.doorOpen && t < C.doorOpen + 1.15;
    for (const w of guoguo.wide || []) w.visible = wide;
  }

  const plateBasin = new THREE.Vector3();
  function updateHeld(t, inOffice) {
    const { plate, sponge, spongeSuds } = held;
    const show = !inOffice;
    for (const p of [plate, sponge, spongeSuds]) if (p) p.visible = show;
    if (!show) return;
    if (dish) {
      dish.update(t); // plates stack -> hand -> rack, sponge, tap stream, splashes
      return;
    }
    const gl = tim.rig.joint('grip_L') || tim.rig.joint('hand_L');
    const gr = tim.rig.joint('grip_R') || tim.rig.joint('hand_R');
    const drop = cue(t, C.timDeflate - 0.02, 0.38, ease.inQuad);
    if (kitchen.spout) {
      kitchen.spout.getWorldPosition(plateBasin);
      plateBasin.add(new THREE.Vector3(0, -0.13, -0.1));
    } else plateBasin.set(S.sink.position.x, 0.5, S.sink.position.z + 0.5);
    const g = cfg.grips || {};
    if (plate && gl) {
      gl.updateWorldMatrix(true, false);
      const m = new THREE.Matrix4().copy(gl.matrixWorld);
      const po = g.plate || { p: [0, 0, 0.02], r: [-0.95, 0, 0.15] };
      m.multiply(new THREE.Matrix4().compose(V3(po.p), new THREE.Quaternion().setFromEuler(new THREE.Euler(...po.r)), new THREE.Vector3(1, 1, 1)));
      m.decompose(plate.position, plate.quaternion, plate.scale);
      if (drop > 0) {
        plate.position.lerp(plateBasin, drop);
        plate.quaternion.slerp(new THREE.Quaternion(), drop);
        plate.scale.setScalar(1 - 0.25 * drop);
      }
      plate.visible = drop < 0.999;
    }
    if (sponge && gr) {
      gr.updateWorldMatrix(true, false);
      const m = new THREE.Matrix4().copy(gr.matrixWorld);
      const so = g.sponge || { p: [0, -0.01, 0.025], r: [0, 0, 0] };
      m.multiply(new THREE.Matrix4().compose(V3(so.p), new THREE.Quaternion().setFromEuler(new THREE.Euler(...so.r)), new THREE.Vector3(1, 1, 1)));
      m.decompose(sponge.position, sponge.quaternion, sponge.scale);
      if (drop > 0) {
        sponge.position.lerp(plateBasin.clone().add(new THREE.Vector3(0.08, 0.02, 0)), drop);
        sponge.scale.setScalar(1 - 0.3 * drop);
      }
      sponge.visible = drop < 0.999;
      if (spongeSuds) {
        spongeSuds.position.copy(sponge.position).add(new THREE.Vector3(0, 0.03, 0));
        spongeSuds.quaternion.identity();
        spongeSuds.scale.setScalar(Math.max(0.001, (1 + 0.08 * Math.sin(t * 9)) * (1 - drop)));
        spongeSuds.visible = drop < 0.999;
      }
    }
  }

  return {
    id: cfg.id,
    title: cfg.title,
    update,
    duration: cfg.duration,
    fps: cfg.fps,
    beats: cfg.beats,
    cues: C,
    camera: cfg.camera,
    stills: cfg.stills,
    beatAt: (t) => cfg.beats.find((b) => t < b.end) || cfg.beats[cfg.beats.length - 1],
  };
}
