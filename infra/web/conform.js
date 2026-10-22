// Material conform: enforce Look A per material family (by material-name prefix, see
// infra/blender/lib/mat.py).  GLB materials keep their colour / maps; the family fixes the rest.
import * as THREE from 'three';

const VINYL = { roughness: 0.5, clearcoat: 0.22, clearcoatRoughness: 0.5, sheen: 0.15, sheenRoughness: 0.8 };

function physicalFrom(src, extra) {
  const m = new THREE.MeshPhysicalMaterial({
    name: src.name,
    color: src.color?.clone() ?? new THREE.Color(1, 1, 1),
    map: src.map ?? null,
    normalMap: src.normalMap ?? null,
    normalScale: src.normalScale?.clone() ?? new THREE.Vector2(1, 1),
    emissive: src.emissive?.clone() ?? new THREE.Color(0, 0, 0),
    emissiveMap: src.emissiveMap ?? null,
    emissiveIntensity: src.emissiveIntensity ?? 1,
    side: src.side,
    vertexColors: src.vertexColors,
    transparent: src.transparent,
    opacity: src.opacity,
    alphaTest: src.alphaTest,
  });
  Object.assign(m, extra);
  return m;
}

/** Returns the conformed material for a GLB material (cached per source material). */
export function conformMaterial(src, maxAniso = 8) {
  if (src.userData.__conformed) return src;
  const name = src.name || '';
  const fam = name.split('_')[0];
  let m = src;
  switch (fam) {
    case 'vinyl':
      m = physicalFrom(src, { ...VINYL, sheenColor: new THREE.Color(1, 1, 1) });
      break;
    case 'hair':
      m = physicalFrom(src, {
        roughness: 0.42, clearcoat: 0.18, clearcoatRoughness: 0.35,
        sheen: 1.0, sheenRoughness: 0.32, sheenColor: new THREE.Color('#8a7464'),
      });
      break;
    case 'fur':
      m = physicalFrom(src, { roughness: 0.92, sheen: 0.6, sheenRoughness: 0.5, sheenColor: new THREE.Color(1, 1, 1) });
      break;
    case 'prop':
    case 'wood':
      m = src;
      m.roughness = 0.62;
      m.metalness = 0;
      break;
    case 'fabric':
      m = physicalFrom(src, { roughness: 0.86, sheen: 0.35, sheenRoughness: 0.6, sheenColor: new THREE.Color(1, 1, 1) });
      break;
    case 'ceramic':
      m = physicalFrom(src, { roughness: 0.28, clearcoat: 0.35, clearcoatRoughness: 0.12 });
      break;
    case 'metal':
      m = src;
      m.metalness = 1;
      m.roughness = Math.min(m.roughness ?? 0.32, 0.45);
      break;
    case 'glass':
      m = src;
      m.transparent = true;
      m.depthWrite = false;
      m.roughness = 0.05;
      break;
    case 'emit':
      m = src;
      m.toneMapped = true;
      break;
    case 'decal':
      m = new THREE.MeshStandardMaterial({
        name, roughness: 0.45, transparent: true, depthWrite: false,
        polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
        color: 0xffffff, opacity: 1,
      });
      m.visible = false; // until an expression texture is assigned
      break;
    case 'ink':
      m = physicalFrom(src, { roughness: 0.25, clearcoat: 0.6, clearcoatRoughness: 0.08 });
      break;
    default:
      break;
  }
  for (const k of ['map', 'emissiveMap', 'normalMap', 'roughnessMap']) {
    if (m[k]) m[k].anisotropy = maxAniso;
  }
  m.userData.__conformed = true;
  m.userData.family = fam;
  return m;
}

/** Conform every mesh under root: materials + shadow flags. */
export function conformScene(root, renderer) {
  const maxAniso = renderer ? renderer.capabilities.getMaxAnisotropy() : 8;
  const cache = new Map();
  root.traverse((o) => {
    if (!o.isMesh) return;
    const conv = (mat) => {
      if (!cache.has(mat)) cache.set(mat, conformMaterial(mat, maxAniso));
      return cache.get(mat);
    };
    o.material = Array.isArray(o.material) ? o.material.map(conv) : conv(o.material);
    const fam = (Array.isArray(o.material) ? o.material[0] : o.material).userData.family;
    const noShadow = fam === 'decal' || fam === 'glass' || fam === 'emit' || o.userData.noShadow;
    o.castShadow = !noShadow;
    o.receiveShadow = fam !== 'glass';
    if (o.isSkinnedMesh) o.frustumCulled = false;
  });
  return root;
}
