// Look A — "3D toy, Animal Crossing smooth".  Renderer, environment, lights and the post stack.
// All values come from docs/scene-spec.md § "Look A (render settings)".
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { SimplexNoise } from 'three/addons/math/SimplexNoise.js';
import { rng } from './math.js';

export const LOOK_A = {
  width: 1920,
  height: 1080,
  fps: 30,
  exposure: 0.95,
  background: 0xe8e0d4,
  fog: [13, 30],
  env: { sigma: 0.04, intensity: 0.3 },
  shadow: { mapSize: 4096, extent: 5.5, radius: 5 },
  hemi: { sky: 0xfff4e4, ground: 0xcdb79a, intensity: 0.6 },
  key: { color: 0xfff0dc, intensity: 2.3, position: [3.2, 6.5, 5.5] },
  rim: { color: 0xe9eeff, intensity: 0.55, position: [-3, 4, -5] },
  post: {
    msaa: 4,
    gtao: { radius: 0.32, samples: 16, blend: 0.8 },
    bloom: { strength: 0.42, radius: 0.45, threshold: 1.6 },
    vignette: 0.16,
  },
  camera: { near: 0.05, far: 60, fov: 30 },
};

/** GTAO with a seeded Poisson-denoise noise texture (the stock pass uses Math.random), and an AO
 *  g-buffer that skips sprites / transparent FX / fur shells (they would print solid quads). */
class SeededGTAOPass extends GTAOPass {
  _overrideVisibility() {
    const cache = this._visibilityCache;
    this.scene.traverse((o) => {
      cache.set(o, o.visible);
      if (o.isPoints || o.isLine || o.isSprite) o.visible = false;
      else if (o.isMesh) {
        const m = o.material;
        const transparent = Array.isArray(m) ? m.every((x) => x.transparent) : m?.transparent;
        if (transparent || o.userData.noAO || o.userData.furShell) o.visible = false;
      }
    });
  }

  _generateNoise(size = 64) {
    const simplex = new SimplexNoise(rng(0x5eed01));
    const data = new Uint8Array(size * size * 4);
    for (let i = 0; i < size; i++) {
      for (let j = 0; j < size; j++) {
        const k = (i * size + j) * 4;
        data[k] = (simplex.noise(i, j) * 0.5 + 0.5) * 255;
        data[k + 1] = (simplex.noise(i + size, j) * 0.5 + 0.5) * 255;
        data[k + 2] = (simplex.noise(i, j + size) * 0.5 + 0.5) * 255;
        data[k + 3] = (simplex.noise(i + size, j + size) * 0.5 + 0.5) * 255;
      }
    }
    const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat, THREE.UnsignedByteType);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.needsUpdate = true;
    return tex;
  }
}

