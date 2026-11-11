"""A trip: an intensity envelope that drives the game's view, colour, time and music for a few minutes.

    from dm import trip
    trip.start("mindcap", "/path/to/track.wav")    # one at a time; a second start is refused while one runs
    trip.stop()                                     # fades back gracefully

The envelope is ported from Solaris's Mindcap: phases with a target intensity, an easing rate and an optional wave,
stepped 60 times a second exactly as Solaris does, so the curve is the same. A profile can be stretched to the length
of its track, so the trip never outlives its music.

The track crossfades with the game's music, equal power over a few seconds each way. When the track ends, the game's
music comes back while the visuals finish landing on their own. Stopping early eases everything down; the game's
music always comes back, also when the world changes.
"""

import math
import random
import sys
import time

STEP = 1.0 / 60.0   # Solaris steps its envelope per frame at 60 fps
FADE_IN = 4.0
FADE_OUT = 6.0
STOP_SECONDS = 4.0

# (seconds, target intensity, easing per step, wave amplitude, wave speed per step), as in Solaris's profiles.rs.
PROFILES = {
    "mindcap": [(15.0, 0.05, 0.008, 0.0, 0.0), (30.0, 0.15, 0.006, 0.0, 0.0), (45.0, 0.45, 0.005, 0.0, 0.0),
                (60.0, 0.80, 0.010, 0.12, 0.03), (90.0, 1.00, 0.004, 0.05, 0.02), (60.0, 0.60, 0.003, 0.0, 0.0),
                (50.0, 0.00, 0.006, 0.0, 0.0)],
    # Cut to "Hoh - ah - oh" (194 s), whose loudness climbs almost to its last seconds: the trip peaks with the
    # song's climax and lands after it, while the game's music comes back.
    "wasserpfeife": [(20.0, 0.10, 0.010, 0.0, 0.0), (40.0, 0.35, 0.006, 0.03, 0.02), (50.0, 0.65, 0.006, 0.08, 0.03),
                     (55.0, 0.90, 0.008, 0.10, 0.04), (27.0, 1.00, 0.020, 0.0, 0.0), (33.0, 0.00, 0.004, 0.0, 0.0)],
    # Cut to "Hau - ra - dah" (185 s, 82 BPM war drums): fire and drone, the drums at 30 s, a leap at 50 s, loud and
    # steady from 70 s with its loudest stretch near the end, then the landing after the music.
    "nordmar": [(30.0, 0.08, 0.010, 0.0, 0.0), (20.0, 0.30, 0.006, 0.02, 0.02), (40.0, 0.65, 0.008, 0.05, 0.02),
                (60.0, 0.85, 0.006, 0.06, 0.02), (32.0, 1.00, 0.015, 0.0, 0.0), (33.0, 0.00, 0.004, 0.0, 0.0)],
    # Cut to "Hu-A-Hra" (170 s, 86 BPM): war drums from the first beat, a gradual climb, a steady middle, the peak near
    # 140 s and a softer last stretch, then the landing after the music.
    "kriegsgesang": [(20.0, 0.10, 0.010, 0.0, 0.0), (30.0, 0.35, 0.006, 0.02, 0.02), (30.0, 0.60, 0.007, 0.04, 0.02),
                     (50.0, 0.85, 0.006, 0.06, 0.02), (30.0, 1.00, 0.015, 0.0, 0.0), (40.0, 0.00, 0.004, 0.0, 0.0)],
}

