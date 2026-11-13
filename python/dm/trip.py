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

# The trips are split in three: the effect engine and the state of the running trip here, what they say in trip_lines,
# and the aftercare in trip_aftercare. Every name of both is re-exported here, so `trip.X` keeps working for all.
from dm.trip_lines import (THOUGHT_POOLS, LANDINGS, DESERT_POOLS, DESERT_LANDINGS, SLEEPER_POOLS, SLEEPER_LANDINGS,
                           POOLS, ESCAPES, REFUSALS, DELIVERY, HERO_VOICE, SPECIAL_OPENERS, SPECIAL_ANSWERS,
                           NORTH_ANSWERS, DESERT_ANSWERS, SLEEPER_ANSWERS, PROFILE_ANSWERS, SPECIAL_CLOSERS,
                           SPECIAL_LAST, SPECIAL_GUARDS, GUARD_GUILDS, SPECIAL_VOICES_ALL, GUARD_VOICES_ALL, DRINKING,
                           SPECIAL_DRINKERS, SPECIAL_BY_NAME, SPECIAL_PEOPLE, special_graph, is_drinking, is_guard,
                           BLACKOUTS, thought_lines, draw_thoughts, HEROLD, HEROLD_OPEN, HEROLD_CLOSE, HEROLD_NEWS,
                           herold_lines)  # noqa: F401
from dm.trip_aftercare import (AFTERCARE_NPC, AFTERCARE_VOICE, AFTERCARE_TOPIC, AFTERCARE_TITLE, PROFILE_REGION,
                               AFTERCARE, AFTERCARE_OPEN, RESERVED_LINE, made_way, AFTERCARE_SKY, AFTERCARE_CLOSE,
                               AFTERCARE_LAST, SMOKE_SET, SMOKE_GIFT, SMOKE_THANKS, SMOKE_MASTER_TOPIC,
                               SMOKE_MASTER_FLAG, SMOKE_MASTER_TITLE, SMOKE_MASTER, SMOKE_MASTER_LAST, RECOGNISE_TITLE,
                               RECOGNISE, REMARK_NEAR, REMARK_GAP, REMARKS_BY_NAME, REMARKS_CITIZEN, REMARKS_GUARD,
                               smoke_set_worn, remark_for, tick_remarks, _story, smoke_set, _carried, _flag,
                               aftercare_graph, _speech, extra_topics, AFTERCARE_FLAG, _pending_aftercare, topic,
                               after_lines)  # noqa: F401


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
    # The scorpion blend from the south, in Emberheart's spirit: it creeps, then hits like heatstroke at the track's
    # first big rise and blazes in waves. Cut to "Khe-Ru-Dhem (1)" (192 s, acoustic): the jump at 20 s, an even drive,
    # the peak near the end, an abrupt stop.
    "skorpion": [(20.0, 0.10, 0.010, 0.0, 0.0), (4.0, 0.90, 0.040, 0.0, 0.0), (46.0, 0.70, 0.008, 0.10, 0.05),
                 (95.0, 0.85, 0.006, 0.10, 0.04), (25.0, 1.00, 0.015, 0.05, 0.05), (25.0, 0.00, 0.008, 0.0, 0.0)],
    # Cut to "Circle of Fire" (208 s, 102 BPM, an acoustic desert ritual; the Goa take was out of place in Gothic):
    # a creeping opening, the heat hitting at the step up at 60 s, waves climbing, the eye opening after the small dip
    # at 165 s, and the blackout as the music stops.
    "skorpion_goa": [(20.0, 0.10, 0.010, 0.0, 0.0), (40.0, 0.35, 0.006, 0.02, 0.02), (5.0, 0.85, 0.040, 0.0, 0.0),
                     (60.0, 0.75, 0.008, 0.10, 0.05), (40.0, 0.85, 0.006, 0.10, 0.04), (37.0, 1.00, 0.012, 0.06, 0.05),
                     (8.0, 0.00, 0.020, 0.0, 0.0)],
    # The Invocation (Y'Berion's forbidden blend). Cut to "Moonlit Prayer" (234 s, 103 BPM): a quiet prayer for a
    # minute, the call rising to 160 s, a short break, the vision opening as the climax starts at 168 s, and the
    # blackout falling with the music's collapse into silence at 230 s.
    "anrufung": [(60.0, 0.30, 0.005, 0.0, 0.0), (40.0, 0.50, 0.005, 0.03, 0.02), (60.0, 0.75, 0.006, 0.05, 0.02),
                 (8.0, 0.65, 0.020, 0.0, 0.0), (60.0, 1.00, 0.012, 0.04, 0.03), (12.0, 0.00, 0.020, 0.0, 0.0)],
}

