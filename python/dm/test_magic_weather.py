"""Fire rain: its roar, strikes near the hero, wounds for the hero and animals only, never fatal, never in a dialogue."""
import pathlib
import random
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import magic_weather as mw  # noqa: E402

calls = []


class Who:
    def __init__(self, instance, guild, pos, alive=True):
        self.instance, self.guild, self.position, self.alive = instance, guild, pos, alive

    def hurt(self, amount):
        calls.append(("hurt", self.instance, amount))
        return amount


class Here:
    def __init__(self, name): self.name = name
    def is_file(self): return True
    def __str__(self): return self.name


class Folder:
    def __truediv__(self, name): return Here(name)


mw.SOUNDS = Folder()
weather = {"kind": "fire", "falling": 1.0}
roofs = {}
hero = Who("hero", 0, (0.0, 1000.0, 0.0))
wolf = Who("WOLF", 31, (150.0, 1000.0, 0.0))
smith = Who("VLK_SMITH", 3, (100.0, 1000.0, 0.0))
partner = [None]
fake = types.SimpleNamespace(
    player=hero,
    world=types.SimpleNamespace(generation=1, npcs_near=lambda r: [wolf, smith],
                                play_effect=lambda *a: calls.append(("effect",) + a) or True),
    weather=types.SimpleNamespace(state=lambda: weather, loop=lambda *a: calls.append(("loop",) + a),
                                  flash=lambda level: calls.append(("flash", round(level, 2))),
                                  roof_at=lambda x, z: roofs.get((round(x), round(z)), 990.0)),
    dialog=types.SimpleNamespace(partner=lambda: partner[0], narrating=lambda: False))

# A strike right next to the hero: the blast, the fire that stays, a flash, and wounds for him and the wolf only.
at, wounded = mw.strike(fake, random.Random(1), at=(100.0, 1000.0, 0.0))
assert ("effect", mw.BLAST, 100.0, 1000.0, 0.0) in calls and ("effect", mw.LINGER, 100.0, 1000.0, 0.0, 30.0) in calls
assert wounded == ["hero", "WOLF"], wounded
assert not any(c[0] == "hurt" and c[1] == "VLK_SMITH" for c in calls), calls
# Under a roof he is safe; in a dialogue nobody is wounded.
calls.clear()
roofs[(0, 0)] = 1800.0
assert mw.strike(fake, random.Random(1), at=(100.0, 1000.0, 0.0))[1] == ["WOLF"]
roofs.clear()
partner[0] = smith
calls.clear()
assert mw.strike(fake, random.Random(1), at=(100.0, 1000.0, 0.0)) == ((100.0, 1000.0, 0.0), [])
assert not any(c[0] == "hurt" for c in calls) and any(c[0] == "flash" for c in calls), calls
partner[0] = None
# Where no ground is known there is no strike.
fake.weather.roof_at = lambda x, z: -1.0e9
assert mw.target(fake, random.Random(2)) is None
fake.weather.roof_at = lambda x, z: 990.0
x, y, z = mw.target(fake, random.Random(2))
assert 400.0 <= ((x ** 2 + z ** 2) ** 0.5) <= mw.FAR and y == 990.0
# A strike chosen by itself can land close enough to wound him.
class Close(random.Random):
    def random(self): return 0.0          # the close band, angle 0
    def uniform(self, a, b): return a     # its nearest edge
x, y, z = mw.target(fake, Close())
assert abs(x - mw.CLOSEST) < 1e-6 and mw.CLOSEST < mw.RADIUS
calls.clear()
assert "hero" in mw.strike(fake, Close())[1], calls
# The tick: the roar follows the fire, strikes come once due, and stop with it.
calls.clear()
mw.tick(fake, 100.0, random.Random(3))
assert ("loop", "fire", "feuer.wav", 0.7, 8.0) in calls and mw._state["next"] is not None
assert mw.tick(fake, mw._state["next"] + 0.1, random.Random(3)) is not None
weather.update(kind="rain", falling=1.0)
calls.clear()
mw.tick(fake, 1000.0, random.Random(3))
assert ("loop", "fire", "feuer.wav", 0.0, 8.0) in calls and mw._state["next"] is None, calls
print("magic weather ok")
