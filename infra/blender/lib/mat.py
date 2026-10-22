"""Material factory.  Material *name prefixes* are the contract with the three.js
look layer (infra/web/conform.js), which enforces the Look A values per family:

  vinyl_*   character soft vinyl  (Physical: rough 0.5, clearcoat 0.22/0.5, sheen 0.15/0.8)
  hair_*    vinyl + soft sheen tinted #8a7464
  fur_*     GuoGuo plush base (shell fur is added in three.js)
  prop_*    props / set dressing (rough 0.62)
  wood_*    wood parts (rough 0.62 + wood-grain map; embed one with `image=`)
  fabric_*  curtains, rug, cushions (rough 0.85, light sheen)
  ceramic_* plates, mug, sink (rough 0.28, light clearcoat)
  metal_*   brass / chrome (metalness 1)
  glass_*   window / bulb glass (transparent)
  emit_*    self-lit (laptop screen, sky card)  -- emission keeps its colour
  decal_*   face-decal shells (canvas textures are assigned in three.js)
  ink_*     small dark details (eyes beads, whisker dots) - glossy dark vinyl

Colours are given as sRGB hex strings ('#36435e') and converted to linear.
"""
import bpy
import numpy as np

_cache = {}


def srgb_to_linear(c):
    c = float(c)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgb(h):
    """'#rrggbb' -> linear (r, g, b)."""
    h = h.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b))


def hex_srgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _bsdf(mat):
    nt = mat.node_tree
    return nt.nodes.get("Principled BSDF")


def material(name, color='#ffffff', roughness=0.5, metallic=0.0, coat=0.0, coat_roughness=0.5,
             sheen=0.0, sheen_roughness=0.5, sheen_tint='#ffffff', emission=None, emission_strength=1.0,
             alpha=1.0, double_sided=False, image=None, normal_image=None, normal_strength=1.0,
             transmission=0.0, ior=1.45, reuse=True):
    """Create (or reuse by name) a Principled BSDF material.

    image:        a bpy Image used as Base Color (multiplied by nothing; colour comes from the image)
    normal_image: a bpy Image (non-colour) used as a tangent-space normal map
    """
    if reuse and name in _cache:
        return _cache[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = _bsdf(mat)
    bsdf.inputs["Base Color"].default_value = (*hex_rgb(color), 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["IOR"].default_value = ior
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = coat_roughness
    if sheen:
        bsdf.inputs["Sheen Weight"].default_value = sheen
        bsdf.inputs["Sheen Roughness"].default_value = sheen_roughness
        bsdf.inputs["Sheen Tint"].default_value = (*hex_rgb(sheen_tint), 1.0)
    if transmission:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*hex_rgb(emission), 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            mat.surface_render_method = 'BLENDED'
        except Exception:
            pass
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.extension = 'REPEAT'
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if image.get("has_alpha"):
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            try:
                mat.surface_render_method = 'BLENDED'
            except Exception:
                pass
    if normal_image is not None:
        ntex = nt.nodes.new("ShaderNodeTexImage")
        ntex.image = normal_image
        ntex.image.colorspace_settings.name = 'Non-Color'
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.inputs["Strength"].default_value = normal_strength
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    mat.use_backface_culling = not double_sided
    mat.diffuse_color = (*hex_rgb(color), 1.0)
    _cache[name] = mat
    return mat


# ---- Look A families -------------------------------------------------------

def vinyl(name, color):
    return material(f"vinyl_{name}", color, roughness=0.5, coat=0.22, coat_roughness=0.5,
                    sheen=0.15, sheen_roughness=0.8)


def hair(name, color, sheen_tint='#8a7464', normal_image=None):
    return material(f"hair_{name}", color, roughness=0.45, coat=0.15, coat_roughness=0.4,
                    sheen=0.6, sheen_roughness=0.35, sheen_tint=sheen_tint, normal_image=normal_image)


def prop(name, color, roughness=0.62, double_sided=False, image=None):
    return material(f"prop_{name}", color, roughness=roughness, double_sided=double_sided, image=image)


def wood(name, color, image=None, roughness=0.62):
    return material(f"wood_{name}", color, roughness=roughness, image=image)


def fabric(name, color, image=None, double_sided=True):
    return material(f"fabric_{name}", color, roughness=0.85, sheen=0.3, sheen_roughness=0.6,
                    image=image, double_sided=double_sided)


def ceramic(name, color, image=None):
    return material(f"ceramic_{name}", color, roughness=0.28, coat=0.3, coat_roughness=0.15, image=image)


def metal(name, color, roughness=0.32):
    return material(f"metal_{name}", color, roughness=roughness, metallic=1.0)


def glass(name, color='#ffffff', alpha=0.25):
    return material(f"glass_{name}", color, roughness=0.05, alpha=alpha, double_sided=True)


def emit(name, color, strength=1.0, image=None):
    m = material(f"emit_{name}", color, roughness=0.6, emission=color, emission_strength=strength, image=image)
    if image is not None:
        # route the image to emission too
        nt = m.node_tree
        bsdf = _bsdf(m)
        tex = [n for n in nt.nodes if n.type == 'TEX_IMAGE'][0]
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    return m


def decal(name):
    return material(f"decal_{name}", '#ffffff', roughness=0.45, alpha=0.0, double_sided=False)


def ink(name, color='#2a2421', roughness=0.3):
    return material(f"ink_{name}", color, roughness=roughness, coat=0.5, coat_roughness=0.1)


def fur(name, image=None, color='#ffffff'):
    return material(f"fur_{name}", color, roughness=0.9, sheen=0.5, sheen_roughness=0.5, image=image)


# ---- images from numpy ------------------------------------------------------

def image_from_array(name, arr, colorspace='sRGB', alpha=False):
    """Create a packed bpy Image from a float array HxWx3|4 in [0,1] (row 0 = TOP of the image).

    The image is packed into the .blend and embedded into the GLB as PNG.
    """
    arr = np.asarray(arr, dtype=np.float32)
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.concatenate([arr, np.ones((h, w, 1), np.float32)], axis=2)
    img = bpy.data.images.new(name, width=w, height=h, alpha=alpha, float_buffer=False)
    img.colorspace_settings.name = colorspace
    # Blender stores rows bottom-up
    flat = np.ascontiguousarray(arr[::-1]).reshape(-1)
    img.pixels.foreach_set(flat)
    img.file_format = 'PNG'
    img.pack()
    if alpha:
        img["has_alpha"] = True
    return img
