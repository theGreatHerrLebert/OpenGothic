"""Start a story file in the running game. Works on every system, unlike scripts/pyeval.

    python python/dm/play_story.py <story.json>

The game must run with OPENGOTHIC_PY_BRIDGE=1 and a save must be loaded.
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
            elif key == "ops":
                out[key] = [walk(o, True) for o in item]
            else:
                out[key] = walk(item)
        return out
    return [walk(op, True) for op in ops]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = pathlib.Path(sys.argv[1])
    story = json.loads(path.read_text(encoding="utf-8"))
    reply = bridge.call("play", story["title"], namespaced(story["plan"], path.stem))
    if reply.get("error") or reply.get("ok") is False:
        raise SystemExit("not started: " + str(reply.get("error")))
    print(f"„{story['title']}“ is running. Alt+O shows the game master's panel.")
