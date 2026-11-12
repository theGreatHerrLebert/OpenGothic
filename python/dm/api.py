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
        # Where this snapshot stands in the game's timelines: a story written from it is bound to it (see play).
        "written_for": {"timeline": observer._observer.timeline, "seq": observer._observer.seq},
        "near": [{"instance": n.instance, "name": n.name, "alive": n.alive}
                 for n in gothic.world.npcs_near(2000)],
        "items": gothic.player.items,
    })


def story_state():
    _reply({"state": story.state(), "results": story.results()[-20:],
            "safe_to_remove": sorted(story.SAFE_TO_REMOVE)})


def health():
    """Each story's progress without spoilers: whether it is running or how it ended, its age, its rules' counts."""
    _reply(story._story.health())


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


def _stale(written_for):
    """Why a story written from a snapshot no longer fits the game played now, or None. The game has gone back to a
    save from before the snapshot: the deeds the story grew out of may never have happened in this timeline."""
    if not written_for:
        return None
    chain = observer._observer.branch()
    timeline, seq = written_for.get("timeline"), written_for.get("seq", 0)
    if timeline not in chain:
        return "written for another timeline: a save was loaded that does not lead to the moment it was written for"
    limit = chain[timeline]
    if limit is not None and seq > limit:
        return "written for a later moment than the save that was loaded"
    return None


def play(reason, ops, requires=None, story_id=None, cast=None, written_for=None):
    """Start the game master if it is not running yet, then queue a whole story. A story's "requires" checks must
    hold in this game right now (chapter, level, guild, a quest the hero finished, ...), or it is not started."""
    from dm import checks
    stale = _stale(written_for)
    if stale:
        _reply({"ok": False, "error": "stale: " + stale})
        return
    problem = checks.validate_all(requires)
    if problem:
        _reply({"ok": False, "error": f"bad requirement: {problem}"})
        return
    unmet = checks.failing(requires)
    if unmet is not None:
        _reply({"ok": False, "error": "not yet: " + json.dumps(unmet, ensure_ascii=False), "unmet": unmet})
        return
    if story_id:
        # The story as a whole: from today, with the cast whose death ends it (see story._tick_cast).
        ops = [{"op": "begin_story", "story": story_id, "title": reason, "day": gothic.world.day,
                "cast": list(cast or [])}] + list(ops)
    import dm
    dm.start()
    submit(reason, ops)


def play_demo():
    """The demo story, built here: its theft waits for the first night after today, which only the game knows."""
    from dm.stories import tilo
    play("Der Fall Tilo", tilo.plan(start_day=gothic.world.day))
