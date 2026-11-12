"""Trip tests against a fake game. Run: python3 python/dm/test_trip.py

They prove the envelope, the look and the crossfade, not how it looks or sounds in the running game.
"""

import math
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from dm import trip  # noqa: E402

# The Mindcap envelope runs 350 s, as in Solaris, rises to its plateau and lands at zero.
assert trip.length("mindcap") == 350
env, peak, samples = trip.Envelope(trip.PROFILES["mindcap"]), 0.0, []
while env.step():
    peak = max(peak, env.intensity)
    samples.append(env.intensity)
assert env.over and env.intensity == 0.0
assert abs(len(samples) / 60 - 350) < 0.1 and peak > 0.9
assert samples[15 * 60] < 0.1 < samples[150 * 60]          # a slow onset, then well into it

# Stretched to a track's length, it keeps its shape and lasts as long as the track.
env = trip.Envelope(trip.stretched("mindcap", 175))
steps = 0
while env.step():
    steps += 1
assert abs(steps / 60 - 175) < 0.1

# Sober looks like nothing; the peak breathes, washes colour, slows and trembles.
sober = trip.look(0.0, 3.0)
assert sober["fov"] == 0.0 and sober["tint"][3] == 0.0 and sober["time"] == 1.0 and sober["post"] == 0.0
# The colour wash stays on Mindcap's palette: pink, violet, bright green, never a plain red or blue.
for h in (0.0, 0.17, 0.33, 0.5, 0.66, 0.83):
    r, g, b = trip._hue(h)
    assert max(r, g, b) - min(r, g, b) >= 0.25 and not (r > 0.9 and g < 0.2 and b < 0.2)   # vivid, never plain red
peak = trip.look(1.0, 3.0)
assert peak["fov"] == 0.0 and peak["tint"][3] > 0.15 and peak["time"] < 0.8 and peak["shake"] == 0.0  # no wobble, no jitter
assert peak["post"] == 1.0 and trip.look(0.3, 3.0)["post"] == 0.3                                           # the shader follows
assert trip.look(1.0, 0.0)["tint"][:3] != trip.look(1.0, 5.0)["tint"][:3]   # the colour turns, slowly

# No wobble: the view draws in on the beat, gently, more the deeper the trip and the more drum; sober feels nothing.
assert trip.look(0.0, 1.0, pulse=1.0, drums=1.0)["zoom"] == 0.0
peak_look = trip.look(1.0, 1.0, pulse=1.0, drums=1.0)
assert peak_look["fov"] == 0.0 and 0 < peak_look["zoom"] <= 0.05 and trip.look(1.0, 1.0, 1.0, 0.0)["zoom"] == 0.0
# The pulse: drawn in quickly at the beat, relaxed over the rest of it, nothing before the first beat.
assert trip.pulse(0.1, 0.65, 0.5) == 0.0
assert trip.pulse(0.5 + 0.65 * trip.CONTRACT, 0.65, 0.5) > 0.99 and trip.pulse(0.5 + 0.6, 0.65, 0.5) < 0.3
# The bounce: after the release dips, the view is drawn in a little once more, never past normal.
curve = [trip.pulse(0.5 + 0.65 * trip.CONTRACT + i / 120, 0.65, 0.5) for i in range(60)]
dip = min(range(len(curve)), key=lambda i: curve[i] if i < 30 else 9)
assert max(curve[dip:]) > curve[dip] + 0.02 and min(curve) >= 0.0
# Never more than MAX_PULSES full pulls a second, whatever the tempo: count them over ten seconds at 200 BPM. The
# bounce after each is a far smaller second pull, never near the height of the beat.
rises, prev, values = 0, 0.0, []
for i in range(600):
    now_value = trip.pulse(i / 60, 60 / 200, 0.0)
    rises += prev < 0.9 <= now_value
    prev = now_value
    values.append(now_value)
assert rises <= trip.MAX_PULSES * 10, rises
after_peak = values[3:36]
assert max(after_peak[after_peak.index(min(after_peak[:10])):]) - min(after_peak[:10]) < 0.3   # a bounce, not a beat