# How each trip looks. Mindcap: neon edges and long tracers in pink, violet and green. Ember (Solaris's Emberheart):
# heat shimmer in rings from the middle, a warm wash and the desert's sand, gold, ochre and amber; edges and tracers
# kept low, so heat carries it rather than neon.
# A second stage can open over the ember once the heat has hit (between OPEN_FROM and OPEN_TO intensity): Solaris's
# DragonflyEye (a compound eye under a turning rose window) or its Afterglow (long exposure: bright things burn in and
# smear). Afterglow keeps its glow in the history images, so its look has no tracers.
LOOKS = {"mindcap": {"look": 0, "edges": 1.0, "tracers": 1.0, "pools": "mindcap"},
         "ember": {"look": 1, "edges": 0.35, "tracers": 0.35, "pools": "ember"},
         "ember_eye": {"look": 1, "edges": 0.35, "tracers": 0.35, "pools": "ember", "eye": True, "at_peak": True},
         "ember_glow": {"look": 1, "edges": 0.35, "tracers": 0.0, "pools": "ember", "afterglow": True},
         # The Invocation: moonlit watercolour, patterns growing from edges, and the vision (a negative) at the peak.
         "invocation": {"look": 2, "edges": 0.15, "tracers": 0.5, "pools": "sleeper", "eye": True, "at_peak": True}}
PROFILE_LOOK = {"skorpion": "ember_glow", "skorpion_goa": "ember_eye", "anrufung": "invocation"}
OPEN_FROM, OPEN_TO = 0.55, 0.9
PEAK_OPEN = 6.0   # seconds over which a stage that waits for the peak fades in once the peak phase begins

BLOCK_ABOVE = 0.35        # above this intensity, conversations become the special trip dialogue
DUCK = 0.4                # the trip's music while a thought is spoken, so the hero carries over the drums
REFUSAL_PAUSE = 8.0       # seconds between two refusal thoughts
THOUGHT_GAP = 4.0         # seconds of quiet after a thought before the next one
SETTINGS = __import__("pathlib").Path(__file__).resolve().parent.parent / "dm_runtime" / "settings.json"


def special_for(npc):
    """The trip dialogue for this NPC while a trip runs, a waiting line after a blackout, else None.

    Only two kinds of conversation ask: any, once the trip is strong (the engine hands them over), and a story's own,
    at any strength. So people with a story to tell meet a tripping hero as such from the first draw to the landing,
    and he cannot finish their quest high; everyone else talks normally while the trip is mild."""
    if _current is None:
        return after_graph(npc)
    if _current.black is not None or _current.envelope.over:
        return None
    return special_graph(npc.voice, _current.rng, getattr(npc, "instance", "") or "", is_guard(npc),
                         getattr(_current, "profile", None), is_drinking(npc), getattr(npc, "name", "") or "")


