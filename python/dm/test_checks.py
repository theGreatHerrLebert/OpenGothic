"""Live condition tests against a fake game. Run: python3 python/dm/test_checks.py"""

import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
fake = types.ModuleType("gothic")
sys.modules["gothic"] = fake

burning = types.SimpleNamespace(dead=False, in_state=lambda s: s == "ZS_MAGICBURN")
corpse = types.SimpleNamespace(dead=True, in_state=lambda s: False)
fake.world = types.SimpleNamespace(
    time=(22, 0), find_npc=lambda n: {"BURNER": burning, "CORPSE": corpse}.get(n),
    instance_kind=lambda n: "npc" if n in ("BURNER", "CORPSE", "ABSENT") else "item" if n.startswith("IT") else None)
fake.player = types.SimpleNamespace(items=[{"instance": "ITMI_GOLD", "count": 40}], armor="ITAR_BAU_L", guild=3)
values = {"GIL_NOV": 3, "GIL_KDF": 4, "SC_ISOBSESSED": 0}
fake.daedalus = types.SimpleNamespace(get=lambda n, i=0: values[n])

from dm import checks, graph  # noqa: E402


def holds(**c):
    return checks.all_hold([c])


assert holds(type="has_item", item="ITMI_GOLD", count=40) and not holds(type="has_item", item="ITMI_GOLD", count=41)
assert not holds(type="has_item", item="ITMI_FLASK")
assert holds(type="wears", item="itar_bau_l") and not holds(type="wears", item="ITAR_NOV_L")
fake.player.armor = None
assert not holds(type="wears", item="ITAR_BAU_L")
assert holds(type="guild", guild="GIL_NOV") and not holds(type="guild", guild="GIL_KDF")
assert holds(type="npc_state", npc="BURNER", state="ZS_MAGICBURN") and not holds(type="npc_state", npc="BURNER", state="ZS_MAGICSLEEP")
assert not holds(type="npc_state", npc="ABSENT", state="ZS_MAGICBURN")
assert holds(type="npc_dead", npc="CORPSE") and not holds(type="npc_dead", npc="BURNER") and not holds(type="npc_dead", npc="ABSENT")
assert not holds(type="obsessed")
values["SC_ISOBSESSED"] = 1
assert holds(type="obsessed")
assert holds(type="hour", **{"from": 21, "to": 5}) and not holds(type="hour", **{"from": 8, "to": 20})
fake.world.time = (3, 0)
assert holds(type="hour", **{"from": 21, "to": 5})
assert holds(type="not", check={"type": "guild", "guild": "GIL_KDF"})
assert checks.all_hold(None) and checks.all_hold([])

for bad, word in [({"type": "nope"}, "unknown"), ({"type": "has_item"}, "needs"), ({"type": "wears", "item": "BURNER"}, "not an item"),
                  ({"type": "guild", "guild": "NOV"}, "not a guild"), ({"type": "npc_state", "npc": "ITX", "state": "ZS_MAGICBURN"}, "not an NPC"),
                  ({"type": "npc_state", "npc": "BURNER", "state": "ZS_TALK"}, "cannot"), ({"type": "hour", "from": 25, "to": 1}, "range"),
                  ({"type": "not", "check": {"type": "nope"}}, "unknown")]:
    assert word in checks.validate(bad), bad
assert checks.validate({"type": "npc_state", "npc": "BURNER", "state": "ZS_MAGICBURN"}) is None

# A checked choice counts as conditional, so it can never be the only way out of a node.
only = {"start": "a", "nodes": {"a": {"line": "x", "choices": [{"text": "y", "ends": True, "checks": [{"type": "obsessed"}]}]}}}
assert "only conditional" in graph.validate(only)
two = {"start": "a", "nodes": {"a": {"line": "x", "choices": [
    {"text": "reich", "ends": True, "checks": [{"type": "has_item", "item": "ITMI_GOLD", "count": 100}]},
    {"text": "arm", "ends": True}]}}}
assert graph.validate(two) is None
player = graph.Player(lambda: {}, lambda n: None, dict)
player.partner, player.node = "N", two["nodes"]["a"]
assert [c["text"] for c in player._visible_choices()] == ["arm"]
fake.player.items[0]["count"] = 100
assert [c["text"] for c in player._visible_choices()] == ["reich", "arm"]
bad = {"start": "a", "nodes": {"a": {"line": "x", "choices": [{"text": "y", "ends": True, "checks": [{"type": "nope"}]}]}}}
assert "unknown" in checks.validate_graph(bad)
print("ok")

# Perceptions.
from dm import perceptions as perc  # noqa: E402

