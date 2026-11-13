"""What people say about the weather as the hero passes (docs/plan-weather.md), as the trips' remarks in passing:
a line with a subtitle in the speaker's own voice, a person at most once per spell of weather, and a breath between
two remarks so it stays a remark and never chatter. Now and then the hero says something himself.

Every line is our own words. Voices are baked once for every voice that speaks them:
    python3 python/dm/weather_talk.py graphs > python/dm_runtime/newgame/graphs_weather.json
"""

import json
import sys

REMARK_NEAR = 500.0      # cm: how close he passes
REMARK_GAP = 75.0        # seconds between two remarks of anyone
HERO_GAP = 420.0         # seconds between two of the hero's own
HERO_CHANCE = 0.25       # of a look in bad weather, once his gap is over
THUNDER_WINDOW = 7.0     # seconds after a flash in which people speak of it
AFTER_RAIN = 300.0       # seconds after the rain in which people are glad it stopped
HERO_VOICE = "15"
VOICES = ["01", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "16", "17"]

GENERIC = {
    "snow": ["Arschkalt ist das.", "Schnee. Ausgerechnet jetzt.", "Mir frieren gleich die Finger ab."],
    "rain": ["Scheißregen.", "Bei dem Wetter jagt man keinen Hund vor die Tür.", "Ich bin nass bis auf die Knochen."],
    "storm": ["Das wird ein Unwetter.", "Hörst du den Wind? Da kommt noch was."],
    "thunder": ["Innos zürnt heut wieder.", "Das hat irgendwo eingeschlagen."],
    "after": ["Endlich hört's auf.", "Na also. Der Regen ist durch."],
    "heat": ["Was für eine Hitze.", "Bei der Hitze krieg ich keinen Bissen runter.", "Ich brauch was zu trinken.",
             "Mir läuft der Schweiß in die Stiefel.", "Nicht mal im Schatten hält man's aus.",
             "Heut geht kein Lüftchen.", "Bei der Hitze arbeitet doch keiner.", "Das Bier wird warm, bevor man's trinkt."],
    "fog": ["Man sieht ja die Hand vor Augen nicht.", "Bei dem Nebel verläuft man sich noch.",
            "Wer weiß, was da im Nebel rumschleicht."],
}
# Who they are colours it: farmers think of the fields, mercenaries of the watch, townsfolk of the mud.
BY_GROUP = {
    "BAU": {"rain": ["Wenn's so weitergeht, säuft uns das Feld ab."],
            "snow": ["Bleibt das liegen, erfrieren uns die Rüben."],
            "fog": ["Bei dem Nebel find ich meine Schafe nicht wieder."],
            "heat": ["Wenn's nicht bald regnet, verdorrt uns alles.", "Der Brunnen gibt kaum noch was her.",
                     "Die Schafe liegen nur noch im Schatten."]},
    "SLD": {"rain": ["Und ich darf heut Nacht Wache stehen. Großartig."],
            "snow": ["Für so ein Wetter zahlt Onar nicht genug."],
            "fog": ["Im Nebel sieht man keinen Banditen kommen."],
            "heat": ["In der Rüstung kocht man bei der Hitze.", "Bei der Hitze schlag ich mich mit keinem."]},
    "VLK": {"rain": ["Die ganze Gasse ist nur noch Matsch."],
            "snow": ["Wenn das so bleibt, wird das Holz teuer."],
            "fog": ["Bei dem Nebel bleiben die Leute zu Hause."],
            "heat": ["Bei der Hitze stinkt der ganze Hafen.", "Der Fisch auf dem Markt ist schon wieder hin."]},
    "MIL": {"rain": ["Die Rüstung rostet mir, und keiner zahlt's."],
            "heat": ["Wache stehen bei der Hitze. Das ist doch eine Strafe."]},
    "PAL": {"rain": ["Die Rüstung rostet mir, und keiner zahlt's."],
            "heat": ["In der Rüstung kocht man bei der Hitze."]},
    "NOV": {"rain": ["Auch der Regen kommt von Innos, sagen die Magier."],
            "heat": ["Innos' Sonne brennt heute besonders heilig."]},
    "KDF": {"rain": ["Auch der Regen kommt von Innos."],
            "heat": ["Innos prüft uns mit seiner Sonne."]},
}
HERO = {
    "snow": ["Hätt ich mal 'nen Mantel.", "Verdammt kalt hier."],
    "rain": ["Na toll. Klatschnass.", "Ich such mir besser ein Dach."],
    "storm": ["Das ist kein Wetter, das ist ein Strafgericht."],
    "thunder": ["Das war nah."],
    "heat": ["Die Sonne brennt einem das Hirn weg.", "Ein Schluck Wasser wär jetzt was.",
             "Ich such mir besser Schatten.", "Mir klebt alles am Leib."],
    "fog": ["Hier sieht man ja gar nichts.", "Nebel. Das hat mir noch gefehlt."],
}

