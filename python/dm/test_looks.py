"""Recolouring a texture for a story's own item. Run: python3 python/dm/test_looks.py"""

import pathlib
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import looks  # noqa: E402
from PIL import Image  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    root = pathlib.Path(d)
    looks.ASSETS = root
    src = root / "src.png"
    Image.new("RGBA", (2, 1), (200, 100, 50, 255)).save(src)
    img = Image.open(src)
    img.putpixel((1, 0), (10, 200, 10, 0))   # transparent stays transparent
    img.save(src)
    out = root / "out.png"
    looks.recolour(src, out, [0.8, 0.9, 1.0], strength=1.0)
    r, g, b, a = Image.open(out).getpixel((0, 0))
    assert b > r and a == 255                              # towards the cold tint
    assert Image.open(out).getpixel((1, 0))[3] == 0

    # a variant: textures written out once, recoloured, registered, and the mesh named by its content
    calls = []
    def export(name, path):
        Image.new("RGBA", (1, 1), (120, 160, 80, 255)).save(path)
        calls.append(("export", name))
        return True
    res = types.SimpleNamespace(mesh_textures=lambda mesh: ["ALOE.TGA", "ALOE.TGA", ""], export_texture=export,
                                register_texture=lambda n, p: calls.append(("tex", n)),
                                register_mesh_variant=lambda a, b, t: calls.append(("mesh", a, b, t)) or True)
    g = types.SimpleNamespace(resources=res)
    look = {"tint": [0.78, 0.86, 1.0], "strength": 0.85, "brighten": 1.25}
    alias = looks.variant(g, "ITPL_ALOE.3DS", look)
    assert alias.startswith("DM_") and alias.endswith(".3DS")
    assert [c[0] for c in calls] == ["export", "tex", "mesh"] and calls[2][3] == {"ALOE.TGA": calls[1][1]}
    calls.clear()
    assert looks.variant(g, "ITPL_ALOE.3DS", look) == alias and [c[0] for c in calls] == ["tex", "mesh"]   # made once
    assert looks.variant(types.SimpleNamespace(), "X.3DS", look) == ""     # an engine without looks: none
print("looks tests passed")