# Bands: written once from a track, read back per frame without numpy.
import array, tempfile  # noqa: E401,E402
from dm import music_bands  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    track = pathlib.Path(d) / "t.wav"
    values = array.array("f", [0.1, 0.2, 0.3, 0.0, 0.9, 0.2, 0.1, 1.0])
    pathlib.Path(str(track) + ".bands").write_bytes(values.tobytes())
    loaded = music_bands.load(track)
    assert music_bands.at(loaded, 1 / 60)[3] == 1.0 and music_bands.at(loaded, 10) == (0.0, 0.0, 0.0, 0.0)
    assert music_bands.load(pathlib.Path(d) / "none.wav") is None

# The crossfade is equal power: never both loud, never a gap.
for p in (0.0, 0.25, 0.5, 0.75, 1.0):
    track, theme = trip.crossfade(p)
    assert abs(track ** 2 + theme ** 2 - 1) < 1e-9
assert trip.crossfade(0) == (0.0, 1.0) and trip.crossfade(1)[0] == 1.0

# Driving a fake game: one trip at a time, the track fades in, everything comes back at the end.
playing = {"on": True}
calls = []
music = types.SimpleNamespace(play_track=lambda p: calls.append(("play", p)) or True,
                              track_playing=lambda: playing["on"],
                              mix=lambda t, m: calls.append(("mix", round(t, 3), round(m, 3))),
                              stop_track=lambda: calls.append(("stop",)))
said, blocked, refused = [], [], {"n": 0}


def take_refused():
    count, refused["n"] = refused["n"], 0
    return count


speaking = {"on": False}
dialog = types.SimpleNamespace(narrate=lambda text, ms, wav: said.append(text) or True,
                               block=lambda on: None, trip_talk=lambda on: blocked.append(on),
                               take_refused=take_refused,
                               narrating=lambda: speaking["on"])
fake = types.SimpleNamespace(music=music, world=types.SimpleNamespace(generation=1), dialog=dialog,
                             trip=types.SimpleNamespace(set=lambda *a: calls.append(("set", a)),
                                                        clear=lambda: calls.append(("clear",))))
assert trip.start("mindcap", "t.wav", seconds=20) and not trip.start("mindcap")   # never two at once
current, now = trip._current, 0.0
while current.tick(fake, now):
    now += 0.05
mixes = [c for c in calls if c[0] == "mix"]
assert ("play", "t.wav") in calls and mixes[0] == ("mix", 0.0, 1.0)
assert max(m[1] for m in mixes) == 1.0 and mixes[-1][1] < 0.1                     # in, then out again
assert 20 <= now <= 20 + trip.FADE_OUT + 1
trip._end(fake)
assert calls[-2:] == [("stop",), ("clear",)] and not trip.running()                 # music back first, then the screen

# The track ending gives the music back at once, while the visuals keep landing on their own.
calls.clear()
trip.start("wasserpfeife", "w.wav")
current, now = trip._current, 0.0
while now < 194:
    current.tick(fake, now)
    now += 0.05
playing["on"] = False                                    # the song is over
landing = []
while current.tick(fake, now):
    landing.append(current.envelope.intensity)
    now += 0.05
assert current.music_end is not None and 194 <= current.music_end < 194.1
assert landing[0] > 0.5 and now >= 220                   # it was still high when the music stopped, then landed
trip._end(fake)

# Stopping early eases down within a few seconds.
playing["on"] = True
trip.start("mindcap", "t.wav")
current, now = trip._current, 0.0
while now < 200:
    current.tick(fake, now)
    now += 0.05
assert current.envelope.intensity > 0.5
current.stop(now)                                        # what trip.stop() does, on this test's clock
while current.tick(fake, now):
    now += 0.05
assert now - 200 <= trip.STOP_SECONDS + trip.FADE_OUT + 0.2
trip._end(fake)

# Stopping during the fade-in fades back from where it stood: no jump to the track at full volume.
calls.clear()
playing["on"] = True
trip.start("mindcap", "t.wav")
current = trip._current
for i in range(21):                                       # one second into the four-second fade-in
    current.tick(fake, i * 0.05)
