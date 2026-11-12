"""Tests against the Tilo story, including the bugs found while playing it.

Run: python3 python/dm/test_knowledge.py
"""

import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from dm import knowledge as k  # noqa: E402

WITNESS, HAREK, TILO = "NOV_610", "HAREK", "NOV_606"


def fact(known_by=(), essential=False, needs=(), topic=False):
    return {"text": "", "known_by": list(known_by), "essential": essential,
            "needs": list(needs), "topic": topic}


PLOT = {
    "start": [],
    "facts": {
        "tilo_named": fact(topic=True),
        "tilo_missing": fact([WITNESS], essential=True),
        "candlesticks": fact([WITNESS, TILO], essential=True),
        "debt": fact([WITNESS, HAREK, TILO], essential=True),
        "silver_sold": fact([HAREK, TILO]),
        "hiding_near_harbour": fact([HAREK], essential=True, needs=["debt"]),
    },
    "items": [{"ref": "ROBE", "teaches": ["tilo_missing"], "needs": []}],
}


def end():
    return {"text": "Danke.", "ends": True}


def conversations():
    return {
        WITNESS: {"start": "a", "nodes": {
            "a": {"line": "Hast du Tilo gesehen?", "teaches": ["tilo_named", "tilo_missing"],
                  "choices": [{"text": "Fehlt etwas?", "goto": "f"},
                              {"text": "Was verschweigst du?", "goto": "c"}, end()]},
            "c": {"line": "Er schuldete jemandem Geld.", "uses": ["tilo_named"], "teaches": ["debt"],
                  "choices": [{"text": "Zurück.", "goto": "a"}, end()]},
            "f": {"line": "Zwei silberne Leuchter fehlen.", "teaches": ["candlesticks"],
                  "choices": [{"text": "Zurück.", "goto": "a"}, end()]}}},
        HAREK: {"start": "a", "nodes": {
            "a": {"line": "Was glotzt du?", "choices": [
                {"text": "Du kennst Tilo.", "uses": ["tilo_named"], "requires": ["tilo_named"], "goto": "b"},
                {"text": "Hast du Leuchter?", "uses": ["candlesticks"], "requires": ["candlesticks"], "goto": "c"},
                {"text": "Hat dir ein Novize etwas verkauft?", "unless": "candlesticks", "goto": "c"}, end()]},
            "b": {"line": "Der schuldet mir Gold.", "uses": ["tilo_named"], "teaches": ["debt"],
                  "choices": [{"text": "Er ist verschwunden.", "uses": ["tilo_missing"],
                               "requires": ["tilo_missing"], "goto": "d"}, end()]},
            "c": {"line": "Pass auf, was du sagst.", "choices": [
                {"text": "Sag schon.", "goto": "d2"}, end()]},
            "d": {"line": "Er kam mit einem Sack Silber.", "uses": ["tilo_named"], "teaches": ["silver_sold"],
                  "choices": [{"text": "Wo ist er?", "goto": "e"}, end()]},
            "d2": {"line": "Der kleine Tilo kam mit einem Sack Silber.",
                   "teaches": ["tilo_named", "silver_sold", "debt"],
                   "choices": [{"text": "Wo ist er?", "goto": "e"}, end()]},
            "e": {"line": "Irgendwo am Hafen.", "uses": ["tilo_named"], "teaches": ["hiding_near_harbour"],
                  "choices": [end()]}}},
    }


def has(errors, text):
    assert any(text in e for e in errors), (text, errors)


def test_story_is_consistent():
    errors, warnings = k.check(PLOT, conversations())
    assert errors == [], errors
    assert warnings == ["only one source for essential fact: candlesticks",
                        "only one source for essential fact: hiding_near_harbour"], warnings


def test_catches_pronoun_before_subject():
    c = conversations()
    c[HAREK]["nodes"]["c"]["choices"][0]["goto"] = "d"
    errors, _ = k.check(PLOT, c)
    has(errors, "line uses 'tilo_named' before it is known: node d")


def test_catches_hero_knowing_too_much():
    c = conversations()
    choice = c[HAREK]["nodes"]["a"]["choices"][1]
    del choice["requires"]
    errors, _ = k.check(PLOT, c)
    has(errors, "hero says 'candlesticks' before knowing it")


def test_catches_npc_knowing_too_much():
    plot = copy.deepcopy(PLOT)
    plot["facts"]["hiding_near_harbour"]["known_by"] = []
    errors, _ = k.check(plot, conversations())
    has(errors, "HAREK cannot know 'hiding_near_harbour'")


