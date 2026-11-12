"""Breaking long lines into sentences. Run: python3 python/dm/test_split_lines.py"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import split_lines as sl  # noqa: E402

assert sl.sentences("Gestopft. Die Pfeife neben dem Wahrsager. Setz dich hin und zieh.") == \
    ["Gestopft. Die Pfeife neben dem Wahrsager.", "Setz dich hin und zieh."]          # short ones join a neighbour
assert sl.sentences("Ein Satz … und noch was. Zweiter langer Satz, wirklich lang genug.") == \
    ["Ein Satz … und noch was.", "Zweiter langer Satz, wirklich lang genug."]          # an ellipsis mid-sentence stays
assert sl.sentences("Nur ein Satz hier.") == ["Nur ein Satz hier."]

graph = {"start": "a", "nodes": {
    "a": {"line": "Das ist der erste lange Satz hier. Das ist der zweite lange Satz dort. Und dann der dritte lange Satz.",
          "sets": ["met"], "teaches": ["met"], "choices": [{"text": "Ja?", "goto": "b"}]},
    "b": {"line": "Erster Satz ist ziemlich lang hier. Zweiter Satz auch ganz schön lang.", "choices": [],
          "returns": "a"},
    "c": {"line": "Erster Satz ist ziemlich lang hier. Zweiter Satz auch ganz schön lang.", "choices": [],
          "variants": [{"when": "x", "line": "Anders."}]}}}
assert sl.split_graph(graph) == 2
n = graph["nodes"]
assert n["a"]["line"] == "Das ist der erste lange Satz hier." and n["a"]["sets"] == ["met"] and n["a"]["choices"] == []
assert n["a"]["returns"] == "a_2" and n["a_2"]["returns"] == "a_3"
assert n["a"]["chain"] and n["a_2"]["chain"] and "chain" not in n["a_3"]
assert n["a_3"]["choices"] == [{"text": "Ja?", "goto": "b"}] and "sets" not in n["a_3"]   # choices at the end
assert n["b"]["returns"] == "b_2" and n["b_2"]["returns"] == "a"                     # its own returns at the end
assert "c_2" not in n                                                                  # variants: left whole
assert sl.split_graph(graph) == 0                                                      # twice changes nothing
print("split_lines tests passed")
