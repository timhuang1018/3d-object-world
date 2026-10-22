// Idea bulb: floats 0.76 m above the head; drift (bob 0.025, tilt 0.05); level b in 0..1 (lit above
// 0.05); rays above 0.5; glow sprite.  Out: droops + tilts over 0.5 s, then 3 smoke puffs rise and a
// snuffed-out wisp.  Colours: glass #fff6dc lit / #e2ddd3 off, emissive #ffe2a0, screw #b8b2a8,
// ray #f3d58e, smoke #9a948c.  update() is a pure function of its inputs.
import * as THREE from 'three';
import { clamp, ease, fbm1, smoothstep, spring } from '@infra/math.js';
import { glowTexture, puffTexture, rayTexture } from './textures.js';

const GLASS_OFF = new THREE.Color('#e2ddd3');
const GLASS_ON = new THREE.Color('#fff6dc');
const EMISSIVE = new THREE.Color('#ffe2a0');
const _v = new THREE.Vector3();
const SMOKE = new THREE.Color('#4f4a45'); // darker than the doc's #9a948c so it reads on the sage cabinets and the window

/** A fat, readable snuffed-out wisp (S-curl with a soft halo), drawn once. */
let _wispTex = null;
function fatWispTexture() {
  if (_wispTex) return _wispTex;
  const c = document.createElement('canvas');
  c.width = 128;
  c.height = 256;
  const g = c.getContext('2d');
  g.lineCap = 'round';
  for (let pass = 0; pass < 3; pass++) {
    g.beginPath();
    g.moveTo(64, 248);
    g.bezierCurveTo(28, 200, 100, 160, 60, 112);
    g.bezierCurveTo(28, 76, 94, 48, 72, 12);
    g.strokeStyle = `rgba(255,255,255,${[0.22, 0.45, 0.95][pass]})`;
    g.lineWidth = [44, 28, 14][pass];
    g.stroke();
  }
  _wispTex = new THREE.CanvasTexture(c);
  _wispTex.colorSpace = THREE.SRGBColorSpace;
  return _wispTex;
}

