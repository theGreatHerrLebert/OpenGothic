"""Story and dialogue graph tests against a fake game. Run: python3 python/dm/test_story.py"""

import pathlib
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


class Npc:
    dead = False
    count = 0

    def __init__(self, instance):
        self.instance = instance
        Npc.count += 1
        self.id = Npc.count   # each NPC object its own, as the game's world index tells them apart


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

    def take_perceptions(self):
        taken, self.perceived = getattr(self, "perceived", []), []
        return taken

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

    def place_item(self, instance, waypoint, count=1, position=None):
        self.placed.append((instance, waypoint))
        return Handle(self, (instance, waypoint))


class Dialog:
    def __init__(self):
        self.bound = []
        self.reset()

    def reset(self):
        self.who, self.opened, self.open, self.lines = None, False, False, []
        self.choices, self.selection, self.is_busy = [], None, False
        self.topics, self.chosen_topic, self.ended_topics = {}, None, 0

    def set_topics(self, npc, topics): self.topics[npc.instance] = list(topics)

    def take_topic(self):
        value, self.chosen_topic = self.chosen_topic, None
        return value

    def end_topic(self):
        self.ended_topics += 1
        return True

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
fake.player = types.SimpleNamespace(position=(0, 0, 0), busy=False, guild=0)
fake.daedalus = types.SimpleNamespace(get=lambda name, i=0: -1)
sys.modules["gothic"] = fake

from dm import graph as graphs  # noqa: E402
from dm import story as st  # noqa: E402

st.SAVES_DIR = pathlib.Path(tempfile.mkdtemp())
st.SAFE_TO_REMOVE.add("NOV_A")
st.ATTACHABLE.update(["NOV_A", "NOV_B", "GHOST"])

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


def test_returns_to_menu():
    graph = {"start": "a", "nodes": {
        "a": {"line": "Menü.", "choices": [{"text": "Frage", "goto": "b"}, {"text": "Tschüss", "ends": True}]},
        "b": {"line": "Antwort.", "returns": "a", "choices": []}}}
    assert graphs.validate(graph) is None
    assert "returns nowhere" in graphs.validate({"start": "a", "nodes": {"a": {"line": "x", "returns": "z", "choices": []}}})
    d = fake.dialog
    d.reset()
    player = graphs.Player(lambda: {"NOV_B": graph}, lambda n: None)
    d.who, d.opened, d.open = Npc("NOV_B"), True, True
    for _ in range(3):
        player.on_tick()
    d.selection = 0
    for _ in range(7):
        player.on_tick()
    assert d.lines == ["Menü.", "Frage", "Antwort."], d.lines
    assert d.choices == ["Frage", "Tschüss"]


def test_handed_over_but_nothing_to_play():
    # The game handed a conversation over (a trip) and the special dialogue broke or no longer applies: it is closed,
    # never left open and empty.
    d = fake.dialog
    d.reset()
    def broken(npc):
        raise TypeError("a bug")
    player = graphs.Player(lambda: {}, lambda n: None, get_special=broken)
    d.who, d.opened, d.open = Npc("VALENTINO"), True, True
    player.on_tick()
    assert not d.open and player.stage == "idle"


def test_questions_are_asked_once():
    graph = {"start": "a", "nodes": {
        "a": {"line": "Menü.", "choices": [
            {"text": "Frage", "goto": "b"}, {"text": "Immer", "goto": "c", "repeat": True},
            {"text": "Tschüss", "ends": True}]},
        "b": {"line": "Antwort.", "returns": "a", "choices": []},
        "c": {"line": "Wieder.", "returns": "a", "choices": []}}}
    flags = {}
    d = fake.dialog
    d.reset()
    player = graphs.Player(lambda: {"NOV_B": graph}, lambda n: flags.update({n: True}), lambda: flags)
    d.who, d.opened, d.open = Npc("NOV_B"), True, True
    for _ in range(3):
        player.on_tick()
    d.selection = 0
    for _ in range(7):
        player.on_tick()
    assert d.choices == ["Immer", "Tschüss"], d.choices
    d.selection = 0
    for _ in range(7):
        player.on_tick()
    assert d.choices == ["Immer", "Tschüss"], d.choices


