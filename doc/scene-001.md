# Scene 001 · Locked in → the lioness → dishes → the idea fades

The first scene in the own-show scene library. It is copied here as the brief for testing a 3D
build. The source is the `content-creation` project (`docs/own-show.md`,
`docs/own-show-scenes.md`, `assets/toon/**`, `assets/toy3d/**`), as of 2026-10-21.

## 3D stack for this project

**Use Three.js + Blender / GLB.**

| Layer | Tool | Role |
|---|---|---|
| Modelling | Blender | Sculpt and rig characters, sets and props; bake materials; author actions |
| Exchange | GLB (glTF 2.0 binary) | One file per bank item (character, set, prop), with its rig, shape keys and actions |
| Scene + render | Three.js | Load GLBs (`GLTFLoader`), place them from the scene timeline, drive the camera, and render with the look-A post stack |

Why: in the source project, the 3D tryout built every mesh from code primitives (spheres, lathes,
rounded boxes). Its known weak points come from that:
- the hair is lumpy;
- the apron is a flat partial lathe;
- the lioness is assembled from primitives;
- the motion is plain sine curves.

The source engine spec already reserves a `gltf:` part type (a frozen GLB with a sha256 and its
provenance) for sculpted parts. This project tests that path.

## Rules that apply to every scene

| Rule | Meaning for the 3D build |
|---|---|
| **Wordless** | No text drawn anywhere. Screens show bars and icons; bubbles hold pictograms; cards hold icons. Words live only in the narration and subtitles |
| **Deterministic** | Rendering is a pure function of time `t`: no wall clock, no unseeded randomness. The same frame renders the same pixels on the same machine |
| **GuoGuo in every scene** | The king-penguin plush appears somewhere in every scene as an easter egg (peeking, reacting in the background) |
| **Locked look** | "3D toy, Animal Crossing smooth" (look A): soft vinyl characters, a dollhouse room, a free camera, face-decal expressions |
| **Picks are frozen** | Randomness belongs at design time: generate options, Tim picks, the pick goes into the bank |
| **Camera** | Must pan, tilt and zoom easily |

References: *Animal Crossing: New Horizons* and *Sylvanian Families*. Express the human through
expression and gesture, "more like a cute stickman".

## Brief

> "I was really lock in on building app with ai agent, but my wife (A fierce lioness) break into
> the room and tell me to do the chores (washing dishes), while I am doing that, the light bulb
> (idea) in my head fade out." (Tim, 2026-09-26)

**Tim's picks:**
- the lioness is **A**, a full lioness in an apron;
- the idea is a **light bulb** (a campfire was tried and not picked);
- the bulb fades slowly and ends in a snuffed-out smoke wisp.

**Verdict:** "this tryout scene meet my expectation". The 2.5D wordless animatic v2 is the
quality bar.