AFTER_NEAR = 500.0    # how close (cm) the hero passes someone before they speak up
SERMON_GAP = 2.5      # seconds between the sentences of a sermon
AFTER_FOR = 900.0     # seconds after waking that the house still remembers him
# A galaxy in place of the sky (shader/sky/sky.frag), every trip its own: the Milky Way panorama graded to the
# trip's colour, two Webb nebulae placed high on the sky, opening with the trip's strength and turning slowly.
# The images live in dm_runtime/sky (see CREDITS.md there); without them the sky stays the game's own.
SKY_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "dm_runtime" / "sky"
SKY_FROM, SKY_TO = 0.2, 0.7     # intensity at which the sky starts to open, and is fully open
SKY_SPIN = 0.006                # radians a second
SKY_GAIN = 1.0
GALAXIES = {
    # Nordmar: the ice-blue Milky Way with the northern lights in front, instead of nebulae, and at the peak of the
    # war chant a blood-red moon.
    "ice": {"tint": (0.55, 0.80, 1.00), "grade": 0.70, "nebulae": (), "aurora": 1.0, "blood_moon": True},
    "hot": {"tint": (1.00, 0.50, 0.15), "grade": 0.75, "nebulae": ("pillars.jpg", "cosmic_cliffs.jpg")},
    "sleeper": {"tint": (0.75, 0.65, 1.00), "grade": 0.30, "nebulae": ("stephans_quintet.jpg", "pillars.jpg")},
    "neon": {"tint": (1.00, 0.45, 1.00), "grade": 0.50, "nebulae": ("cosmic_cliffs.jpg", "stephans_quintet.jpg")},
}
PROFILE_GALAXY = {"nordmar": "ice", "kriegsgesang": "ice", "skorpion": "hot", "skorpion_goa": "hot",
                  "anrufung": "sleeper", "mindcap": "neon", "wasserpfeife": "neon"}
# Where the two nebulae hang: (yaw, pitch, size across, strength), radians; high up, on opposite sides.
NEBULA_SPOTS = ((0.6, 0.75, 0.95, 0.9), (3.6, 0.55, 0.85, 0.8))
_sky_loaded = {}


def sky_amount(intensity):
    x = min(1.0, max(0.0, (intensity - SKY_FROM) / (SKY_TO - SKY_FROM)))
    return x * x * (3 - 2 * x)


def _load_sky(gothic, slot, name):
    """Loads an image into a sky slot once; False if it or the engine's sky is missing."""
    if _sky_loaded.get(slot) == name:
        return True
    path = SKY_DIR / name
    if not path.is_file() or not hasattr(gothic, "sky") or not gothic.sky.load(slot, str(path)):
        return False
    _sky_loaded[slot] = name
    return True


def set_sky(gothic, kind, intensity, seconds, glow=0.0, peak=0.0):
    """Shows the trip's galaxy at this intensity, or the game's own sky when there is none. peak (0..1) is how far
    the trip's highest stage has opened, for what rises only then (the blood moon)."""
    if not hasattr(gothic, "sky"):
        return
    cfg = GALAXIES.get(kind)
    if cfg is None or not _load_sky(gothic, 0, "milkyway.jpg"):
        gothic.sky.clear()
        return
    spots = [spot if _load_sky(gothic, i + 1, name) else (0.0, 0.0, 0.0, 0.0)
             for i, (name, spot) in enumerate(zip(cfg["nebulae"], NEBULA_SPOTS))]
    gothic.sky.galaxy(sky_amount(intensity), SKY_GAIN, cfg["tint"], cfg["grade"], seconds * SKY_SPIN,
                      min(1.0, glow), spots, cfg.get("aurora", 0.0), seconds,
                      peak * sky_amount(intensity) if cfg.get("blood_moon") else 0.0)


FADE_BLACK = 3.5    # seconds to black
FADE_WAKE = 5.0     # seconds back from black
SETTLE = 1.5        # seconds in the dark before looking for the bed: the world needs a moment after a move
LIE_DOWN_FOR = 6.0  # seconds to keep trying to lie down before waking anyway
DARK_AFTER = 2.5    # seconds of black once he lies there


def say_plain(gothic, text):
    """A line in the hero's ordinary voice, as he comes to: no distortion. Its length in seconds, or None if busy."""
    from dm import voices
    wav, ms = voices.lookup(HERO_VOICE, text)
    if not gothic.dialog.narrate(text, ms, wav):
        return None
    return (ms or max(2000, len(text) * 70)) / 1000.0


def visuals_on():
    """Whether trips may change the picture. Off keeps the music and the thoughts (photosensitivity)."""
    try:
        return bool(__import__("json").loads(SETTINGS.read_text(encoding="utf-8")).get("trip_visuals", True))
    except (OSError, ValueError):
        return True


