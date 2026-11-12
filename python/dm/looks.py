"""A story's own looks for its own items: a game mesh with its textures recoloured, so a Mondaloe looks like the aloe
it grows beside, but in moonlight.

    from dm import looks
    looks.variant(gothic, "ITPL_SAGITTA_HERB_MIS.3DS", {"tint": [0.78, 0.86, 1.0], "strength": 0.85, "brighten": 1.25})

The engine writes the game's textures out recoloured (the game's own Python has no imaging library, and it is
faster there), into the gitignored dm_runtime/assets, named by their content, so a look made once is found again and
a changed look never replaces one in use.

Or a shape the game does not have: a Wavefront OBJ file in dm_runtime/assets/models with its PNG texture beside it.

    looks.model(gothic, "flower.obj", "flower.png")

The OBJ is read as Blender writes it by default (Y up, -Z forward): y up, 1 unit = 1 cm (give scale=100 for a model
made in metres), its origin where the item stands, one UV set laid on the one texture. models.py makes a test flower.
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


def models_dir():
    """Where a story's own models and their textures are kept (gitignored)."""
    return ASSETS / "models"


def plain_name(name, suffix):
    """Whether `name` is a bare file name with that suffix: nothing outside the models folder can be named."""
    return (isinstance(name, str) and name.lower().endswith(suffix) and len(name) > len(suffix)
            and pathlib.PurePath(name).name == name and name not in (".", ".."))


def _referenced(path, keyword):
    """The existing files a .obj or .mtl names after `keyword` (mtllib, map_Kd), next to it."""
    found = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        words = line.split()
        if words and words[0] == keyword and len(words) > 1:
            candidate = path.parent / " ".join(words[1:])
            if not candidate.is_file():
                candidate = path.parent / words[-1]
            if candidate.is_file():
                found.append(candidate)
    return found


def model(gothic, file, texture="", scale=1.0):
    """The name of a mesh read from the OBJ `file` in models_dir(), drawn with the PNG `texture` from there (or, with
    none, with the images of its MTL file, else plain white), registered with the engine, or "" when the engine or a
    file cannot give one. Named by the files' content, so a changed model never replaces one in use."""
    if not plain_name(file, ".obj") or not (texture == "" or plain_name(texture, ".png")):
        return ""
    if not hasattr(gothic, "resources") or not hasattr(gothic.resources, "register_mesh_file"):
        return ""
    obj = models_dir() / file
    png = models_dir() / texture if texture else None
    if not obj.is_file() or (png is not None and not png.is_file()):
        return ""
    digest = hashlib.sha1(obj.read_bytes())
    digest.update(png.read_bytes() if png is not None else b"")
    if png is None:
        # Drawn with its MTL's images: they are part of what it looks like, so part of its name.
        for mtl in _referenced(obj, "mtllib"):
            digest.update(mtl.read_bytes())
            for image in _referenced(mtl, "map_Kd"):
                digest.update(image.read_bytes())
    digest.update(json.dumps(float(scale)).encode("utf-8"))
    key = digest.hexdigest()[:10]
    own = ""
    if png is not None:
        own = f"DM_{key}_T.TGA"
        gothic.resources.register_texture(own, str(png))
    alias = f"DM_{key}.3DS"
    return alias if gothic.resources.register_mesh_file(alias, str(obj), own, float(scale)) else ""