export class Bulb {
  constructor(gltfScene) {
    this.root = new THREE.Group();
    this.root.name = 'idea_bulb';
    this.body = gltfScene.clone(true);
    this.body.scale.setScalar(1.0);
    this.root.add(this.body);

    this.glass = new THREE.MeshPhysicalMaterial({
      color: GLASS_OFF.clone(), roughness: 0.32, clearcoat: 0.7, clearcoatRoughness: 0.12,
      emissive: EMISSIVE.clone(), emissiveIntensity: 0, sheen: 0.2, sheenColor: new THREE.Color(1, 1, 1),
    });
    this.filament = new THREE.MeshStandardMaterial({ color: 0x6d5a3a, emissive: EMISSIVE.clone(), emissiveIntensity: 0 });
    this.body.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = false; // floating graphic: no shadow on the set
      o.receiveShadow = false;
      if (o.name.startsWith('bulb_glass')) o.material = this.glass;
      else if (o.name.startsWith('bulb_filament')) o.material = this.filament;
    });

    // glow sprite
    this.glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: glowTexture(), color: new THREE.Color('#ffd98a'), blending: THREE.AdditiveBlending,
      depthWrite: false, transparent: true, opacity: 0,
    }));
    this.glow.renderOrder = 10;
    this.root.add(this.glow);

    // rays (camera-facing ring of dashes)
    this.rays = new THREE.Group();
    const rayMat = new THREE.MeshBasicMaterial({
      map: rayTexture(), color: new THREE.Color('#f3d58e'), transparent: true, depthWrite: false, opacity: 0,
    });
    this.rayMat = rayMat;
    const rayGeo = new THREE.PlaneGeometry(0.02, 0.075);
    rayGeo.translate(0, 0.0375, 0);
    for (let i = 0; i < 8; i++) {
      const pivot = new THREE.Group();
      pivot.rotation.z = (i / 8) * Math.PI * 2 + Math.PI / 8;
      const m = new THREE.Mesh(rayGeo, rayMat);
      m.position.y = 0.13;
      m.renderOrder = 11;
      pivot.add(m);
      this.rays.add(pivot);
    }
    this.root.add(this.rays);

    // smoke: 3 puffs + a wisp (world-space, children of root)
    this.puffs = [0, 1, 2].map((i) => {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({
        map: puffTexture(5 + i), color: SMOKE.clone(), transparent: true, depthWrite: false, opacity: 0,
      }));
      s.renderOrder = 12;
      this.root.add(s);
      return s;
    });
    this.wisp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: fatWispTexture(), color: SMOKE.clone(), transparent: true, depthWrite: false, opacity: 0,
    }));
    this.wisp.center.set(0.5, 0.0);
    this.wisp.renderOrder = 12;
    this.root.add(this.wisp);

    // subtle warm light so the level reads on the hair/head
    this.light = new THREE.PointLight(0xffd9a0, 0, 1.6, 2);
    this.light.position.set(0, -0.02, 0);
    this.root.add(this.light);
  }

  /**
   * @param {object} s
   * @param {number} s.t          scene time (s)
   * @param {THREE.Vector3} s.anchor  head centre (world)
   * @param {number} s.level      0..1
   * @param {number|null} s.outT  seconds since it went out (null = not out)
   * @param {THREE.Camera} s.camera
   * @param {boolean} s.visible
   */
  update({ t, anchor, level, outT = null, camera, visible = true, height = 0.76 }) {
    this.root.visible = visible;
    if (!visible) return;
    const b = clamp(level, 0, 1);
    const lit = b > 0.05 ? 1 : 0;
    // drift (pure: sum of smooth noises)
    const bob = 0.025 * fbm1(t * 0.55, 11, 2) + 0.006 * Math.sin(t * 2.1);
    const tiltZ = 0.05 * fbm1(t * 0.42, 23, 2);
    const tiltX = 0.035 * fbm1(t * 0.37, 37, 2);
    this.root.position.set(anchor.x, anchor.y + height + bob, anchor.z);

    // out: droop + tilt over 0.5 s with a little settle
    let droop = 0, tilt = 0;
    if (outT !== null && outT >= 0) {
      const e = ease.outBack(clamp(outT / 0.5), 1.4);
      droop = 0.09 * e;
      tilt = 0.5 * e;
    }
    this.body.position.set(0, -droop, 0);
    this.body.rotation.set(tiltX, 0, tiltZ + tilt);

    this.glass.color.copy(GLASS_OFF).lerp(GLASS_ON, lit * smoothstep(0.05, 0.6, b));
    this.glass.emissiveIntensity = lit * (0.15 + 3.1 * b * b);
    this.filament.emissiveIntensity = lit * (1.5 + 7 * b);
    this.light.intensity = lit * 0.35 * b;

    const gs = 0.42 + 0.55 * b;
    this.glow.scale.set(gs, gs, 1);
    this.glow.position.set(0, -droop * 0.8, 0);
    this.glow.material.opacity = lit * (0.08 + 0.6 * b * b);

    const rayAmt = smoothstep(0.5, 0.95, b) * lit;
    this.rayMat.opacity = rayAmt * 0.95;
    this.rays.visible = rayAmt > 0.001;
    if (this.rays.visible) {
      this.rays.quaternion.copy(camera.quaternion);
      const pulse = 1 + 0.12 * Math.sin(t * 5.3);
      this.rays.children.forEach((p, i) => {
        const m = p.children[0];
        m.scale.set(1, rayAmt * pulse * (i % 2 ? 0.8 : 1.0), 1);
        m.position.y = 0.12 + 0.012 * pulse;
      });
    }

    // smoke puffs after the droop
    // smoke starts at the bulb's top, nudged toward the camera so the glass never hides it
    const toCam = new THREE.Vector3();
    if (camera) toCam.copy(camera.position).sub(this.root.position).setY(0).normalize().multiplyScalar(0.1);
    const top = _v.set(Math.sin(-tilt) * 0.1 + toCam.x, 0.03 - droop, toCam.z);
    this.puffs.forEach((s, i) => {
      const pt = outT === null ? -1 : outT - (0.12 + i * 0.24);
      const life = 1.5;
      if (pt < 0 || pt > life) {
        s.material.opacity = 0;
        s.visible = false;
        return;
      }
      s.visible = true;
      const p = pt / life;
      s.position.set(top.x + 0.03 * Math.sin(p * 4 + i * 2) + (i - 1) * 0.025, top.y + 0.04 + 0.3 * ease.outQuad(p), top.z);
      const sc = 0.07 + 0.22 * ease.outCubic(p);
      s.scale.set(sc, sc, 1);
      s.material.rotation = i * 1.3 + p * 0.8;
      s.material.opacity = 0.95 * Math.min(1, pt / 0.1) * (1 - p) ** 1.2;
    });
    const wt = outT === null ? -1 : outT - 0.1;
    if (wt >= 0 && wt < 3.2) {
      // the snuffed-out wisp: a thin curl that rises and stretches, readable at a glance
      this.wisp.visible = true;
      const p = wt / 3.2;
      this.wisp.position.set(top.x + 0.015 * fbm1(wt * 0.9, 61), top.y + 0.02 + 0.12 * ease.outQuad(p), top.z);
      this.wisp.scale.set(0.24 + 0.05 * p, 0.36 + 0.24 * ease.outCubic(p), 1);
      this.wisp.material.rotation = 0.12 * fbm1(wt * 0.7, 63);
      this.wisp.material.opacity = 0.9 * Math.min(1, wt / 0.2) * (1 - p) ** 0.8;
    } else {
      this.wisp.visible = false;
    }
    void spring;
  }
}
