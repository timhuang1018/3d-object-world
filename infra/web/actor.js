// Actor base: a GLB character placed in the world, posed by layered clips + procedural tweaks.
import * as THREE from 'three';
import { Rig } from './rig.js';

const _v = new THREE.Vector3();

export class Actor {
  constructor(name, gltf) {
    this.name = name;
    this.root = new THREE.Group();
    this.root.name = `actor_${name}`;
    this.model = gltf ? gltf.scene : new THREE.Group();
    this.root.add(this.model);
    this.rig = new Rig(this.model, gltf?.animations ?? []);
    this.head = this.rig.joint('head') || this.model;
    // head centre offset (head-local) from the face-decal frame, so graphics anchor on the face,
    // not on the head pivot (the lioness pivots at the neck base)
    this.headCenterOffset = new THREE.Vector3();
    this.model.updateMatrixWorld(true);
    this.model.traverse((o) => {
      const c = o.userData?.decal_center;
      if (c && this.head !== this.model) {
        const hp = this.head.getWorldPosition(new THREE.Vector3());
        this.headCenterOffset.set(c[0] - hp.x, c[1] - hp.y, c[2] - hp.z);
      }
    });
  }

  has(clip) {
    return this.rig.clips.has(clip);
  }

  place(x, y, z, yaw = 0) {
    this.root.position.set(x, y, z);
    this.root.rotation.set(0, yaw, 0);
  }

  /** layers: [{ clip, time, weight=1, loop=false, mask, exclude }] applied in order over the rest pose */
  pose(layers = [], post = null) {
    const rig = this.rig;
    rig.reset();
    for (const L of layers) {
      if (!L || !(L.weight ?? 1) || !rig.clips.has(L.clip)) continue;
      rig.applyClip(L.clip, L.time ?? 0, L.weight ?? 1, L);
    }
    if (post) post(rig);
    this.root.updateMatrixWorld(true);
  }

  headWorld(out = new THREE.Vector3()) {
    return this.head.getWorldPosition(out);
  }

  /** Centre of the face (decal frame) in world space. */
  headCenter(out = new THREE.Vector3()) {
    out.copy(this.headCenterOffset);
    return this.head.localToWorld(out);
  }

  jointWorld(name, out = new THREE.Vector3()) {
    const j = this.rig.joint(name);
    return j ? j.getWorldPosition(out) : this.root.getWorldPosition(out);
  }

  /** Yaw (radians, about +Y) from this actor's facing to a world point, for look-ats. */
  yawTo(point) {
    this.root.getWorldPosition(_v);
    const dx = point.x - _v.x, dz = point.z - _v.z;
    let a = Math.atan2(dx, dz) - this.root.rotation.y;
    while (a > Math.PI) a -= 2 * Math.PI;
    while (a < -Math.PI) a += 2 * Math.PI;
    return a;
  }
}

/** Placeholder capsule for a character whose GLB is not built yet. */
export function placeholder(color = 0xcc8866, height = 1.5) {
  const g = new THREE.Group();
  const m = new THREE.Mesh(new THREE.CapsuleGeometry(height * 0.2, height * 0.55, 8, 16), new THREE.MeshStandardMaterial({ color, roughness: 0.6 }));
  m.position.y = height / 2;
  m.castShadow = true;
  g.add(m);
  const head = new THREE.Bone();
  head.name = 'head';
  head.position.y = height * 0.72;
  g.add(head);
  return { scene: g, animations: [] };
}
