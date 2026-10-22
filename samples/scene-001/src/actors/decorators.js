// Registers three.js-side decorators for bank items (viewer + scene share these).
import { registerDecorator } from './registry.js';
import { setFace } from './faces.js';

registerDecorator('characters/tim', ({ root, query }) => {
  setFace(root, 'tim', query?.get('expr') || 'deadfish');
  return null;
});

registerDecorator('characters/lioness', ({ root, query }) => {
  setFace(root, 'lioness', query?.get('expr') || 'stern');
  return null;
});

registerDecorator('characters/guoguo', async (ctx) => {
  const { addShellFur } = await import('./fur.js');
  const fur = addShellFur(ctx.root);
  return { update: () => fur.update?.() };
});

// The smoke-test head uses Tim's decal frame (S = 0.42) — handy for face previews.
registerDecorator('test/', ({ root, query }) => {
  if (query?.get('expr')) setFace(root, 'tim', query.get('expr'));
  return null;
});