before = [c for c in calls if c[0] == "mix"][-1]
current.stop(1.0)
current.tick(fake, 1.05)
after = [c for c in calls if c[0] == "mix"][-1]
assert before[1] < 0.5 and after[1] <= before[1] + 0.01, (before, after)
trip._end(fake)

# Cleanup gives the music back even when there is no world to clear the screen in.
calls.clear()
trip.start("mindcap", "t.wav")
def no_world():
    raise RuntimeError("no world")
fake.trip.clear = no_world
trip._end(fake)
assert ("stop",) in calls
fake.trip.clear = lambda: calls.append(("clear",))

# Thoughts: each said once on the way up, one on landing, in order; conversations blocked while strong, then free.
said.clear(); blocked.clear()
trip.start("kriegsgesang", None)
current, now = trip._current, 0.0
while current.tick(fake, now):
    now += 0.05
assert 2 <= len(said) <= len(trip.THOUGHT_POOLS) + 1, said                  # stages it leaps past are skipped
stage_of = {line: i for i, (_, pool) in enumerate(trip.THOUGHT_POOLS) for line in pool}
ups = [stage_of[line] for line in said[:-1]]
assert ups == sorted(ups) and len(set(ups)) == len(ups)                     # rising, each stage at most once
assert said[-1] in trip.LANDINGS
# The scorpion draws from the desert's pools, not the general ones.
desert = trip.Trip(trip.PROFILES["skorpion"], None, style="ember_glow")
assert all(line in pool for (_, line), (_, pool) in zip(desert.thoughts, trip.DESERT_POOLS))
assert desert.landing in trip.DESERT_LANDINGS
assert set(trip.thought_lines()) >= {l for _, p in trip.DESERT_POOLS for l in p} | set(trip.DESERT_LANDINGS)
assert True in blocked and blocked[-1] is False
trip._end(fake)
assert blocked[-1] is False

# Trying to talk while strong: refused by the engine, and the hero says why, not more often than every few seconds.
said.clear()
trip.start("kriegsgesang", None)
current, now = trip._current, 0.0
while current.envelope.intensity < 0.6:
    current.tick(fake, now)
    now += 0.05
said.clear()
for _ in range(3):
    refused["n"] = 1
    current.tick(fake, now)
    now += 0.05
assert len([s for s in said if s in trip.REFUSALS]) == 1
trip._end(fake)

# Two trips draw differently: over twenty trips, more than one line turns up for every stage.
import random  # noqa: E402
rng = random.Random(7)
drawn = [trip.draw_thoughts(rng) for _ in range(20)]
for stage in range(len(trip.THOUGHT_POOLS)):
    assert len({d[stage][1] for d in drawn}) > 1
# Refusals are random but never the same twice in a row.
refusals = []
trip.start("kriegsgesang", None)
current, now = trip._current, 0.0
while current.envelope.intensity < 0.6:
    current.tick(fake, now)
    now += 0.05
for _ in range(12):
    said.clear()
    refused["n"] = 1
    now += trip.REFUSAL_PAUSE
    current.tick(fake, now)
    refusals += [s for s in said if s in trip.REFUSALS]
assert len(refusals) >= 10 and all(a != b for a, b in zip(refusals, refusals[1:])) and len(set(refusals)) > 2
trip._end(fake)

# The heatstroke: a leap through three stages at once says only the highest, never three lines back to back.
said.clear()
leap = trip.Trip([(5.0, 0.1, 0.05, 0, 0), (5.0, 0.9, 0.5, 0, 0), (60.0, 0.9, 0.05, 0, 0)], None,
                 thoughts=[(0.25, "eins"), (0.5, "zwei"), (0.75, "drei"), (0.95, "vier")])
now = 0.0
while now < 20:
    leap.tick(fake, now)
    now += 0.05
assert said in (["drei"], ["eins", "drei"]), said    # at most the first crossing and then the highest, never the middle
# Between two thoughts there is always a breath of quiet.
said.clear()
times = []
paced = trip.Trip([(60.0, 1.0, 0.002, 0, 0)], None, thoughts=[(0.2, "a"), (0.4, "b"), (0.6, "c"), (0.8, "d")])
dialog.narrate = lambda text, ms, wav: said.append(text) or times.append(now) or True
now = 0.0
while now < 60:
    paced.tick(fake, now)
    now += 0.05
