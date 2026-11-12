"""Small models made here, so a story's own item can have a shape of its own without Blender: a low-poly flower
rosette, written as a Wavefront OBJ the way the engine reads one (y up, 1 unit = 1 cm, origin at the foot, faces
counter-clockwise seen from the front, one UV set) with its PNG texture beside it.

    python3 python/dm/models.py      # writes flower.obj and flower.png into dm_runtime/assets/models

then `"look": {"model": "flower.obj", "texture": "flower.png"}` in a define_item. The files stay in the gitignored
dm_runtime; nothing made here is committed.
"""

import math
import pathlib
import struct
import sys
import zlib

# Where in the texture each part lies, in image terms (0, 0 is the top left): petals on the left half, the stem top
# right, the flower's heart bottom right.
PETAL_AREA = (0.0, 0.0, 0.5, 1.0)
STEM_AREA = (0.5, 0.0, 1.0, 0.5)
HEART_AREA = (0.5, 0.5, 1.0, 1.0)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(v):
    n = math.sqrt(_dot(v, v)) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def _uv(area, s, t):
    """A point of an area of the texture, s across and t down (0..1), as OBJ coordinates (v runs up)."""
    x0, y0, x1, y1 = area
    return (x0 + (x1 - x0) * s, 1.0 - (y0 + (y1 - y0) * t))


class Obj:
    """Vertices, texture coordinates and normals, and triangles that face where they are told to."""

    def __init__(self):
        self.v, self.vt, self.vn, self.faces = [], [], [], []

    def vertex(self, p, uv, n):
        self.v.append(p)
        self.vt.append(uv)
        self.vn.append(_unit(n))
        return len(self.v)          # OBJ counts from 1

    def triangle(self, a, b, c, front):
        """A triangle seen from `front` (a direction): counter-clockwise from there, as OBJ wants it."""
        pa, pb, pc = self.v[a - 1], self.v[b - 1], self.v[c - 1]
        if _dot(_cross(_sub(pb, pa), _sub(pc, pa)), front) < 0:
            b, c = c, b
        self.faces.append((a, b, c))

    def text(self, comment=""):
        lines = [f"# {comment}"] if comment else []
        lines += [f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in self.v]
        lines += [f"vt {u:.4f} {v:.4f}" for u, v in self.vt]
        lines += [f"vn {x:.4f} {y:.4f} {z:.4f}" for x, y, z in self.vn]
        lines += ["f " + " ".join(f"{i}/{i}/{i}" for i in face) for face in self.faces]
        return "\n".join(lines) + "\n"


