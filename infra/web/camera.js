// Camera rig: the scripted "shot" camera (a pure function of t, from the scene) and a free camera
// (OrbitControls: drag = orbit/tilt, right-drag / shift-drag = pan, wheel = dolly, alt+wheel = zoom FOV).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { LOOK_A } from './look.js';

export class CameraRig {
  constructor(look, domElement) {
    this.look = look;
    this.shot = look.camera;
    this.free = new THREE.PerspectiveCamera(LOOK_A.camera.fov, look.width / look.height, LOOK_A.camera.near, LOOK_A.camera.far);
    this.mode = 'shot';
    this.controls = new OrbitControls(this.free, domElement);
    this.controls.enabled = false;
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.12;
    this.controls.screenSpacePanning = true;
    this.controls.minDistance = 0.4;
    this.controls.maxDistance = 24;
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.controls.keys = { LEFT: 'KeyA', UP: 'KeyW', RIGHT: 'KeyD', BOTTOM: 'KeyS' };
    this.controls.listenToKeyEvents(window);
    this._target = new THREE.Vector3();
    domElement.addEventListener(
      'wheel',
      (e) => {
        if (this.mode !== 'free' || !e.altKey) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        this.free.fov = THREE.MathUtils.clamp(this.free.fov * (e.deltaY > 0 ? 1.06 : 1 / 1.06), 8, 70);
        this.free.updateProjectionMatrix();
      },
      { capture: true, passive: false },
    );
  }

  /** Apply a shot: { position: [x,y,z], target: [x,y,z], fov, roll } */
  setShot(s) {
    const c = this.shot;
    c.position.set(...s.position);
    this._target.set(...s.target);
    c.up.set(0, 1, 0);
    c.lookAt(this._target);
    if (s.roll) c.rotateZ(s.roll);
    if (c.fov !== s.fov) {
      c.fov = s.fov;
      c.updateProjectionMatrix();
    }
    c.updateMatrixWorld();
    this.shotTarget = this._target;
  }

  get active() {
    return this.mode === 'free' ? this.free : this.shot;
  }

  setMode(mode) {
    if (mode === this.mode) return;
    if (mode === 'free') {
      // start the free camera exactly where the shot camera is
      this.free.position.copy(this.shot.position);
      this.free.fov = this.shot.fov;
      this.free.aspect = this.shot.aspect;
      this.free.updateProjectionMatrix();
      this.controls.target.copy(this.shotTarget || new THREE.Vector3(0, 1, 0));
      this.controls.update();
    }
    this.mode = mode;
    this.controls.enabled = mode === 'free';
  }

  resize(w, h) {
    for (const c of [this.shot, this.free]) {
      c.aspect = w / h;
      c.updateProjectionMatrix();
    }
  }

  update() {
    if (this.mode === 'free') this.controls.update();
  }
}
