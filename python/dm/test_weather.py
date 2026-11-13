"""Snowfall tests against a fake game. Run: python3 python/dm/test_weather.py

They prove the curve and the indoor fade, not how the snow looks.
"""

import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import weather  # noqa: E402

# A few flakes first, thickening to the peak, held, then clearing.
d = lambda s: weather.density_at(s, 60, 90, 40)
assert d(0) == 0 and 0 < d(10) < 0.1 and 0.4 < d(30) < 0.6 and d(60) == 1 and d(120) == 1
assert d(150 + 20) < 1 and d(190) == 0 and d(-1) == 0
assert all(d(s) <= d(s + 1) for s in range(0, 60))          # never thins out while it is meant to thicken

# Indoors it fades out and comes back outside; it ends on its own and leaves no snow behind.
sent = []
room = {"name": ""}


class Player:
    @property
    def room(self):
        return room["name"]


game = types.SimpleNamespace(player=Player(), weather=types.SimpleNamespace(snow=sent.append))
fall = weather.Snowfall(10, 10, 10, 1.0)
now = 0.0
while now < 15:
    fall.tick(game, now)
    now += 0.05
assert sent[-1] > 0.95
room["name"] = "HAFENKNEIPE"
for _ in range(60):
    fall.tick(game, now)
    now += 0.05
assert sent[-1] < 0.05
room["name"] = ""
while fall.tick(game, now):
    now += 0.05
assert 29.9 <= now <= 30.1

# Stopping eases it off within a few seconds.
fall = weather.Snowfall(5, 100, 5, 1.0)
now = 0.0
while now < 10:
    fall.tick(game, now)
    now += 0.05
fall.ending = (now, 1.0)
start = now
while fall.tick(game, now):
    now += 0.05
assert now - start <= 4.1 and sent[-1] < 0.05
print("weather ok")

# With world weather, the snowfall sets it (only when it changes), lets snow lie, and indoors is left to the roof map.
world_calls = []
world = types.SimpleNamespace(set=lambda *a, **kw: world_calls.append(("set",) + a + tuple(sorted(kw.items()))),
                              cover=lambda *a: world_calls.append(("cover",) + a),
                              snow=lambda d: world_calls.append(("lens", d)))
g2 = types.SimpleNamespace(player=types.SimpleNamespace(room="HOUSE"), weather=world)
fall = weather.Snowfall(10, 10, 10, 1.0)
fall.tick(g2, 0.0)
fall.tick(g2, 15.0)   # at the peak, indoors: still snowing in the world; the roof map keeps it off him
fall.tick(g2, 15.5)   # the same level: nothing set again
sets = [c for c in world_calls if c[0] == "set"]
assert sets[-1][:3] == ("set", "snow", 1.0) and sets[-1][4] == weather.WIND and ("open_sky", True) in sets[-1], sets
assert len([c for c in sets if c[2] == 1.0]) == 1 and not any(c[0] == "lens" for c in world_calls)
assert ("cover", 0.7, 90.0) in world_calls
print("world snowfall ok")
