"""Magical weather in the world (docs/plan-weather.md, Fire rain round 2): what a fire rain does where it comes down.

Nothing to call: it looks every second at the weather. While a fire rain falls its roar plays (a CC0 recording of a
big fire, python/dm_runtime/assets/sounds/feuer.wav; without it, silence), and now and then a strike comes down near
the hero: the game's own firestorm blast where it lands (light and sound included, its spell damage switched off), a
fire that burns on there for a while, an orange flash, and wounds for the hero and for animals close by, never fatal.
People are never hurt by it, nor anyone in a dialogue: a story must not break on the weather. The fires are not saved.
"""

import math
import pathlib
import sys

SOUNDS = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "assets" / "sounds"
ROAR = "feuer.wav"
ROAR_VOLUME = 0.7
STRIKE_FROM = 0.3          # a fire rain at least this strong has strikes
STRIKE_GAP = (10.0, 20.0)  # seconds between two strikes at full strength; weaker rain, longer gaps
NEAR, FAR = 800.0, 4500.0  # cm: where strikes land around the hero
CLOSE_CHANCE = 0.15        # of a strike landing nearer, 1.5 to 8 m: close enough to burn him
CLOSEST = 150.0            # cm: never right on him
BLAST = "SPELLFX_FIRESTORM_COLLIDE"
LINGER = "SPELLFX_FIRESTORM_SPREAD"
LINGER_SECONDS = 30.0
RADIUS = 400.0             # cm: who is wounded
WOUND = 40                 # hp at the very centre, less further out
GIL_SEPERATOR_HUM = 16     # guilds above it are animals and monsters
SHELTER = 250.0            # cm: something static this far above someone keeps the fire off him
LOOK = 1.0

_state = {"world": None, "roar": None, "next": None}


def _hurt(who, amount):
    if amount > 0 and hasattr(who, "hurt"):
        return who.hurt(int(amount))
    return 0


def _sheltered(gothic, pos):
    roof = gothic.weather.roof_at(pos[0], pos[2])
    return roof > pos[1] + SHELTER


def target(gothic, rng):
    """Where the next strike lands, (x, y, z) in cm, or None when there is no ground known there."""
    hx, hy, hz = gothic.player.position
    angle = rng.random() * 2 * math.pi
    dist = rng.uniform(CLOSEST, NEAR) if rng.random() < CLOSE_CHANCE else rng.uniform(NEAR, FAR)
    x, z = hx + math.cos(angle) * dist, hz + math.sin(angle) * dist
    y = gothic.weather.roof_at(x, z)
    if y < -1e8 or not hy - 3000.0 < y < hy + 1500.0:   # outside the map, or a cliff far over or under him
        return None
    return x, y, z


def strike(gothic, rng, at=None):
    """One strike: the blast, the fire after it, the flash, the wounds. Returns (where, who was wounded), or None."""
    at = at or target(gothic, rng)
    if at is None:
        return None
    x, y, z = at
    if not gothic.world.play_effect(BLAST, x, y, z):
        return None
    gothic.world.play_effect(LINGER, x, y, z, LINGER_SECONDS)
    hx, hy, hz = gothic.player.position
    near = math.dist((x, y, z), (hx, hy, hz))
    gothic.weather.flash(max(0.25, 1.0 - near / FAR))
    if gothic.dialog.partner() is not None or gothic.dialog.narrating():
        return at, []   # nobody is wounded while someone talks
    wounded = []
    if near < RADIUS and not _sheltered(gothic, (hx, hy, hz)):
        if _hurt(gothic.player, WOUND * (1.0 - near / RADIUS)):
            wounded.append("hero")
    for npc in gothic.world.npcs_near(near + RADIUS):
        if getattr(npc, "guild", 0) <= GIL_SEPERATOR_HUM or not getattr(npc, "alive", True):
            continue   # people are not wounded: a story must not break on the weather
        pos = npc.position
        d = math.dist((x, y, z), pos)
        if d < RADIUS and not _sheltered(gothic, pos) and _hurt(npc, WOUND * (1.0 - d / RADIUS)):
            wounded.append(getattr(npc, "instance", "?"))
    return at, wounded


def tick(gothic, now, rng):
    if not hasattr(gothic, "weather") or not hasattr(gothic.world, "play_effect"):
        return None
    world = getattr(gothic.world, "generation", None)
    if world != _state["world"]:   # a load or a new world: its engine starts silent, and no strike is due
        _state.update(world=world, roar=None, next=None)
    state = gothic.weather.state()
    fire = state.get("falling", 0.0) if state.get("kind") == "fire" else 0.0
    roar = round(fire * ROAR_VOLUME, 2)
    if roar != _state["roar"] and (SOUNDS / ROAR).is_file():
        gothic.weather.loop("fire", str(SOUNDS / ROAR), roar, 8.0)
        _state["roar"] = roar
    if fire < STRIKE_FROM:
        _state["next"] = None
        return None
    if _state["next"] is None:
        _state["next"] = now + rng.uniform(*STRIKE_GAP) / fire * 0.5   # the first one comes sooner
        return None
    if now < _state["next"]:
        return None
    _state["next"] = now + rng.uniform(*STRIKE_GAP) / fire
    done = strike(gothic, rng)
    if done is not None:
        from dm import weather_talk
        weather_talk.flashed(now)
    return done


_next_look = 0.0


def _tick(_dt):
    global _next_look
    import random
    import time
    import gothic
    now = time.monotonic()
    if now < _next_look:
        return
    _next_look = now + LOOK
    try:
        gothic.world.day
        gothic.player.position
    except (RuntimeError, AttributeError):
        return
    tick(gothic, now, random)


def start():
    import gothic
    if getattr(gothic, "_dm_magic_weather_registered", False):
        return
    gothic.on_tick(lambda dt: sys.modules["dm.magic_weather"]._tick(dt))
    gothic._dm_magic_weather_registered = True
