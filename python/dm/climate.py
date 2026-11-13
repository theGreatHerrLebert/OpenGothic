"""Weather in the world when no story sets it: fronts that come and go, decided by game time alone.

Each block of BLOCK_HOURS in-game hours has its own weather, drawn from a hash of the block's number, so the same
moment always has the same weather: a load agrees without saving anything. Khorinis is mostly clear, sometimes rains,
and never snows by itself; snow comes only from a story (the weather op). A story's weather outranks this until its
`hours` run out. Snow lying on the ground follows the snowfall and melts after it.

Off unless dm_runtime/settings.json has "climate": true, or climate.enable() is called (docs/plan-weather.md).
"""

import hashlib
import json
import pathlib

BLOCK_HOURS = 3
FADE = 90.0            # seconds of game time for a front to come or go
TICK_SECONDS = 2.0     # how often the controller looks (real seconds)
# (kind, intensity, share of blocks)
FRONTS = [("clear", 0.0, 0.66), ("rain", 0.35, 0.22), ("rain", 0.85, 0.12)]
SETTINGS = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "settings.json"

_enabled = None
_last = None
_next_look = 0.0


def front(day, hour):
    """The weather of the block a moment falls in: (kind, intensity, wind (x, z) in m/s)."""
    block = (day * 24 + int(hour)) // BLOCK_HOURS
    digest = hashlib.sha256(f"khorinis-weather-{block}".encode()).digest()
    roll = digest[0] / 255.0
    acc = 0.0
    kind, intensity = FRONTS[-1][0], FRONTS[-1][1]
    for k, i, share in FRONTS:
        acc += share
        if roll <= acc:
            kind, intensity = k, i
            break
    wind_strength = digest[1] / 255.0 * (5.0 if kind == "rain" else 2.5)
    angle = digest[2] / 255.0 * 6.2832
    import math
    return kind, intensity, (round(math.cos(angle) * wind_strength, 2), round(math.sin(angle) * wind_strength, 2))


def story_weather(state, now_hours):
    """The weather a story has set and still owns, or None."""
    weather = state.get("weather")
    if not weather:
        return None
    until = weather.get("until")
    return weather if until is None or now_hours < until else None


def wanted(state, day, hour, minute):
    """What should be falling now, and who decided it: (kind, intensity, wind, by_story, cover)."""
    now = day * 24 + hour + minute / 60.0
    owned = story_weather(state, now)
    if owned is not None:
        return owned["kind"], owned.get("intensity", 1.0), tuple(owned.get("wind", (0, 0))), True, owned.get("cover")
    kind, intensity, wind = front(day, hour)
    return kind, intensity, wind, False, None


def enabled():
    global _enabled
    if _enabled is None:
        try:
            _enabled = bool(json.loads(SETTINGS.read_text(encoding="utf-8")).get("climate", False))
        except (OSError, ValueError):
            _enabled = False
    return _enabled


def forget():
    """Something else set the weather: set the climate's front again on the next look."""
    global _last
    _last = None


def enable(on=True):
    global _enabled, _last
    _enabled, _last = on, None


_world = None


_air_ended = None   # (world, the story weather's end) whose heat and fog were taken away


def _end_story_air(gothic, state, by_story, generation):
    """A story's heat and ground fog end with its hours, however the game got here (a load, a trip's snowfall): once
    per world and story weather, whenever the story no longer owns the weather. The climate brings none of its own."""
    global _air_ended
    weather = state.get("weather") or {}
    if by_story or not (weather.get("heat") or weather.get("fog")):
        return
    key = (generation, weather.get("until"))
    if _air_ended == key:
        return
    _air_ended = key
    if hasattr(gothic.weather, "heat"):
        gothic.weather.heat(0.0, 600.0)
    if hasattr(gothic.weather, "fog"):   # it thins where it lies, it does not move first
        gothic.weather.fog(0.0, weather.get("fog_height") or 25.0, weather.get("fog_base"), 300.0)


def tick(gothic, state, now):
    """Sets the climate's front when it changes, ends a story's weather when its hours run out, and lets snow lie
    while it snows. A story's own weather is set by the story (with its own fade) and never set again here."""
    global _last, _world
    if not hasattr(gothic, "weather") or not hasattr(gothic.weather, "set"):
        return None
    from dm import weather as snowfall
    generation = getattr(gothic.world, "generation", None)
    if snowfall.active():
        _last = None   # a trip's snowfall owns the sky; afterwards everything is set again
        day, (hour, minute) = gothic.world.day, gothic.world.time
        _end_story_air(gothic, state, story_weather(state, day * 24 + hour + minute / 60.0) is not None, generation)
        return None
    if generation != _world:   # a loaded or new world: nothing set here holds any more
        _world, _last = generation, None
    day, (hour, minute) = gothic.world.day, gothic.world.time
    kind, intensity, wind, by_story, cover = wanted(state, day, hour, minute)
    current = ("story", kind, intensity, wind) if by_story else ("climate", kind, intensity, wind)
    _end_story_air(gothic, state, by_story, generation)
    if by_story:
        _last = current
    elif enabled():
        if current != _last:
            gothic.weather.set(kind, intensity, FADE, wind)
            _last = current
    else:
        if _last is not None and _last[0] == "story":   # the story's hours ran out and nothing takes over: clear up
            gothic.weather.set("clear", 0.0, FADE, (0, 0))
            gothic.weather.cover(0.0, 1800.0)
        _last = None
        return None
    if cover is None:   # a story that set its own cover keeps it; otherwise snow lies while it snows and melts after
        if kind in ("snow", "crystal"):   # a crystal storm frosts the ground the same way
            gothic.weather.cover(min(1.0, intensity * 0.8), 1200.0)
        else:
            gothic.weather.cover(0.0, 1800.0)
    return current


STORM_FROM = 0.75        # rain at least this heavy can bring lightning
STORM_CHANCE = 0.06      # per look (every TICK_SECONDS): about one flash in half a minute


def storm(gothic, rng):
    """Lightning in heavy rain, whoever set it: a flash, and its thunder after the time sound needs (0.5 to 5 s).
    A fire rain's strikes are magic_weather's."""
    if not hasattr(gothic.weather, "lightning"):
        return False
    state = gothic.weather.state()
    kind, intensity = state.get("kind"), state.get("intensity", 0)
    if kind != "rain" or intensity < STORM_FROM or rng.random() > STORM_CHANCE:
        return False
    gothic.weather.lightning(round(0.5 + rng.random() ** 2 * 4.5, 2))
    import time
    from dm import weather_talk
    weather_talk.flashed(time.monotonic())   # people may speak of it
    return True


def _tick(_dt):
    global _next_look
    import random
    import time
    import gothic
    from dm import story
    now = time.monotonic()
    if now < _next_look:
        return
    _next_look = now + TICK_SECONDS
    try:
        gothic.world.day
    except RuntimeError:
        return   # no world while loading
    tick(gothic, story.state(), now)
    storm(gothic, random)


def start():
    """Safe to call repeatedly."""
    import gothic
    if getattr(gothic, "_dm_climate_registered", False):
        return
    gothic.on_tick(_tick)
    gothic._dm_climate_registered = True
