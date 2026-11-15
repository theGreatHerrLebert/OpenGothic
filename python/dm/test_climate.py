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
# A used item's weather lies over everything while it lasts, then the story's own comes back with its heat and fog.
sys.modules["gothic"] = fake     # story._world_weather sets the sky through the game module
day = 20 * 24
storm = {"kind": "crystal", "intensity": 0.8, "wind": [6, 2], "fog": 0.5, "fog_base": 900.0, "fog_height": 30,
         "until": day + 11.2, "item": "ITMI_PACKET"}
underneath = {"kind": "rain", "intensity": 0.5, "wind": [1, 0], "fade": 40, "heat": None, "fog": None, "until": day + 15}
layered = {"weather": underneath, "item_weather": storm}
assert climate.wanted(layered, 20, 10, 0)[:2] == ("crystal", 0.8) and climate.wanted(layered, 20, 10, 0)[3]
assert climate.wanted(layered, 20, 11, 30)[:2] == ("rain", 0.5)
assert climate.wanted({"item_weather": storm}, 20, 12, 0)[3] is False   # nothing under it: the climate's
calls.clear()
air.clear()
fake.world.day, fake.world.time, fake.world.generation = 20, (10, 0), 3
climate.enable(False)
climate.tick(fake, layered, 20)
assert not [c for c in calls if c[0] == "set"] and air == [], (calls, air)   # the story set it; nothing here
fake.world.time = (11, 30)
climate.tick(fake, layered, 21)
assert ("set", "rain", 0.5, 40, (1, 0)) in calls, calls                   # the story's own again, with its fade
assert air == [("fog", 0.0, 30, 900.0, 300.0)], air                      # the storm's fog thins where it lay
calls.clear()
air.clear()
climate.tick(fake, layered, 22)
assert not [c for c in calls if c[0] == "set"] and air == [], (calls, air)   # once only
# Without a story's weather under it, the climate (here off: clear sky) takes over when it ends.
alone = {"item_weather": dict(storm, until=day + 13.2)}
fake.world.time = (13, 0)
climate.tick(fake, alone, 23)
calls.clear()
air.clear()
fake.world.time = (13, 30)
climate.tick(fake, alone, 24)
assert ("set", "clear", 0.0, climate.FADE, (0, 0)) in calls and ("fog", 0.0, 30, 900.0, 300.0) in air, (calls, air)
# A load after the overlay ran out sets nothing: the story set the sky itself on rebind.
expired = {"weather": dict(underneath, until=day + 20), "item_weather": dict(storm, until=day + 14)}
fake.world.time, fake.world.generation = (14, 30), 4
calls.clear()
air.clear()
climate.tick(fake, expired, 25)
assert not [c for c in calls if c[0] == "set"] and air == [], (calls, air)
# A story's fog ending under a used item's fog leaves the item's alone.
foggy_story = {"weather": {"kind": "clear", "intensity": 0.0, "fog": 0.6, "heat": 0.5, "until": day + 15},
               "item_weather": dict(storm, until=day + 17)}
fake.world.time = (16, 0)
air.clear()
climate.tick(fake, foggy_story, 26)
assert air == [("heat", 0.0, 600.0)], air
# Used and run out before the next look (the hero slept right after): the story told us, so its end is handled.
slept = {"item_weather": dict(storm, until=day + 17.2)}
climate.overlay_shown(fake.world.generation, day + 17.2)
fake.world.time = (23, 0)
calls.clear()
air.clear()
climate.tick(fake, slept, 27)
assert ("set", "clear", 0.0, climate.FADE, (0, 0)) in calls and ("fog", 0.0, 30, 900.0, 300.0) in air, (calls, air)
del sys.modules["gothic"]
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
