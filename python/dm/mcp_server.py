"""MCP server through which a Director reads the game and submits story plans.

Run with the dm_runtime/mcp virtualenv. The game must be started with
OPENGOTHIC_PY_BRIDGE=1 for live tools; plot checking works without it.
"""

import json
import os
import pathlib
import sys
import time
import uuid

from mcp.server.mcpserver import MCPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import knowledge  # noqa: E402
import status  # noqa: E402

BRIDGE = pathlib.Path(os.environ.get("OPENGOTHIC_PY_BRIDGE_DIR",
                                     f"/tmp/opengothic-{os.environ.get('USER', 'user')}-bridge"))
CHARACTERS = pathlib.Path(__file__).resolve().parent / "characters"
TIMEOUT_S = 10

mcp = MCPServer("gothic")


def _call(function, *args):
    """Invoke one fixed function of dm.api in the running game."""
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


@mcp.tool()
def get_recent_events(count: int = 50) -> str:
    """Recent player activity: places, conversations, items, NPCs nearby."""
    return json.dumps(_call("events", count), ensure_ascii=False)


@mcp.tool()
def get_world() -> str:
    """Current time, player location and inventory, and who is nearby."""
    return json.dumps(_call("world"), ensure_ascii=False)


@mcp.tool()
def get_story_state() -> str:
    """Committed facts, flags, removed NPCs, active dialogues and plan results."""
    return json.dumps(_call("story_state"), ensure_ascii=False)


@mcp.tool()
def describe_name(name: str) -> str:
    """Whether a name is an NPC instance, item instance or waypoint in the game."""
    return json.dumps(_call("describe", name), ensure_ascii=False)


@mcp.tool()
def get_character(name: str) -> str:
    """A character sheet by name, for example tilo or harek."""
    path = CHARACTERS / f"{pathlib.Path(name).name.lower()}.json"
    return path.read_text(encoding="utf-8") if path.exists() else json.dumps({"error": "no such character"})


@mcp.tool()
def list_characters() -> str:
    """Names of the available character sheets."""
    return json.dumps(sorted(p.stem for p in CHARACTERS.glob("*.json")))


@mcp.tool()
def check_plot(plot: dict, conversations: dict) -> str:
    """Prove a plot is solvable and its dialogue consistent. Returns errors and warnings."""
    errors, warnings = knowledge.check(plot, conversations)
    return json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False)


@mcp.tool()
def validate_plan(ops: list) -> str:
    """Check story operations against the game without applying them."""
    return json.dumps(_call("validate", ops), ensure_ascii=False)


@mcp.tool()
def submit_plan(reason: str, ops: list) -> str:
    """Queue validated story operations. They apply together, or not at all, at a safe moment."""
    return json.dumps(_call("submit", reason, ops), ensure_ascii=False)


@mcp.tool()
def report_status(stage: str, done: int | None = None, total: int | None = None, quest: str | None = None) -> str:
    """Show what the DM is doing on the in-game panel. Stage is schreibt, prüft, Stimmen or bereit; counts and quest title are optional.

    Works without the game. The panel clears itself after two minutes without a new report.
    """
    try:
        status.report(stage, done, total, quest)
    except ValueError as error:
        return json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False)
    return json.dumps({"ok": True, "panel": status.read()}, ensure_ascii=False)


@mcp.tool()
def clear_status() -> str:
    """Hide the in-game DM panel."""
    status.clear()
    return json.dumps({"ok": True})


if __name__ == "__main__":
    mcp.run()
