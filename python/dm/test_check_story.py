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
