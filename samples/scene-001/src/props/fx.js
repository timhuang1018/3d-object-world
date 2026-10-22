// Graphic FX: billboards / sprites driven as pure functions of scene time.
import * as THREE from 'three';
import { clamp, ease, fbm1, rng, smoothstep, spring, wobble } from '@infra/math.js';
import { angerTexture, bangTexture, bubbleTexture, haloTexture, streakTexture, xCardTexture } from './textures.js';

const _right = new THREE.Vector3();
const _up = new THREE.Vector3();
const _fwd = new THREE.Vector3();
const _v = new THREE.Vector3();

function cameraAxes(camera) {
  camera.updateMatrixWorld();
  const e = camera.matrixWorld.elements;
  _right.set(e[0], e[1], e[2]).normalize();
  _up.set(e[4], e[5], e[6]).normalize();
  _fwd.set(-e[8], -e[9], -e[10]).normalize();
}

function billboard(texture, w, h, opts = {}) {
  const m = new THREE.Mesh(
    new THREE.PlaneGeometry(w, h),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false, toneMapped: true, fog: false, ...opts }),
  );
  m.renderOrder = 20;
  return m;
}

/** Speech bubble beside the speaker's head (right 0.42, up 0.62 in camera axes) with a pulsing "!". */
export class Bubble {
  constructor() {
    this.root = new THREE.Group();
    this.body = billboard(bubbleTexture(), 0.5, 0.41);
    this.bang = billboard(bangTexture(), 0.075, 0.15);
    this.bang.position.set(0.15, 0.035, 0.002);
    this.bang.renderOrder = 21;
    this.root.add(this.body, this.bang);
    this.root.visible = false;
  }

  update({ t, t0, head, camera, jabs = [], hideAt = Infinity }) {
    const lt = t - t0;
    this.root.visible = lt >= 0 && t < hideAt;
    if (!this.root.visible) return;
    cameraAxes(camera);
    const bob = 0.012 * Math.sin(lt * 3.1) + 0.006 * fbm1(lt * 1.3, 4);
    this.root.position.copy(head).addScaledVector(_right, 0.42).addScaledVector(_up, 0.62 + bob);
    this.root.quaternion.copy(camera.quaternion);
    const s = spring(lt, 2.6, 0.38);
    this.root.scale.setScalar(Math.max(0.001, s));
    let pulse = 0;
    for (const j of jabs) {
      const d = t - j;
      if (d > -0.05) pulse = Math.max(pulse, Math.exp(-Math.max(0, d) * 9) * (d < 0 ? 1 + d / 0.05 : 1));
    }
    this.bang.scale.setScalar(1 + 0.35 * pulse + 0.05 * Math.sin(lt * 9));
    this.bang.rotation.z = -0.12 + 0.1 * pulse;
  }
}

/** Animal Crossing vein mark by the head (opposite side to the bubble): pops with an overshoot and throbs. */
export class AngerMark {
  constructor(size = 0.42) {
    this.root = billboard(angerTexture(), size, size, { depthTest: false });
    this.root.renderOrder = 22;
    this.root.visible = false;
  }

  update({ t, t0, head, camera, hideAt = Infinity, right = -0.27, up = 0.3 }) {
    const lt = t - t0;
    this.root.visible = lt >= 0 && t < hideAt;
    if (!this.root.visible) return;
    cameraAxes(camera);
    this.root.position.copy(head).addScaledVector(_right, right).addScaledVector(_up, up).addScaledVector(_fwd, -0.15);
    this.root.quaternion.copy(camera.quaternion);
    const pop = spring(lt, 3.2, 0.32);
    // heartbeat throb: sharp double beat, then rest (not a sine)
    const ph = (lt * 1.6) % 1;
    const beat = Math.exp(-((ph - 0.08) ** 2) / 0.0012) + 0.6 * Math.exp(-((ph - 0.26) ** 2) / 0.0012);
    const throb = 1 + 0.16 * beat;
    this.root.scale.setScalar(Math.max(0.001, pop * throb));
    this.root.rotation.z = 0.12 * wobble(lt, 2.5, 4);
  }
}

/** Speed lines trailing behind a mover (axis-aligned billboards along the motion direction).
 *  Drawn as dark ink strokes on top of the set (no depth test) so they read against the light walls. */
