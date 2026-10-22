// Kitchen set wrapper: spots, the dish-cycle plates (the SAME plate objects travel stack -> hand -> rack;
// the director's dishwash choreography places them), merged soap foam (gentle breathing), the faucet
// stream (turns on/off with a falling head and tail), splash rings + droplets, rising/popping bubbles.
// Everything here is a pure function of the state handed in (no frame-to-frame memory).
import * as THREE from 'three';
import { collectSpots, findNode } from '@infra/loader.js';
import { clamp, fbm1, rng } from '@infra/math.js';
import { WaterStream } from '../props/fx.js';

export const STACK_PITCH = 0.0215;
const SPLASH_POOL = 4;
const DROPS = 12;
const GRAV = -3.2; // toy-scale gravity (m/s^2): droplets read at 30 fps without vanishing in 2 frames

const waterMat = () => new THREE.MeshPhysicalMaterial({ color: '#e4f1f6', roughness: 0.05, transparent: true, opacity: 0.75, clearcoat: 1, depthWrite: false });

export class KitchenSet {
  constructor(gltf, dishes) {
    this.root = gltf ? gltf.scene : new THREE.Group();
    this.root.name = 'set_kitchen';
    this.spots = collectSpots(this.root);
    this.spout = findNode(this.root, 'faucet_spout');
    this.foam = findNode(this.root, 'sink_foam_base');
    this.foamBase = this.foam ? { s: this.foam.scale.clone(), p: this.foam.position.clone() } : null;
    // water line from the translucent water sheet (falls back to the build constant)
    this.waterY = 0.468;
    const wm = findNode(this.root, 'sink_water');
    if (wm) {
      this.root.updateMatrixWorld(true);
      const bb = new THREE.Box3().setFromObject(wm);
      if (Number.isFinite(bb.max.y)) {
        this.waterY = bb.max.y;
        const c = bb.getCenter(new THREE.Vector3()), sz = bb.getSize(new THREE.Vector3());
        this.basin = { cx: c.x, cz: c.z, a: sz.x / 2 - 0.02, b: sz.z / 2 - 0.02 };
      }
    }
    this.water = new WaterStream();
    this.water.mesh.renderOrder = 3;
    this.root.add(this.water.root);

    // dishes from props/dishes.glb
    this.protos = {};
    if (dishes) {
      for (const name of ['plate_dirty', 'plate_clean', 'sponge', 'suds_puff', 'suds_dab']) {
        const n = findNode(dishes.scene, name);
        if (n) {
          const c = n.clone(true);
          c.position.set(0, 0, 0);
          c.rotation.set(0, 0, 0);
          c.updateMatrixWorld(true);
          this.protos[name] = c;
        }
      }
    }
    // stack of 6 dirty plates: the bottom three stay; the top three are wash plates (they leave in
    // order 5, 4, 3).  washPlates = [the one already in Tim's hands, stack 5, stack 4, stack 3]
    this.stack = [];
    this.washPlates = [];
    const stackSpot = this.spots.plate_stack;
    this.stackBase = [];
    if (stackSpot && this.protos.plate_dirty) {
      for (let i = 0; i < 6; i++) {
        const base = stackSpot.position.clone().add(new THREE.Vector3(0, i * STACK_PITCH, 0));
        this.stackBase.push(base);
        if (i < 3) {
          const p = this.protos.plate_dirty.clone(true);
          p.position.copy(base);
          p.rotation.y = i * 1.7; // vary smudges
          this.root.add(p);
          this.stack.push(p);
        }
      }
    }
    if (this.protos.plate_dirty && this.protos.plate_clean) {
      this.washPlates.push(this._washPlate(0.6));
      for (const i of [5, 4, 3]) this.washPlates.push(this._washPlate(i * 1.7));
    }

    // splash pool: a widening ring on the water + droplets on ballistic arcs
    this.splashes = [];
    const ringGeo = new THREE.RingGeometry(0.78, 1.0, 48).rotateX(-Math.PI / 2);
    const dropGeo = new THREE.SphereGeometry(0.005, 10, 8);
    // flared open cylinder (unit radius at the base, wider lip), origin at the base
    const crownGeo = new THREE.CylinderGeometry(1.18, 1.0, 1, 40, 1, true).translate(0, 0.5, 0);
    for (let k = 0; k < SPLASH_POOL; k++) {
      const g = new THREE.Group();
      const ringMat = new THREE.MeshBasicMaterial({ color: '#f4fbff', transparent: true, opacity: 0.8, depthWrite: false, side: THREE.DoubleSide });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.renderOrder = 4;
      g.add(ring);
      // the crown: a thin translucent sheet of water thrown up around the plate rim
      const crownMat = new THREE.MeshPhysicalMaterial({ color: '#eef7fb', roughness: 0.05, transparent: true, opacity: 0.6, clearcoat: 1, depthWrite: false, side: THREE.DoubleSide });
      const crown = new THREE.Mesh(crownGeo, crownMat);
      crown.renderOrder = 4;
      g.add(crown);
      const drops = [];
      const dm = waterMat();
      for (let d = 0; d < DROPS; d++) {
        const m = new THREE.Mesh(dropGeo, dm);
        m.renderOrder = 4;
        g.add(m);
        drops.push(m);
      }
      g.visible = false;
      this.root.add(g);
      this.splashes.push({ g, ring, ringMat, crown, crownMat, drops, dm });
    }

    // rising bubbles that pop (deterministic table)
    this.bubbles = [];
    const bubGeo = new THREE.SphereGeometry(1, 16, 12);
    const bubMat = new THREE.MeshPhysicalMaterial({ color: '#ffffff', roughness: 0.04, transparent: true, opacity: 0.45, clearcoat: 1, iridescence: 0.9, iridescenceIOR: 1.3, depthWrite: false });
    const r = rng(0xb0b1e);
    for (let k = 0; k < 9; k++) {
      const m = new THREE.Mesh(bubGeo, bubMat);
      m.renderOrder = 5;
      m.visible = false;
      this.root.add(m);
      this.bubbles.push({ m, u: r.range(-0.85, 0.85), v: r.range(-0.8, 0.8), period: r.range(1.1, 1.7), phase: r.range(0, 2), size: r.range(0.0045, 0.0075), seed: k * 7 + 3 });
    }
  }

