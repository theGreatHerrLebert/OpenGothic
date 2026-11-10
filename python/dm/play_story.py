"""Start a story file in the running game. Works on every system, unlike scripts/pyeval.

    python python/dm/play_story.py <story.json>

The game must run with OPENGOTHIC_PY_BRIDGE=1 and a save must be loaded.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bridge  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    story = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    reply = bridge.call("play", story["title"], story["plan"])
    if reply.get("error") or reply.get("ok") is False:
        raise SystemExit("not started: " + str(reply.get("error")))
    print(f"„{story['title']}“ is running. Alt+O shows the game master's panel.")
