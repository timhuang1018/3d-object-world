"""GLB export + manifest (sha256 + provenance)."""
import hashlib
import json
import os
import bpy

# ROOT = the repository root (provenance paths are recorded relative to it).
# ASSETS = <project>/public/assets; build.py calls set_project() before building anything.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ASSETS = None
MANIFEST = None


def set_project(project_dir):
    """Point the exporter at a project (e.g. samples/scene-001): GLBs go to <project>/public/assets."""
    global ASSETS, MANIFEST
    ASSETS = os.path.join(os.path.abspath(project_dir), "public", "assets")
    MANIFEST = os.path.join(ASSETS, "manifest.json")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export_glb(rel_out, animations=True):
    """Export the whole current scene to <project>/public/assets/<rel_out>."""
    out = os.path.join(ASSETS, rel_out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=out,
        export_format='GLB',
        export_yup=True,
        export_apply=True,             # apply non-armature modifiers
        export_extras=True,            # custom props -> extras (spots, decal frames)
        export_attributes=True,        # '_NAME' custom attributes (e.g. _FURLEN)
        export_texcoords=True,
        export_normals=True,
        export_materials='EXPORT',
        export_image_format='AUTO',
        export_vertex_color='ACTIVE',
        export_animations=animations,
        export_animation_mode='ACTIONS',
        export_force_sampling=True,
        export_optimize_animation_size=True,
        export_optimize_animation_keep_anim_armature=False,
        export_anim_slide_to_zero=False,
        export_def_bones=False,
        export_leaf_bone=False,
        export_rest_position_armature=True,
        export_skins=True,
        export_morph=True,
        export_lights=False,
        export_cameras=False,
    )
    canonicalize_indices(out)
    return out


def canonicalize_indices(path):
    """Make GLB bytes reproducible: Blender's exporter can emit the same triangles in a varying order
    for some meshes. Rotate each triangle so its smallest index comes first (winding kept) and sort the
    triangles. Same vertices, same faces, same byte layout -> stable sha256 in the manifest."""
    import struct
    import numpy as np
    with open(path, "rb") as f:
        data = bytearray(f.read())
    jlen = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(bytes(data[20:20 + jlen]))
    bin_off = 20 + jlen + 8  # start of the BIN chunk payload
    types = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}
    done = set()
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            ai = prim.get("indices")
            if ai is None or prim.get("mode", 4) != 4 or ai in done:
                continue
            done.add(ai)
            acc = gltf["accessors"][ai]
            view = gltf["bufferViews"][acc["bufferView"]]
            dt = types[acc["componentType"]]
            start = bin_off + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            n = acc["count"]
            idx = np.frombuffer(bytes(data[start:start + n * np.dtype(dt).itemsize]), dtype=dt).reshape(-1, 3)
            k = np.argmin(idx, axis=1)
            rows = np.arange(len(idx))
            tri = np.stack([idx[rows, k], idx[rows, (k + 1) % 3], idx[rows, (k + 2) % 3]], axis=1)
            tri = tri[np.lexsort((tri[:, 2], tri[:, 1], tri[:, 0]))]
            data[start:start + tri.nbytes] = tri.astype(dt).tobytes()
    with open(path, "wb") as f:
        f.write(data)


def update_manifest(item_id, rel_out, script_rel, meta=None):
    out = os.path.join(ASSETS, rel_out)
    with open(os.path.join(ROOT, script_rel), "rb") as f:
        script_sha = hashlib.sha256(f.read()).hexdigest()
    entry = {
        "file": rel_out,
        "sha256": sha256_file(out),
        "bytes": os.path.getsize(out),
        "provenance": {
            "tool": "blender (bpy module)",
            "blender": bpy.app.version_string,
            "script": script_rel,
            "script_sha256": script_sha,
        },
    }
    if meta:
        entry["meta"] = meta
    import fcntl
    os.makedirs(ASSETS, exist_ok=True)
    with open(MANIFEST + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # several builds may run in parallel
        data = {}
        if os.path.exists(MANIFEST):
            with open(MANIFEST) as f:
                data = json.load(f)
        data.setdefault("items", {})[item_id] = entry
        data["items"] = dict(sorted(data["items"].items()))
        tmp = MANIFEST + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, MANIFEST)
        fcntl.flock(lock, fcntl.LOCK_UN)
    return entry