def test_variant_line():
    graph = {"start": "a", "nodes": {"a": {"line": "Normal.", "variants": [{"when": "mage", "line": "Meister!"}],
             "choices": [{"text": "Tschüss", "ends": True}]}}}
    flags = {"mage": True}
    d = fake.dialog
    d.reset()
    player = graphs.Player(lambda: {"NOV_B": graph}, lambda n: None, lambda: flags)
    d.who, d.opened, d.open = Npc("NOV_B"), True, True
    player.on_tick()
    player.on_tick()
    assert d.lines == ["Meister!"], d.lines


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
    fake.player = types.SimpleNamespace(position=(0, 0, 0), given=[], busy=False, guild=1,
                                        give_item=lambda i, c=1: fake.player.given.append((i, c)))
    started = []
    for n in w.npcs.values():
        n.position, n.alive, n.sees = (9000, 0, 0), True, True
        n.can_see_player = lambda who=n: who.sees
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
    fake.player.guild = 5
    fake.daedalus = types.SimpleNamespace(get=lambda name, i=0: 5)
    s.state["scenes"]["s"]["not_guilds"] = ["GIL_KDF"]
    s.on_tick()
    assert started == []                 # too important
    s.state["scenes"]["s"]["not_guilds"] = []
    fake.daedalus = types.SimpleNamespace(get=lambda name, i=0: -1)
    w.npcs["PARLAN"].sees = False
    s.on_tick()
    assert started == []                 # through a wall
    w.npcs["PARLAN"].sees = True
    fake.player.busy = True
    s.on_tick()
    assert started == []                 # in bed
    fake.player.busy = False
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

    # a night rule waits for dark and for the player to be away
    s.apply_plan({"reason": "r", "ops": [{"op": "add_rule", "id": "night", "when": [], "after_night_of": 1,
                  "unseen_by_near": "PARLAN", "ops": [{"op": "give_item", "instance": "ITNIGHT"}]}]})
    w.time = (12, 0)
    w.npcs["PARLAN"].position = (100, 0, 0)
    s.on_tick()
    assert ("ITNIGHT", 1) not in fake.player.given
    w.day = 2                            # slept through it: morning of the next day
    s.on_tick()
    assert ("ITNIGHT", 1) not in fake.player.given   # the player is still close by
    w.npcs["PARLAN"].position = (9000, 0, 0)
    s.on_tick()
    assert ("ITNIGHT", 1) in fake.player.given
    w.time = (20, 0)
    w.day = 1


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


def test_rule_contents_are_checked_when_submitted():
    s = st.Story()
    rule = {"op": "add_rule", "id": "r", "when": ["x"], "ops": [{"op": "place_item", "instance": "ITX", "waypoint": "BAD"}]}
    rejected(s, [rule], "no such waypoint")
    bad_graph = {"op": "add_rule", "id": "r", "when": ["x"], "ops": [
        {"op": "attach_dialogue_graph", "npc": "NOV_B", "graph": {"start": "a", "nodes": {}}}]}
    rejected(s, [bad_graph], "bad dialogue graph")
    rejected(s, [{"op": "attach_dialogue_graph", "npc": "PARLAN", "graph": GOOD}], "cannot be taken over")


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
    assert d.lines == ["Hallo."] and [x for x in flags if not x.startswith("asked:")] == ["met"]
    assert d.choices == ["Mehr", "Tschüss"]

    # the hero speaks the chosen line, then the NPC answers
    pump(0)
    assert d.lines == ["Hallo.", "Mehr", "Größe."]
    assert d.choices == ["Zurück"]

    # stepping back is silent and shows the earlier choices
    pump(0)
    assert d.lines == ["Hallo.", "Mehr", "Größe."] and [x for x in flags if not x.startswith("asked:")] == ["met"]
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


