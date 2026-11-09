"""Checks a story written for the experiment, against the real names of the game.

    python3 python/dm/check_story.py <story.json> <world_names.json>

A story file holds "title", "hidden_truth", "plot", "conversations" and "plan". Prints a JSON report.
"""

import json
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
gothic = types.ModuleType("gothic")
sys.modules["gothic"] = gothic

from dm import graph, knowledge, story  # noqa: E402


def _spawned(ops):
    """NPCs a plan creates itself. Who is already placed in the world is unknown offline."""
    found = set()
    for op in ops:
        if op.get("op") == "spawn_npc":
            found.add(str(op.get("instance", "")).upper())
        found |= _spawned(op.get("ops", []))
    return found


def check(path, names_path):
    names = json.loads(pathlib.Path(names_path).read_text(encoding="utf-8"))
    npcs, items, waypoints = set(names["npcs"]), set(names["items"]), set(names["waypoints"])

    class Npc:
        dead = False

        def __init__(self, instance):
            self.instance = instance

    class World:
        day, time, generation = 0, (8, 0), 1

        def instance_kind(self, name):
            name = name.upper()
            return "npc" if name in npcs else "item" if name in items else None

        def has_waypoint(self, name):
            return name in waypoints

        def find_npc(self, name):
            return Npc(name.upper()) if name.upper() in npcs and name.upper() not in spawned else None

    errors = []
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    spawned = _spawned(data.get("plan", []))
    gothic.world = World()
    for key in ("title", "hidden_truth", "plot", "conversations", "plan"):
        if key not in data:
            errors.append(f"missing field: {key}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": []}

    all_graphs = dict(data["conversations"])
    for name, conversation in all_graphs.items():
        problem = graph.validate(conversation)
        if problem:
            errors.append(f"{name}: {problem}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": []}

    logic_errors, warnings = knowledge.check(data["plot"], data["conversations"])
    errors += logic_errors

    scratch = story.Story()
    try:
        scratch.validate(data["plan"])
    except story.PlanError as error:
        errors.append(f"plan: {error}")
    except (KeyError, TypeError, AttributeError) as error:
        errors.append(f"plan is malformed: {error!r}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


if __name__ == "__main__":
    print(json.dumps(check(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1))
