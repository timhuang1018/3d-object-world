// Scene 001 · Locked in → the lioness → dishes → the idea fades   (13 s, 4 beats, 30 fps)
// Cue times, bulb curve and cameras from docs/scene-spec.md ("Timeline", "Beat-level cues", "Cameras").
// Everything is a pure function of scene time t (seconds).
import { Color } from 'three';
import { DEG, clamp, cue, ease, lerp, noise1, rng, smootherstep, smoothstep, spring } from '@infra/math.js';
import { createDirector, mix3, orbit } from './director.js';

const B2 = 3.5, B3 = 6.2, B4 = 9.7, END = 13.0;

export const BEATS = [
  { id: 1, name: 'Locked in', start: 0.0, end: B2, set: 'office', camera: 'front34_push', narration: 'I was locked in, building an app with my agent…' },
  { id: 2, name: 'Break-in', start: B2, end: B3, set: 'office', camera: 'two_shot', narration: '…then the lioness arrived.' },
  { id: 3, name: 'Dishes', start: B3, end: B4, set: 'kitchen', camera: 'side_truck', narration: 'So I did the dishes.' },
  { id: 4, name: 'Idea gone', start: B4, end: END, set: 'kitchen', camera: 'close_push', narration: 'And the idea? Gone.' },
];

export const CUES = {
  timBlinks: [1.25, 3.02, 7.45, 8.95, 11.85],
  lionListen: 3.05,
  doorOpen: B2 + 0.05, // door opens (0.25 s) — spring ring + dust
  lionBrace: B2 - 0.07,
  lionMove: B2 + 0.1, // from just outside the door to doorway_in (lionPath m, 0.9 s, smoothstep, planted walk)
  lionMoveDur: 0.9,
  speedLines: B2 + 0.12,
  timTurn: B2 + 0.22,
  timShock: B2 + 0.25, // sit_shock (0.2 s, ease back)
  bulbFlicker: B2 + 0.35,
  bubble: B2 + 1.0, // bubble (dishes + bang) and the anger mark
  anger: B2 + 1.0,
  lionTurn: B2 + 0.92, // she settles at doorway_in at B2 + 1.0, then turns, akimbo, points
  lionAkimbo: B2 + 1.0,
  lionPoint: B2 + 1.05,
  lionBlinks: [2.4, 5.55],
  stackSteps: [B3 + 3.5 / 6, B3 + 3.5 / 2, B3 + (3.5 * 5) / 6], // stack 6 -> 3, linear over 3.5 s
  timDeflate: B4 + 0.1, // stand_sink_idle / deflated (0.4 s)
  bulbBlink: B4 + 0.65,
  bulbOut: B4 + 0.9,
  card: B4 + 1.6, // ✗-bulb card at screen (0.64, 0.30)
};
CUES.jabs = [CUES.lionPoint + 0.42, CUES.lionPoint + 0.66];

// Beat-2 flicker (0.35–0.85): seeded table frozen at load time.
const FLICKER = (() => {
  const r = rng(0xb01b);
  const segs = [];
  let t = CUES.bulbFlicker;
  while (t < B3) {
    let v = r.range(0.35, 0.85);
    if (r.random() < 0.18) v = 0.35;
    segs.push([t, v]);
    t += r.range(0.05, 0.17);
  }
  return segs;
})();

export function bulbLevel(t) {
  if (t < CUES.bulbFlicker) return 1.0;
  if (t < B3) {
    let v = 1.0;
    for (const [s, val] of FLICKER) {
      if (s > t) break;
      v = val;
    }
    return v;
  }
  if (t < B4) return lerp(0.75, 0.3, (t - B3) / (B4 - B3)); // dims linearly over 3.5 s
  if (t >= CUES.bulbOut) return 0;
  if (t >= CUES.bulbBlink && t < CUES.bulbBlink + 0.12) return 0.35; // one blink back up
  return lerp(0.3, 0.05, ease.inOutSine(clamp((t - B4) / 0.9))); // fades to 0.05 over 0.9 s
}

export function cameraAt(t) {
  if (t < B2) return beat1Cam(t);
  if (t < B3) return beat2Cam(t);
  if (t < B4) return beat3Cam(t);
  return beat4Cam(t);
}

// Spot positions are the frozen set spots (doc "Spot" table), so the framing survives model rebuilds.
const DESK = [0.85, 0, -0.5];
const SINK = [0.3, 0, -0.48];
const TIM_HEAD_SIT = 1.12; // head centre, seated
const TIM_HEAD_STAND = 1.07; // head centre, standing at the sink

