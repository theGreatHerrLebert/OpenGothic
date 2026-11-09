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
    current = status.read()
    if current == _shown:
        return
    _shown = current
    if current is None:
        gothic.overlay.clear()
    else:
        gothic.overlay.set(current[0], current[1])


def start():
    """Safe to call repeatedly."""
    if getattr(gothic, "_dm_overlay_registered", False):
        return
    gothic.on_tick(_tick)
    gothic._dm_overlay_registered = True
