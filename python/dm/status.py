"""Reports what the DM is doing, for the in-game overlay. Needs no game, so any tool can call it.

    status.report("Stimmen", 23, 41)
    status.report("schreibt", quest="Der heilige Hering")
    python3 python/dm/status.py demo      # walks through every stage, to check how the overlay looks

Stage names are a fixed set. The only free text is the optional quest title, which the player chose to see, and up
to three omens: cryptic lines the author wrote for the coming story, checked to be short and to name nobody.
"""

import json
import os
import pathlib
import re
import sys
import tempfile
import time

PATH = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "dm_status.json"
STAGES = {"schreibt", "prüft", "Stimmen", "bereit"}
STALE_SECONDS = 120   # a tool that died must not leave the panel up forever
READY_SECONDS = 20


# Omens: up to three cryptic lines the author wrote for the story being prepared, shown in turn on the second line.
# They are the one place a story reaches the panel, so they are checked: short, and naming nobody with a sheet.
MAX_OMENS = 3
MAX_OMEN = 55
OMEN_SECONDS = 12
GENERIC_NAMES = {"Bauer", "Bürger", "Bürgerin", "Arbeiter", "Magd"}
CHARACTERS = pathlib.Path(__file__).resolve().parent / "characters"


TITLES = {"Lord", "Meister", "Bruder", "Schwester", "Vater", "Mutter", "Sir", "Herr", "Frau", "Der", "Die", "Das"}


def _names():
    names = set()
    for path in CHARACTERS.glob("*.json"):
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("name")
        except ValueError:
            continue
        if name and name not in GENERIC_NAMES:
            names.add(name)
    return names


def _name_words(names):
    """Each name's own words, without titles: 'Lord Andre' is caught as 'Andre'."""
    return {word for name in names for word in re.findall(r"[^\W\d_][\w'-]*", name)
            if word not in TITLES and word not in GENERIC_NAMES and len(word) > 2}


def check_omens(omens, names=None, extra=()):
    """Raise ValueError unless the omens are safe to show. extra: names the story itself gives people."""
    if not isinstance(omens, list) or len(omens) > MAX_OMENS:
        raise ValueError(f"omens must be a list of at most {MAX_OMENS}")
    words = _name_words((_names() if names is None else set(names)) | set(extra))
    for omen in omens:
        if not isinstance(omen, str) or not omen.strip() or len(omen) > MAX_OMEN:
            raise ValueError(f"omen must be text of at most {MAX_OMEN} characters: {omen!r}")
        # A German possessive or genitive ("Tilos", "Andres", "Hans'") counts as the name.
        named = [w for w in words if re.search(rf"\b{re.escape(w)}(?:s|es|')?(?!\w)", omen, re.IGNORECASE)]
        if named:
            raise ValueError(f"omen names someone: {sorted(named)[0]}")


# Writing has no countable steps, so its bar fills against the usual writing time and stops short of full: an
# estimate, marked with "~", that never claims to be done.
EXPECTED_WRITING = 15 * 60
ESTIMATE_CAP = 0.95
# Once a story has a first person to meet, the panel shows only near them (game units are centimetres).
NEAR = 3000


def report(stage, done=None, total=None, quest=None, omens=None, started=None, expected=None, anchor=None,
           names=()):
    """started/expected (seconds since the epoch, seconds) give writing its estimated bar; anchor is the NPC instance
    the story starts with (or a list of them), near whom alone the panel shows. Omens and anchor carry over to later
    reports for the same quest. names: people the story itself names, which omens must not mention either."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    previous = entry()
    if quest and previous and previous.get("quest") == quest:
        # Tools that know only the title (the voice baker) keep what was set for this quest.
        omens = omens or previous.get("omens")
        anchor = anchor or previous.get("anchor")
    if omens:
        check_omens(omens, extra=names)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=PATH.parent, delete=False, suffix=".tmp") as f:
        json.dump({"stage": stage, "done": done, "total": total, "quest": quest, "omens": omens or [],
                   "started": started, "expected": expected, "anchor": anchor, "at": time.time()}, f)
    os.replace(f.name, PATH)  # the game may read at any moment, so it must never see half a file


def clear():
    PATH.unlink(missing_ok=True)


def describe(entry, now):
    """The panel's (text, progress), with progress -1 when the length is unknown, or None to hide it."""
    age = now - entry["at"]
    if age > (READY_SECONDS if entry["stage"] == "bereit" else STALE_SECONDS):
        return None
    # The second line: the quest title and the omens take turns.
    second = ([entry["quest"]] if entry.get("quest") else []) + list(entry.get("omens") or [])
    quest = f"\n{second[int(now // OMEN_SECONDS) % len(second)]}" if second else ""
    if entry["stage"] == "bereit":
        return "DM: bereit" + quest, 1.0
    done, total = entry.get("done"), entry.get("total")
    if done is not None and total:
        return f"DM: {entry['stage']} {done}/{total}{quest}", min(done / total, 1.0)
    if entry.get("started"):
        expected = entry.get("expected") or EXPECTED_WRITING
        elapsed = max(0.0, now - entry["started"])
        return (f"DM: {entry['stage']} ~ {int(elapsed // 60)}/{int(round(expected / 60))} min{quest}",
                min(elapsed / expected, ESTIMATE_CAP))
    return f"DM: {entry['stage']}...{quest}", -1.0


def entry():
    """The raw status, or None."""
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read(now=None):
    current = entry()
    return None if current is None else describe(current, time.time() if now is None else now)


def near(here, there, limit=NEAR):
    """Whether two (x, y, z) positions are within limit, measured across the ground."""
    return (here[0] - there[0]) ** 2 + (here[2] - there[2]) ** 2 <= limit * limit


def _demo():
    quest = "Der heilige Hering"
    report("schreibt", quest=quest)
    time.sleep(6)
    for n in range(1, 6):
        report("prüft", n, 5, quest)
        time.sleep(1)
    for n in range(1, 42, 2):
        report("Stimmen", n, 41, quest)
        time.sleep(0.4)
    report("bereit", quest=quest)


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        _demo()