assert all(b - a >= trip.THOUGHT_GAP for a, b in zip(times, times[1:])), times
dialog.narrate = lambda text, ms, wav: said.append(text) or True

# A story's own thoughts replace the defaults.
said.clear()
trip.start("kriegsgesang", None, thoughts=[(0.2, "Bodo?"), (0.6, "Bodo hat Flügel.")])
current, now = trip._current, 0.0
while current.tick(fake, now):
    now += 0.05
assert said[:2] == ["Bodo?", "Bodo hat Flügel."] and not set(said) & {l for _, p in trip.THOUGHT_POOLS for l in p}
trip._end(fake)

# Visuals off: the music and the thoughts stay, the screen does not change.
calls.clear(); said.clear()
real_visuals_on = trip.visuals_on
trip.visuals_on = lambda: False                  # the switch is read while the trip runs, not only at its start
trip.start("kriegsgesang", "k.wav")
current, now = trip._current, 0.0
while now < 150:
    current.tick(fake, now)
    now += 0.05
sets = [c[1] for c in calls if c[0] == "set"]
assert all(s[5] == 0.0 and s[2][3] == 0.0 and s[9] == 0.0 for s in sets)        # no shader, no tint, no zoom
assert ("play", "k.wav") in calls and said
trip._end(fake)
# Switched off in the middle of a trip: the picture is sober within a second.
trip.visuals_on = lambda: True
calls.clear()
trip.start("kriegsgesang", "k.wav")
current, now = trip._current, 0.0
while now < 120:
    current.tick(fake, now)
    now += 0.05
assert [c[1] for c in calls if c[0] == "set"][-1][5] > 0.5     # strong
trip.visuals_on = lambda: False
end = now + 1.1
while now < end:
    current.tick(fake, now)
    now += 0.05
assert [c[1] for c in calls if c[0] == "set"][-1][5] == 0.0    # sober
trip._end(fake)
trip.visuals_on = real_visuals_on

# While a thought is spoken, the trip's music ducks, then comes back.
calls.clear()
trip.start("kriegsgesang", "k.wav")
current, now = trip._current, 0.0
while now < 10:
    current.tick(fake, now)
    now += 0.05
loud = [c for c in calls if c[0] == "mix"][-1][1]
speaking["on"] = True
for _ in range(20):
    current.tick(fake, now)
    now += 0.05
ducked = [c for c in calls if c[0] == "mix"][-1][1]
speaking["on"] = False
for _ in range(60):
    current.tick(fake, now)
    now += 0.05
back = [c for c in calls if c[0] == "mix"][-1][1]
assert abs(ducked - loud * trip.DUCK) < 0.05 and back > 0.95 * loud, (loud, ducked, back)
trip._end(fake)

# A blackout: to black at the landing, moved and laid in a bed (quietly) in the dark, the next morning, back from
# black, and a sober line on waking.
moves, times, uses = [], [], []
fake.player = types.SimpleNamespace(set_position=lambda *p: moves.append(p),
                                    use_object=lambda scheme, state, quiet=False: uses.append((scheme, state, quiet))
                                    or len(uses) >= 2)
fake.world.set_time = lambda h, m: times.append((h, m))
said.clear()
talking = {"open": True}                                        # mid-conversation when it goes black
dialog.is_open = lambda: talking["open"]
dialog.close = lambda: talking.update(open=False)
blackout = {"bed": (1.0, 2.0, 3.0), "scheme": "BEDHIGH", "hour": 9, "wake": ["Wo bin ich?"]}
out = trip.Trip([(5.0, 1.0, 0.2, 0, 0), (5.0, 0.0, 0.01, 0, 0)], None, thoughts=[(0.5, "heiß")], blackout=blackout)
tints, now = [], 0.0
while out.tick(fake, now):
    tints.append([c for c in calls if c[0] == "set"][-1][1][2][3] if any(c[0] == "set" for c in calls) else 0)
    now += 0.05
    assert now < 60, "the blackout never ended"