/** Beat 1 · front34_push: opens on the whole dollhouse room (the open front framed by the ceiling fascia
 *  and the side walls), then a long eased dolly + zoom that arcs round to ¾ front on the focused face
 *  (GuoGuo on the shelf to the left of frame, the bulb above Tim's head). Tim's head grows ~1.85x. */
function beat1Cam(t) {
  // start: near eye level, far back on a longer lens so the frame stays inside the proscenium (solved
  // with the out-of-set ray check: no frame edge ever looks past the set); end: the earlier ¾ framing.
  // GuoGuo sits at the left end of the shelf top (ggOfficeNudge) so he peeks out left of Tim
  const u = smootherstep(0.0, B2 - 0.1, t);
  const position = mix3([1.0, 1.3, 5.8], [1.65, 1.72, 3.45], u);
  const target = mix3([0.45, 1.28, -0.42], [0.57, 1.29, -0.41], u);
  return { position, target, fov: lerp(26.5, 22, u) };
}

/** Beat 2 · two_shot: (A) wide on the door + Tim with a punch-in kick and shake on the burst,
 *  (B) ease into a lioness-favouring two-shot for the point and jabs, (C) a snap zoom onto Tim's shock
 *  and the flickering bulb, with an overshoot. */
function beat2Cam(t) {
  const lt = t - B2;
  // every framing here was solved so no frame edge looks past the open sides / over the walls
  // A: wide from the front-right: the door (left wall, seen nearly square-on) + the lioness + Tim
  const A = { position: [2.5, 2.4, 2.7], target: [0.093, 1.142, -0.273], fov: 26 };
  // B: lioness ¾ on the left third (body near profile so the point reads side-on), Tim on the right
  const Bs = { position: [0.6, 2.35, 4.2], target: [-0.245, 1.057, -0.355], fov: 30 };
  const kAB = ease.inOutCubic(clamp((lt - 0.7) / 0.5));
  const CUT = 1.95;
  if (lt >= CUT) {
    // C: CUT to Tim's shock: face on the right third looking off-left toward the lioness, chin and
    // raised hands in frame, the flickering bulb above him; a quick spring punch-in + shake
    const c = lt - CUT;
    const push = spring(c, 1.8, 0.55);
    const position = mix3([1.85, 1.92, 4.75], [1.8, 1.9, 4.6], push);
    const target = [0.35, 1.064, -0.578];
    const sh = 0.01 * Math.exp(-7 * c);
    position[0] += sh * noise1(c * 27, 5);
    position[1] += sh * noise1(c * 31, 6);
    return { position, target, fov: lerp(21.5, 20, push) };
  }
  const position = mix3(A.position, Bs.position, kAB);
  const target = mix3(A.target, Bs.target, kAB);
  const fov = lerp(A.fov, Bs.fov, kAB);
  // burst punch: a quick FOV kick in, spring settle back out; decaying shake
  const burst = lt - 0.05;
  const kick = burst <= 0 ? 0 : 0.12 * Math.exp(-4 * burst) * (1 - Math.exp(-40 * burst));
  const sh = (b, amp) => (b <= 0 ? 0 : amp * Math.exp(-6 * b));
  const shake = sh(burst, 0.018) + sh(t - CUES.timShock, 0.005);
  position[0] += shake * noise1(lt * 23, 3);
  position[1] += shake * noise1(lt * 29, 4);
  return { position, target, fov: fov * (1 - kick) };
}

/** Beat 3 · side_truck (re-staged front ¾ over the sink): Tim's glum face, the plate and suds, the
 *  shrinking stack on his left and GuoGuo on the cabinet behind, trucking slowly around.  One insert
 *  (INSERT3) cuts in close on the hands for a full scrub -> rinse -> rack so the chore reads, then cuts
 *  back to the truck. */
const INSERT3 = [B3 + 0.85, B3 + 1.75]; // plate 1 of the stack: scrub, rinse, into the rack
function beat3Cam(t) {
  if (t >= INSERT3[0] && t < INSERT3[1]) {
    // insert: high front-right on the mittens, sponge and plate over the soapy water, the spout and the
    // stack framing it; a slow drift in
    const k = smootherstep(INSERT3[0], INSERT3[1], t);
    const target = [lerp(0.4, 0.42, k), lerp(0.555, 0.545, k), -0.13];
    return { position: orbit(target, lerp(36, 32, k), lerp(40, 38, k), lerp(0.8, 0.74, k)), target, fov: 36 };
  }
  const u = smootherstep(B3, B4, t);
  const target = [lerp(0.3, 0.34, u), lerp(1.04, 1.08, u), lerp(-0.33, -0.38, u)];
  return { position: orbit(target, lerp(32, 20, u), lerp(15, 12, u), lerp(3.6, 3.2, u)), target, fov: 30 };
}

