"""Playability audit tests on a tiny made-up game. Run: python3 python/dm/test_playability.py"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import playability as pa  # noqa: E402

W = pa.WORLD


def cond(*guards):
    return {"effects": [{"return": "TRUE", "if": list(guards)}]}


DIALOGUES = [
    {"id": "DIA_SMITH_HELLO", "npc": "VLK_1_SMITH", "description": None, "condition": cond(), "information": {"effects": []}},
    {"id": "DIA_SMITH_JOB", "npc": "VLK_1_SMITH", "description": "x", "condition": cond("NPC_KNOWSINFO(OTHER, DIA_SMITH_HELLO)"),
     "information": {"effects": [{"set": "MIS_SMITH_JOB = LOG_RUNNING"}]}},
    {"id": "DIA_SMITH_DONE", "npc": "VLK_1_SMITH", "description": "x",
     "condition": cond("((MIS_SMITH_JOB == LOG_RUNNING) && (NPC_HASITEMS(OTHER, ITFK_BOX) >= 1))"),
     "information": {"effects": [{"set": "MIS_SMITH_JOB = LOG_SUCCESS"},
                                 {"do": "B_GIVEINVITEMS(SELF, OTHER, ITFK_GIFT, 1)"}]}},
    {"id": "DIA_SMITH_LATER", "npc": "VLK_1_SMITH", "description": "x", "condition": cond("(KAPITEL >= 3)"),
     "information": {"effects": [{"set": "MIS_LATE = LOG_SUCCESS"}]}},
    {"id": "DIA_SMITH_GUARDS", "npc": "VLK_1_SMITH", "description": "x", "condition": cond("(OTHER.GUILD == GIL_MIL)"),
     "information": {"effects": [{"set": "MIS_GUARD = LOG_RUNNING"}]}},
    {"id": "DIA_SMITH_EARLY_NO", "npc": "VLK_1_SMITH", "description": "x",
     "condition": {"effects": [{"return": "FALSE", "if": ["(KAPITEL < 2)"]}, {"return": "TRUE"}]},
     "information": {"effects": []}},
    {"id": "DIA_SMITH_TRADE", "npc": "VLK_1_SMITH", "description": "x", "condition": cond(),
     "information": {"effects": [{"do": "B_GIVETRADEINV(SELF)"}]}},
    {"id": "DIA_GHOST_HI", "npc": "VLK_9_GHOST", "description": "x", "condition": cond(), "information": {"effects": []}},
    {"id": "PC_MIXING", "npc": "PC_HERO", "description": "x",
     "condition": cond("((PLAYER_MOBSI_PRODUCTION == MOBSI_WORKBENCH) && (NPC_HASITEMS(HERO, ITFK_LEAF) >= 1))"),
     "information": {"effects": [{"do": "INFO_ADDCHOICE(PC_MIXING, \"x\", PC_MIXING_PASTE)",
                                  "if": ["(NPC_HASITEMS(HERO, ITFK_RESIN) >= 2)"]}],
                     "choices": {"PC_MIXING_PASTE": {"effects": [{"do": "CREATEINVITEMS(HERO, ITFK_PASTE, 1)"}]}}}},
]
FUNCTIONS = {
    "RTN_START_1": [{"do": 'TA_STAND_ARMSCROSSED(8, 0, 22, 0, "WP_FORGE")'}, {"do": 'TA_SLEEP(22, 0, 8, 0, "WP_BED")'}],
    "RTN_START_2": [{"do": 'TA_SMOKE_WATERPIPE(20, 0, 1, 0, "WP_PIPE")'}, {"do": 'TA_SIT_BENCH(1, 0, 20, 0, "WP_FORGE")'}],
    "RTN_START_3": [{"do": 'TA_WORKBENCH(6, 0, 18, 0, "WP_SHED")'}, {"do": 'TA_SLEEP(18, 0, 6, 0, "WP_BED")'}],
    "B_GIVETRADEINV": [{"set": "B_GIVETRADEINV.TRD_SMITH = HLP_GETNPC(VLK_1_SMITH)"}],
    "B_GIVETRADEINV_SMITH": [{"do": "CREATEINVITEMS(B_GIVETRADEINV_SMITH.SLF, ITFK_LEAF, 3)", "if": ["((KAPITEL >= 1) && (A == FALSE))"]},
                             {"do": "CREATEINVITEMS(B_GIVETRADEINV_SMITH.SLF, ITFK_RARE, 1)", "if": ["((KAPITEL >= 3) && (B == FALSE))"]}],
    "STARTUP_NEWWORLD_PART_TOWN": [{"do": 'WLD_INSERTITEM(ITFK_RESIN, "FP_SHED")'}],
}
WORLD = [{"world": W, "kind": "waypoint", "name": name, "x": x, "y": 0, "z": z} for name, x, z in
         (("WP_FORGE", 0, 0), ("WP_BED", 1000, 0), ("WP_PIPE", 5000, 5000), ("WP_SHED", -3000, 0), ("WP_FAR", 9000, 9000))]
WORLD += [{"world": W, "kind": "item", "name": "ITFK_LEAF", "instance": "ITFK_LEAF", "x": 1010, "y": 0, "z": 5},
          {"world": W, "kind": "container", "name": "CHEST_SHED", "x": -2990, "y": 0, "z": 0, "locked": False,
           "key": "", "pick": "", "contents": "ItFk_Box,ItMi_Gold:5"},
          {"world": W, "kind": "container", "name": "", "x": 9000, "y": 0, "z": 9000, "locked": True,
           "key": "", "pick": "LR", "contents": "ItFk_Locked"},
          {"world": "OTHERWORLD.ZEN", "kind": "item", "name": "ITFK_RARE", "instance": "ITFK_RARE", "x": 0, "y": 0, "z": 0}]
ITEMS = {name: {"name": name.title()} for name in ("ITFK_LEAF", "ITFK_RESIN", "ITFK_PASTE", "ITFK_BOX", "ITFK_GIFT",
                                                    "ITFK_RARE", "ITFK_LOCKED", "ITMI_GOLD")}
PEOPLE = {W: [{"instance": f"VLK_{i}_{n}", "name": n.title(), "id": str(i), "spawn": {"chapter": 1, "conditions": []},
               "routines": {"1": f"RTN_START_{i}"}} for i, n in ((1, "SMITH"), (2, "SMOKER"), (3, "CARPENTER"))]}
PEOPLE["OLDWORLD.ZEN"] = [{"instance": "VLK_9_GHOST", "name": "Ghost", "id": "9", "spawn": {"chapter": 2}, "routines": {}}]
QUESTS = {"Smith's job": {"variables": ["MIS_SMITH_JOB"]}}
PIPE = (W, "SMOKE", 5050, 5000)
game = pa.Game(ITEMS, DIALOGUES, FUNCTIONS, QUESTS, WORLD, PEOPLE, inventories={"VLK_2_SMOKER": {"ITFK_RARE": 1}},
               objects=[PIPE, (W, "SMOKE", 8000, 8000)])

# the game's conditions, read three-valued: chapter 1 and no guild are certain, the rest the hero can bring about
assert game.guard("(KAPITEL >= 3)") == pa.FALSE and game.guard("(KAPITEL == 1)") == pa.TRUE
assert game.guard("(OTHER.GUILD == GIL_NONE)") == pa.TRUE and game.guard("(OTHER.GUILD == GIL_MIL)") == pa.FALSE
assert game.guard("(SOMETHING == TRUE)") == pa.MAYBE
assert game.guard("((SOMETHING == TRUE) || (KAPITEL == 1))") == pa.TRUE
assert game.guard("((SOMETHING == TRUE) && (KAPITEL >= 2))") == pa.FALSE
assert game.guard("NPC_KNOWSINFO(OTHER, DIA_SMITH_LATER)") == pa.FALSE
assert game.guard("!NPC_KNOWSINFO(OTHER, DIA_SMITH_LATER)") == pa.TRUE
assert game.guard("(MIS_LATE == LOG_SUCCESS)") == pa.FALSE and game.guard("(MIS_LATE != LOG_SUCCESS)") == pa.TRUE
assert game.guard("((MIS_SMITH_JOB == LOG_SUCCESS) || NPC_KNOWSINFO(OTHER, DIA_SMITH_HELLO))") == pa.TRUE
assert game.guard("this is ( not a guard") == pa.MAYBE                  # unreadable text never decides

# dialogues: who is around, what their condition allows, and a "return FALSE" that comes first
assert game.dialogue_reachable("DIA_SMITH_JOB")[0] == pa.TRUE
assert game.dialogue_reachable("DIA_SMITH_LATER")[0] == pa.FALSE
assert "KAPITEL" in game.dialogue_reachable("DIA_SMITH_LATER")[1]
assert game.dialogue_reachable("DIA_SMITH_EARLY_NO")[0] == pa.FALSE
assert game.dialogue_reachable("DIA_GHOST_HI") == (pa.FALSE, "only in OLDWORLD.ZEN")
assert game.dialogue_reachable("DIA_NOBODY")[0] == pa.FALSE

# quests: started and finished by someone the hero can reach, or not
assert game.quest_reachable("MIS_SMITH_JOB", "LOG_RUNNING")[0] == pa.TRUE
assert game.quest_reachable("MIS_SMITH_JOB", "LOG_SUCCESS")[0] == pa.MAYBE
assert game.quest_reachable("MIS_LATE", "LOG_SUCCESS")[0] == pa.FALSE
assert game.quest_reachable("MIS_GUARD", "LOG_RUNNING")[0] == pa.FALSE
assert game.quest_reachable("MIS_NEVER", "LOG_SUCCESS") == (pa.FALSE, [])

# item sources: on the ground, in a chest, at a trader in this chapter only, from a dialogue, made at a bench
kinds = lambda item: {(s["kind"], s["reach"]) for s in game.item_sources(item)}  # noqa: E731
assert ("placed", pa.TRUE) in kinds("ITFK_LEAF") and ("trader", pa.TRUE) in kinds("ITFK_LEAF")
leaf = [s for s in game.item_sources("ITFK_LEAF") if s["kind"] == "placed"][0]
assert "WP_BED" in leaf["text"]                                         # named by its nearest waypoint
assert kinds("ITFK_BOX") == {("container", pa.TRUE)}
assert kinds("ITFK_LOCKED") == {("container", pa.MAYBE)}                # locked, but it can be picked
assert kinds("ITFK_GIFT") == {("dialogue", pa.MAYBE)}
assert kinds("ITFK_RESIN") == {("placed", pa.TRUE)}                     # inserted by a chapter-1 startup script
paste = game.item_sources("ITFK_PASTE")
assert [s["kind"] for s in paste] == ["made"] and paste[0]["reach"] == pa.TRUE
assert "2x ITFK_RESIN" in paste[0]["text"] and "1x ITFK_LEAF" in paste[0]["text"] and "WP_SHED" in paste[0]["text"]
assert kinds("ITFK_RARE") == {("carried", pa.MAYBE)}                    # only chapter 3 stock, another world, a pocket
assert game.item_sources("ITFK_NOTHING") == []

# time: windows wrap past midnight, as the story's hour check reads them
assert pa.minutes(22 * 60, 2 * 60) == set(range(1320, 1440)) | set(range(0, 120))
assert pa.spans(pa.hour_window({"from": 22, "to": 2})) == "22:00-02:00"
assert pa.spans(set(range(1440))) == "all day" and pa.spans(set()) == "never"
assert pa.hour_window({"from": 5, "to": 5}) == set()


def graph(*choices, sets=None):
    node = {"line": "...", "choices": list(choices) + [{"text": "Bye.", "ends": True}]}
    if sets:
        node["sets"] = sets
    return {"start": "a", "nodes": {"a": node, "b": {"line": "...", "sets": "done", "choices": [{"text": "Ok.", "ends": True}]}}}


def ending(flag):
    return {"op": "add_rule", "id": f"end_{flag}", "when": [flag], "ops": [{"op": "journal", "topic": "T", "status": 2}]}


def audit(plan, others=(), name="s"):
    story = pa.Story({"title": name, "plan": plan}, name)
    return pa.Audit(story, game, [pa.Story({"title": "o", "plan": p}, f"other{i}") for i, p in enumerate(others)]).run()


# a story the game can carry from start to end
good = audit([
    {"op": "rename_npc", "instance": "VLK_1_SMITH", "display_name": "Hob"},
    {"op": "add_topic", "id": "ask", "npc": "VLK_1_SMITH", "title": "?", "checks": [
        {"type": "heard", "info": "DIA_SMITH_HELLO"}, {"type": "hour", "from": 9, "to": 12}],
     "graph": graph({"text": "Here.", "goto": "b", "takes": {"item": "ITFK_PASTE", "count": 1},
                     "checks": [{"type": "quest", "quest": "MIS_SMITH_JOB", "state": "success"}]})},
    {"op": "place_item", "instance": "ITFK_GIFT", "waypoint": "WP_FAR"},
    ending("done")])
assert good["verdict"] == "playable end to end", good["blockers"] + good["caveats"]
assert good["renamed"] == [{"npc": "VLK_1_SMITH", "name": "Hob", "was": "Smith"}]
assert good["placed"][0]["exists"] and good["endings"]["endings"][0]["status"] == "reachable"
assert good["heard"][0]["reach"] == pa.TRUE and good["quests"][0]["reach"] == pa.MAYBE

# a story the game cannot carry: an item from a later chapter, a topic while its man sleeps, a later quest
bad = audit([
    {"op": "add_topic", "id": "night", "npc": "VLK_1_SMITH", "title": "?", "checks": [{"type": "hour", "from": 23, "to": 2}],
     "graph": graph({"text": "Here.", "goto": "b", "takes": {"item": "ITFK_LATER", "count": 1}})},
    {"op": "add_scene", "id": "late", "npc": "VLK_1_SMITH", "checks": [{"type": "quest", "quest": "MIS_LATE", "state": "success"}],
     "graph": graph(sets="done")},
    {"op": "add_rule", "id": "seen", "when": [], "checks": [{"type": "heard", "info": "DIA_GHOST_HI"}], "ops": []},
    {"op": "place_item", "instance": "ITFK_BOX", "waypoint": "WP_NOWHERE"},
    ending("done")])
assert bad["verdict"] == "blocked"
text = " | ".join(bad["blockers"])
assert "ITFK_LATER" in text and "sleeps through" in text and "DIA_GHOST_HI" in text and "WP_NOWHERE" in text
assert "no ending can be reached" in text
assert bad["endings"]["endings"][0]["status"] == "blocked by the game"

# partly asleep: usable, with a caveat that says when
dusk = audit([{"op": "add_topic", "id": "dusk", "npc": "VLK_1_SMITH", "title": "?",
               "checks": [{"type": "hour", "from": 20, "to": 23}], "graph": graph()}])
assert dusk["verdict"] == "playable with caveats" and "usable only 20:00-22:00" in dusk["caveats"][0]

# an object someone smokes at: resolved once a conversation fills it, a conflict when nothing does
smoke = {"op": "add_rule", "id": "puff", "when": ["filled"], "on": {"event": "used_object", "object": "SMOKE",
                                                                    "near": [5050, 5000, 1]}, "ops": []}
filled = audit([{"op": "add_topic", "id": "fill", "npc": "VLK_1_SMITH", "title": "?",
                 "graph": graph({"text": "Fill it.", "goto": "b"}, sets="filled")}, smoke])
users = filled["objects"][0]["users"]
assert [(u["npc"], u["status"]) for u in users] == [("VLK_2_SMOKER", "resolved by reservation")]
assert users[0]["overlap"] == "20:00-01:00"
bare = audit([{"op": "set_flag", "name": "x", "value": True}, dict(smoke, when=[])])
assert bare["objects"][0]["users"][0]["status"] == "conflict" and "nothing makes him get up" in bare["caveats"][0]
lonely = audit([dict(smoke, when=[], checks=[{"type": "hour", "from": 9, "to": 12}])])
assert lonely["objects"][0]["users"][0]["status"] == "no clash" and lonely["verdict"] == "playable end to end"

# an npc_state check needs the routine to put him in that state
state = audit([{"op": "add_topic", "id": "s", "npc": "VLK_1_SMITH", "title": "?", "graph": graph(),
                "checks": [{"type": "npc_state", "npc": "VLK_1_SMITH", "state": "ZS_SMOKE_WATERPIPE"}]}])
assert state["verdict"] == "blocked" and "never ZS_SMOKE_WATERPIPE" in state["blockers"][0]

# a rule that waits for the story's own item also fires on any other copy the game holds
copy = audit([{"op": "place_item", "instance": "ITFK_LEAF", "waypoint": "WP_FAR"},
              {"op": "add_rule", "id": "took", "when": [], "on": {"event": "took_item", "item": "ITFK_LEAF"}, "ops": []}])
assert any("taking any copy fires them" in c for c in copy["caveats"])

# replacing an NPC's conversations hides the topic the story waits for
hidden = audit([{"op": "attach_dialogue_graph", "npc": "VLK_1_SMITH", "graph": graph()},
                {"op": "add_scene", "id": "x", "npc": "VLK_2_SMOKER", "graph": graph(),
                 "checks": [{"type": "heard", "info": "DIA_SMITH_HELLO"}]}])
assert any("replaces" in b and "DIA_SMITH_HELLO" in b for b in hidden["blockers"])

# stories in one game share flags; the audit names where a foreign flag reaches in
shared = audit([{"op": "add_scene", "id": "x", "npc": "VLK_1_SMITH", "requires": ["met"], "graph": graph()}],
               others=[[{"op": "add_rule", "id": "y", "when": [], "ops": [{"op": "set_flag", "name": "met", "value": True}]}]])
assert any("flag met is also set by other0" in c and "scene x" in c for c in shared["caveats"])

# the outputs are readable and serialisable
assert "**Verdict: blocked**" in pa.markdown(bad) and "### 5. Objects" in pa.markdown(filled)
json.dumps(pa.summary(bad))
print("ok")

# endings: a flag the plan sets at once counts from the start; an "unless" the runtime never lets pass bars the way
seeded = audit([{"op": "set_flag", "name": "ready", "value": True}, ending("ready")])
assert seeded["endings"]["endings"][0]["status"] == "reachable", seeded["endings"]
contradiction = audit([
    {"op": "add_rule", "id": "sets_ready", "when": [], "ops": [{"op": "set_flag", "name": "ready", "value": True}]},
    {"op": "add_rule", "id": "end_x", "when": ["ready"], "unless": "ready",
     "ops": [{"op": "journal", "topic": "T", "status": 2}]}])
assert contradiction["endings"]["endings"][0]["status"] != "reachable", contradiction["endings"]
self_barred = audit([{"op": "add_topic", "id": "t", "npc": "VLK_1_SMITH", "title": "?",
                      "graph": graph({"text": "Go.", "goto": "b", "unless": "seen"}, sets="seen")}, ending("done")])
assert self_barred["endings"]["endings"][0]["status"] != "reachable", self_barred["endings"]
print("ending guards ok")
