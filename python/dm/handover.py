"""Hands items between the hero and a story the way the game does: the item moves, and a short line in the middle of
the screen says so ("10 Gold erhalten"), in the position and font the game's own hand-over routine (B_GiveInvItems)
uses. That routine itself is not called: its message is an AI action that needs a conversation context the story's
Python-driven dialogue does not set up. The engine's own PrintScreen is used instead, with the game's constants
(gothic.daedalus.call cannot call engine externs, only script functions).
"""

import gothic

GOLD = "ITMI_GOLD"
SECONDS = 2


def message(instance, count, given, name):
    """The line the game shows for a hand-over, in its wording pattern. given: the hero hands it over."""
    verb = "gegeben" if given else "erhalten"
    if instance.upper() == GOLD:
        return f"{count} Gold {verb}"
    if count == 1:
        return f"{name} {verb}"
    return f"{count} Gegenstände {verb} ({name})"


def _name(instance):
    """The item's display name, read from the hero's inventory; the instance name if he carries none."""
    wanted = instance.upper()
    try:
        return next((i["name"] for i in gothic.player.items if i["instance"].upper() == wanted), instance)
    except (AttributeError, KeyError, RuntimeError):
        return instance   # only the message needs the name; the hand-over goes on without it


def _announce(text, given):
    d = gothic.daedalus
    try:
        gothic.print_screen(text, -1, d.get("YPOS_ITEMGIVEN" if given else "YPOS_ITEMTAKEN"),
                            d.get("FONT_SCREENSMALL"), SECONDS)
    except Exception:
        pass   # the item has moved; a missing message must not break the story


def give(instance, count=1):
    """The hero receives something."""
    gothic.player.give_item(instance, count)
    _announce(message(instance, count, False, _name(instance)), False)


def take(instance, count=1):
    """The hero hands something over."""
    name = _name(instance)   # read before it leaves the inventory
    gothic.player.remove_item(instance, count)
    _announce(message(instance, count, True, name), True)
