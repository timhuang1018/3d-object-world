#!/usr/bin/env node
// Headless capture through the running Vite dev server (npm run dev) and system Chrome.
//
//   node infra/tools/shot.mjs "/viewer.html?asset=characters/tim.glb&sheet=views" preview/tim.png
//   node infra/tools/shot.mjs "/?render=1" preview/frame.png --t 4.2            # player frame at t
//   node infra/tools/shot.mjs "/?render=1" preview/sheet.png --t 1,3.6,5,7,10,12.5 --sheet 3
//
// Options: --base http://127.0.0.1:5173   --timeout 180   --w 1920 --h 1080 (player only)
// Prints page console errors so build scripts can be debugged from the terminal.
//
// The PNG is compressed for viewing by default (infra/tools/compress.py: longest side <= 1280,
// 256-colour palette, <= 250 KB); a .jpg output path gives a true-colour JPEG instead.
//   --max 1024 --budget 150   tighter preview      --full   keep the raw full-size capture
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import puppeteer from 'puppeteer-core';

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  if (i < 0) return def;
  const v = args[i + 1];
  args.splice(i, 2);
  return v;
};
const base = opt('base', process.env.SHOT_BASE || 'http://127.0.0.1:5173');
const timeout = parseFloat(opt('timeout', '180')) * 1000;
const tList = opt('t', null);
const sheetCols = parseInt(opt('sheet', '0'), 10);
const scale = parseFloat(opt('scale', '0.5'));
const maxSide = opt('max', '1280');
const budget = opt('budget', '250');
// inspection camera for player frames: --cam x,y,z --target x,y,z [--fov 30]  (overrides the scene camera)
const camOpt = opt('cam', null);
const targetOpt = opt('target', null);
const fovOpt = opt('fov', null);
const fullIdx = args.indexOf('--full');
const full = fullIdx >= 0;
if (full) args.splice(fullIdx, 1);
const [urlPath, outPath] = args;
if (!urlPath || !outPath) {
  console.error('usage: node infra/tools/shot.mjs <path?query> <out.png> [--t 1,2,3] [--sheet cols]');
  process.exit(2);
}

const CHROME = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--enable-webgl', '--no-first-run', '--hide-scrollbars'],
  defaultViewport: { width: 1280, height: 800, deviceScaleFactor: 1 },
  protocolTimeout: timeout,
});

let exitCode = 0;
try {
  const page = await browser.newPage();
  page.on('console', (m) => {
    const type = m.type();
    if (type === 'error' || type === 'warning' || process.env.SHOT_VERBOSE) console.log(`[page:${type}] ${m.text()}`);
    else if (/^(spots|clips|bounds|info)/.test(m.text())) console.log(`[page] ${m.text()}`);
  });
  page.on('pageerror', (e) => console.log(`[page:exception] ${e.message}`));
  const url = base + (urlPath.startsWith('/') ? urlPath : `/${urlPath}`) + (urlPath.includes('?') ? '&' : '?') + 'headless=1';
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
  await page.waitForFunction('window.__app && window.__app.ready === true', { timeout, polling: 200 });
  const err = await page.evaluate('window.__app.error');
  if (err) {
    console.error('[shot] app error:\n' + err);
    exitCode = 1;
  } else {
    fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
    if (camOpt && targetOpt) {
      await page.evaluate(
        (c, tg, f) => {
          const app = window.__app;
          const orig = app.scene.camera;
          app.scene.camera = (t) => ({ ...orig(t), position: c, target: tg, ...(f ? { fov: f } : {}) });
        },
        camOpt.split(',').map(Number),
        targetOpt.split(',').map(Number),
        fovOpt ? Number(fovOpt) : null,
      );
    }
    let dataUrl;
    if (tList) {
      const ts = tList.split(',').map(Number);
      dataUrl = await page.evaluate(
        async (ts, cols, scale) => {
          const app = window.__app;
          if (ts.length === 1 && !cols) return app.captureAt(ts[0]);
          const imgs = [];
          for (const t of ts) imgs.push(await app.captureAt(t));
          const c = cols || Math.min(3, ts.length);
          const first = await new Promise((r) => { const i = new Image(); i.onload = () => r(i); i.src = imgs[0]; });
          const tw = Math.round(first.width * scale), th = Math.round(first.height * scale);
          const sheet = document.createElement('canvas');
          sheet.width = tw * c;
          sheet.height = th * Math.ceil(ts.length / c);
          const g = sheet.getContext('2d');
          for (let k = 0; k < imgs.length; k++) {
            const im = await new Promise((r) => { const i = new Image(); i.onload = () => r(i); i.src = imgs[k]; });
            g.drawImage(im, (k % c) * tw, Math.floor(k / c) * th, tw, th);
          }
          return sheet.toDataURL('image/png');
        },
        ts,
        sheetCols,
        scale,
      );
    } else {
      dataUrl = await page.evaluate('window.__app.capture()');
    }
    const b64 = dataUrl.replace(/^data:image\/png;base64,/, '');
    fs.writeFileSync(outPath, Buffer.from(b64, 'base64'));
    if (full) {
      console.log(`[shot] wrote ${outPath} (full size, ${(fs.statSync(outPath).size / 1024) | 0} KB — do not view raw)`);
    } else {
      const py = fs.existsSync('./.venv/bin/python') ? './.venv/bin/python' : 'python3';
      const compressPy = path.join(path.dirname(new URL(import.meta.url).pathname), 'compress.py');
      execFileSync(py, [compressPy, outPath, '--max', maxSide, '--budget', budget], { stdio: 'inherit' });
      console.log(`[shot] wrote ${outPath}`);
    }
  }
} catch (e) {
  console.error('[shot] failed:', e.message);
  exitCode = 1;
} finally {
  await browser.close();
}
process.exit(exitCode);