**Placeholder narration** (Tim's voice; never drawn on screen):
1. "I was locked in, building an app with my agent…"
2. "…then the lioness arrived."
3. "So I did the dishes."
4. "And the idea? Gone."

## Timeline (13 s, 4 beats)

| # | Time | Set | Camera | What happens | Bulb |
|---|---|---|---|---|---|
| 1 | 0.0–3.5 | office | ¾ front push-in | **Locked in.** Tim types at the desk, focused. A warm focus glow surrounds him and the bulb above his head is bright | 1.0 |
| 2 | 3.5–6.2 | office | two-shot | **Break-in.** The door swings open, with speed lines. The lioness strides to the doorway and points; a bubble shows dirty plates and "!", and she has an anger mark. Tim snaps into shock and the bulb flickers | flickers 0.35–0.85 |
| 3 | 6.2–9.7 | kitchen | side truck | **Dishes.** Tim scrubs a plate at the sink, glum. The plate stack shrinks from 6 to 3, a cool glow replaces the warm one, and the bulb dims | 0.75 → 0.3 |
| 4 | 9.7–13.0 | kitchen | close push-in | **Idea gone.** Tim slumps, deflated. The bulb gives one last flicker, goes out and lets off a smoke wisp, then a ✗-bulb card pops in | 0.3 → out |

**Beat-level cues** (seconds after the beat starts):
- **Beat 2:**
  - 0.05: the door opens (0.25 s).
  - 0.1: the lioness moves to the doorway (0.6 s, ease out, with a walk bob).
  - 0.12: speed lines.
  - 0.25: Tim goes to `sit_shock` / shocked (0.2 s, ease back).
  - 0.35: the bulb flickers.
  - 0.8: the bubble (dishes + bang) and the anger mark.
- **Beat 3:** the bulb (1.0 → 0.3) and the stack (6 → 3) both run linearly over 3.5 s.
- **Beat 4:**
  - 0.0: the bulb fades to 0.05 (0.9 s).
  - 0.1: Tim goes to `stand_sink_idle` / deflated (0.4 s).
  - 0.65: one blink back up to 0.35.
  - 0.9: the bulb goes out.
  - 1.6: the ✗ card appears at screen position (0.64, 0.30).

### Beat 2 already in 3D (8 s, the locked clip)

The 3D tryout rendered beat 2 alone, as one continuous camera move. It is the parity reference
for the locked look, and it adds GuoGuo watching from the top of the bookshelf.

| t (s) | Event |
|---|---|
| 0.0 | Tim types; GuoGuo sits on the shelf watching him; the camera orbits in |
| 1.25 / 3.02 | Tim blinks |
| 1.9 | The lioness's ears flick behind the door |
| 2.2 | **The door bursts open** (spring ring, dust puff); GuoGuo is startled (hop, flipper flap, squash, jelly settle, wide eyes) |
| 2.21–2.5 | The lioness braces through the door, then straightens up |
| 2.3–3.0 | She walks to just inside the door (the camera pans to the door, then to her) |
| 2.75 | She turns 45°, cheated toward the camera |
| 2.9 | The far paw goes on her hip (akimbo) |
| 3.0 | She points at Tim and jabs twice (0.42 s and 0.66 s after the point starts); the "!" pulses with the jabs |
| 3.12 | The bubble pops in: dirty plates + "!" |
| 3.78 | Tim's swivel chair turns toward the door |
| 3.9 | **Shock:** Tim's hands go up, he jolts and trembles, the chair rolls back 0.1 m, a sweat drop slides down, GuoGuo flinches; the camera zooms in on Tim |
| 3.9–5.5 | The bulb flickers out (0.1, 0.9, 0.15, 0.85 … 0.0); smoke puffs |
| 4.61 | The lioness blinks |
| 4.85 | The camera tilts up to the dying bulb |
| 5.6–7.6 | The camera re-bases and orbits out to a wide shot |

## Look A (render settings)

| Setting | Value |
|---|---|
| Frame | 1920 × 1080, 30 fps |
| Tone mapping | Neutral, exposure 0.95 |
| Background / fog | `#e8e0d4`, fog from 13 m to 30 m |
| Environment | `RoomEnvironment` PMREM (sigma 0.04), intensity 0.3 |
| Shadows | PCF; a 4096 key-light map with extent 5.5 and radius 5 |
| Lights | hemisphere `#fff4e4`/`#cdb79a` at 0.6 · key `#fff0dc` at 2.3 from (3.2, 6.5, 5.5) · rim `#e9eeff` at 0.55 from (-3, 4, -5) · warm hall point light · a faint blue laptop screen light |
| Post | MSAA ×4 · GTAO (radius 0.32, 16 samples, blend 0.8) with a seeded denoise · bloom 0.42 / radius 0.45 / threshold 1.6 (only the bulb blooms) · vignette 0.16 · no grain |
| Character material ("soft vinyl") | `MeshPhysicalMaterial`: roughness 0.5, clearcoat 0.22 (roughness 0.5), sheen 0.15 (roughness 0.8) |
| Prop material | roughness 0.62, with a wood-grain map on wood parts |
| Face decals | roughness 0.45; a canvas-drawn texture on a front-projected shell, swapped per expression |

Camera: perspective with near 0.05 and far 60; the field of view is mostly 30°, zooming to 12.5°
for close-ups. Units are metres.

## Characters

### Tim (the host)

An Animal Crossing-style villager with a chibi head (radius 0.42 m on a 0.42 m torso). He stands
about 1.5 m tall.

| Part | Description |
|---|---|
| Signature features | **Hair H3, a textured crop**: dark brown-black with a soft sheen, a high near-straight fringe, a soft M at the temples, and short sides tapering to the nape. **Thin round wire glasses** as real geometry (rings 0.092 m) |
| Body | A navy hoodie with a hood ring, a kangaroo pocket and splayed drawstrings; dark cuffs and hem; taupe pants; cream shoes with tan soles; ears |
| Rig (FK) | `seat.ry`/`seat.pz` (swivel chair), hips, torso, neck (3 axes), two-joint arms and legs |
| Expressions in 3D | `neutral`, `blink`, `shock` (white shock eyes, open mouth, forehead gloom lines, and a sweat drop that pops and slides down) |
| Expressions in 2.5D | neutral, talking, happy, **focused**, worried, shocked, **glum**, **deflated** (bold ones = used in 001) |
| Default face since 2026-10-19 | **"Dead fish" A eyes + a flat mouth** (heavy flat lids, pupils hanging under them, no smile), with a matching blink, for Tim in every scene |
| Poses | `typing` (seated, with typing loops on the arms, head bob and foot swing), `shock` (hands up, jolt, tremble, hands wiggling), `turned` (the chair swivels), `pushed` (the chair rolls back) · 2.5D only so far: `stand_wash` (scrubbing loop, right hand), `stand_sink_idle` |

Palette: skin `#f4dcc6` · hoodie `#36435e` / `#2c374d` · drawstring `#efe7d8` · pants `#8f8576` ·
shoe `#ece5d8` · sole `#a08d78` · hair `#2b241f` (sheen `#8a7464`) · wire `#3b3633` · ink
`#2a2421` · mouth `#6b3f36` · blush `#e49286` · gloom `#7891be` · sweat drop `#a9cfe3`.

### The lioness (lioness A)

A Sylvanian Families-style figure. She stands about 1.6 m tall (built at scale 1.15).

| Part | Description |
|---|---|
| Lion cues | **No mane** in 3D. Side-set round ears with dark backs, a cat muzzle with whisker dots and whiskers, a pink-brown nose, cream under-eye patches and a tufted tail |
| Clothes | A lavender dress and a cream apron with a gingham hem, a bib and a pocket |
| Rig (FK) | root yaw, hips, body, neck, two-joint arms and legs, tail, ears; a pointing finger on the right paw |
| Walk | Phase comes from the distance walked: stride 0.2, bob 0.022, sway 0.06; it settles after arrival |
| Expressions in 3D | `stern` (flat lids with the inner corners lower, brows slanting down to the nose), `blink` · 2.5D adds `angry` |
| Poses | `stand` (tail sway loop), `listen` (ear flick), `brace` (leans in), `upright`, `turned` (45° toward the camera), `akimbo` (far paw on her hip), `point` (jabs twice) |

Palette: fur `#d5b186` / light `#e3c6a0` · muzzle `#f3e7d2` · nose `#b27c6c` · inner ear `#efd9c0`
· ear back `#6e5442` · tail tuft `#7a5a40` · dress `#a8a8c6` · apron `#f7f1e6` with a
`rgba(201,139,124,0.5)` check · brow `#8a6446`.

Known weak points: the build is primitives and the walk is a sine curve. A sculpted Blender
version is the obvious first GLB test.

### GuoGuo (the mascot easter egg)

Tim's own king-penguin hand-puppet plush, **frozen at v7** (2026-10-13). He is child-size (about
0.66 m standing), and in scene 001 he sits **on top of the bookshelf**, in frame for every beat.