values["SPL_FIREBOLT"] = 18
ev = dict(kind="cast_spell", actor="PLAYER", target="BURNER", item="", spell=18, seen_by=[])
assert perc.matches({"event": "cast_spell"}, ev) and perc.matches({"event": "cast_spell", "target": "BURNER", "spell": "SPL_FIREBOLT"}, ev)
assert not perc.matches({"event": "hit"}, ev) and not perc.matches({"event": "cast_spell", "target": "CORPSE"}, ev)
values["SPL_SLEEP"] = 7
assert not perc.matches({"event": "cast_spell", "spell": "SPL_SLEEP"}, ev)
take = dict(kind="took_item", actor="PLAYER", target="", item="ITMI_GOLD", spell=-1, seen_by=["CORPSE"])
assert perc.matches({"event": "took_item", "item": "itmi_gold", "seen_by": "CORPSE"}, take)
assert not perc.matches({"event": "took_item", "unseen": True}, take) and not perc.matches({"event": "took_item", "item": "ITMI_X"}, take)
assert perc.matches({"event": "took_item", "unseen": True}, {**take, "seen_by": []})
done_to_hero = dict(kind="hit", actor="BURNER", target="PLAYER", item="", spell=-1, seen_by=[])
assert not perc.matches({"event": "hit"}, done_to_hero) and perc.matches({"event": "hit", "target": "PLAYER"}, done_to_hero)
# Getting up from an object: matched by its scheme, case blind, and part of a longer scheme name counts.
pipe = {"kind": "used_object", "actor": "PLAYER", "target": "", "item": "SMOKE_WATERPIPE", "spell": -1, "seen_by": []}
assert perc.matches({"event": "used_object"}, pipe) and perc.matches({"event": "used_object", "object": "waterpipe"}, pipe)
assert not perc.matches({"event": "used_object", "object": "BENCH"}, pipe)
assert perc.validate({"event": "used_object", "object": "WATERPIPE"}) is None
assert "object" in perc.validate({"event": "used_object", "object": ""})
assert "object" in perc.validate({"event": "hit", "object": "WATERPIPE"})
# One particular pipe: by its own name, or by where it stands.
pipe = {**pipe, "object": "NW_CITY_PIPE_02", "position": (9000.0, 300.0, 6000.0)}
assert perc.matches({"event": "used_object", "name": "nw_city_pipe_02"}, pipe)
assert not perc.matches({"event": "used_object", "name": "NW_CITY_PIPE_01"}, pipe)
assert perc.matches({"event": "used_object", "near": [9100, 6000, 2]}, pipe)            # 1 m away
assert not perc.matches({"event": "used_object", "near": [9500, 6000, 2]}, pipe)        # 5 m away
assert not perc.matches({"event": "used_object", "near": [9000, 6000, 2]}, {**pipe, "position": None})
assert perc.validate({"event": "used_object", "near": [9000, 6000, 2]}) is None
for bad in ([9000, 6000], [9000, 6000, 0], [9000, 6000, 99], ["9000", 6000, 2], [True, 6000, 2]):
    assert "near" in perc.validate({"event": "used_object", "near": bad}), bad
assert "name" in perc.validate({"event": "took_item", "name": "X"})
for bad, word in [({"event": "nope"}, "unknown"), ({"event": "took_item", "item": "BURNER"}, "not an item"), ({"event": "hit", "target": "ITX"}, "not an NPC"),
                  ({"event": "cast_spell", "spell": "FIRE"}, "not a spell"), ({"event": "hit", "seen_by": "BURNER", "unseen": True}, "exclude")]:
    assert word in perc.validate(bad), bad
assert perc.validate(None) is None and perc.validate({"event": "hit", "target": "PLAYER"}) is None
print("perceptions ok")

# The game's own quest state, and "any".
values.update({"LOG_RUNNING": 1, "LOG_SUCCESS": 2, "LOG_FAILED": 3, "LOG_OBSOLETE": 4,
               "MIS_LOBART_RUEBEN": 2, "MIS_VINO_WEIN": 1, "MIS_LOBARTKILLBUGS": 0})
assert holds(type="quest", quest="MIS_LOBART_RUEBEN", state="success")
assert holds(type="quest", quest="mis_vino_wein", state="running") and not holds(type="quest", quest="MIS_VINO_WEIN", state="success")
assert holds(type="quest", quest="MIS_LOBARTKILLBUGS", state="open")
helped = {"type": "any", "checks": [{"type": "quest", "quest": q, "state": "success"} for q in ("MIS_VINO_WEIN", "MIS_LOBART_RUEBEN")]}
assert checks.all_hold([helped])
values["MIS_LOBART_RUEBEN"] = 1
assert not checks.all_hold([helped])
assert checks.validate(helped) is None
assert "no such quest" in checks.validate({"type": "quest", "quest": "MIS_NOPE", "state": "success"})
assert "not a quest" in checks.validate({"type": "quest", "quest": "LOBART", "state": "success"})
assert "unknown quest state" in checks.validate({"type": "quest", "quest": "MIS_VINO_WEIN", "state": "done"})
assert "list of checks" in checks.validate({"type": "any", "checks": []})
assert "unknown check" in checks.validate({"type": "any", "checks": [{"type": "nope"}]})

# Whether the hero has heard one of the game's own topics: a story topic can wait for "who are you?".
heard_topics = {"DIA_ABUYIN_DU"}


def heard(name):
    if not name.startswith("DIA_ABUYIN"):
        raise ValueError(f"not a dialogue topic: {name}")
    return name in heard_topics


