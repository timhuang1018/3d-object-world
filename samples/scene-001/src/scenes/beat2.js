// Beat 2 on its own — an 8 s clip of the break-in as one continuous camera move (a look test).
// docs/scene-spec.md: GuoGuo watches from the bookshelf.
import { clamp, ease, lerp, smoothstep } from '@infra/math.js';
import { createDirector, mix3, orbit } from './director.js';

const END = 8.0;
export const BEATS = [{ id: 2, name: 'Break-in · locked clip', start: 0, end: END, set: 'office', camera: 'beat2', narration: '…then the lioness arrived.' }];

export const CUES = {
  timBlinks: [1.25, 3.02],
  lionListen: 1.9, // ears flick behind the door
  doorOpen: 2.2, // the door bursts open (spring ring, dust puff); GuoGuo startled
  lionBrace: 2.21, // braces through the door (2.21–2.5), then straightens up
  lionMove: 2.3, // walks to just inside the door (2.3–3.0)
  lionMoveDur: 0.7,
  lionTurn: 2.75, // turns 45°, cheated toward the camera
  lionAkimbo: 2.9, // far paw on her hip
  lionPoint: 3.0, // points and jabs twice (0.42 s and 0.66 s after)
  bubble: 3.12, // dirty plates + "!"
  timTurn: 3.78, // swivel chair turns toward the door
  timShock: 3.9, // hands up, jolt, tremble, chair rolls back 0.1 m, sweat drop, GuoGuo flinches
  lionBlinks: [4.61],
  bulbOut: 5.5,
};
CUES.jabs = [CUES.lionPoint + 0.42, CUES.lionPoint + 0.66];

// 3.9–5.5: the bulb flickers out (0.1, 0.9, 0.15, 0.85 … 0.0)
const FLICK = [[3.9, 0.1], [4.02, 0.9], [4.16, 0.15], [4.3, 0.85], [4.46, 0.2], [4.6, 0.7], [4.78, 0.12], [4.92, 0.55], [5.08, 0.1], [5.22, 0.3], [5.36, 0.06]];
export function bulbLevel(t) {
  if (t < 3.9) return 1.0;
  if (t >= CUES.bulbOut) return 0;
  let v = 1;
  for (const [s, x] of FLICK) if (t >= s) v = x;
  return v;
}

const ROOM = [-0.45, 1.0, -0.4];
export function cameraAt(t) {
  // 1. orbit in: az 40° / el 27° / d 10.2 -> 6° / 12° / 5.8 over 2.25 s
  const k1 = ease.inOutCubic(clamp(t / 2.25));
  let az = lerp(40, 6, k1), el = lerp(27, 12, k1), dist = lerp(10.2, 5.8, k1);
  // 2. target pans: door (2.3 s), lioness (2.85 s), Tim (3.45 s)
  const door = [-2.4, 1.0, -0.7], lion = [-1.15, 1.05, -0.1], tim = [0.85, 1.15, -0.55];
  let target = ROOM;
  target = mix3(target, door, ease.inOutCubic(clamp((t - 2.05) / 0.25)));
  target = mix3(target, lion, ease.inOutCubic(clamp((t - 2.5) / 0.35)));
  target = mix3(target, tim, ease.inOutCubic(clamp((t - 3.1) / 0.35)));
  // 3. zoom 30° -> 12.5° on the shock (4.0 s);  4. tilt up to the bulb (4.85 s)
  let fov = lerp(30, 12.5, ease.inOutCubic(clamp((t - 3.95) / 0.45)));
  target = mix3(target, [0.85, 1.95, -0.6], ease.inOutCubic(clamp((t - 4.85) / 0.55)));
  // 5. re-base and orbit out to −13° / 4° / 4.9 (5.6–7.6 s)
  const k5 = ease.inOutCubic(clamp((t - 5.6) / 2.0));
  if (k5 > 0) {
    az = lerp(az, -13, k5);
    el = lerp(el, 4, k5);
    dist = lerp(dist, 4.9, k5);
    fov = lerp(fov, 30, k5);
    target = mix3(target, [0.2, 1.25, -0.5], k5);
  }
  // the orbit pivots around the room centre; the look target moves independently
  const pivot = mix3(ROOM, [0.2, 1.2, -0.45], smoothstep(5.6, 7.6, t));
  return { position: orbit(pivot, az, el, dist), target, fov };
}

export const BEAT2 = {
  id: 'beat2',
  title: 'Beat 2 · locked clip 8 s',
  duration: END,
  fps: 30,
  beats: BEATS,
  cues: CUES,
  glow: false,
  seatTurnDeg: -32,
  setAt: () => 'office',
  bulbLevel,
  camera: cameraAt,
};

export const createBeat2 = (world) => createDirector(world, BEAT2);