export class SpeedLines {
  constructor(count = 16, seed = 21) {
    this.root = new THREE.Group();
    const r = rng(seed);
    this.lines = [];
    for (let i = 0; i < count; i++) {
      const m = new THREE.Mesh(
        new THREE.PlaneGeometry(1, 0.05).translate(-0.5, 0, 0),
        new THREE.MeshBasicMaterial({ map: streakTexture(), color: i % 3 ? 0x6e5a48 : 0xfffaf0, transparent: true, depthWrite: false, depthTest: false, opacity: 0, fog: false, toneMapped: false }),
      );
      m.renderOrder = 19;
      this.root.add(m);
      this.lines.push({ m, y: r.range(0.15, 1.75), z: r.range(-0.4, 0.4), len: r.range(0.7, 1.6), lag: r.range(0, 0.09), w: r.range(0.75, 1.4), x0: r.range(0.12, 0.4) });
    }
    this.root.visible = false;
  }

  /** origin = mover position (world), dir = unit motion direction (xz) */
  update({ t, t0, dur = 0.55, origin, dir, camera }) {
    const lt = t - t0;
    this.root.visible = lt >= 0 && lt <= dur;
    if (!this.root.visible) return;
    const yaw = Math.atan2(dir.x, dir.z) - Math.PI / 2;
    this.root.position.copy(origin);
    this.root.rotation.set(0, yaw, 0);
    // roll each streak about its own axis to face the camera
    camera.getWorldPosition(_v);
    this.root.updateMatrixWorld();
    const local = this.root.worldToLocal(_v.clone());
    for (const L of this.lines) {
      const p = clamp((lt - L.lag) / dur);
      const grow = ease.outQuart(clamp(p / 0.22));
      const fade = 1 - smoothstep(0.5, 1, p);
      L.m.position.set(-L.x0 - 0.35 * ease.outCubic(p), L.y, L.z);
      L.m.scale.set(L.len * grow * (1 - 0.35 * p), L.w, 1);
      L.m.rotation.set(Math.atan2(-(local.y - L.y), local.z - L.z), 0, 0);
      L.m.material.opacity = 0.9 * fade * grow;
    }
  }
}

/** Halo with a solid core and a soft outer falloff: placed behind a head, the visible part is a ring of
 *  colour hugging the silhouette (the stock halo is faint exactly where it peeks out). */
let _ringHalo = null;
function ringHaloTexture() {
  if (_ringHalo) return _ringHalo;
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grd.addColorStop(0, 'rgba(255,255,255,0.95)');
  grd.addColorStop(0.45, 'rgba(255,255,255,0.9)');
  grd.addColorStop(0.62, 'rgba(255,255,255,0.55)');
  grd.addColorStop(0.8, 'rgba(255,255,255,0.18)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 256, 256);
  _ringHalo = new THREE.CanvasTexture(c);
  _ringHalo.colorSpace = THREE.SRGBColorSpace;
  return _ringHalo;
}

/** Focus glow: large soft halo behind the character (warm or cool).
 *  blend 'additive' (default) brightens — right for the warm glow on the dim office; 'normal' paints the
 *  tint over the background — needed for the cool halo, which would vanish additively on the pale tiles. */
export class FocusGlow {
  constructor() {
    this.sprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: haloTexture(), color: 0xffffff, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0, fog: false,
    }));
    this.sprite.renderOrder = 1;
    this.root = this.sprite;
  }

  update({ center, camera, color, amount, size = 2.3, t = 0, blend = 'additive', back = 0.75, ring = false }) {
    this.sprite.visible = amount > 0.002;
    if (!this.sprite.visible) return;
    camera.getWorldPosition(_v);
    const dir = center.clone().sub(_v).normalize();
    this.sprite.position.copy(center).addScaledVector(dir, back);
    const breathe = 1 + 0.03 * Math.sin(t * 1.7);
    this.sprite.scale.set(size * breathe, size * breathe, 1);
    this.sprite.material.color.set(color);
    this.sprite.material.opacity = amount;
    this.sprite.material.blending = blend === 'normal' ? THREE.NormalBlending : THREE.AdditiveBlending;
    this.sprite.material.map = ring ? ringHaloTexture() : haloTexture();
  }
}

