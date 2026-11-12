"""What comes after a trip, through the story layer: Abuyin's aftercare topic, the three smokes he gives, who
recognises them and who remarks on them. trip re-exports every name here and registers itself with the story layer,
so these are its hooks (extra_topics, topic, made_way); the state they read and change (_aftercare, _current,
_remarked, _remark_at) belongs to trip and is reached through it, so there is one of each."""

import random
import sys

from dm.trip_lines import (BLACKOUTS, GUARD_VOICES_ALL, HERO_VOICE, HEROLD_NEWS, SPECIAL_VOICES_ALL, herold_lines,
                           is_guard)


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


def made_way(key, evicted):
    """Someone got up from a pipe kept for the hero: Abuyin, if he is near, says it was ordered (story.py keeps it)."""
    import gothic
    from dm import story
    abuyin = gothic.world.find_npc(AFTERCARE_NPC)
    here = gothic.player.position
    if abuyin is not None and sum((a - b) ** 2 for a, b in zip(here, abuyin.position)) < 2000 ** 2:
        story.narrate_later(RESERVED_LINE, AFTERCARE_VOICE)


AFTERCARE_SKY = "Und der Himmel? Man sagt, er öffnet sich, wenn das Kraut gut ist."
AFTERCARE_CLOSE = "Gut, gut. Komm wieder, wenn du bereit bist. Und nimm beim nächsten Mal kleinere Züge."
AFTERCARE_LAST = "Mach ich."


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
    # Vatras, who will one day ask for swampweed for the Eye of Innos and never say what for
    ("VLK_439_VATRAS", None, "05", ["Dieses Amulett riecht nach drei Nächten, die du besser verschlafen hättest.",
                                    "Adanos lehrt das Maß, mein Sohn.",
                                    "Und solltest du mir eines Tages Sumpfkraut bringen müssen … frag nicht, wofür."],
     "Ich frag nicht."),
    ("VLK_454_BUERGER", "Bjarne", "01", ["Ha! Der Mann mit den drei Rauchen.",
                                         "Im Norden gäben sie dir am Feuer den ersten Platz."], "Den nehm ich gern."),
    ("VLK_455_BUERGER", "Kasim", "08", ["Du trägst den Wüstenrauch an der Hand.",
                                        "In Ishtar würden sie fragen, wer du bist. Ich frage nicht."], "Besser so."),
    ("VLK_498_IGNAZ", None, "14", ["Faszinierend! Drei Rauschmittel, drei Artefakte.",
                                   "Darf ich vielleicht … nein. Lieber nicht. Oder doch?"], "Lieber nicht, Ignaz."),
    ("DJG_705_ANGAR_NW", None, "04", ["Diesen Rauch kenne ich. So rochen die Nächte der Gurus.",
                                      "Du hast gesehen, was Y'Berion sah. Behalte es für dich."], "Ich weiß, was er sah."),
    # the city's alchemist knows what is in each blend, and sells something for the morning after
    ("VLK_417_CONSTANTINO", None, "10", ["Zeig mal her. Hm. Schwefel, Sumpfkraut und … das ist doch Feuernessel.",
                                         "Wenn du schon Zeug rauchst, das du nicht verstehst, dann komm wenigstens zu "
                                         "einem, der weiß, was er mischt.",
                                         "Ich hätte da übrigens was gegen Kopfschmerzen. Kostet aber."],
     "Ich komm drauf zurück."),
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
    "VLK_417_CONSTANTINO": ("10", ["Hmpf. Drei Rauche, und keiner davon aus meiner Werkstatt.",
                                   "Drei Rauche. Und dann wundert man sich über Kopfschmerzen."]),
    "MIL_311_ANDRE": ("08", ["Ich weiß, was diese Ringe bedeuten. Und ich weiß, dass ich nichts weiß. Weiter."]),
}
REMARKS_CITIZEN = ["Ist das nicht der, von dem der Ausrufer erzählt hat?", "Riechst du das? Sumpf, Schnee und Wüste."]
REMARKS_GUARD = ["Drei Rauchringe. Ich hab dich im Auge."]


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
    from dm import trip   # its state: trip owns it
    if now - trip._remark_at[0] < REMARK_GAP or trip._current is not None:
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
        if trip._remarked.get(instance) == day or not getattr(npc, "alive", True):
            continue
        said = remark_for(npc, rng)
        if said is None:
            continue
        from dm import voices
        wav, ms = voices.lookup(*said)
        if gothic.dialog.narrate(said[1], ms, wav):
            trip._remarked[instance] = day
            trip._remark_at[0] = now
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


AFTERCARE_FLAG = "trip:aftercare:"   # + region: the talk Abuyin still owes, a flag in the story's log


def _pending_aftercare(gothic=None):
    """The region of the trip Abuyin still has to hear about: from this session, else from the save's story flags."""
    from dm import trip   # its state: trip owns it
    if trip._aftercare is not None and (gothic is None or trip._aftercare[1] == gothic.world.generation):
        return trip._aftercare[0]
    story = _story()
    if story is None:
        return None
    return next((r for r in AFTERCARE if story.state["flags"].get(f"{AFTERCARE_FLAG}{r}")), None)


def topic(key):
    """A trip topic's data when it is chosen, taken once; None if there is none (any more)."""
    from dm import trip   # its state: trip owns it
    region = _pending_aftercare() if key == AFTERCARE_TOPIC else None
    if region is not None:
        trip._aftercare = None
        story = _story()
        if story is not None and story.state["flags"].get(f"{AFTERCARE_FLAG}{region}"):
            story.player_flag(f"{AFTERCARE_FLAG}{region}", False)
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