def flower(petals=6, height=14.0, radius=4.5, along=4, across=2):
    """A flower rosette: a six-sided stem, petals around a heart that curve up and out, both sides of each drawn."""
    obj = Obj()
    top = height
    # stem: a thin six-sided tube from the ground to the flower
    ring = 6
    stem_r = 0.35
    for i in range(ring):
        a0, a1 = 2 * math.pi * i / ring, 2 * math.pi * (i + 1) / ring
        mid = (a0 + a1) / 2
        out = (math.cos(mid), 0.0, math.sin(mid))
        ids = []
        for k, (a, y) in enumerate(((a0, 0.0), (a1, 0.0), (a1, top), (a0, top))):
            s = (i + (1 if k in (1, 2) else 0)) / ring
            ids.append(obj.vertex((stem_r * math.cos(a), y, stem_r * math.sin(a)),
                                  _uv(STEM_AREA, s, 1.0 - y / top), (math.cos(a), 0.0, math.sin(a))))
        obj.triangle(ids[0], ids[1], ids[2], out)
        obj.triangle(ids[0], ids[2], ids[3], out)
    # heart: a little raised disc over the stem
    heart_r, heart_y = 0.9, top + 0.5
    centre = obj.vertex((0.0, heart_y + 0.3, 0.0), _uv(HEART_AREA, 0.5, 0.5), (0, 1, 0))
    rim = []
    for i in range(8):
        a = 2 * math.pi * i / 8
        rim.append(obj.vertex((heart_r * math.cos(a), heart_y, heart_r * math.sin(a)),
                              _uv(HEART_AREA, 0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)),
                              (math.cos(a) * 0.4, 1.0, math.sin(a) * 0.4)))
    for i in range(8):
        obj.triangle(centre, rim[i], rim[(i + 1) % 8], (0, 1, 0))
    # petals: strips from the heart outwards, widest in the middle, rising and cupped at their edges
    inner = 0.5
    for k in range(petals):
        a = 2 * math.pi * (k + 0.5) / petals
        out = (math.cos(a), 0.0, math.sin(a))
        side = (-math.sin(a), 0.0, math.cos(a))

        def point(t, s):
            width = 0.15 + 2.2 * math.sin(math.pi * min(t, 0.97)) ** 0.8
            r = inner + (radius - inner) * t
            y = top + 0.3 + 2.6 * t - 1.2 * t * t + 0.35 * width * s * s
            return (out[0] * r + side[0] * s * width / 2, y, out[2] * r + side[2] * s * width / 2)

        def normal(t, s):
            e = 1e-3
            dt = _sub(point(min(t + e, 1.0), s), point(max(t - e, 0.0), s))
            ds = _sub(point(t, min(s + e, 1.0)), point(t, max(s - e, -1.0)))
            n = _unit(_cross(ds, dt))
            return n if n[1] >= 0 else (-n[0], -n[1], -n[2])

        for face in (1, -1):        # the top, then the underside: thin as a petal, seen from both
            grid = {}
            for i in range(along + 1):
                for j in range(across + 1):
                    t, s = i / along, -1.0 + 2.0 * j / across
                    n = normal(t, s)
                    n = n if face > 0 else (-n[0], -n[1], -n[2])
                    grid[i, j] = obj.vertex(point(t, s), _uv(PETAL_AREA, j / across, 1.0 - t), n)
            for i in range(along):
                for j in range(across):
                    a0, a1, b1, b0 = grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1]
                    want = normal((i + 0.5) / along, -1.0 + 2.0 * (j + 0.5) / across)
                    want = want if face > 0 else (-want[0], -want[1], -want[2])
                    obj.triangle(a0, a1, b1, want)
                    obj.triangle(a0, b1, b0, want)
    return obj


def png(width, height, pixels):
    """A PNG file of RGBA rows (each a list of (r, g, b, a)), with nothing but the standard library."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + bytes(c for px in row for c in px) for row in pixels)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def flower_texture(size=64, petal=(196, 170, 236), heart=(240, 200, 60), stem=(70, 130, 50)):
    """The flower's texture: petals pale at the heart and coloured at the tips with a darker vein, a green stem and a
    yellow heart, laid out as PETAL_AREA, STEM_AREA and HEART_AREA."""
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            u, v = (x + 0.5) / size, (y + 0.5) / size
            if u < 0.5:
                tip = 1.0 - v                      # the top of the petal area is its tip
                across = abs(u / 0.5 - 0.5) * 2    # 0 on the vein, 1 at the edges
                c = [255 + (p - 255) * (0.35 + 0.65 * tip) for p in petal]
                if across < 0.12:
                    c = [ch * 0.82 for ch in c]
            elif v < 0.5:
                shade = 0.85 + 0.15 * math.sin(u * 40)
                c = [ch * shade for ch in stem]
            else:
                d = math.hypot(u - 0.75, v - 0.75) / 0.25
                c = [ch * (1.0 - 0.35 * min(d, 1.0)) for ch in heart]
            row.append(tuple(int(max(0, min(255, round(ch)))) for ch in c) + (255,))
        rows.append(row)
    return png(size, size, rows)


def write_flower(folder=None, name="flower"):
    """Writes <name>.obj and <name>.png into the folder (by default the models folder of looks.py); their paths."""
    if folder is None:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from dm import looks
        folder = looks.models_dir()
    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    obj_path, png_path = folder / f"{name}.obj", folder / f"{name}.png"
    model = flower()
    obj_path.write_text(model.text(f"{name}: a flower rosette made by models.py, {len(model.faces)} triangles"),
                        encoding="utf-8")
    png_path.write_bytes(flower_texture())
    return obj_path, png_path


if __name__ == "__main__":
    for path in write_flower(sys.argv[1] if len(sys.argv) > 1 else None):
        print(path)
