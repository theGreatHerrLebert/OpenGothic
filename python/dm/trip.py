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

# The hero's thoughts from off, distorted (delivery "rausch", see trip_voices.py). Each trip draws one line per stage
# at random, so two trips never sound quite alike, and says it once when the trip first reaches that intensity; one
# landing line when it comes down again. A story may give its own thoughts instead, which are then said as written.
THOUGHT_POOLS = [
    (0.25, ["Was ist hier los?", "Irgendwas stimmt hier nicht …", "Hm. Der Boden … der wackelt.",
            "Warum ist alles so … bunt?"]),
    (0.5, ["Die Wände … die atmen.", "Hörst du das? Das Licht, es ... es summt.", "Meine Hände … die sind so weit weg.",
           "Die Luft schmeckt nach Farben."]),
    (0.75, ["Die Trommeln … die sind in meinem Kopf.", "Alles dreht sich … und ich dreh mich mit.",
            "Ich glaub, ich kann die Sterne hören.", "Wer hat die Welt so laut gemacht?"]),
    (0.95, ["Die Wände schmelzen …", "Ich bin … riesig. Oder winzig?", "Jetzt seh ich alles. Alles!",
            "Beliar, bist du das?"]),
]
LANDINGS = ["Langsam … langsam kommt alles zurück.", "Uff. Was war das denn?", "Nie wieder. Oder … morgen wieder.",
            "Mein Kopf … wie nach drei Flaschen Wein."]
# The desert's thoughts, for the ember trips (the scorpion blends): heat, sand, scorpions, a whisper from the south.
DESERT_POOLS = [
    (0.25, ["Warum ist mir so heiß?", "Riecht hier was … verbrannt?", "Der Boden flimmert.",
            "Hm. Mein Mund ist voller Sand."]),
    (0.5, ["Der Sand … der singt.", "Wer hat die Sonne angezündet?", "Alles schmilzt in der Hitze.",
           "Da krabbelt was. Viele Beine."]),
    (0.75, ["Die Hitze … die flüstert mir was zu.", "Ich seh Dünen. Hier gibt's keine Dünen!",
            "Mein Schatten … der hat einen Stachel.", "Trommeln … aus dem Süden."]),
    (0.95, ["Ich bin … der Skorpion.", "Beliar … bist du das in der Hitze?", "Alles brennt. Und es ist schön.",
            "Die Sonne … die frisst mich auf."]),
]
DESERT_LANDINGS = ["Wasser. Ich brauch Wasser.", "Uff. Die Hitze lässt nach.", "Nie wieder Skorpion. Ehrlich.",
                   "Mein Kopf glüht noch …"]
# The Sleeper's thoughts, for the Invocation: a prayer in the night, a call, and what the Gurus saw.
SLEEPER_POOLS = [
    (0.25, ["Der Mond … der ist so nah.", "Alles ist so still. So friedlich.", "Ich sollte beten. Zu wem eigentlich?",
            "Das Licht ist ganz silbern."]),
    (0.5, ["Da ruft jemand. Ganz leise.", "Erwache …", "Die Muster … die waren vorher nicht da.",
           "Die Wände haben Gesichter."]),
    (0.75, ["Er ruft mich. Der Schläfer.", "Ich seh … die Barriere. Sie leuchtet.", "Die Stimmen beten mit mir.",
            "Er sieht mich. Er sieht mich an."]),
    (0.95, ["Das ist kein Gott …", "Seine Augen … sie brennen!", "Y'Berion, was hast du gesehen?",
            "Er erwacht. Er erwacht!"]),
]
SLEEPER_LANDINGS = ["Es ist vorbei. Ich glaub, es ist vorbei.", "Nie wieder Gurukraut.", "Der Schläfer … schläft. Gut so."]
POOLS = {"mindcap": (THOUGHT_POOLS, LANDINGS), "ember": (DESERT_POOLS, DESERT_LANDINGS),
         "sleeper": (SLEEPER_POOLS, SLEEPER_LANDINGS)}

# Said when Escape is pressed during a trip (the menu waits; a second Escape soon after opens it anyway).
ESCAPES = ["Ich glaube, im Moment sollte ich mich auf das Hier und Jetzt konzentrieren.",
           "Fortlaufen? Vor mir selbst? Keine gute Idee.", "Ausruhen kann ich mich später. Jetzt … das hier."]
# Said instead when the hero tries to talk to someone while the trip is too strong for it; never twice in a row.
REFUSALS = ["Nicht jetzt … sein Gesicht zerfließt.", "Mit dem red ich jetzt besser nicht.", "Der hat … drei Augen.",
            "Nee. Der guckt so komisch.", "Später. Wenn er wieder normal aussieht."]