fake.player.heard = heard
assert holds(type="heard", info="dia_abuyin_du") and not holds(type="heard", info="DIA_ABUYIN_ANDEREN")
assert checks.validate({"type": "heard", "info": "DIA_ABUYIN_DU"}) is None
assert "not a dialogue topic" in checks.validate({"type": "heard", "info": "ABUYIN"})
assert "no such dialogue topic" in checks.validate({"type": "heard", "info": "DIA_NOPE"})
del fake.player.heard
assert checks.validate({"type": "heard", "info": "DIA_NOPE"}) is None     # offline the name cannot be looked up

# Handing things over.
removed, given = [], []
fake.player.remove_item = lambda i, c=1: removed.append((i, c))
fake.player.give_item = lambda i, c=1: given.append((i, c))
fake.player.items = [{"instance": "ITWR_LETTER", "count": 1}]
hand = {"text": "Hier.", "ends": True, "takes": {"item": "ITWR_LETTER"}, "gives": {"item": "ITMI_GOLD", "count": 5}}
node = {"start": "a", "nodes": {"a": {"line": "x", "choices": [hand, {"text": "Nein.", "ends": True}]}}}
assert graph.validate(node) is None and checks.validate_graph(node) is None
assert "only conditional" in graph.validate({"start": "a", "nodes": {"a": {"line": "x", "choices": [hand]}}})
player.node = node["nodes"]["a"]
assert len(player._visible_choices()) == 2
printed = []
values.update({"YPOS_ITEMGIVEN": 37, "YPOS_ITEMTAKEN": 40, "FONT_SCREENSMALL": "FONT_OLD_10_WHITE.TGA"})
fake.print_screen = lambda *args: printed.append(("PRINTSCREEN", *args))
fake.player.items = [{"instance": "ITWR_LETTER", "count": 1, "name": "Brief"}]
checks.transfer(hand)
assert removed == [("ITWR_LETTER", 1)] and given == [("ITMI_GOLD", 5)]
# Each hand-over is announced like the game does it, in its position and font.
assert printed == [("PRINTSCREEN", "Brief gegeben", -1, 37, "FONT_OLD_10_WHITE.TGA", 2),
                   ("PRINTSCREEN", "5 Gold erhalten", -1, 40, "FONT_OLD_10_WHITE.TGA", 2)], printed
from dm import handover  # noqa: E402
assert handover.message("ITFO_APPLE", 3, False, "Apfel") == "3 Gegenstände erhalten (Apfel)"
fake.print_screen = lambda *a: (_ for _ in ()).throw(RuntimeError("no world"))
handover.give("ITMI_GOLD", 1)                      # a failing message does not stop the hand-over
assert given[-1] == ("ITMI_GOLD", 1)
fake.player.items = []
assert [c["text"] for c in player._visible_choices()] == ["Nein."]
assert "not an item" in checks.validate_graph({"nodes": {"a": {"choices": [{"text": "y", "takes": {"item": "BURNER"}}]}}})
assert "need an item" in checks.validate_graph({"nodes": {"a": {"choices": [{"text": "y", "gives": {}}]}}})
assert perc.validate({"event": "read_item", "item": "ITWR_LETTER"}) is None
for count in (1.5, 0, -1, True, "2"):
    assert "whole number" in checks.validate_graph({"nodes": {"a": {"choices": [{"text": "y", "gives": {"item": "ITMI_GOLD", "count": count}}]}}}), count
print("handover ok")

# Chapter, level and day: ranges with both ends included and either end optional.
values["KAPITEL"] = 2
fake.player.level, fake.world.day = 7, 4
assert holds(type="chapter", **{"from": 2}) and holds(type="chapter", to=2) and not holds(type="chapter", **{"from": 3})
assert holds(type="level", min=5, max=7) and not holds(type="level", min=8) and not holds(type="level", max=6)
assert holds(type="day", **{"from": 0, "to": 4}) and not holds(type="day", **{"from": 5})
assert checks.failing([{"type": "chapter", "from": 1}, {"type": "level", "min": 9}]) == {"type": "level", "min": 9}
assert checks.failing([{"type": "chapter", "from": 1}]) is None and checks.failing(None) is None
for bad, word in [({"type": "chapter"}, "needs"), ({"type": "chapter", "from": 0}, "range"), ({"type": "level", "min": "5"}, "range"),
                  ({"type": "day", "from": 4, "to": 2}, "after"), ({"type": "chapter", "from": 8}, "range")]:
    assert word in checks.validate(bad), bad
assert checks.validate({"type": "chapter", "from": 3, "to": 6}) is None and checks.validate({"type": "level", "max": 10}) is None
# The hero is close to someone: within 15 m by default, never near the dead or absent.
burning.position, corpse.position, fake.player.position = (1000.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
assert checks.failing([{"type": "near", "npc": "BURNER"}]) is None
assert checks.failing([{"type": "near", "npc": "BURNER", "within": 500}]) is not None
assert checks.failing([{"type": "near", "npc": "CORPSE"}]) is not None and checks.failing([{"type": "near", "npc": "ABSENT"}]) is not None
assert checks.validate({"type": "near"}) is not None and checks.validate({"type": "near", "npc": "BURNER"}) is None
print("checks ok")
