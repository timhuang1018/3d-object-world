#!/usr/bin/env python3
"""Tile PNGs into one contact sheet:  montage.py out.png in1.png in2.png ... [--cols 3] [--w 480]

The sheet is compressed for viewing (infra/tools/compress.py, <= 1280 px / 250 KB); pass --full to skip.
"""
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compress import compress  # noqa: E402

args = sys.argv[1:]
cols, width = 3, None
if "--cols" in args:
    i = args.index("--cols"); cols = int(args[i + 1]); del args[i:i + 2]
if "--w" in args:
    i = args.index("--w"); width = int(args[i + 1]); del args[i:i + 2]
full = "--full" in args
if full:
    args.remove("--full")
out, files = args[0], args[1:]
ims = [Image.open(f).convert("RGB") for f in files]
if width:
    ims = [im.resize((width, round(im.height * width / im.width))) for im in ims]
w = max(im.width for im in ims)
h = max(im.height for im in ims)
rows = (len(ims) + cols - 1) // cols
sheet = Image.new("RGB", (w * cols, h * rows), (30, 28, 26))
for k, im in enumerate(ims):
    sheet.paste(im, ((k % cols) * w, (k // cols) * h))
sheet.save(out)
print("tiled", out, sheet.size)
if not full:
    compress(out)