| Trait | Description |
|---|---|
| Fur | Long-pile fluffy fur all over; shorter pile around the eyes and on the head |
| Head | Black, down to the flipper-top line all round, with no neck: the head and body are one continuous loft |
| Beak | Long and black, tilted about 14° down, with an orange stripe on the lower mandible |
| Eyes | Blue glass beads set flush on the sides of the head, close to the beak, with big pupils |
| Cheeks | Large round orange patches, low on each side of the head |
| Throat | A **yellow V-shaped bib**, not a band |
| Body | A full white front, with a medium-grey back and sides |
| Flippers | Stuck out sideways: white in front, grey behind |
| Feet | Stubby and black |
| Poses | `standing` (design views) · `seated` (a pyramid silhouette: idle head wander, breathing bob, flipper paddle) · `startled` (hop, hard flap, squash on landing, jiggle, shiver, wide eyes) · `flinch` · `look_off` |
| Face | No decal: his face is the beads and the beak; wide eyes are a pose flag |

Palette: white `#f3f2ee` · grey `#9b9da0` · black `#1b1b1e` · bib `#f4e638` · orange `#f56a1c` ·
iris `#2f78bd` · pupil `#0b0b0d`.

The 3D build is a lofted body from traced photo outlines, with shell fur (22 shells, length 0.015
m). The frozen profile table is `assets/toy3d/bank/characters/guoguo.yaml` in the source project.
For Blender, either rebuild the loft from that table or sculpt to the reference views; then use
hair particles or a shell-fur shader in Three.js.

