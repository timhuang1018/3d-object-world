// Canvas textures for FX and graphics. All wordless and deterministic.
import * as THREE from 'three';
import { rng } from '@infra/math.js';

function canvas(w, h = w) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

function tex(c, srgb = true) {
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

const cache = new Map();
const once = (key, fn) => {
  if (!cache.has(key)) cache.set(key, fn());
  return cache.get(key);
};

/** Soft radial glow, white centre -> transparent (tint with material colour). */
export const glowTexture = () =>
  once('glow', () => {
    const c = canvas(256);
    const g = c.getContext('2d');
    const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grd.addColorStop(0, 'rgba(255,255,255,1)');
    grd.addColorStop(0.18, 'rgba(255,255,255,0.55)');
    grd.addColorStop(0.45, 'rgba(255,255,255,0.16)');
    grd.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, 256, 256);
    return tex(c);
  });

/** Wide soft halo for the focus glow. */
export const haloTexture = () =>
  once('halo', () => {
    const c = canvas(256);
    const g = c.getContext('2d');
    const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grd.addColorStop(0, 'rgba(255,255,255,0.9)');
    grd.addColorStop(0.35, 'rgba(255,255,255,0.45)');
    grd.addColorStop(0.7, 'rgba(255,255,255,0.1)');
    grd.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, 256, 256);
    return tex(c);
  });

/** Smoke / dust puff: soft lumpy blob (seeded). */
export const puffTexture = (seed = 3) =>
  once(`puff${seed}`, () => {
    const c = canvas(128);
    const g = c.getContext('2d');
    const r = rng(seed);
    for (let i = 0; i < 9; i++) {
      const a = (i / 9) * Math.PI * 2 + r.range(-0.3, 0.3);
      const d = i === 0 ? 0 : r.range(14, 26);
      const x = 64 + Math.cos(a) * d, y = 64 + Math.sin(a) * d;
      const rad = i === 0 ? 40 : r.range(18, 28);
      const grd = g.createRadialGradient(x, y, 0, x, y, rad);
      grd.addColorStop(0, 'rgba(255,255,255,0.75)');
      grd.addColorStop(0.6, 'rgba(255,255,255,0.35)');
      grd.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = grd;
      g.beginPath();
      g.arc(x, y, rad, 0, Math.PI * 2);
      g.fill();
    }
    return tex(c);
  });

/** A curly smoke wisp (snuffed-out). */
export const wispTexture = () =>
  once('wisp', () => {
    const c = canvas(128, 256);
    const g = c.getContext('2d');
    g.lineCap = 'round';
    for (let pass = 0; pass < 3; pass++) {
      g.beginPath();
      g.moveTo(64, 250);
      g.bezierCurveTo(30, 200, 98, 160, 60, 115);
      g.bezierCurveTo(30, 80, 90, 50, 70, 10);
      g.strokeStyle = `rgba(255,255,255,${[0.18, 0.35, 0.85][pass]})`;
      g.lineWidth = [26, 16, 7][pass];
      g.stroke();
    }
    return tex(c);
  });

/** Rounded ray dash for the bulb rays. */
export const rayTexture = () =>
  once('ray', () => {
    const c = canvas(64, 256);
    const g = c.getContext('2d');
    g.fillStyle = '#ffffff';
    const r = 26;
    g.beginPath();
    g.moveTo(32 - r, 32);
    g.arc(32, 32, r, Math.PI, 0);
    g.lineTo(32 + r, 224);
    g.arc(32, 224, r, 0, Math.PI);
    g.closePath();
    g.fill();
    return tex(c);
  });

/** Speed line streak: tapered, soft. */
export const streakTexture = () =>
  once('streak', () => {
    const c = canvas(512, 32);
    const g = c.getContext('2d');
    const grd = g.createLinearGradient(0, 0, 512, 0);
    grd.addColorStop(0, 'rgba(255,255,255,0)');
    grd.addColorStop(0.55, 'rgba(255,255,255,0.75)');
    grd.addColorStop(1, 'rgba(255,255,255,1)');
    g.fillStyle = grd;
    g.beginPath();
    g.moveTo(0, 16);
    g.quadraticCurveTo(300, 9, 500, 6);
    g.arc(500, 16, 10, -Math.PI / 2, Math.PI / 2);
    g.quadraticCurveTo(300, 23, 0, 16);
    g.fill();
    return tex(c);
  });

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function dirtyPlate(g, cx, cy, rx, ry, seed) {
  const r = rng(seed);
  // plate
  g.beginPath();
  g.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  g.fillStyle = '#f3eee4';
  g.fill();
  g.lineWidth = 5;
  g.strokeStyle = '#8a7a6a';
  g.stroke();
  g.beginPath();
  g.ellipse(cx, cy, rx * 0.66, ry * 0.62, 0, 0, Math.PI * 2);
  g.lineWidth = 3;
  g.strokeStyle = 'rgba(138,122,106,0.45)';
  g.stroke();
  // smudges + crumbs
  for (let i = 0; i < 3; i++) {
    g.beginPath();
    g.ellipse(cx + r.range(-0.4, 0.4) * rx, cy + r.range(-0.35, 0.35) * ry, r.range(0.12, 0.24) * rx, r.range(0.1, 0.18) * ry, r.range(0, 3), 0, Math.PI * 2);
    g.fillStyle = `rgba(150,104,70,${r.range(0.45, 0.7)})`;
    g.fill();
  }
  for (let i = 0; i < 6; i++) {
    g.beginPath();
    g.arc(cx + r.range(-0.6, 0.6) * rx, cy + r.range(-0.5, 0.5) * ry, r.range(2.5, 5), 0, Math.PI * 2);
    g.fillStyle = '#8b5e3c';
    g.fill();
  }
}

