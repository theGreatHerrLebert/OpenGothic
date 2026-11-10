"""Where every character is, by world, chapter and hour, read from the game's own scripts and worlds.

    python3 python/dm/map_data.py <GOTHIC install>

Needs mechanics/world.jsonl from tools/world_dump.cpp (it holds the waypoints). Writes
python/dm_runtime/map/map_data.json, which quotes character names from the game and so stays out of the repository.

A character is placed by its daily routine: each TA_ entry says what it does from one time to another at one waypoint.
The routine it starts with comes from its instance; chapter scripts (B_ENTER_<world>_KAPITEL_<n>) can swap it, and
dialogue can swap it too. Those dialogue routines depend on the player and are listed, not placed.
"""

import json
import pathlib
import re
import struct
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import depmap as dm  # noqa: E402
import quest_mine as qm  # noqa: E402
import voices  # noqa: E402
from bake_voices import read_vdf_index  # noqa: E402

OUT = voices.RUNTIME_DIR / "map" / "map_data.json"
IMAGES = voices.RUNTIME_DIR / "map"
TEXTURE_ARCHIVES = ("Textures.vdf", "Textures_Addon.vdf")
WORLD_DUMP = voices.RUNTIME_DIR / "mechanics" / "world.jsonl"

WORLDS = {  # world file → the scripts that fill it at the start and on entering it in each chapter
    "NEWWORLD.ZEN": ("STARTUP_NEWWORLD", "B_ENTER_NEWWORLD_KAPITEL_"),
    "OLDWORLD.ZEN": ("STARTUP_OLDWORLD", "B_ENTER_OLDWORLD_KAPITEL_"),
    "ADDONWORLD.ZEN": ("STARTUP_ADDONWORLD", "B_ENTER_ADDONWORLD_KAPITEL_"),
    "DRAGONISLAND.ZEN": ("STARTUP_DRAGONISLAND", None),
}
CHAPTERS = range(1, 7)
TA = re.compile(r'^(TA_[A-Z0-9_]+)\((\d+), (\d+), (\d+), (\d+), "([^"]+)"\)$')
INSERT = re.compile(r'^WLD_INSERTNPC\(([A-Z0-9_]+), "([^"]+)"\)$')
SWAP = re.compile(r'^(?:B_STARTOTHERROUTINE|NPC_EXCHANGEROUTINE)\(([A-Z0-9_]+), "([^"]+)"\)$')
REMOVE = re.compile(r'^(?:B_REMOVENPC|B_KILLNPC)\(([A-Z0-9_]+)\)$')
ALIAS = re.compile(r'^([A-Z0-9_]+) = HLP_GETNPC\(([A-Z0-9_]+)\)$')
ONCE = re.compile(r'^\(?ENTER[A-Z]*_KAPITEL\d+ == FALSE\)?$')  # "run this chapter block only once" is no condition
CALL = re.compile(r'^([A-Z0-9_]+)\(\)$')


def _number(token, symbols):
    """The decompiler prints an integer that equals a symbol's index as that symbol's name; undo that."""
    token = token.strip()
    sign = -1 if token.startswith("-") else 1
    token = token.lstrip("-")
    return sign * (int(token) if token.isdigit() else symbols[token])


def read_maps(program, index):
    """Every map item: its texture, its world and the world rectangle it shows."""
    maps = {}
    for symbol in program.symbols:
        if symbol["kind"] != dm.T_FUNC or not symbol["address"] or symbol["flags"] & 8:
            continue
        texture = world = coords = None
        for record in program.run(symbol):
            text = record.get("do", "")
            if text.startswith("DOC_SETPAGE("):
                texture = re.search(r'"([^"]+\.TGA)"', text, re.I)
            elif text.startswith("DOC_SETLEVEL("):
                world = re.search(r'"(?:[^"\\]*\\+)?([^"\\]+\.ZEN)"', text, re.I)
            elif text.startswith("DOC_SETLEVELCOORDS("):
                coords = [_number(t, index) for t in text[len("DOC_SETLEVELCOORDS("):-1].split(", ")[1:]]
        if texture and world and coords:
            name = texture[1].upper()
            maps.setdefault(name, {"texture": name, "world": world[1].upper(), "left": coords[0], "top": coords[1],
                                   "right": coords[2], "bottom": coords[3]})
    return sorted(maps.values(), key=lambda m: m["texture"])