sets = [c[1] for c in calls if c[0] == "set"]
assert moves == [(1.0, 2.0, 3.0)] and times == [(9, 0)]
assert uses[-1] == ("BEDHIGH", 1, True)                         # quietly: no sleep menu
assert said[-1] == "Wo bin ich?" and "heiß" in said
assert not talking["open"]                                      # the conversation ended with the blackout

# After waking, the house speaks up as he passes: each line once, in order, only near its speaker.
said.clear()
people = {"VLK_435_NADJA": types.SimpleNamespace(position=(0.0, 0.0, 0.0)),
          "VLK_433_BROMOR": types.SimpleNamespace(position=(2000.0, 0.0, 0.0)),
          "VLK_434_BORKA": types.SimpleNamespace(position=(4000.0, 0.0, 0.0))}
fake.world.find_npc = lambda name: people.get(name)
dialog.partner = lambda: None
pitched = {"DIA_BORKA_TROUBLE"}
fake.player = types.SimpleNamespace(position=(5000.0, 0.0, 0.0), heard=lambda info: info in pitched)
trip.remember_after(fake, trip.BLACKOUTS["skorpion_goa"]["after"], 0.0)
def walk(at, now):
    fake.player.position = at
    trip.tick_after(fake, now)
walk((5000.0, 0.0, 0.0), 1.0)
assert said == []                                               # far from everyone: nothing
walk((1990.0, 0.0, 0.0), 2.0)
assert len(said) == 1 and said[0].startswith("Eigentlich")      # Bromor first, if he is passed first
walk((1990.0, 0.0, 0.0), 2.5)
assert len(said) == 1                                           # each once
walk((100.0, 0.0, 0.0), 3.0)
assert len(said) == 2 and said[1].startswith("Komm vorbei")
walk((4000.0, 0.0, 0.0), 4.0)
assert len(said) == 3 and said[2].startswith("Mein Auftrag")    # Borka at the door
walk((4000.0, 0.0, 0.0), 5.0)
assert trip._after is None                                      # all said: forgotten
trip.remember_after(fake, trip.BLACKOUTS["skorpion_goa"]["after"], 0.0)
walk((100.0, 0.0, 0.0), trip.AFTER_FOR + 1)
assert len(said) == 3 and trip._after is None                   # too late: forgotten
pitched.clear()                                                 # never pitched to: his farewell takes his pitch's place
binds = []
dialog.bind = lambda npc: binds.append(("bind", npc))
dialog.unbind = lambda npc=None: binds.append(("unbind", npc))
trip.remember_after(fake, trip.BLACKOUTS["skorpion_goa"]["after"], 0.0)
walk((4000.0, 0.0, 0.0), 1.0)
assert len(said) == 3 and binds == [("bind", people["VLK_434_BORKA"])]  # his conversation is ours, not narrated
walk((4000.0, 0.0, 0.0), 1.5)
assert len(binds) == 1                                          # bound once
assert trip.special_for(types.SimpleNamespace(instance="VLK_433_BROMOR")) is None
sys.modules.setdefault("gothic", types.ModuleType("gothic")).player = fake.player   # the game's own module
fake.player.mark_heard = lambda info: pitched.add(info)
g = trip.special_for(types.SimpleNamespace(instance="VLK_434_BORKA", voice=11))
assert {"DIA_BORKA_TROUBLE", "DIA_BORKA_SECOND_CHANCE", "DIA_BORKA_PISSOFF"} <= pitched   # heard at once: no pitch as it closes
assert g["voice"] == "11" and g["nodes"]["a"]["line"].startswith("Mein Auftrag")
assert g["nodes"]["a"]["choices"] == [{"text": "Schon gut, ich geh ja schon.", "ends": True}]
sys.modules.setdefault("gothic", types.ModuleType("gothic"))
from dm import graph as _graph  # noqa: E402
assert _graph.validate(g) is None
dialog.partner = lambda: people["VLK_434_BORKA"]                # still talking to him
walk((4000.0, 0.0, 0.0), 1.8)
assert binds[-1][0] == "bind"                                   # not let go mid-conversation
dialog.partner = lambda: None
walk((4000.0, 0.0, 0.0), 2.0)
assert binds[-1] == ("unbind", people["VLK_434_BORKA"])         # his own conversations back afterwards
pitched.clear()
assert trip.special_for(types.SimpleNamespace(instance="VLK_434_BORKA", voice=11)) is None   # once
trip.remember_after(fake, trip.BLACKOUTS["skorpion_goa"]["after"], 0.0)
walk((4000.0, 0.0, 0.0), 1.0)
walk((4000.0, 0.0, 0.0), trip.AFTER_FOR + 1)
assert binds[-1] == ("unbind", people["VLK_434_BORKA"]) and trip._after is None   # too late: released too
assert ("15", "Schon gut, ich geh ja schon.") in trip.after_lines()
assert trip.BLACKOUTS["skorpion_goa"]["after"][2].get("bound") is None   # the shared config is never touched
del people["VLK_434_BORKA"]                                     # someone gone from the world is dropped
trip.remember_after(fake, trip.BLACKOUTS["skorpion_goa"]["after"], 0.0)
walk((9000.0, 0.0, 0.0), 1.0)
assert [line["npc"] for line in trip._after[0]] == ["VLK_435_NADJA", "VLK_433_BROMOR"]
assert ("16", trip.BLACKOUTS["skorpion_goa"]["after"][0]["line"]) in trip.after_lines()
assert max(s[2][3] for s in sets) == 1.0 and sets[-1][2][3] == 0.0  # fully black, then clear again
dark = [s for s in sets if s[2] == (0.0, 0.0, 0.0, 1.0)]
assert dark and all(s[5] == 0.0 for s in dark)                  # sober while black
fake.player = None

