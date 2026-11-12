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
fake.world.has_waypoint = lambda wp: True
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
trip._after = None
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
trip._after = None
trip.remember_after(fake, trip.BLACKOUTS["skorpion_goa"]["after"], 0.0)
walk((100.0, 0.0, 0.0), trip.AFTER_FOR + 1)
assert len(said) == 3 and trip._after is None                   # too late: forgotten
pitched.clear()                                                 # never pitched to: his farewell takes his pitch's place
binds = []
dialog.bind = lambda npc: binds.append(("bind", npc))
dialog.unbind = lambda npc=None: binds.append(("unbind", npc))
trip._after = None
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
trip._after = None
trip.remember_after(fake, trip.BLACKOUTS["skorpion_goa"]["after"], 0.0)
walk((4000.0, 0.0, 0.0), 1.0)
walk((4000.0, 0.0, 0.0), trip.AFTER_FOR + 1)
assert binds[-1] == ("unbind", people["VLK_434_BORKA"]) and trip._after is None   # too late: released too
assert ("15", "Schon gut, ich geh ja schon.") in trip.after_lines()
assert trip.BLACKOUTS["skorpion_goa"]["after"][2].get("bound") is None   # the shared config is never touched
del people["VLK_434_BORKA"]                                     # someone gone from the world is dropped
trip._after = None
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
drinker = types.SimpleNamespace(voice=6, instance="VLK_4_X", guild=3, in_state=lambda st: st == "ZS_STAND_DRINKING")
g = trip.special_for(drinker)                                   # at the barrel: advice on mixing
assert g["nodes"]["a"]["line"] in trip.SPECIAL_DRINKERS["openers"] and g["nodes"]["z"]["line"] in trip.SPECIAL_DRINKERS["closers"]
sober_one = types.SimpleNamespace(voice=6, instance="VLK_4_X", guild=3, in_state=lambda st: False)
assert trip.special_for(sober_one)["nodes"]["a"]["line"] in trip.SPECIAL_OPENERS
pablo = types.SimpleNamespace(voice=4, instance="MIL_319_PABLO", guild=2)
assert trip.special_for(pablo)["nodes"]["a"]["line"] in trip.SPECIAL_GUARDS["openers"]
assert not trip.is_guard(types.SimpleNamespace(voice=4, guild=3))
trip._current.envelope.intensity = 0.2
assert trip.special_for(npc) is not None    # a story's own conversation is the trip's from the first draw (only a
                                            # story's asks while mild: the engine hands others over only when strong)
trip._current.envelope.over = True
assert trip.special_for(npc) is None                                  # landed: everyone talks normally again
trip._current.envelope.over = False
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
assert trip.length("skorpion") == 215 and trip.length("skorpion_goa") == 210

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

# The Invocation: its own look (2), the moonlit tint, the vision opens at the peak like the eye, its own thoughts.
fx = trip.look(0.8, 10.0, style="invocation", opened=0.5)
assert fx["look"] == 2 and fx["eye"] == 0.5 and fx["afterglow"] == 0.0
assert trip.PROFILE_LOOK["anrufung"] == "invocation" and trip.LOOKS["invocation"]["at_peak"]
inv = trip.Trip(trip.PROFILES["anrufung"], None, style="invocation", rng=_random.Random(2))
assert all(text in [t for _, pool in trip.SLEEPER_POOLS for t in pool] for _, text in inv.thoughts)
assert set(trip.SLEEPER_ANSWERS) <= set(trip.thought_lines())

# Its blackout has no bed: he wakes on his feet at a waypoint, and Vatras's first conversation is his line.
moves, times, said_before = [], [], len(said)
fake.player = types.SimpleNamespace(set_position=lambda *p: moves.append(p), position=(0.0, 0.0, 0.0),
                                    use_object=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no bed")),
                                    heard=lambda info: False)
fake.world.set_time = lambda h, m: times.append((h, m))
fake.world.waypoint_position = lambda wp: {"NW_CITY_MERCHANT_TEMPLE_IN": (10.0, 20.0, 30.0)}[wp]
dialog.is_open = lambda: False
dialog.partner = lambda: None
binds.clear()
vatras = types.SimpleNamespace(position=(0.0, 0.0, 9000.0), instance="VLK_439_VATRAS", voice=5)
people.clear()
people["VLK_439_VATRAS"] = vatras
night = trip.Trip([(3.0, 1.0, 0.2, 0, 0), (3.0, 0.0, 0.01, 0, 0)], None, style="invocation",
                  blackout=trip.BLACKOUTS["anrufung"])