BLOCK_ABOVE = 0.35        # above this intensity, conversations become the special trip dialogue
DUCK = 0.4                # the trip's music while a thought is spoken, so the hero carries over the drums
REFUSAL_PAUSE = 8.0       # seconds between two refusal thoughts
THOUGHT_GAP = 4.0         # seconds of quiet after a thought before the next one
DELIVERY = "rausch"
HERO_VOICE = "15"
SETTINGS = __import__("pathlib").Path(__file__).resolve().parent.parent / "dm_runtime" / "settings.json"


# The special trip dialogue: anyone but a guard who talks to the hero while the trip is strong, or whom he talks to,
# notices the state he is in. Their lines are voiced in every NPC voice (trip_voices.py), the hero's are distorted.
SPECIAL_OPENERS = ["Was ist denn mit dir los? Deine Augen sind ganz komisch.",
                   "Du schwankst ja wie ein Kahn im Sturm. Hast du was geraucht?",
                   "Bleib mir vom Leib. Du riechst nach Rauch und Ärger.",
                   "Hallo? Hörst du mich überhaupt?"]
SPECIAL_ANSWERS = ["Dein Gesicht … das schmilzt.", "Psst. Die Wände hören mit.", "Du hast so schöne … Farben."]
# And what he babbles depends on where the smoke takes him: the north's war drums or the desert's sand.
NORTH_ANSWERS = ["Hörst du auch die Trommeln?", "Ich muss nach Nordmar. Die Clans rufen mich.",
                 "Wo geht's hier nach Nordmar?", "Riechst du das? Schnee. Und Feuer."]
DESERT_ANSWERS = ["Ich bin ein Skorpion. Glaub ich.", "Der Sand … überall ist Sand.",
                  "Hast du meine Karawane gesehen?"]
SLEEPER_ANSWERS = ["Erwache!", "Der Schläfer ruft mich.", "Hast du den Mond gesehen? Er hat Augen."]
PROFILE_ANSWERS = {"nordmar": NORTH_ANSWERS, "kriegsgesang": NORTH_ANSWERS,
                   "skorpion": DESERT_ANSWERS, "skorpion_goa": DESERT_ANSWERS, "anrufung": SLEEPER_ANSWERS}
SPECIAL_CLOSERS = ["Geh nach Hause und schlaf deinen Rausch aus.", "Mit dir red ich, wenn du wieder klar bist.",
                   "Verschwinde, bevor dich die Miliz so sieht."]
SPECIAL_LAST = "Na gut …"
# Guards notice in their own tone, when the hero talks to them (one who stops him keeps his own words).
SPECIAL_GUARDS = {"openers": ["Du bist ja völlig zugedröhnt.", "Was hast du geraucht? Nein, sag's mir lieber nicht.",
                              "Steh gerade, wenn du mit der Stadtwache redest!"],
                  "closers": ["Geh mir aus den Augen, bevor ich dich einsperre.",
                              "Noch ein falscher Schritt, und du schläfst in der Kaserne.",
                              "Schlaf deinen Rausch aus. Woanders."]}
GUARD_GUILDS = ("GIL_PAL", "GIL_MIL")
# The voices citizens and guards speak in (as trip_voices voices their lines).
SPECIAL_VOICES_ALL = ["01", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "16", "17"]
GUARD_VOICES_ALL = ["01", "03", "04", "05", "06", "07", "08", "09", "11", "12", "13"]
# Whoever stands drinking (at a barrel, tankard in hand) has an opinion on mixing.
DRINKING = "ZS_STAND_DRINKING"
SPECIAL_DRINKERS = {"openers": ["Ich glaube, du solltest dich vom Bier lieber fernhalten. So wie du gerade aussiehst, "
                                "würde ich dir vom Mischkonsum abraten.",
                                "Noch eins? Nee, mein Freund. Du hattest schon was. Sieht man.",
                                "Du riechst nach Rauch und willst noch Bier? Mutig."],
                    "closers": ["Trink Wasser. Viel Wasser.", "Das Fass läuft nicht weg. Du hoffentlich schon.",
                                "Komm wieder, wenn du nur noch eins davon bist: durstig oder benebelt."]}
# People with their own reason to notice: whoever filled the pipe knows exactly what is going on.
# Bjarne (story 3's renamed citizen) smokes the war blend for his dead brother, and in the north one never smokes it
# alone: the second man bears witness. He speaks to the hero as that witness, only while he is Bjarne, so the same
# citizen in a game without the story stays a stranger. The brother goes unnamed: saves keep the story's older text.
SPECIAL_BY_NAME = {
    ("VLK_454_BUERGER", "Bjarne"): {
        "openers": ["Du hast gezogen. Gut. Siehst du sie? Die Alten, am Feuer?",
                    "Halt dich gerade. Die Trommeln schlagen für dich. Und für meinen Bruder."],
        "closers": ["Ich bezeug's. Du hast für ihn gezogen. Jetzt lauf.",
                    "Lauf, solang die Trommeln schlagen. Reden kannst du morgen."]},
}
SPECIAL_PEOPLE = {
    "VLK_456_ABUYIN": {"openers": ["Ich hab's dir ja gesagt. Ich hab's dir doch gesagt!",
                                   "Ich hab's dir ja gesagt, mein Freund. Langsam ziehen, hab ich gesagt."],
                       "closers": ["Setz dich, trink Wasser und lass den Rauch weiterziehen.",
                                   "Komm wieder, wenn du deinen Namen wieder weißt."]},
}


