"""Story and dialogue graph tests against a fake game. Run: python3 python/dm/test_story.py"""

import pathlib
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


class Npc:
    def __init__(self, instance):
        self.instance = instance


class Handle:
    def __init__(self, world, key):
        self.world, self.key = world, key

    def remove(self):
        self.world.placed.remove(self.key)


class World:
    day, time, generation = 1, (20, 0), 1

    def __init__(self):
        self.npcs = {"NOV_A": Npc("NOV_A"), "NOV_B": Npc("NOV_B"), "PARLAN": Npc("PARLAN")}
        self.placed = []
        self.fail_place = None

    def instance_kind(self, name):
        name = name.upper()
        if name in ("NOV_A", "NOV_B", "PARLAN", "GHOST"):
            return "npc"
        return "item" if name.startswith("IT") else None

    def has_waypoint(self, name):
        return name.startswith("WP_")

    def find_npc(self, name):
        return self.npcs.get(name.upper())

    def remove_npc(self, npc):
        if self.fail_place == "remove":
            raise RuntimeError("engine refused")
        del self.npcs[npc.instance]

    def spawn(self, instance):
        npc = Npc(instance.upper())
        npc.set_position = lambda *p: setattr(npc, "at", p)
        npc.stand_here = lambda: None
        self.npcs[instance.upper()] = npc
        return npc

    def place_item(self, instance, waypoint):
        self.placed.append((instance, waypoint))
        return Handle(self, (instance, waypoint))


class Dialog:
    def __init__(self):
        self.bound = []
        self.reset()

    def reset(self):
        self.who, self.opened, self.open, self.lines = None, False, False, []
        self.choices, self.selection, self.is_busy = [], None, False

    def bind(self, npc): self.bound.append(npc.instance)
    def unbind(self, npc=None): self.bound.remove(npc.instance)
    def partner(self): return self.who
    def is_open(self): return self.open
    def busy(self): return self.is_busy
    def set_choices(self, c): self.choices = c
    def close(self): self.open, self.who = False, None

    def just_opened(self):
        value, self.opened = self.opened, False
        return value

    def say(self, text, **kw):
        self.lines.append(text)
        return True

    def poll_selection(self):
        value, self.selection = self.selection, None
        return value


fake = types.ModuleType("gothic")
fake.world, fake.dialog = World(), Dialog()
sys.modules["gothic"] = fake

from dm import graph as graphs  # noqa: E402
from dm import story as st  # noqa: E402

st.SAVES_DIR = pathlib.Path(tempfile.mkdtemp())
st.SAFE_TO_REMOVE.add("NOV_A")

GOOD = {"start": "a", "nodes": {
    "a": {"line": "Hallo.", "sets": "met", "choices": [
        {"text": "Mehr", "goto": "b"}, {"text": "Tschüss", "ends": True}]},
    "b": {"line": "Größe.", "choices": [{"text": "Zurück", "goto": "a"}]}}}


def test_conditional_choices():
    graph = {"start": "a", "nodes": {"a": {"line": "Hallo.", "choices": [
        {"text": "Wissend", "requires": ["known"], "ends": True},
        {"text": "Unwissend", "unless": "known", "ends": True},
        {"text": "Tschüss", "ends": True}]}}}
    assert graphs.validate(graph) is None
    bad = {"start": "a", "nodes": {"a": {"line": "x", "choices": [
        {"text": "y", "requires": ["k"], "ends": True}]}}}
    assert "only conditional" in graphs.validate(bad)

    flags = {}
    fake.dialog.reset()
    d = fake.dialog
    player = graphs.Player(lambda: {"NOV_B": graph}, lambda n: None, lambda: flags)
    d.who, d.opened, d.open = Npc("NOV_B"), True, True
    for _ in range(3):
        player.on_tick()
    assert d.choices == ["Unwissend", "Tschüss"]
    flags["known"] = True
    d.reset()
    d.who, d.opened, d.open = Npc("NOV_B"), True, True
    for _ in range(3):
        player.on_tick()
    assert d.choices == ["Wissend", "Tschüss"]
    d.selection = 0
    for _ in range(4):
        player.on_tick()
    assert d.lines[-1] == "Wissend"


def test_again_line():
    graph = {"start": "a", "nodes": {"a": {"line": "Erstes Mal.", "again": "Du schon wieder.",
             "sets": "met", "choices": [{"text": "Tschüss", "ends": True}]}}}
    flags = {}
    d = fake.dialog
    player = graphs.Player(lambda: {"NOV_B": graph}, lambda n: flags.update({n: True}), lambda: flags)
    for expected in ("Erstes Mal.", "Du schon wieder."):
        d.reset()
        d.who, d.opened, d.open = Npc("NOV_B"), True, True
        for _ in range(2):
            player.on_tick()
        assert d.lines == [expected], d.lines


