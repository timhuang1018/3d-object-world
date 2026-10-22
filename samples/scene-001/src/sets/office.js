// Office + hall set wrapper: door hinge (spring ring), swivel chair (seat.ry / seat.pz), laptop screen,
// warm hall light, faint blue laptop light, wall clock.
import * as THREE from 'three';
import { collectSpots, findNode } from '@infra/loader.js';
import { LaptopScreen } from '../props/screen.js';

const DEG = Math.PI / 180;

export class OfficeSet {
  constructor(gltf) {
    this.root = gltf ? gltf.scene : new THREE.Group();
    this.root.name = 'set_office';
    this.spots = collectSpots(this.root);
    const grab = (name) => {
      const n = findNode(this.root, name);
      return n ? { node: n, q: n.quaternion.clone(), p: n.position.clone() } : null;
    };
    this.door = grab('door_hinge');
    this.chairBase = grab('chair_base');
    this.chairSwivel = grab('chair_swivel');
    this.clockH = grab('clock_hour');
    this.clockM = grab('clock_minute');
    const screenMesh = findNode(this.root, 'laptop_screen');
    let mesh = screenMesh;
    if (mesh && !mesh.isMesh) mesh.traverse((o) => { if (!mesh.isMesh && o.isMesh) mesh = o; });
    this.screen = new LaptopScreen(mesh && mesh.isMesh ? mesh : null);

    // lights
    const hallAnchor = findNode(this.root, 'light_hall');
    this.hallLight = new THREE.PointLight(0xffc68a, 2.2, 5.5, 2);
    (hallAnchor || this.root).getWorldPosition(this.hallLight.position);
    if (!hallAnchor) this.hallLight.position.set(-3.5, 1.9, -0.9);
    this.root.add(this.hallLight);
    const lapAnchor = findNode(this.root, 'light_laptop');
    this.laptopLight = new THREE.PointLight(0x9fc0ff, 0.08, 1.4, 2);
    if (lapAnchor) lapAnchor.getWorldPosition(this.laptopLight.position);
    else this.laptopLight.position.set(0.85, 0.72, -0.25);
    this.root.add(this.laptopLight);
    this._q = new THREE.Quaternion();
    this._axisY = new THREE.Vector3(0, 1, 0);
    this._axisX = new THREE.Vector3(1, 0, 0);
  }

  spot(name) {
    return this.spots[name];
  }

  /** s: { t, doorAngle (rad), seatRy (rad), seatPz (m), typed (chars), visible } */
  update(s) {
    this.root.visible = s.visible !== false;
    if (!this.root.visible) return;
    if (this.door) this.door.node.quaternion.copy(this.door.q).multiply(this._q.setFromAxisAngle(this._axisY, s.doorAngle || 0));
    if (this.chairBase) this.chairBase.node.position.copy(this.chairBase.p).add(new THREE.Vector3(0, 0, s.seatPz || 0));
    if (this.chairSwivel) this.chairSwivel.node.quaternion.copy(this.chairSwivel.q).multiply(this._q.setFromAxisAngle(this._axisY, s.seatRy || 0));
    // wall clock: ~3:42, creeping (deterministic)
    const minutes = 42 + (s.t || 0) * 0.35;
    if (this.clockM) this.clockM.node.quaternion.copy(this.clockM.q).multiply(this._q.setFromAxisAngle(this._axisX, -minutes * 6 * DEG));
    if (this.clockH) this.clockH.node.quaternion.copy(this.clockH.q).multiply(this._q.setFromAxisAngle(this._axisX, -(3 * 30 + minutes * 0.5) * DEG));
    this.screen.update({ t: s.t || 0, typed: s.typed || 0 });
  }
}
