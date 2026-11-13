"""Summer: cicadas on a hot day, crickets and the Milky Way on a warm clear night."""
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import summer  # noqa: E402

hot = {"heat": 0.8, "overcast": 0.0, "falling": 0.0}
assert summer.levels(hot, 13, 0) == (1.0, 0.0) and summer.levels(hot, 23, 0) == (0.0, 1.0)
assert summer.levels(hot, 7, 0) == (0.0, 0.0)                        # early morning: neither
assert 0.0 < summer.levels(hot, 21, 0)[1] < 1.0 and 0.0 < summer.levels(hot, 9, 30)[0] < 1.0
assert summer.levels(dict(hot, overcast=0.3), 23, 0) == (0.0, 0.0)  # clouds: no stars, no warm night
assert summer.levels(dict(hot, overcast=0.3), 13, 0)[0] == 1.0      # a few clouds: still cicadas
assert summer.levels(dict(hot, heat=0.2), 13, 0) == (0.0, 0.0)      # a mild day is just a day
assert summer.levels(dict(hot, falling=0.3), 13, 0) == (0.0, 0.0)

calls = []
summer.SOUNDS = types.SimpleNamespace(__truediv__=None)
class Here:
    def __init__(self, name): self.name = name
    def is_file(self): return True
    def __str__(self): return self.name
class Folder:
    def __truediv__(self, name): return Here(name)
summer.SOUNDS = Folder()
fake = types.SimpleNamespace(
    world=types.SimpleNamespace(time=(23, 0), generation=1),
    weather=types.SimpleNamespace(state=lambda: hot, loop=lambda *a: calls.append(("loop",) + a)),
    sky=types.SimpleNamespace(galaxy=lambda *a: calls.append(("galaxy",) + a[:1]), clear=lambda: calls.append(("clear",))))
from dm import trip  # noqa: E402
trip._load_sky = lambda gothic, slot, name: True
summer.tick(fake, 100.0)
assert ("loop", "crickets", "grillen.wav", 0.6, 20.0) in calls and ("galaxy", 0.43) in calls, calls
calls.clear()
summer.tick(fake, 102.0)
assert not any(c[0] == "loop" for c in calls), calls                 # unchanged: not set again
fake.world.generation = 2                                            # loaded: set again
calls.clear()
summer.tick(fake, 104.0)
assert ("loop", "crickets", "grillen.wav", 0.6, 20.0) in calls, calls
# a trip has the sky, but the crickets still follow the weather
trip._current = object()
hot["falling"] = 0.5
calls.clear()
summer.tick(fake, 106.0)
assert ("loop", "crickets", "grillen.wav", 0.0, 20.0) in calls and not any(c[0] == "galaxy" for c in calls), calls
trip._current = None
hot["falling"] = 0.0
summer.tick(fake, 107.0)                                             # the trip is over: the stars again
fake.world.time = (13, 0)                                            # noon: cicadas, the game's sky
calls.clear()
summer.tick(fake, 108.0)
assert ("loop", "cicadas", "zikaden.wav", 0.35, 20.0) in calls and ("clear",) in calls, calls
print("summer ok")
