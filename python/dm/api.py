"""The only game functions the MCP server may call. Runs inside the game.

Each function prints one JSON document, so the server never executes anything
beyond these fixed entry points.
"""

import json

import gothic

from dm import observer, story


GUILDS = ("GIL_NONE", "GIL_VLK", "GIL_NOV", "GIL_KDF", "GIL_MIL", "GIL_PAL", "GIL_SLD", "GIL_BAU", "GIL_DJG", "GIL_BDT", "GIL_PIR")


def _reply(value):
    print(json.dumps(value, ensure_ascii=False))


def _guild_name(guild):
    for name in GUILDS:
        if gothic.daedalus.get(name, 0) == guild:
            return name
    return str(guild)


def events(n=50):
    _reply(observer.recent(int(n)))


def world():
    hour, minute = gothic.world.time
    _reply({
        "day": gothic.world.day, "hour": hour, "minute": minute,
        "waypoint": gothic.player.waypoint, "room": gothic.player.room,
        "hp": gothic.player.hp,
        "guild": _guild_name(gothic.player.guild),
        "level": gothic.player.level,
        "chapter": gothic.daedalus.get("KAPITEL", 0),
        "quests": {topic: len(entries) for topic, entries in gothic.journal_entries().items()},
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


def play(reason, ops):
    """Start the game master if it is not running yet, then queue a whole story."""
    import dm
    dm.start()
    submit(reason, ops)
