"""Creatures of a story's own: a remix of one of the game's nameless creatures (a wolf, a shadowbeast, a sheep) with its
own name, look, size, strength and loot. The game's other creatures of the same kind stay as they are.

    {"op": "spawn_creature", "id": "white_wolf", "like": "WOLF", "waypoint": "NW_BIGFARM_SHEEP2_04",
     "name": "Weißer Wolf", "look": {"tint": [0.92, 0.96, 1.0], "brighten": 2.2}, "scale": 1.3,
     "hp": 400, "strength": 70, "level": 20, "loot": [{"item": "ITAT_WOLFFUR", "count": 1}]}

look is a recolour of the creature's own fur ({"tint": [r, g, b], "brighten": n}, each channel 0 to 2) or a PNG of the
story's own in dm_runtime/assets/creatures ({"texture": "white_wolf.png"}, laid out like the game's texture). The look
works through the game's body texture variants: the creature wears variant 50 and up, which only it uses.

A story refers to its creature by id: {"type": "npc_dead", "creature": "white_wolf"} in checks, {"event": "killed",
"creature": "white_wolf"} in a rule's "on". The game tells it from others of its kind by kind and name, so each
creature's name is its own.
"""

import pathlib
import re

import gothic

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "assets" / "creatures"
VARIANT_BASE = 50   # the game's own body variants stay below this
MAX_CREATURES = 49  # variants 50 to 99
RANGES = {"hp": (1, 5000), "strength": (0, 500), "dexterity": (0, 500), "level": (0, 100)}

_found = {}         # creature id -> (world generation, Npc) found last


class Problem(ValueError):
    pass


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check(args, state, attachable):
    """Raises Problem with the first thing wrong with a spawn_creature operation."""
    for field in ("id", "like", "waypoint", "name"):
        if field not in args:
            raise Problem(f"missing field: {field}")
    cid = args["id"]
    if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_:]{1,60}", cid):
        raise Problem("a creature id is letters, digits and underscores")
    known = state.get("creatures", {})
    if cid in known:
        raise Problem(f"creature already exists: {cid}")
    if len(known) >= MAX_CREATURES:
        raise Problem("no room for another creature of a story's own")
    like = str(args["like"]).upper()
    if gothic.world.instance_kind(like) != "npc" or like not in attachable:
        raise Problem(f"not a nameless creature a story may remix: {args['like']}")
    if not gothic.world.has_waypoint(args["waypoint"]):
        raise Problem(f"no such waypoint: {args['waypoint']}")
    name = args["name"]
    if not isinstance(name, str) or not 0 < len(name.strip()) <= 40:
        raise Problem("a creature needs a name of up to 40 letters")
    if any(c["name"] == name and c["like"].upper() == like for c in known.values()):
        raise Problem(f"another creature of this kind already has the name {name}")
    if "scale" in args and not (_number(args["scale"]) and 0.3 <= args["scale"] <= 3):
        raise Problem("scale is a number from 0.3 to 3")
    for field, (low, high) in RANGES.items():
        if field in args and (type(args[field]) is not int or not low <= args[field] <= high):
            raise Problem(f"{field} is a whole number from {low} to {high}")
    look = args.get("look")
    if look is not None:
        if not isinstance(look, dict):
            raise Problem("look is a tint or a texture")
        if "texture" in look:
            texture = look["texture"]
            if not isinstance(texture, str) or not texture.lower().endswith(".png") or "/" in texture or "\\" in texture:
                raise Problem("look texture is a .png file name in dm_runtime/assets/creatures")
            if not (ASSETS / texture).exists() and getattr(gothic, "resources", None) is not None:
                raise Problem(f"look texture not in dm_runtime/assets/creatures: {texture}")
        else:
            tint = look.get("tint")
            if (not isinstance(tint, list) or len(tint) != 3 or not all(_number(v) and 0 <= v <= 2 for v in tint)):
                raise Problem("look tint is three numbers from 0 to 2")
            if "brighten" in look and not (_number(look["brighten"]) and 0.2 <= look["brighten"] <= 4):
                raise Problem("look brighten is a number from 0.2 to 4")
    loot = args.get("loot", [])
    if not isinstance(loot, list) or len(loot) > 5:
        raise Problem("loot is a list of up to five items")
    for entry in loot:
        if not isinstance(entry, dict) or gothic.world.instance_kind(str(entry.get("item", ""))) != "item":
            raise Problem(f"loot needs item instances: {entry}")
        count = entry.get("count", 1)
        if type(count) is not int or not 0 < count <= 1000:
            raise Problem("a loot count is a whole number from 1 to 1000")