def read_npcs(program):
    npcs = {}
    for symbol in program.symbols:
        if symbol["kind"] != dm.T_INSTANCE or dm.root_class(program.symbols, symbol) != "C_NPC" or not symbol["address"]:
            continue
        fields = {}
        for record in program.run(symbol):
            match = re.match(r"^C_NPC\.(NAME|GUILD|ID|VOICE|DAILY_ROUTINE|NPCTYPE) = (.+)$", record.get("set", ""))
            if match:
                fields[match[1].lower()] = match[2].strip('"')
        if fields.get("daily_routine"):  # people; monsters have no routine
            npcs[symbol["name"]] = fields
    return npcs


def read_bodies(program, prefix):
    return {s["name"]: program.run(s) for s in program.symbols
            if s["kind"] == dm.T_FUNC and s["name"].startswith(prefix) and s["address"] and not s["flags"] & 8}


def calls_in(name, bodies_of, seen=None):
    """A script's statements, with those of the STARTUP_ and B_ENTER_ scripts it calls folded in."""
    seen = set() if seen is None else seen
    if name in seen:
        return []
    seen.add(name)
    found = []
    for record in bodies_of(name):
        match = CALL.match(record.get("do", ""))
        if match and match[1].startswith(("STARTUP_", "B_ENTER_")):
            found += calls_in(match[1], bodies_of, seen)
        else:
            found.append(record)
    return found


def read_aliases(program):
    """Scripts mostly name characters by short variables (BENNET), set once from their instances (SLD_809_BENNET)."""
    aliases = {}
    for symbol in program.symbols:
        if symbol["kind"] == dm.T_FUNC and symbol["name"] == "B_INITNPCGLOBALS" and symbol["address"]:
            for record in program.run(symbol):
                match = ALIAS.match(record.get("set", ""))
                if match:
                    aliases[match[1]] = match[2]
    return aliases


def conditions(record):
    return [g for g in record.get("if", []) if not ONCE.match(g)]


def schematic(world, waypoints, width=1024, margin=0.06):
    """A stand-in map for a world the game has no map of: the bounds of its waypoints, drawn from its paths."""
    if not waypoints:
        return None
    xs, zs = [p[0] for p in waypoints.values()], [p[1] for p in waypoints.values()]
    left, right, top, bottom = min(xs), max(xs), max(zs), min(zs)
    pad = max(right - left, top - bottom) * margin
    left, right, top, bottom = left - pad, right + pad, top + pad, bottom - pad
    return {"texture": "WAYNET", "world": world, "left": round(left), "top": round(top), "right": round(right),
            "bottom": round(bottom), "width": width, "height": round(width * (top - bottom) / (right - left)),
            "schematic": True}


def schedule(records, waypoints):
    entries = []
    for record in records:
        match = TA.match(record.get("do", ""))
        if not match:
            continue
        activity, h1, m1, h2, m2, wp = match.groups()
        point = waypoints.get(wp.upper())
        entries.append({"from": int(h1) * 60 + int(m1), "to": int(h2) * 60 + int(m2), "activity": activity[3:],
                        "wp": wp.upper(), "x": point and point[0], "z": point and point[1]})
    return entries


