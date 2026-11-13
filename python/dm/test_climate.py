"""The weather controller: fronts by game time, a story's weather first, snow cover following snowfall."""
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import climate  # noqa: E402

# The same moment always has the same front, and Khorinis never snows by itself.
assert climate.front(14, 5) == climate.front(14, 3) == climate.front(14, 3)
kinds = {climate.front(d, h)[0] for d in range(60) for h in range(0, 24, 3)}
assert kinds <= {"clear", "rain"} and "rain" in kinds and "clear" in kinds, kinds

# A story's weather owns the sky until its hours run out.
state = {"weather": {"kind": "snow", "intensity": 0.7, "wind": [1, 0], "cover": None, "until": 14 * 24 + 8}}
assert climate.wanted(state, 14, 6, 0)[:2] == ("snow", 0.7) and climate.wanted(state, 14, 6, 0)[3]
assert not climate.wanted(state, 14, 9, 0)[3]
assert climate.wanted({"weather": {"kind": "rain", "intensity": 0.5, "until": None}}, 99, 1, 0)[0] == "rain"

# Ticking: set when it changes, cover follows snow; the climate itself stays off unless enabled.
calls = []
fake = types.SimpleNamespace(world=types.SimpleNamespace(day=14, time=(6, 0)),
                             weather=types.SimpleNamespace(set=lambda *a: calls.append(("set",) + a),
                                                           cover=lambda *a: calls.append(("cover",) + a)))
climate.enable(False)
assert climate.tick(fake, {}, 0) is None and calls == []
climate.tick(fake, state, 0)
assert calls == [("cover", 0.7 * 0.8, 1200.0)], calls   # the story set its own snow, with its own fade: only cover here
calls.clear()
fake.world.time = (9, 0)
climate.tick(fake, state, 1)   # its hours are over and the climate is off: clear up and melt
assert calls == [("set", "clear", 0.0, climate.FADE, (0, 0)), ("cover", 0.0, 1800.0)], calls
calls.clear()
climate.enable(True)
climate.tick(fake, state, 2)   # with the climate on, its front takes over
assert calls[0][0] == "set" and calls[-1] == ("cover", 0.0, 1800.0), calls
calls.clear()
climate.tick(fake, state, 3)
assert calls == [("cover", 0.0, 1800.0)], calls   # the same front is not set again
fake.world.generation = 7      # a loaded world: set again
climate.tick(fake, state, 4)
assert calls[-2][0] == "set", calls
# While a trip's snowfall falls, the climate keeps out of it entirely.
from dm import weather as snowfall
snowfall._current = object()
calls.clear()
assert climate.tick(fake, state, 5) is None and calls == []
snowfall._current = None
# A story's heat and fog end with its hours, even when a load (a new world) came between: once per world.
air = []
fake.weather.heat = lambda *a: air.append(("heat",) + a)
fake.weather.fog = lambda *a: air.append(("fog",) + a)
hot = {"weather": {"kind": "clear", "intensity": 0.0, "heat": 0.8, "fog": None, "until": 14 * 24 + 8}}
fake.world.time, fake.world.generation = (7, 0), 1
climate.tick(fake, hot, 10)
assert air == [], air                      # still the story's
fake.world.time, fake.world.generation = (9, 0), 2   # loaded after the hours ran out
climate.tick(fake, hot, 11)
climate.tick(fake, hot, 12)
assert air == [("heat", 0.0, 600.0), ("fog", 0.0, 25.0, None, 300.0)], air
# Expired fog thins where it lay, at its own height.
air.clear()
foggy = {"weather": {"kind": "clear", "intensity": 0.0, "fog": 0.6, "fog_height": 40, "fog_base": 900.0, "until": 1}}
climate.tick(fake, foggy, 13)
assert ("fog", 0.0, 40, 900.0, 300.0) in air, air
# Lightning only in heavy rain, its thunder delayed by distance.
flashes = []
sky = types.SimpleNamespace(state=lambda: {"kind": "rain", "intensity": 0.9}, lightning=flashes.append)
always = types.SimpleNamespace(random=lambda: 0.0)
assert climate.storm(types.SimpleNamespace(weather=sky), always) and flashes == [0.5]
sky.state = lambda: {"kind": "rain", "intensity": 0.4}
assert not climate.storm(types.SimpleNamespace(weather=sky), always)
sky.state = lambda: {"kind": "snow", "intensity": 1.0}
assert not climate.storm(types.SimpleNamespace(weather=sky), always)
print("climate ok")
