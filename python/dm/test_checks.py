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