def build(game):
    data = (pathlib.Path(game) / "_work/Data/Scripts/_compiled/GOTHIC.DAT").read_bytes()
    program = qm.Program(data)
    index = {s["name"]: i for i, s in enumerate(program.symbols)}
    by_name = {s["name"]: s for s in program.symbols}

    def bodies_of(name):
        symbol = by_name.get(name)
        return program.run(symbol) if symbol and symbol["address"] else []

    points, edges = {}, {}
    for line in WORLD_DUMP.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry["kind"] == "waypoint":
            points.setdefault(entry["world"], {})[entry["name"].upper()] = (round(entry["x"]), round(entry["z"]))
        elif entry["kind"] == "edge":
            edges.setdefault(entry["world"], []).append([entry["a"].upper(), entry["b"].upper()])

    npcs = read_npcs(program)
    aliases = read_aliases(program)

    def instance_of(name):
        name = aliases.get(name, name)
        return name if name in npcs else None

    routines = read_bodies(program, "RTN_")
    maps = read_maps(program, index)
    worlds = {}
    for world, (startup, chapter_prefix) in WORLDS.items():
        waypoints = points.get(world, {})
        present = {}   # instance → {"chapter", "wp", "conditions"}
        swaps = {}     # instance → {chapter: routine}
        removed = {}   # instance → {"chapter", "conditions"}
        steps = [(1, startup)] + ([(c, f"{chapter_prefix}{c}") for c in CHAPTERS] if chapter_prefix else [])
        for chapter, script in steps:
            for record in calls_in(script, bodies_of):
                text = record.get("do", "")
                inserted, swapped, gone = INSERT.match(text), SWAP.match(text), REMOVE.match(text)
                if inserted and instance_of(inserted[1]) and instance_of(inserted[1]) not in present:
                    present[instance_of(inserted[1])] = {"chapter": chapter, "wp": inserted[2].upper(),
                                                         "conditions": conditions(record)}
                elif swapped and instance_of(swapped[1]):
                    swaps.setdefault(instance_of(swapped[1]), {})[chapter] = swapped[2].upper()
                elif gone and instance_of(gone[1]) and instance_of(gone[1]) not in removed:
                    removed[instance_of(gone[1])] = {"chapter": chapter, "conditions": conditions(record)}
        people = []
        for instance, spawn in sorted(present.items()):
            fields = npcs[instance]
            npc_id = fields.get("id", "")
            start = fields["daily_routine"].upper()
            by_chapter = {}
            leaves = removed.get(instance)
            for chapter in CHAPTERS:
                if chapter < spawn["chapter"]:
                    continue
                if leaves and not leaves["conditions"] and chapter >= leaves["chapter"]:
                    break  # removed for good when the player enters this chapter
                later = [c for c in swaps.get(instance, {}) if c <= chapter]
                by_chapter[chapter] = f"RTN_{swaps[instance][max(later)]}_{npc_id}" if later else start
            used = set(by_chapter.values())
            own = sorted(name for name in routines if name.endswith(f"_{npc_id}") and npc_id)
            people.append({"instance": instance, "name": fields.get("name", instance), "guild": fields.get("guild", ""),
                           "id": npc_id, "voice": fields.get("voice", ""), "type": fields.get("npctype", ""),
                           "spawn": spawn, "routines": by_chapter, "leaves": leaves,
                           "schedules": {name: schedule(routines.get(name, []), waypoints) for name in used},
                           "other_routines": [name for name in own if name not in used]})
        own_maps = [m for m in maps if m["world"] == world]
        stand_in = None if own_maps else schematic(world, waypoints)
        worlds[world] = {"maps": own_maps + ([stand_in] if stand_in else []), "people": people,
                         "waypoints": {name: list(xz) for name, xz in waypoints.items()},
                         "paths": [e for e in edges.get(world, []) if e[0] in waypoints and e[1] in waypoints] if stand_in else []}
    return {"worlds": worlds}


def _png(width, height, rgba):
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    rows = b"".join(b"\0" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def tga_to_png(raw):
    """An uncompressed true-colour TGA, as the game's map pages are, converted to PNG."""
    id_length, colour_map, kind = raw[0], raw[1], raw[2]
    width, height, bits, descriptor = struct.unpack_from("<HHBB", raw, 12)
    if colour_map or kind != 2 or bits not in (24, 32):
        raise ValueError(f"unsupported TGA (type {kind}, {bits} bit)")
    step = bits // 8
    pixels = raw[18 + id_length:18 + id_length + width * height * step]
    rows = [pixels[y * width * step:(y + 1) * width * step] for y in range(height)]
    if not descriptor & 0x20:  # stored bottom row first
        rows.reverse()
    rgba = bytearray()
    for row in rows:
        for i in range(0, len(row), step):
            b, g, r = row[i], row[i + 1], row[i + 2]
            rgba += bytes((r, g, b, row[i + 3] if step == 4 else 255))
    return _png(width, height, bytes(rgba)), width, height


def extract_images(game, maps):
    """Writes each map page as <TEXTURE>.png next to the data and notes its size."""
    index = {}
    for name in TEXTURE_ARCHIVES:
        path = pathlib.Path(game) / "Data" / name
        if path.exists():
            index.update(read_vdf_index(path))
    IMAGES.mkdir(parents=True, exist_ok=True)
    for entry in maps:
        if entry.get("schematic"):
            continue
        found = index.get(entry["texture"])
        if found is None:
            continue
        path, offset, size = found
        with open(path, "rb") as f:
            f.seek(offset)
            png, entry["width"], entry["height"] = tga_to_png(f.read(size))
        entry["image"] = entry["texture"].rsplit(".", 1)[0] + ".png"
        (IMAGES / entry["image"]).write_bytes(png)


def coverage(result):
    placed = missing = 0
    for world in result["worlds"].values():
        for person in world["people"]:
            for entries in person["schedules"].values():
                for entry in entries:
                    placed += entry["x"] is not None
                    missing += entry["x"] is None
    return placed, missing


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    result = build(sys.argv[1])
    extract_images(sys.argv[1], [m for world in result["worlds"].values() for m in world["maps"]])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    placed, missing = coverage(result)
    for name, world in result["worlds"].items():
        print(f"{name}: {len(world['people'])} people, maps: {', '.join(m['texture'] for m in world['maps']) or 'none'}")
    print(f"routine entries placed: {placed}, waypoint not found: {missing}")
    print(OUT)
