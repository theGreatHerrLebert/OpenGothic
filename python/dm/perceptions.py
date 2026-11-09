"""What the player just did, as the game itself noticed it, for a rule's "on" field.

    {"event": "took_item", "item": "ITMI_GOLD", "seen_by": "VLK_469_HALVOR"}
    {"event": "cast_spell", "target": "VLK_4006_BOTE", "spell": "SPL_FIREBOLT"}
    {"event": "hit", "target": "VLK_432_MOE", "unseen": true}

Events: took_item (picked up from the ground), hit, knocked_down, killed, cast_spell, entered_room, read_item (a letter
opened from the inventory), drew_weapon (fists, blade, bow or spell readied). The player is the
actor. All fields other than "event" are optional. "seen_by" needs that NPC among those who could see it happen; "unseen"
needs nobody to have seen it. `target` may be "PLAYER", for what is done to the hero.
"""

import gothic

EVENTS = {"took_item", "hit", "knocked_down", "killed", "cast_spell", "entered_room", "read_item", "drew_weapon"}
PLAYER = "PLAYER"


def validate(on):
    """Returns a description of the first problem, or None."""
    if on is None:
        return None
    if not isinstance(on, dict) or on.get("event") not in EVENTS:
        return f"unknown event: {on}"
    if on.get("item") and gothic.world.instance_kind(on["item"]) != "item":
        return f"not an item instance: {on['item']}"
    for field in ("target", "seen_by"):
        name = on.get(field)
        if name and name != PLAYER and gothic.world.instance_kind(name) != "npc":
            return f"not an NPC: {name}"
    if on.get("spell") and not str(on["spell"]).startswith("SPL_"):
        return f"not a spell: {on['spell']}"
    if on.get("seen_by") and on.get("unseen"):
        return "seen_by and unseen exclude each other"
    return None


def matches(on, event):
    if event["kind"] != on["event"]:
        return False
    target = on.get("target")
    if event["actor"] != PLAYER and not (target == PLAYER and event["target"] == PLAYER):
        return False
    if target and event["target"].upper() != target.upper():
        return False
    if on.get("item") and event["item"].upper() != on["item"].upper():
        return False
    if on.get("spell") and event["spell"] != gothic.daedalus.get(on["spell"], -2):
        return False
    witnesses = {w.upper() for w in event["seen_by"]}
    if on.get("unseen") and witnesses:
        return False
    return not on.get("seen_by") or on["seen_by"].upper() in witnesses