# A profile's own track, in python/dm_runtime/music (private: never committed).
TRACKS = {"mindcap": "mindcap.wav", "wasserpfeife": "wasserpfeife.wav", "nordmar": "nordmar.wav",
          "kriegsgesang": "kriegsgesang.wav", "skorpion": "skorpion.wav", "skorpion_goa": "skorpion_fire.wav",
          "anrufung": "anrufung.wav"}
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


def look(intensity, seconds, pulse=0.0, drums=0.0, style="mindcap", opened=None):
    """What the game shows at this intensity, `seconds` into the trip. pulse (0..1) is where the beat's contraction
    stands, drums (0..1) how much drum is playing. The view does not wobble; it draws in gently on the beat. Nothing
    flashes. Everything scales with intensity, so a sober hero sees nothing. Pure, to tune and test."""
    hue = (seconds / 20.0) % 1.0   # a slow turn of colour: a full circle every twenty seconds
    r, g, b = _hue(hue, {1: DESERT, 2: MOON}.get(LOOKS[style]["look"], PALETTE))
    if opened is None:
        x = min(1.0, max(0.0, (intensity - OPEN_FROM) / (OPEN_TO - OPEN_FROM)))
        opened = x * x * (3 - 2 * x)   # the second stage opens smoothly once the heat has hit
    return {"fov": 0.0, "speed": 1.0,
            "zoom": 0.04 * intensity * drums * pulse,
            "tint": (r, g, b, 0.18 * intensity),
            "time": 1.0 - 0.3 * intensity,
            "shake": 0.0,   # the engine's shake jumps every frame, which reads as flicker, not as a tremble
            # The post-process over the finished frame: glowing edges, tracers, Mindcap's colours.
            "post": intensity, "edges": LOOKS[style]["edges"], "tracers": LOOKS[style]["tracers"],
            "look": LOOKS[style]["look"],
            "eye": opened if LOOKS[style].get("eye") else 0.0,
            "afterglow": opened if LOOKS[style].get("afterglow") else 0.0}


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
# Emberheart's desert, as in shader/trip/trip.frag: pale sand, gold, deep ochre, amber.
DESERT = ((1.00, 0.91, 0.63), (1.00, 0.80, 0.33), (0.87, 0.60, 0.20), (1.00, 0.67, 0.27))
# The Invocation's night, as in the shader: moonlight silver, the swamp's green, violet, a cold blue.
MOON = ((0.80, 0.86, 1.00), (0.40, 0.90, 0.50), (0.58, 0.34, 0.96), (0.40, 0.55, 1.00))


def _vivid_mix(a, b, f):
    """a and b blended, with the colourfulness pushed back up to the blend of theirs, so midpoints never turn grey."""
    c = [x + (y - x) * f for x, y in zip(a, b)]
    lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    want = (max(a) - min(a)) * (1 - f) + (max(b) - min(b)) * f
    have = max(c) - min(c)
    if have > 1e-6:
        c = [lum + (x - lum) * want / have for x in c]
    return tuple(min(1.0, max(0.0, x)) for x in c)


def _hue(h, palette=PALETTE):
    """A colour on a palette's circle for a position between 0 and 1."""
    h = (h % 1.0) * len(palette)
    i = int(h)
    f = h - i
    f = f * f * (3 - 2 * f)   # smoothstep, as in the shader
    return _vivid_mix(palette[i], palette[(i + 1) % len(palette)], f)


def crossfade(progress):
    """Equal-power volumes (track, game music) for a fade from 0 (game music only) to 1 (track only)."""
    progress = min(1.0, max(0.0, progress))
    return math.sin(progress * math.pi / 2), math.cos(progress * math.pi / 2)


def say(gothic, text):
    """A thought from off: the distorted take if there is one, the plain one, or a silent subtitle. Its length in
    seconds once it plays, or None while something else is being said."""
    from dm import voices
    wav, ms = voices.lookup(HERO_VOICE, text, DELIVERY)
    if not wav:
        wav, ms = voices.lookup(HERO_VOICE, text)
    if not gothic.dialog.narrate(text, ms, wav):
        return None
    return (ms or max(2000, len(text) * 70)) / 1000.0   # the engine's own length for a line without audio


