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
SPECIAL_PEOPLE_VOICES = {"VLK_456_ABUYIN": "13"}


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
    for voice, line in trip.after_lines():
        all_graphs.setdefault(f"trip__after_{voice}", {"voice": voice, "narration": []})["narration"].append(line)
    graphs.write_text(json.dumps(all_graphs, ensure_ascii=False, indent=1), encoding="utf-8")
    game = json.loads((voices.RUNTIME_DIR / "settings.json").read_text(encoding="utf-8"))["game"]
    subprocess.run([sys.executable, str(HERE / "bake_voices.py"), "all", game, str(graphs)], check=True)
    made = sum(distort(line) for line in lines)
    print(f"{made} of {len(lines)} thoughts distorted")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--again"]:
        redistort(sys.argv[2:])
    else:
        main(sys.argv[1:])