# The hero's thoughts from off, distorted (delivery "rausch", see trip_voices.py). Each trip draws one line per stage
# at random, so two trips never sound quite alike, and says it once when the trip first reaches that intensity; one
# landing line when it comes down again. A story may give its own thoughts instead, which are then said as written.
THOUGHT_POOLS = [
    (0.25, ["Was ist hier los?", "Irgendwas stimmt hier nicht …", "Hm. Der Boden … der wackelt.",
            "Warum ist alles so … bunt?"]),
    (0.5, ["Die Wände … die atmen.", "Hörst du das? Das Licht summt.", "Meine Hände … die sind so weit weg.",
           "Die Luft schmeckt nach Farben."]),
    (0.75, ["Die Trommeln … die sind in meinem Kopf.", "Alles dreht sich … und ich mit.",
            "Ich glaub, ich kann die Sterne hören.", "Wer hat die Welt so laut gemacht?"]),
    (0.95, ["Die Wände schmelzen …", "Ich bin … riesig. Oder winzig?", "Jetzt seh ich alles. Alles!",
            "Beliar, bist du das?"]),
]
LANDINGS = ["Langsam … langsam kommt alles zurück.", "Uff. Was war das denn?", "Nie wieder. Oder … morgen wieder.",
            "Mein Kopf … wie nach drei Flaschen Wein."]
# Said instead when the hero tries to talk to someone while the trip is too strong for it; never twice in a row.
REFUSALS = ["Nicht jetzt … sein Gesicht zerfließt.", "Mit dem red ich jetzt besser nicht.", "Der hat … drei Augen.",
            "Nee. Der guckt so komisch.", "Später. Wenn er wieder normal aussieht."]
BLOCK_ABOVE = 0.35        # no conversations above this intensity
DUCK = 0.4                # the trip's music while a thought is spoken, so the hero carries over the drums
REFUSAL_PAUSE = 8.0       # seconds between two refusal thoughts
DELIVERY = "rausch"
HERO_VOICE = "15"
SETTINGS = __import__("pathlib").Path(__file__).resolve().parent.parent / "dm_runtime" / "settings.json"


def visuals_on():
    """Whether trips may change the picture. Off keeps the music and the thoughts (photosensitivity)."""
    try:
        return bool(__import__("json").loads(SETTINGS.read_text(encoding="utf-8")).get("trip_visuals", True))
    except (OSError, ValueError):
        return True


def thought_lines(thoughts=None):
    """Every line a trip may say, for voicing: the given thoughts or all the pools, the landings and the refusals."""
    ups = [text for _, text in thoughts] if thoughts else [line for _, pool in THOUGHT_POOLS for line in pool]
    return ups + LANDINGS + REFUSALS


def draw_thoughts(rng):
    """One line per stage, picked at random: this trip's thoughts on the way up."""
    return [(at, rng.choice(pool)) for at, pool in THOUGHT_POOLS]


# A profile's own track, in python/dm_runtime/music (private: never committed).
TRACKS = {"mindcap": "mindcap.wav", "wasserpfeife": "wasserpfeife.wav", "nordmar": "nordmar.wav",
          "kriegsgesang": "kriegsgesang.wav"}
MUSIC_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "dm_runtime" / "music"


def length(profile):
    return sum(phase[0] for phase in PROFILES[profile])


class Envelope:
    """Solaris's ActiveTrip: intensity eased towards each phase's target, one step per frame."""

    def __init__(self, phases):
        self.phases = phases
        self.index = 0
        self.timer = phases[0][0]
        self.frame = 0
        self.intensity = 0.0
        self.over = False

    def step(self):
        if self.over:
            return False
        _, target, ease, wave_amp, wave_speed = self.phases[self.index]
        self.timer -= STEP
        self.frame += 1
        wave = math.sin(self.frame * wave_speed) * wave_amp
        self.intensity += (min(1.0, max(0.0, target + wave)) - self.intensity) * ease
        if self.timer <= 0:
            self.index += 1
            if self.index >= len(self.phases):
                self.intensity = 0.0
                self.over = True
                return False
            self.timer = self.phases[self.index][0]
        return True


def stretched(profile, seconds):
    """The profile's phases stretched evenly to last `seconds`, so a trip can be fitted to its track."""
    factor = seconds / length(profile)
    return [(d * factor, target, ease / factor, amp, speed / factor) for d, target, ease, amp, speed in PROFILES[profile]]