  _washPlate(texYaw) {
    const holder = new THREE.Group();
    holder.name = 'wash_plate';
    const inner = new THREE.Group();
    inner.rotation.y = texYaw;
    const clean = this.protos.plate_clean.clone(true);
    const dirty = this.protos.plate_dirty.clone(true);
    const mats = [];
    dirty.traverse((o) => {
      if (!o.isMesh) return;
      const ms = (Array.isArray(o.material) ? o.material : [o.material]).map((m) => {
        const c = m.clone();
        c.transparent = true;
        c.depthWrite = false;
        c.polygonOffset = true;
        c.polygonOffsetFactor = -2;
        c.polygonOffsetUnits = -2;
        mats.push(c);
        return c;
      });
      o.material = Array.isArray(o.material) ? ms : ms[0];
      o.renderOrder = 2;
    });
    inner.add(clean, dirty);
    holder.add(inner);
    let suds = null;
    if (this.protos.suds_dab) {
      suds = this.protos.suds_dab.clone(true);
      suds.position.set(0.018, 0.0072, -0.012);
      holder.add(suds);
    }
    this.root.add(holder);
    return { obj: holder, dirtyMats: mats, dirty, suds };
  }

  spot(name) {
    return this.spots[name];
  }

  makeProp(name) {
    return this.protos[name] ? this.protos[name].clone(true) : null;
  }

  /** Place wash plate i: world position / quaternion of its frame (bottom centre, +y = face normal),
   *  dirt 0..1 (smudges fade), suds 0..1 (foam clinging to the face). */
  setPlate(i, { position, quaternion, dirt = 1, suds = 0, visible = true }) {
    const P = this.washPlates[i];
    if (!P) return;
    P.obj.visible = visible;
    if (!visible) return;
    this.root.updateMatrixWorld();
    // the set root sits at the origin; convert anyway so a moved set keeps working
    const inv = new THREE.Matrix4().copy(this.root.matrixWorld).invert();
    const m = new THREE.Matrix4().compose(position, quaternion, new THREE.Vector3(1, 1, 1)).premultiply(inv);
    m.decompose(P.obj.position, P.obj.quaternion, P.obj.scale);
    const d = clamp(dirt);
    for (const mm of P.dirtyMats) mm.opacity = d;
    P.dirty.visible = d > 0.003;
    if (P.suds) {
      P.suds.visible = suds > 0.02;
      P.suds.scale.set(0.45 + 0.9 * suds, 0.35 + 1.1 * suds, 0.45 + 0.9 * suds);
    }
  }

  /** Faucet stream: `on`/`off` times (s) for the current run (off = Infinity while running); the column's
   *  head falls from the spout to `hitY` and, after off, its tail falls after it. */
  setStream({ t, on = Infinity, off = Infinity, hitY = 0.5 }) {
    if (!this.spout || !(t >= on)) {
      this.water.update({ visible: false });
      return;
    }
    const sp = new THREE.Vector3();
    this.spout.getWorldPosition(sp);
    this.root.worldToLocal(sp);
    const v = 1.6;
    const full = Math.max(0.01, sp.y - hitY);
    const head = Math.min(full, v * (t - on));
    const tail = t >= off ? Math.min(full, v * (t - off) + 0.5 * 4 * (t - off) ** 2) : 0;
    if (head - tail < 0.004) {
      this.water.update({ visible: false });
      return;
    }
    this.water.update({ spout: sp.clone().add(new THREE.Vector3(0, -tail, 0)), length: head - tail, t, visible: true });
  }