def special_graph(voice, rng, instance="", guard=False, profile=None, drinking=False, name=""):
    """A short dialogue for an NPC of this voice number: it notices, the hero babbles (of the trip's own region, if it
    has one), it sends him off."""
    answers = rng.sample(SPECIAL_ANSWERS + PROFILE_ANSWERS.get(profile, []), 3)
    own = (SPECIAL_BY_NAME.get((instance.upper(), name)) or SPECIAL_PEOPLE.get(instance.upper())
           or (SPECIAL_DRINKERS if drinking else SPECIAL_GUARDS if guard else {}))
    return {"voice": f"{int(voice):02d}", "start": "a", "nodes": {
        "a": {"line": rng.choice(own.get("openers", SPECIAL_OPENERS)),
              "choices": [{"text": text, "goto": "z", "delivery": DELIVERY, "repeat": True}  # babble never runs out
                          for text in answers]},
        "z": {"line": rng.choice(own.get("closers", SPECIAL_CLOSERS)),
              "choices": [{"text": SPECIAL_LAST, "ends": True, "delivery": DELIVERY}]}}}


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


def is_drinking(npc):
    """Whether this NPC stands drinking right now."""
    try:
        return bool(npc.in_state(DRINKING))
    except (AttributeError, RuntimeError, ValueError):
        return False


def is_guard(npc):
    """Whether this NPC is militia or a paladin, by the script's own guild numbers."""
    try:
        import gothic
        guilds = {gothic.daedalus.get(name) for name in GUARD_GUILDS}
    except (ImportError, AttributeError, RuntimeError, TypeError, KeyError):
        return False
    return getattr(npc, "guild", None) in guilds


# A trip that ends in a blackout: instead of landing, the screen goes black, the hero comes to somewhere else, hours
# later, in a bed (used quietly, without the sleep menu), and wakes sober. The bed is found by its scheme near the spot.
BLACKOUTS = {
    # An open bed upstairs in the Red Lantern: the one beside it is behind a door the hero cannot open alone.
    "skorpion_goa": {"bed": (2233.0, 97.0, -2556.0), "scheme": "BEDHIGH", "hour": 9,
                     "in_world": "NW_CITY_HABOUR_PUFF_ENTRANCE",   # the Red Lantern exists only in Khorinis
                     "wake": ["Wo … wo bin ich?", "Was ist das für ein Bett?", "Riecht nach billigem Parfüm …",
                              "Mein Kopf … was ist passiert?"],
         # On the way out, the house has a word for him: each once, as he passes them.
         "after": [{"npc": "VLK_435_NADJA", "voice": "16",
                    "line": "Komm vorbei, wann immer dir danach ist. Du warst … unterhaltsam."},
                   {"npc": "VLK_433_BROMOR", "voice": "07",
                    "line": "Eigentlich müsste ich dir die Nacht extra berechnen. Aber über das, was da oben passiert "
                            "ist, will ich so bald nicht reden. Lassen wir's gut sein."},
                   # Borka would stop him with his pitch to come in; to a guest on his way out he says this instead,
                   # and the hero answers. After that the pitch counts as heard: no stranger any more.
                   {"npc": "VLK_434_BORKA", "voice": "11", "instead_of": "DIA_BORKA_TROUBLE",
                    # and what he would say to someone still standing at his door: the goodbye is his last word
                    "also_heard": ["DIA_BORKA_SECOND_CHANCE", "DIA_BORKA_PISSOFF"],
                    "reply": "Schon gut, ich geh ja schon.",
                    "line": "Mein Auftrag ist es, hier Kundschaft reinzubringen. Aber dich … dich sehe ich lieber "
                            "wieder gehen."}]},
    # Y'Berion collapsed at the Invocation; the hero comes to in Adanos's temple, where Vatras prays at night and
    # preaches outside from five. No bed: he wakes on his feet before the altar. Vatras's first conversation is this.
    "anrufung": {"waypoint": "NW_CITY_MERCHANT_TEMPLE_IN", "in_world": "NW_CITY_MERCHANT_TEMPLE_IN", "hour": 6,
                 "wake": ["Wo bin ich … ein Tempel?", "Adanos? Warum ausgerechnet Adanos?",
                          "Mein Kopf … und warum knie ich hier?"],
                 "after": [{"npc": "VLK_439_VATRAS", "voice": "05", "converse": True,
                            "line": "Was auch immer du heute Nacht angebetet hast, mein Sohn: Adanos war es nicht.",
                            "reply": "Ich … hab nur was geraucht."},
                           # And this morning his sermon is on moderation, Adanos's balance; his own waits meanwhile.
                           # His own sermon (ZS_PREACH_VATRAS, only in his START routine) is put on hold by having
                           # him stand, and START given back after; in another routine there is nothing to hush.
                           {"npc": "VLK_439_VATRAS", "voice": "05", "near": 1500.0,
                            "hush": "ZS_PREACH_VATRAS", "resume": "START", "sermon": [
                               "Hört mich an, Bürger von Khorinis! Adanos lehrt uns das Gleichgewicht. In allen Dingen.",
                               "Wer nach dem Feuer greift, verbrennt sich. Wer nach den Sternen greift, der fällt.",
                               "Manch einer sucht in Rauch und Kraut, was ihm nur die Demut geben kann.",
                               "Ein Becher Wein ist Freude. Zehn sind Torheit. Und was manch einer in seine Pfeife "
                               "stopft … darüber schweige ich lieber.",
                               "Haltet Maß, Brüder und Schwestern, und Adanos wird euch Frieden schenken."]}]},
}
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