# The special trip dialogue: anyone but a guard who talks to the hero while the trip is strong gets it, in their own
# voice; the hero's answers are distorted, three of them, different each time.
import random as _random  # noqa: E402
g = trip.special_graph(5, _random.Random(3))
assert g["voice"] == "05" and g["nodes"]["a"]["line"] in trip.SPECIAL_OPENERS
answers = g["nodes"]["a"]["choices"]
assert len(answers) == 3 and len({c["text"] for c in answers}) == 3
assert all(c["delivery"] == trip.DELIVERY and c["text"] in trip.SPECIAL_ANSWERS for c in answers)
for seed in range(30):                                          # the north never babbles of the desert, nor back
    north = {c["text"] for c in trip.special_graph(5, _random.Random(seed), profile="kriegsgesang")["nodes"]["a"]["choices"]}
    desert = {c["text"] for c in trip.special_graph(5, _random.Random(seed), profile="skorpion_goa")["nodes"]["a"]["choices"]}
    assert north <= set(trip.SPECIAL_ANSWERS + trip.NORTH_ANSWERS)
    assert desert <= set(trip.SPECIAL_ANSWERS + trip.DESERT_ANSWERS)
assert all(c["repeat"] for c in answers)                        # the same person can be babbled at on every trip
assert g["nodes"]["z"]["line"] in trip.SPECIAL_CLOSERS and g["nodes"]["z"]["choices"][0]["ends"]
sys.modules.setdefault("gothic", types.ModuleType("gothic"))   # validating a graph never touches the game
from dm import graph as _graph  # noqa: E402
assert _graph.validate(g) is None
assert set(trip.SPECIAL_ANSWERS + trip.NORTH_ANSWERS + trip.DESERT_ANSWERS) <= set(trip.thought_lines())       # voiced and distorted with the thoughts
npc = types.SimpleNamespace(voice=7)
assert trip.special_for(npc) is None                                  # no trip, no special dialogue
trip.start("kriegsgesang", None)
trip._current.envelope.intensity = 0.8
assert trip.special_for(npc)["voice"] == "07"
abuyin = types.SimpleNamespace(voice=13, instance="VLK_456_ABUYIN")   # the pipe master knew this would happen
g = trip.special_for(abuyin)
assert g["voice"] == "13" and g["nodes"]["a"]["line"] in trip.SPECIAL_PEOPLE["VLK_456_ABUYIN"]["openers"]
g = trip.special_graph(4, _random.Random(1), "MIL_319_PABLO", guard=True)  # a guard in his own tone
assert g["nodes"]["a"]["line"] in trip.SPECIAL_GUARDS["openers"] and g["nodes"]["z"]["line"] in trip.SPECIAL_GUARDS["closers"]
_gothic = sys.modules["gothic"]
_gothic.daedalus = types.SimpleNamespace(get=lambda name, index=0: {"GIL_PAL": 1, "GIL_MIL": 2}[name])  # as the game's
pablo = types.SimpleNamespace(voice=4, instance="MIL_319_PABLO", guild=2)
assert trip.special_for(pablo)["nodes"]["a"]["line"] in trip.SPECIAL_GUARDS["openers"]
assert not trip.is_guard(types.SimpleNamespace(voice=4, guild=3))
trip._current.envelope.intensity = 0.2
assert trip.special_for(npc) is None                                  # not while the trip is still mild
trip._end(fake)

