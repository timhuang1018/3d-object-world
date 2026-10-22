// Deterministic math helpers: easing, springs, seeded random, smooth noise.
// Everything here is a pure function of its inputs (no clocks, no Math.random).

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, t) => a + (b - a) * t;
export const invLerp = (a, b, x) => clamp((x - a) / (b - a));
export const remap = (x, a, b, c, d) => lerp(c, d, invLerp(a, b, x));
export const smoothstep = (a, b, x) => { const t = invLerp(a, b, x); return t * t * (3 - 2 * t); };
export const smootherstep = (a, b, x) => { const t = invLerp(a, b, x); return t * t * t * (t * (t * 6 - 15) + 10); };
export const DEG = Math.PI / 180;

export const ease = {
  linear: (t) => t,
  inQuad: (t) => t * t,
  outQuad: (t) => 1 - (1 - t) * (1 - t),
  inOutQuad: (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2),
  inCubic: (t) => t * t * t,
  outCubic: (t) => 1 - Math.pow(1 - t, 3),
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  outQuart: (t) => 1 - Math.pow(1 - t, 4),
  inOutSine: (t) => -(Math.cos(Math.PI * t) - 1) / 2,
  outSine: (t) => Math.sin((t * Math.PI) / 2),
  inSine: (t) => 1 - Math.cos((t * Math.PI) / 2),
  outExpo: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  outBack: (t, s = 1.70158) => 1 + (s + 1) * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2),
  inBack: (t, s = 1.70158) => (s + 1) * t * t * t - s * t * t,
  inOutBack: (t, s = 1.70158 * 1.525) =>
    t < 0.5
      ? (Math.pow(2 * t, 2) * ((s + 1) * 2 * t - s)) / 2
      : (Math.pow(2 * t - 2, 2) * ((s + 1) * (t * 2 - 2) + s) + 2) / 2,
  outElastic: (t) => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
  },
};

/** Progress of a cue: 0 before start, 1 after start+dur, eased in between. */
export function cue(t, start, dur, e = ease.inOutCubic) {
  if (t <= start) return 0;
  if (t >= start + dur) return 1;
  return e((t - start) / dur);
}

/** Closed-form damped spring step response (0 -> 1) at time t after the step.
 *  freq in Hz, zeta = damping ratio (<1 overshoots). Pure function of t. */
export function spring(t, freq = 2.5, zeta = 0.35) {
  if (t <= 0) return 0;
  const w = 2 * Math.PI * freq;
  if (zeta >= 1) return 1 - Math.exp(-w * t) * (1 + w * t);
  const wd = w * Math.sqrt(1 - zeta * zeta);
  return 1 - Math.exp(-zeta * w * t) * (Math.cos(wd * t) + ((zeta * w) / wd) * Math.sin(wd * t));
}

/** Damped oscillation impulse: starts at 0, swings with amplitude 1 and decays. */
export function wobble(t, freq = 3, decay = 4) {
  if (t <= 0) return 0;
  return Math.sin(2 * Math.PI * freq * t) * Math.exp(-decay * t);
}

/** Mulberry32 seeded PRNG. */
export function rng(seed = 1) {
  let a = seed >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return { random: next, range: (lo, hi) => lo + (hi - lo) * next(), int: (lo, hi) => Math.floor(lo + (hi - lo + 1) * next()) };
}

/** Integer hash -> [0,1). */
export function hash1(n, seed = 0) {
  let x = (Math.imul(n | 0, 0x27d4eb2d) ^ Math.imul(seed | 0, 0x165667b1)) >>> 0;
  x = Math.imul(x ^ (x >>> 15), 0x85ebca6b) >>> 0;
  x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35) >>> 0;
  return ((x ^ (x >>> 16)) >>> 0) / 4294967296;
}

/** Smooth 1D value noise in [-1, 1] (cubic-interpolated hashed lattice). */
export function noise1(x, seed = 0) {
  const i = Math.floor(x);
  const f = x - i;
  const u = f * f * (3 - 2 * f);
  const a = hash1(i, seed) * 2 - 1;
  const b = hash1(i + 1, seed) * 2 - 1;
  return a + (b - a) * u;
}

/** Fractal 1D noise in about [-1, 1]. */
export function fbm1(x, seed = 0, oct = 3) {
  let s = 0, amp = 0.5, tot = 0, f = 1;
  for (let o = 0; o < oct; o++) { s += amp * noise1(x * f, seed + o * 17); tot += amp; amp *= 0.5; f *= 2.03; }
  return s / tot;
}

/** Piecewise keyframes: [[t, v], ...] with per-segment easing (default inOutCubic). */
export function keys(t, ks, e = ease.inOutCubic) {
  if (t <= ks[0][0]) return ks[0][1];
  for (let i = 0; i < ks.length - 1; i++) {
    const [t0, v0] = ks[i];
    const [t1, v1, e1] = ks[i + 1];
    if (t <= t1) return lerp(v0, v1, (e1 || e)((t - t0) / (t1 - t0)));
  }
  return ks[ks.length - 1][1];
}