def thought_lines(thoughts=None):
    """Every line a trip may say, for voicing: the given thoughts or every pool, all landings, the refusals and the
    lines spoken on waking from a blackout."""
    if thoughts:
        ups = [text for _, text in thoughts]
    else:
        ups = [line for pools, _ in POOLS.values() for _, pool in pools for line in pool]
    wakes = [line for blackout in BLACKOUTS.values() for line in blackout["wake"]]
    return (ups + [line for _, landings in POOLS.values() for line in landings] + REFUSALS + ESCAPES + wakes
            + SPECIAL_ANSWERS + NORTH_ANSWERS + DESERT_ANSWERS + SLEEPER_ANSWERS + [SPECIAL_LAST])


def draw_thoughts(rng, style="mindcap"):
    """One line per stage, picked at random from the look's pools: this trip's thoughts on the way up."""
    return [(at, rng.choice(pool)) for at, pool in POOLS[style][0]]


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
        if npc is not None:
            gothic.dialog.unbind(npc)


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


# The town crier (VLK_406, voice 04) reads what the city saw of the hero's night, once, the next time the hero passes
# him, but not before two minutes have passed (he stands some 16 m from the pipes): his own reading waits (he
# announces in ZS_ANNOUNCE_HEROLD, only in his START routine) and comes back after.
HEROLD = {"npc": "VLK_406_HEROLD", "voice": "04", "near": 2000.0, "for": 3 * 3600.0, "wait": 120.0,
          "hush": "ZS_ANNOUNCE_HEROLD", "resume": "START"}
HEROLD_OPEN = "Hört, Bürger von Khorinis! Eine Bekanntmachung der Stadtwache!"
HEROLD_CLOSE = "Wer etwas weiß, melde sich bei der Miliz. Gezeichnet, die Stadtwache von Khorinis."
HEROLD_NEWS = {
    "north": ["Im Hafenviertel wurde ein Mann gesehen, der mit erhobener Faust gegen Orks anbrüllte, die nicht da "
              "waren.",
              "Er rief nach den Clans des Nordens und behauptete, es schneie. Es hat nicht geschneit."],
    "desert": ["Am Hafen kroch ein Fremder auf allen vieren und behauptete, er sei ein Skorpion. Zuletzt gesehen im "
               "Freudenhaus.",
               "Die Miliz erinnert daran: Das Stechen von Bürgern ist verboten. Auch mit dem Finger."],
    "sleeper": ["Im Hafen hat jemand den Schläfer angerufen. Laut. Mehrmals.",
                "Der Schläfer ist fort und bleibt es. Wer ihn dennoch ruft, zahlt der Stadt Strafe für Ruhestörung."],
    "other": ["Am Hafen wurde ein Mann gesehen, der mit den Farben an der Wand gesprochen hat.",
              "Die Wände von Khorinis antworten nicht. Bitte lasst sie in Ruhe."],
}


def herold_lines(region):
    """The crier's announcement after a trip of this region, as a waiting sermon."""
    return dict(HEROLD, sermon=[HEROLD_OPEN] + HEROLD_NEWS[region] + [HEROLD_CLOSE])