def test_drawing_a_weapon_is_perceived():
    fake.world.__init__()
    fake.dialog.__init__()
    watcher = types.SimpleNamespace(instance="PARLAN", alive=True, can_see_player=lambda: True)
    fake.world.npcs_near = lambda radius: [watcher]
    fake.player = types.SimpleNamespace(position=(0, 0, 0), given=[], busy=False, guild=0, weapon="melee",
                                        give_item=lambda i, c=1: fake.player.given.append((i, c)))
    s = st.Story()
    s.generation = fake.world.generation
    s.apply_plan({"reason": "r", "ops": [{"op": "add_rule", "id": "armed", "when": [],
                                          "on": {"event": "drew_weapon", "seen_by": "PARLAN"},
                                          "ops": [{"op": "give_item", "instance": "ITREWARD"}]}]})
    s.on_tick()
    assert fake.player.given == []       # already drawn when the story began: not an event
    fake.player.weapon = "none"
    s.on_tick()
    fake.player.weapon = "magic"
    s.on_tick()
    assert fake.player.given == [("ITREWARD", 1)]
    del fake.world.npcs_near


def test_narration_waits_for_quiet():
    fake.world.__init__()
    fake.dialog.__init__()
    played, state = [], {"busy": True}
    fake.dialog.narrating = lambda: state["busy"]
    fake.dialog.narrate = lambda text, ms=0, wav="": played.append(text) or True
    fake.player = types.SimpleNamespace(position=(0, 0, 0), given=[], busy=False, guild=0)
    s = st.Story()
    s.generation = fake.world.generation
    rejected(s, [{"op": "narrate", "text": "  "}], "needs text")
    s.apply_plan({"reason": "r", "ops": [{"op": "narrate", "text": "Es war ein ruhiger Morgen.", "voice": "10"},
                                         {"op": "narrate", "text": "Zu ruhig."}]})
    s.on_tick()
    assert played == []                              # another line is still running
    state["busy"] = False
    s.on_tick()
    s.on_tick()
    assert played == ["Es war ein ruhiger Morgen."]  # the second waits for the quiet gap
    s.narrator_quiet_until = 0
    s.on_tick()
    assert played == ["Es war ein ruhiger Morgen.", "Zu ruhig."]
    s.apply_plan({"reason": "r", "ops": [{"op": "narrate", "text": "Aus einem anderen Spielstand."}]})
    s.reset()                                        # loading another save drops what was queued
    s.generation = fake.world.generation
    s.narrator_quiet_until = 0
    s.on_tick()
    assert played == ["Es war ein ruhiger Morgen.", "Zu ruhig."]
    del fake.dialog.narrating, fake.dialog.narrate


def test_rule_fires_on_perception():
    fake.world.__init__()
    fake.dialog.__init__()
    w = fake.world
    fake.player = types.SimpleNamespace(position=(0, 0, 0), given=[], busy=False, guild=0,
                                        give_item=lambda i, c=1: fake.player.given.append((i, c)))
    fake.daedalus = types.SimpleNamespace(get=lambda name, i=0: -1)
    s = st.Story()
    s.generation = w.generation
    s.apply_plan({"reason": "r", "ops": [{"op": "add_rule", "id": "seen", "when": ["active"],
                                          "on": {"event": "took_item", "item": "ITGOLD", "unseen": True},
                                          "ops": [{"op": "give_item", "instance": "ITREWARD"}]}]})
    theft = dict(kind="took_item", actor="PLAYER", target="", item="ITGOLD", spell=-1, seen_by=[])
    w.perceived = [theft]
    s.on_tick()
    assert fake.player.given == []       # the story was not listening yet
    s.state["flags"]["active"] = True
    s.on_tick()
    assert fake.player.given == []       # nothing has happened since it began to listen
    w.perceived = [{**theft, "seen_by": ["PARLAN"]}]
    s.on_tick()
    assert fake.player.given == []       # somebody saw it
    w.perceived = [theft]
    s.on_tick()
    assert fake.player.given == [("ITREWARD", 1)]
    w.perceived = [theft]
    s.on_tick()
    assert fake.player.given == [("ITREWARD", 1)]  # once only
    for bad in ({"event": "nope"}, {"event": "hit", "target": "ITGOLD"}):
        rejected(s, [{"op": "add_rule", "id": "x", "when": [], "on": bad, "ops": []}], "bad check")


