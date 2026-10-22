// Shell fur (GuoGuo): 22 shells, 0.015 m, per docs/scene-spec.md.
// Each shell re-draws the fur mesh pushed out along its (skinned) normal; strands are hashed from the
// REST-pose object position, so they stay glued to the surface while the rig moves and need no UVs.
// Per-vertex length comes from the `_FURLEN` attribute (GLTFLoader name: `_furlen`), default 1.
//
// Plush look (round 2):
// - dense, even pile: strand heights vary only a little, strands are fat at the root and taper softly;
//   the strand edge is anti-aliased into alpha-to-coverage (MSAA) instead of a hard discard, so the pile
//   reads as soft velvet rather than sparkling pixels when the strands are smaller than a pixel;
// - fur-blended colour borders: every strand takes its colour from a random point a few mm away (biased
//   upward: long pile from above falls over the area below), so the hard texture borders dissolve into
//   interleaved tufts of both colours;
// - matte: dense dark undercoat at the root, light-catching tips (visible pile even on the black head),
//   a little per-strand brightness variation, and the base layer's specular turned down.
import * as THREE from 'three';

export const FUR = {
  shells: 22,
  length: 0.015,
  density: 640.0, // strand cells per metre (rest object space)
  droop: 0.0045, // tips sag (object -y) by this much at full length
  jitter: [0.007, 0.011], // per-strand colour pick-up offset (uv units: u = around, v = up)
  lift: 0.014, // linear grey added at the tips (makes dark pile visible, negligible on white)
};

function furMaterial(base, k, n) {
  const m = base.clone();
  m.userData = { ...base.userData, furShell: k };
  m.alphaToCoverage = true;
  const shellT = k / n;
  m.onBeforeCompile = (shader) => {
    shader.uniforms.uShellT = { value: shellT };
    shader.uniforms.uFurLen = { value: FUR.length };
    shader.uniforms.uDensity = { value: FUR.density };
    shader.uniforms.uDroop = { value: FUR.droop };
    shader.uniforms.uJitter = { value: new THREE.Vector2(...FUR.jitter) };
    shader.uniforms.uLift = { value: FUR.lift };
    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        `#include <common>
        uniform float uShellT; uniform float uFurLen; uniform float uDroop;
        attribute float _furlen;
        varying vec3 vRestPos; varying vec3 vRestNrm; varying float vFurLen;`,
      )
      .replace(
        '#include <skinning_vertex>',
        `#include <skinning_vertex>
        vRestPos = position;
        vRestNrm = normal;
        vFurLen = _furlen;
        transformed += normalize(objectNormal) * uFurLen * uShellT * _furlen;
        transformed.y -= uDroop * uShellT * uShellT * _furlen;`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        `#include <common>
        uniform float uShellT; uniform float uDensity; uniform vec2 uJitter; uniform float uLift;
        varying vec3 vRestPos; varying vec3 vRestNrm; varying float vFurLen;
        // strand lattice in a tilted frame (no axis-aligned layers on the round body)
        const mat3 FUR_ROT = mat3(0.8165, -0.4082, -0.4082, 0.0, 0.7071, -0.7071, 0.5774, 0.5774, 0.5774);
        float furHash(vec3 p) { p = fract(p * 0.3183099 + vec3(0.71, 0.113, 0.419)); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }`,
      )
      .replace(
        '#include <map_fragment>',
        `// strand cell (shared by every shell of the same strand)
        vec3 fq = FUR_ROT * vRestPos * uDensity;
        vec3 fcell = floor(fq);
        vec3 ff = fract(fq) - 0.5;
        float fh = furHash(fcell);
        float fh2 = furHash(fcell + 17.31);
        float fh3 = furHash(fcell + 41.7);
        #ifdef USE_MAP
          // colour pick-up from a nearby root (biased upward) -> soft, tufted colour borders
          vec2 fj = vec2(fh2 - 0.5, fh3 - 0.30) * uJitter * clamp(vFurLen * 1.3, 0.25, 1.0);
          vec2 fuv = vMapUv + fj;
          fuv.y = clamp(fuv.y, 0.002, 0.998);
          diffuseColor *= texture2D(map, fuv);
        #endif`,
      )
      .replace(
        '#include <alphatest_fragment>',
        `#include <alphatest_fragment>
        {
          if (vFurLen < 0.02) discard;
          // even pile: heights vary 78..100 %, fat roots, soft taper to the tip
          float len = mix(0.78, 1.0, fh);
          float st = uShellT / len;
          if (st > 1.0) discard;
          float r = mix(0.72, 0.16, st * st);
          // distance to the strand axis (a cylinder along the surface normal through the jittered cell
          // centre): measured in the tangent plane, so the lattice layers never print as rings
          vec3 fn = normalize(FUR_ROT * vRestNrm);
          vec3 fp = ff + (vec3(fh2, fh, fh3) - 0.5) * 0.42;
          fp -= dot(fp, fn) * fn;
          float d = length(fp);
          float w = max(fwidth(d), 0.035);
          float cov = 1.0 - smoothstep(r - w, r + w, d);
          if (cov < 0.02) discard;
          diffuseColor.a = cov;
        }`,
      )
      .replace(
        '#include <color_fragment>',
        `#include <color_fragment>
        {
          float ft = clamp(uShellT, 0.0, 1.0);
          // dense undercoat at the root, light-catching tips, slight per-strand variation
          diffuseColor.rgb *= mix(0.58, 1.03, smoothstep(0.0, 1.0, ft)) * (0.94 + 0.12 * fh2);
          diffuseColor.rgb += vec3(uLift) * ft * ft;
        }`,
      );
  };
  m.customProgramCacheKey = () => `fur-shell-v3-${k}`;
  return m;
}

