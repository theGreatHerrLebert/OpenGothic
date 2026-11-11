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
# Omens: checked when reported, and the second line takes turns between title and omens.
with tempfile.TemporaryDirectory() as d:
    status.PATH = pathlib.Path(d) / "s.json"
    for bad in (["x" * (status.MAX_OMEN + 1)], ["a", "b", "c", "d"], [""], "a string"):
        try:
            status.check_omens(bad, names=set())
            raise SystemExit(f"bad omens accepted: {bad!r}")
        except ValueError:
            pass
    try:
        status.check_omens(["Lobart weiß mehr, als er sagt"], names={"Lobart"})
        raise SystemExit("an omen naming someone was accepted")
    except ValueError:
        pass
    status.check_omens(["Ein Schaf zu wenig, ein Wort zu viel …"], names={"Lobart"})
    for named, names in (("Tilos Schuld wird heute beglichen.", {"Tilo"}),          # possessive
                         ("Andre weiß, wer das Silber nahm.", {"Lord Andre"}),       # title dropped
                         ("Hans' Hut liegt im Graben.", {"Hans"}),
                         ("lobart schläft schlecht", {"Lobart"})):
        try:
            status.check_omens([named], names=names)
            raise SystemExit(f"named omen accepted: {named}")
        except ValueError:
            pass
    try:
        status.check_omens(["Jost hat zu viel gehört"], names=set(), extra=["Jost"])   # named by the story
        raise SystemExit("an omen naming a story's own character was accepted")
    except ValueError:
        pass
    status.check_omens(["Der Meister schweigt"], names={"Meister Harad"})   # a title alone names nobody
    status.report("schreibt", omens=["Eins", "Zwei"])
    entry = status.json.loads(status.PATH.read_text())
    seen = {status.describe(entry, entry["at"] + i * status.OMEN_SECONDS)[0] for i in range(2)}
    assert seen == {"DM: schreibt...\nEins", "DM: schreibt...\nZwei"}
    status.report("Stimmen", 1, 2, "Titel", omens=["Eins"])
    entry = status.json.loads(status.PATH.read_text())
    seen = {status.describe(entry, entry["at"] + i * status.OMEN_SECONDS)[0] for i in range(2)}
    assert seen == {"DM: Stimmen 1/2\nTitel", "DM: Stimmen 1/2\nEins"}

# Writing: an estimated bar against the usual time, marked "~", never full.
with tempfile.TemporaryDirectory() as d:
    status.PATH = pathlib.Path(d) / "s.json"
    status.report("schreibt", started=1000.0, expected=900)
    raw = status.entry()
    text, progress = status.describe({**raw, "at": 1360.0}, 1360.0)
    assert text == "DM: schreibt ~ 6/15 min" and abs(progress - 0.4) < 1e-9
    assert status.describe({**raw, "at": 9000.0}, 9000.0)[1] == status.ESTIMATE_CAP
    status.report("Stimmen", 3, 30, anchor="BAU_953_BAUER")
    assert status.entry()["anchor"] == "BAU_953_BAUER"
    status.report("prüft", 1, 2, "Titel", omens=["Eins"], anchor=["A", "B"])
    status.report("Stimmen", 1, 9, "Titel")                       # the baker knows only the title
    assert status.entry()["omens"] == ["Eins"] and status.entry()["anchor"] == ["A", "B"]
    status.report("Stimmen", 1, 9, "Anderer Titel")
    assert status.entry()["omens"] == [] and status.entry()["anchor"] is None

# A ready story with an anchor stays announced until met, then hides like any other.
with tempfile.NamedTemporaryFile(suffix=".json") as f:
    status.PATH = pathlib.Path(f.name)
    status.report("bereit", quest="Titel", anchor=["A"])
    raw = status.entry()
    assert status.describe(raw, raw["at"] + 3600)[0] == "DM: bereit\nTitel"
    status.mark_met()
    raw = status.entry()
    assert raw["met"] and status.describe(raw, raw["at"] + status.READY_SECONDS + 1) is None
    status.report("bereit", quest="Titel")                     # a later report keeps "met"
    raw = status.entry()
    assert raw["met"] and status.describe(raw, raw["at"] + status.READY_SECONDS + 1) is None
    status.report("bereit", quest="Anderer")                   # no anchor: the usual short notice
    raw = status.entry()
    assert status.describe(raw, raw["at"] + status.READY_SECONDS + 1) is None

# Near: across the ground, height ignored.
assert status.near((0, 0, 0), (9999, 5000, 0)) and not status.near((0, 0, 0), (8000, 0, 8000))
# Closeness: full within FULL, nothing at NEAR, evenly in between, height ignored.
assert status.closeness((0, 0, 0), (status.FULL, 900, 0)) == 1.0
assert status.closeness((0, 0, 0), (status.NEAR, 0, 0)) == 0.0
middle = (status.NEAR + status.FULL) / 2
assert abs(status.closeness((0, 0, 0), (0, 0, middle)) - 0.5) < 1e-9

print("status ok")
