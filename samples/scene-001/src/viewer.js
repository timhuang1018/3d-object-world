// Bank viewer: inspect one GLB under Look A.  Used interactively and by infra/tools/shot.mjs.
//
//   /viewer.html?asset=characters/tim.glb                 orbit view (drag / wheel)
//   &view=front|34|34r|side|sider|back|top|face            fixed camera preset
//   &sheet=views                                           6-view contact sheet
//   &sheet=action&action=walk&n=6&view=34                  N frames across an action
//   &action=sit_type&at=0.4                                pose with an action at time `at`
//   &expr=<name>                                           face decal expression (when the actor supports it)
//   &decal=grid                                            debug UV grid on decal shells
//   &bones=1  &spots=1  &post=0  &floor=0  &tile=640
//   &cam=x,y,z&target=x,y,z&fov=30                         explicit camera (world coords)
//   &focus=<nodeName>&dist=1.6                             frame around a node
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { Look } from '@infra/look.js';
import { loadAsset, findNode, collectSpots } from '@infra/loader.js';
import { Rig } from '@infra/rig.js';
import { decorateAsset } from './actors/registry.js';

const q = new URLSearchParams(location.search);
const assetRel = q.get('asset') || 'test/smoketest.glb';
const tile = parseInt(q.get('tile') || '640', 10);
const sheetMode = q.get('sheet');
const info = document.getElementById('info');

const canvas = document.getElementById('gl');
const W = sheetMode ? tile : parseInt(q.get('w') || '1280', 10);
const H = sheetMode ? tile : parseInt(q.get('h') || '720', 10);
const look = new Look(canvas, { width: W, height: H, post: q.get('post') !== '0' });
const { scene, camera } = look;

const app = { ready: false, error: null };
window.__app = app;

function decalGridTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const g = c.getContext('2d');
  g.clearRect(0, 0, 512, 512);
  g.strokeStyle = 'rgba(255,0,80,0.9)';
  g.lineWidth = 2;
  for (let i = 0; i <= 8; i++) {
    g.beginPath(); g.moveTo(i * 64, 0); g.lineTo(i * 64, 512); g.stroke();
    g.beginPath(); g.moveTo(0, i * 64); g.lineTo(512, i * 64); g.stroke();
  }
  g.strokeStyle = 'rgba(0,120,255,1)';
  g.lineWidth = 4;
  g.beginPath(); g.arc(256, 256, 30, 0, Math.PI * 2); g.stroke(); // centre = decal_center
  g.fillStyle = 'rgba(0,160,60,1)';
  g.fillRect(0, 0, 40, 40); // top-left marker (u=0, v=1 in Blender terms => top of head, viewer's left)
  const t = new THREE.CanvasTexture(c);
  t.flipY = false;
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