def test_trip_operation():
    s = st.Story()
    s.validate([{"op": "trip", "profile": "kriegsgesang"}])
    s.validate([{"op": "trip", "profile": "kriegsgesang", "thoughts": [[0.3, "Bodo?"], [0.8, "Bodo hat Flügel."]]}])
    rejected(s, [{"op": "trip", "profile": "nope"}], "unknown trip")
    rejected(s, [{"op": "trip"}], "profile")
    for bad in ([[1.5, "zu viel"]], [[0.5, ""]], [["0.5", "x"]], [[True, "x"]], [[0.5]], [[0.1, "x"]] * 9, "text"):
        rejected(s, [{"op": "trip", "profile": "kriegsgesang", "thoughts": bad}], "thought")
    # A trip can wait in a rule, and its contents are checked when the rule is submitted.
    rejected(s, [{"op": "add_rule", "id": "r", "when": ["x"], "ops": [{"op": "trip", "profile": "nope"}]}], "unknown trip")


def test_items_of_our_own():
    # An item of the story's own gets a carrier nothing in the game uses, and every mention of it becomes that carrier.
    s = st.Story()
    plan = [{"op": "define_item", "item": "Mondaloe", "like": "ITPL_SAGITTA_HERB_MIS", "name": "Mondaloe",
             "rows": [["Blüht nur im Mondlicht", 0]]},
            {"op": "place_item", "instance": "MONDALOE", "waypoint": "WP_HUT"},
            {"op": "add_rule", "id": "r", "when": ["x"], "on": {"event": "took_item", "item": "MONDALOE"},
             "checks": [{"type": "has_item", "item": "MONDALOE"}], "ops": []}]
    resolved = s.resolve_items(plan)
    carrier = resolved[0]["carrier"]
    assert carrier == st.ITEM_CARRIERS[0] and resolved[0]["item"] == "Mondaloe"     # its own id stays
    assert resolved[1]["instance"] == carrier and resolved[2]["on"]["item"] == carrier
    assert resolved[2]["checks"][0]["item"] == carrier and plan[1]["instance"] == "MONDALOE"   # the plan is untouched
    s.validate(plan)
    defined = []
    fake.world.define_item = lambda *a: defined.append(a)
    s.apply_plan({"reason": "r", "ops": plan})
    assert s.state["items"]["MONDALOE"]["carrier"] == carrier, s.state.get("items")
    assert defined and defined[0][:3] == (carrier, "ITPL_SAGITTA_HERB_MIS", "Mondaloe"), defined
    rejected(s, [{"op": "define_item", "item": "X", "like": "ITPL_A", "name": "X", "look": {"tint": [1, 1]}}], "tint")
    # a later plan of the same game names the item and gets the same carrier; a second item gets the next one
    again = s.resolve_items([{"op": "give_item", "instance": "Mondaloe"},
                             {"op": "define_item", "item": "Nachtkerze", "like": "ITPL_SAGITTA_HERB_MIS", "name": "N"}])
    assert again[0]["instance"] == carrier and again[1]["carrier"] == st.ITEM_CARRIERS[1]
    # after a load the engine has forgotten it: the story defines it again
    defined.clear()
    s.rebind()
    assert defined and defined[0][0] == carrier
    rejected(s, [{"op": "define_item", "item": "Y", "like": "ITPL_A", "name": "Y", "carrier": "ITPL_A"}], "carrier")
    rejected(s, [{"op": "define_item", "item": "Y", "like": "ITPL_A", "name": "Y", "carrier": carrier}], "carrier")
    rejected(s, [{"op": "define_item", "item": "Mondaloe", "like": "ITPL_A", "name": "M",
                  "carrier": st.ITEM_CARRIERS[3]}], "already has")
    order = []
    fake.world.define_item = lambda *a: order.append("define")
    real_give = st.OPS["give_item"]
    st.OPS["give_item"] = (real_give[0], real_give[1], lambda args: order.append("give"))
    s2 = st.Story()
    s2.apply_plan({"reason": "r", "ops": [{"op": "give_item", "instance": "Z"},
                                          {"op": "define_item", "item": "Z", "like": "ITPL_A", "name": "Z"}]})
    assert order == ["define", "give"]                   # defined first, so what is given is the story's own
    st.OPS["give_item"] = real_give
    rejected(s, [{"op": "define_item", "item": "X", "like": "NOV_A", "name": "X"}], "not an item")
    rejected(s, [{"op": "define_item", "item": "X", "like": "ITPL_A", "name": ""}], "name")
    rejected(s, [{"op": "define_item", "item": "X", "like": "ITPL_A", "name": "X", "rows": [["a", "b"]]}], "rows")
    del fake.world.define_item


