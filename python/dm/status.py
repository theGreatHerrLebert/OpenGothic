"""Reports what the DM is doing, for the in-game overlay. Needs no game, so any tool can call it.

    status.report("Stimmen", 23, 41)
    status.report("schreibt", quest="Der heilige Hering")
    python3 python/dm/status.py demo      # walks through every stage, to check how the overlay looks

Stage names are a fixed set. The only free text is the optional quest title, which the player chose to see.
"""

import json
import os
import pathlib
import sys
import tempfile
import time

PATH = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime" / "dm_status.json"
STAGES = {"schreibt", "prüft", "Stimmen", "bereit"}
STALE_SECONDS = 120   # a tool that died must not leave the panel up forever
READY_SECONDS = 20


def report(stage, done=None, total=None, quest=None):
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=PATH.parent, delete=False, suffix=".tmp") as f:
        json.dump({"stage": stage, "done": done, "total": total, "quest": quest, "at": time.time()}, f)
    os.replace(f.name, PATH)  # the game may read at any moment, so it must never see half a file


def clear():
    PATH.unlink(missing_ok=True)


def describe(entry, now):
    """The panel's (text, progress), with progress -1 when the length is unknown, or None to hide it."""
    age = now - entry["at"]
    if age > (READY_SECONDS if entry["stage"] == "bereit" else STALE_SECONDS):
        return None
    quest = f"\n{entry['quest']}" if entry.get("quest") else ""
    if entry["stage"] == "bereit":
        return "DM: bereit" + quest, 1.0
    done, total = entry.get("done"), entry.get("total")
    if done is not None and total:
        return f"DM: {entry['stage']} {done}/{total}{quest}", min(done / total, 1.0)
    return f"DM: {entry['stage']}...{quest}", -1.0


def read(now=None):
    try:
        entry = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return describe(entry, time.time() if now is None else now)


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
