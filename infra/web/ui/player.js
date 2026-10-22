// Player controls: transport, scrubber with beat markers, beat jump, shot/free camera, quality, loop.
// The wall clock only advances t while playing; every frame is still renderAt(t) (pure).
export function createPlayerUI({ scene, cams, look, canvas, renderAt, getT, startT = 0 }) {
  const ui = document.getElementById('ui');
  const D = scene.duration;
  ui.innerHTML = `
    <div class="narration" id="narr"></div>
    <div class="bar">
      <button id="play" title="Play / pause (Space)">▶</button>
      <button id="restart" title="Restart (Home)">⏮</button>
      <div class="time"><span id="tc">0.00</span><small> / ${D.toFixed(2)} s · f<span id="fr">0</span></small></div>
      <div class="track" id="track">
        ${scene.beats.map((b) => `<div class="beat" style="left:${(b.start / D) * 100}%;width:${((b.end - b.start) / D) * 100}%" data-start="${b.start}"><span>${b.id} · ${b.name}</span></div>`).join('')}
        <div class="head" id="head"></div>
      </div>
      <div class="group">
        <select id="scene" title="Scene">
          <option value="001">001 · 13 s</option>
          <option value="beat2">beat 2 · locked clip 8 s</option>
        </select>
        <button id="cam" title="Shot / free camera (C). Free: drag = orbit/tilt, right-drag = pan, wheel = zoom, alt+wheel = FOV">🎥 Shot</button>
        <button id="reset" title="Reset free camera to the shot (R)">⟲</button>
        <button id="loop" class="on" title="Loop (L)">⟳</button>
        <button id="hq" title="Full / half resolution">1080p</button>
      </div>
    </div>
    <div class="help">Space play · ←/→ frame (⇧ 1 s) · 1–4 beat · C camera · R reset · L loop · H hide UI</div>`;
  const $ = (id) => document.getElementById(id);
  $('scene').value = scene.id;
  $('scene').onchange = (e) => {
    const u = new URL(location.href);
    u.searchParams.set('scene', e.target.value);
    u.searchParams.delete('t');
    location.href = u.toString();
  };
  let playing = false, loop = true, last = 0;

  const fit = () => {
    const stage = document.getElementById('stage');
    const sw = stage.clientWidth, sh = stage.clientHeight;
    const ar = look.width / look.height;
    const w = Math.min(sw, sh * ar), h = w / ar;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
  };
  window.addEventListener('resize', fit);
  fit();

  const sync = () => {
    const t = getT();
    $('tc').textContent = t.toFixed(2);
    $('fr').textContent = String(Math.round(t * scene.fps));
    $('head').style.left = `${(t / D) * 100}%`;
    const b = scene.beatAt(t);
    $('narr').textContent = b.narration;
    document.querySelectorAll('.beat').forEach((el) => el.classList.toggle('active', +el.dataset.start === b.start));
    $('play').textContent = playing ? '⏸' : '▶';
  };
  const go = (t) => {
    renderAt(t);
    sync();
  };
  const toggle = () => {
    if (!playing && getT() >= D - 1e-3) go(0);
    playing = !playing;
    last = performance.now();
    sync();
  };

  $('play').onclick = toggle;
  $('restart').onclick = () => go(0);
  $('loop').onclick = () => { loop = !loop; $('loop').classList.toggle('on', loop); };
  const setCam = (mode) => {
    cams.setMode(mode);
    $('cam').textContent = mode === 'free' ? '🕹 Free' : '🎥 Shot';
    $('cam').classList.toggle('on', mode === 'free');
    go(getT());
  };
  if (cams.mode === 'free') setCam('free');
  $('cam').onclick = () => setCam(cams.mode === 'free' ? 'shot' : 'free');
  $('reset').onclick = () => { cams.setMode('shot'); setCam('free'); };
  $('hq').onclick = () => {
    const full = look.width === 1920;
    look.setSize(full ? 960 : 1920, full ? 540 : 1080);
    cams.resize(look.width, look.height);
    $('hq').textContent = full ? '540p' : '1080p';
    fit();
    go(getT());
  };

  // scrubbing
  const track = $('track');
  let dragging = false;
  const scrub = (e) => {
    const r = track.getBoundingClientRect();
    go(Math.min(D, Math.max(0, ((e.clientX - r.left) / r.width) * D)));
  };
  track.addEventListener('pointerdown', (e) => { dragging = true; playing = false; track.setPointerCapture(e.pointerId); scrub(e); });
  track.addEventListener('pointermove', (e) => dragging && scrub(e));
  track.addEventListener('pointerup', () => (dragging = false));

  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    const f = 1 / scene.fps;
    switch (e.code) {
      case 'Space': e.preventDefault(); toggle(); break;
      case 'ArrowRight': playing = false; go(getT() + (e.shiftKey ? 1 : f)); break;
      case 'ArrowLeft': playing = false; go(getT() - (e.shiftKey ? 1 : f)); break;
      case 'Home': go(0); break;
      case 'Digit1': case 'Digit2': case 'Digit3': case 'Digit4': go(scene.beats[+e.code.slice(5) - 1].start + 1e-4); break;
      case 'KeyC': setCam(cams.mode === 'free' ? 'shot' : 'free'); break;
      case 'KeyR': cams.setMode('shot'); setCam('free'); break;
      case 'KeyL': $('loop').click(); break;
      case 'KeyH': document.body.classList.toggle('noui'); setTimeout(fit, 0); break;
      default: break;
    }
  });

  const tick = (now) => {
    if (playing) {
      let t = getT() + Math.min(0.1, (now - last) / 1000);
      if (t >= D) {
        if (loop) t = 0;
        else { t = D; playing = false; }
      }
      go(t);
    } else if (cams.mode === 'free') {
      go(getT()); // keep orbit damping alive while paused
    }
    last = now;
    requestAnimationFrame(tick);
  };
  go(startT);
  requestAnimationFrame((n) => { last = n; tick(n); });
}
