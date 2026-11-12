"""Start a story file in the running game. Works on every system, unlike scripts/pyeval.

    python python/dm/play_story.py <story.json>

The game must run with OPENGOTHIC_PY_BRIDGE=1 and a save must be loaded. A story whose "requires" checks do not
hold in that save (an earlier chapter, too low a level, ...) is not started.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bridge  # noqa: E402


# Keys whose values name flags, wherever they appear in a plan: rules wait on "when", topics and scenes on "requires",
# anything may be barred by "unless", a dialogue node "sets" flags, a line's variant waits on "when".
FLAG_KEYS = ("when", "requires", "unless", "sets")
# Flags the runtime sets itself for every story (the hero's guild): shared on purpose, never prefixed.
SHARED_FLAGS = {"hero_mage"}


def namespaced(ops, prefix):
    """A plan's operations with every fact, scene and rule id prefixed, and every flag, so stories played in one game
    cannot collide: two stories may both call their hidden truth "truth", and both wait for "blend_mixed". The
    runtime's own follow-ups are built from the stored ids, so they stay consistent; flags the runtime sets for all
    stories stay shared."""
    def flag(name):
        if not isinstance(name, str) or ":" in name or name in SHARED_FLAGS:
            return name
        return f"{prefix}:{name}"

    def flags(value):
        return [flag(v) for v in value] if isinstance(value, list) else flag(value)

    def walk(value, top=False):
        if isinstance(value, list):
            return [walk(v, top) for v in value]
        if not isinstance(value, dict):
            return value
        out = {}
        for key, item in value.items():
            if key in FLAG_KEYS:
                out[key] = flags(item)
            elif key == "name" and value.get("op") == "set_flag":
                out[key] = flag(item)
            elif key == "id" and top:
                out[key] = f"{prefix}:{item}"
            elif key == "creature" and isinstance(item, str) and ":" not in item:
                out[key] = f"{prefix}:{item}"   # a check or perception naming the story's own creature
            elif key == "type" and item == "story_age" and "story" not in value:
                out[key], out["story"] = item, prefix   # "days since this story began" names its own story
            elif key == "ops":
                out[key] = [walk(o, True) for o in item]
            else:
                out[key] = walk(item)
        return out
    return [walk(op, True) for op in ops]


# Operations whose NPC belongs to a story's cast: if one of them dies, the story cannot go on as written.
CAST_FIELDS = {"attach_dialogue_graph": "npc", "add_scene": "npc", "add_topic": "npc", "send_npc": "instance",
               "rename_npc": "instance", "spawn_npc": "instance", "relocate_npc": "instance", "return_npc": "instance"}


def closures(story, prefix):
    """A story's closures as rules: each is a rule whose operations end with the story's quiet ending.

        "closures": [{"id": "too_late", "outcome": "timeout", "checks": [{"type": "story_age", "days": 5}],
                      "ops": [{"op": "narrate", "text": "..."}]}]

    A closure may carry everything a rule carries ("when", "unless", "checks", "on")."""
    rules = []
    for closure in story.get("closures") or []:
        rule = {k: v for k, v in closure.items() if k not in ("outcome",)}
        rule["op"] = "add_rule"
        rule.setdefault("when", [])
        rule["ops"] = list(closure.get("ops", [])) + [
            {"op": "end_story", "story": prefix, "outcome": closure.get("outcome") or closure.get("id", "closed")}]
        rules.append(rule)
    return rules


def cast(ops):
    found = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        field = CAST_FIELDS.get(op.get("op"))
        if field and isinstance(op.get(field), str) and op[field].upper() not in found:
            found.append(op[field].upper())
        for nested in op.get("ops", []) if isinstance(op.get("ops"), list) else []:
            for name in cast([nested]):
                if name not in found:
                    found.append(name)
    return found


def prepare(story, prefix):
    """What the game is sent to start a story: its plan and closures, every id under the story's own prefix, and the
    cast whose death ends it. The game adds the day it begins (dm.api.play)."""
    plan = list(story["plan"]) + closures(story, prefix)
    return {"story": prefix, "title": story["title"], "ops": namespaced(plan, prefix), "cast": cast(plan),
            "requires": story.get("requires") or [], "written_for": story.get("written_for")}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = pathlib.Path(sys.argv[1])
    story = json.loads(path.read_text(encoding="utf-8"))
    start = prepare(story, path.stem)
    reply = bridge.call("play", start["title"], start["ops"], start["requires"], start["story"], start["cast"],
                        start["written_for"])
    if reply.get("error") or reply.get("ok") is False:
        raise SystemExit("not started: " + str(reply.get("error")))
    print(f"„{story['title']}“ is running. Alt+O shows the game master's panel.")