def test_scene_and_rule():
    fake.world.__init__()
    fake.dialog.__init__()
    w, d = fake.world, fake.dialog
    fake.player = types.SimpleNamespace(position=(0, 0, 0), given=[],
                                        give_item=lambda i, c=1: fake.player.given.append((i, c)))
    started = []
    for n in w.npcs.values():
        n.position, n.alive = (9000, 0, 0), True
        n.start_dialog = lambda who=n: (started.append(who.instance), setattr(d, "open", True), setattr(d, "who", who))
    s = st.Story()
    s.generation = w.generation
    s.apply_plan({"reason": "r", "ops": [
        {"op": "add_scene", "id": "s", "npc": "PARLAN", "graph": GOOD, "requires": ["ready"]},
        {"op": "add_rule", "id": "pay", "when": ["met"], "ops": [{"op": "give_item", "instance": "ITGOLD", "count": 5}]},
    ]})
    s.on_tick()
    assert started == []                 # condition not met
    s.state["flags"]["ready"] = True
    s.on_tick()
    assert started == []                 # too far away
    w.npcs["PARLAN"].position = (100, 0, 0)
    s.on_tick()
    assert started == ["PARLAN"] and d.bound == ["PARLAN"]
    assert "PARLAN" in s.graphs_now()

    s.state["flags"]["met"] = True
    s.on_tick()
    assert fake.player.given == []       # rules wait until the conversation ends
    d.open, d.who = False, None
    s.on_tick()
    assert d.bound == [] and s.state["scenes"]["s"]["done"]
    assert "PARLAN" not in s.graphs_now()
    s.on_tick()
    assert fake.player.given == [("ITGOLD", 5)] and s.state["rules"]["pay"]["fired"]
    s.on_tick()
    assert fake.player.given == [("ITGOLD", 5)] and started == ["PARLAN"]  # both happen once


def rejected(story, ops, fragment):
    try:
        story.validate(ops)
    except st.PlanError as err:
        assert fragment in str(err), err
        return
    raise AssertionError(f"accepted: {ops}")


def test_graph_validation():
    assert graphs.validate(GOOD) is None
    assert "start" in graphs.validate({"start": "x", "nodes": {}})
    assert "nowhere" in graphs.validate({"start": "a", "nodes": {
        "a": {"line": "x", "choices": [{"text": "y", "goto": "z"}]}}})
    assert "never end" in graphs.validate({"start": "a", "nodes": {
        "a": {"line": "x", "choices": [{"text": "y", "goto": "b"}]},
        "b": {"line": "x", "choices": [{"text": "y", "goto": "a"}]}}})


def test_validation():
    s = st.Story()
    rejected(s, [], "empty")
    rejected(s, [{"op": "bogus"}], "unknown")
    rejected(s, [{"op": "remove_npc", "instance": "PARLAN"}], "safe list")
    rejected(s, [{"op": "remove_npc", "instance": "NOPE"}], "not an NPC")
    rejected(s, [{"op": "remove_npc", "instance": "GHOST"}], "safe list")
    rejected(s, [{"op": "place_item", "instance": "ITX", "waypoint": "BAD"}], "waypoint")
    rejected(s, [{"op": "place_item", "instance": "NOV_A", "waypoint": "WP_1"}], "not an item")
    rejected(s, [{"op": "commit_fact", "id": "a", "text": "x", "known_by": ["NOPE"]}], "not an NPC")
    rejected(s, [{"op": "commit_fact", "id": "a", "text": "x"},
                 {"op": "commit_fact", "id": "a", "text": "y"}], "already committed")
    rejected(s, [{"op": "remove_npc", "instance": "NOV_A"},
                 {"op": "attach_dialogue_graph", "npc": "NOV_A", "graph": GOOD}], "removed")
    assert s.log == [] and s.state == st.empty_state()


def test_apply_and_rollback():
    fake.world.__init__()
    s = st.Story()
    s.apply_plan({"reason": "r", "ops": [
        {"op": "commit_fact", "id": "f", "text": "Geheimnis", "known_by": ["PARLAN"]},
        {"op": "place_item", "instance": "ITCLUE", "waypoint": "WP_1"},
        {"op": "remove_npc", "instance": "NOV_A"},
    ]})
    assert fake.world.placed == [("ITCLUE", "WP_1")]
    assert "NOV_A" not in fake.world.npcs
    assert s.state["facts"]["f"]["known_by"] == ["PARLAN"]
    assert s.state["removed"] == ["NOV_A"]

    # removal fails after the item is placed: the item comes back out
    fake.world.__init__()
    fake.world.fail_place = "remove"
    s = st.Story()
    try:
        s.apply_plan({"reason": "r", "ops": [
            {"op": "remove_npc", "instance": "NOV_A"},
            {"op": "place_item", "instance": "ITCLUE", "waypoint": "WP_1"},
        ]})
        raise AssertionError("expected failure")
    except RuntimeError:
        pass
    assert fake.world.placed == []
    assert s.log == [] and s.state == st.empty_state()