async function main() {
  const g = await loadAsset(assetRel, look.renderer);
  const root = g.scene;
  scene.add(root);
  const isSet = assetRel.startsWith('sets/');

  if (q.get('floor') !== '0' && !isSet) {
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(6, 96).rotateX(-Math.PI / 2),
      new THREE.MeshStandardMaterial({ color: 0xd8ccba, roughness: 0.8 }),
    );
    floor.receiveShadow = true;
    floor.position.y = -0.001;
    scene.add(floor);
  }

  const rig = new Rig(root, g.animations);
  const deco = await decorateAsset(assetRel, { root, rig, look, query: q });

  if (q.get('decal') === 'grid') {
    const tex = decalGridTexture();
    root.traverse((o) => {
      if (o.isMesh && o.material?.userData?.family === 'decal') {
        o.material.map = tex;
        o.material.visible = true;
        o.material.needsUpdate = true;
      }
    });
  }

  if (q.get('bones') === '1') {
    const sk = new THREE.SkeletonHelper(root);
    sk.material.depthTest = false;
    sk.material.linewidth = 2;
    scene.add(sk);
  }
  if (q.get('spots') === '1') {
    const spots = collectSpots(root);
    for (const [name, s] of Object.entries(spots)) {
      const m = new THREE.Mesh(new THREE.ConeGeometry(0.06, 0.2, 12).rotateX(Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0xff2266, depthTest: false }));
      m.position.copy(s.position).add(new THREE.Vector3(0, 0.1, 0));
      m.rotation.y = s.yaw;
      m.renderOrder = 999;
      scene.add(m);
    }
    console.log('spots', Object.fromEntries(Object.entries(spots).map(([k, s]) => [k, [s.position.x.toFixed(3), s.position.y.toFixed(3), s.position.z.toFixed(3), (s.yaw * 180 / Math.PI).toFixed(1)]])));
  }

  const pose = (actionName, at) => {
    rig.reset();
    if (actionName) rig.applyClip(actionName, at, 1);
    deco?.update?.(at ?? 0, actionName);
    root.updateMatrixWorld(true);
  };
  pose(q.get('action'), parseFloat(q.get('at') || '0'));

  // framing
  const box = new THREE.Box3().setFromObject(root, true);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  look.setShadowCenter(sphere.center.x, 0, sphere.center.z);

  const fov = parseFloat(q.get('fov') || '30');
  camera.fov = fov;
  const presets = {
    front: [0, 8], '34': [35, 14], '34r': [-35, 14], side: [90, 6], sider: [-90, 6], back: [180, 10], top: [25, 55],
  };
  function placeCamera(view) {
    camera.fov = fov;
    camera.aspect = look.width / look.height;
    camera.updateProjectionMatrix();
    let target = sphere.center.clone();
    let r = sphere.radius;
    if (view === 'face' || q.get('focus')) {
      const node = findNode(root, q.get('focus') || 'head');
      if (node) {
        node.getWorldPosition(target);
        r = parseFloat(q.get('dist') || '0.55');
        view = view === 'face' ? 'front' : view;
      }
    }
    const [az, el] = presets[view] || presets['34'];
    const vfov = (camera.fov * Math.PI) / 180;
    const fit = Math.min(vfov, 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect));
    const d = (r / Math.sin(fit / 2)) * 1.08;
    const a = (az * Math.PI) / 180, e = (el * Math.PI) / 180;
    camera.position.set(target.x + d * Math.cos(e) * Math.sin(a), target.y + d * Math.sin(e), target.z + d * Math.cos(e) * Math.cos(a));
    camera.lookAt(target);
    camera.updateMatrixWorld();
    return target;
  }

  const camQ = q.get('cam');
  let controls = null;
  if (camQ) {
    const [x, y, z] = camQ.split(',').map(Number);
    const [tx, ty, tz] = (q.get('target') || '0,1,0').split(',').map(Number);
    camera.position.set(x, y, z);
    camera.lookAt(tx, ty, tz);
    camera.fov = fov;
    camera.updateProjectionMatrix();
  } else {
    const target = placeCamera(q.get('view') || '34');
    if (!sheetMode && !q.get('view')) {
      controls = new OrbitControls(camera, canvas);
      controls.target.copy(target);
      controls.update();
    }
  }

  const sheetCanvas = document.getElementById('sheet');
  app.capture = async () => {
    if (!sheetMode) {
      look.render();
      return canvas.toDataURL('image/png');
    }
    let frames = [];
    if (sheetMode === 'views') {
      frames = ['front', '34', 'side', 'back', '34r', q.get('focus') ? 'face' : 'top'].map((v) => () => placeCamera(v));
      if (findNode(root, 'head') && !q.get('focus')) frames[5] = () => placeCamera('face');
    } else if (sheetMode === 'action') {
      const name = q.get('action');
      const clip = rig.clips.get(name);
      const n = parseInt(q.get('n') || '6', 10);
      const dur = clip ? clip.duration : 1;
      frames = Array.from({ length: n }, (_, i) => () => {
        pose(name, (dur * i) / Math.max(1, n - 1));
        placeCamera(q.get('view') || '34');
      });
    }
    const cols = Math.min(3, frames.length);
    const rows = Math.ceil(frames.length / cols);
    sheetCanvas.width = cols * tile;
    sheetCanvas.height = rows * tile;
    const g2 = sheetCanvas.getContext('2d');
    for (let i = 0; i < frames.length; i++) {
      frames[i]();
      look.render();
      g2.drawImage(canvas, (i % cols) * tile, Math.floor(i / cols) * tile, tile, tile);
    }
    return sheetCanvas.toDataURL('image/png');
  };

  const clipNames = [...rig.clips.keys()];
  info.textContent = `${assetRel}\nclips: ${clipNames.map((n) => `${n} (${rig.clips.get(n).duration.toFixed(2)}s)`).join(', ') || '-'}`;
  console.log('clips', JSON.stringify(clipNames.map((n) => [n, +rig.clips.get(n).duration.toFixed(3)])));
  console.log('bounds', JSON.stringify({ min: box.min.toArray().map((v) => +v.toFixed(3)), max: box.max.toArray().map((v) => +v.toFixed(3)) }));

  if (!sheetMode) {
    const loop = () => {
      controls?.update();
      look.render();
      if (!app.headless) requestAnimationFrame(loop);
    };
    loop();
  }
  app.ready = true;
}

main().catch((e) => {
  console.error(e);
  app.error = String(e?.stack || e);
  info.textContent = app.error;
  app.ready = true;
});
