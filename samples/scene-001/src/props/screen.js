// Laptop screen: a wordless code editor. Pastel code bars fill while Tim types.
// Deterministic: layout from a seeded RNG, typed amount + cursor blink are functions of t.
import * as THREE from 'three';
import { rng } from '@infra/math.js';

const W = 512, H = 320;
const BG = '#2f3546';
const BARS = ['#9fc7e6', '#b7b2e6', '#a6d0a8', '#efb995'];

function layout(seed = 7, lines = 26) {
  const r = rng(seed);
  const out = [];
  let indent = 0;
  for (let i = 0; i < lines; i++) {
    if (i > 0 && r.random() < 0.28) indent = Math.max(0, Math.min(3, indent + (r.random() < 0.55 ? 1 : -1)));
    const n = 1 + Math.floor(r.random() * 3);
    const bars = [];
    for (let k = 0; k < n; k++) bars.push({ len: 3 + Math.floor(r.random() * 9), color: BARS[Math.floor(r.random() * BARS.length)] });
    const blank = r.random() < 0.12;
    out.push({ indent, bars: blank ? [] : bars });
  }
  return out;
}

export class LaptopScreen {
  constructor(mesh) {
    this.mesh = mesh;
    this.canvas = document.createElement('canvas');
    this.canvas.width = W;
    this.canvas.height = H;
    this.g = this.canvas.getContext('2d');
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.flipY = false;
    this.texture.anisotropy = 8;
    this.lines = layout();
    this.total = this.lines.reduce((s, L) => s + L.bars.reduce((a, b) => a + b.len + 1, 0) + 1, 0);
    this.key = '';
    if (mesh) {
      mesh.material = new THREE.MeshStandardMaterial({
        color: 0x111111, roughness: 0.25, metalness: 0, emissive: 0xffffff, emissiveMap: this.texture, emissiveIntensity: 0.9, map: this.texture,
      });
      mesh.castShadow = false;
    }
    this.draw(0, true);
  }

  /** typed: characters typed so far (float); cursorOn: blink state */
  draw(typed, cursorOn) {
    const key = `${Math.floor(typed)}|${cursorOn ? 1 : 0}`;
    if (key === this.key) return;
    this.key = key;
    const g = this.g;
    g.fillStyle = BG;
    g.fillRect(0, 0, W, H);
    // title bar with three dots
    g.fillStyle = '#262b3a';
    g.fillRect(0, 0, W, 26);
    ['#e8a598', '#efd29a', '#a6d0a8'].forEach((c, i) => {
      g.beginPath();
      g.arc(16 + i * 18, 13, 5.5, 0, Math.PI * 2);
      g.fillStyle = c;
      g.fill();
    });
    // a tab
    g.fillStyle = BG;
    g.beginPath();
    g.roundRect(70, 6, 92, 20, [6, 6, 0, 0]);
    g.fill();
    g.fillStyle = '#9fc7e6';
    g.fillRect(84, 14, 40, 4);
    const lineH = 15, top = 38, charW = 7.2, gutter = 34;
    const visibleLines = Math.floor((H - top - 6) / lineH);
    let left = Math.floor(typed);
    let curLine = 0, curX = gutter + 10;
    const rows = [];
    for (let i = 0; i < this.lines.length && left > 0; i++) {
      const L = this.lines[i];
      const row = { i, segs: [] };
      let x = gutter + 10 + L.indent * 3 * charW;
      left -= 1;
      for (const b of L.bars) {
        if (left <= 0) break;
        const n = Math.min(b.len, left);
        row.segs.push({ x, w: n * charW, color: b.color });
        x += (b.len + 1) * charW;
        left -= b.len + 1;
      }
      rows.push(row);
      curLine = i;
      curX = row.segs.length ? row.segs[row.segs.length - 1].x + row.segs[row.segs.length - 1].w + 3 : x;
    }
    const scroll = Math.max(0, curLine - visibleLines + 2);
    for (let r = 0; r < visibleLines; r++) {
      const i = r + scroll;
      const y = top + r * lineH;
      // gutter marks (wordless line markers)
      g.fillStyle = 'rgba(160,170,200,0.28)';
      g.fillRect(10, y + 4, 12 + (i % 3) * 3, 4);
      const row = rows.find((q) => q.i === i);
      if (!row) continue;
      for (const s of row.segs) {
        g.fillStyle = s.color;
        g.beginPath();
        g.roundRect(s.x, y + 2, Math.max(2, s.w - 2), 8, 3);
        g.fill();
      }
    }
    if (cursorOn) {
      const r = curLine - scroll;
      g.fillStyle = '#f2ebdd';
      g.fillRect(curX, top + r * lineH + 1, 3, 11);
    }
    this.texture.needsUpdate = true;
  }

  update({ t, typed }) {
    this.draw(Math.min(typed, this.total), Math.floor(t * 2.2) % 2 === 0);
  }
}
