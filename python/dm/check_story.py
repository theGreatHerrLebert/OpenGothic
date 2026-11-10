"""Checks a story written for the experiment, against the real names of the game.

    python3 python/dm/check_story.py <story.json> <world_names.json>

A story file holds "title", "hidden_truth", "plot", "conversations" and "plan". Prints a JSON report.
"""

import json
import pathlib
import re
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
gothic = types.ModuleType("gothic")
sys.modules["gothic"] = gothic

from dm import graph, knowledge, story  # noqa: E402

STAGE_DIRECTION = re.compile(r"\([^)]*\)|\*[^*]+\*")


def _spawned(ops):
    """NPCs a plan creates itself. Who is already placed in the world is unknown offline."""
    found = set()
    for op in ops:
        if op.get("op") == "spawn_npc":
            found.add(str(op.get("instance", "")).upper())
        found |= _spawned(op.get("ops", []))
    return found


DEED_CHECKS = {"npc_state", "npc_dead", "hour", "has_item", "wears", "obsessed"}


def deeds(data):
    """What in a story the player does with their hands rather than their mouth: rules that react to an action
    (`on`), and conditions on the state of the world. Guild and conversation flags do not count."""
    found = []

    def walk(o, where):
        if isinstance(o, dict):
            where = o.get("id", where)
            if isinstance(o.get("on"), dict):
                found.append(f"{where}: {o['on'].get('event')}")
            for check in o.get("checks") or []:
                if isinstance(check, dict) and check.get("type") in DEED_CHECKS:
                    found.append(f"{where}: {check['type']}")
            for value in o.values():
                walk(value, where)
        elif isinstance(o, list):
            for value in o:
                walk(value, where)

    walk(data.get("plan", []), "plan")
    walk(data.get("conversations", {}), "conversations")
    return found


def lint(data):
    """Defects no conversation-level check sees: story logic that can never happen, and text that cannot be spoken."""
    errors, warnings = [], []
    written, needed, blocked = set(story.HERO_GUILD_FLAGS), {}, {}

    def walk(o, where):
        if isinstance(o, dict):
            if o.get("op") == "set_flag":
                written.add(o.get("flag") or o.get("name"))
            for key, into in (("requires", needed), ("when", needed), ("unless", blocked)):
                value = o.get(key)
                for flag in [value] if isinstance(value, str) else value if isinstance(value, list) else []:
                    into.setdefault(flag, where)
            for key, value in o.items():
                if key == "sets":
                    written.update([value] if isinstance(value, str) else value)
                walk(value, o.get("id", where))
        elif isinstance(o, list):
            for value in o:
                walk(value, where)

    walk(data["conversations"], "conversations")
    walk(data["plan"], "plan")
    for flag, where in needed.items():
        if flag not in written and not flag.startswith("asked:"):  # the dialogue player writes these itself
            errors.append(f"flag is needed but never set: {flag} ({where})")
    for flag, where in blocked.items():
        if flag not in written:
            warnings.append(f"flag blocks something but is never set: {flag} ({where})")

    for name, conversation in data["conversations"].items():
        nodes = conversation["nodes"]
        seen, frontier = {conversation["start"]}, [conversation["start"]]
        while frontier:
            node = nodes[frontier.pop()]
            for target in [node.get("returns")] + [c.get("goto") for c in node.get("choices", [])]:
                if target in nodes and target not in seen:
                    seen.add(target)
                    frontier.append(target)
        for key in nodes:
            if key not in seen:
                errors.append(f"{name}: node can never be reached: {key}")
        for key, node in nodes.items():
            texts = [node.get("line", ""), node.get("again", "")] + [v["line"] for v in node.get("variants", [])] + [c["text"] for c in node.get("choices", [])]
            for text in texts:
                if STAGE_DIRECTION.search(text):
                    errors.append(f"{name}.{key}: stage direction would be read aloud: {text[:50]}")
    if not deeds(data):
        warnings.append("no deed: every way through this story is talking; see 'Deeds, not only words' in "
                        "docs/director-brief.md")
    return errors, warnings


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
    data = path if isinstance(path, dict) else json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
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
    lint_errors, lint_warnings = lint(data)
    errors += lint_errors
    warnings += lint_warnings

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