now = 0.0
while night.tick(fake, now):
    now += 0.05
    assert now < 60, "the blackout never ended"
assert moves == [(10.0, 20.0, 30.0)] and times == [(6, 0)]
assert said[-1] in trip.BLACKOUTS["anrufung"]["wake"]
trip._after = None                                               # a fresh morning: nothing else waiting
trip.remember_after(fake, trip.BLACKOUTS["anrufung"]["after"], now)
trip._current = None
trip.tick_after(fake, now + 0.1)
assert binds == [("bind", vatras)]                              # far away, yet his conversation is already the line
g = trip.special_for(vatras)
assert g["voice"] == "05" and g["nodes"]["a"]["line"].startswith("Was auch immer")
assert g["nodes"]["a"]["choices"][0]["text"] == "Ich … hab nur was geraucht."
trip.tick_after(fake, now + 0.2)
assert binds[-1] == ("unbind", vatras)                          # his own conversations back
trip.tick_after(fake, now + 0.3)
assert [bool(line.get("sermon")) for line in trip._after[0]] == [True]   # only the sermon still waits
assert ("05", trip.BLACKOUTS["anrufung"]["after"][0]["line"]) in trip.after_lines()

# The morning sermon: begun once he is near, his own preaching hushed meanwhile, preached to the end even if the
# hero walks off, one sentence at a time with a pause, then his routine is his own again.
sermon = trip.BLACKOUTS["anrufung"]["after"][1]["sermon"]
hushed, routines = [], []
vatras.in_state = lambda state: state == "ZS_PREACH_VATRAS"
vatras.stand_here = lambda: hushed.append("stand")
fake.daedalus = types.SimpleNamespace(call=lambda name, npc, routine: routines.append((name, npc, routine)))
said.clear()
trip._after = None
trip.remember_after(fake, [trip.BLACKOUTS["anrufung"]["after"][1]], 0.0)
fake.player.position = (0.0, 0.0, 0.0)                          # 90 m away
trip.tick_after(fake, 1.0)
assert said == [] and hushed == []
fake.player.position = (0.0, 0.0, 8000.0)                       # 10 m: he begins
trip.tick_after(fake, 2.0)
assert said == [sermon[0]] and hushed == ["stand"]              # his own sermon on hold
fake.player.position = (0.0, 0.0, 0.0)                          # walking off does not stop a sermon begun
trip.tick_after(fake, 2.5)
assert said == [sermon[0]] and hushed == ["stand"] and not routines   # a pause; still on hold
t = 3.0
while trip._after is not None and t < 400:
    trip.tick_after(fake, t)
    t += 0.5
assert said == sermon                                           # all of it, in order, once
assert routines == [("B_STARTOTHERROUTINE", vatras, "START")] and hushed == ["stand"]   # his own routine back
# In another routine (not preaching) there is nothing to hush and nothing to give back.
vatras.in_state = lambda state: False
hushed.clear(); routines.clear(); said.clear()
trip._after = None
trip.remember_after(fake, [trip.BLACKOUTS["anrufung"]["after"][1]], 0.0)
fake.player.position = (0.0, 0.0, 8000.0)
t = 1.0
while trip._after is not None and t < 400:
    trip.tick_after(fake, t)
    t += 0.5
assert said == sermon and hushed == [] and routines == []
# Forgotten mid-sermon (too late), he still gets his routine back.
vatras.in_state = lambda state: state == "ZS_PREACH_VATRAS"
said.clear()
trip._after = None
trip.remember_after(fake, [trip.BLACKOUTS["anrufung"]["after"][1]], 0.0)
trip.tick_after(fake, 1.0)
trip.tick_after(fake, trip.AFTER_FOR + 1)
assert routines == [("B_STARTOTHERROUTINE", vatras, "START")] and trip._after is None
assert all(("05", text) in trip.after_lines() for text in sermon)

# In another world (no temple there) he comes to where he fell: no move, no morning, nobody waiting.
moves.clear(); times.clear(); binds.clear()
fake.world.has_waypoint = lambda wp: False
fake.player.use_object = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no bed elsewhere"))
elsewhere = trip.Trip([(3.0, 1.0, 0.2, 0, 0), (3.0, 0.0, 0.01, 0, 0)], None, style="invocation",
                      blackout=trip.BLACKOUTS["anrufung"])