const VignetteShader = {
  uniforms: { tDiffuse: { value: null }, amount: { value: 0.16 }, aspect: { value: 16 / 9 } },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse; uniform float amount; uniform float aspect;
    varying vec2 vUv;
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      vec2 p = (vUv - 0.5) * vec2(aspect, 1.0) / vec2(aspect * 0.5 + 0.5, 1.0);
      float d = length(p);
      float v = smoothstep(0.35, 1.05, d);
      c.rgb *= 1.0 - amount * v;
      gl_FragColor = c;
    }`,
};

export class Look {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {{width?:number,height?:number,post?:boolean,preserve?:boolean,pixelRatio?:number}} opts
   */
  constructor(canvas, opts = {}) {
    const L = LOOK_A;
    this.width = opts.width ?? L.width;
    this.height = opts.height ?? L.height;
    this.postEnabled = opts.post ?? true;

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      preserveDrawingBuffer: opts.preserve ?? true,
      powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(opts.pixelRatio ?? 1);
    renderer.setSize(this.width, this.height, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.toneMappingExposure = L.exposure;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer = renderer;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(L.background);
    scene.fog = new THREE.Fog(L.background, L.fog[0], L.fog[1]);
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    scene.environment = pmrem.fromScene(room, L.env.sigma).texture;
    scene.environmentIntensity = L.env.intensity;
    room.dispose?.();
    pmrem.dispose();
    this.scene = scene;

    this.camera = new THREE.PerspectiveCamera(L.camera.fov, this.width / this.height, L.camera.near, L.camera.far);

    // Lights
    const hemi = new THREE.HemisphereLight(L.hemi.sky, L.hemi.ground, L.hemi.intensity);
    const key = new THREE.DirectionalLight(L.key.color, L.key.intensity);
    key.position.set(...L.key.position);
    key.castShadow = true;
    key.shadow.mapSize.set(L.shadow.mapSize, L.shadow.mapSize);
    const e = L.shadow.extent;
    Object.assign(key.shadow.camera, { left: -e, right: e, top: e, bottom: -e, near: 0.5, far: 30 });
    key.shadow.radius = L.shadow.radius;
    key.shadow.bias = -0.0003;
    key.shadow.normalBias = 0.015;
    const rim = new THREE.DirectionalLight(L.rim.color, L.rim.intensity);
    rim.position.set(...L.rim.position);
    // Mood "practical": a soft spot on the hero, off by default (setMood drives it per beat).
    const spot = new THREE.SpotLight(0xffd7a0, 0, 7, 0.42, 0.85, 1.6);
    spot.castShadow = false;
    this.lights = { hemi, key, rim, spot };
    scene.add(hemi, key, key.target, rim, spot, spot.target);

    // Post stack: MSAA x4 -> GTAO (seeded denoise) -> bloom (only the bulb) -> vignette -> output
    const rt = new THREE.WebGLRenderTarget(this.width, this.height, {
      type: THREE.HalfFloatType,
      samples: L.post.msaa,
    });
    const composer = new EffectComposer(renderer, rt);
    composer.setPixelRatio(1);
    composer.setSize(this.width, this.height);
    this.renderPass = new RenderPass(scene, this.camera);
    composer.addPass(this.renderPass);
    const gtao = new SeededGTAOPass(scene, this.camera, this.width, this.height);
    gtao.output = GTAOPass.OUTPUT.Default;
    gtao.blendIntensity = L.post.gtao.blend;
    gtao.updateGtaoMaterial({ radius: L.post.gtao.radius, samples: L.post.gtao.samples, distanceExponent: 1, thickness: 1, scale: 1 });
    gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 4, radiusExponent: 1, rings: 2, samples: 16 });
    composer.addPass(gtao);
    const bloom = new UnrealBloomPass(new THREE.Vector2(this.width, this.height), L.post.bloom.strength, L.post.bloom.radius, L.post.bloom.threshold);
    composer.addPass(bloom);
    const vignette = new ShaderPass(VignetteShader);
    vignette.uniforms.amount.value = L.post.vignette;
    vignette.uniforms.aspect.value = this.width / this.height;
    composer.addPass(vignette);
    composer.addPass(new OutputPass());
    this.composer = composer;
    this.passes = { gtao, bloom, vignette };

    // Optional overlay (HUD) scene rendered after the post stack, untouched by tone mapping.
    this.hud = new THREE.Scene();
    this.hudCamera = new THREE.OrthographicCamera(0, 1, 1, 0, -10, 10); // x: 0..1 left->right, y: 0..1 bottom->top
  }

  setSize(w, h) {
    this.width = w;
    this.height = h;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.passes.vignette.uniforms.aspect.value = w / h;
  }

  /**
   * Per-beat lighting mood on top of the Look A base (pure: set every frame from the scene's t).
   * Any field left out falls back to the LOOK_A value, so setMood({}) restores the locked look.
   * m: { exposure, background, hemi:{sky,ground,intensity}, key:{color,intensity}, rim:{color,intensity,position?},
   *      env, vignette, spot:{color,intensity,position:[x,y,z],target:[x,y,z],angle,penumbra} }
   */
  setMood(m = {}) {
    const L = LOOK_A;
    const { hemi, key, rim, spot } = this.lights;
    this.renderer.toneMappingExposure = m.exposure ?? L.exposure;
    const bg = m.background ?? L.background;
    this.scene.background.set(bg);
    this.scene.fog.color.set(bg);
    this.scene.environmentIntensity = m.env ?? L.env.intensity;
    hemi.color.set(m.hemi?.sky ?? L.hemi.sky);
    hemi.groundColor.set(m.hemi?.ground ?? L.hemi.ground);
    hemi.intensity = m.hemi?.intensity ?? L.hemi.intensity;
    key.color.set(m.key?.color ?? L.key.color);
    key.intensity = m.key?.intensity ?? L.key.intensity;
    rim.color.set(m.rim?.color ?? L.rim.color);
    rim.intensity = m.rim?.intensity ?? L.rim.intensity;
    // optional rim direction (e.g. a low back light so the rim catches silhouettes, not table tops)
    rim.position.set(...(m.rim?.position ?? L.rim.position));
    this.passes.vignette.uniforms.amount.value = m.vignette ?? L.post.vignette;
    const s = m.spot;
    spot.intensity = s?.intensity ?? 0;
    // (the spot stays in the scene at intensity 0 so the light count — and the shaders — never change)
    if (s && spot.intensity > 0) {
      spot.color.set(s.color ?? 0xffd7a0);
      spot.position.set(...s.position);
      spot.target.position.set(...s.target);
      spot.angle = s.angle ?? 0.42;
      spot.penumbra = s.penumbra ?? 0.85;
      spot.target.updateMatrixWorld();
    }
  }

  /** Point the key-light shadow frustum at a set (centre in world coords). */
  setShadowCenter(x, y, z) {
    const k = this.lights.key;
    const [px, py, pz] = LOOK_A.key.position;
    k.target.position.set(x, y, z);
    k.position.set(x + px, y + py, z + pz);
    k.target.updateMatrixWorld();
  }

  render(camera = this.camera) {
    this.renderPass.camera = camera;
    this.passes.gtao.camera = camera;
    if (this.postEnabled) this.composer.render();
    else this.renderer.render(this.scene, camera);
    if (this.hud.children.length) {
      const r = this.renderer;
      const ac = r.autoClear;
      r.autoClear = false;
      r.setRenderTarget(null);
      r.clearDepth();
      r.render(this.hud, this.hudCamera);
      r.autoClear = ac;
    }
  }
}
