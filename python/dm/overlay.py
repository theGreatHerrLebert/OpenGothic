"""Feeds the DM status into the in-game panel. Alt+O shows or hides it."""

import time

import gothic

from dm import status

POLL_SECONDS = 0.5
_next_poll = 0.0
_shown = None


def _tick(_dt):
    global _next_poll, _shown
    now = time.monotonic()
    if now < _next_poll:
        return
    _next_poll = now + POLL_SECONDS
    raw = status.entry()
    current = None if raw is None else status.describe(raw, time.time())
    if current is not None and raw.get("anchor") and not _near(raw["anchor"]):
        current = None
    if current == _shown:
        return
    _shown = current
    if current is None:
        gothic.overlay.clear()
    else:
        gothic.overlay.set(current[0], current[1])


def _near(anchor):
    """Whether the hero is close to an NPC a story starts with. Unknown counts as far, so nothing leaks."""
    try:
        here = gothic.player.position
        for instance in ([anchor] if isinstance(anchor, str) else anchor):
            npc = gothic.world.find_npc(instance)
            if npc is not None and status.near(here, npc.position):
                return True
    except RuntimeError:
        pass
    return False


def start():
    """Safe to call repeatedly."""
    if getattr(gothic, "_dm_overlay_registered", False):
        return
    # Through the module, so reloading dm.overlay in a running game takes effect.
    gothic.on_tick(lambda dt: __import__("sys").modules["dm.overlay"]._tick(dt))
    gothic._dm_overlay_registered = True
