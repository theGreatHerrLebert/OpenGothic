"""The reference of every story operation, written to docs/story-ops.md.

    python3 python/dm/op_reference.py          rewrite docs/story-ops.md

Each operation in story.OPS is described here once. test_op_reference.py fails when an operation has no entry or the
document is older than this file, so the reference cannot drift from the code.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

DOC = pathlib.Path(__file__).resolve().parent.parent.parent / "docs" / "story-ops.md"

# Group, what it does, an example. "runtime" operations are written by the game master itself, never by an author.
OPS = {
    # The story's knowledge and memory
    "commit_fact": ("Knowledge", "Records a fact of the story and who knows it; dialogue may only say what is known.",
                    {"op": "commit_fact", "id": "thief", "text": "Bodo hat das Kraut gestohlen.", "known_by": ["SLD_810_DAR"]}),
    "set_flag": ("Knowledge", "Sets a flag the story remembers; rules, scenes, topics and lines wait on flags.",
                 {"op": "set_flag", "name": "wolf_seen", "value": True}),
    "journal": ("Knowledge", "Writes an entry into the hero's journal (status 1 running, 2 success, 3 failed).",
                {"op": "journal", "topic": "Der weiße Wolf", "entry": "Pepe vermisst Schafe.", "status": 1}),
    "do_nothing": ("Knowledge", "Records a decision to leave the world alone, with the reason.",
                   {"op": "do_nothing", "reason": "Der Held ist mitten im Kampf."}),
    # Dialogue
    "attach_dialogue_graph": ("Dialogue", "Gives a nameless NPC a conversation of the story's own, for good.",
                              {"op": "attach_dialogue_graph", "npc": "BAU_901_BAUER", "graph": {"start": "a", "nodes": {}}}),
    "detach_dialogue_graph": ("Dialogue", "Takes a story's conversation away from an NPC again.",
                              {"op": "detach_dialogue_graph", "npc": "BAU_901_BAUER"}),
    "add_topic": ("Dialogue", "Adds a topic to any NPC's own menu, beside the game's topics, while its conditions hold.",
                  {"op": "add_topic", "id": "wolf", "npc": "BAU_912_PEPE", "title": "Der weiße Wolf?",
                   "graph": {"start": "a", "nodes": {}}, "requires": ["wolf_seen"]}),
    "add_scene": ("Dialogue", "A conversation an NPC starts himself when the hero comes within sight, once.",
                  {"op": "add_scene", "id": "warning", "npc": "BAU_912_PEPE", "graph": {"start": "a", "nodes": {}},
                   "within": 800, "requires": ["wolf_seen"]}),
    "finish_scene": ("Dialogue", "Marks a scene done without playing it.", {"op": "finish_scene", "id": "warning"}),
    "refuse_talk": ("Dialogue", "Someone stops talking to the hero: every conversation with him, his own topics and "
                                "trade included, is one line of refusal and the hero's reply, until the flag in unless "
                                "is set or the story ends. Not on people the main quest needs.",
                    {"op": "refuse_talk", "id": "snitch", "npc": "BAU_919_BAUER", "voice": "07",
                     "line": "Mit dir red ich nicht mehr, du Petze.", "reply": "Dann eben nicht.", "unless": "forgiven"}),
    "narrate": ("Dialogue", "A line from off-screen, queued until no conversation runs.",
                {"op": "narrate", "text": "Irgendwo heult ein Wolf.", "voice": "10"}),
    # Rules
    "add_rule": ("Rules", "Waits for flags (when), live checks and optionally a deed (on), then runs its operations once.",
                 {"op": "add_rule", "id": "slain", "when": [], "on": {"event": "killed", "creature": "white_wolf"},
                  "ops": [{"op": "set_flag", "name": "wolf_dead", "value": True}]}),
    "fire_rule": ("runtime", "Marks a rule fired.", {"op": "fire_rule", "id": "slain"}),
    "perceive": ("runtime", "Marks that a rule's deed happened.", {"op": "perceive", "id": "slain"}),
    "fail_rule": ("runtime", "Marks a rule broken, so a load does not try it again.",
                  {"op": "fail_rule", "id": "slain", "error": "no such waypoint"}),
    "retire": ("runtime", "Retires one rule, scene, topic or refusal by its id, as if its story had ended (for tests and repairs).",
               {"op": "retire", "id": "test_dice"}),
    "retry_rule": ("runtime", "Lets a broken rule try again, after the cause was fixed.", {"op": "retry_rule", "id": "slain"}),
    # People and creatures
    "spawn_npc": ("People", "Brings an existing character into the world at a waypoint.",
                  {"op": "spawn_npc", "instance": "BAU_901_BAUER", "waypoint": "NW_BIGFARM_SHEEP2_04"}),
    "spawn_creature": ("People", "Remixes a nameless creature into the story's own: name, fur, size, strength, loot.",
                       {"op": "spawn_creature", "id": "white_wolf", "like": "WOLF", "waypoint": "NW_BIGFARM_SHEEP2_04",
                        "name": "Der Weiße", "look": {"tint": [0.92, 0.96, 1.0], "brighten": 2.2}, "scale": 1.3,
                        "hp": 400, "strength": 70, "level": 20}),
    "rename_npc": ("People", "Shows an NPC under a new name.",
                   {"op": "rename_npc", "instance": "BAU_901_BAUER", "display_name": "Jorgen"}),
    "send_npc": ("People", "Sends an NPC to a waypoint to stay there.",
                 {"op": "send_npc", "instance": "BAU_901_BAUER", "waypoint": "NW_BIGFARM_KITCHEN"}),
    "relocate_npc": ("People", "Moves an NPC on the safe list to a waypoint at once.",
                     {"op": "relocate_npc", "instance": "BAU_901_BAUER", "waypoint": "NW_BIGFARM_KITCHEN"}),
    "remove_npc": ("People", "Takes an NPC on the safe list out of the world.", {"op": "remove_npc", "instance": "BAU_901_BAUER"}),
    "return_npc": ("People", "Brings back an NPC a story removed, at a position.",
                   {"op": "return_npc", "instance": "BAU_901_BAUER", "position": [0, 0, 0]}),
    "attack": ("People", "One of the story's people goes for the hero (or, with target, for another of them) with his "
                         "fists: the game's own brawl, ended by a knock-down, never a killing. Waits until no "
                         "conversation runs; give the rule a check that the hero is close.",
               {"op": "attack", "npc": "SLD_819_SOELDNER", "target": "BAU_904_BAUER"}),
    # Items and rewards
    "define_item": ("Items", "An item of the story's own, on an unused carrier: name, rows, value, damage, look or model.",
                    {"op": "define_item", "item": "MONDALOE", "like": "ITPL_HEALTH_HERB_01", "name": "Mondaloe",
                     "look": {"model": "mondaloe.obj"}}),
    "place_item": ("Items", "Lays an item at a waypoint.", {"op": "place_item", "instance": "MONDALOE", "waypoint": "NW_BIGFARM_SHEEP2_04"}),
    "npc_item": ("Items", "Puts an item into someone's pockets for real: he can be robbed of it, it can be looted from "
                          "him when he lies down, a trader may sell it. Check where it is with npc_has and has_item.",
                 {"op": "npc_item", "npc": "SLD_807_BULLCO", "instance": "OLES_TALER"}),
    "give_item": ("Items", "Gives the hero an item, as the game's own handover.", {"op": "give_item", "instance": "ITMI_GOLD", "count": 50}),
    "give_xp": ("Items", "Experience with the game's own message and sound, at most 300.", {"op": "give_xp", "amount": 150}),
    # Effects
    "trip": ("Effects", "A trip of a few minutes with its own music, picture and thoughts.",
             {"op": "trip", "profile": "kriegsgesang"}),
    # The story as a whole
    "begin_story": ("runtime", "Written by the game when a story starts: its day and cast.",
                    {"op": "begin_story", "story": "story_6", "title": "Der weiße Wolf", "day": 4, "cast": ["BAU_912_PEPE"]}),
    "end_story": ("Story", "Ends the story: its rules, scenes and topics are retired. Put it in every ending rule; the "
                           "story is filled in when it is played. Closures end with it by themselves.",
                  {"op": "end_story", "outcome": "returned"}),
}

GROUPS = ["Knowledge", "Dialogue", "Rules", "People", "Items", "Effects", "Story", "runtime"]


def render():
    if "gothic" not in sys.modules:   # outside the game: story only needs the module to exist
        import types
        sys.modules["gothic"] = types.ModuleType("gothic")
    from dm import story
    lines = ["# Story operations", "",
             "Generated by `python3 python/dm/op_reference.py` from `python/dm/op_reference.py`; do not edit by hand.",
             "Every operation is validated when a plan is submitted (`story.Story.validate`). The rules for using them are",
             "in `docs/director-brief.md`; live conditions are in `python/dm/checks.py`, deeds in `python/dm/perceptions.py`.",
             ""]
    for group in GROUPS:
        lines += [f"## {'Written by the game master itself' if group == 'runtime' else group}", ""]
        for name, (where, text, example) in OPS.items():
            if where != group:
                continue
            assert name in story.OPS, name
            lines += [f"### `{name}`", "", text, "", "```json", json.dumps(example, ensure_ascii=False), "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    DOC.write_text(render(), encoding="utf-8")
    print(f"wrote {DOC}")
