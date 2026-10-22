#!/usr/bin/env node
// Evaluate a JS expression in the player page (after load) and print the JSON result.
//   node infra/tools/evalpage.mjs "(() => { const a = window.__app; a.renderAt(7); return a.world.actors.tim.headWorld().toArray(); })()"
import puppeteer from 'puppeteer-core';

const code = process.argv[2];
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new',
  args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('[page:exception]', e.message));
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log(`[page:${m.type()}]`, m.text()); });
await page.goto(`http://127.0.0.1:5173/?render=1&scene=${process.env.SCENE || '001'}`);
await page.waitForFunction('window.__app && window.__app.ready === true', { timeout: 120000 });
const out = await page.evaluate(`(async () => { return (${code}); })()`);
console.log(JSON.stringify(out, null, 0));
await browser.close();
