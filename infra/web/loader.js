// GLB loading with caching + Look A conform.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { conformScene } from './conform.js';

const loader = new GLTFLoader();
const cache = new Map();

export function assetUrl(rel) {
  const base = import.meta.env?.BASE_URL ?? '/';
  return `${base}assets/${rel}`;
}

/** Load a GLB once; returns { scene, animations, json } (scene is the original — clone if reused). */
export function loadGLB(rel) {
  if (!cache.has(rel)) {
    cache.set(
      rel,
      new Promise((resolve, reject) => {
        loader.load(
          assetUrl(rel),
          (gltf) => resolve({ scene: gltf.scene, animations: gltf.animations, json: gltf.parser.json }),
          undefined,
          (err) => reject(new Error(`Failed to load ${rel}: ${err?.message || err}`)),
        );
      }),
    );
  }
  return cache.get(rel);
}

/** Load + conform materials/shadows. */
export async function loadAsset(rel, renderer) {
  const g = await loadGLB(rel);
  conformScene(g.scene, renderer);
  return g;
}

/** Find a node by (sanitised) name. GLTFLoader strips '.', ':', '/', '[', ']' from names. */
export function findNode(root, name) {
  let found = null;
  root.traverse((o) => {
    if (!found && o.name === name) found = o;
  });
  return found;
}

/** Collect spot empties: nodes named spot_<name> with extras -> { name: {position, yaw, extras, node} } */
export function collectSpots(root) {
  const spots = {};
  root.updateMatrixWorld(true);
  root.traverse((o) => {
    if (o.name.startsWith('spot_')) {
      const p = new THREE.Vector3();
      o.getWorldPosition(p);
      spots[o.name.slice(5)] = { position: p, yaw: (o.userData.yaw ?? 0) * (Math.PI / 180), extras: o.userData, node: o };
    }
  });
  return spots;
}