/** Tim's sweat drop: pops 0.18 s into the shock and slides down the side of the head. */
export class SweatDrop {
  constructor() {
    const pts = [];
    for (let i = 0; i <= 16; i++) {
      const a = (i / 16) * Math.PI;
      const r = Math.sin(a) * (1 - 0.55 * (1 - Math.cos(a)) / 2) * 0.5;
      pts.push(new THREE.Vector2(Math.max(0.0001, r * (a < Math.PI / 2 ? 0.7 + 0.6 * (a / Math.PI) : 1)), -Math.cos(a) * 0.8));
    }
    const geo = new THREE.LatheGeometry(pts, 24);
    geo.scale(0.06, 0.06, 0.06);
    this.mesh = new THREE.Mesh(geo, new THREE.MeshPhysicalMaterial({
      color: '#a9cfe3', roughness: 0.12, clearcoat: 1, clearcoatRoughness: 0.05, transmission: 0, sheen: 0, emissive: '#6b98b8', emissiveIntensity: 0.15,
    }));
    this.mesh.castShadow = false;
    this.root = this.mesh;
    this.mesh.visible = false;
  }

  /** head: Object3D of the head joint (local space ~ head centre); lt = time since shock start */
  update({ lt, head, R = 0.43 }) {
    const p0 = 0.18;
    const vis = lt >= p0 && lt < p0 + 1.9;
    this.mesh.visible = vis;
    if (!vis) return;
    if (this.mesh.parent !== head) head.add(this.mesh);
    const k = lt - p0;
    const slide = ease.inOutSine(clamp((k - 0.25) / 1.3));
    const el = 0.42 - 0.62 * slide;
    const az = -0.95; // character's right side, toward the front
    this.mesh.position.set(Math.sin(az) * Math.cos(el) * R, Math.sin(el) * R, Math.cos(az) * Math.cos(el) * R);
    const pop = spring(k, 3.5, 0.4);
    const fade = 1 - smoothstep(1.45, 1.9, k);
    this.mesh.scale.setScalar(Math.max(0.001, pop * fade * (1 + 0.15 * slide)));
    this.mesh.rotation.set(0, 0, 0.35 - 0.2 * slide);
  }
}

/** Soft, shaded dust-cloud sprite (seeded): lumpy billow lit from the upper left with a darker underside
 *  and a feathered alpha edge, so a tinted puff reads against both the white door and the warm floor. */
const _dustTex = new Map();
function dustCloudTexture(seed) {
  if (_dustTex.has(seed)) return _dustTex.get(seed);
  const S = 128;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const g = c.getContext('2d');
  const r = rng(seed);
  const lumps = [];
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2 + r.range(-0.4, 0.4);
    const d = i === 0 ? 0 : r.range(8, 16);
    lumps.push([64 + Math.cos(a) * d, 66 + Math.sin(a) * d * 0.8, i === 0 ? 44 : r.range(28, 38)]);
  }
  const blob = (x, y, rad, stops) => {
    const grd = g.createRadialGradient(x, y, 0, x, y, rad);
    for (const [o, col] of stops) grd.addColorStop(o, col);
    g.fillStyle = grd;
    g.beginPath();
    g.arc(x, y, rad, 0, Math.PI * 2);
    g.fill();
  };
  // soft round billow: a faintly shaded body, then a light top offset up-left; very feathered edges
  for (const [x, y, rad] of lumps) blob(x, y, rad, [[0, 'rgba(205,205,205,0.9)'], [0.4, 'rgba(200,200,200,0.6)'], [0.75, 'rgba(198,198,198,0.2)'], [1, 'rgba(198,198,198,0)']]);
  for (const [x, y, rad] of lumps) blob(x - rad * 0.15, y - rad * 0.2, rad * 0.8, [[0, 'rgba(255,255,255,0.8)'], [0.45, 'rgba(255,255,255,0.45)'], [1, 'rgba(255,255,255,0)']]);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  _dustTex.set(seed, t);
  return t;
}

