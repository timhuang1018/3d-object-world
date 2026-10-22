// Face decals: canvas-drawn expression textures for the front-projected face shells.
//
// Decal mapping (infra/blender/lib/geo.py face_shell):  u = 0.5 + x / 2S,  v = 0.5 + y / 2S  (head-local
// metres, x = character's left = viewer's right, y = up).  glTF flips v, and our CanvasTexture uses
// flipY = false, so canvas X = u * N and canvas Y = (0.5 - y / 2S) * N  — i.e. we draw the face as seen
// from the front.  Every drawing is deterministic (no randomness).
import * as THREE from 'three';

const N = 1024;
const INK = '#2a2421';

function makeCanvas() {
  const c = document.createElement('canvas');
  c.width = c.height = N;
  return c;
}

function toTexture(canvas) {
  const t = new THREE.CanvasTexture(canvas);
  t.flipY = false;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  return t;
}

/** Map head-local metres -> canvas px for a decal half-size S. */
function mapper(S) {
  const k = N / (2 * S);
  return { X: (x) => N / 2 + x * k, Y: (y) => N / 2 - y * k, L: (m) => m * k };
}

function softOval(g, x, y, rx, ry, color, alpha) {
  g.save();
  g.translate(x, y);
  g.scale(1, ry / rx);
  const grd = g.createRadialGradient(0, 0, 0, 0, 0, rx);
  grd.addColorStop(0, color);
  grd.addColorStop(1, 'rgba(0,0,0,0)');
  g.globalAlpha = alpha;
  g.fillStyle = grd;
  g.beginPath();
  g.arc(0, 0, rx, 0, Math.PI * 2);
  g.fill();
  g.restore();
}

function stroke(g, w, color = INK) {
  g.lineWidth = w;
  g.strokeStyle = color;
  g.lineCap = 'round';
  g.lineJoin = 'round';
  g.stroke();
}

// --------------------------------------------------------------------------------------------
// Tim — "dead fish" A eyes (heavy flat lids, pupils hanging under them), flat mouth.
// Eyes at head-local (±0.155, −0.02) inside the glasses rings (r 0.092); mouth at (0, −0.17).
// --------------------------------------------------------------------------------------------
const TIM = {
  S: 0.42,
  eyeX: 0.155,
  eyeY: -0.02,
  mouthY: -0.17,
  skin: '#f4dcc6',
  mouth: '#6b3f36',
  blush: '#e49286',
  gloom: '#7891be',
};

function timEye(g, M, side, o) {
  // side: -1 = character's right (viewer's left), +1 = left
  const cx = M.X(side * TIM.eyeX + (o.lookX || 0));
  const cy = M.Y(TIM.eyeY + (o.lookY || 0));
  const pw = M.L(o.pupilW ?? 0.023); // pupil half-width
  const ph = M.L(o.pupilH ?? 0.03); // pupil half-height
  const lidY = cy + M.L(o.lid ?? 0.006); // lid line (canvas y grows downward)
  const lidW = M.L(o.lidW ?? 0.04);
  const tilt = (o.lidTilt ?? 0) * side; // + raises the outer end
  if (o.closed) {
    g.beginPath();
    const sag = M.L(o.closedSag ?? 0.006);
    g.moveTo(cx - lidW, lidY + tilt * M.L(0.01));
    g.quadraticCurveTo(cx, lidY + sag * 2, cx + lidW, lidY - tilt * M.L(0.01));
    stroke(g, M.L(0.0085));
    return;
  }
  if (o.shock) {
    const r = M.L(0.05);
    g.beginPath();
    g.ellipse(cx, cy - M.L(0.004), r, r * 1.12, 0, 0, Math.PI * 2);
    g.fillStyle = '#ffffff';
    g.fill();
    stroke(g, M.L(0.0065));
    g.beginPath();
    g.arc(cx + side * M.L(-0.004), cy + M.L(0.002), M.L(0.0105), 0, Math.PI * 2);
    g.fillStyle = INK;
    g.fill();
    return;
  }
  // pupil, clipped below the lid line
  g.save();
  g.beginPath();
  g.rect(cx - lidW * 1.6, lidY + M.L(0.002), lidW * 3.2, ph * 3);
  g.clip();
  g.beginPath();
  g.ellipse(cx, cy + M.L(o.pupilDrop ?? 0.012), pw, ph, 0, 0, Math.PI * 2);
  g.fillStyle = INK;
  g.fill();
  if (o.glint) {
    g.beginPath();
    g.arc(cx + side * M.L(0.006) - M.L(0.004), cy + M.L(0.02), M.L(0.0045), 0, Math.PI * 2);
    g.fillStyle = 'rgba(255,255,255,0.85)';
    g.fill();
  }
  g.restore();
  // heavy flat lid
  g.beginPath();
  g.moveTo(cx - lidW, lidY + tilt * M.L(0.012));
  g.lineTo(cx + lidW, lidY - tilt * M.L(0.012));
  stroke(g, M.L(o.lidThick ?? 0.0095));
}

