"""Namespacing a story for one game among several. Run: python3 python/dm/test_play_story.py"""

import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.modules.setdefault("bridge", types.ModuleType("bridge"))
import play_story  # noqa: E402

plan = [
    {"op": "commit_fact", "id": "truth", "text": "x"},
    {"op": "add_topic", "id": "t", "npc": "VLK_456_ABUYIN", "requires": ["legend"], "unless": "blend_mixed",
     "checks": [{"type": "hour", "from": 0, "to": 2}],
     "graph": {"voice": "13", "start": "a", "nodes": {
         "a": {"line": "Hm.", "sets": ["pipe_ready"], "variants": [{"when": "geraucht", "line": "Na?"}],
               "choices": [{"text": "Ja.", "requires": ["legend", "hero_mage"], "unless": "x:already", "ends": True}]}}}},
    {"op": "add_rule", "id": "r", "when": ["pipe_ready"], "unless": ["geraucht"],
     "on": {"event": "used_object", "object": "SMOKE", "near": [1, 2, 1.5]},
     "ops": [{"op": "set_flag", "name": "geraucht", "value": True}, {"op": "journal", "topic": "T", "entry": "e"}]},
]
out = play_story.namespaced(plan, "story_5")
fact, topic, rule = out
assert fact["id"] == "story_5:truth" and topic["id"] == "story_5:t" and rule["id"] == "story_5:r"
assert topic["requires"] == ["story_5:legend"] and topic["unless"] == "story_5:blend_mixed"
node = topic["graph"]["nodes"]["a"]
assert node["sets"] == ["story_5:pipe_ready"] and node["variants"][0]["when"] == "story_5:geraucht"
choice = node["choices"][0]
assert choice["requires"] == ["story_5:legend", "hero_mage"]      # the runtime's guild flag stays shared
assert choice["unless"] == "x:already"                             # already namespaced: left alone
assert rule["when"] == ["story_5:pipe_ready"] and rule["unless"] == ["story_5:geraucht"]
assert rule["ops"][0]["name"] == "story_5:geraucht" and rule["on"]["object"] == "SMOKE"
assert topic["checks"] == [{"type": "hour", "from": 0, "to": 2}] and node["line"] == "Hm."
assert plan[1]["requires"] == ["legend"]                           # the story file itself is untouched
print("play_story tests passed")

# Voicing a story covers its topic titles too: the hero says them, and they live in the plan, not a conversation.
story = {"conversations": {"A": {"voice": "13", "start": "a", "nodes": {}}},
         "plan": [{"op": "add_topic", "id": "t", "npc": "X", "title": "Kanntest du ihn?", "graph": {}},
                  {"op": "add_rule", "id": "r", "when": [], "ops": [{"op": "add_topic", "id": "u", "title": "Und?"}]}]}
graphs = play_story.voice_graphs(story, "newgame_9")
assert graphs["newgame_9__TOPIC_TITLES"] == {"voice": "15", "narration": ["Kanntest du ihn?", "Und?"]}
assert "newgame_9__A" in graphs
print("voice graphs ok")

# An ending rule ends its own story without naming it.
ended = play_story.namespaced([{"op": "add_rule", "id": "won", "when": [], "ops": [{"op": "end_story", "outcome": "won"}]}], "story_9")
assert ended[0]["ops"][0] == {"op": "end_story", "outcome": "won", "story": "story_9"}, ended
print("own ending ok")
