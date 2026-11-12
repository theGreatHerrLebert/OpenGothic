"""A story's own looks for its own items: a game mesh with its textures recoloured, so a Mondaloe looks like the aloe
it grows beside, but in moonlight.

    from dm import looks
    looks.variant(gothic, "ITPL_SAGITTA_HERB_MIS.3DS", {"tint": [0.78, 0.86, 1.0], "strength": 0.85, "brighten": 1.25})

The engine writes the game's textures out recoloured (the game's own Python has no imaging library, and it is
faster there), into the gitignored dm_runtime/assets, named by their content, so a look made once is found again and
a changed look never replaces one in use.
"""

import hashlib
import json
import pathlib

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "assets"


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
        own = f"DM_{key}_{i}"
        target = ASSETS / f"{own}.png"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if not gothic.resources.export_texture(texture, str(target), tuple(look.get("tint", [1.0, 1.0, 1.0])),
                                                   look.get("strength", 0.8), look.get("brighten", 1.0)):
                continue
        gothic.resources.register_texture(f"{own}.TGA", str(target))
        swapped[texture] = f"{own}.TGA"
    if not swapped:
        return ""
    alias = f"DM_{key}.3DS"
    return alias if gothic.resources.register_mesh_variant(alias, mesh, swapped) else ""
