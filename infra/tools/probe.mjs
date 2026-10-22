#!/usr/bin/env node
// Print world positions of key joints at given times (for camera framing).
//   node infra/tools/probe.mjs 1.0 4.5 7.0 11.0
import puppeteer from 'puppeteer-core';

const ts = process.argv.slice(2).map(Number);
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new',
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('[page:exception]', e.message));
await page.goto(`http://127.0.0.1:5173/?render=1&scene=${process.env.SCENE || '001'}`);
await page.waitForFunction('window.__app && window.__app.ready === true', { timeout: 120000 });
const out = await page.evaluate((ts) => {
  const app = window.__app;
  const r = (v) => v.toArray().map((x) => +x.toFixed(3));
  const res = [];
  for (const t of ts) {
    app.renderAt(t);
    const { tim, lioness, guoguo } = app.world.actors;
    const row = { t };
    row.timHead = r(tim.headWorld());
    row.timHips = r(tim.jointWorld('hips'));
    row.timRoot = r(tim.root.position);
    row.lionHead = r(lioness.headWorld());
    row.lionRoot = r(lioness.root.position);
    row.ggHead = r(guoguo.headWorld());
    row.bulb = r(app.world.bulb.root.position);
    res.push(row);
  }
  return res;
}, ts);
for (const row of out) console.log(JSON.stringify(row));
await browser.close();
