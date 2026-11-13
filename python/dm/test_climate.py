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
print("climate ok")