def fold(args, state):
    known = state.setdefault("creatures", {})
    known[args["id"]] = {"like": args["like"].upper(), "name": args["name"], "look": args.get("look"),
                         "variant": args.get("variant", VARIANT_BASE + len(known))}


def assign_variants(ops, state):
    """Each new creature in a plan gets the next free body variant, written into the operation so a load replays it."""
    taken = {c["variant"] for c in state.get("creatures", {}).values()}
    out = []
    for op in ops:
        if isinstance(op, dict) and op.get("op") == "spawn_creature" and "variant" not in op:
            variant = next((v for v in range(VARIANT_BASE, VARIANT_BASE + MAX_CREATURES + 1) if v not in taken), None)
            if variant is not None:
                op = dict(op, variant=variant)
                taken.add(variant)
        out.append(op)
    return out


def _dress(npc, entry):
    """Registers the creature's own texture for its variant and puts it on. Again after every load, since the
    registration lives only as long as the game runs."""
    look, variant = entry.get("look"), entry["variant"]
    if not look:
        return
    textures = [t for t in gothic.resources.mesh_textures(npc.body_mesh + ".ASC") if "_V0" in t.upper()]
    for texture in textures:
        own = re.sub("_V0", f"_V{variant}", texture.upper(), count=1)
        if "texture" in look:
            path = ASSETS / look["texture"]
        else:
            ASSETS.mkdir(parents=True, exist_ok=True)
            tint = look["tint"]
            stem = re.sub(r"[^a-z0-9]+", "_", f"{entry['like']}_{variant}_{tint}_{look.get('brighten', 1)}".lower())
            path = ASSETS / f"{stem}_{texture.lower().replace('.tga', '')}.png"
            if not path.exists():
                gothic.resources.export_texture(texture, str(path), tuple(tint), 1.0, float(look.get("brighten", 1)))
        gothic.resources.register_texture(own, str(path))
    npc.set_body_texture(variant)


def spawn(args):
    """The world effect: the creature stands at its waypoint, made its own. Returns its undo."""
    npc = gothic.world.spawn(args["like"], args["waypoint"])
    try:
        npc.display_name = args["name"]
        _dress(npc, {"like": args["like"].upper(), "look": args.get("look"), "variant": args["variant"]})
        if "scale" in args:
            npc.set_scale(float(args["scale"]))
        if "hp" in args:
            npc.set_attribute("hp_max", args["hp"])
            npc.set_attribute("hp", args["hp"])
        for field in ("strength", "dexterity"):
            if field in args:
                npc.set_attribute(field, args[field])
        if "level" in args:
            npc.level = args["level"]
        for entry in args.get("loot", []):
            npc.add_item(entry["item"], entry.get("count", 1))
    except Exception:
        gothic.world.remove_npc(npc)
        raise
    _found[args["id"]] = (gothic.world.generation, npc)
    return lambda: gothic.world.remove_npc(npc)


def find(cid, state):
    """The creature in the world now, or None: not spawned yet, or gone. Its body stays findable while it lies dead."""
    entry = state.get("creatures", {}).get(cid)
    if entry is None:
        return None
    generation = gothic.world.generation
    cached = _found.get(cid)
    if cached is not None and cached[0] == generation:
        try:
            if cached[1].display_name == entry["name"]:
                return cached[1]
        except (RuntimeError, ValueError):
            pass
    for npc in gothic.world.npcs:
        try:
            if npc.instance.upper() == entry["like"] and npc.display_name == entry["name"]:
                _found[cid] = (generation, npc)
                return npc
        except (RuntimeError, ValueError):
            continue
    _found.pop(cid, None)
    return None


def rebind(state):
    for cid, entry in state.get("creatures", {}).items():
        npc = find(cid, state)
        if npc is not None:
            _dress(npc, entry)


def is_dead(cid, state):
    """A creature that was spawned and can no longer be found counts as dead; one not spawned yet does not."""
    if cid not in state.get("creatures", {}):
        return False
    npc = find(cid, state)
    return npc is None or npc.dead


def is_target(cid, state, event):
    entry = state.get("creatures", {}).get(cid)
    return (entry is not None and str(event.get("target", "")).upper() == entry["like"]
            and event.get("target_name", "") == entry["name"])
