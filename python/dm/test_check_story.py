"""Story checker tests for the deed rule. Run: python3 python/dm/test_check_story.py"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import check_story  # noqa: E402

talk_only = {"plan": [{"op": "add_scene", "id": "s", "graph": {}, "requires": ["met"]},
                      {"op": "add_rule", "id": "r", "when": ["met"], "checks": [{"type": "guild", "guild": "GIL_NOV"}],
                       "ops": []}],
             "conversations": {"A": {"start": "a", "nodes": {"a": {"line": "Hallo.", "choices": [{"text": "Ja.", "ends": True}]}}}}}
assert check_story.deeds(talk_only) == []                  # flags and guild are not deeds

seen = {"plan": [{"op": "add_rule", "id": "letter", "when": [], "on": {"event": "read_item", "item": "ITWR_X"},
                  "ops": []}], "conversations": {}}
assert check_story.deeds(seen) == ["letter: read_item"]

asleep = {"plan": [], "conversations": {"G": {"start": "a", "nodes": {"a": {"line": "...", "choices": [
    {"text": "Vorbei.", "ends": True, "checks": [{"type": "npc_state", "npc": "G", "state": "ZS_MAGICSLEEP"}]}]}}}}}
assert check_story.deeds(asleep) == ["conversations: npc_state"]

errors, warnings = check_story.lint({**talk_only, "conversations": talk_only["conversations"]})
assert any(w.startswith("no deed") for w in warnings)
assert not any(w.startswith("no deed") for w in check_story.lint(seen)[1])
print("ok")


# A dialogue the plan plays but the conversations do not list escapes the knowledge check, so it is an error.
extra = {"voice": "13", "start": "a", "nodes": {"a": {"line": "Hm.", "choices": []}}}
hidden = {"plan": [{"op": "add_topic", "id": "extra", "npc": "VLK_456_ABUYIN", "graph": extra}], "conversations": {}}
assert check_story.unlisted_graphs(hidden) == ["plan: add_topic extra plays a dialogue missing from conversations"]
hidden["conversations"]["VLK_456_ABUYIN_EXTRA"] = extra
assert check_story.unlisted_graphs(hidden) == []

nested = {"plan": [{"op": "add_rule", "id": "r", "when": ["x"], "ops": [{"op": "add_topic", "id": "deep", "graph": extra}]}],
          "conversations": {}}
assert check_story.unlisted_graphs(nested) == ["plan: add_topic deep plays a dialogue missing from conversations"]

# A story's requires are checked like any other checks.
import json, tempfile  # noqa: E401,E402
with tempfile.TemporaryDirectory() as d:
    names = pathlib.Path(d) / "names.json"
    names.write_text(json.dumps({"npcs": [], "items": [], "waypoints": []}))
    base = {"title": "t", "hidden_truth": "", "plot": {"facts": {}, "conversations": {}}, "conversations": {}, "plan": []}
    for requires, wanted in [([{"type": "chapter", "from": 9}], "requires: chapter out of range: 9"),
                             ({"type": "chapter"}, "requires must be a list of checks")]:
        report = check_story.check({**base, "requires": requires}, str(names))
        assert wanted in report["errors"], report
    report = check_story.check({**base, "requires": [{"type": "chapter", "from": 2}]}, str(names))
    assert not any(e.startswith("requires") for e in report["errors"]), report
print("requires ok")

# Why the story matters: missing or empty is refused, four real answers pass.
assert check_story.significance_problems(None)[0].startswith("no significance")
assert check_story.significance_problems({"theme": "a b c d", "from_play": "x", "stakes": "a b c d", "choice": "a b c d",
                                          "changes": "a b c d"}) == ["significance.from_play is missing or too short to say anything"]
assert "significance.theme is missing or too short to say anything" in check_story.significance_problems(
    {"from_play": "a b c d", "stakes": "a b c d", "choice": "a b c d", "changes": "a b c d"})
assert check_story.significance_problems({k: "one two three four" for k in check_story.SIGNIFICANCE}) == []
print("significance ok")

# Endings: one that closes the journal must end the story; key and reward items should be the story's own.
done = {"op": "journal", "topic": "T", "entry": "e", "status": 2}
plain = {"plan": [{"op": "add_rule", "id": "won", "when": ["x"], "ops": [done, {"op": "give_item", "instance": "ITMW_AXE"}]},
                  {"op": "add_rule", "id": "found", "on": {"event": "took_item", "item": "ITSE_POUCH"}, "ops": []}]}
found = check_story.ending_warnings(plain)
assert any("won: closes the journal" in w for w in found) and any("plain game item (ITMW_AXE)" in w for w in found)
assert any("found: waits for a plain game item (ITSE_POUCH)" in w for w in found), found
own = {"plan": [{"op": "define_item", "item": "ITSE_POUCH"}, {"op": "define_item", "item": "ITMW_AXE"},
                {"op": "add_rule", "id": "won", "when": ["x"], "ops": [done, {"op": "give_item", "instance": "ITMW_AXE"},
                                                                        {"op": "give_item", "instance": "ITMI_GOLD"},
                                                                        {"op": "end_story", "story": "s", "outcome": "won"}]},
                {"op": "add_rule", "id": "found", "on": {"event": "took_item", "item": "ITSE_POUCH"}, "ops": []}]}
assert check_story.ending_warnings(own) == [], check_story.ending_warnings(own)
print("endings ok")

# An item worth more than the gold traded around it.
priced = {"plan": [{"op": "define_item", "item": "DIE", "value": 200}],
          "conversations": {"c": {"nodes": {"a": {"choices": [{"text": "x", "takes": {"item": "ITMI_GOLD", "count": 150}}]}}}}}
assert any("worth 200" in w and "150" in w for w in check_story.value_warnings(priced)), check_story.value_warnings(priced)
priced["plan"][0]["value"] = 100
assert check_story.value_warnings(priced) == []
print("values ok")

# Discoverability: a topic nobody points to, a night-only topic nobody says is at night, a deed nothing hints at.
from dm import discoverability  # noqa: E402
G = lambda *lines: {"start": "a", "nodes": {"a": {"line": lines[0], "choices": [{"text": l, "ends": True} for l in lines[1:]] or [{"text": "Gut.", "ends": True}]}}}
lost = {"title": "t", "plan": [
    {"op": "add_scene", "id": "hook", "npc": "VLK_1_HANNO", "graph": G("Geh zu Bodo.")},
    {"op": "add_topic", "id": "bodo", "npc": "VLK_2_BODO", "title": "Hanno schickt mich.", "requires": ["met"],
     "graph": G("Ja?"), "checks": [{"type": "hour", "from": 22, "to": 4}]},
    {"op": "add_topic", "id": "nobody", "npc": "VLK_3_GERDA", "title": "Und?", "requires": ["met"], "graph": G("Hm.")},
    {"op": "add_rule", "id": "deed", "when": [], "on": {"event": "used_object", "object": "BENCH"}, "ops": []}]}
found = {f["id"]: f["text"] for f in discoverability.findings(lost) if f["level"] == "guess"}
assert "bodo" in found and "no line says so" in found["bodo"], found          # Bodo is named, the night is not
assert "nobody" in found and "never named" in found["nobody"], found          # Gerda is never named
assert "deed" in found, found                                                  # nobody mentions a bench
lost["plan"][0]["graph"] = G("Geh heute Nacht zu Bodo, und zu Gerda. Setz dich auf die Bank.")
assert [f for f in discoverability.findings(lost) if f["level"] == "guess"] == []
assert any(w.startswith("discoverability: no hook") for w in discoverability.warnings({"plan": lost["plan"][1:]}))
print("discoverability ok")

# Conversations attached without an id stay apart: one NPC's lines never point to himself, nor mix with another's.
two = {"plan": [{"op": "attach_dialogue_graph", "npc": "BAU_901_BAUER", "graph": G("Frag Gesa.")},
                {"op": "attach_dialogue_graph", "npc": "BAU_904_BAUER", "graph": G("Ich bin Gesa.")}]}
sources = {s for s, _ in discoverability.model(two)["texts"]}
assert sources == {"attach_dialogue_graph:BAU_901_BAUER", "attach_dialogue_graph:BAU_904_BAUER"}, sources
print("attached apart ok")