def test_give_xp():
    s = st.Story()
    s.validate([{"op": "give_xp", "amount": 150}])
    s.validate([{"op": "add_rule", "id": "r", "when": ["x"], "ops": [{"op": "give_xp", "amount": 200}]}])
    for bad in (0, 301, "150", 1.5, True):
        rejected(s, [{"op": "give_xp", "amount": bad}], "give_xp")
    rejected(s, [{"op": "give_xp"}], "amount")
    called = []
    fake.daedalus.call = lambda name, *args: called.append((name, *args))
    st._world_xp({"amount": 150})
    assert called == [("B_GIVEPLAYERXP", 150)]
    del fake.daedalus.call


def test_waited_for_pipe_is_reserved():
    # A pipe a rule waits for the hero to smoke is kept for him while the rule's conditions hold, then given back.
    calls = []
    fake.world.reserve_object = lambda scheme, x, z, on=True: calls.append((scheme, x, z, on)) or ("BJARNE" if on else "")
    fake.world.find_npc = lambda name: types.SimpleNamespace(position=(0, 0, 0))   # Abuyin, right there
    st._narration.clear()
    s = st.Story()
    s.state["rules"]["smoke"] = {"on": {"event": "used_object", "object": "SMOKE", "near": [6741, 2972, 1.5]},
                                 "when": ["pipe_ready"], "checks": [], "fired": False, "ops": []}
    s._tick_reservations()
    assert calls == []                                   # not filled yet: the pipe is everyone's
    s.state["flags"]["pipe_ready"] = True
    s._tick_reservations()
    assert calls == [("SMOKE", 6741.0, 2972.0, True)]    # filled: kept for the hero, the smoker gets up
    assert st._narration[-1]["voice"] == "13"            # and Abuyin tells him why
    s._tick_reservations()
    assert len(calls) == 1                               # once
    assert s.evicted == {("SMOKE", 6741.0, 2972.0): "BJARNE"}   # he waits on a bench, his routine held
    s.state["rules"]["smoke"]["fired"] = True
    s._tick_reservations()
    assert calls[-1] == ("SMOKE", 6741.0, 2972.0, False) and s.reserved == {} and s.evicted == {}   # given back
    del fake.world.reserve_object, fake.world.find_npc
    st._narration.clear()


