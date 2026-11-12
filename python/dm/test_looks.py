"""A story's own look for its own item. Run: python3 python/dm/test_looks.py"""

import pathlib
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import looks  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    looks.ASSETS = pathlib.Path(d)
    # each texture written out recoloured once, registered, and the mesh named by its content
    calls = []
    def export(name, path, tint, strength, brighten):
        pathlib.Path(path).write_bytes(b"png")
        calls.append(("export", name, tint, strength, brighten))
        return True
    res = types.SimpleNamespace(mesh_textures=lambda mesh: ["ALOE.TGA", "ALOE.TGA", ""], export_texture=export,
                                register_texture=lambda n, p: calls.append(("tex", n)),
                                register_mesh_variant=lambda a, b, t: calls.append(("mesh", a, b, t)) or True)
    g = types.SimpleNamespace(resources=res)
    look = {"tint": [0.78, 0.86, 1.0], "strength": 0.85, "brighten": 1.25}
    alias = looks.variant(g, "ITPL_ALOE.3DS", look)
    assert alias.startswith("DM_") and alias.endswith(".3DS")
    assert [c[0] for c in calls] == ["export", "tex", "mesh"]
    assert calls[0][2:] == ((0.78, 0.86, 1.0), 0.85, 1.25) and calls[2][3] == {"ALOE.TGA": calls[1][1]}
    calls.clear()
    assert looks.variant(g, "ITPL_ALOE.3DS", look) == alias and [c[0] for c in calls] == ["tex", "mesh"]   # made once
    assert looks.variant(types.SimpleNamespace(), "X.3DS", look) == ""     # an engine without looks: none
print("looks tests passed")