def test_return_npc():
    fake.world.__init__()
    fake.dialog.__init__()
    s = st.Story()
    rejected(s, [{"op": "return_npc", "instance": "NOV_A", "position": [1, 2, 3]}], "not removed")
    s.apply_plan({"reason": "gone", "ops": [{"op": "remove_npc", "instance": "NOV_A"}]})
    s.apply_plan({"reason": "back", "ops": [
        {"op": "return_npc", "instance": "NOV_A", "position": [1, 2, 3]},
        {"op": "attach_dialogue_graph", "npc": "NOV_A", "graph": GOOD},
    ]})
    assert fake.world.npcs["NOV_A"].at == (1, 2, 3)
    assert s.state["removed"] == [] and "NOV_A" in s.state["graphs"]
    assert fake.dialog.bound == ["NOV_A"]


def test_queue_waits_for_safe_point():
    fake.world.__init__()
    fake.dialog.reset()
    s = st.Story()
    s.generation = fake.world.generation
    s.submit("r", [{"op": "set_flag", "name": "a", "value": 1}])
    fake.dialog.who = Npc("PARLAN")
    s.on_tick()
    assert s.log == []
    fake.dialog.who = None
    s.on_tick()
    assert s.state["flags"] == {"a": 1} and s.results[-1]["ok"]


def test_save_load_does_not_reapply_world():
    fake.world.__init__()
    fake.dialog.__init__()
    s = st.Story()
    s.apply_plan({"reason": "Märchen", "ops": [
        {"op": "commit_fact", "id": "f", "text": "Größe"},
        {"op": "place_item", "instance": "ITCLUE", "waypoint": "WP_1"},
        {"op": "attach_dialogue_graph", "npc": "NOV_B", "graph": GOOD},
    ]})
    s.save("slot1.sav")
    saved_state = s.state

    fake.world.placed.clear()
    other = st.Story()
    other.load("slot1.sav")
    assert other.state == saved_state
    assert fake.world.placed == []

    # handles are gone after loading, so graphs bind again on the new generation
    fake.dialog.bound.clear()
    other.on_tick()
    assert fake.dialog.bound == ["NOV_B"]

    other.load("never_saved.sav")
    assert other.state == st.empty_state()


def test_player():
    fake.dialog.reset()
    flags = []
    player = graphs.Player(lambda: {"NOV_B": GOOD}, flags.append)
    d = fake.dialog

    def pump(picks=None):
        if picks is not None:
            d.selection = picks
        for _ in range(8):
            player.on_tick()

    d.who, d.opened, d.open = Npc("NOV_B"), True, True
    pump()
    assert d.lines == ["Hallo."] and flags == ["met"]
    assert d.choices == ["Mehr", "Tschüss"]

    # the hero speaks the chosen line, then the NPC answers
    pump(0)
    assert d.lines == ["Hallo.", "Mehr", "Größe."]
    assert d.choices == ["Zurück"]

    # stepping back is silent and shows the earlier choices
    pump(0)
    assert d.lines == ["Hallo.", "Mehr", "Größe."] and flags == ["met"]
    assert d.choices == ["Mehr", "Tschüss"]

    # asking again gets the answer again
    pump(0)
    assert d.lines[-2:] == ["Mehr", "Größe."] and len(d.lines) == 5

    # the hero says the closing line before the conversation ends
    pump(0)
    pump(1)
    assert d.lines[-1] == "Tschüss" and not d.is_open()

    # a line refused while the UI is busy is retried
    d.reset()
    d.who, d.opened, d.open = Npc("NOV_B"), True, True
    real_say, attempts = d.say, []
    d.say = lambda text, **kw: attempts.append(text) or len(attempts) > 1
    player.on_tick()
    player.on_tick()
    assert len(attempts) == 2
    d.say = real_say


for test in (test_graph_validation, test_validation, test_apply_and_rollback, test_return_npc, test_conditional_choices, test_again_line, test_scene_and_rule,
             test_queue_waits_for_safe_point, test_save_load_does_not_reapply_world,
             test_player):
    test()
print("story tests passed")