# Aftercare: after every trip, Abuyin (who fills the pipes) has a new topic in his own menu, beside his usual ones:
# he asks how the journey was, the hero tells, region by region. Once per trip, and gone after a load.
AFTERCARE_NPC = "VLK_456_ABUYIN"
AFTERCARE_VOICE = "13"
AFTERCARE_TOPIC = "trip:aftercare"
AFTERCARE_TITLE = "Wegen dem Kraut von vorhin …"
PROFILE_REGION = {"nordmar": "north", "kriegsgesang": "north", "skorpion": "desert", "skorpion_goa": "desert",
                  "anrufung": "sleeper"}
AFTERCARE = {
    "north": {"tell": ["Ich hab die Trommeln der Clans gehört.", "Kalt. Und laut. Und wunderschön."],
              "ask": "Die Clans des Nordens rauchen das vor der Schlacht. Hast du gekämpft?",
              "fight": ["Nur gegen einen Baum. Der Baum hat gewonnen.", "Ich glaub, ich hab einen Schneemann besiegt."],
              "sky": ["Grüne Lichter am Himmel. Und ein Mond, rot wie Blut."]},
    "desert": {"tell": ["Heiß. Ich war ein Skorpion. Glaub ich.", "Ich hab Dünen gesehen, wo keine sind."],
               "ask": "Der Skorpion aus dem Süden sticht jeden, der ihn unterschätzt. Hat er dich gestochen?",
               "fight": ["Mitten ins Herz.", "Nein. Ich hab zurückgestochen."],
               "sky": ["Er hat gebrannt. Der ganze Himmel."]},
    "sleeper": {"tell": ["Ich hab gebetet. Und etwas hat zurückgesehen.", "Ich hab den Schläfer gesehen."],
                "ask": "Den Schläfer? Mein Freund … manche Dinge sollte man nicht rufen. Hat er dir geantwortet?",
                "fight": ["Er hat mich angesehen. Das hat gereicht.",
                          "Ich bin bei Vatras aufgewacht. Das war Antwort genug."],
                "sky": ["Er war voller Sterne. Und voller Augen."]},
    "other": {"tell": ["Bunt. Sehr, sehr bunt.", "Die Wände haben geatmet."],
              "ask": "So ist es beim ersten Mal. Hast du dich verloren?",
              "fight": ["Nur ein bisschen.", "Ich weiß nicht mal mehr, wo ich angefangen hab."],
              "sky": ["Ich hab bis ans Ende der Welt gesehen."]},
}
AFTERCARE_OPEN = "Ah, mein Freund! Du lebst noch. Erzähl, wie war die Reise?"
# Said by Abuyin when a pipe he filled for the hero is freed of someone sitting at it (story.py keeps it reserved).
RESERVED_LINE = "Die Pfeife ist bestellt, Freund. Such dir heute eine andere."
AFTERCARE_SKY = "Und der Himmel? Man sagt, er öffnet sich, wenn das Kraut gut ist."
AFTERCARE_CLOSE = "Gut, gut. Komm wieder, wenn du bereit bist. Und nimm beim nächsten Mal kleinere Züge."
AFTERCARE_LAST = "Mach ich."
_aftercare = None   # (region, world generation) of the last trip, until talked about


# The three smokes: whoever has come through a trip gets a piece of a set from Abuyin at the end of the talk about
# it, made like the add-on's mana set (two rings and an amulet), so its own equip scripts and set bonus apply.
SMOKE_SET = {
    "north": {"item": "RAUCHRING_NORD", "like": "ITRI_ADDON_MANA_01", "name": "Ring des Nordrauchs",
              "rows": ["Kalt wie Schnee auf der Haut.", "Wer ihn trägt, hört Trommeln."], "tint": [0.6, 0.85, 1.0]},
    "desert": {"item": "RAUCHRING_SUED", "like": "ITRI_ADDON_MANA_02", "name": "Ring des Wüstenrauchs",
               "rows": ["Warm, als läge er in der Sonne.", "Ein Skorpion ist eingraviert."], "tint": [1.0, 0.6, 0.25]},
    "sleeper": {"item": "RAUCHAMULETT", "like": "ITAM_ADDON_MANA", "name": "Amulett des Mondrauchs",
                "rows": ["Kühl, selbst in der Hand.", "Es schimmert im Mondlicht."], "tint": [0.72, 0.62, 1.0]},
}
SMOKE_GIFT = {"north": "Hier. Wer den Rauch des Nordens überstanden hat, soll diesen Ring tragen.",
              "desert": "Nimm den. Wer den Skorpion übersteht, verdient einen Ring aus dem Süden.",
              "sleeper": "Und dies hier. Wer den Schläfer gesehen hat und davon erzählen kann, trägt den Mond."}
