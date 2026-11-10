"""Calls into the running game through the file bridge (start the game with OPENGOTHIC_PY_BRIDGE=1).

Only the fixed functions of dm.api can be called, so a caller never runs arbitrary code in the game.
"""

import json
import os
import pathlib
import time
import uuid

# Same rule as the game (common/script/pybridge.cpp): Windows has no USER, so both sides fall back to "anon".
BRIDGE = pathlib.Path(os.environ.get("OPENGOTHIC_PY_BRIDGE_DIR")
                      or f"/tmp/opengothic-{os.environ.get('USER') or 'anon'}-bridge")
TIMEOUT_S = 10


def call(function, *args):
    """Invoke one function of dm.api in the running game and return its JSON reply."""
    if not (BRIDGE / "in").is_dir():
        return {"error": "game is not running with OPENGOTHIC_PY_BRIDGE=1"}
    arguments = ", ".join(repr(a) for a in args)
    source = f"import dm.api\ndm.api.{function}({arguments})"
    name = uuid.uuid4().hex
    temporary = BRIDGE / "in" / f"{name}.py.tmp"
    temporary.write_text(source, encoding="utf-8")
    temporary.rename(BRIDGE / "in" / f"{name}.py")
    reply = BRIDGE / "out" / f"{name}.out"
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        if reply.exists():
            status, _, body = reply.read_text(encoding="utf-8").partition("\n")
            reply.unlink()
            if status != "OK":
                return {"error": body.strip()}
            lines = body.strip().splitlines()
            return json.loads(lines[-1]) if lines else {"error": "empty reply"}
        time.sleep(0.05)
    return {"error": "timed out; the game may be paused or in a menu"}
