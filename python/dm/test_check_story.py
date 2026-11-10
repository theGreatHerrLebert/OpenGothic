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
