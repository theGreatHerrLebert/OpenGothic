"""Summer in the world (docs/plan-weather.md, Heat): on a hot day the cicadas saw away in the sun; on the warm night
after it, under a clear sky, the crickets sing and the Milky Way stands over the land as in the trips, without their
colour or nebulae.

Nothing to call: it looks every few seconds at the weather and the hour. The sounds are CC0 recordings from Freesound,
looped (python/dm_runtime/assets/sounds, see CREDITS.md there); without them it stays silent. A trip owns the sky while
it runs; the sounds keep following the weather."""

import pathlib
import sys

SOUNDS = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "assets" / "sounds"
HOT = 0.3          # heat from which a day or night counts as hot, full from 0.6
CLEAR = 0.15       # overcast above which the stars are hidden
GALAXY = 0.43      # how much the Milky Way replaces the night sky at most
TINT = (1.0, 0.95, 0.86)   # a little warm, not the trip's colours
SPIN = 0.002       # radians a second: the stars turn slowly
CICADAS, CRICKETS = 0.35, 0.35   # loudest volume of each
LOOK = 2.0         # seconds between looks


def ramp(h, up_from, up_to, down_from, down_to):
    """0..1 over a day: rising from up_from to up_to, full until down_from, gone at down_to (hours, may wrap)."""
    def inside(a, b):
        return (a <= h < b) if a <= b else (h >= a or h < b)
    if inside(up_to, down_from):
        return 1.0
    if inside(up_from, up_to):
        return ((h - up_from) % 24) / ((up_to - up_from) % 24)
    if inside(down_from, down_to):
        return 1.0 - ((h - down_from) % 24) / ((down_to - down_from) % 24)
    return 0.0


def levels(state, hour, minute):
    """(cicadas, crickets and stars) now, each 0..1."""
    h = hour + minute / 60.0
    warm = min(1.0, max(0.0, (state.get("heat", 0.0) - HOT) / (0.6 - HOT)))
    if state.get("falling", 0.0) > 0.01:
        return 0.0, 0.0
    day = ramp(h, 8.5, 10.5, 17.5, 19.5) * (1.0 if state.get("overcast", 0.0) < 0.5 else 0.0)
    night = ramp(h, 20.5, 22.0, 4.0, 5.5) * (1.0 if state.get("overcast", 0.0) <= CLEAR else 0.0)
    return round(warm * day, 2), round(warm * night, 2)


_shown = {"world": None, "cicadas": None, "crickets": None, "galaxy": None, "since": None}


def _loop(gothic, name, file, level, volume):
    if level == _shown[name]:
        return
    path = SOUNDS / file
    if path.is_file():
        gothic.weather.loop(name, str(path), level * volume, 20.0)
    _shown[name] = level


def tick(gothic, now):
    if not hasattr(gothic, "weather") or not hasattr(gothic.weather, "loop"):
        return None
    world = getattr(gothic.world, "generation", None)
    if world != _shown["world"]:   # a load or a new world: its engine starts silent, with the game's own sky
        _shown.update(world=world, cicadas=None, crickets=None, galaxy=None, since=None)
    hour, minute = gothic.world.time
    day, night = levels(gothic.weather.state(), hour, minute)
    _loop(gothic, "cicadas", "zikaden.wav", day, CICADAS)
    _loop(gothic, "crickets", "grillen.wav", night, CRICKETS)
    trip = sys.modules.get("dm.trip")
    if not hasattr(gothic, "sky") or (trip is not None and getattr(trip, "_current", None) is not None):
        _shown["galaxy"] = None   # the trip has the sky; afterwards it is set again
        return day, night
    if night <= 0.0:
        if _shown["galaxy"]:
            gothic.sky.clear()
        _shown.update(galaxy=0.0, since=None)
        return day, night
    if _shown["since"] is None:
        _shown["since"] = now
    from dm import trip as trips
    if trips._load_sky(gothic, 0, "milkyway.jpg"):   # the image lives in dm_runtime/sky
        amount = round(night * GALAXY, 2)
        t = now - _shown["since"]
        gothic.sky.galaxy(amount, 1.0, TINT, 0.2, t * SPIN, 0.0, [], 0.0, t, 0.0)
        _shown["galaxy"] = amount
    return day, night


_next_look = 0.0


def _tick(_dt):
    global _next_look
    import time
    import gothic
    now = time.monotonic()
    if now < _next_look:
        return
    _next_look = now + LOOK
    try:
        gothic.world.day
    except RuntimeError:
        return
    tick(gothic, now)


def start():
    import gothic
    if getattr(gothic, "_dm_summer_registered", False):
        return
    gothic.on_tick(lambda dt: sys.modules["dm.summer"]._tick(dt))
    gothic._dm_summer_registered = True
