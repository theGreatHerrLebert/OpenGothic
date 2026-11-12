"""What the player just did, as the game itself noticed it, for a rule's "on" field.

    {"event": "took_item", "item": "ITMI_GOLD", "seen_by": "VLK_469_HALVOR"}
    {"event": "cast_spell", "target": "VLK_4006_BOTE", "spell": "SPL_FIREBOLT"}
    {"event": "hit", "target": "VLK_432_MOE", "unseen": true}
    {"event": "used_object", "object": "SMOKE_WATERPIPE"}     the hero got up from an object of this scheme
    {"event": "used_object", "near": [9061, 5911, 2]}        ... from the one standing within 2 m of x, z
    {"event": "used_object", "name": "NW_CITY_PIPE_01"}      ... from the one with this name in the world

Events: took_item (picked up from the ground), hit, knocked_down, killed, cast_spell, entered_room, read_item (a letter
opened from the inventory), drew_weapon (fists, blade, bow or spell readied). The player is the
actor. All fields other than "event" are optional. "seen_by" needs that NPC among those who could see it happen; "unseen"
needs nobody to have seen it. `target` may be "PLAYER", for what is done to the hero. `creature` names a story's own
creature (spawn_creature) by its id instead of a target: {"event": "killed", "creature": "white_wolf"}.
"""

import gothic

EVENTS = {"took_item", "hit", "knocked_down", "killed", "cast_spell", "entered_room", "read_item", "drew_weapon",
          "used_object"}
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
    if "creature" in on and (not isinstance(on["creature"], str) or on.get("target")):
        return "creature names a story's own creature by id, instead of a target"
    if "object" in on and (on["event"] != "used_object" or not isinstance(on["object"], str) or not on["object"].strip()):
        return "object names the scheme of a used object, such as a water pipe"
    if "name" in on and (on["event"] != "used_object" or not isinstance(on["name"], str) or not on["name"].strip()):
        return "name is a used object's own name in the world"
    if "near" in on:
        near = on["near"]
        if (on["event"] != "used_object" or not isinstance(near, list) or len(near) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in near) or not 0 < near[2] <= 50):
            return "near is [x, z, metres up to 50] where a used object stands"
    return None


def matches(on, event):
    if event["kind"] != on["event"]:
        return False
    target = on.get("target")
    if event["actor"] != PLAYER and not (target == PLAYER and event["target"] == PLAYER):
        return False
    if target and event["target"].upper() != target.upper():
        return False
    if on.get("creature"):
        from dm import creatures, story
        if not creatures.is_target(on["creature"], story.state(), event):
            return False
    if on.get("item") and event["item"].upper() != on["item"].upper():
        return False
    if on.get("object") and on["object"].upper() not in event["item"].upper():
        return False                     # the scheme of a used object travels in the record's item field
    if on.get("name") and on["name"].upper() != (event.get("object") or "").upper():
        return False
    if on.get("near"):
        x, z, metres = on["near"]
        at = event.get("position")
        if at is None or (at[0] - x) ** 2 + (at[2] - z) ** 2 > (metres * 100) ** 2:   # game units are centimetres
            return False
    if on.get("spell") and event["spell"] != gothic.daedalus.get(on["spell"], -2):
        return False
    witnesses = {w.upper() for w in event["seen_by"]}
    if on.get("unseen") and witnesses:
        return False
    return not on.get("seen_by") or on["seen_by"].upper() in witnesses