def look(intensity, seconds, pulse=0.0, drums=0.0):
    """What the game shows at this intensity, `seconds` into the trip. pulse (0..1) is where the beat's contraction
    stands, drums (0..1) how much drum is playing. The view does not wobble; it draws in gently on the beat. Nothing
    flashes. Everything scales with intensity, so a sober hero sees nothing. Pure, to tune and test."""
    hue = (seconds / 20.0) % 1.0   # a slow turn of colour: a full circle every twenty seconds
    r, g, b = _hue(hue)
    return {"fov": 0.0, "speed": 1.0,
            "zoom": 0.04 * intensity * drums * pulse,
            "tint": (r, g, b, 0.18 * intensity),
            "time": 1.0 - 0.3 * intensity,
            "shake": 0.0,   # the engine's shake jumps every frame, which reads as flicker, not as a tremble
            # The post-process over the finished frame: glowing edges, tracers, Mindcap's colours.
            "post": intensity, "edges": 1.0, "tracers": 1.0}


# The beat's contraction: drawn in over the first CONTRACT of a beat, then released over RELAX seconds with a damped
# rebound (BOUNCE of the pull, every BOUNCE_PERIOD seconds), so the view springs rather than sags. It never zooms out
# past normal. Pulses never come faster than MAX_PULSES a second (photosensitivity guidelines allow three flashes a
# second; this stays well under).
CONTRACT = 0.06
RELAX = 0.28
BOUNCE = 0.35
BOUNCE_PERIOD = 0.30
MAX_PULSES = 2.5


def pulse(seconds, period, phase):
    """Where the beat's contraction stands, 0..1, at a time in the track. A fast track pulses every other beat."""
    while 1.0 / period > MAX_PULSES:
        period *= 2
    if seconds < phase:
        return 0.0
    into = ((seconds - phase) % period) / period
    if into < CONTRACT:
        x = into / CONTRACT
        return x * x * (3 - 2 * x)
    after = (into - CONTRACT) * period          # seconds since the pull peaked
    release = math.exp(-after / RELAX)
    rebound = BOUNCE * math.exp(-after / (RELAX * 0.9)) * math.sin(2 * math.pi * after / BOUNCE_PERIOD)
    return min(1.0, max(0.0, release - rebound))


# How the music's hits are smoothed: a swell rises over about ATTACK seconds and fades over DECAY.
ATTACK = 0.3
DECAY = 0.8


def smooth(value, target, dt):
    """One step of a value easing towards target, faster up than down."""
    tau = ATTACK if target > value else DECAY
    return value + (target - value) * min(1.0, dt / tau)


# Mindcap's palette, as in shader/trip/trip.frag: hot pink (Solaris's 0xff44ff), violet and a bright green, visited
# pink, violet, green, violet, pink so it never crosses straight from green to pink, which goes through grey.
PINK, VIOLET, GREEN = (1.00, 0.27, 1.00), (0.55, 0.25, 1.00), (0.30, 1.00, 0.45)
PALETTE = (PINK, VIOLET, GREEN, VIOLET)


def _vivid_mix(a, b, f):
    """a and b blended, with the colourfulness pushed back up to the blend of theirs, so midpoints never turn grey."""
    c = [x + (y - x) * f for x, y in zip(a, b)]
    lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    want = (max(a) - min(a)) * (1 - f) + (max(b) - min(b)) * f
    have = max(c) - min(c)
    if have > 1e-6:
        c = [lum + (x - lum) * want / have for x in c]
    return tuple(min(1.0, max(0.0, x)) for x in c)


def _hue(h):
    """A colour on the palette's circle for a position between 0 and 1."""
    h = (h % 1.0) * len(PALETTE)
    i = int(h)
    f = h - i
    f = f * f * (3 - 2 * f)   # smoothstep, as in the shader
    return _vivid_mix(PALETTE[i], PALETTE[(i + 1) % len(PALETTE)], f)


