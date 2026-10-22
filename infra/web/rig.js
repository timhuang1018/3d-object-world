// Deterministic pose engine for GLB rigs.
//
// Joints come from the GLB (bones exported "up, roll 0" => identity rest rotations, so
// joint-local axes == character axes: x = character's left, y = up, z = front).
// Clips are sampled with KeyframeTrack interpolants (pure functions of time) and blended
// layer by layer onto the rest pose:  reset() -> applyClip(...) -> addRot(...) -> ...
import * as THREE from 'three';

const _q = new THREE.Quaternion();
const _q2 = new THREE.Quaternion();
const _v = new THREE.Vector3();
const _e = new THREE.Euler();
const EPS = 1e-4;

function arraysClose(a, b, n, off = 0, eps = EPS) {
  for (let i = 0; i < n; i++) if (Math.abs(a[off + i] - b[i]) > eps) return false;
  return true;
}

export class Rig {
  constructor(root, animations = []) {
    this.root = root;
    this.joints = new Map();
    this.rest = new Map();
    root.traverse((o) => {
      if (o.isBone || o.type === 'Bone' || o.userData?.joint) this._addJoint(o);
    });
    this.clips = new Map();
    for (const clip of animations) this.addClip(clip);
  }

  _addJoint(o) {
    if (this.joints.has(o.name)) return;
    this.joints.set(o.name, o);
    this.rest.set(o.name, { p: o.position.clone(), q: o.quaternion.clone(), s: o.scale.clone() });
  }

  joint(name) {
    return this.joints.get(name);
  }

  addClip(clip) {
    const tracks = [];
    for (const track of clip.tracks) {
      const { nodeName, propertyName } = THREE.PropertyBinding.parseTrackName(track.name);
      let node = this.joints.get(nodeName);
      if (!node) {
        node = this.root.getObjectByName(nodeName);
        if (node) this._addJoint(node);
      }
      if (!node || !['quaternion', 'position', 'scale'].includes(propertyName)) continue;
      const size = track.getValueSize();
      const rest = this.rest.get(node.name);
      const restArr = propertyName === 'quaternion' ? rest.q.toArray() : (propertyName === 'position' ? rest.p : rest.s).toArray();
      // skip channels that never leave the rest value (lets partial clips layer)
      let atRest = true;
      for (let k = 0; k < track.times.length && atRest; k++) {
        if (!arraysClose(track.values, restArr, size, k * size, propertyName === 'quaternion' ? 2e-4 : 2e-4)) atRest = false;
      }
      if (atRest) continue;
      tracks.push({ node, prop: propertyName, interp: track.createInterpolant(), size });
    }
    this.clips.set(clip.name, { name: clip.name, duration: clip.duration, tracks });
  }

  /** Back to the bind/rest pose. */
  reset() {
    for (const [name, o] of this.joints) {
      const r = this.rest.get(name);
      o.position.copy(r.p);
      o.quaternion.copy(r.q);
      o.scale.copy(r.s);
    }
  }

  clipDuration(name) {
    return this.clips.get(name)?.duration ?? 0;
  }

  /** Blend a clip sampled at `time` onto the current pose with `weight` (0..1).
   *  opts.loop wraps time; opts.mask = Set of joint names to include; opts.exclude = Set to skip. */
  applyClip(name, time, weight = 1, opts = {}) {
    const clip = this.clips.get(name);
    if (!clip || weight <= 0) return;
    let t = time;
    if (opts.loop && clip.duration > 0) t = ((t % clip.duration) + clip.duration) % clip.duration;
    else t = Math.min(Math.max(t, 0), clip.duration);
    for (const tr of clip.tracks) {
      if (opts.mask && !opts.mask.has(tr.node.name)) continue;
      if (opts.exclude && opts.exclude.has(tr.node.name)) continue;
      const v = tr.interp.evaluate(t);
      if (tr.prop === 'quaternion') {
        _q.fromArray(v);
        if (weight >= 1) tr.node.quaternion.copy(_q);
        else tr.node.quaternion.slerp(_q, weight);
      } else {
        _v.fromArray(v);
        const target = tr.prop === 'position' ? tr.node.position : tr.node.scale;
        if (weight >= 1) target.copy(_v);
        else target.lerp(_v, weight);
      }
    }
  }

  /** Multiply an extra rotation (radians, Euler 'ZYX' == Blender XYZ) in the joint's own frame. */
  addRot(name, rx = 0, ry = 0, rz = 0, weight = 1) {
    const o = this.joints.get(name);
    if (!o || weight === 0) return;
    _e.set(rx * weight, ry * weight, rz * weight, 'ZYX');
    _q2.setFromEuler(_e);
    o.quaternion.multiply(_q2);
  }

  /** Pre-multiply a rotation expressed in the PARENT frame (useful for whole-limb swings). */
  preRot(name, rx = 0, ry = 0, rz = 0, weight = 1) {
    const o = this.joints.get(name);
    if (!o || weight === 0) return;
    _e.set(rx * weight, ry * weight, rz * weight, 'ZYX');
    _q2.setFromEuler(_e);
    o.quaternion.premultiply(_q2);
  }

  /** Blend joint rotation toward an absolute local rotation (radians, 'ZYX'). */
  setRot(name, rx = 0, ry = 0, rz = 0, weight = 1) {
    const o = this.joints.get(name);
    if (!o || weight <= 0) return;
    _e.set(rx, ry, rz, 'ZYX');
    _q2.setFromEuler(_e);
    if (weight >= 1) o.quaternion.copy(_q2);
    else o.quaternion.slerp(_q2, weight);
  }

  addPos(name, x = 0, y = 0, z = 0, weight = 1) {
    const o = this.joints.get(name);
    if (!o) return;
    o.position.x += x * weight;
    o.position.y += y * weight;
    o.position.z += z * weight;
  }

  mulScale(name, sx = 1, sy = 1, sz = 1) {
    const o = this.joints.get(name);
    if (!o) return;
    o.scale.x *= sx;
    o.scale.y *= sy;
    o.scale.z *= sz;
  }
}
