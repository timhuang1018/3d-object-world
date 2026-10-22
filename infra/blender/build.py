"""Build bank items (Blender -> GLB) for a project.

  ./.venv/bin/python infra/blender/build.py                         # every item of the default project
  ./.venv/bin/python infra/blender/build.py tim office              # selected items (by short name)
  ./.venv/bin/python infra/blender/build.py --project samples/scene-001 --list
  PROJECT=samples/my-scene ./.venv/bin/python infra/blender/build.py

A project is a folder (default: samples/scene-001, or $PROJECT) with:
  items/<name>.py      one module per bank item (items/__init__.py makes it a package)
  public/assets/       where the GLBs and manifest.json are written

Each item module defines:
  ITEM = {"id": "characters/tim", "out": "characters/tim.glb"}
  def build() -> dict | None      # builds into a fresh scene; may return manifest meta
Optionally `SAVE_BLEND = True` writes <project>/out/blend/<name>.blend for inspection.
Item modules import shared helpers as `from lib import core, geo, mat, rig, tex` and each other as
`from items import <module>`. Files starting with "_" are skipped unless named explicitly.
"""
import importlib
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

from lib import core, export  # noqa: E402


def _project_from(argv):
    if "--project" in argv:
        i = argv.index("--project")
        p = argv[i + 1]
        del argv[i:i + 2]
    else:
        p = os.environ.get("PROJECT", "samples/scene-001")
    return p if os.path.isabs(p) else os.path.join(REPO, p)


def available(items_dir):
    """Item modules = items/*.py that define ITEM at top level (helpers like *_kit.py are skipped)."""
    names = []
    for f in sorted(os.listdir(items_dir)):
        if not f.endswith(".py") or f.startswith("_"):
            continue
        with open(os.path.join(items_dir, f), encoding="utf-8") as fh:
            if any(line.startswith("ITEM") and "=" in line for line in fh):
                names.append(f[:-3])
    return names


def build_one(name, project):
    mod = importlib.import_module(f"items.{name}")
    core.reset_scene(fps=getattr(mod, "FPS", 60))
    from lib import mat as _mat
    _mat._cache.clear()
    t0 = time.time()
    meta = mod.build() or {}
    rel_out = mod.ITEM["out"]
    export.export_glb(rel_out, animations=getattr(mod, "ANIMATIONS", True))
    entry = export.update_manifest(mod.ITEM["id"], rel_out, os.path.relpath(mod.__file__, export.ROOT), meta)
    if getattr(mod, "SAVE_BLEND", False):
        import bpy
        p = os.path.join(project, "out", "blend", f"{name}.blend")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=p, compress=True)
    print(f"[build] {name}: {rel_out}  {entry['bytes'] / 1024:.0f} KiB  sha256 {entry['sha256'][:12]}  "
          f"({time.time() - t0:.1f}s)")


def main(argv):
    argv = list(argv)
    project = _project_from(argv)
    items_dir = os.path.join(project, "items")
    if not os.path.isdir(items_dir):
        print(f"[build] no items/ folder in {project}")
        return 2
    sys.path.insert(0, project)  # `items.<name>` resolves inside the project
    export.set_project(project)
    if "--list" in argv:
        print("\n".join(available(items_dir)))
        return 0
    names = [a for a in argv if not a.startswith("-")] or available(items_dir)
    bad = 0
    for n in names:
        try:
            build_one(n, project)
        except Exception:
            bad += 1
            print(f"[build] {n}: FAILED")
            traceback.print_exc()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