def crossfade(progress):
    """Equal-power volumes (track, game music) for a fade from 0 (game music only) to 1 (track only)."""
    progress = min(1.0, max(0.0, progress))
    return math.sin(progress * math.pi / 2), math.cos(progress * math.pi / 2)


def say(gothic, text):
    """A thought from off: the distorted take if there is one, the plain one, or a silent subtitle. False while busy."""
    from dm import voices
    wav, ms = voices.lookup(HERO_VOICE, text, DELIVERY)
    if not wav:
        wav, ms = voices.lookup(HERO_VOICE, text)
    return gothic.dialog.narrate(text, ms, wav)


class Trip:
    def __init__(self, phases, track, thoughts=None, rng=None):
        from dm import music_bands
        self.envelope = Envelope(phases)
        self.track = track
        self.bands = music_bands.load(track) if track else None
        self.beat = music_bands.beat(track) if track else None
        self.track_started = None
        self.swell = 0.0
        self.bass = 0.0
        self.mid = 0.0
        self.treble = 0.0
        self.last_look = None
        self.started = None
        self.carry = 0.0
        self.rng = rng or random.Random()
        self.thoughts = sorted(thoughts) if thoughts else draw_thoughts(self.rng)
        self.landing = self.rng.choice(LANDINGS)
        self.last_refusal = None
        self.said = set()
        self.peaked = False
        self.landed = False
        self.queue = []          # thoughts waiting until nothing else is being said
        self.refused_at = None
        self.visuals = visuals_on()
        self.visuals_read = None
        self.duck = 1.0
        self.duck_at = None
        self.music_end = None   # when the crossfade back to the game's music began
        self.fade_from = 1.0    # how far faded in the track was at that moment
        self.generation = None
        self.last = None

    def _give_music_back(self, now):
        """Begin the crossfade back from wherever the fade-in stood, so stopping early never jumps."""
        if self.music_end is None:
            self.music_end = now
            self.fade_from = min(1.0, (now - self.started) / FADE_IN) if self.started is not None else 0.0

    def stop(self, now):
        """Ease everything down over a few seconds and give the music back."""
        self.envelope.phases = [(STOP_SECONDS, 0.0, 0.02, 0.0, 0.0)]
        self.envelope.index, self.envelope.timer = 0, STOP_SECONDS
        self._give_music_back(now)

    def _think(self, gothic, now):
        """Thoughts on the way up and on landing, conversations blocked while strong, a refusal when one is tried."""
        level = self.envelope.intensity
        for at, text in self.thoughts:
            if level >= at and text not in self.said:
                self.said.add(text)
                self.queue.append(text)
        self.peaked = self.peaked or level >= 0.9
        if self.peaked and not self.landed and level < 0.3:
            self.landed = True
            self.queue.append(self.landing)
        gothic.dialog.block(level > BLOCK_ABOVE and not self.envelope.over)
        if gothic.dialog.take_refused() and (self.refused_at is None or now - self.refused_at >= REFUSAL_PAUSE):
            self.refused_at = now
            self.last_refusal = self.rng.choice([r for r in REFUSALS if r != self.last_refusal])
            self.queue.insert(0, self.last_refusal)
        if self.queue and say(gothic, self.queue[0]):
            self.queue.pop(0)

    def tick(self, gothic, now):
        if self.started is None:
            self.started = now
            self.generation = gothic.world.generation
            if self.track and not gothic.music.play_track(self.track):
                self.track = None
            self.track_started = now
        if gothic.world.generation != self.generation:
            return False        # a new world or a loaded save: drop the trip at once
        if self.last is not None:
            self.carry += now - self.last
        self.last = now
        while self.carry >= STEP and not self.envelope.over:
            self.envelope.step()
            self.carry -= STEP
        elapsed = now - self.started
        if self.track:
            if self.music_end is None and (self.envelope.over or not gothic.music.track_playing()):
                self._give_music_back(now)
            # Duck under a spoken thought: down quickly, back up slowly, like dialogue over film music.
            target = DUCK if gothic.dialog.narrating() else 1.0
            step = (now - self.duck_at) if self.duck_at is not None else 0.0
            self.duck_at = now
            self.duck += (target - self.duck) * min(1.0, step / (0.15 if target < self.duck else 0.6))
            if self.music_end is None:
                track, theme = crossfade(elapsed / FADE_IN)
            else:
                track, theme = crossfade(self.fade_from * (1 - (now - self.music_end) / FADE_OUT))
            gothic.music.mix(track * self.duck, theme)
        from dm import music_bands
        bass, mid, treble, kick = (music_bands.at(self.bands, now - self.track_started) if self.music_end is None
                                   else (0, 0, 0, 0))
        dt = now - self.last_look if self.last_look is not None else 0.0
        self.last_look = now
        self.swell = smooth(self.swell, kick, dt)
        self.bass = smooth(self.bass, bass, dt)
        self.mid = smooth(self.mid, mid, dt)
        self.treble = smooth(self.treble, treble, dt)
        beat = pulse(now - self.track_started, *self.beat) if self.beat and self.music_end is None else 0.0
        drums = min(1.0, max(0.0, (self.swell - 0.15) / 0.35))   # no drum, no pulse: the quiet intro stays calm
        if self.visuals_read is None or now - self.visuals_read >= 1.0:
            self.visuals = visuals_on()          # the off switch works at once, also during a running trip
            self.visuals_read = now
        fx = look(self.envelope.intensity, elapsed, beat, drums)
        if not self.visuals:
            fx = look(0.0, elapsed)          # music and thoughts only: nothing on screen changes
        gothic.trip.set(fx["fov"], fx["speed"], fx["tint"], fx["time"], fx["shake"], fx["post"], fx["edges"],
                        fx["tracers"], (self.bass, self.mid, self.treble), fx["zoom"])
        self._think(gothic, now)
        music_back = not self.track or (self.music_end is not None and now - self.music_end >= FADE_OUT)
        return not (self.envelope.over and music_back)


