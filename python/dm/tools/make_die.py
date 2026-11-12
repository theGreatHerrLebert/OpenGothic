"""A bone die for stories: chamfered cube, pips in a 3x2 atlas.

    python3 python/dm/tools/make_die.py python/dm_runtime/assets/models   writes wuerfel.obj, .mtl and .png
"""
import itertools, pathlib, sys
from PIL import Image, ImageDraw, ImageFilter

out = pathlib.Path(sys.argv[1]); H, C = 4.5, 0.9          # half edge, chamfer (game units = cm)
CELL = 256
img = Image.new("RGB", (CELL * 3, CELL * 2), (226, 214, 186))
d = ImageDraw.Draw(img)
PIPS = {1: [(.5, .5)], 2: [(.27, .27), (.73, .73)], 3: [(.25, .25), (.5, .5), (.75, .75)],
        4: [(.27, .27), (.73, .27), (.27, .73), (.73, .73)], 5: [(.25, .25), (.75, .25), (.5, .5), (.25, .75), (.75, .75)],
        6: [(.27, .22), (.73, .22), (.27, .5), (.73, .5), (.27, .78), (.73, .78)]}
for n in range(1, 7):
    cx, cy = ((n - 1) % 3) * CELL, ((n - 1) // 3) * CELL
    d.rectangle([cx, cy, cx + CELL - 1, cy + CELL - 1], fill=(232, 221, 194))
    for px, py in PIPS[n]:
        r = CELL * 0.085
        x, y = cx + px * CELL, cy + py * CELL
        d.ellipse([x - r, y - r, x + r, y + r], fill=(40, 28, 20))
img = img.filter(ImageFilter.GaussianBlur(1.2))
# speckles of age
import random
random.seed(7)
for _ in range(900):
    x, y = random.randrange(img.width), random.randrange(img.height)
    v = random.randint(170, 205)
    img.putpixel((x, y), (v, v - 10, v - 30))
img.save(out / "wuerfel.png")

V, VT, VN, F = [], [], [], []
def vert(p): V.append(p); return len(V)
def uv(u, v): VT.append((u, v)); return len(VT)
def nrm(n): VN.append(n); return len(VN)
def poly(points, uvs, n):
    """Points in counter-clockwise order seen from outside (normal n)."""
    ni = nrm(n)
    idx = [(vert(p), uv(*t)) for p, t in zip(points, uvs)]
    for i in range(1, len(idx) - 1):
        F.append((idx[0], idx[i], idx[i + 1], ni))

BONE = (0.03, 0.03)   # a pip-free corner of the atlas, for the chamfers
faces = {(0, 1): 1, (0, -1): 6, (2, 1): 2, (2, -1): 5, (1, 1): 3, (1, -1): 4}   # axis(x=0,y=1,z=2), sign: number
# main faces, inset by the chamfer
for (axis, sign), n in faces.items():
    a, b = [i for i in range(3) if i != axis]
    corners = []
    for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        p = [0, 0, 0]; p[axis] = sign * H; p[a] = s1 * (H - C); p[b] = s2 * (H - C)
        corners.append(tuple(p))
    nvec = [0, 0, 0]; nvec[axis] = sign
    # order counter-clockwise around nvec
    cross = lambda u, w: (u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0])
    e1 = [corners[1][i] - corners[0][i] for i in range(3)]; e2 = [corners[2][i] - corners[0][i] for i in range(3)]
    if sum(x * y for x, y in zip(cross(e1, e2), nvec)) < 0:
        corners.reverse()
    col, row = (n - 1) % 3, (n - 1) // 3
    u0, v0 = col / 3, 1 - (row + 1) / 2
    uvs = [(u0 + 0.0, v0 + 0.0), (u0 + 1 / 3, v0), (u0 + 1 / 3, v0 + 0.5), (u0, v0 + 0.5)]
    poly(corners, uvs, tuple(nvec))

# edges and corners: the convex hull of all 24 inset points fills them; build them explicitly
pts = set()
for (axis, sign) in faces:
    a, b = [i for i in range(3) if i != axis]
    for s1, s2 in itertools.product((-1, 1), repeat=2):
        p = [0, 0, 0]; p[axis] = sign * H; p[a] = s1 * (H - C); p[b] = s2 * (H - C); pts.add(tuple(p))
pts = list(pts)
import numpy as np
from scipy.spatial import ConvexHull
hull = ConvexHull(np.array(pts))
for simplex, eq in zip(hull.simplices, hull.equations):
    n = eq[:3]
    if max(abs(n)) > 0.999:      # a main face, already written with its pips
        continue
    tri = [tuple(pts[i]) for i in simplex]
    e1 = np.subtract(tri[1], tri[0]); e2 = np.subtract(tri[2], tri[0])
    if np.dot(np.cross(e1, e2), n) < 0:
        tri = [tri[0], tri[2], tri[1]]
    poly(tri, [BONE] * 3, tuple(float(x) for x in n))

with open(out / "wuerfel.obj", "w") as f:
    f.write("# a bone die, made by make_die.py\nmtllib wuerfel.mtl\n")
    for p in V: f.write("v %.4f %.4f %.4f\n" % p)
    for t in VT: f.write("vt %.4f %.4f\n" % t)
    for n in VN: f.write("vn %.4f %.4f %.4f\n" % n)
    f.write("usemtl bone\n")
    for a, b, c, ni in F:
        f.write("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a[0], a[1], ni, b[0], b[1], ni, c[0], c[1], ni))
(out / "wuerfel.mtl").write_text("newmtl bone\nmap_Kd wuerfel.png\n")
print(len(V), "vertices", len(F), "triangles")