_said = {}            # instance -> the spell of weather he already spoke in
_state = {"remark_at": -1e9, "hero_at": -1e9, "flash_at": -1e9, "rain_ended_at": -1e9, "was_rain": False}


def flashed(now):
    """The climate calls this when lightning struck, so people can speak of it."""
    _state["flash_at"] = now


def category(state, now):
    """What the weather gives people to say now, or None."""
    kind, intensity = state.get("kind"), state.get("intensity", 0.0)
    raining = kind == "rain" and intensity > 0.2
    if _state["was_rain"] and not raining:
        _state["rain_ended_at"] = now
    _state["was_rain"] = raining
    if raining and now - _state["flash_at"] < THUNDER_WINDOW:
        return "thunder"
    if kind in ("rain", "snow") and intensity > 0.2:
        wx, wz = state.get("wind", (0, 0))
        if intensity > 0.75 or (wx * wx + wz * wz) ** 0.5 > 4.0:
            return "storm"
        return kind
    # Fog where nothing falls: thick enough to speak of. (Rain or snow in fog is talked about as rain or snow.)
    if state.get("heat", 0.0) > 0.4:
        return "heat"
    if state.get("fog", 0.0) > 0.3:
        return "fog"
    if now - _state["rain_ended_at"] < AFTER_RAIN and state.get("wet", 0) > 0.2:
        return "after"
    return None


def lines_for(instance, voice, what, base_kind):
    """The lines someone of this group and voice may say about this weather."""
    if voice not in VOICES:
        return []
    group = instance.split("_")[0]
    # their own lines speak of weather that is falling now: not of rain that has stopped, nor in a thunderclap
    own = BY_GROUP.get(group, {}).get(base_kind, []) if what in ("rain", "snow", "storm", "fog", "heat") else []
    return GENERIC.get(what, []) + own


def spell(state, day, hour, what=None):
    """One spell of weather: the same kind in the same three hours (fog counts as its own kind)."""
    kind = what if what in ("fog", "heat") else state.get("kind")
    return f"{kind}-{day}-{int(hour) // 3}"


def tick(gothic, now, rng):
    """At most one remark: someone the hero passes, or now and then the hero himself."""
    if not hasattr(gothic, "weather") or not hasattr(gothic.weather, "state"):
        return None
    state = gothic.weather.state()
    what = category(state, now)
    if what is None or now - _state["remark_at"] < REMARK_GAP:
        return None
    if gothic.dialog.partner() is not None or gothic.dialog.narrating():
        return None
    from dm import voices
    hour, _ = gothic.world.time
    current = spell(state, gothic.world.day, hour, what)
    base_kind = what if what in ("fog", "heat") else (state.get("kind") if state.get("kind") in ("rain", "snow") else "rain")
    for npc in gothic.world.npcs_near(REMARK_NEAR):
        instance = getattr(npc, "instance", "") or ""
        if _said.get(instance) == current or not getattr(npc, "alive", True) or instance.startswith("PC_"):
            continue
        voice = f"{int(getattr(npc, 'voice', 0) or 0):02d}"
        choices = lines_for(instance, voice, what, base_kind)
        if not choices:
            continue
        text = rng.choice(choices)
        wav, ms = voices.lookup(voice, text)
        if gothic.dialog.narrate(text, ms, wav):
            _said[instance] = current
            _state["remark_at"] = now
            return voice, text
        return None
    if now - _state["hero_at"] > HERO_GAP and rng.random() < HERO_CHANCE and HERO.get(what):
        text = rng.choice(HERO[what])
        wav, ms = voices.lookup(HERO_VOICE, text)
        if gothic.dialog.narrate(text, ms, wav):
            _state["hero_at"] = _state["remark_at"] = now
            return HERO_VOICE, text
    return None


def graphs():
    """Every line in every voice that may say it, for bake_voices.py."""
    out = {}
    for voice in VOICES:
        lines = [t for group in GENERIC.values() for t in group]
        for group, by_kind in BY_GROUP.items():
            lines += [t for ts in by_kind.values() for t in ts]
        out[f"weather__{voice}"] = {"voice": voice, "narration": sorted(set(lines))}
    out["weather__hero"] = {"voice": HERO_VOICE, "narration": sorted({t for ts in HERO.values() for t in ts})}
    return out


_next_look = 0.0


def _tick(_dt):
    global _next_look
    import random
    import time
    import gothic
    now = time.monotonic()
    if now < _next_look:
        return
    _next_look = now + 2.0
    try:
        gothic.world.day
    except RuntimeError:
        return
    tick(gothic, now, random)


def start():
    """Safe to call repeatedly."""
    import gothic
    if getattr(gothic, "_dm_weather_talk_registered", False):
        return
    gothic.on_tick(_tick)
    gothic._dm_weather_talk_registered = True


if __name__ == "__main__":
    if sys.argv[1:] == ["graphs"]:
        print(json.dumps(graphs(), ensure_ascii=False, indent=1))
    else:
        raise SystemExit(__doc__)