now = 0.0
while elsewhere.tick(fake, now):
    now += 0.05
    assert now < 60, "the blackout never ended"
assert moves == [] and times == [] and trip._after is None and said[-1] in trip.BLACKOUTS["anrufung"]["wake"]
fake.world.has_waypoint = lambda wp: True
fake.player = None
print("invocation ok")

# The galaxy: each trip its own, opening with the trip's strength; images loaded once; the game's sky without them.
import pathlib as _pl, tempfile as _tf  # noqa: E402
loads, shown = [], []
skyfake = types.SimpleNamespace(load=lambda slot, path: loads.append((slot, _pl.Path(path).name)) or True,
                                galaxy=lambda *a: shown.append(a), clear=lambda: shown.append("clear"))
g = types.SimpleNamespace(sky=skyfake)
trip._sky_loaded.clear()
trip.SKY_DIR = _pl.Path(_tf.mkdtemp())
for name in ("milkyway.jpg", "cosmic_cliffs.jpg", "pillars.jpg"):
    (trip.SKY_DIR / name).write_bytes(b"")
assert trip.sky_amount(0.0) == 0.0 and trip.sky_amount(1.0) == 1.0 and 0 < trip.sky_amount(0.45) < 1
trip.set_sky(g, "hot", 1.0, 10.0, glow=0.3)
amount, gain, tint, grade, spin, glow, spots, aurora, secs, moon = shown[-1]
assert amount == 1.0 and tint == trip.GALAXIES["hot"]["tint"] and spin == 10.0 * trip.SKY_SPIN and glow == 0.3
assert loads == [(0, "milkyway.jpg"), (1, "pillars.jpg"), (2, "cosmic_cliffs.jpg")] and all(s[3] > 0 for s in spots)
assert aurora == 0.0 and secs == 10.0 and moon == 0.0
trip.set_sky(g, "hot", 0.5, 11.0)
assert len(loads) == 3                                          # loaded once
trip.set_sky(g, "ice", 1.0, 11.5)                               # Nordmar: northern lights, no nebulae
assert shown[-1][7] == 1.0 and shown[-1][6] == [] and shown[-1][9] == 0.0   # no moon before the peak
trip.set_sky(g, "ice", 1.0, 12.0, peak=1.0)
assert shown[-1][9] == 1.0                                      # the blood moon at the peak of the war chant
trip.set_sky(g, "hot", 1.0, 12.0, peak=1.0)
assert shown[-1][9] == 0.0                                      # only Nordmar's
trip.set_sky(g, "sleeper", 1.0, 12.0)                           # Stephan's Quintet is missing here: that nebula off
assert shown[-1][6][0][3] == 0.0 and shown[-1][6][1][3] > 0
trip.set_sky(g, None, 1.0, 13.0)
assert shown[-1] == "clear"                                     # a trip without a galaxy keeps the game's sky
(trip.SKY_DIR / "milkyway.jpg").unlink()
trip._sky_loaded.clear()
trip.set_sky(g, "hot", 1.0, 14.0)
assert shown[-1] == "clear"                                     # no panorama: the game's sky
trip.set_sky(types.SimpleNamespace(), "hot", 1.0, 15.0)         # an engine without a sky: nothing happens
assert set(trip.PROFILE_GALAXY.values()) <= set(trip.GALAXIES)
print("galaxy ok")

# Aftercare: after a trip, Abuyin has a topic of his own about it, region by region; taken once, gone after a load.
trip._aftercare = None
w = types.SimpleNamespace(world=types.SimpleNamespace(generation=5))
assert trip.extra_topics(w) == {trip.AFTERCARE_NPC: []}         # listed empty: a topic talked about disappears
trip._aftercare = ("north", 5)
assert trip.extra_topics(w) == {trip.AFTERCARE_NPC: [(trip.AFTERCARE_TOPIC, trip.AFTERCARE_TITLE)]}
w.world.generation = 6
assert trip.extra_topics(w)[trip.AFTERCARE_NPC] == []           # another save: not this trip's
w.world.generation = 5
care = trip.topic(trip.AFTERCARE_TOPIC)
assert care["title"] == trip.AFTERCARE_TITLE and _graph.validate(care["graph"]) is None
nodes = care["graph"]["nodes"]
assert nodes["b"]["line"] == trip.AFTERCARE["north"]["ask"] and "Blut" in nodes["c"]["choices"][0]["text"]
assert nodes["d"]["choices"][0]["ends"] and care["graph"]["voice"] == "13"
assert trip.topic(trip.AFTERCARE_TOPIC) is None and trip.extra_topics(w)[trip.AFTERCARE_NPC] == []   # once
assert trip.topic("trip:other") is None
for region in trip.AFTERCARE:
    assert _graph.validate(trip.aftercare_graph(region)) is None