/** Speech bubble with a dirty-plates pictogram (the "!" is a separate sprite so it can pulse). */
export const bubbleTexture = () =>
  once('bubble', () => {
    const c = canvas(512, 420);
    const g = c.getContext('2d');
    // drop shadow
    g.save();
    g.translate(6, 8);
    g.globalAlpha = 0.18;
    roundRect(g, 26, 22, 440, 290, 120);
    g.fillStyle = '#6b5a4a';
    g.fill();
    g.restore();
    // body + tail (tail points down-left toward the speaker)
    g.beginPath();
    roundRect(g, 26, 22, 440, 290, 120);
    g.moveTo(130, 300);
    g.quadraticCurveTo(95, 370, 52, 398);
    g.quadraticCurveTo(140, 380, 196, 306);
    g.fillStyle = '#fdfbf6';
    g.fill();
    g.lineWidth = 8;
    g.strokeStyle = '#6b5a4a';
    g.stroke();
    g.beginPath();
    roundRect(g, 26, 22, 440, 290, 120);
    g.fillStyle = '#fdfbf6';
    g.fill();
    g.lineWidth = 8;
    g.stroke();
    // a stack of dirty plates
    for (let i = 0; i < 3; i++) dirtyPlate(g, 205, 230 - i * 34, 112, 44, 11 + i);
    return tex(c);
  });

/** Red "!" drawn as shapes (no font). */
export const bangTexture = () =>
  once('bang', () => {
    const c = canvas(128, 256);
    const g = c.getContext('2d');
    g.fillStyle = '#c4614e';
    g.strokeStyle = '#7d3527';
    g.lineWidth = 6;
    g.beginPath();
    g.moveTo(40, 20);
    g.lineTo(88, 20);
    g.lineTo(76, 168);
    g.lineTo(52, 168);
    g.closePath();
    g.fill();
    g.stroke();
    g.beginPath();
    g.arc(64, 214, 22, 0, Math.PI * 2);
    g.fill();
    g.stroke();
    return tex(c);
  });

/** Animal Crossing-style anger (vein) mark: four curved red segments. */
export const angerTexture = () =>
  once('anger', () => {
    const c = canvas(256);
    const g = c.getContext('2d');
    g.translate(128, 128);
    g.lineCap = 'round';
    for (let k = 0; k < 4; k++) {
      g.save();
      g.rotate((k * Math.PI) / 2 + Math.PI / 4);
      g.beginPath();
      g.moveTo(22, -46);
      g.quadraticCurveTo(26, -22, 46, -20);
      g.lineWidth = 30;
      g.strokeStyle = '#7d3527';
      g.stroke();
      g.lineWidth = 20;
      g.strokeStyle = '#d4523f';
      g.stroke();
      g.restore();
    }
    return tex(c);
  });

/** Icon card: a crossed-out light bulb. */
export const xCardTexture = () =>
  once('xcard', () => {
    const c = canvas(512);
    const g = c.getContext('2d');
    g.save();
    g.translate(8, 12);
    g.globalAlpha = 0.25;
    roundRect(g, 40, 40, 432, 432, 70);
    g.fillStyle = '#4a3a2e';
    g.fill();
    g.restore();
    roundRect(g, 40, 40, 432, 432, 70);
    g.fillStyle = '#fdfbf6';
    g.fill();
    g.lineWidth = 12;
    g.strokeStyle = '#6b5a4a';
    g.stroke();
    // bulb (off, grey)
    g.beginPath();
    g.arc(256, 210, 92, Math.PI * 0.78, Math.PI * 2.22);
    g.lineTo(296, 330);
    g.lineTo(216, 330);
    g.closePath();
    g.fillStyle = '#e2ddd3';
    g.fill();
    g.lineWidth = 10;
    g.strokeStyle = '#8a8178';
    g.stroke();
    roundRect(g, 214, 330, 84, 56, 14);
    g.fillStyle = '#b8b2a8';
    g.fill();
    g.stroke();
    for (const y of [348, 366]) {
      g.beginPath();
      g.moveTo(216, y);
      g.lineTo(296, y);
      g.lineWidth = 6;
      g.stroke();
    }
    // filament squiggle
    g.beginPath();
    g.moveTo(232, 292);
    g.quadraticCurveTo(244, 240, 256, 262);
    g.quadraticCurveTo(268, 240, 280, 292);
    g.lineWidth = 7;
    g.strokeStyle = '#a49a90';
    g.stroke();
    // red X
    g.lineCap = 'round';
    for (const [a, b, cc, d] of [[132, 112, 380, 400], [380, 112, 132, 400]]) {
      g.beginPath();
      g.moveTo(a, b);
      g.lineTo(cc, d);
      g.lineWidth = 44;
      g.strokeStyle = '#7d3527';
      g.stroke();
      g.lineWidth = 30;
      g.strokeStyle = '#d4523f';
      g.stroke();
    }
    return tex(c);
  });