def test_catches_missing_source():
    c = conversations()
    del c[WITNESS]["nodes"]["f"]["teaches"]
    errors, _ = k.check(PLOT, c)
    has(errors, "essential fact can never be learned: candlesticks")


def test_catches_cycle():
    plot = copy.deepcopy(PLOT)
    plot["facts"]["debt"]["needs"] = ["hiding_near_harbour"]
    errors, _ = k.check(plot, conversations())
    has(errors, "facts depend on each other")


def test_catches_learning_out_of_order():
    plot = copy.deepcopy(PLOT)
    plot["facts"]["silver_sold"]["needs"] = ["hiding_near_harbour"]
    errors, _ = k.check(plot, conversations())
    has(errors, "'silver_sold' can be learned before")


def test_catches_unknown_fact():
    c = conversations()
    c[HAREK]["nodes"]["a"]["uses"] = ["typo"]
    errors, _ = k.check(PLOT, c)
    has(errors, "unknown fact: typo")


def test_gated_unlock_stays_consistent():
    c = conversations()
    c[HAREK]["nodes"]["a"]["choices"][1]["requires"] = ["silver_sold"]
    errors, _ = k.check(PLOT, c)
    has(errors, "hero says 'candlesticks' before knowing it")


def _weed(truth_known_by=("SLD_810_DAR",), believed=("SLD_803_CIPHER",), claimed=(), truth_taught=True):
    facts = {
        "dar_stole": {"text": "Dar hat das Kraut gestohlen.", "essential": True, "known_by": list(truth_known_by)},
        "bodo_stole": {"text": "Bodo hat es gestohlen.", "false": True, "contradicts": "dar_stole",
                       "believed_by": list(believed), "claimed_by": list(claimed)}}
    cipher = {"start": "a", "nodes": {"a": {"line": "Bodo war's.", "teaches": ["bodo_stole"],
                                            "choices": [{"text": "Hm.", "ends": True}]}}}
    dar = {"start": "a", "nodes": {"a": {"line": "Ich war's.", "teaches": ["dar_stole"] if truth_taught else [],
                                         "choices": [{"text": "So.", "ends": True}]}}}
    return {"start": [], "facts": facts, "items": []}, {"SLD_803_CIPHER": cipher, "SLD_810_DAR": dar}


def test_a_believer_may_say_what_is_not_so():
    plot, convs = _weed()
    errors, warnings = k.check(plot, convs)
    assert errors == [], errors
    assert not any("never find out" in w for w in warnings), warnings


def test_only_believers_say_it():
    plot, convs = _weed(believed=())
    errors, _ = k.check(plot, convs)
    has(errors, "SLD_803_CIPHER cannot believe or claim 'bodo_stole'")


def test_a_lie_is_never_essential_and_names_its_truth():
    plot, convs = _weed()
    plot["facts"]["bodo_stole"]["essential"] = True
    has(k.check(plot, convs)[0], "a false fact cannot be essential: bodo_stole")
    plot, convs = _weed()
    del plot["facts"]["bodo_stole"]["contradicts"]
    has(k.check(plot, convs)[0], "false fact names no truth")
    plot, convs = _weed()
    plot["facts"]["dar_stole"]["believed_by"] = ["X"]
    has(k.check(plot, convs)[0], "not marked false")


def test_misled_for_good_is_warned():
    plot, convs = _weed(truth_taught=False)
    plot["facts"]["dar_stole"]["essential"] = False
    _, warnings = k.check(plot, convs)
    assert any("never find out that 'bodo_stole' is wrong" in w for w in warnings), warnings


def test_a_liar_knows_better():
    plot, convs = _weed(truth_known_by=(), claimed=("SLD_810_DAR",), believed=())
    plot["facts"]["dar_stole"]["known_by"] = ["SLD_810_DAR"]
    convs["SLD_803_CIPHER"]["nodes"]["a"]["teaches"] = []
    convs["SLD_810_DAR"]["nodes"]["a"]["teaches"] = ["bodo_stole", "dar_stole"]
    errors, warnings = k.check(plot, convs)
    assert errors == [] and not any("a believer, not a liar" in w for w in warnings), (errors, warnings)
    plot["facts"]["dar_stole"]["known_by"] = ["SLD_803_CIPHER"]
    convs["SLD_810_DAR"]["nodes"]["a"]["teaches"] = ["bodo_stole"]
    _, warnings = k.check(plot, convs)
    assert any("a believer, not a liar" in w for w in warnings), warnings


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        fn()
print("knowledge tests passed")
