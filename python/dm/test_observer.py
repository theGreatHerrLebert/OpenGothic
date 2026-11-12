"""Observer logic tests against a fake game. Run: python3 python/dm/test_observer.py"""

import collections
import pathlib
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


class Npc:
    def __init__(self, instance, name, alive=True):
        self.instance, self.name, self.alive = instance, name, alive


state = dict(day=0, room="", wp="NW_A_1", items=[], near=[], partner=None, alive=True, gen=1)


class World:
    day = property(lambda s: state["day"])
    time = property(lambda s: (8, 0))
    generation = property(lambda s: state["gen"])
    def npcs_near(self, radius): return state["near"]


class Player:
    room = property(lambda s: state["room"])
    waypoint = property(lambda s: state["wp"])
    items = property(lambda s: state["items"])
    alive = property(lambda s: state["alive"])


class Dialog:
    def partner(self): return state["partner"]


fake = types.ModuleType("gothic")
fake.world, fake.player, fake.dialog = World(), Player(), Dialog()
sys.modules["gothic"] = fake

import dm.observer as o  # noqa: E402

tmp = pathlib.Path(tempfile.mkdtemp())
o.RUNTIME_DIR, o.LOG_PATH = tmp, tmp / "events.jsonl"
ob = o.Observer()


def step(**changes):
    state.update(changes)
    before = ob.seq
    ob.poll()
    return list(ob.events)[before - ob.seq:] if ob.seq > before else []


def kinds(events):
    return [e["type"] for e in events]


def quiet(polls):
    out = []
    for _ in range(polls):
        out += step()
    return out


def items(**counts):
    return [{"instance": k, "count": v, "name": k, "equipped": False} for k, v in counts.items()]


def test():
    assert o.place_of("NW_XARDAS_TOWER_IN1_02") == "XARDAS_TOWER"
    assert o.place_of("NW_MONASTERY_CHURCH_01") == "MONASTERY_CHURCH"
    assert o.place_of("NW_CITY_MERCHANT_PATH_36") == "CITY_MERCHANT"
    assert o.place_of("XARDAS") == "XARDAS"

    assert kinds(step(items=items(BREAD=2))) == ["world_loaded"]
    assert quiet(3) == []

    # pickups merge, and flush only after a quiet spell
    assert step(items=items(BREAD=3)) == []
    assert step(items=items(BREAD=3, GOLD=1)) == []
    assert step(items=items(BREAD=3, GOLD=4)) == []
    merged = quiet(o.ITEM_QUIET_POLLS)
    assert kinds(merged) == ["items_gained"], merged
    assert merged[0]["items"] == {"BREAD": 1, "GOLD": 4}

    # picked up and dropped within the window nets to nothing
    step(items=items(BREAD=4, GOLD=4))
    step(items=items(BREAD=3, GOLD=4))
    assert quiet(o.ITEM_QUIET_POLLS) == []

    # a conversation closes the current batch first
    step(items=items(BREAD=2, GOLD=4))
    karras = Npc("KARRAS", "Karras")
    assert kinds(step(partner=karras)) == ["items_lost", "talk_started"]
    assert kinds(step(partner=None)) == ["talk_ended"]

    # NPC sighting cooldown
    jorgen = Npc("JORGEN", "Jorgen")
    assert kinds(step(near=[jorgen])) == ["npc_near"]
    step(near=[])
    assert step(near=[jorgen]) == []
    step(near=[])
    quiet(o.NEAR_COOLDOWN_POLLS)
    assert kinds(step(near=[jorgen])) == ["npc_near"]
    assert kinds(step(near=[Npc("JORGEN", "Jorgen", alive=False)])) == ["npc_down"]
    step(near=[])

    # waypoints inside one place are silent; a new place needs to settle
    assert step(wp="NW_A_2") == []
    assert quiet(4) == []
    step(wp="NW_MONASTERY_CHURCH_01")
    assert quiet(2) == []
    assert kinds(quiet(1)) == ["place_entered"]
    step(wp="NW_MONASTERY_CHURCH_02")
    assert quiet(5) == []

    # rooms, days, player down
    assert kinds(step(room="KLOSTER")) == ["room_entered"]
    assert kinds(step(room="")) == ["room_left"]
    assert kinds(step(day=1)) == ["day_changed"]
    assert kinds(step(alive=False)) == ["player_down"]
    state["alive"] = True
    step()

    # a load flushes pending items, then resets without reporting differences
    step(items=items(BREAD=9, GOLD=4))
    assert kinds(step(gen=2, items=items(SWORD=1), room="X", day=9)) == ["items_gained", "world_loaded"]
    assert quiet(o.ITEM_QUIET_POLLS) == []


test()
print("observer tests passed")

# Timelines: a reload leaves behind what happened after the save, and an author never sees it.
o.TIMELINES_PATH, o.SAVES_DIR = tmp / "timelines.json", tmp / "saves"
ob = o.Observer()
o._observer = ob
ob.on_new_game()
step(gen=10)
step(room="KITCHEN")                  # before the save: part of the game
ob.on_save("slot1")
step(room="")
step(room="CELLAR")                   # after the save: thrown away by the reload below
cellar = [e for e in ob.events if e.get("room") == "CELLAR"]
assert cellar and ob.on_branch(cellar[0])
ob.on_load("slot1")
step(gen=11)
step(room="TOWER")                    # the new timeline
rooms = [e.get("room") for e in o.recent(50) if e["type"] == "room_entered"]
assert "KITCHEN" in rooms and "TOWER" in rooms and "CELLAR" not in rooms, rooms
keep = o.branch_filter()
assert not keep(cellar[0]) and keep([e for e in ob.events if e.get("room") == "KITCHEN"][0])
# A save made in the new timeline, loaded later, still leads back through the first one.
ob.on_save("slot2")
step(room="")
step(room="ATTIC")
ob.on_load("slot2")
rooms = [e.get("room") for e in o.recent(50) if e["type"] == "room_entered"]
assert rooms[:2] == ["KITCHEN", "TOWER"] and "ATTIC" not in rooms and "CELLAR" not in rooms, rooms
# A save from before timelines starts a fresh one: its past is unknown, so nothing old is shown.
ob.on_load("never_saved")
assert o.recent(50) == []
print("timeline tests passed")