def test_topics_extend_an_npc():
    fake.world.__init__()
    fake.dialog.__init__()
    s = st.Story()
    graph = {"start": "a", "nodes": {"a": {"line": "Aus dem Norden? Ja, davon hab ich gehört.",
                                           "choices": [{"text": "Danke.", "ends": True}], "sets": ["legend_heard"]}}}
    topic = {"op": "add_topic", "id": "legend", "npc": "PARLAN", "title": "Kennst du die Kriegsmischung?",
             "graph": graph, "unless": ["legend_heard"]}
    rejected(s, [{**topic, "npc": "NOBODY"}], "NOBODY")
    rejected(s, [{**topic, "title": " "}], "title")
    rejected(s, [{**topic, "graph": {"start": "x", "nodes": {}}}], "graph")
    s.submit("Legende", [topic])
    s.on_tick()   # applies the plan
    s.on_tick()   # shows its topic
    # The engine shows the topic in the NPC's own menu, beside his scripted ones.
    assert fake.dialog.topics["PARLAN"] == [("legend", "Kennst du die Kriegsmischung?")]
    rejected(s, [topic], "already added")
    # Chosen: the story plays it, and at its end hands the conversation back instead of closing it.
    player = graphs.Player(lambda: s.graphs_now(), s.player_flag, lambda: s.state["flags"],
                           lambda key: s.state["topics"].get(key))
    fake.dialog.who = fake.world.npcs["PARLAN"]
    fake.dialog.open = True
    fake.dialog.chosen_topic = "legend"
    for _ in range(12):
        player.on_tick()
        if player.stage == "choose":
            fake.dialog.selection = 0
    assert fake.dialog.ended_topics == 1 and fake.dialog.open and player.topic is None
    assert "Aus dem Norden? Ja, davon hab ich gehört." in fake.dialog.lines
    # The hero says the topic's title first, as with the game's own topics.
    lines = fake.dialog.lines
    assert lines.index("Kennst du die Kriegsmischung?") < lines.index("Aus dem Norden? Ja, davon hab ich gehört.")
    # Its own flag hides it: the menu loses the topic once it has been heard.
    s.on_tick()
    assert fake.dialog.topics["PARLAN"] == []
    # A topic whose conditions no longer hold cannot be played, even if an old menu still offered it.
    assert s.topic("legend") is None
    # A conversation closed in the middle of a topic leaves no topic mode behind.
    s.state["flags"]["legend_heard"] = False
    fake.dialog.open, fake.dialog.chosen_topic = True, "legend"
    player.on_tick()
    assert player.topic == "legend"
    fake.dialog.open = False
    player.on_tick()
    assert player.topic is None and player.stage == "idle"
    # An NPC removed and spawned again as the same instance gets the topics anew.
    s.on_tick()
    old_parlan = fake.world.npcs["PARLAN"]
    fake.world.npcs["PARLAN"] = Npc("PARLAN")
    fake.dialog.topics.clear()
    s.on_tick()
    assert fake.world.npcs["PARLAN"] is not old_parlan and "PARLAN" in fake.dialog.topics   # sent to the new one
    # Invalid conditions on a topic are refused when it is submitted.
    rejected(st.Story(), [{**topic, "id": "x", "checks": [{"type": "nope"}]}], "unknown check")
    s.state["flags"]["legend_heard"] = True
    s.on_tick()
    # After a world change the engine has forgotten the topics, and the story sets them again.
    s.state["flags"]["legend_heard"] = False
    fake.dialog.topics.clear()
    fake.world.generation += 1
    s.on_tick()
    assert fake.dialog.topics["PARLAN"] == [("legend", "Kennst du die Kriegsmischung?")]


for test in (test_items_of_our_own, test_give_xp, test_waited_for_pipe_is_reserved, test_handed_over_but_nothing_to_play, test_topics_extend_an_npc, test_trip_operation, test_rule_contents_are_checked_when_submitted, test_graph_validation, test_validation, test_apply_and_rollback, test_return_npc, test_conditional_choices, test_returns_to_menu, test_questions_are_asked_once, test_variant_line, test_again_line, test_scene_and_rule, test_rule_fires_on_perception, test_narration_waits_for_quiet, test_drawing_a_weapon_is_perceived,
             test_queue_waits_for_safe_point, test_save_load_does_not_reapply_world,
             test_player):
    test()
print("story tests passed")