# A loaded save ends the trip at once.
trip.start("mindcap", None, seconds=20)
trip._current.tick(fake, 0.0)
fake.world.generation = 2
assert trip._current.tick(fake, 0.1) is False
trip._end(fake)

# The water pipe's profile lasts the track plus its landing.
assert trip.length("wasserpfeife") == 225
assert trip.length("nordmar") == 215          # the 185 s track plus its landing
assert trip.length("kriegsgesang") == 200     # the 170 s track plus its landing
assert trip.length("skorpion") == 215 and trip.length("skorpion_goa") == 265

# The scorpion blend looks like heat, not neon: Emberheart's look, desert colours, edges and tracers low.
ember, neon = trip.look(1.0, 3.0, style="ember"), trip.look(1.0, 3.0)
assert ember["look"] == 1 and neon["look"] == 0 and ember["edges"] < neon["edges"] and ember["tracers"] < neon["tracers"]
for h in (0.0, 0.25, 0.5, 0.75):
    r, g, b = trip._hue(h, trip.DESERT)
    assert r >= g >= b                                       # warm: never blue, never pink
assert trip.PROFILE_LOOK["skorpion"] == "ember_glow" and trip.PROFILE_LOOK["skorpion_goa"] == "ember_eye"
assert "kriegsgesang" not in trip.PROFILE_LOOK
# The second stage opens only once the heat has hit, and only the one the track asks for.
assert trip.look(0.5, 1.0, style="ember_eye")["eye"] == 0.0
assert trip.look(1.0, 1.0, style="ember_eye")["eye"] == 1.0 and trip.look(1.0, 1.0, style="ember_eye")["afterglow"] == 0.0
assert trip.look(1.0, 1.0, style="ember_glow")["afterglow"] == 1.0 and trip.look(1.0, 1.0)["eye"] == 0.0
assert trip.look(1.0, 1.0, style="ember_glow")["tracers"] == 0.0     # its glow lives where the tracers would
assert 0 < trip.look(0.7, 1.0, style="ember_eye")["eye"] < 1
# The Goa scorpion's eye waits for the peak phase: closed through the heatstroke, open once the peak climbs.
goa = trip.Trip(trip.PROFILES["skorpion_goa"], None, style="ember_eye")
eyes, now = [], 0.0
calls.clear()
while now < 200:
    goa.tick(fake, now)
    eyes.append((now, [c for c in calls if c[0] == "set"][-1][1][11]))
    now += 0.25
peak_start = sum(d for d, *_ in trip.PROFILES["skorpion_goa"][:goa.peak_phase])
assert all(e == 0.0 for t_, e in eyes if t_ < peak_start - 0.5)       # nothing through the heatstroke at 60 s
assert all(e > 0.99 for t_, e in eyes if t_ > peak_start + trip.PEAK_OPEN + 0.5)
# It hits like heatstroke at the first big rise of its track.
env = trip.Envelope(trip.PROFILES["skorpion"])
for _ in range(int(25 * 60)):
    env.step()
assert env.intensity > 0.75
print("trip ok")
