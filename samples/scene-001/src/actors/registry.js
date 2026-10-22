// Per-asset decorators used by the viewer (and the scene) to attach three.js-side behaviour:
// face decals, shell fur, screen textures ...  Each decorator gets { root, rig, look, query }
// and may return { update(t, actionName) }.
const registry = new Map();

export function registerDecorator(assetPrefix, fn) {
  registry.set(assetPrefix, fn);
}

export async function decorateAsset(assetRel, ctx) {
  // lazy-load actor modules so the viewer stays light
  await import('./decorators.js').catch((e) => console.warn('decorators not loaded', e));
  for (const [prefix, fn] of registry) {
    if (assetRel.startsWith(prefix)) return fn(ctx);
  }
  return null;
}