SMOKE_THANKS = "Danke, Abuyin."
SMOKE_MASTER_TOPIC = "trip:dreirauche"
SMOKE_MASTER_FLAG = "trip:rauchmeister"
SMOKE_MASTER_TITLE = "Ich hab jetzt alle drei Rauche geschmeckt."
SMOKE_MASTER = ["Zeig her. Nordrauch, Wüstenrauch, Mondrauch.",
                "Das hat in ganz Khorinis noch keiner geschafft, seit ich hier sitze.",
                "Du hast den Krieg der Clans gerochen, den Stich der Wüste gespürt und den Schläfer gesehen.",
                "Trag die drei zusammen, mein Freund. Wer sie erkennt, weiß, mit wem er raucht."]
SMOKE_MASTER_LAST = "Ich werd's mir merken."
# Who knows the smokes, when the hero wears the amulet: once each. (instance, name it must have or None, voice, lines,
# the hero's answer.) Bjarne and Kasim only while a story has made them so.
RECOGNISE_TITLE = "Was schaust du so auf mein Amulett?"
RECOGNISE = [
    ("VLK_449_LARES", None, "09", ["Das Amulett kenn ich nicht. Aber den Geruch daran.",
                                   "Im Neuen Lager hätten sie dir dafür Erz gegeben, Junge."], "Ich rauch nicht für Erz."),
    ("VLK_439_VATRAS", None, "05", ["Dieses Amulett riecht nach drei Nächten, die du besser verschlafen hättest.",
                                    "Adanos lehrt das Maß, mein Sohn. Vergiss das nicht."], "Ich halte Maß. Meistens."),
    ("VLK_454_BUERGER", "Bjarne", "01", ["Ha! Der Mann mit den drei Rauchen.",
                                         "Im Norden gäben sie dir am Feuer den ersten Platz."], "Den nehm ich gern."),
    ("VLK_455_BUERGER", "Kasim", "08", ["Du trägst den Wüstenrauch an der Hand.",
                                        "In Ishtar würden sie fragen, wer du bist. Ich frage nicht."], "Besser so."),
    ("VLK_498_IGNAZ", None, "14", ["Faszinierend! Drei Rauschmittel, drei Artefakte.",
                                   "Darf ich vielleicht … nein. Lieber nicht. Oder doch?"], "Lieber nicht, Ignaz."),
    ("DJG_705_ANGAR_NW", None, "04", ["Diesen Rauch kenne ich. So rochen die Nächte der Gurus.",
                                      "Du hast gesehen, was Y'Berion sah. Behalte es für dich."], "Ich weiß, was er sah."),
    # where nobody would expect it: Ulthar of the high council, strictest of the Fire Mages, who was young once too
    ("KDF_502_ULTHAR", None, "05", ["Diese Ringe. Und das Amulett. Komm näher.",
                                     "Ja. Das ist es. Nordrauch, Wüstenrauch, Mondrauch.",
                                     "Als ich jung war, noch vor dem Kloster, gab es einen Sommer, in dem …",
                                     "Nun. Innos vergibt die Torheiten der Jugend. Meistens.",
                                     "Kein Wort davon zu den Novizen."], "Kein Wort, Meister."),
]


# Wearing all three smokes, the hero is remarked on as he passes: some by name, any citizen and any guard in their
# own voice. Each person once a game day, and a breath between remarks, so it stays a remark and never chatter.
REMARK_NEAR = 450.0       # how close (cm) he passes
REMARK_GAP = 40.0         # seconds between two remarks
REMARKS_BY_NAME = {
    "VLK_456_ABUYIN": ("13", ["Da geht er, der Mann der drei Rauche."]),
    "VLK_431_KARDIF": ("14", ["Drei Rauche an einem Mann. Du verträgst sicher mehr als meine Gäste."]),
    "VLK_432_MOE": ("01", ["Du riechst nach drei Ländern auf einmal, Freundchen."]),
    "VLK_409_ZURIS": ("14", ["Ich verkauf dir den Tabak. Was du draus machst, will ich gar nicht wissen."]),
    "VLK_469_HALVOR": ("06", ["Lass dich mit den Ringen bloß nicht von der Miliz erwischen."]),
    # and where nobody would expect it
    "VLK_417_CONSTANTINO": ("10", ["Hmpf. Drei Rauche, und keiner davon aus meiner Werkstatt."]),
    "MIL_311_ANDRE": ("08", ["Ich weiß, was diese Ringe bedeuten. Und ich weiß, dass ich nichts weiß. Weiter."]),
}
REMARKS_CITIZEN = ["Ist das nicht der, von dem der Ausrufer erzählt hat?", "Riechst du das? Sumpf, Schnee und Wüste."]
REMARKS_GUARD = ["Drei Rauchringe. Ich hab dich im Auge."]
_remarked = {}            # instance -> game day of his remark
_remark_at = [0.0]


def smoke_set_worn(carried, pieces):
    """Whether all three smokes are worn at once."""
    return len(pieces) == len(SMOKE_SET) and all(carried.get(c, False) for c in pieces.values())