/** Beat 4 · close_push: opens a touch wider on Tim at the basin so the plate slipping back into the water
 *  and the sponge plopping in read, then pushes in to a medium close-up: head + slumped shoulders + bulb,
 *  GuoGuo on the right.  Off-axis to the faucet's right so it stays below/left of his face. */
function beat4Cam(t) {
  // frontal ¾ on Tim at the basin (the swing-arm faucet sits off to his right, below his chin line), left
  // of centre; GuoGuo on the right, the bulb + smoke above him and the ✗ card upper right.  Holds ~0.45 s
  // for the slide, then a slow eased push in to head + slumped shoulders, the bulb kept at the top edge
  const u = smootherstep(B4 + 0.45, END, t);
  const target = [lerp(0.6, 0.62, u), lerp(1.16, 1.25, u), -0.32];
  return { position: orbit(target, lerp(30, 27, u), lerp(14, 13, u), lerp(3.45, 2.7, u)), target, fov: lerp(31, 29, u) };
}

// ---------------------------------------------------------------- lighting mood per beat
// Warm, focused office (room dimmed, a warm practical on Tim) -> daylight snaps back on the break-in ->
// cooler, greyer kitchen that keeps dimming as the idea dies.  Built on the Look A base values.
const LOOK_RIM = [-3, 4, -5]; // LOOK_A rim direction
const KITCHEN_RIM = [-2.2, 1.5, -5];
const MOODS = {
  focus: {
    exposure: 0.88, background: '#cdbfab', env: 0.18, vignette: 0.36,
    hemi: { sky: '#ffe2bd', ground: '#a88d70', intensity: 0.3 },
    key: { color: '#ffd9a8', intensity: 1.2 },
    rim: { color: '#ffd09a', intensity: 1.0 },
    spot: { color: '#ffcf8f', intensity: 12, position: [0.15, 2.7, 1.1], target: [DESK[0], 0.95, DESK[2]], angle: 0.45, penumbra: 0.95 },
  },
  office: {
    exposure: 0.95, background: '#e8e0d4', env: 0.3, vignette: 0.18,
    hemi: { sky: '#fff4e4', ground: '#cdb79a', intensity: 0.6 },
    key: { color: '#fff0dc', intensity: 2.3 },
    rim: { color: '#e9eeff', intensity: 0.55 },
    spot: { color: '#ffe6c4', intensity: 0, position: [0.2, 2.6, 1.0], target: [DESK[0], 0.9, DESK[2]], angle: 0.5, penumbra: 0.9 },
  },
  kitchen: {
    exposure: 0.86, background: '#cfd5db', env: 0.24, vignette: 0.28,
    hemi: { sky: '#d3e0f2', ground: '#94938f', intensity: 0.46 },
    key: { color: '#dde7ff', intensity: 1.75 },
    // low cool back light: a clear blue-grey rim on Tim's silhouette against the pale tiles
    rim: { color: '#a9bfe6', intensity: 2.4, position: KITCHEN_RIM },
    spot: { color: '#bcd2f2', intensity: 3.5, position: [0.9, 2.5, 1.4], target: [SINK[0], 0.9, SINK[2]], angle: 0.55, penumbra: 0.9 },
  },
  gone: {
    exposure: 0.74, background: '#b3bac3', env: 0.17, vignette: 0.42,
    hemi: { sky: '#d9e0ea', ground: '#8e8a84', intensity: 0.36 },
    key: { color: '#e2e8f5', intensity: 1.25 },
    rim: { color: '#9fb3d8', intensity: 2.8, position: KITCHEN_RIM },
    spot: { color: '#a9c2e6', intensity: 3.0, position: [0.9, 2.5, 1.4], target: [SINK[0], 1.0, SINK[2]], angle: 0.45, penumbra: 0.9 },
  },
  out: {
    exposure: 0.64, background: '#a1a8b1', env: 0.14, vignette: 0.5,
    hemi: { sky: '#d2d9e4', ground: '#84807a', intensity: 0.3 },
    key: { color: '#dde3f0', intensity: 1.05 },
    rim: { color: '#97a9cc', intensity: 2.5, position: KITCHEN_RIM },
    spot: { color: '#a3bde3', intensity: 2.6, position: [0.9, 2.5, 1.4], target: [SINK[0], 1.0, SINK[2]], angle: 0.42, penumbra: 0.9 },
  },
};
const _c1 = new Color(), _c2 = new Color();
const mixC = (a, b, k) => '#' + _c1.set(a).lerp(_c2.set(b), k).getHexString();
function mixMood(a, b, k) {
  if (k <= 0) return a;
  if (k >= 1) return b;
  const n = (x, y) => lerp(x, y, k);
  const L = (p, q) => ({ color: mixC(p.color, q.color, k), intensity: n(p.intensity, q.intensity) });
  const R = (p, q) => ({ ...L(p, q), position: mix3(p.position ?? LOOK_RIM, q.position ?? LOOK_RIM, k) });
  return {
    exposure: n(a.exposure, b.exposure), background: mixC(a.background, b.background, k), env: n(a.env, b.env), vignette: n(a.vignette, b.vignette),
    hemi: { sky: mixC(a.hemi.sky, b.hemi.sky, k), ground: mixC(a.hemi.ground, b.hemi.ground, k), intensity: n(a.hemi.intensity, b.hemi.intensity) },
    key: L(a.key, b.key), rim: R(a.rim, b.rim),
    spot: { ...L(a.spot, b.spot), position: mix3(a.spot.position, b.spot.position, k), target: mix3(a.spot.target, b.spot.target, k), angle: n(a.spot.angle, b.spot.angle), penumbra: n(a.spot.penumbra, b.spot.penumbra) },
  };
}

