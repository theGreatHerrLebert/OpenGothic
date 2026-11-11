"""Start a story file in the running game. Works on every system, unlike scripts/pyeval.

    python python/dm/play_story.py <story.json>

The game must run with OPENGOTHIC_PY_BRIDGE=1 and a save must be loaded.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bridge  # noqa: E402


def namespaced(ops, prefix):
    """A plan's operations with every fact, scene and rule id prefixed, so stories played in one game cannot collide:
    two stories may both call their hidden truth "truth". The runtime's own follow-ups are built from the stored ids,
    so they stay consistent. Flags are not touched."""
    def walk(op):
        op = dict(op)
        if "id" in op:
            op["id"] = f"{prefix}:{op['id']}"
        if isinstance(op.get("ops"), list):
            op["ops"] = [walk(o) for o in op["ops"]]
        return op
    return [walk(op) for op in ops]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = pathlib.Path(sys.argv[1])
    story = json.loads(path.read_text(encoding="utf-8"))
    reply = bridge.call("play", story["title"], namespaced(story["plan"], path.stem))
    if reply.get("error") or reply.get("ok") is False:
        raise SystemExit("not started: " + str(reply.get("error")))
    print(f"„{story['title']}“ is running. Alt+O shows the game master's panel.")