class Trip:
    def __init__(self, phases, track, thoughts=None, rng=None, style="mindcap", blackout=None):
        from dm import music_bands
        self.envelope = Envelope(phases)
        self.style = style
        self.blackout = dict(blackout) if blackout else None
        targets = [phase[1] for phase in phases]
        self.peak_phase = targets.index(max(targets))   # the first phase that climbs to the trip's highest point
        self.peak_at = None
        self.black = None      # the blackout under way: {"stage", "at", ...}
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
        pools = LOOKS[style]["pools"]
        self.thoughts = sorted(thoughts) if thoughts else draw_thoughts(self.rng, pools)
        self.landing = self.rng.choice(POOLS[pools][1])
        self.last_refusal = None
        self.said = set()
        self.peaked = False
        self.landed = False
        self.queue = []          # thoughts waiting until nothing else is being said
        self.refused_at = None
        self.quiet_until = 0.0
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
        reached = [text for at, text in self.thoughts if level >= at and text not in self.said]
        if reached:
            # A trip that leaps through several stages at once says only the highest; the ones it rushed past are
            # skipped, and so is any earlier stage still waiting to be said.
            self.said.update(reached)
            stages = {text for _, text in self.thoughts}
            self.queue = [t for t in self.queue if t not in stages] + [reached[-1]]
        self.peaked = self.peaked or level >= 0.9
        if self.peaked and not self.landed and level < 0.3:
            self.landed = True
            self.queue.append(self.landing)
        gothic.dialog.trip_talk(level > BLOCK_ABOVE and not self.envelope.over)
        if gothic.dialog.take_refused() and (self.refused_at is None or now - self.refused_at >= REFUSAL_PAUSE):
            self.refused_at = now
            self.last_refusal = self.rng.choice([r for r in REFUSALS if r != self.last_refusal])
            self.queue.insert(0, self.last_refusal)
        escapes = gothic.trip.take_escapes() if hasattr(gothic.trip, "take_escapes") else 0
        if escapes and not (self.queue and self.queue[0] in ESCAPES):
            self.queue.insert(0, self.rng.choice(ESCAPES))   # he answers the menu he was about to open
        refusing = self.queue and (self.queue[0] in REFUSALS or self.queue[0] in ESCAPES)
        if self.queue and (refusing or now >= self.quiet_until):
            length = say(gothic, self.queue[0])
            if length is not None:
                self.queue.pop(0)
                self.quiet_until = now + length + THOUGHT_GAP

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
        # The peak phase opens over PEAK_OPEN seconds: a look's second stage may wait for it, and the sky's moon does.
        if self.peak_at is None and self.envelope.index >= self.peak_phase:
            self.peak_at = now
        x = 0.0 if self.peak_at is None else min(1.0, (now - self.peak_at) / PEAK_OPEN)
        peak_open = x * x * (3 - 2 * x)
        opened = peak_open if LOOKS[self.style].get("at_peak") else None
        fx = look(self.envelope.intensity, elapsed, beat, drums, self.style, opened)
        if not self.visuals:
            fx = look(0.0, elapsed, style=self.style)   # music and thoughts only: nothing on screen changes
        if self.blackout and self.black is None and self.envelope.index >= len(self.envelope.phases) - 1:
            self.black = {"stage": "fading", "at": now}   # the landing becomes a blackout
            self.queue = []
            self._give_music_back(now)
        if self.black is not None:
            fx = self._blackout(gothic, now, fx, elapsed)
        gothic.trip.set(fx["fov"], fx["speed"], fx["tint"], fx["time"], fx["shake"], fx["post"], fx["edges"],
                        fx["tracers"], (self.bass, self.mid, self.treble), fx["zoom"], fx["look"], fx["eye"],
                        fx["afterglow"])
        set_sky(gothic, PROFILE_GALAXY.get(getattr(self, "profile", None)), fx["post"], elapsed, self.swell,
                peak_open if self.visuals else 0.0)
        if self.black is None:
            self._think(gothic, now)
        music_back = not self.track or (self.music_end is not None and now - self.music_end >= FADE_OUT)
        if self.black is not None:
            return self.black["stage"] != "done"
        return not (self.envelope.over and music_back)

    def _blackout(self, gothic, now, fx, elapsed):
        """The blackout's picture and its steps: to black, the move and the bed in the dark, back from black."""
        b, cfg = self.black, self.blackout
        since = now - b["at"]
        if b["stage"] == "fading":
            alpha = min(1.0, since / FADE_BLACK)
            if alpha >= 1.0:
                b.update(stage="dark", at=now)
                gothic.dialog.trip_talk(False)
                if gothic.dialog.is_open():
                    gothic.dialog.close()                  # nobody talks through a blackout: the partner stays behind
                if "in_world" not in cfg or gothic.world.has_waypoint(cfg["in_world"]):
                    gothic.player.set_position(*(cfg["bed"] if "bed" in cfg
                                                 else gothic.world.waypoint_position(cfg["waypoint"])))
                    gothic.world.set_time(cfg["hour"], 0)  # the next morning; NPCs go back to their routines
                else:
                    b["elsewhere"] = True                  # another world: he comes to where he fell, nobody waits
                return dict(look(0.0, elapsed, style=self.style), tint=(0.0, 0.0, 0.0, 1.0))
            return dict(fx, tint=(0.0, 0.0, 0.0, alpha))
        sober = look(0.0, elapsed, style=self.style)
        if b["stage"] == "dark":
            if "scheme" not in cfg or b.get("elsewhere"):
                b.setdefault("lying", True)                # no bed: he comes to on his feet
                b.setdefault("lay_at", now)
            if not b.get("lying") and since >= SETTLE:
                b["lying"] = gothic.player.use_object(cfg["scheme"], 1, quiet=True)
                if b["lying"]:
                    b["lay_at"] = now
            ready = (b.get("lying") and now - b["lay_at"] >= DARK_AFTER) or since >= SETTLE + LIE_DOWN_FOR
            if ready:
                b.update(stage="waking", at=now)
            return dict(sober, tint=(0.0, 0.0, 0.0, 1.0))
        if b["stage"] == "waking":
            alpha = max(0.0, 1.0 - since / FADE_WAKE)
            if alpha <= 0.0 and say_plain(gothic, self.rng.choice(cfg["wake"])) is not None:
                b["stage"] = "done"
                if not b.get("elsewhere"):
                    remember_after(gothic, cfg.get("after", []), now)
            return dict(sober, tint=(0.0, 0.0, 0.0, alpha))
        return sober


