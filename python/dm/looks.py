"""A story's own looks for its own items: a game mesh with its textures recoloured, so a Mondaloe looks like the aloe
it grows beside, but in moonlight.

    from dm import looks
    looks.variant(gothic, "ITPL_SAGITTA_HERB_MIS.3DS", {"tint": [0.78, 0.86, 1.0], "strength": 0.85, "brighten": 1.25})

The game's textures are written out once, recoloured here and kept in the gitignored dm_runtime/assets, named by their
content, so a look made once is found again and a changed look never replaces one in use.
"""

import hashlib
import json
import pathlib

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "assets"


def recolour(source, target, tint, strength=0.8, brighten=1.0):
    """Moves an image's colours towards a tint by its own lightness, keeping its shapes, shading and transparency."""
    from PIL import Image
    img = Image.open(source).convert("RGBA")
    pixels = img.load()
    tr, tg, tb = tint
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            lum = (0.299 * r + 0.587 * g + 0.114 * b) * brighten
            nr = r * (1 - strength) + min(255.0, lum * tr) * strength
            ng = g * (1 - strength) + min(255.0, lum * tg) * strength
            nb = b * (1 - strength) + min(255.0, lum * tb) * strength
            pixels[x, y] = (int(min(255, nr)), int(min(255, ng)), int(min(255, nb)), a)
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target)


def variant(gothic, mesh, look):
    """The name of a mesh that is `mesh` with every texture recoloured by `look`, registered with the engine, or ""
    when the game or the mesh cannot give one."""
    if not mesh or not hasattr(gothic, "resources"):
        return ""
    key = hashlib.sha1(json.dumps([mesh.upper(), look], sort_keys=True).encode("utf-8")).hexdigest()[:10]
    swapped = {}
    for i, texture in enumerate(dict.fromkeys(gothic.resources.mesh_textures(mesh))):
        if not texture:
            continue
        source = ASSETS / "game" / f"{texture.upper()}.png"
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            if not gothic.resources.export_texture(texture, str(source)):
                continue
        own = f"DM_{key}_{i}"
        target = ASSETS / f"{own}.png"
        if not target.exists():
            recolour(source, target, look.get("tint", [1.0, 1.0, 1.0]), look.get("strength", 0.8),
                     look.get("brighten", 1.0))
        gothic.resources.register_texture(f"{own}.TGA", str(target))
        swapped[texture] = f"{own}.TGA"
    if not swapped:
        return ""
    alias = f"DM_{key}.3DS"
    return alias if gothic.resources.register_mesh_variant(alias, mesh, swapped) else ""
