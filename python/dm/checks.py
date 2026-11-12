"""Typed conditions on the live game, usable on scenes, rules and dialogue choices.

    {"type": "has_item", "item": "ITMI_GOLD", "count": 50}     hero carries at least this many
    {"type": "wears", "item": "ITAR_BAU_L"}                    hero's equipped armour
    {"type": "guild", "guild": "GIL_NOV"}                      hero's guild
    {"type": "npc_state", "npc": "X", "state": "ZS_MAGICBURN"} what an NPC is doing right now
    {"type": "npc_dead", "npc": "X"}
    {"type": "obsessed"}                                       the game's own obsession flag on the hero
    {"type": "hour", "from": 21, "to": 5}                      wraps past midnight
    {"type": "quest", "quest": "MIS_LOBART_RUEBEN", "state": "success"}   the game's own quest state
    {"type": "heard", "info": "DIA_ABUYIN_DU"}                 the hero has heard this topic of the game's own
    {"type": "chapter", "from": 2, "to": 3}                    the game's chapter (KAPITEL), both ends included
    {"type": "level", "min": 5, "max": 12}                     the hero's level, both ends included
    {"type": "day", "from": 3, "to": 6}                        the game's day counter (0 on the first day), included
    {"type": "not", "check": {...}}
    {"type": "any", "checks": [{...}, ...]}                    at least one holds

For chapter, level and day either end may be left out: {"type": "chapter", "from": 3} holds from chapter 3 on.

A quest state is "open" (never given), "running", "success", "failed" or "obsolete", read from the game's MIS_
variable, so a story can follow what the hero has really done in the original game.

Flags say what the story remembers. Checks say what is true in the game right now. All of them must hold.
"""

import gothic

# States a story may react to. Each is a real ZS_ function in the game's scripts.
STATES = {"ZS_MAGICBURN", "ZS_MAGICBURNSHORT", "ZS_MAGICSLEEP", "ZS_MAGICFREEZE", "ZS_MAGICSHRINK", "ZS_MAGICSHRUNK",
          "ZS_MAGICFLEE", "ZS_WHIRLWIND", "ZS_SUCKENERGY", "ZS_UNCONSCIOUS", "ZS_DEAD", "ZS_FLEE", "ZS_DANCE", "ZS_SLEEP",
          "ZS_PRAY_INNOS", "ZS_STAND_DEMENTOR", "ZS_SMOKE_WATERPIPE", "ZS_STAND_DRINKING"}
QUEST_STATES = {"open": None, "running": "LOG_RUNNING", "success": "LOG_SUCCESS", "failed": "LOG_FAILED",
                "obsolete": "LOG_OBSOLETE"}
_REQUIRED = {"has_item": ("item",), "wears": ("item",), "guild": ("guild",), "npc_state": ("npc", "state"), "npc_dead": ("npc",),
             "obsessed": (), "hour": ("from", "to"), "not": ("check",),
             "quest": ("quest", "state"), "any": ("checks",), "heard": ("info",),
             "chapter": (), "level": (), "day": ()}
# Range checks: which two fields bound them, and the smallest sensible value.
RANGES = {"chapter": ("from", "to", 1, 7), "level": ("min", "max", 0, 100), "day": ("from", "to", 0, 100000)}


def validate(check):
    """Returns a description of the first problem, or None."""
    kind = check.get("type") if isinstance(check, dict) else None
    if kind not in _REQUIRED:
        return f"unknown check: {kind}"
    for field in _REQUIRED[kind]:
        if field not in check:
            return f"check {kind} needs {field}"
    if kind in ("has_item", "wears") and gothic.world.instance_kind(check["item"]) != "item":
        return f"not an item instance: {check['item']}"
    if kind == "guild" and not str(check["guild"]).startswith("GIL_"):
        return f"not a guild: {check['guild']}"
    if kind in ("npc_state", "npc_dead") and gothic.world.instance_kind(check["npc"]) != "npc":
        return f"not an NPC: {check['npc']}"
    if kind == "npc_state" and check["state"] not in STATES:
        return f"state cannot be checked: {check['state']}"
    if kind == "hour" and not (0 <= check["from"] <= 23 and 0 <= check["to"] <= 23):
        return "hour out of range"
    if kind in RANGES:
        low_key, high_key, smallest, largest = RANGES[kind]
        low, high = check.get(low_key), check.get(high_key)
        if low is None and high is None:
            return f"check {kind} needs {low_key} or {high_key}"
        for value in (low, high):
            if value is not None and (type(value) is not int or not smallest <= value <= largest):
                return f"{kind} out of range: {value}"
        if low is not None and high is not None and low > high:
            return f"{kind}: {low_key} is after {high_key}"
    if kind == "quest":
        if not str(check["quest"]).upper().startswith("MIS_"):
            return f"not a quest variable: {check['quest']}"
        if check["state"] not in QUEST_STATES:
            return f"unknown quest state: {check['state']}"
        if _known_quest(check["quest"]) is False:
            return f"no such quest in this game: {check['quest']}"
    if kind == "heard":
        if not isinstance(check["info"], str) or not check["info"].upper().startswith("DIA_"):
            return f"not a dialogue topic: {check['info']}"
        if _known_topic(check["info"]) is False:
            return f"no such dialogue topic in this game: {check['info']}"
    if kind == "not":
        return validate(check["check"])
    if kind == "any":
        if not isinstance(check["checks"], list) or not check["checks"]:
            return "any needs a list of checks"
        return validate_all(check["checks"])
    return None


