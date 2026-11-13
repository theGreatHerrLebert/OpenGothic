"""Seeking shelter: who goes, when, where; more waiting while it rains; nobody grabbed out of a talk or a story."""
import pathlib
import random
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import shelter  # noqa: E402

calls = []


class Npc:
    def __init__(self, nid, instance, state="ZS_SMALLTALK", guild=3, pos=(0.0, 0.0, 0.0)):
        self.key, self.instance, self.state, self.guild, self.position = nid, instance, state, guild, pos
        self.alive, self.routine_held, self.ai_queue = True, False, 0

    def can_reach(self, wp): return True

    def shelter_at(self, wp, wait, run):
        calls.append(("shelter", self.instance, wp))
        self.ai_queue = 3
        return True

    def wait_more(self, wait):
        calls.append(("more", self.instance))
        self.ai_queue += 1


weather = {"kind": "rain", "falling": 0.9}
smith = Npc(11, "VLK_SMITH")            # talking in the square: goes
guard = Npc(12, "MIL_GUARD", "ZS_STAND_GUARDING")
held = Npc(13, "VLK_HELD"); held.routine_held = True
wolf = Npc(14, "WOLF", guild=31)
roofed = Npc(15, "VLK_ROOF", pos=(5000.0, 0.0, 0.0))
talker = Npc(16, "VLK_TALKER")
cast = Npc(17, "VLK_CAST")
people = [smith, guard, held, wolf, roofed, talker, cast]
fake = types.SimpleNamespace(
    player=types.SimpleNamespace(position=(0.0, 0.0, 0.0)),
    world=types.SimpleNamespace(generation=1, npcs_near=lambda r: people,
                                shelter_points=lambda x, y, z, r, taken: [(n, 300.0, 0.0, 0.0) for n in ("WP_A", "WP_B")
                                                                          if n not in taken]),
    weather=types.SimpleNamespace(state=lambda: weather, roof_at=lambda x, z: 900.0 if x > 4000 else -1e9),
    dialog=types.SimpleNamespace(partner=lambda: partner[0]))
partner = [talker]
story = types.ModuleType("dm.story")
story._story = types.SimpleNamespace(state={"stories": {"s1": {"ended": None, "cast": ["vlk_cast"]}}})
sys.modules["dm.story"] = story


class Now(random.Random):
    def uniform(self, a, b): return 0.0   # everyone notices at once


shelter.tick(fake, 100.0, Now())            # they notice
assert calls == [], calls
sent = shelter.tick(fake, 102.0, Now())     # and go
assert sent == [("VLK_SMITH", "WP_A")], sent  # not the guard, the held, the wolf, the roofed, the talker, the cast
# Under cover, more waiting is queued while it rains, when what is queued runs low.
smith.position, smith.ai_queue = (300.0, 0.0, 0.0), 1
calls.clear()
shelter.tick(fake, 104.0, Now())
assert ("more", "VLK_SMITH") in calls, calls
# Interrupted (a fight cleared his queue and he is elsewhere): let go, not grabbed again at once.
smith.position, smith.ai_queue = (2000.0, 0.0, 0.0), 0
shelter.tick(fake, 106.0, Now())
assert 11 not in shelter._sheltered and shelter._failed[11] > 106.0
# Pulled into a talk while under cover: no more waiting is queued that would hold the talk up.
shelter._reset(); shelter._failed.clear()
smith.position, smith.ai_queue = (0.0, 0.0, 0.0), 0
shelter.tick(fake, 150.0, Now()); shelter.tick(fake, 152.0, Now())
smith.position, smith.ai_queue = (300.0, 0.0, 0.0), 1
partner[0] = smith
calls.clear()
shelter.tick(fake, 154.0, Now())
assert not any(c[0] == "more" for c in calls) and 11 not in shelter._sheltered, calls
partner[0] = talker
# The rain stops: nobody is sent, nobody waits longer; when his waiting runs out he is let go.
shelter._reset()
shelter._failed.clear()
smith.position, smith.ai_queue = (0.0, 0.0, 0.0), 0
shelter.tick(fake, 200.0, Now()); shelter.tick(fake, 202.0, Now())
assert 11 in shelter._sheltered
weather.update(falling=0.1)
smith.position, smith.ai_queue = (300.0, 0.0, 0.0), 1
calls.clear()
shelter.tick(fake, 204.0, Now())
assert not any(c[0] == "more" for c in calls), calls
smith.ai_queue = 0
shelter.tick(fake, 240.0, Now())
assert 11 not in shelter._sheltered
# A fire rain sends them too; light rain does not.
assert shelter.wetness({"kind": "fire", "falling": 0.5}) == 0.5 and shelter.wetness({"kind": "rain", "falling": 0.3}) == 0.0
print("shelter ok")
