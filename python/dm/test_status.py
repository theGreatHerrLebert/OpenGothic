"""Overlay status tests. Run: python3 python/dm/test_status.py"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import status  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    status.PATH = pathlib.Path(d) / "s.json"
    assert status.read() is None
    status.report("Stimmen", 23, 46)
    text, progress = status.read()
    assert text == "DM: Stimmen 23/46" and progress == 0.5
    status.report("schreibt")
    assert status.read() == ("DM: schreibt...", -1.0)
    status.report("Stimmen", 1, 2, "Der Bestienvogt")
    assert status.read() == ("DM: Stimmen 1/2\nDer Bestienvogt", 0.5)
    status.report("bereit", quest="Der Bestienvogt")
    assert status.read()[0] == "DM: bereit\nDer Bestienvogt"
    at = status.time.time()
    assert status.read(at + status.STALE_SECONDS + 1) is None   # a dead tool does not stay on screen
    status.report("bereit")
    assert status.read()[1] == 1.0 and status.read(at + status.READY_SECONDS + 5) is None
    status.PATH.write_text("{half")
    assert status.read() is None                                # never crash the game on a bad file
    status.report("prüft", 9, 5)
    assert status.read()[1] == 1.0
    status.clear()
    assert status.read() is None
    try:
        status.report("Der heilige Hering")
        raise SystemExit("a free-text stage must be refused")
    except ValueError:
        pass
print("status ok")