function timBrow(g, M, side, o) {
  if (!o.brow) return;
  const cx = M.X(side * (TIM.eyeX - 0.005));
  const cy = M.Y(TIM.eyeY + 0.118 + (o.browY || 0));
  const w = M.L(0.034);
  const inner = M.L(o.brow.inner); // + = inner end lower (angry/determined), - = raised (sad)
  g.beginPath();
  g.moveTo(cx - side * w, cy + inner); // inner end (toward the nose)
  g.lineTo(cx + side * w, cy - inner * 0.4);
  stroke(g, M.L(0.012), o.browColor || '#3a302a');
}

function timMouth(g, M, o) {
  const cx = M.X(0), cy = M.Y(TIM.mouthY);
  g.beginPath();
  switch (o.mouth) {
    case 'flat':
      g.moveTo(cx - M.L(0.03), cy);
      g.lineTo(cx + M.L(0.03), cy);
      stroke(g, M.L(0.0085));
      break;
    case 'press':
      g.moveTo(cx - M.L(0.022), cy + M.L(0.002));
      g.lineTo(cx + M.L(0.022), cy - M.L(0.002));
      stroke(g, M.L(0.009));
      break;
    case 'frown':
      g.moveTo(cx - M.L(0.032), cy + M.L(0.01));
      g.quadraticCurveTo(cx, cy - M.L(0.014), cx + M.L(0.032), cy + M.L(0.01));
      stroke(g, M.L(0.0085));
      break;
    case 'wavy':
      g.moveTo(cx - M.L(0.036), cy + M.L(0.004));
      g.bezierCurveTo(cx - M.L(0.018), cy - M.L(0.012), cx - M.L(0.006), cy + M.L(0.012), cx + M.L(0.008), cy);
      g.bezierCurveTo(cx + M.L(0.018), cy - M.L(0.01), cx + M.L(0.028), cy + M.L(0.008), cx + M.L(0.036), cy + M.L(0.002));
      stroke(g, M.L(0.0075));
      break;
    case 'open': {
      g.ellipse(cx, cy + M.L(0.008), M.L(0.034), M.L(0.042), 0, 0, Math.PI * 2);
      g.fillStyle = TIM.mouth;
      g.fill();
      stroke(g, M.L(0.006));
      g.beginPath();
      g.ellipse(cx, cy + M.L(0.034), M.L(0.02), M.L(0.012), 0, 0, Math.PI * 2);
      g.fillStyle = '#d98579';
      g.fill();
      break;
    }
    case 'sigh':
      g.ellipse(cx, cy + M.L(0.004), M.L(0.012), M.L(0.014), 0, 0, Math.PI * 2);
      g.fillStyle = TIM.mouth;
      g.fill();
      stroke(g, M.L(0.005));
      break;
    default:
      break;
  }
}