assert set(trip.PROFILE_REGION.values()) <= set(trip.AFTERCARE)
assert (trip.HERO_VOICE, trip.AFTERCARE_TITLE) in trip.after_lines()
print("aftercare ok")

# Aftercare only for a trip that ran its course in this world, not one a load cut off.
sys.modules["gothic"].world = types.SimpleNamespace(generation=7)
sys.modules["gothic"].music = music
sys.modules["gothic"].trip = fake.trip
sys.modules["gothic"].dialog = dialog
trip._aftercare = None
trip._current = types.SimpleNamespace(generation=3, tick=lambda g, now: False, profile="kriegsgesang")
trip._tick(0.0)
assert trip._aftercare is None and trip._current is None        # cut off by a load: nothing to talk about
trip._current = types.SimpleNamespace(generation=7, tick=lambda g, now: False, profile="kriegsgesang")
trip._tick(0.0)
assert trip._aftercare == ("north", 7)                          # ran its course here
print("aftercare load ok")

# No saving during a trip, nor while a preacher's own sermon is on hold.
blocks = []
fake.trip.block_save = lambda on: blocks.append(on)
sys.modules["gothic"].trip = fake.trip
trip._after = None
trip._current = types.SimpleNamespace(generation=7, tick=lambda g, now: True, profile="kriegsgesang")
trip._tick(0.0)
assert blocks[-1] is True
trip._current = None
trip._tick(0.0)
assert blocks[-1] is False
trip._after = [[{"npc": "X", "sermon": ["a"], "hushed": True}], 1e12, 7]
sys.modules["gothic"].world = types.SimpleNamespace(generation=7, find_npc=lambda n: None)
assert trip.saving_blocked()
trip._after = None
assert not trip.saving_blocked()
print("save block ok")

# Escape during a trip: the hero answers it at once, in his trip voice.
said.clear()
esc = {"n": 0}
fake.trip.take_escapes = lambda: esc.update(n=0) or 1 if esc["n"] else 0
calm = trip.Trip([(30.0, 0.5, 0.2, 0, 0)], None, thoughts=[(0.99, "nie")])
calm.tick(fake, 0.0)
esc["n"] = 1
calm.tick(fake, 0.1)
assert said and said[-1] in trip.ESCAPES
assert set(trip.ESCAPES) <= set(trip.thought_lines())
print("escape ok")

# Bjarne speaks as the witness while he is Bjarne; the same citizen elsewhere is a stranger.
import random as _r2  # noqa: E402
g = trip.special_graph(1, _r2.Random(4), "VLK_454_BUERGER", name="Bjarne", profile="kriegsgesang")
assert g["nodes"]["a"]["line"] in trip.SPECIAL_BY_NAME[("VLK_454_BUERGER", "Bjarne")]["openers"]
g = trip.special_graph(1, _r2.Random(4), "VLK_454_BUERGER", name="Bürger")
assert g["nodes"]["a"]["line"] in trip.SPECIAL_OPENERS
# The north brings its snow.
falls = []
sys.modules["dm.weather"] = types.SimpleNamespace(snow=lambda **k: falls.append(k))
import dm as _dm  # noqa: E402
_dm.weather = sys.modules["dm.weather"]
trip._current = None
trip.start("kriegsgesang", None)
assert falls and falls[-1]["rise"] > 0
trip._current = None
trip.start("skorpion_goa", None)
assert len(falls) == 1                                           # the desert does not
trip._current = None
print("bjarne and snow ok")

