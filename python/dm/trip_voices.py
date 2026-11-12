"""Voices the hero's trip thoughts and the NPC lines of the special trip dialogue (in every NPC voice), then distorts
the hero's: the plain take is baked as usual, and a copy is made with the
pitch dropped, a slow vibrato, a flanger and a long cellar echo, stored as delivery "rausch". Private use only, like
every voice: the takes never leave this machine.

    python3 python/dm/trip_voices.py [story.json ...]          the default thoughts, plus those of any trip in the stories
    python3 python/dm/trip_voices.py --again [story.json ...]  only the distortion again, from the plain takes

Needs the voice model (bake_voices.py setup) and ffmpeg.
"""

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from dm import trip, voices  # noqa: E402

# Pitch down by a tenth with the tempo kept, a slow wobble, a flanger, an echo off stone, the top rolled off, then
# brought up loud: the effects eat loudness, and a thought has to carry over the trip's music.
FILTER = ("asetrate={rate}*0.9,aresample={rate},atempo=1.111,vibrato=f=3.5:d=0.35,"
          "flanger=delay=4:depth=3:speed=0.25,aecho=0.8:0.6:180|340:0.35|0.22,lowpass=f=5500,"
          "loudnorm=I=-12:TP=-1.0:LRA=7")


def story_thoughts(path):
    """The thought lines of every trip a story plays."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    found = []

    def walk(ops):
        for op in ops:
            if op.get("op") == "trip" and op.get("thoughts"):
                found.extend(text for _, text in op["thoughts"])
            walk(op.get("ops", []))
    walk(data.get("plan", []))
    return found


def distort(text):
    """The distorted copy of a baked line. False if the plain take is missing."""
    source = voices.audio_path(trip.HERO_VOICE, text)
    if not source.exists():
        return False
    rate = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate",
                           "-of", "csv=p=0", str(source)], capture_output=True, text=True, check=True).stdout.strip()
    target = voices.audio_path(trip.HERO_VOICE, text, trip.DELIVERY)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-af", FILTER.format(rate=rate),
                    "-ar", rate, "-c:a", "pcm_s16le", str(partial)], check=True)
    partial.replace(target)   # never a half-written take where the game looks for one
    return True


def redistort(stories):
    """Makes the distorted takes again from the plain ones, without voicing anything new."""
    lines = list(dict.fromkeys(trip.thought_lines() + [line for path in stories for line in story_thoughts(path)]))
    print(f"{sum(distort(line) for line in lines)} of {len(lines)} thoughts distorted again")


# Every NPC voice that is not a guard's, for the special trip dialogue: its lines are spoken in all of them.
SPECIAL_VOICES = ["01", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "16", "17"]


# Every voice a militiaman or paladin speaks with, for the guards' own trip lines.
GUARD_VOICES = ["01", "03", "04", "05", "06", "07", "08", "09", "11", "12", "13"]

# The voice number of each person in trip.SPECIAL_PEOPLE.
SPECIAL_PEOPLE_VOICES = {"VLK_456_ABUYIN": "13", "VLK_454_BUERGER": "01"}


# Who speaks each trip voice file's lines, for the story library's "Trip-Stimmen" page.
LIBRARY_LABELS = {"trip__thoughts": "Held · Gedanken im Rausch (Rohaufnahme, im Spiel verzerrt)", "trip__after_15": "Held · nüchtern",
                  "trip__after_13": "Abuyin · Nachgespräch", "trip__special_vlk_456_abuyin": "Abuyin · im Rausch",
                  "trip__after_16": "Nadja · Abschied", "trip__after_07": "Bromor · Abschied",
                  "trip__after_11": "Borka · Abschied", "trip__after_05": "Vatras · Morgen danach"}


def write_library(all_graphs):
    """Writes the trip's lines as a page for the story library (newgame/story_trip.json and its graphs_trip.json):
    one conversation per speaker, one node per line. Not a story to play: a place to hear every recording and choose
    the better take. The hero's thoughts appear as their plain recording, the one new takes can be made of; the game
    plays a distorted copy, remade from the chosen take with --again."""
    conversations = {}
    for key, graph in all_graphs.items():
        label = LIBRARY_LABELS.get(key) or (f"Wache · Stimme {graph['voice']}" if key.startswith("trip__guard_")
                                            else f"Jemand · Stimme {graph['voice']}")
        delivery = None
        nodes = {}
        lines = graph["narration"]
        for i, line in enumerate(lines):
            node = {"line": line, "choices": []}
            if delivery:
                node["delivery"] = delivery
            if i + 1 < len(lines):
                node["returns"] = f"n{i + 1}"
            nodes[f"n{i}"] = node
        conversations[label] = {"voice": graph["voice"], "start": "n0", "nodes": nodes}
    story = {"title": "Trip-Stimmen", "premise": "Alle Zeilen der Trips zum Anhören und Sortieren: Gedanken, "
             "Gespräche im Rausch, Wachen, Trinker, Abschiede und das Nachgespräch. Keine Geschichte zum Spielen.",
             "hidden_truth": "", "plot": {"facts": {}}, "conversations": conversations, "plan": [], "voices_only": True}
    folder = voices.RUNTIME_DIR / "newgame"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "story_trip.json").write_text(json.dumps(story, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "graphs_trip.json").write_text(
        json.dumps({f"newgame_trip__{k}": g for k, g in conversations.items()}, ensure_ascii=False, indent=1),
        encoding="utf-8")


def main(stories):
    lines = trip.thought_lines() + [line for path in stories for line in story_thoughts(path)]
    lines = list(dict.fromkeys(lines))
    graphs = voices.RUNTIME_DIR / "trip_thoughts.json"
    npc_lines = (trip.SPECIAL_OPENERS + trip.SPECIAL_CLOSERS
                 + trip.SPECIAL_DRINKERS["openers"] + trip.SPECIAL_DRINKERS["closers"])
    all_graphs = {"trip__thoughts": {"voice": trip.HERO_VOICE, "narration": lines}}
    all_graphs.update({f"trip__special_{v}": {"voice": v, "narration": npc_lines} for v in SPECIAL_VOICES})
    all_graphs.update({f"trip__special_{name.lower()}": {"voice": SPECIAL_PEOPLE_VOICES[name],
                                                         "narration": own["openers"] + own["closers"]}
                       for name, own in trip.SPECIAL_PEOPLE.items()})
    guard_lines = trip.SPECIAL_GUARDS["openers"] + trip.SPECIAL_GUARDS["closers"]
    all_graphs.update({f"trip__guard_{v}": {"voice": v, "narration": guard_lines} for v in GUARD_VOICES})
    for (instance, _name), own in trip.SPECIAL_BY_NAME.items():
        all_graphs[f"trip__special_{instance.lower()}"] = {"voice": SPECIAL_PEOPLE_VOICES[instance],
                                                           "narration": own["openers"] + own["closers"]}
    for voice, line in trip.after_lines():
        all_graphs.setdefault(f"trip__after_{voice}", {"voice": voice, "narration": []})["narration"].append(line)
    graphs.write_text(json.dumps(all_graphs, ensure_ascii=False, indent=1), encoding="utf-8")
    game = json.loads((voices.RUNTIME_DIR / "settings.json").read_text(encoding="utf-8"))["game"]
    subprocess.run([sys.executable, str(HERE / "bake_voices.py"), "all", game, str(graphs)], check=True)
    made = sum(distort(line) for line in lines)
    print(f"{made} of {len(lines)} thoughts distorted")
    write_library(all_graphs)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--library"]:
        write_library(json.loads((voices.RUNTIME_DIR / "trip_thoughts.json").read_text(encoding="utf-8")))
    elif sys.argv[1:2] == ["--again"]:
        redistort(sys.argv[2:])
    else:
        main(sys.argv[1:])
