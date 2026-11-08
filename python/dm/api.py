"""The only game functions the MCP server may call. Runs inside the game.

Each function prints one JSON document, so the server never executes anything
beyond these fixed entry points.
"""

import json

import gothic

from dm import observer, story


def _reply(value):
    print(json.dumps(value, ensure_ascii=False))


def events(n=50):
    _reply(observer.recent(int(n)))


def world():
    hour, minute = gothic.world.time
    _reply({
        "day": gothic.world.day, "hour": hour, "minute": minute,
        "waypoint": gothic.player.waypoint, "room": gothic.player.room,
        "hp": gothic.player.hp,
        "near": [{"instance": n.instance, "name": n.name, "alive": n.alive}
                 for n in gothic.world.npcs_near(2000)],
        "items": gothic.player.items,
    })


def story_state():
    _reply({"state": story.state(), "results": story.results()[-20:],
            "safe_to_remove": sorted(story.SAFE_TO_REMOVE)})


def describe(name):
    kind = gothic.world.instance_kind(name)
    npc = gothic.world.find_npc(name) if kind == "npc" else None
    _reply({"name": name, "kind": kind, "live": npc is not None,
            "display_name": npc.name if npc else None,
            "waypoint_exists": gothic.world.has_waypoint(name)})


def validate(ops):
    try:
        story._story.validate(ops)
        _reply({"ok": True})
    except story.PlanError as err:
        _reply({"ok": False, "error": str(err)})


def submit(reason, ops):
    try:
        story.submit(reason, ops)
        _reply({"ok": True, "queued": True})
    except story.PlanError as err:
        _reply({"ok": False, "error": str(err)})