/** Soft round mote (a speck of dust in the air). */
let _moteTex = null;
function moteTexture() {
  if (_moteTex) return _moteTex;
  const c = document.createElement('canvas');
  c.width = c.height = 32;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(0.45, 'rgba(255,255,255,0.75)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 32, 32);
  _moteTex = new THREE.CanvasTexture(c);
  _moteTex.colorSpace = THREE.SRGBColorSpace;
  return _moteTex;
}

/** Dust when the door bursts open: a rolling floor burst swept out along the door's swing arc, a gust
 *  through the doorway into the room, and motes drifting in the air. Warm grey-beige so it reads against
 *  the white door, the cream walls and the lioness. Pure function of lt (time since the burst). */
export class DoorDust {
  constructor(seed = 33, { floor = 14, gust = 9, motes = 26 } = {}) {
    this.root = new THREE.Group();
    const r = rng(seed);
    const tints = ['#e6d8c0', '#dfcfb3', '#eadfca', '#e2d2b8'];
    const sprite = (map, color, order) => {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map, color, transparent: true, depthWrite: false, opacity: 0, fog: false }));
      s.renderOrder = order;
      s.visible = false;
      this.root.add(s);
      return s;
    };
    this.floor = [];
    for (let i = 0; i < floor; i++) {
      this.floor.push({
        s: sprite(dustCloudTexture(60 + i), tints[i % tints.length], 18),
        a: 0.12 + 1.42 * ((i + r.range(0, 1)) / floor), // angle along the swing (rad from closed)
        R: r.range(0.3, 0.9), // distance from the hinge
        vt: r.range(0.35, 0.95), vr: r.range(0.1, 0.55), rise: r.range(0.03, 0.2),
        size: r.range(0.34, 0.58), life: r.range(1.3, 1.75), spin: r.range(-1, 1), jit: r.range(0, 0.03),
      });
    }
    this.gust = [];
    for (let i = 0; i < gust; i++) {
      this.gust.push({
        s: sprite(dustCloudTexture(90 + i), tints[(i + 1) % tints.length], 18),
        // biased to the front of the doorway (toward the camera side, ahead of the lioness), low to the floor
        along: r.range(-0.3, 1.15), out: r.range(0.4, 1.6), up: r.range(0.02, 0.28), delay: r.range(0.0, 0.06),
        size: r.range(0.34, 0.58), life: r.range(1.25, 1.7), spin: r.range(-1, 1),
      });
    }
    this.motes = [];
    for (let i = 0; i < motes; i++) {
      this.motes.push({
        s: sprite(moteTexture(), i % 3 ? '#7d6c57' : '#a8967c', 19),
        along: r.range(0.2, 1.5), y: r.range(0.2, 1.4), out: r.range(0.1, 0.6), drift: r.range(0.4, 1.3), lift: r.range(-0.1, 0.25),
        size: r.range(0.045, 0.08), delay: r.range(0.02, 0.3), life: r.range(1.6, 2.4), seed: 200 + i,
      });
    }
    this._delays = null;
  }

  /** hinge = floor point under the door hinge, doorDir = unit vector hinge -> free edge (door closed),
   *  into = unit vector into the room (the way the free edge swings), swingAt(lt) = door angle (rad),
   *  center = floor point mid-opening (gust origin); lt = time since the burst. */
  update({ lt, hinge, doorDir, into, center, swingAt, radius = 0.85, along }) {
    this.root.visible = lt >= 0 && lt < 2.6;
    if (!this.root.visible) return;
    if (!center) center = hinge.clone().addScaledVector(doorDir, radius / 2);
    along = along || doorDir;
    if (!this._delays) {
      // when the free edge passes each puff's angle (sampled once; same function every frame -> pure)
      this._delays = this.floor.map((P) => {
        if (!swingAt) return 0.02 + 0.14 * (P.a / 1.6);
        for (let s = 0; s < 0.6; s += 0.004) if (swingAt(s) >= P.a) return s;
        return 0.3;
      });
    }
    const _p = _v;
    this.floor.forEach((P, i) => {
      const k = (lt - this._delays[i] - P.jit) / P.life;
      P.s.visible = k >= 0 && k <= 1;
      if (!P.s.visible) return;
      const ca = Math.cos(P.a), sa = Math.sin(P.a);
      const go = ease.outExpo(Math.min(1, k * 1.3));
      // pushed ahead of the door (tangent to the arc) and out from the hinge, rolling along the floor
      const dt = P.vt * go, dr = P.vr * go;
      const x = P.R * ca + dr * ca - dt * sa, z = P.R * sa + dr * sa + dt * ca;
      const sc = P.size * (0.45 + 1.25 * ease.outCubic(k));
      _p.copy(hinge).addScaledVector(doorDir, x).addScaledVector(into, z);
      _p.y = hinge.y + sc * 0.32 + P.rise * ease.outCubic(k);
      P.s.position.copy(_p);
      P.s.scale.set(sc * 1.15, sc, 1);
      P.s.material.rotation = P.spin * (0.3 + 1.5 * k);
      P.s.material.opacity = 0.68 * Math.min(1, k / 0.05) * (1 - smoothstep(0.3, 1, k));
    });
    for (const P of this.gust) {
      const k = (lt - P.delay) / P.life;
      P.s.visible = k >= 0 && k <= 1;
      if (!P.s.visible) continue;
      const go = ease.outExpo(k);
      const sc = P.size * (0.5 + 1.1 * ease.outCubic(k));
      P.s.position.copy(center).addScaledVector(along, P.along * radius * (1 + 0.4 * go)).addScaledVector(into, P.out * (0.15 + 1.2 * go));
      P.s.position.y = center.y + sc * 0.3 + P.up * (0.4 + 0.7 * k);
      P.s.scale.set(sc, sc, 1);
      P.s.material.rotation = P.spin * k * 2;
      P.s.material.opacity = 0.62 * Math.min(1, k / 0.06) * (1 - smoothstep(0.25, 1, k));
    }
    for (const P of this.motes) {
      const k = (lt - P.delay) / P.life;
      P.s.visible = k >= 0 && k <= 1;
      if (!P.s.visible) continue;
      const tt = lt - P.delay;
      const go = ease.outCubic(Math.min(1, k * 1.6));
      P.s.position.copy(center).addScaledVector(along, P.along * radius + 0.05 * fbm1(tt * 1.3, P.seed))
        .addScaledVector(into, P.out + P.drift * go + 0.08 * k);
      P.s.position.y = center.y + P.y + P.lift * k + 0.04 * fbm1(tt * 1.1, P.seed + 50);
      const tw = 0.75 + 0.25 * Math.sin(tt * 9 + P.seed); // a little twinkle as they tumble
      P.s.scale.setScalar(P.size * (0.6 + 0.4 * go));
      P.s.material.opacity = 0.95 * tw * Math.min(1, k / 0.08) * (1 - smoothstep(0.6, 1, k));
    }
  }
}

