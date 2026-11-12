"""The operation reference covers every operation and is up to date. Run: python3 python/dm/test_op_reference.py"""

import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.modules.setdefault("gothic", types.ModuleType("gothic"))
from dm import op_reference, story  # noqa: E402

missing = set(story.OPS) - set(op_reference.OPS)
assert not missing, f"operations without a reference entry: {sorted(missing)}"
assert not set(op_reference.OPS) - set(story.OPS), "reference describes operations that do not exist"
assert op_reference.DOC.read_text(encoding="utf-8") == op_reference.render(), \
    "docs/story-ops.md is stale: run python3 python/dm/op_reference.py"
print("op reference ok")
