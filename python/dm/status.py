"""Reports what the DM is doing, for the in-game overlay. Needs no game, so any tool can call it.

    status.report("Stimmen", 23, 41)
    status.report("schreibt")
    python3 python/dm/status.py demo      # walks through every stage, to check how the overlay looks

Only a fixed set of stage names exists, and counts are the only detail, so the overlay cannot spoil a story.
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


def report(stage, done=None, total=None):
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=PATH.parent, delete=False, suffix=".tmp") as f:
        json.dump({"stage": stage, "done": done, "total": total, "at": time.time()}, f)
    os.replace(f.name, PATH)  # the game may read at any moment, so it must never see half a file


def clear():
    PATH.unlink(missing_ok=True)


def describe(entry, now):
    """The panel's (text, progress), with progress -1 when the length is unknown, or None to hide it."""
    age = now - entry["at"]
    if age > (READY_SECONDS if entry["stage"] == "bereit" else STALE_SECONDS):
        return None
    if entry["stage"] == "bereit":
        return "DM: bereit", 1.0
    done, total = entry.get("done"), entry.get("total")
    if done is not None and total:
        return f"DM: {entry['stage']} {done}/{total}", min(done / total, 1.0)
    return f"DM: {entry['stage']}...", -1.0


def read(now=None):
    try:
        entry = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return describe(entry, time.time() if now is None else now)


def _demo():
    report("schreibt")
    time.sleep(6)
    for n in range(1, 6):
        report("prüft", n, 5)
        time.sleep(1)
    for n in range(1, 42, 2):
        report("Stimmen", n, 41)
        time.sleep(0.4)
    report("bereit")


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        _demo()