/** HUD icon card (crossed-out bulb) at a normalised screen position (x from left, y from top). */
export class XCard {
  constructor(look) {
    this.look = look;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: xCardTexture(), transparent: true, depthTest: false, toneMapped: false }));
    this.mesh.visible = false;
    look.hud.add(this.mesh);
  }

  update({ t, t0, x = 0.64, y = 0.3, size = 0.22 }) {
    const lt = t - t0;
    this.mesh.visible = lt >= 0;
    if (!this.mesh.visible) return;
    const aspect = this.look.width / this.look.height;
    const s = Math.max(0.001, spring(lt, 2.4, 0.4)) * size;
    this.mesh.position.set(x, 1 - y, 0);
    this.mesh.scale.set(s / aspect, s, 1);
    this.mesh.rotation.z = -0.1 + 0.18 * wobble(lt, 2.2, 3.5);
  }
}

/** Thin water stream from a faucet spout down into the basin. */
export class WaterStream {
  constructor() {
    this.mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(0.006, 0.0085, 1, 12, 1, true).translate(0, -0.5, 0),
      new THREE.MeshPhysicalMaterial({ color: '#d7ecf7', roughness: 0.05, transparent: true, opacity: 0.55, clearcoat: 1, depthWrite: false }),
    );
    this.mesh.castShadow = false;
    this.root = this.mesh;
  }

  update({ spout, length = 0.22, t = 0, visible = true }) {
    this.mesh.visible = visible && !!spout;
    if (!this.mesh.visible) return;
    this.mesh.position.copy(spout);
    this.mesh.scale.set(1 + 0.08 * Math.sin(t * 23), length, 1 + 0.08 * Math.cos(t * 19));
  }
}

export { cameraAxes };