def remark_for(npc, rng):
    """(voice, line) someone says to a hero wearing the three smokes, or None."""
    instance = getattr(npc, "instance", "") or ""
    if instance in REMARKS_BY_NAME:
        voice, lines = REMARKS_BY_NAME[instance]
        return voice, rng.choice(lines)
    voice = f"{int(getattr(npc, 'voice', 0) or 0):02d}"
    if is_guard(npc) and voice in GUARD_VOICES_ALL:
        return voice, rng.choice(REMARKS_GUARD)
    if instance.startswith(("VLK_", "BAU_")) and voice in SPECIAL_VOICES_ALL:
        return voice, rng.choice(REMARKS_CITIZEN)
    return None


def tick_remarks(gothic, now, rng=random):
    """One remark from someone the hero passes while he wears the three smokes."""
    if now - _remark_at[0] < REMARK_GAP or _current is not None:
        return
    if gothic.dialog.partner() is not None or gothic.dialog.narrating():
        return
    pieces = smoke_set() if _story() is not None else {}
    if not smoke_set_worn(_carried(gothic), pieces):
        return
    day = gothic.world.day
    here = gothic.player.position
    for npc in gothic.world.npcs_near(REMARK_NEAR):
        instance = getattr(npc, "instance", "")
        if _remarked.get(instance) == day or not getattr(npc, "alive", True):
            continue
        said = remark_for(npc, rng)
        if said is None:
            continue
        from dm import voices
        wav, ms = voices.lookup(*said)
        if gothic.dialog.narrate(said[1], ms, wav):
            _remarked[instance] = day
            _remark_at[0] = now
        return


def _story():
    return getattr(sys.modules.get("dm.story"), "_story", None)


def smoke_set():
    """The set's carriers by region, defined once per game through the story layer (so they persist with the save
    and get carriers no other item has), or {} without a story."""
    story = _story()
    if story is None:
        return {}
    items = story.state.get("items", {})
    missing = [cfg for cfg in SMOKE_SET.values() if cfg["item"] not in items]
    if missing:
        story.apply_plan({"reason": "Die drei Rauche", "ops": [
            {"op": "define_item", "item": cfg["item"], "like": cfg["like"], "name": cfg["name"],
             "description": cfg["name"], "rows": [[r, 0] for r in cfg["rows"]],
             "look": {"tint": cfg["tint"], "strength": 0.65, "brighten": 1.15}} for cfg in missing]})
        items = story.state.get("items", {})
    return {region: items[cfg["item"]]["carrier"] for region, cfg in SMOKE_SET.items() if cfg["item"] in items}


def _carried(gothic):
    """{instance: equipped?} of what the hero carries."""
    player = getattr(gothic, "player", None)
    return {i["instance"]: i.get("equipped", False) for i in (getattr(player, "items", None) or [])}


def _flag(name):
    story = _story()
    return bool(story and story.state["flags"].get(name))


def aftercare_graph(region, gift=None):
    """Abuyin's questions about a trip, the hero's answers to choose from, and, if he does not have it yet, the
    piece of the set that belongs to this smoke (gift: its carrier)."""
    talk = AFTERCARE[region]
    last = {"text": AFTERCARE_LAST, "goto": "e"} if gift else {"text": AFTERCARE_LAST, "ends": True}
    nodes = {
        "a": {"line": AFTERCARE_OPEN, "choices": [{"text": t, "goto": "b"} for t in talk["tell"]]},
        "b": {"line": talk["ask"], "choices": [{"text": t, "goto": "c"} for t in talk["fight"]]},
        "c": {"line": AFTERCARE_SKY, "choices": [{"text": t, "goto": "d"} for t in talk["sky"]]},
        "d": {"line": AFTERCARE_CLOSE, "choices": [last]}}
    if gift:
        nodes["e"] = {"line": SMOKE_GIFT[region],
                      "choices": [{"text": SMOKE_THANKS, "ends": True, "gives": {"item": gift, "count": 1}}]}
    return {"voice": AFTERCARE_VOICE, "start": "a", "nodes": nodes}


def _speech(voice, lines, last, sets=None):
    """A graph of sentences one after another (as split_lines makes them) ending in the hero's one answer."""
    keys = [f"s{i}" for i in range(len(lines))]
    nodes = {}
    for i, key in enumerate(keys):
        node = {"line": lines[i], "choices": []}
        if i + 1 < len(keys):
            node.update(returns=keys[i + 1], chain=True)
        else:
            node["choices"] = [{"text": last, "ends": True}]
        nodes[key] = node
    if sets:
        nodes[keys[0]]["sets"] = sets
    return {"voice": voice, "start": keys[0], "nodes": nodes}


