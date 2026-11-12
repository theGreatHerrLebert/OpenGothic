"""Stories that end gracefully, and the game's entry points, against a fake game. Run: python3 python/dm/test_endings.py"""

import io
import json
import pathlib
import sys
import tempfile
import types
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
fake = types.ModuleType("gothic")
sys.modules["gothic"] = fake


class Npc:
    def __init__(self, instance):
        self.instance, self.dead, self.alive, self.id = instance, False, True, 1
        self.position = (0, 0, 0)

    def can_see_player(self): return False


class World:
    day, time, generation = 3, (12, 0), 1

    def __init__(self):
        self.people = {"BAU_901_BAUER": Npc("BAU_901_BAUER"), "BAU_904_BAUER": Npc("BAU_904_BAUER")}

    def instance_kind(self, n): return "npc" if n.upper().startswith("BAU") else "item" if n.upper().startswith("IT") else None
    def has_waypoint(self, n): return n.startswith("NW_")
    def find_npc(self, n): return self.people.get(n.upper())
    def take_perceptions(self): return []


fake.world = World()
fake.player = types.SimpleNamespace(position=(0, 0, 0), guild=0, items=[], busy=False, level=1)
fake.daedalus = types.SimpleNamespace(get=lambda n, i=0: 1 if n == "KAPITEL" else 0)
fake.dialog = types.SimpleNamespace(partner=lambda: None, bind=lambda n: None, unbind=lambda n=None: None,
                                    is_open=lambda: False, set_topics=lambda n, t: None, narrating=lambda: False)
fake.journal = lambda *a: None

from dm import api, checks, play_story, story as st  # noqa: E402

st.SAVES_DIR = pathlib.Path(tempfile.mkdtemp())
st.ATTACHABLE.update(["BAU_901_BAUER", "BAU_904_BAUER"])
GRAPH = {"start": "a", "nodes": {"a": {"line": "Na?", "choices": [{"text": "Nichts.", "ends": True}]}}}
STORY = {"title": "Der Zaun", "plan": [
    {"op": "attach_dialogue_graph", "npc": "BAU_901_BAUER", "graph": GRAPH},
    {"op": "add_rule", "id": "later", "when": ["never_set"], "ops": [{"op": "set_flag", "name": "x", "value": True}]},
    {"op": "add_topic", "id": "ask", "npc": "BAU_904_BAUER", "title": "Der Zaun?", "graph": GRAPH}],
    "closures": [{"id": "too_late", "outcome": "timeout", "checks": [{"type": "story_age", "days": 2}],
                  "ops": [{"op": "set_flag", "name": "forgotten", "value": True}]}]}

# prepare: closures become rules ending the story, ids and story_age name the story, the cast is found.
start = play_story.prepare(STORY, "story_9")
assert start["cast"] == ["BAU_901_BAUER", "BAU_904_BAUER"] and start["story"] == "story_9"
closure = [o for o in start["ops"] if o.get("id") == "story_9:too_late"][0]
assert closure["checks"] == [{"type": "story_age", "days": 2, "story": "story_9"}]
assert closure["ops"][-1] == {"op": "end_story", "story": "story_9", "outcome": "timeout"}


def play(story_start, requires=None):
    out = io.StringIO()
    with redirect_stdout(out):
        api.play(story_start["title"], story_start["ops"], requires, story_start["story"], story_start["cast"])
    return json.loads(out.getvalue().strip().splitlines()[-1])


# api.play: refuses where the story's requirements fail, else queues it with its beginning.
st._story = st.Story()
fake.start_called = []
sys.modules["dm"].start = lambda: fake.start_called.append(1)
reply = play(start, [{"type": "chapter", "from": 3}])
assert reply["ok"] is False and "not yet" in reply["error"] and st._story.queue == []
assert play(start, [{"type": "chapter", "to": 9, "from": 9, "nope": 1}])["ok"] is False
assert play(start, [{"type": "nonsense"}])["error"].startswith("bad requirement")
assert play(start)["ok"] and fake.start_called
s = st._story
s.apply_plan(s.queue.pop(0))
assert s.state["stories"]["story_9"] == {"title": "Der Zaun", "started": 3, "cast": ["BAU_901_BAUER", "BAU_904_BAUER"],
                                         "ended": None}
assert s.topic("story_9:ask") is not None

