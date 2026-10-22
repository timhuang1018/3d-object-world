// Loads the bank (GLBs) and builds the world: sets, actors, props, FX.
import * as THREE from 'three';
import { loadAsset } from '@infra/loader.js';
import { Actor, placeholder } from '@infra/actor.js';
import { setFace } from './actors/faces.js';
import { addShellFur } from './actors/fur.js';
import { Bulb } from './props/bulb.js';
import { AngerMark, Bubble, DoorDust, FocusGlow, SpeedLines, SweatDrop, XCard } from './props/fx.js';
import { OfficeSet } from './sets/office.js';
import { KitchenSet } from './sets/kitchen.js';

export const BANK = {
  office: 'sets/office.glb',
  kitchen: 'sets/kitchen.glb',
  tim: 'characters/tim.glb',
  lioness: 'characters/lioness.glb',
  guoguo: 'characters/guoguo.glb',
  bulb: 'props/bulb.glb',
  dishes: 'props/dishes.glb',
};

export async function buildWorld(look, onProgress = () => {}) {
  const missing = [];
  let done = 0;
  const entries = await Promise.all(
    Object.entries(BANK).map(async ([k, rel]) => {
      try {
        const g = await loadAsset(rel, look.renderer);
        return [k, g];
      } catch (e) {
        console.warn(`[bank] ${rel} not available: ${e.message}`);
        missing.push(rel);
        return [k, null];
      } finally {
        onProgress(++done / Object.keys(BANK).length);
      }
    }),
  );
  const g = Object.fromEntries(entries);
  const scene = look.scene;

  const office = new OfficeSet(g.office);
  const kitchen = new KitchenSet(g.kitchen, g.dishes);
  scene.add(office.root, kitchen.root);
  if (!g.office && !g.kitchen) {
    const table = new THREE.Mesh(new THREE.CylinderGeometry(7, 7, 0.1, 96), new THREE.MeshStandardMaterial({ color: 0xd8ccba, roughness: 0.8 }));
    table.position.y = -0.05;
    table.receiveShadow = true;
    scene.add(table);
  }

  const tim = new Actor('tim', g.tim || placeholder(0x36435e, 1.5));
  const lioness = new Actor('lioness', g.lioness || placeholder(0xd5b186, 1.6));
  const guoguo = new Actor('guoguo', g.guoguo || placeholder(0x1b1b1e, 0.5));
  scene.add(tim.root, lioness.root, guoguo.root);
  if (g.tim) setFace(tim.model, 'tim', 'focused');
  if (g.lioness) setFace(lioness.model, 'lioness', 'stern');
  if (g.guoguo) addShellFur(guoguo.model);
  guoguo.wide = ['eyewide_L', 'eyewide_R'].map((n) => guoguo.model.getObjectByName(n)).filter(Boolean);

  // held props for the dishes beats
  const held = {
    plate: kitchen.makeProp('plate_dirty'),
    sponge: kitchen.makeProp('sponge'),
    spongeSuds: kitchen.makeProp('suds_puff'),
  };
  for (const p of Object.values(held)) if (p) scene.add(p);

  const bulb = new Bulb(g.bulb ? g.bulb.scene : new THREE.Mesh(new THREE.SphereGeometry(0.075), new THREE.MeshStandardMaterial()));
  scene.add(bulb.root);

  const fx = {
    bubble: new Bubble(),
    anger: new AngerMark(),
    speed: new SpeedLines(),
    warmGlow: new FocusGlow(),
    coolGlow: new FocusGlow(),
    sweat: new SweatDrop(),
    dust: new DoorDust(),
    card: new XCard(look),
  };
  scene.add(fx.bubble.root, fx.anger.root, fx.speed.root, fx.warmGlow.root, fx.coolGlow.root, fx.dust.root);

  return { look, sets: { office, kitchen }, actors: { tim, lioness, guoguo }, bulb, fx, held, missing };
}
