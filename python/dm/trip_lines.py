"""What the trips say: the hero's thoughts, his babble and the people's answers while he is high, what the
blackouts say on waking and after, and the town crier's news. Pure data and a few small helpers over it; the effect
engine (trip.py) and the aftercare (trip_aftercare.py) use them, and trip re-exports every name here."""


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
DELIVERY = "rausch"
HERO_VOICE = "15"


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
