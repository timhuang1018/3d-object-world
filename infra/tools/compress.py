#!/usr/bin/env python3
"""Shrink preview images so they are quick to open, review and share.

A raw 1920x1080 Look A frame is 2-3.5 MB as PNG. A compressed preview is <= 250 KB (~12x smaller),
which keeps review sheets, chat attachments and docs light.

What it does: downscale so the longest side is <= --max (default 1280), quantize to a 256-colour
Floyd-Steinberg-dithered palette, optimise, and keep stepping the size down until the file fits
--budget KB. Output stays a .png, so paths in scripts and docs do not change. If the output path ends
in .jpg/.jpeg it is written as a true-colour JPEG (q85) instead: smaller, and best for judging smooth
shading (no palette at all).

    infra/tools/compress.py preview/kitchen/side.png             # in place
    infra/tools/compress.py preview/                             # every PNG under a dir, in place
    infra/tools/compress.py out/stills --to preview/stills       # keep the originals, write copies
    infra/tools/compress.py a.png --max 1024 --budget 150

Files already within budget and size are left untouched, so re-running is cheap and safe.
Importable: `from compress import compress`.
"""
import io
import os
import sys
from pathlib import Path

from PIL import Image

MAX_SIDE = 1280
BUDGET_KB = 250
_STEPS = (1.0, 0.8, 0.64, 0.5, 0.4)  # fallback scales of max_side if still over budget


def _encode(im, side, fmt="PNG"):
    s = side / max(im.size)
    if s < 1:
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    if fmt == "JPEG":
        im.save(buf, "JPEG", quality=85, optimize=True)
    else:
        # Pillow ignores `dither` unless quantizing to a given palette: build the palette first, then
        # map with Floyd-Steinberg so smooth shading does not posterize into fake "bands".
        pal = im.quantize(256, method=Image.Quantize.FASTOCTREE)
        im.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG).save(buf, "PNG", optimize=True)
    return buf.getvalue(), im.size


def compress(src, dst=None, max_side=MAX_SIDE, budget_kb=BUDGET_KB, quiet=False):
    """Compress one image to `dst` (default: overwrite `src`). Returns the bytes written."""
    src = Path(src)
    dst = Path(dst) if dst else src
    before = src.stat().st_size
    im = Image.open(src)
    im.load()
    fmt = "JPEG" if dst.suffix.lower() in (".jpg", ".jpeg") else "PNG"
    if before <= budget_kb * 1024 and max(im.size) <= max_side and im.format == fmt:
        if dst != src:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
        if not quiet:
            print(f"[compress] ok   {src}  {im.size[0]}x{im.size[1]}  {before // 1024} KB")
        return before
    im = im.convert("RGB")  # previews are opaque renders; RGBA would double palette work
    data, size = None, im.size
    for k in _STEPS:
        data, size = _encode(im, min(max_side * k, max(im.size)), fmt)
        if len(data) <= budget_kb * 1024:
            break
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dst)
    if not quiet:
        print(f"[compress] wrote {dst}  {size[0]}x{size[1]}  {before // 1024} KB -> {len(data) // 1024} KB")
    return len(data)


def _main(argv):
    def opt(name, default):
        if f"--{name}" in argv:
            i = argv.index(f"--{name}")
            v = argv[i + 1]
            del argv[i:i + 2]
            return v
        return default

    max_side = int(opt("max", MAX_SIDE))
    budget = int(opt("budget", BUDGET_KB))
    to = opt("to", None)
    if not argv:
        print(__doc__)
        return 2
    total_before = total_after = 0
    for arg in argv:
        p = Path(arg)
        files = sorted(p.rglob("*.png")) if p.is_dir() else [p]
        for f in files:
            dst = None
            if to:
                rel = f.relative_to(p) if p.is_dir() else Path(f.name)
                dst = Path(to) / rel
            total_before += f.stat().st_size
            total_after += compress(f, dst, max_side, budget)
    if total_before:
        print(f"[compress] total {total_before / 1e6:.1f} MB -> {total_after / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
