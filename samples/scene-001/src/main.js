// Player entry: loads the bank, builds Scene 001, renders frames as a pure function of t.
//   /                 interactive player (Space play/pause, ←/→ frame, 1-4 beats, C camera, R reset, L loop)
//   /?render=1        headless export mode: window.__app.captureAt(t) -> PNG data URL (1920x1080)
//   /?t=4.2           start at a time;   &cam=free  start in free-camera mode;  &q=half  half resolution
import '@infra/ui/player.css';
import { Look, LOOK_A } from '@infra/look.js';
import { CameraRig } from '@infra/camera.js';
import { buildWorld } from './world.js';
import { createScene001 } from './scenes/scene001.js';
import { createBeat2 } from './scenes/beat2.js';
import { createPlayerUI } from '@infra/ui/player.js';

const SCENES = { '001': createScene001, beat2: createBeat2 };

const q = new URLSearchParams(location.search);
const renderMode = q.get('render') === '1';
const canvas = document.getElementById('gl');
const loading = document.getElementById('loading');
const app = { ready: false, error: null };
window.__app = app;

async function main() {
  const half = q.get('q') === 'half';
  const w = renderMode ? LOOK_A.width : half ? LOOK_A.width / 2 : LOOK_A.width;
  const h = renderMode ? LOOK_A.height : half ? LOOK_A.height / 2 : LOOK_A.height;
  const look = new Look(canvas, { width: w, height: h, preserve: true });
  const world = await buildWorld(look, (p) => (loading.textContent = `loading bank… ${Math.round(p * 100)}%`));
  if (world.missing.length) console.warn('[bank] missing (placeholders used):', world.missing.join(', '));
  const scene = (SCENES[q.get('scene')] || createScene001)(world);
  const cams = new CameraRig(look, canvas);

  let t = Math.min(scene.duration, Math.max(0, parseFloat(q.get('t') || '0')));
  const renderAt = (time) => {
    t = Math.min(scene.duration, Math.max(0, time));
    cams.setShot(scene.camera(t));
    cams.update();
    scene.update(t, cams.active);
    look.render(cams.active);
  };
  // warm-up: compile every shader for both sets before the first visible frame
  for (const tt of [0.5, 4.4, 7.0, 11.5]) renderAt(Math.min(tt, scene.duration - 0.01));
  renderAt(t);
  loading.style.display = 'none';

  app.renderAt = renderAt;
  app.captureAt = async (time) => {
    renderAt(time);
    return canvas.toDataURL('image/png');
  };
  app.scene = scene;
  app.world = world;
  app.look = look;

  if (!renderMode) {
    if (q.get('cam') === 'free') cams.setMode('free');
    createPlayerUI({ scene, cams, look, canvas, renderAt, getT: () => t, startT: t });
  } else {
    document.body.classList.add('render');
  }
  app.ready = true;
}

main().catch((e) => {
  console.error(e);
  app.error = String(e?.stack || e);
  loading.textContent = `error: ${e.message}`;
  app.ready = true;
});