## Sets

### Office + hall (3D, frozen)

A Sylvanian-style **dollhouse cutaway**, open at the front and on the right, standing on a large
round tabletop.

| Element | Size / place (m) |
|---|---|
| Room | x −2.6 … 2.4, z −1.9 … 1.25; walls 2.3 high, 0.1 thick |
| Door | In the left wall, z −1.125 … −0.275, 1.75 high; a white panel door with a brass knob. It swings in, rings on a spring and puffs dust |
| Hall | Beyond the door: x −4.3 … −2.7, z −1.75 … 0.35, with checked wallpaper, a warm light and vases |
| Window | On the back wall, x 1.45 … 2.15, y 0.95 … 1.75. It has a sky, clouds and hills, and gingham curtains on a wooden rod |
| Desk | Centre (0.85, z 0.025); 1.15 × 0.55, 0.55 high. Holds a laptop, a mug, a notebook and a small plant |
| Laptop | The lid is tilted 0.26 rad. The screen (0.35 × 0.22) is a wordless code editor: pastel code bars fill while Tim types |
| Swivel chair | At (0.85, 0, −0.5), behind the desk facing the camera; a mustard pad on a grey frame |
| Bookshelf | Centre x −0.45, against the back wall; 0.88 × 1.02 × 0.41, with 3 shelves of seeded pastel books, a pot plant and a vase on top |
| Other dressing | A floor plant near the back wall, a round braided rug (radius 0.85) under Tim, a wall clock on the left wall, a landscape painting on the back wall |
| Walls | Cream wallpaper with small flower dots, a sage wainscot, cream trim, wooden beams |
| Floor | Warm wooden planks |

| Spot | Position | Used for |
|---|---|---|
| `desk_seat` | (0.85, 0, −0.5), seat = chair | Tim typing |
| `doorway_out` | (−3.25, 0, −0.7), yaw 90° | The lioness in the hall, before the burst |
| `doorway_in` | (−1.15, 0, −0.1), yaw 90° | The lioness just inside the door |
| `shelf_top` | (−0.26, 1.04, −1.72) | GuoGuo |
| `turntable` | (1.85, 0, 0.65) | Design views |

Palette (main): wall `#efe5d1` · flower dots `#d9ad9f`/`#a9b897` · wainscot `#b9c3a8` · trim
`#f5efe3` · floor `#c9a47c` · beam `#b98e67` · exterior `#e3d5bf` · door `#f2ebdd` · brass
`#c8a66a` · hall wall `#efdcb4` · desk `#d9b68e` / `#b8916b` · laptop `#ccc8c1` / `#5a5753` ·
screen `#2f3546` with code bars `#9fc7e6 #b7b2e6 #a6d0a8 #efb995` · chair pad `#d2b06f` · frame
`#6c6661` · shelf `#cfa77f` · plant `#93a77f` / `#7c9169` · pot `#c99a7a` · tabletop `#d8ccba`.

### Kitchen (2.5D only, not built in 3D yet)

Beats 3–4 need it. In the 2.5D engine it is a ghosted kitchen: counter, **sink with faucet and
suds**, window and cabinets, with one spot, `sink`. For the 3D test, build it in the same dollhouse
language and palette as the office, with GuoGuo placed somewhere in frame (for example on a
cabinet top or a windowsill).

## Props and graphics

| Item | 3D status | Description |
|---|---|---|
| **Idea bulb** | Built | Floats 0.76 m above the head. It drifts (bob 0.025, tilt 0.05) and has a glow sprite, rays at levels above 0.5, and a brightness level `b` from 0 to 1 (lit above 0.05). **Out:** it droops and tilts over 0.5 s, then 3 smoke puffs rise. Glass `#fff6dc` lit / `#e2ddd3` off, emissive `#ffe2a0`, screw `#b8b2a8`, ray `#f3d58e`, smoke `#9a948c` |
| **Speech bubble** | Built | A billboard beside the speaker's head (right 0.42, up 0.62 in camera axes) that bobs and pops in. It holds a dirty-plates pictogram and a red "!" (`#c4614e`) that pulses with the point jabs. Bubble `#fdfbf6`, plate `#f3eee4`, brown smudges and crumbs |
| **Sweat drop** | Built | Tim's shock: pops 0.18 s in and slides down |
| **Door dust** | Built | A puff when the door swings |
| Plate (held) | 2.5D only | Held in Tim's hands while he scrubs |
| Plate stack | 2.5D only | Beside the sink; its count animates from 6 to 3 |
| Faucet + suds | 2.5D only | Part of the kitchen set |
| Anger mark | 2.5D only | An Animal Crossing-style vein mark by the lioness's head |
| Speed lines | 2.5D only | Behind the lioness as she bursts in |
| Focus glow | 2.5D only | Warm (beat 1) and cool (beats 3–4) radial glow around Tim |
| ✗-bulb card | 2.5D only | An icon card, a crossed-out bulb, that pops in at the end (screen position 0.64, 0.30) |

