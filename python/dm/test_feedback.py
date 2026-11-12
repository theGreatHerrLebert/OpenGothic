"""In-game feedback tests. Run: python3 python/dm/test_feedback.py

The game is faked, so this proves the menu and what gets recorded, not that the hotkeys reach Python.
"""

import json
import pathlib
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import feedback  # noqa: E402

# The menu: a moment is one key, a rating is three answers, and stray keys change nothing.
menu = feedback.Menu()
assert menu.press("1") == (None, None)                      # closed: digits mean nothing
text, entry = menu.press("feedback")
assert text == feedback.MAIN and entry is None
text, entry = menu.press("4")
assert text == feedback.SAVED and entry == {"kind": "moment", "tag": "unlogisch"} and menu.state == "closed"

menu.press("feedback")
assert menu.press("5", None) == (feedback.NO_STORY, None)   # nothing to rate

menu.press("feedback")
text, _ = menu.press("5", "Die eine Flasche")
assert text.startswith("„Die eine Flasche“")
assert menu.press("3") == (None, None)                      # yes/no question ignores a 3
assert menu.press("2")[0] == feedback.ASK_INTEREST
assert menu.press("4")[0] == feedback.ASK_DEED
assert menu.press("1")[0] == feedback.ASK_ORIGINAL
assert menu.press("2")[0] == feedback.ASK_WAY
assert menu.press("4") == (None, None)                      # only three ways
assert menu.press("2")[0] == feedback.ASK_SURPRISE
assert menu.press("1")[0] == feedback.ASK_BROKE
text, entry = menu.press("1")
assert text == feedback.RATED
assert entry == {"kind": "rating", "story": "Die eine Flasche", "worth": "no", "interest": 4, "deed": "yes",
                 "original": "no", "way": "luck", "surprised": "yes", "broke": "no", "played": True}

with tempfile.TemporaryDirectory() as d:
    log = pathlib.Path(d) / "feedback.jsonl"
    log.write_text("\n".join(json.dumps(e) for e in [
        entry, dict(entry, interest=2, way="alone", surprised="no", broke="yes"), {"kind": "moment", "tag": "gut"},
        {"kind": "rating", "story": "Alt", "worth": "yes", "interest": 3, "deed": "no", "original": "yes"}]) + "\n{torn")
    summary = feedback.report(log)
    flasche = summary["Die eine Flasche"]
    assert flasche["ratings"] == 2 and flasche["technical"]["ran_clean"] == 0.5 and flasche["narrative"]["interest"] == 3.0
    assert flasche["experience"] == {"worth_playing": 0.0, "found_way_alone": 0.5, "surprised": 0.5}
    assert summary["Alt"]["experience"]["surprised"] is None    # a rating from before the question counts as unknown

menu.press("feedback")
menu.press("5", "X")
assert menu.press("feedback") == ("", None) and menu.state == "closed"   # Alt+F cancels a rating halfway
assert menu.press("1") == (None, None)

# The panel never shows story text beyond the title.
for fixed in (feedback.MAIN, feedback.ASK_WORTH, feedback.ASK_INTEREST, feedback.ASK_DEED, feedback.ASK_ORIGINAL,
              feedback.ASK_WAY, feedback.ASK_SURPRISE, feedback.ASK_BROKE):
    assert "Flasche" not in fixed

# Which story is current: internal log entries do not count.
story_module = types.SimpleNamespace(_story=types.SimpleNamespace(log=[
    {"reason": "Der Fall Tilo", "ops": [{"op": "commit_fact"}]},
    {"reason": "player", "ops": [{"op": "set_flag"}]},
    {"reason": "Regel: x", "ops": [{"op": "fire_rule"}]},
    {"reason": "warten", "ops": [{"op": "do_nothing"}]},
]))
assert feedback.current_story(story_module) == "Der Fall Tilo"
story_module._story.log = []
assert feedback.current_story(story_module) is None

with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    events = d / "events.jsonl"
    events.write_text("".join(json.dumps({"seq": i}) + "\n" for i in range(30)) + "{half\n")
    recent = feedback.recent_events(events, 5)
    assert [e["seq"] for e in recent] == [25, 26, 27, 28, 29]   # a torn last line is skipped, not counted
    assert feedback.recent_events(d / "missing.jsonl") == []
    assert feedback.recent_events(events, 100)[0]["seq"] == 0   # a short file keeps its first line

    # Context inside a story conversation names the conversation, node and line.
    graph = {"start": "a", "nodes": {}}
    story_module = types.SimpleNamespace(
        _story=types.SimpleNamespace(log=[{"reason": "Die eine Flasche", "ops": [{"op": "commit_fact"}]}],
                                     graphs_now=lambda: {"NOV_610_NOVIZE": graph}),
        _player=types.SimpleNamespace(stage="offer", graph=graph, partner="NOV_610_NOVIZE", path=["a", "c"],
                                      line="Was willst du?"))
    fake = types.SimpleNamespace(
        world=types.SimpleNamespace(time=(14, 5), day=3),
        player=types.SimpleNamespace(waypoint="NW_MONASTERY_01", room="", position=(1.0, 2.0, 3.0)),
        dialog=types.SimpleNamespace(partner=lambda: types.SimpleNamespace(instance="NOV_610_NOVIZE")))
    feedback.EVENTS = events
    found = feedback.context(fake, story_module)
    assert found["story"] == "Die eine Flasche" and found["conversation"] == "NOV_610_NOVIZE"
    assert found["node"] == "c" and found["line"] == "Was willst du?" and found["hour"] == 14
    assert [e["seq"] for e in found["events"]] == list(range(20, 30))   # last 10 events, torn line skipped

    # Outside a conversation there is no line to blame.
    fake.dialog.partner = lambda: None
    assert "line" not in feedback.context(fake, story_module)

    # Stored entries come back, and a rating marks its story played.
    path = d / "feedback.jsonl"
    feedback.append({"kind": "moment", "tag": "gut", "story": "A"}, path)
    feedback.append({"kind": "rating", "story": "B", "played": True}, path)
    with path.open("a") as f:
        f.write("{half\n")
    assert len(feedback.load(path)) == 2
    assert feedback.played(path) == {"B"}
    assert feedback.load(d / "none.jsonl") == []

print("feedback ok")