def _known_topic(name):
    """True or False in a running game; None offline, where the game's topics cannot be looked up."""
    heard = getattr(getattr(gothic, "player", None), "heard", None)
    if heard is None:
        return None
    try:
        heard(name.upper())
        return True
    except (ValueError, RuntimeError):
        return False


def _known_quest(name):
    """True or False in a running game; None offline, where the game's variables cannot be read."""
    daedalus = getattr(gothic, "daedalus", None)
    if daedalus is None:
        return None
    try:
        daedalus.get(name.upper())
        return True
    except (RuntimeError, KeyError):
        return False


def validate_all(checks):
    for check in checks or []:
        problem = validate(check)
        if problem:
            return problem
    return None


def _validate_transfer(transfer):
    if not isinstance(transfer, dict) or "item" not in transfer:
        return "takes and gives need an item"
    if gothic.world.instance_kind(transfer["item"]) != "item":
        return f"not an item instance: {transfer['item']}"
    count = transfer.get("count", 1)
    if type(count) is not int or not 0 < count <= 100000:  # the engine call takes an int, and fails after the other half ran
        return "count must be a positive whole number"
    return None


def validate_graph(graph):
    for key, node in graph["nodes"].items():
        for choice in node.get("choices", []):
            problem = validate_all(choice.get("checks"))
            for field in ("takes", "gives"):
                if choice.get(field) is not None:
                    problem = problem or _validate_transfer(choice[field])
            if problem:
                return f"{key}: {problem}"
    return None


def can_pay(choice):
    """A line that hands something over only appears while the hero actually carries it."""
    takes = choice.get("takes")
    return takes is None or _holds({"type": "has_item", "item": takes["item"], "count": takes.get("count", 1)})


def transfer(choice):
    from dm import handover
    takes, gives = choice.get("takes"), choice.get("gives")
    if takes:
        handover.take(takes["item"], takes.get("count", 1))
    if gives:
        handover.give(gives["item"], gives.get("count", 1))


def _holds(check):
    kind = check["type"]
    if kind == "has_item":
        wanted = check["item"].upper()
        return sum(i["count"] for i in gothic.player.items if i["instance"].upper() == wanted) >= check.get("count", 1)
    if kind == "wears":
        return (gothic.player.armor or "").upper() == check["item"].upper()
    if kind == "guild":
        return gothic.player.guild == gothic.daedalus.get(check["guild"], 0)
    if kind == "npc_state":
        npc = gothic.world.find_npc(check["npc"])
        return npc is not None and npc.in_state(check["state"])
    if kind == "npc_dead":
        npc = gothic.world.find_npc(check["npc"])
        return npc is not None and npc.dead
    if kind == "obsessed":
        return bool(gothic.daedalus.get("SC_ISOBSESSED", 0))
    if kind == "hour":
        hour, _ = gothic.world.time
        start, end = check["from"], check["to"]
        return start <= hour < end if start <= end else hour >= start or hour < end
    if kind == "quest":
        value = gothic.daedalus.get(check["quest"].upper(), 0)
        constant = QUEST_STATES[check["state"]]
        return value == (0 if constant is None else gothic.daedalus.get(constant, 0))
    if kind in RANGES:
        low_key, high_key, _, _ = RANGES[kind]
        value = _current(kind)
        return check.get(low_key, value) <= value <= check.get(high_key, value)
    if kind == "any":
        return any(_holds(c) for c in check["checks"])
    if kind == "heard":
        return bool(gothic.player.heard(check["info"].upper()))
    return not _holds(check["check"])


def _current(kind):
    if kind == "chapter":
        return int(gothic.daedalus.get("KAPITEL", 0))
    if kind == "level":
        return int(gothic.player.level)
    return int(gothic.world.day)


def failing(checks):
    """The first check that does not hold right now, or None."""
    for check in checks or []:
        if not _holds(check):
            return check
    return None


def all_hold(checks):
    return all(_holds(c) for c in checks or [])
