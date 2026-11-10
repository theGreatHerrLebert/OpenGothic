"""Story library tests: stages, the accept gate and blind ids. Run: python3 python/dm/test_library.py"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import library  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    root = pathlib.Path(d)
    (root / "stories").mkdir()
    library.EXPERIMENT = root
    library.STAGE_FILE = root / "story_stages.json"
    story = root / "stories" / "s1_1.json"
    story.write_text(json.dumps({"title": "Zweite", "premise": "p", "plan": []}), encoding="utf-8")
    (root / "stories" / "s1_1.first.json").write_text("{}", encoding="utf-8")       # drafts are not stories
    (root / "stories" / "x1_1.json").write_text(json.dumps({"title": "Erste", "bonus": True, "plan": []}), encoding="utf-8")

    sid = library.blind_id("s1_1")
    assert library.path_of(sid) == story and library.path_of("nope") is None
    listed = library.entries()
    assert [e["id"] for e in listed][0] == library.DEMO_ID                # the demo comes first
    assert [e["title"] for e in listed[1:]] == ["Erste", "Zweite"]        # then by title, not by file name
    assert all("s1_1" not in json.dumps(e) for e in listed)               # the file name never leaves the module

    assert library.stage_of(sid) == (library.PROPOSED, False)
    assert library.stage_of(library.DEMO_ID)[0] == library.ACCEPTED
    assert library.move(sid, library.ACCEPTED, []) == "cannot move from proposed to accepted"
    assert library.move(sid, "done", []) == "unknown stage"
    assert library.move(sid, library.IN_PROGRESS, []) is None
    assert library.move(sid, library.ACCEPTED, ["2 lines not reviewed"]).startswith("not ready")
    assert library.stage_of(sid)[0] == library.IN_PROGRESS
    assert library.move(sid, library.ACCEPTED, []) is None
    assert library.stage_of(sid) == (library.ACCEPTED, False)

    story.write_text(json.dumps({"title": "Zweite", "premise": "geändert", "plan": []}), encoding="utf-8")
    assert library.stage_of(sid) == (library.IN_PROGRESS, True)            # a changed story needs a new look
    assert library.move(sid, library.ACCEPTED, []) is None
    assert library.stage_of(sid) == (library.ACCEPTED, False)

    # a caller's own fingerprint (every line and recording) decides, not just the file
    assert library.move(sid, library.IN_PROGRESS, []) is None
    assert library.move(sid, library.ACCEPTED, [], rev="lines-v1") is None
    assert library.stage_of(sid, rev="lines-v1") == (library.ACCEPTED, False)
    assert library.stage_of(sid, rev="lines-v2") == (library.IN_PROGRESS, True)   # a re-recorded line reopens it

    library.STAGE_FILE.write_text("{half", encoding="utf-8")
    assert library.stage_of(sid) == (library.PROPOSED, False)              # a broken file never breaks the page

# the plan plays the dialogue that was voiced, not an older copy inside the story
written = {"start": "a", "nodes": {"a": {"line": "Alt.", "choices": []}}}
voiced = {"start": "a", "nodes": {"a": {"line": "Neu.", "choices": []}}}
plan = [{"op": "add_scene", "id": "s", "graph": written},
        {"op": "add_rule", "id": "r", "when": ["x"], "ops": [{"op": "attach_dialogue_graph", "graph": written}]}]
synced = library._with_graphs(plan, {"K": written}, {"K": voiced})
assert synced[0]["graph"] == voiced and synced[1]["ops"][0]["graph"] == voiced
assert plan[0]["graph"] == written                                       # the input stays as it was

index = {"a": "t:1", "a__voice": "a:1", "b": "t:2", "b__voice": None}     # b has no recording, so no voice review
assert library.gate([], {"a": {"verdict": "approve"}, "a__voice": {"verdict": "approve"},
                         "b": {"verdict": "approve"}}, index) == []
assert library.gate(["x"], {}, index) == ["1 check errors", "3 lines not reviewed"]
assert library.gate([], {"a": {"verdict": "reject"}, "a__voice": {"verdict": "approve"},
                         "b": {"verdict": "approve"}}, index) == ["1 lines rejected"]
print("ok")