_current = None


def start(profile="mindcap", track=None, seconds=None, thoughts=None):
    """Begin a trip with the profile's own track unless another is given. seconds stretches the profile (shorter for
    a preview); thoughts replaces the hero's default ones, as (intensity, text). False if one already runs: never two
    tracks at once."""
    global _current
    if _current is not None:
        return False
    if profile not in PROFILES:
        raise ValueError(f"unknown trip: {profile}")
    if track is None and (MUSIC_DIR / TRACKS.get(profile, "")).is_file():
        track = str(MUSIC_DIR / TRACKS[profile])
    phases = stretched(profile, seconds) if seconds else PROFILES[profile]
    _current = Trip(phases, track, [tuple(t) for t in thoughts] if thoughts else None)
    return True


def stop():
    """Ease the running trip down and give the game's music back."""
    if _current is not None:
        _current.stop(time.monotonic())


def running():
    return _current is not None


def _end(gothic):
    global _current
    _current = None
    try:
        gothic.music.stop_track()   # first, and on its own: needs no world, gives the game's music back its volume
    except RuntimeError:
        pass
    try:
        gothic.trip.clear()         # needs a world; without one there is nothing on screen to clear
    except RuntimeError:
        pass
    gothic.dialog.block(False)      # the hero may always talk again


def _tick(_dt):
    import gothic
    if _current is None:
        return
    try:
        if not _current.tick(gothic, time.monotonic()):
            _end(gothic)
    except RuntimeError:
        _end(gothic)                # no world while loading


def start_ticking():
    """Safe to call repeatedly."""
    import gothic
    if getattr(gothic, "_dm_trip_registered", False):
        return
    gothic.on_tick(lambda dt: sys.modules["dm.trip"]._tick(dt))
    gothic._dm_trip_registered = True
