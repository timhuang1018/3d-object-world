# Bank build conventions (Blender → GLB → three.js)

Every bank item is a **Python script** run with Blender-as-a-module (`bpy` 5.2 in `.venv`). Scripts are
deterministic: no wall clock, and any randomness uses an explicit seed (`numpy.random.default_rng(seed)`
or `random.Random(seed)`). Paths below are relative to a **project** folder (e.g. `samples/scene-001/`)
unless they start with `infra/`.

```bash
./.venv/bin/python infra/blender/build.py tim            # build one item → <project>/public/assets/... + manifest.json
./.venv/bin/python infra/blender/build.py --list
PROJECT=samples/my-scene ./.venv/bin/python infra/blender/build.py
node infra/tools/shot.mjs "/viewer.html?asset=characters/tim.glb&sheet=views" preview/tim/views.png
```
The Vite dev server must be running on `http://127.0.0.1:5173` (`npm run dev`); `infra/tools/shot.mjs` renders
through headless Chrome under the real Look A pipeline and writes a PNG.

> [!TIP]
> **Keep previews small.** A raw 1920×1080 frame is 2–3.5 MB. `infra/tools/shot.mjs` and `infra/tools/montage.py`
> compress their output by default (`infra/tools/compress.py`: longest side ≤ 1280 px, dithered 256-colour PNG,
> ≤ 250 KB); `--full` keeps the raw capture. Write a **`.jpg`** path to get a true-colour JPEG (best for
> judging smooth shading). Prefer one contact sheet (`--t a,b,c --sheet 3`, `sheet=views`, `montage.py`) over
> many single frames, and compress anything else (e.g. `out/stills`) with `infra/tools/compress.py` before
> sharing it.

## 1. Files

| What | Where |
|---|---|
| Item script | `items/<name>.py`: defines `ITEM = {"id": ..., "out": ...}` and `build()` |
| Item-private helpers | `items/<name>_*.py` or `items/*_kit.py` (no `ITEM`, so the builder skips them). Do **not** put project-specific code in `infra/blender/lib/*`; it is shared |
| Output | `public/assets/<out>` (GLB); `public/assets/manifest.json` gets sha256 + provenance |
| Previews | `preview/<name>/*.png` or `.jpg` at the repo root (git-ignored) |

Shared helpers (in `infra/blender/lib/`): `core.py` (scene, `B()` coords, join, modifiers), `geo.py` (sphere, rounded_box,
cylinder, lathe, loft, superellipse, tube, torus, extrude_outline, box_uv, planar_uv, face_shell,
vertex_colors, point_attribute), `mat.py` (material families + `image_from_array`), `tex.py`
(numpy textures: wood_grain, dots_wallpaper, gingham, checks, braided_rug, stripes_normal, sky_window),
`rig.py` (`Rig`, `bind_rigid`, `bind_chain`, `bind_fn`, `ActionBuilder`), `export.py` (GLB export with
reproducible index order, manifest).

## 2. Space and units

- Metres. **The brief's coordinates are three.js coordinates**: x right, **y up**, z toward the camera
  (the open front of the dollhouse).
- Blender is Z-up. Convert with `core.B(x, y, z)` (three.js to Blender); the exporter converts back.
- **Characters face +Z in three.js** (−Y in Blender). A character's own **left is +X**.
- A character's root (origin) is on the floor between its feet (y = 0).

## 3. Names

glTF / three.js **strips `.` `:` `/` `[` `]` from node names**, so use only `[a-z0-9_]`, with suffixes
`_L` / `_R` (the character's own left / right). Object names become node names.

## 4. Materials (name prefix = Look A family, enforced in `infra/web/conform.js`)

`vinyl_` characters (soft vinyl) · `hair_` · `fur_` · `prop_` · `wood_` (embed a grain map) · `fabric_` ·
`ceramic_` · `metal_` · `glass_` · `emit_` (self-lit: screen, sky) · `decal_` (face shells) · `ink_`
(small glossy dark details). Use `lib/mat.py` (`mat.vinyl("hoodie", "#36435e")` → `vinyl_hoodie`).
Colours are the sRGB hex values from the brief. **No text anywhere** (textures are wordless).

## 5. Rigs

- Use `lib/rig.Rig`. **Every bone points straight up with roll 0**. The joints then have identity rest
  rotations in three.js, so the joint axes are the character axes: **x = left, y = up, z = front**.
- Rotation keys are degrees `(rx, ry, rz)` (Blender XYZ Euler, which is three.js `'ZYX'`):
  - `rx > 0` pitches forward (head nods down, arm swings forward/up in front).
  - `ry > 0` turns to the character's left.
  - `rz > 0` rolls toward the character's right. A hanging **left** arm abducts (lifts sideways) with
    `rz > 0`; the **right** arm with `rz < 0`.
- Skin with vertex groups: `bind_rigid` (whole part on one bone) or `bind_chain` (smooth bend along
  shoulder → elbow → wrist, and similar). Max 4 influences per vertex. All meshes of a character use
  one armature.
- **The rest pose is the neutral standing pose**: arms hanging, slightly away from the body.

## 6. Actions (glTF animations)

- Author with `rig.action(name)` / `.key(t_seconds, rot=..., loc=..., scale=..., interp=..., easing=...)`
  / `.done()`. Times are in **seconds**, starting at 0. Scene fps for sampling is 60.
- **Key only the bones the action needs.** three.js layers clips per joint, and channels left at rest
  are ignored.
- Loops: the last key equals the first, so the loop is seamless.
- Prefer arcs, overlap, ease-in/out and settle (`'BACK'`/`'ELASTIC'` easing is fine) over plain sine
  waves; sine-only motion reads as mechanical.
- `loc` keys are offsets from the bone's rest position in character axes.

## 7. Face decals (Tim, the lioness)

- Build the head, then `geo.face_shell(head_obj, center=<head centre, Blender coords>, half_size=S,
  mat=mat.decal("face"))` and `bind_rigid(shell, "head")`. This writes extras `decal_center` and
  `decal_half_size`.
- Mapping (three.js draws the faces on a canvas): `u = 0.5 + (x − cx) / 2S` (x = character's left =
  viewer's right in a front view) and `v = 0.5 + (y − cy) / 2S` (y up). The canvas is drawn **as seen from
  the front**.
- **Do not model eyes, brows or mouths.** Those are decals. Keep the face area (the front of the head
  between the eyes' height and the mouth) clear of geometry, except for what the character's spec
  asks for.

## 8. Spots and hooks in sets

Empties named `spot_<name>` with a custom property `yaw` (degrees, 0 = facing +Z, 90 = facing +X).
Other named empties and nodes the engine drives are listed in each item's brief (door hinge, chair
swivel, screen mesh, light anchors and so on).

## 9. Checklist for a new or changed item

1. `infra/blender/build.py <name>` runs clean, with no exceptions.
2. A `sheet=views` preview, plus `sheet=action&action=<each>` previews, show what the item's spec asks for.
3. The node/joint names and action names match the spec exactly (the scene code drives them by name).
4. GLB size is reasonable: under 6 MB for a set, under 3 MB for a character.