# The crier: after a trip that ran its course, one announcement of the trip's region, ready after a wait, read in his
# voice as a sermon when the hero passes; a later trip's news replaces one not yet read.
trip._after = None
crier = types.SimpleNamespace(position=(0.0, 0.0, 0.0), in_state=lambda st: False, instance="VLK_406_HEROLD")
gw = types.SimpleNamespace(generation=9, find_npc=lambda n: crier if n == "VLK_406_HEROLD" else None)
sys.modules["gothic"].world = gw
sys.modules["gothic"].player = types.SimpleNamespace(position=(0.0, 0.0, 100.0))
trip._aftercare = None
trip._current = types.SimpleNamespace(generation=9, tick=lambda g, now: False, profile="skorpion_goa")
trip._tick(0.0)
waiting = [l for l in trip._after[0] if l["npc"] == "VLK_406_HEROLD"]
assert len(waiting) == 1 and waiting[0]["sermon"][1] == trip.HEROLD_NEWS["desert"][0]
trip._current = types.SimpleNamespace(generation=9, tick=lambda g, now: False, profile="kriegsgesang")
trip._tick(0.0)
waiting = [l for l in trip._after[0] if l["npc"] == "VLK_406_HEROLD"]
assert len(waiting) == 1 and waiting[0]["sermon"][1] == trip.HEROLD_NEWS["north"][0]   # tonight's news only
said.clear()
g2 = types.SimpleNamespace(world=gw, player=sys.modules["gothic"].player, dialog=dialog, daedalus=types.SimpleNamespace(call=lambda *a: None))
dialog.partner = lambda: None
start = waiting[0]["ready"] - 1
trip.tick_after(g2, start)
assert said == []                                               # not before the wait
t = waiting[0]["ready"]
while trip._after is not None and t < waiting[0]["ready"] + 400:
    trip.tick_after(g2, t)
    t += 0.5
assert said == waiting[0]["sermon"]
assert all((trip.HEROLD["voice"], text) in trip.after_lines() for text in trip.herold_lines("sleeper")["sermon"])
print("crier ok")

# No saving while someone waits on a bench for the pipe the hero was given: a save would keep him there.
trip._current, trip._after = None, None
sys.modules["dm.story"] = types.SimpleNamespace(_story=types.SimpleNamespace(evicted={("SMOKE", 1.0, 2.0): "CANTHAR"}))
assert trip.saving_blocked()
sys.modules["dm.story"]._story.evicted = {}
assert not trip.saving_blocked()
del sys.modules["dm.story"]
print("bench save block ok")

# The three smokes: a piece of the set after each trip's talk with Abuyin (once), Abuyin's ceremony with all three,
# and those who know recognising the amulet when it is worn.
class _FakeStory:
    def __init__(self):
        self.state = {"items": {}, "flags": {}}
    def apply_plan(self, plan):
        for i, op in enumerate(plan["ops"]):
            self.state["items"][op["item"]] = {"carrier": f"CARRIER_{len(self.state['items'])}"}
sys.modules["dm.story"] = types.SimpleNamespace(_story=_FakeStory())
pieces = trip.smoke_set()
assert set(pieces) == {"north", "desert", "sleeper"} and len(set(pieces.values())) == 3
assert trip.smoke_set() == pieces                                   # defined once
inv = []
gw = types.SimpleNamespace(world=types.SimpleNamespace(generation=1, find_npc=lambda n: types.SimpleNamespace(
    name={"VLK_454_BUERGER": "Bjarne", "VLK_455_BUERGER": "Bürger"}.get(n, "x"))), player=types.SimpleNamespace(items=inv))