function gloom(g, M, strength, S) {
  if (!strength) return;
  // blue forehead shade hanging from the fringe + vertical gloom lines (Animal Crossing style)
  const top = M.Y(0.215), bot = M.Y(0.04);
  const grd = g.createLinearGradient(0, top, 0, bot);
  grd.addColorStop(0, `rgba(120,145,190,${0.55 * strength})`);
  grd.addColorStop(1, 'rgba(120,145,190,0)');
  g.fillStyle = grd;
  g.beginPath();
  g.ellipse(M.X(0), top, M.L(0.27), bot - top, 0, 0, Math.PI);
  g.fill();
  const xs = [-0.11, -0.065, -0.02, 0.025, 0.07, 0.115];
  xs.forEach((x, i) => {
    const len = (i % 2 ? 0.075 : 0.1) * (0.75 + 0.25 * strength);
    g.beginPath();
    g.moveTo(M.X(x), M.Y(0.2));
    g.lineTo(M.X(x), M.Y(0.2 - len));
    stroke(g, M.L(0.0085), `rgba(120,145,190,${Math.min(1, 0.35 + 0.65 * strength)})`);
  });
}

const TIM_EXPR = {
  deadfish: { lid: 0.004, pupilDrop: 0.014, mouth: 'flat', blush: 0.22 },
  focused: { lid: 0.008, pupilDrop: 0.016, lookY: -0.004, lookX: 0, lidTilt: -0.15, brow: { inner: 0.012 }, mouth: 'press', blush: 0.18, glint: true },
  shock: { shock: true, mouth: 'open', gloom: 1.0, brow: { inner: -0.014 }, browY: 0.02, blush: 0.0 },
  glum: { lid: 0.012, pupilDrop: 0.016, lookY: -0.008, lidTilt: 0.12, brow: { inner: -0.012 }, mouth: 'frown', gloom: 0.45, blush: 0.12 },
  deflated: { lid: 0.019, pupilDrop: 0.012, lookY: -0.01, lidTilt: 0.25, pupilH: 0.026, brow: { inner: -0.016 }, browY: -0.005, mouth: 'wavy', gloom: 1.0, blush: 0.0 },
  talking: { lid: 0.002, pupilDrop: 0.012, mouth: 'sigh', blush: 0.2 },
};

function drawTim(name) {
  const base = name.replace(/_blink$/, '');
  const blink = name.endsWith('_blink');
  const o = { ...(TIM_EXPR[base] || TIM_EXPR.deadfish) };
  const c = makeCanvas();
  const g = c.getContext('2d');
  const M = mapper(TIM.S);
  if (o.blush) {
    softOval(g, M.X(-0.235), M.Y(-0.115), M.L(0.05), M.L(0.03), TIM.blush, o.blush);
    softOval(g, M.X(0.235), M.Y(-0.115), M.L(0.05), M.L(0.03), TIM.blush, o.blush);
  }
  gloom(g, M, o.gloom, TIM.S);
  for (const side of [-1, 1]) {
    timEye(g, M, side, blink ? { ...o, closed: true, shock: false, lid: (o.lid ?? 0.004) + 0.012 } : o);
    timBrow(g, M, side, o);
  }
  timMouth(g, M, o);
  return c;
}

// --------------------------------------------------------------------------------------------
// Lioness A — Sylvanian eyes (small dark ovals + glint), cream under-eye patches, brows #8a6446.
// Drawn in UV units (u, v with v up); the shell reports S, so this is head-size independent.
// --------------------------------------------------------------------------------------------
const LION = { eyeU: 0.16, eyeV: 0.57, browV: 0.685, patchV: 0.505, brow: '#8a6446', patch: '#f3e7d2', ink: '#2b211c' };