export function moodAt(t) {
  if (t < B3) {
    // focus fades in over the first beat; the burst snaps the room lights back (fast, slight flash)
    const k = cue(t, CUES.doorOpen, 0.18, ease.outCubic);
    const m = mixMood(MOODS.focus, MOODS.office, k);
    const flash = t > CUES.doorOpen ? 0.12 * Math.exp(-8 * (t - CUES.doorOpen)) : 0;
    return { ...m, exposure: m.exposure + flash };
  }
  if (t < B4) return mixMood(MOODS.kitchen, MOODS.gone, smoothstep(B3 + 0.4, B4 + 0.6, t));
  if (t < CUES.bulbOut) return mixMood(MOODS.kitchen, MOODS.gone, smoothstep(B3 + 0.4, B4 + 0.6, t));
  return mixMood(MOODS.gone, MOODS.out, cue(t, CUES.bulbOut, 1.4, ease.outCubic));
}

export const SCENE001 = {
  id: '001',
  title: 'Scene 001 · 13 s',
  duration: END,
  fps: 30,
  beats: BEATS,
  cues: CUES,
  glow: true,
  kitchenStart: B3,
  setAt: (t) => (t < B3 ? 'office' : 'kitchen'),
  bulbLevel,
  camera: cameraAt,
  mood: moodAt,
  // key moments for `render.mjs --stills` and the README stills
  stills: { b1_locked_in: 2.6, b2_burst: 3.9, b2_point: 4.95, b2_shock: 5.8, b3_insert: 7.4, b3_dishes: 8.4, b4_out: 10.95, b4_card: 12.6 },
  // staging knobs read by the director
  focusLift: 9, // beat 1: lift the focused face toward the lens (deg)
  washLift: 18, // beat 3: glum face lifted over the plate so the expression reads
  shockHop: 0.045, // beat 2: Tim's take (m)
  slumpLift: 24,
  slump: { torso: 9, sink: 0, arms: 0 },
  lionPath: 1.7, // beat 2: she walks 1.7 m (from just outside the door, clear of its swing) to doorway_in
  lionCheatDeg: 80, // beat 2: body near profile so the short pointing arm reads side-on, aimed at Tim
  lionNeckYaw: -30, // ...while her head turns toward the camera (¾ face)
  lionNeckTurn: 0.22,
  lionAim: { lean: 7, jabLean: 5, jabFlick: 0.22, up: 0.3, weight: 1 },
  glowOnHead: 1.0, // centre the focus glow on the head so it haloes the face (not hidden behind the desk)
  ggOfficeNudge: [-0.4, 0, 0], // GuoGuo at the left end of the shelf top (x -0.66), clear of Tim's head
  // Tim stays at spot_sink through beats 3-4 (the plate slides back into the water on the deflate, so he
  // must still be at the basin); the low chibi-height faucet sits below his face from both cameras
  // cool halo: normal blend (additive vanished on the pale tiles), desaturated blue that shrinks and greys
  // across beats 3-4 as the idea fades
  fxLook: {
    warm: 0.85, warmSize: 2.6, warmColor: '#ffc47a', speedDur: 0.62,
    cool: 0.6, coolSize: 2.9, coolSizeEnd: 2.7, coolColor: '#5f86c4', coolColorEnd: '#7a8aa6', coolBlend: 'normal', coolBack: 0.6, coolRing: true,
  },
};
void DEG;
void TIM_HEAD_SIT;
void TIM_HEAD_STAND;

export const createScene001 = (world) => createDirector(world, SCENE001);
