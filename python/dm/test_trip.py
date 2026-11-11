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
fake = types.SimpleNamespace(music=music, world=types.SimpleNamespace(generation=1),
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
print("trip ok")
