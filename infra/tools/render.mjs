#!/usr/bin/env node
// Deterministic export: renders every frame t = i / fps of the scene in headless Chrome
// (/?render=1, 1920x1080) and encodes an MP4 with ffmpeg (from imageio-ffmpeg in .venv).
//
//   node infra/tools/render.mjs                         -> out/scene-<id>.mp4 (H.264, CRF 23: small, for sharing)
//   node infra/tools/render.mjs --master                -> near-lossless master (CRF 16, ~3x bigger)
//   node infra/tools/render.mjs --crf 26                -> any quality/size trade-off (lower = better, bigger)
//   node infra/tools/render.mjs --webp                  -> also an animated WebP preview (640 px, 12 fps) for READMEs
//   node infra/tools/render.mjs --frames                -> also keep PNGs in out/frames/
//   node infra/tools/render.mjs --from 3.5 --to 6.2     -> a range (seconds)
//   node infra/tools/render.mjs --stills                -> out/stills/*.png at the scene's key moments (scene.stills)
//   node infra/tools/render.mjs --scene beat2           -> another scene of the running project
//   node infra/tools/render.mjs --out path/to/file.mp4
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import puppeteer from 'puppeteer-core';

const args = process.argv.slice(2);
const flag = (n) => args.includes(`--${n}`);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const base = opt('base', 'http://127.0.0.1:5173');
const fps = parseFloat(opt('fps', '30'));
const sceneId = opt('scene', '001');
const out = opt('out', `out/scene-${sceneId}.mp4`);
const keepFrames = flag('frames');
const crf = flag('master') ? '16' : opt('crf', '23');
const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

function ffmpegPath() {
  try {
    return execFileSync('./.venv/bin/python', ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())']).toString().trim();
  } catch {
    return 'ffmpeg';
  }
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--hide-scrollbars'],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
  protocolTimeout: 600000,
});
const page = await browser.newPage();
page.on('console', (m) => { if (m.type() === 'error') console.log('[page:error]', m.text()); });
page.on('pageerror', (e) => console.log('[page:exception]', e.message));
await page.goto(`${base}/?render=1&scene=${sceneId}`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction('window.__app && window.__app.ready === true', { timeout: 300000, polling: 250 });
const err = await page.evaluate('window.__app.error');
if (err) {
  console.error(err);
  await browser.close();
  process.exit(1);
}
const duration = await page.evaluate('window.__app.scene.duration');

if (flag('stills')) {
  // key moments come from the scene config (`stills: { name: t }`); fallback: the middle of each beat
  const stills = await page.evaluate(() => {
    const s = window.__app.scene;
    if (s.stills) return s.stills;
    return Object.fromEntries((s.beats || []).map((b) => [`b${b.id}`, (b.start + b.end) / 2]));
  });
  fs.mkdirSync('out/stills', { recursive: true });
  for (const [name, t] of Object.entries(stills)) {
    const url = await page.evaluate((tt) => window.__app.captureAt(tt), t);
    fs.writeFileSync(`out/stills/${name}.png`, Buffer.from(url.split(',')[1], 'base64'));
    console.log(`still ${name} @ ${t}s`);
  }
  await browser.close();
  process.exit(0);
}

const from = parseFloat(opt('from', '0'));
const to = Math.min(duration, parseFloat(opt('to', String(duration))));
const first = Math.round(from * fps);
const last = Math.round(to * fps) - 1;
fs.mkdirSync(path.dirname(out), { recursive: true });
if (keepFrames) fs.mkdirSync('out/frames', { recursive: true });

const ff = spawn(ffmpegPath(), ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
  '-c:v', 'libx264', '-preset', 'slow', '-tune', 'animation', '-crf', crf, '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });

const t0 = Date.now();
for (let i = first; i <= last; i++) {
  const t = i / fps;
  const url = await page.evaluate((tt) => window.__app.captureAt(tt), t);
  const buf = Buffer.from(url.split(',')[1], 'base64');
  if (keepFrames) fs.writeFileSync(`out/frames/f${String(i).padStart(4, '0')}.png`, buf);
  if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
  if (i % 30 === 0) process.stdout.write(`\rframe ${i}/${last}  (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
}
ff.stdin.end();
await new Promise((r) => ff.on('close', r));
await browser.close();
console.log(`\nwrote ${out}  (${last - first + 1} frames @ ${fps} fps, CRF ${crf}, ${(fs.statSync(out).size / 1e6).toFixed(1)} MB)`);
if (flag('webp')) {
  const webp = out.replace(/\.mp4$/, '') + '.webp';
  execFileSync(ffmpegPath(), ['-y', '-loglevel', 'error', '-i', out, '-vf', 'fps=12,scale=640:-1:flags=lanczos',
    '-c:v', 'libwebp', '-q:v', '60', '-loop', '0', webp]);
  console.log(`wrote ${webp}  (${(fs.statSync(webp).size / 1e6).toFixed(1)} MB)`);
}
