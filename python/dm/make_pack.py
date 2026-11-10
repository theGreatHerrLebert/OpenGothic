"""Packs one story for a friend: the story and its dialogue, no audio. The voices are made on their machine.

    python3 python/dm/make_pack.py "Der heilige Hering"     (title or blind id)

Writes python/dm_runtime/packs/<name>.zip. Cloned voices and reference clips never go into a pack: they are
generated from the receiver's own Gothic install with bake_voices.py.
"""

import json
import pathlib
import re
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import library  # noqa: E402
from dm import voices  # noqa: E402

PACKS = voices.RUNTIME_DIR / "packs"

README = """# {title}

Eine Geschichte für den KI-Spielleiter von OpenGothic. Dieses Paket enthält nur Text: die Geschichte und ihre Dialoge.
Die Stimmen erzeugst du selbst aus deiner eigenen Gothic-II-Installation, sie verlassen deinen Rechner nie.

Du brauchst den Zweig `python-repl` von OpenGothic, eine deutsche Installation von Gothic II: Die Nacht des Raben und
Python 3.11 oder 3.12. Unter Windows startest du Python mit `py`, sonst mit `python3`.

## 1. Paket ablegen

Entpacke diesen Ordner nach `python/dm_runtime/packs/{slug}/` im OpenGothic-Ordner.

## 2. Stimmen erzeugen

Einmalig das Sprachmodell einrichten (lädt einige GB, mit NVIDIA-Grafikkarte deutlich schneller):

    py python/dm/bake_voices.py setup

Dann alle Zeilen dieser Geschichte, {lines} Stück. Der Pfad ist dein Gothic-Ordner:

    py python/dm/bake_voices.py all "C:/Spiele/Gothic II" python/dm_runtime/packs/{slug}/graphs.json

Das holt zuerst je Sprecher vier Zeilen aus deiner Installation als Vorlage und erzeugt dann jede Zeile. Abgebrochene
Läufe setzen dort fort, wo sie aufgehört haben.

## 3. Spielen

Das Spiel mit Brücke starten. Unter Windows lege den Brückenordner fest, damit Spiel und Skript ihn gleich finden:

    set OPENGOTHIC_PY_BRIDGE=1
    set OPENGOTHIC_PY_BRIDGE_DIR=C:/Temp/opengothic-bridge
    build/opengothic/Gothic2Notr.exe -g "C:/Spiele/Gothic II"

Einen Spielstand laden, dann in einem zweiten Fenster (mit demselben `OPENGOTHIC_PY_BRIDGE_DIR`):

    py python/dm/play_story.py python/dm_runtime/packs/{slug}/story.json

Alt+O blendet die Anzeige des Spielleiters ein.

## Wichtig

Die erzeugten Stimmen sind Nachbildungen der Originalsprecher. Gib sie nicht weiter und lade sie nirgends hoch.
"""


def slug(title):
    plain = title.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "geschichte"


def find(name):
    for entry in library.entries():
        if not entry["demo"] and name in (entry["id"], entry["title"]):
            return entry
    return None


def build(name):
    entry = find(name)
    if entry is None:
        raise SystemExit(f"no generated story called {name!r}")
    data, conversations = library.generated(entry["id"])
    folder = slug(entry["title"])
    # graph names carry the story's file name, which says where it came from; the pack only uses its own name
    graphs = {f"{folder}__{key}": graph for key, graph in conversations.items()}
    lines = sum(1 for line in {(voice, text, delivery) for graph in graphs.values()
                               for voice, text, delivery in _spoken(graph)})
    # a delivery (a threatening 09, say) is cloned from hand-picked game lines; the pack names them, never the audio
    refs = {}
    for name in _needed(graphs):
        if "_" in name:
            keys = _reference_keys(name)
            if not keys:
                raise SystemExit(f"cannot tell which game lines make the voice {name}; rebuild it with bake_voices.py named")
            refs[name] = keys
    PACKS.mkdir(parents=True, exist_ok=True)
    target = PACKS / f"{folder}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr(f"{folder}/story.json", json.dumps(data, ensure_ascii=False, indent=1))
        pack.writestr(f"{folder}/graphs.json", json.dumps(graphs, ensure_ascii=False, indent=1))
        if refs:
            pack.writestr(f"{folder}/refs.json", json.dumps(refs, indent=1))
        pack.writestr(f"{folder}/LIESMICH.md", README.format(title=entry["title"], slug=folder, lines=lines))
        names = pack.namelist()
    assert not any(n.lower().endswith((".wav", ".mp3", ".ogg", ".safetensors")) for n in names)
    assert not any(n.endswith(".txt") for n in names)   # a reference's text quotes the game
    return target, names, lines


def _spoken(graph):
    from dm import bake_voices
    return bake_voices.spoken_lines(graph)


def _needed(graphs):
    from dm import bake_voices
    return bake_voices.needed_voices(graphs)


def _reference_keys(name):
    from dm import bake_voices
    return bake_voices.reference_keys(name)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path, names, lines = build(sys.argv[1])
    print(path)
    for name in names:
        print("  " + name)
    print(f"{lines} lines to voice on the receiving machine")