_current = None
SNOW_WITH = {"nordmar", "kriegsgesang"}   # trips that bring their own snowfall


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
    _current = Trip(phases, track, [tuple(t) for t in thoughts] if thoughts else None,
                    style=PROFILE_LOOK.get(profile, "mindcap"), blackout=BLACKOUTS.get(profile))
    _current.profile = profile
    if profile in SNOW_WITH:
        # The north brings its weather: snow thickening over the first third, held, clearing before the landing.
        total = sum(phase[0] for phase in phases)
        from dm import weather
        weather.snow(rise=total * 0.3, hold=total * 0.45, fall=total * 0.2)
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
    try:
        if hasattr(gothic, "sky"):
            gothic.sky.clear()      # the game's own sky again
    except RuntimeError:
        pass
    gothic.dialog.block(False)      # the hero may always talk again, as himself
    gothic.dialog.trip_talk(False)


# Lines people say to the hero after a blackout, once each as he passes them: [lines, until, world generation].
_after = None


def remember_after(gothic, lines, now):
    """Lines people have for the hero after a trip, each until its own "for" seconds have passed (AFTER_FOR unless
    it says). Added to those still waiting in this world, so a blackout's farewells and the crier's news both keep."""
    global _after
    fresh = [dict(line, until=now + line.get("for", AFTER_FOR), ready=now + line.get("wait", 0.0)) for line in lines]
    if not fresh:
        return
    if _after is not None and _after[2] == gothic.world.generation:
        _after[0].extend(fresh)
        _after[1] = max(_after[1], max(line["until"] for line in fresh))
    else:
        _after = [fresh, max(line["until"] for line in fresh), gothic.world.generation]


def _forget_after(gothic, same_world):
    global _after
    if _after is not None and same_world:
        for line in _after[0]:
            _release(gothic, line)
            if line.get("hushed"):
                npc = gothic.world.find_npc(line["npc"])
                if npc is not None:
                    _unhush(gothic, npc, line)
    _after = None