sys.modules["gothic"].player = gw.player
trip._aftercare = ("north", 1)
g = trip.topic(trip.AFTERCARE_TOPIC)["graph"]
assert g["nodes"]["e"]["choices"][0]["gives"] == {"item": pieces["north"], "count": 1}   # the north's ring
inv.append({"instance": pieces["north"], "equipped": False})
trip._aftercare = ("north", 1)
assert "e" not in trip.topic(trip.AFTERCARE_TOPIC)["graph"]["nodes"]                     # only once
assert _graph.validate(g) is None
assert trip.extra_topics(gw)[trip.AFTERCARE_NPC] == []                                   # one piece: no ceremony yet
inv += [{"instance": pieces["desert"], "equipped": True}, {"instance": pieces["sleeper"], "equipped": False}]
topics = trip.extra_topics(gw)
assert (trip.SMOKE_MASTER_TOPIC, trip.SMOKE_MASTER_TITLE) in topics[trip.AFTERCARE_NPC]
assert topics["VLK_449_LARES"] == []                                                      # amulet not worn
inv[-1]["equipped"] = True
topics = trip.extra_topics(gw)
assert topics["VLK_449_LARES"] == []                                                      # the amulet alone: not yet
inv[0]["equipped"] = True                                                                 # all three worn
topics = trip.extra_topics(gw)
assert topics["VLK_449_LARES"] == [("trip:erkannt:VLK_449_LARES", trip.RECOGNISE_TITLE)]
assert topics["VLK_454_BUERGER"] and topics["VLK_455_BUERGER"] == []                      # Bjarne is; Kasim isn't here
g = trip.topic("trip:erkannt:VLK_449_LARES")["graph"]
assert g["voice"] == "09" and g["nodes"]["s0"]["sets"] == ["trip:erkannt:VLK_449_LARES"] and _graph.validate(g) is None
sys.modules["dm.story"]._story.state["flags"]["trip:erkannt:VLK_449_LARES"] = True
assert trip.extra_topics(gw)["VLK_449_LARES"] == [] and trip.topic("trip:erkannt:VLK_449_LARES") is None   # once
m = trip.topic(trip.SMOKE_MASTER_TOPIC)["graph"]
assert m["nodes"]["s0"]["sets"] == [trip.SMOKE_MASTER_FLAG] and _graph.validate(m) is None
assert (trip.HERO_VOICE, trip.SMOKE_THANKS) in trip.after_lines() and ("04", trip.RECOGNISE[-1][3][0]) in trip.after_lines()
del sys.modules["dm.story"]
trip._aftercare = None
print("three smokes ok")

# The talk Abuyin still owes survives a restart: it is kept in the save's story state.
sys.modules["dm.story"] = types.SimpleNamespace(_story=_FakeStory())
trip._aftercare = None
gw2 = types.SimpleNamespace(world=types.SimpleNamespace(generation=3, find_npc=lambda n: None), player=types.SimpleNamespace(items=[]))
sys.modules["dm.story"]._story.state["aftercare"] = "desert"            # as a loaded save would have it
assert (trip.AFTERCARE_TOPIC, trip.AFTERCARE_TITLE) in trip.extra_topics(gw2)[trip.AFTERCARE_NPC]
assert trip.topic(trip.AFTERCARE_TOPIC)["graph"]["nodes"]["b"]["line"] == trip.AFTERCARE["desert"]["ask"]
assert "aftercare" not in sys.modules["dm.story"]._story.state                 # talked about: gone
del sys.modules["dm.story"]
print("aftercare across restarts ok")

# Passing people while wearing the three smokes: a remark, by name or in a citizen's or guard's own voice, once a day
# each, with a breath between remarks; nothing without the whole set.
sys.modules["dm.story"] = types.SimpleNamespace(_story=_FakeStory())
pieces = trip.smoke_set()
inv = [{"instance": c, "equipped": True} for c in pieces.values()]
said.clear()
near = [types.SimpleNamespace(instance="VLK_456_ABUYIN", voice=13, alive=True),
        types.SimpleNamespace(instance="VLK_4_BUERGER", voice=6, alive=True, guild=3)]
gw3 = types.SimpleNamespace(world=types.SimpleNamespace(generation=1, day=4, npcs_near=lambda r: near,
                                                        find_npc=lambda n: None),
                            player=types.SimpleNamespace(items=inv, position=(0, 0, 0)), dialog=dialog)
dialog.partner = lambda: None
trip._current, trip._remarked, trip._remark_at[0] = None, {}, -1000.0
trip.tick_remarks(gw3, 0.0)
assert said[-1] in trip.REMARKS_BY_NAME["VLK_456_ABUYIN"][1]
trip.tick_remarks(gw3, 5.0)
assert len(said) == 1                                                                     # a breath between
trip.tick_remarks(gw3, 50.0)
assert said[-1] in trip.REMARKS_CITIZEN                                                   # the citizen in his voice
trip.tick_remarks(gw3, 100.0)
assert len(said) == 2                                                                     # each once a day
inv[0]["equipped"] = False
gw3.world.day = 5
trip.tick_remarks(gw3, 200.0)
assert len(said) == 2                                                                     # not the whole set: nothing
assert ("13", trip.REMARKS_BY_NAME["VLK_456_ABUYIN"][1][0]) in trip.after_lines()
del sys.modules["dm.story"]
print("remarks ok")