/** Adds fur shells to every mesh with a fur_* material under root. Returns { shells }. */
export function addShellFur(root, opts = {}) {
  const n = opts.shells ?? FUR.shells;
  const shells = [];
  const targets = [];
  root.traverse((o) => {
    if (o.isMesh && !o.userData.furShell && o.material?.userData?.family === 'fur') targets.push(o);
  });
  for (const mesh of targets) {
    const geo = mesh.geometry;
    if (!geo.getAttribute('_furlen')) {
      const count = geo.getAttribute('position').count;
      geo.setAttribute('_furlen', new THREE.BufferAttribute(new Float32Array(count).fill(1), 1));
    }
    // matte base layer (the pile, not the skin, catches the light)
    const bm = mesh.material;
    if (bm && !bm.userData.furMatte) {
      if ('specularIntensity' in bm) bm.specularIntensity = 0.25;
      if ('sheen' in bm) {
        bm.sheen = 0.35;
        bm.sheenRoughness = 0.75;
      }
      bm.roughness = 1.0;
      bm.userData.furMatte = true;
      bm.needsUpdate = true;
    }
    for (let k = 1; k <= n; k++) {
      const shell = mesh.isSkinnedMesh ? new THREE.SkinnedMesh(geo, furMaterial(mesh.material, k, n)) : new THREE.Mesh(geo, furMaterial(mesh.material, k, n));
      if (mesh.isSkinnedMesh) {
        shell.bind(mesh.skeleton, mesh.bindMatrix);
        shell.bindMode = mesh.bindMode;
      }
      shell.name = `${mesh.name}_fur${k}`;
      shell.userData.furShell = k;
      shell.castShadow = false;
      shell.receiveShadow = true;
      shell.frustumCulled = false;
      shell.renderOrder = k;
      shell.position.copy(mesh.position);
      shell.quaternion.copy(mesh.quaternion);
      shell.scale.copy(mesh.scale);
      mesh.parent.add(shell);
      shells.push(shell);
    }
  }
  return { shells, update() {} };
}
