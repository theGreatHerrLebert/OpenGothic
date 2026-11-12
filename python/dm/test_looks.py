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

    # a shape of its own: the made flower, registered with its texture under a name from their content
    from dm import models
    obj_path, png_path = models.write_flower(looks.models_dir())
    text = obj_path.read_text(encoding="utf-8")
    faces = [line.split()[1:] for line in text.splitlines() if line.startswith("f ")]
    counts = {k: sum(1 for line in text.splitlines() if line.startswith(k + " ")) for k in ("v", "vt", "vn")}
    assert 0 < len(faces) < 300 and all(len(f) == 3 for f in faces)
    assert all(1 <= int(i) <= counts[k] for f in faces for c in f for i, k in zip(c.split("/"), ("v", "vt", "vn")))
    vts = [tuple(map(float, line.split()[1:])) for line in text.splitlines() if line.startswith("vt ")]
    assert all(0 <= u <= 1 and 0 <= v <= 1 for u, v in vts)                  # one texture, nothing outside it
    ys = [float(line.split()[2]) for line in text.splitlines() if line.startswith("v ")]
    assert min(ys) == 0 and 10 < max(ys) < 25                                  # standing on its origin, in cm
    assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    # every triangle counter-clockwise seen from where its normals point, as OBJ wants it
    vs = [tuple(map(float, line.split()[1:])) for line in text.splitlines() if line.startswith("v ")]
    ns = [tuple(map(float, line.split()[1:])) for line in text.splitlines() if line.startswith("vn ")]
    for f in faces:
        a, b, c = (vs[int(x.split("/")[0]) - 1] for x in f)
        n = [sum(ns[int(x.split("/")[2]) - 1][k] for x in f) for k in range(3)]
        cr = models._cross(models._sub(b, a), models._sub(c, a))
        assert models._dot(cr, n) > 0

    calls.clear()
    res.register_mesh_file = lambda a, p, t, s: calls.append(("file", a, p, t, s)) or True
    alias = looks.model(g, "flower.obj", "flower.png")
    assert alias.startswith("DM_") and alias.endswith(".3DS")
    assert [c[0] for c in calls] == ["tex", "file"] and calls[1][2] == str(obj_path) and calls[1][3] == calls[0][1]
    assert calls[1][4] == 1.0
    assert looks.model(g, "flower.obj", "flower.png") == alias                # the same files, the same name
    assert looks.model(g, "flower.obj", "flower.png", scale=100) != alias     # scaled is another mesh
    calls.clear()
    plain = looks.model(g, "flower.obj")
    assert plain not in ("", alias) and [c[0] for c in calls] == ["file"] and calls[0][3] == ""   # its MTL's or white
    obj_path.write_text(text + "# changed\n", encoding="utf-8")
    assert looks.model(g, "flower.obj", "flower.png") != alias                # changed: a new name, the old one stays
    for bad in (("missing.obj", ""), ("flower.obj", "missing.png"), ("../flower.obj", ""), ("flower.png", ""),
                ("flower.obj", "flower.obj"), ("sub/flower.obj", "")):
        assert looks.model(g, *bad) == "", bad
    assert looks.model(types.SimpleNamespace(resources=types.SimpleNamespace()), "flower.obj") == ""   # older engine
print("looks tests passed")

# Mondaloe from an exported aloe: drawn up and slender, a blossom on top in its own material.
from dm import models  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    src = d / "aloe.obj"
    src.write_text("mtllib aloe.mtl\nv -2 0 0\nv 2 0 0\nv 0 10 0\nvt 0 0\nvt 1 0\nvt 0 1\nvn 0 0 1\nvn 0 0 1\nvn 0 0 1\n"
                   "usemtl m0\nf 1/1/1 2/2/2 3/3/3\n", encoding="utf-8")
    (d / "aloe.mtl").write_text("newmtl m0\nmap_Kd aloe_0.png\n", encoding="utf-8")
    out = models.mondaloe(src, d, petals=5)
    v, vt, vn, rest = models.read_obj(out.read_text(encoding="utf-8"))
    assert max(p[1] for p in v[:3]) > 10                                    # drawn up
    assert sum(1 for line in rest if line.startswith("f ")) == 1 + 5 * 7     # the aloe's face, 5 petals both sides + heart
    assert "usemtl bloom" in rest and "map_Kd mondaloe_bloom.png" in (d / "mondaloe.mtl").read_text(encoding="utf-8")
    assert (d / "mondaloe_bloom.png").read_bytes().startswith(b"\x89PNG")
print("mondaloe ok")