function drawLioness(name) {
  const blink = name.endsWith('_blink');
  const base = name.replace(/_blink$/, '');
  const c = makeCanvas();
  const g = c.getContext('2d');
  const U = (u) => u * N;
  const V = (v) => (1 - v) * N;
  const angry = base === 'angry';
  for (const side of [-1, 1]) {
    const ex = U(0.5 + side * LION.eyeU);
    const ey = V(LION.eyeV);
    // cream under-eye patch
    g.save();
    g.beginPath();
    g.ellipse(ex + side * N * 0.006, V(LION.patchV), N * 0.075, N * 0.05, side * 0.18, 0, Math.PI * 2);
    g.fillStyle = LION.patch;
    g.globalAlpha = 0.95;
    g.fill();
    g.restore();
    if (blink) {
      g.beginPath();
      g.moveTo(ex - N * 0.034, ey + N * 0.004);
      g.quadraticCurveTo(ex, ey + N * 0.022, ex + N * 0.034, ey + N * 0.004);
      stroke(g, N * 0.011, LION.ink);
    } else {
      // eye
      const ew = N * 0.031, eh = N * 0.042;
      g.save();
      // stern lid: flat, inner corner lower => clip the top part with a slanted line
      const lidDrop = angry ? 0.42 : 0.3; // fraction of eye height covered
      const slant = angry ? 0.5 : 0.32; // inner corner lower
      const innerX = ex - side * ew * 1.6, outerX = ex + side * ew * 1.6;
      const lidOuterY = ey - eh + eh * 2 * lidDrop * (1 - slant);
      const lidInnerY = ey - eh + eh * 2 * lidDrop * (1 + slant);
      g.beginPath();
      g.moveTo(innerX, lidInnerY);
      g.lineTo(outerX, lidOuterY);
      g.lineTo(outerX, ey + eh * 2);
      g.lineTo(innerX, ey + eh * 2);
      g.closePath();
      g.clip();
      g.beginPath();
      g.ellipse(ex, ey, ew, eh, 0, 0, Math.PI * 2);
      g.fillStyle = LION.ink;
      g.fill();
      g.beginPath();
      g.arc(ex - N * 0.009, ey + N * 0.004, N * 0.0085, 0, Math.PI * 2);
      g.fillStyle = 'rgba(255,255,255,0.9)';
      g.fill();
      g.restore();
      // lid line
      g.beginPath();
      g.moveTo(innerX + side * ew * 0.45, lidInnerY - (lidInnerY - lidOuterY) * 0.14);
      g.lineTo(outerX - side * ew * 0.55, lidOuterY + (lidInnerY - lidOuterY) * 0.17);
      stroke(g, N * 0.009, LION.ink);
    }
    // brows slanting down toward the nose
    const bx = U(0.5 + side * (LION.eyeU - 0.005));
    const by = V(LION.browV - (angry ? 0.012 : 0));
    const drop = N * (angry ? 0.04 : 0.024);
    g.beginPath();
    g.moveTo(bx - side * N * 0.045, by + drop);
    g.quadraticCurveTo(bx, by - N * 0.004, bx + side * N * 0.04, by - drop * 0.25);
    stroke(g, N * (angry ? 0.02 : 0.017), LION.brow);
  }
  if (angry) {
    // furrow lines between the brows
    for (const s of [-1, 1]) {
      g.beginPath();
      g.moveTo(U(0.5 + s * 0.012), V(0.665));
      g.lineTo(U(0.5 + s * 0.02), V(0.63));
      stroke(g, N * 0.006, 'rgba(138,100,70,0.7)');
    }
  }
  return c;
}

const textureCache = new Map();

/** Get (cached) texture for a character expression, e.g. faceTexture('tim', 'shock'). */
export function faceTexture(character, expr) {
  const key = `${character}:${expr}`;
  if (!textureCache.has(key)) {
    const canvas = character === 'tim' ? drawTim(expr) : drawLioness(expr);
    textureCache.set(key, toTexture(canvas));
  }
  return textureCache.get(key);
}

export const TIM_EXPRESSIONS = Object.keys(TIM_EXPR);
export const LIONESS_EXPRESSIONS = ['stern', 'angry'];

/** Assign an expression to every decal_face mesh under root. */
export function setFace(root, character, expr) {
  const tex = faceTexture(character, expr);
  root.traverse((o) => {
    if (o.isMesh && o.material?.userData?.family === 'decal') {
      if (o.material.map !== tex) {
        const first = !o.material.map;
        o.material.map = tex;
        o.material.visible = true;
        if (first) o.material.needsUpdate = true;
      }
    }
  });
}
