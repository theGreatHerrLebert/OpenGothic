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
    if raw and raw.get("anchor") and not raw.get("met") and _talking_to(raw["anchor"]):
        status.mark_met()
        raw = status.entry()
    current = None if raw is None else status.describe(raw, time.time())
    strength = 1.0
    if current is not None and raw.get("anchor"):
        # Steps of a twentieth, so walking does not resend the panel every tick.
        strength = round(_closeness(raw["anchor"]) * 20) / 20
        if strength <= 0:
            current = None
    shown = None if current is None else (current[0], current[1], strength)
    if shown == _shown:
        return
    _shown = shown
    if shown is None:
        gothic.overlay.clear()
    else:
        gothic.overlay.set(*shown)


def _talking_to(anchor):
    """Whether the hero is in a story conversation with one of the story's first people."""
    from dm import story
    player = story._player
    names = [anchor] if isinstance(anchor, str) else anchor
    return player.stage != "idle" and player.partner in names


def _closeness(anchor):
    """How close the hero is to the nearest NPC a story starts with, 0 to 1. Unknown counts as far, so nothing leaks."""
    best = 0.0
    try:
        here = gothic.player.position
        for instance in ([anchor] if isinstance(anchor, str) else anchor):
            npc = gothic.world.find_npc(instance)
            if npc is not None:
                best = max(best, status.closeness(here, npc.position))
    except RuntimeError:
        pass
    return best


def start():
    """Safe to call repeatedly."""
    if getattr(gothic, "_dm_overlay_registered", False):
        return
    # Through the module, so reloading dm.overlay in a running game takes effect.
    gothic.on_tick(lambda dt: __import__("sys").modules["dm.overlay"]._tick(dt))
    gothic._dm_overlay_registered = True