  /** Splash events [{ t0, pos: Vector3 (on the water), size }]; renders the ones younger than 0.6 s. */
  setSplashes(t, events) {
    const live = events.filter((e) => t >= e.t0 && t < e.t0 + 0.6).slice(0, SPLASH_POOL);
    this.splashes.forEach((S, k) => {
      const e = live[k];
      S.g.visible = !!e;
      if (!e) return;
      const a = t - e.t0;
      const sz = e.size ?? 1;
      S.g.position.copy(e.pos);
      const rr = sz * (0.1 + 0.1 * (1 - Math.exp(-a * 6)));
      S.ring.scale.set(rr, 1, rr);
      S.ring.position.y = 0.004;
      S.ringMat.opacity = 0.95 * Math.max(0, 1 - a / 0.55) ** 1.2;
      // crown rises fast and collapses within ~0.25 s
      const ch = a < 0.28 ? Math.sin((a / 0.28) * Math.PI) * (1 - a / 0.4) : 0;
      S.crown.visible = ch > 0.01;
      S.crown.scale.set(sz * (0.11 + 0.05 * a / 0.28), sz * 0.03 * ch, sz * (0.11 + 0.05 * a / 0.28));
      S.crownMat.opacity = 0.65 * Math.min(1, ch * 2);
      const r = rng(Math.round(e.t0 * 1000) + 17);
      S.drops.forEach((m) => {
        const th = r.range(0, Math.PI * 2);
        const sp = sz * r.range(0.18, 0.42);
        const vy = sz * r.range(0.45, 0.85);
        const delay = r.range(0, 0.05);
        const aa = a - delay;
        const y = vy * aa + 0.5 * GRAV * aa * aa;
        m.visible = aa > 0 && y > -0.002;
        if (!m.visible) return;
        m.position.set(Math.cos(th) * (0.105 * sz + sp * aa), y + 0.004, Math.sin(th) * (0.105 * sz + sp * aa));
        const s = 0.7 + 0.6 * r.random();
        m.scale.setScalar(s * sz);
      });
    });
  }

  /** s: { t, visible, avoid?: [x, z, rx, rz] (the work patch: no bubbles there) } */
  update(s) {
    this.root.visible = s.visible !== false;
    if (!this.root.visible) return;
    const t = s.t || 0;
    if (this.foam && this.foamBase) {
      // the foam mass breathes very slightly (settling suds), never a bounce
      const w = 1 + 0.035 * fbm1(t * 0.9, 51);
      this.foam.scale.set(this.foamBase.s.x, this.foamBase.s.y * w, this.foamBase.s.z);
    }
    // bubbles: rise from the foam top, swell, pop
    const A = this.basin ? { ...this.basin, top: this.waterY + 0.018, avoid: s.avoid } : null;
    for (const B of this.bubbles) {
      if (!A) {
        B.m.visible = false;
        continue;
      }
      const ph = (t + B.phase) / B.period;
      const cyc = Math.floor(ph);
      const a = (ph - cyc) * B.period; // age within this cycle (s)
      const life = 0.75;
      if (a > life + 0.06) {
        B.m.visible = false;
        continue;
      }
      // a new spot per cycle (seeded), avoiding the work patch
      const r = rng(B.seed * 131 + cyc * 7919);
      let u = B.u + r.range(-0.12, 0.12), v = B.v + r.range(-0.12, 0.12);
      if (A.avoid && Math.hypot((A.cx + u * A.a - A.avoid[0]) / A.avoid[2], (A.cz + v * A.b - A.avoid[1]) / A.avoid[3]) < 1.1) u = -Math.sign(u || 1) * 0.8;
      const k = Math.min(1, a / life);
      const x = A.cx + u * A.a + 0.003 * Math.sin(a * 17 + B.seed);
      const z = A.cz + v * A.b + 0.003 * Math.cos(a * 13 + B.seed);
      const y = A.top + 0.035 * (1 - (1 - k) * (1 - k));
      let sc = B.size * (0.5 + 0.5 * k);
      if (a > life) sc *= 1.35 * (1 - (a - life) / 0.06); // pop
      B.m.visible = sc > 0.0005;
      B.m.position.set(x, y, z);
      B.m.scale.setScalar(Math.max(0.0001, sc));
    }
  }
}
