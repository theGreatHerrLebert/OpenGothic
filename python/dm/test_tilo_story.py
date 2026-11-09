"""The real story must pass the checker. Run: python3 python/dm/test_tilo_story.py"""

import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.modules.setdefault("gothic", types.ModuleType("gothic"))

from dm import graph, knowledge  # noqa: E402
from dm.stories import tilo  # noqa: E402

for name, conversation in tilo.all_graphs().items():
    problem = graph.validate(conversation)
    assert problem is None, (name, problem)

checked = tilo.conversations_to_check()
assert len(checked) == len(tilo.all_graphs()), (len(checked), len(tilo.all_graphs()))

errors, warnings = knowledge.check(tilo.PLOT, checked)
assert errors == [], errors
print("tilo story passes;", len(checked), "conversations; warnings:", warnings)
