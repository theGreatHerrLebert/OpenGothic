"""Reusable helpers for the OpenGothic Python REPL.

Edit this file in your normal editor (VS Code, etc.), save, then reload
without restarting the game:

    py gothic.reload("tools")
    py from tools import *    # re-pull updated names into the REPL

Every helper defined here is available from Marvin (F2) after `init.py`
imports it.
"""

import gothic


def where():
    """Print the player's position and name."""
    p = gothic.player
    x, y, z = p.position
    print(f"{p.name} at ({x:.1f}, {y:.1f}, {z:.1f})")


def living_npcs():
    """Count NPCs currently alive in the active world."""
    return sum(1 for n in gothic.world.npcs if n.alive)


def noon():
    """Jump the in-game clock to 12:00."""
    gothic.world.set_time(12, 0)


def midnight():
    """Jump the in-game clock to 00:00."""
    gothic.world.set_time(0, 0)
