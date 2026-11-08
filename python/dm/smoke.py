"""In-game check of the story layer.

    py import dm.smoke as s
    py s.run()
"""

import gothic

from dm import story

GRAPH = {"start": "a", "nodes": {
    "a": {"line": "Hast du den Novizen gesehen? Er kam nicht zurück.", "sets": "smoke_met", "choices": [
        {"text": "Welchen Novizen?", "goto": "b"},
        {"text": "Leb wohl.", "ends": True}]},
    "b": {"line": "Den Jungen aus der Bibliothek. Seltsam, nicht wahr?", "choices": [
        {"text": "Zurück.", "goto": "a"},
        {"text": "Leb wohl.", "ends": True}]},
}}


def run():
    story.start()
    instance = "VLK_4250_JORGEN"
    speaker = gothic.world.spawn(instance)
    speaker.display_name = "Zeuge"
    waypoint = gothic.player.waypoint
    count = gothic.world.npc_count

    story.SAFE_TO_REMOVE.add("TEST_NOT_A_REAL_NPC")
    checks = {
        "bread is an item": gothic.world.instance_kind("ItFo_Bread") == "item",
        "speaker is an npc": gothic.world.instance_kind(instance) == "npc",
        "unknown is None": gothic.world.instance_kind("NOPE_XYZ") is None,
        "waypoint exists": gothic.world.has_waypoint(waypoint),
        "bad waypoint": not gothic.world.has_waypoint("NOPE_XYZ"),
    }

    story.submit("Rauchtest", [
        {"op": "commit_fact", "id": "smoke_%d" % len(story._story.log), "text": "Der Zeuge lügt.", "known_by": [instance]},
        {"op": "place_item", "instance": "ItFo_Bread", "waypoint": waypoint},
        {"op": "attach_dialogue_graph", "npc": instance, "graph": GRAPH},
    ])

    for name, passed in checks.items():
        print(("PASS " if passed else "FAIL ") + name)
    print(f"submitted; npcs={count}, bread at {waypoint}; talk to Zeuge")
    return all(checks.values())


def report():
    print("results", story.results())
    print("facts", list(story.state()["facts"]))
    print("flags", story.state()["flags"])
    print("graphs", list(story.state()["graphs"]))