def _release(gothic, line):
    """Gives a speaker his own conversations back."""
    if line.pop("bound", False):
        npc = gothic.world.find_npc(line["npc"])
        story = sys.modules.get("dm.story")   # only if it runs: importing it here would start it
        graphs = story.state().get("graphs", {}) if story is not None else {}
        if npc is not None and str(line["npc"]).upper() not in graphs:
            gothic.dialog.unbind(npc)   # one with a story conversation of his own keeps it


def tick_after(gothic, now):
    """Speaks a waiting line once the hero is near its speaker, in whatever order he passes them; forgets them when
    too late or in another world or save. A speaker who would stop the hero with his own words takes over that
    conversation instead (see after_graph)."""
    if _after is None:
        return
    lines, until, generation = _after
    if not lines or now > until or gothic.world.generation != generation:
        _forget_after(gothic, gothic.world.generation == generation)
        return
    for line in list(lines):
        if now > line.get("until", until) and not line.get("next"):
            _release(gothic, line)          # too late for this one; a sermon begun is still preached to the end
            lines.remove(line)
    talking = gothic.dialog.partner() is not None
    for line in list(lines):
        if line.get("taken") and not talking:  # unbinding the partner would close the conversation he is in
            _release(gothic, line)
            lines.remove(line)

    for line in list(lines):
        takes_over = line.get("converse") or (line.get("instead_of") and not gothic.player.heard(line["instead_of"]))
        if takes_over and not line.get("bound"):
            npc = gothic.world.find_npc(line["npc"])
            if npc is not None:
                gothic.dialog.bind(npc)         # his conversation becomes this line, whoever starts it
                line["bound"] = True
    for line in lines:
        if line.get("sermon") and line.get("next", 0) > 0:
            npc = gothic.world.find_npc(line["npc"])
            if npc is not None:
                _hush(npc, line)                # every tick once begun, also while a sentence is playing
    if gothic.dialog.partner() is not None or gothic.dialog.narrating():
        return
    here = gothic.player.position
    for line in list(lines):
        if line.get("bound"):
            continue                            # said in the conversation he starts himself
        if line.get("sermon"):
            if _preach(gothic, line, here, now):
                return
            continue
        npc = gothic.world.find_npc(line["npc"])
        if npc is None:
            lines.remove(line)                  # gone (dead, or elsewhere in the world): nothing to say
            continue
        if sum((a - b) ** 2 for a, b in zip(here, npc.position)) > AFTER_NEAR ** 2:
            continue
        from dm import voices
        wav, ms = voices.lookup(line["voice"], line["line"])
        if gothic.dialog.narrate(line["line"], ms, wav):
            lines.remove(line)
        return                                  # one at a time


def _preach(gothic, line, here, now):
    """The next sentence of a sermon once the hero is near and the last has had its pause; True if one was said.
    Finished sermons leave the list, and the preacher his own routine again."""
    npc = gothic.world.find_npc(line["npc"])
    if npc is None:
        _after[0].remove(line)
        return False
    if line.get("next", 0) == 0 and (now < line.get("ready", 0.0)
                                     or sum((a - b) ** 2 for a, b in zip(here, npc.position)) > line["near"] ** 2):
        return False                            # not begun until ready and near; once begun, it is preached to the end
    _hush(npc, line)
    if now < line.get("quiet_until", 0.0):
        return False
    if line.get("next", 0) >= len(line["sermon"]):
        _after[0].remove(line)
        _unhush(gothic, npc, line)
        return False
    from dm import voices
    text = line["sermon"][line.get("next", 0)]
    wav, ms = voices.lookup(line["voice"], text)
    if not gothic.dialog.narrate(text, ms, wav):
        return False
    line["next"] = line.get("next", 0) + 1
    line["quiet_until"] = now + (ms or max(2500, len(text) * 70)) / 1000.0 + SERMON_GAP
    return True


def _hush(npc, line):
    """Puts the preacher's own sermon on hold: he stands while he gives ours (also if he only reaches his spot once
    ours has begun)."""
    if line.get("hush") and not line.get("hushed") and npc.in_state(line["hush"]):
        npc.stand_here()
        line["hushed"] = True