def extra_topics(gothic):
    """Topics the trips add to people's own menus, as {npc: [(key, title)]}; every npc listed, empty when none, so a
    topic talked about disappears again."""
    out = {AFTERCARE_NPC: []}
    if _pending_aftercare(gothic) is not None:
        out[AFTERCARE_NPC].append((AFTERCARE_TOPIC, AFTERCARE_TITLE))
    pieces = smoke_set() if _story() is not None else {}
    if len(pieces) == len(SMOKE_SET):
        carried = _carried(gothic)
        if all(c in carried for c in pieces.values()) and not _flag(SMOKE_MASTER_FLAG):
            out[AFTERCARE_NPC].append((SMOKE_MASTER_TOPIC, SMOKE_MASTER_TITLE))
        wearing = smoke_set_worn(carried, pieces)
        for instance, name, _voice, _lines, _last in RECOGNISE:
            out.setdefault(instance, [])
            if not wearing or _flag(f"trip:erkannt:{instance}"):
                continue
            npc = gothic.world.find_npc(instance)
            if npc is None or (name and getattr(npc, "name", "") != name):
                continue
            out[instance].append((f"trip:erkannt:{instance}", RECOGNISE_TITLE))
    return out


def _pending_aftercare(gothic=None):
    """The region of the trip Abuyin still has to hear about: from this session, else from the save's story state."""
    if _aftercare is not None and (gothic is None or _aftercare[1] == gothic.world.generation):
        return _aftercare[0]
    story = _story()
    return story.state.get("aftercare") if story is not None else None


def topic(key):
    """A trip topic's data when it is chosen, taken once; None if there is none (any more)."""
    global _aftercare
    region = _pending_aftercare() if key == AFTERCARE_TOPIC else None
    if region is not None:
        _aftercare = None
        story = _story()
        if story is not None:
            story.state.pop("aftercare", None)
        gift = smoke_set().get(region)
        if gift:
            import gothic
            if gift in _carried(gothic):
                gift = None             # he has this smoke's piece already
        return {"title": AFTERCARE_TITLE, "graph": aftercare_graph(region, gift)}
    if key == SMOKE_MASTER_TOPIC and not _flag(SMOKE_MASTER_FLAG):
        return {"title": SMOKE_MASTER_TITLE,
                "graph": _speech(AFTERCARE_VOICE, SMOKE_MASTER, SMOKE_MASTER_LAST, [SMOKE_MASTER_FLAG])}
    if key.startswith("trip:erkannt:") and not _flag(key):
        for instance, _name, voice, lines, last in RECOGNISE:
            if key == f"trip:erkannt:{instance}":
                return {"title": RECOGNISE_TITLE, "graph": _speech(voice, lines, last, [key])}
    return None


def after_lines():
    """Every line said after a blackout, by voice, for voicing: the speakers' and the hero's replies."""
    said = [line for b in BLACKOUTS.values() for line in b.get("after", [])]
    said += [herold_lines(region) for region in HEROLD_NEWS]
    care = [(AFTERCARE_VOICE, AFTERCARE_OPEN), (AFTERCARE_VOICE, AFTERCARE_SKY), (AFTERCARE_VOICE, AFTERCARE_CLOSE),
            (AFTERCARE_VOICE, RESERVED_LINE), (HERO_VOICE, SMOKE_THANKS), (HERO_VOICE, SMOKE_MASTER_TITLE),
            (HERO_VOICE, SMOKE_MASTER_LAST), (HERO_VOICE, RECOGNISE_TITLE)]
    care += [(AFTERCARE_VOICE, line) for line in list(SMOKE_GIFT.values()) + SMOKE_MASTER]
    for _instance, _name, voice, lines, last in RECOGNISE:
        care += [(voice, line) for line in lines] + [(HERO_VOICE, last)]
    for voice, lines in REMARKS_BY_NAME.values():
        care += [(voice, line) for line in lines]
    care += [(v, line) for v in SPECIAL_VOICES_ALL for line in REMARKS_CITIZEN]
    care += [(v, line) for v in GUARD_VOICES_ALL for line in REMARKS_GUARD]
    care += [
            (HERO_VOICE, AFTERCARE_TITLE), (HERO_VOICE, AFTERCARE_LAST)]
    for talk in AFTERCARE.values():
        care += [(AFTERCARE_VOICE, talk["ask"])] + [(HERO_VOICE, t) for t in talk["tell"] + talk["fight"] + talk["sky"]]
    return (care + [(line["voice"], line["line"]) for line in said if "line" in line]
            + [(line["voice"], text) for line in said for text in line.get("sermon", [])]
            + [(HERO_VOICE, line["reply"]) for line in said if line.get("reply")])


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
                    story.state["aftercare"] = _aftercare[0]   # kept in the save: a restart does not lose the talk
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