# Two days on, the timeout closure fires and retires the rest: topics hidden, waiting rules never fire.
assert not checks.all_hold([{"type": "story_age", "days": 2, "story": "story_9"}])
fake.world.day = 5
s._tick_rules()
assert s.state["stories"]["story_9"]["ended"] == "timeout" and s.state["flags"]["story_9:forgotten"]
assert s.topic("story_9:ask") is None
s.state["flags"]["story_9:never_set"] = True
s._tick_rules()
assert not s.state["rules"]["story_9:later"]["fired"]
health = s.health()["story_9"]
assert health["ended"] == "timeout" and health["days"] == 2 and health["rules_waiting"] == 1

# The safety net: a cast member dies and no closure speaks of it, so the story ends quietly by itself.
fake.world.day = 3
s2 = st.Story()
second = play_story.prepare(dict(STORY, closures=[]), "story_10")
s2.apply_plan({"reason": "r", "ops": [{"op": "begin_story", "story": "story_10", "title": "t", "day": 3,
                                      "cast": second["cast"]}] + second["ops"]})
s2._tick_cast()
assert s2.state["stories"]["story_10"]["ended"] is None
fake.world.people["BAU_904_BAUER"].dead = True
s2._tick_cast()
assert s2.state["stories"]["story_10"]["ended"] == "cast_dead:BAU_904_BAUER"
# ... and it survives a save and load.
s2.save("endings")
s3 = st.Story()
s3.load("endings")
assert s3.state["stories"]["story_10"]["ended"] == "cast_dead:BAU_904_BAUER"

# A closure that speaks of the death itself is left to fire; the net stays out of it.
fake.world.people["BAU_904_BAUER"].dead = False
mourned = dict(STORY, closures=[{"id": "mourned", "outcome": "mourned",
                                 "checks": [{"type": "npc_dead", "npc": "BAU_904_BAUER"}], "ops": []}])
third = play_story.prepare(mourned, "story_11")
s4 = st.Story()
s4.apply_plan({"reason": "r", "ops": [{"op": "begin_story", "story": "story_11", "title": "t", "day": 3,
                                      "cast": third["cast"]}] + third["ops"]})
fake.world.people["BAU_904_BAUER"].dead = True
s4._tick_cast()
assert s4.state["stories"]["story_11"]["ended"] is None
s4._tick_rules()
assert s4.state["stories"]["story_11"]["ended"] == "mourned"

# api.validate and api.submit answer with ok or the problem.
out = io.StringIO()
with redirect_stdout(out):
    api.validate([{"op": "nope"}])
    api.submit("r", [{"op": "set_flag", "name": "y", "value": True}])
lines = [json.loads(line) for line in out.getvalue().strip().splitlines()]
assert lines[0]["ok"] is False and "unknown operation" in lines[0]["error"] and lines[1] == {"ok": True, "queued": True}
# A story is bound to the timeline it was written for: the review's sequence. The player steals, a story is written
# from that moment, he reloads to before the theft: the story no longer fits and is refused.
from dm import observer  # noqa: E402
observer.TIMELINES_PATH, observer.SAVES_DIR = st.SAVES_DIR / "timelines.json", st.SAVES_DIR
ob = observer._observer = observer.Observer()
fake.world.time, fake.world.day = (12, 0), 3
ob.on_new_game()
ob.on_save("before_theft")
ob.seq += 5                                                          # the theft and what followed
written_for = {"timeline": ob.timeline, "seq": ob.seq}               # the snapshot the author writes from
fresh = play_story.prepare(dict(STORY, closures=[]), "story_12")
st._story = st.Story()
out = io.StringIO()
with redirect_stdout(out):
    api.play(fresh["title"], fresh["ops"], None, fresh["story"], fresh["cast"], written_for)
assert json.loads(out.getvalue())["ok"], out.getvalue()               # still the same game: it starts
ob.on_load("before_theft")                                          # back to before the theft
out = io.StringIO()
with redirect_stdout(out):
    api.play(fresh["title"], fresh["ops"], None, "story_13", fresh["cast"], written_for)
reply = json.loads(out.getvalue())
assert reply["ok"] is False and reply["error"].startswith("stale"), reply
ob.on_save("later")                                                 # a save in the new timeline, loaded again
ob.on_load("later")
out = io.StringIO()
with redirect_stdout(out):
    api.play(fresh["title"], fresh["ops"], None, "story_14", fresh["cast"], {"timeline": ob.branch() and
                                                                            list(ob.branch())[-1], "seq": 0})
assert json.loads(out.getvalue())["ok"]                              # a story from before the fork still fits
print("endings ok")