def _unhush(gothic, npc, line):
    """Gives a preacher his own routine back."""
    if line.pop("hushed", False):
        try:
            gothic.daedalus.call("B_STARTOTHERROUTINE", npc, line["resume"])
        except RuntimeError:
            pass


def after_graph(npc):
    """The conversation a speaker of a waiting line has instead of his own, or None. Taken once."""
    if _after is None:
        return None
    for line in _after[0]:
        if line.get("bound") and not line.get("taken") and line["npc"] == getattr(npc, "instance", ""):
            line["taken"] = True                # released once the conversation is over (tick_after)
            # Counted as heard now, not when he is let go: the moment the conversation closes his own AI would
            # stop the hero with the pitch, before the next tick could say otherwise.
            try:
                import gothic
                for info in ([line["instead_of"]] if line.get("instead_of") else []) + line.get("also_heard", []):
                    gothic.player.mark_heard(info)  # after that night he is no stranger to pitch to
            except (ImportError, AttributeError, ValueError, RuntimeError):
                pass                            # an older game build: he pitches once more, nothing worse
            return {"voice": line["voice"], "start": "a", "nodes": {"a": {
                "line": line["line"],
                "choices": [{"text": line.get("reply", "…"), "ends": True}]}}}
    return None


# The aftercare's state (trip_aftercare reads and changes it through this module, so there is one of each).
_aftercare = None   # (region, world generation) of the last trip, until talked about
_remarked = {}            # instance -> game day of his remark
_remark_at = [0.0]


def saving_blocked():
    """While a trip runs, a preacher's own sermon is on hold for the morning's, or someone waits on a bench for the
    pipe the hero was given: a save would keep half of it, or keep him there."""
    held = _after is not None and any(line.get("hushed") for line in _after[0])
    story = getattr(sys.modules.get("dm.story"), "_story", None)
    waiting = bool(getattr(story, "evicted", None))
    return _current is not None or held or waiting


def _block_save(gothic):
    if hasattr(gothic.trip, "block_save"):
        gothic.trip.block_save(saving_blocked())


def _tick(_dt):
    global _aftercare
    import gothic
    if _current is None:
        try:
            tick_after(gothic, time.monotonic())
            tick_remarks(gothic, time.monotonic())
        except RuntimeError:
            pass                    # no world while loading
        _block_save(gothic)
        return
    try:
        if not _current.tick(gothic, time.monotonic()):
            if _current.generation == gothic.world.generation:
                # Only a trip that ran its course here: one cut off by a load never happened in the loaded save.
                _aftercare = (PROFILE_REGION.get(getattr(_current, "profile", None), "other"), gothic.world.generation)
                story = _story()
                if story is not None:
                    # Through the story's log, which is what a save keeps: a restart does not lose the talk.
                    for region in AFTERCARE:
                        if story.state["flags"].get(f"{AFTERCARE_FLAG}{region}"):
                            story.player_flag(f"{AFTERCARE_FLAG}{region}", False)
                    story.player_flag(f"{AFTERCARE_FLAG}{_aftercare[0]}")
                if _after is not None:   # a crier's earlier news gives way to tonight's
                    _after[0][:] = [line for line in _after[0] if line.get("npc") != HEROLD["npc"] or line.get("next")]
                remember_after(gothic, [herold_lines(_aftercare[0])], time.monotonic())
            _end(gothic)
    except RuntimeError:
        _end(gothic)                # no world while loading
    _block_save(gothic)


def start_ticking():
    """Safe to call repeatedly."""
    import gothic
    if getattr(gothic, "_dm_trip_registered", False):
        return
    gothic.on_tick(lambda dt: sys.modules["dm.trip"]._tick(dt))
    gothic._dm_trip_registered = True


# The story layer asks its extensions for topics, conversations and reactions; the trips are one.
TOPIC_PREFIX = "trip:"
try:
    from dm import story as _story_layer
    _story_layer.register(sys.modules[__name__])
except ModuleNotFoundError:   # outside the game (a tool or test without the gothic module): no story layer to join
    pass
