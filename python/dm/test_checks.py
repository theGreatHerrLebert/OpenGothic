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
for bad, word in [({"event": "nope"}, "unknown"), ({"event": "took_item", "item": "BURNER"}, "not an item"), ({"event": "hit", "target": "ITX"}, "not an NPC"),
                  ({"event": "cast_spell", "spell": "FIRE"}, "not a spell"), ({"event": "hit", "seen_by": "BURNER", "unseen": True}, "exclude")]:
    assert word in perc.validate(bad), bad
assert perc.validate(None) is None and perc.validate({"event": "hit", "target": "PLAYER"}) is None
print("perceptions ok")

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
