# Tools

All tools run from the repository root. Capture tools drive the running dev server (`npm run dev`, `http://127.0.0.1:5173`) through headless Google Chrome (`CHROME_PATH` overrides the default macOS path).

| Tool | What it does |
|---|---|
| [`infra/blender/build.py`](../infra/blender/build.py) | Build a project's bank items into GLBs + manifest |
| [`infra/tools/shot.mjs`](../infra/tools/shot.mjs) | Capture one frame, a contact sheet or a bank-viewer sheet; compressed by default |
| [`infra/tools/render.mjs`](../infra/tools/render.mjs) | Export the scene to MP4 (+ animated WebP, PNG frames or key stills) |
| [`infra/tools/compress.py`](../infra/tools/compress.py) | Shrink images for review and sharing (≤ 1280 px, ≤ 250 KB) |
| [`infra/tools/montage.py`](../infra/tools/montage.py) | Tile images into one contact sheet |
| [`infra/tools/probe.mjs`](../infra/tools/probe.mjs) | Print world positions of key joints at given times (for framing) |
| [`infra/tools/evalpage.mjs`](../infra/tools/evalpage.mjs) | Evaluate any JS expression in the player page and print the JSON result |

## build.py

```bash
./.venv/bin/python infra/blender/build.py                         # all items of samples/scene-001
./.venv/bin/python infra/blender/build.py tim office              # selected items
./.venv/bin/python infra/blender/build.py --project samples/x --list
PROJECT=samples/x npm run assets
```

## shot.mjs

```bash
node infra/tools/shot.mjs "/?render=1" preview/frame.png --t 4.2                       # one player frame
node infra/tools/shot.mjs "/?render=1" preview/sheet.png --t 1,3.6,5,7,10,12.5 --sheet 3  # contact sheet
node infra/tools/shot.mjs "/viewer.html?asset=characters/tim.glb&sheet=views" preview/tim.jpg
node infra/tools/shot.mjs "/?render=1" preview/x.jpg --t 7.4 --cam 0.45,1.45,0.95 --target 0.38,0.6,-0.12 --fov 35
```

| Option | Meaning |
|---|---|
| `--t a,b,c` / `--sheet cols` / `--scale 0.5` | Times to capture; tile them into a sheet with this many columns, scaled per tile |
| `--cam x,y,z --target x,y,z --fov deg` | Inspection camera that overrides the scene camera |
| `--max 1280 --budget 250` | Compression limits (longest side, KB) |
| `.jpg` output path | True-colour JPEG instead of a palette PNG (best for smooth shading) |
| `--full` | Keep the raw full-size PNG |

## render.mjs

```bash
node infra/tools/render.mjs                                   # out/scene-001.mp4, H.264 CRF 23
node infra/tools/render.mjs --master                          # CRF 16 near-lossless master
node infra/tools/render.mjs --crf 26 --webp --out media/x.mp4 # smaller + animated WebP preview
node infra/tools/render.mjs --from 3.5 --to 6.2 --frames      # a range, keeping PNG frames
node infra/tools/render.mjs --stills                          # out/stills/<name>.png from scene.stills
node infra/tools/render.mjs --scene beat2                     # another scene id of the project
```

Encoding is `libx264 -preset slow -tune animation -pix_fmt yuv420p -movflags +faststart`. For Scene 001, 13 s at 1080p30 is ≈6 MB at CRF 23, ≈4 MB at CRF 26 and ≈18 MB at CRF 16.

## compress.py / montage.py

```bash
./.venv/bin/python infra/tools/compress.py preview/                         # every PNG under a folder, in place
./.venv/bin/python infra/tools/compress.py out/stills --to media/stills     # keep originals, write copies
./.venv/bin/python infra/tools/montage.py sheet.png a.png b.png c.png --cols 3 --w 480
```

PNG output is a Floyd–Steinberg-dithered 256-colour palette. If it's still over budget, the size steps down until it fits. A `.jpg` destination gives a true-colour JPEG (q85). Files already within budget are left alone.

## probe.mjs / evalpage.mjs

```bash
node infra/tools/probe.mjs 1.0 4.5 7.0 11.0
node infra/tools/evalpage.mjs "(() => { const a = window.__app; a.renderAt(7); return a.scene.camera(7); })()"
```

`window.__app` exposes `renderAt(t)`, `captureAt(t)`, `scene`, `world` and `look`.