## Cameras

| Beat | 2.5D preset | Feel |
|---|---|---|
| 1 | `front34_push` | ¾ front, a slow push-in |
| 2 | `two_shot` | Wider, framing the door and Tim, with a quick punch-in on the burst |
| 3 | `side_truck` | A side view of the sink, slowly trucking around |
| 4 | `close_push` | Close on Tim's head and the bulb, a slow push-in |

The 3D beat-2 camera (`beat2`) is one continuous orbit:
1. It starts at azimuth 40°, elevation 27°, distance 10.2 and eases in to 6° / 12° / 5.8 over
   2.25 s.
2. The target then pans to the door (2.3 s), the lioness (2.85 s) and Tim (3.45 s).
3. The field of view zooms 30° → 12.5° on the shock (4.0 s).
4. The camera tilts up to the bulb (4.85 s).
5. It re-bases and orbits out to −13° / 4° / 4.9 (5.6–7.6 s).

The 3D stills:

| Still | Camera position | Target | FOV |
|---|---|---|---|
| `twoshot` | (−0.55, 1.28, 3.55) | (−0.15, 1.12, −0.3) | 31° |
| `closeup` | (0.36, 1.42, 1.75) | (0.84, 1.3, −0.5) | 30° |

## Asset checklist for Blender → GLB

| Asset | In the source 3D bank | To do here |
|---|---|---|
| Tim | Yes (primitives + FK) | Sculpt the head, H3 hair, hoodie; rig; shape keys or a decal atlas for the faces (default "dead fish" face, blink, shock, focused, glum, deflated) |
| Lioness | Yes (primitives) | Sculpt; rig with ears, tail and a finger; add the `angry` face |
| GuoGuo | Yes (loft + shell fur) | Rebuild standing and seated; fur |
| Office + hall | Yes | Model as a dollhouse GLB with named spot empties and a door hinge |
| Kitchen | No | New: counter, sink, faucet, suds, window, cabinets; a `sink` spot and a GuoGuo spot |
| Idea bulb | Yes | Model; drive the level and the smoke from Three.js |
| Plate, plate stack | No | New |
| Bubble, ✗ card, anger mark, speed lines, glow | Bubble only | Billboards or sprites in Three.js (pictograms only, no text) |
| Poses / actions | Partly | Blender actions: typing, shock, chair swivel, walk, point, akimbo, wash loop, sink idle, GuoGuo seated/startled/flinch |

## Source files (in `content-creation`)

| What | Path |
|---|---|
| Show guideline (style, rules, GuoGuo) | `docs/own-show.md` |
| Scene library entry 001 | `docs/own-show-scenes.md` |
| 2.5D scene file (the 13 s, 4 beats) | `assets/toon/scenes/001-lioness-dishes.yaml` |
| 3D scene file (beat 2, 8 s) | `assets/toy3d/scenes/001-beat2-break-in.yaml` |
| 3D bank (style, characters, poses, expressions, set, props, cameras) | `assets/toy3d/bank/**` |
| 2.5D bank (kitchen, plates, 2.5D poses and expressions) | `assets/toon/bank/**` |
| Toy3D engine spec | `docs/superpowers/specs/2026-10-13-toy3d-engine-v0-design.md` |
| Frozen 3D tryout (`scene.js`, the stills, `locked_clip_v7.mp4`) | `output/projects/20260724-hybrid-ai-agent-controller/style-tryouts/r7-3d/frozen-v7-20261013/` |
| 2.5D animatic v2 (the quality bar) | `output/own-show/scenes/001-lioness-dishes/animatic_v2_bulb.mp4` |
