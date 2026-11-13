"""Remarks about the weather against a fake game."""
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
fake = types.ModuleType("gothic")
sys.modules["gothic"] = fake
from dm import voices, weather_talk as wt  # noqa: E402

voices.lookup = lambda voice, text: ("x.wav", 1000)
said = []
dialog = types.SimpleNamespace(partner=lambda: None, narrating=lambda: False,
                               narrate=lambda text, ms, wav: said.append(text) or True)
farmer = types.SimpleNamespace(instance="BAU_901_BAUER", voice=13, alive=True)
weather = {"kind": "rain", "intensity": 0.5, "wind": (0, 0), "wet": 0.4}
fake.weather = types.SimpleNamespace(state=lambda: weather)
fake.dialog = dialog
fake.world = types.SimpleNamespace(day=3, time=(14, 0), npcs_near=lambda r: [farmer])
first = types.SimpleNamespace(choice=lambda xs: xs[-1], random=lambda: 0.0)

# Rain: the farmer thinks of his field; once per spell, and nothing within the gap.
assert wt.category(weather, 0.0) == "rain"
assert wt.tick(fake, 100.0, first) == ("13", "Wenn's so weitergeht, säuft uns das Feld ab.")
assert wt.tick(fake, 101.0, first) is None                    # the gap
said.clear()
wt.tick(fake, 300.0, first)                                    # same spell: he has spoken; the hero may
assert said == ["Ich such mir besser ein Dach."], said
# Heavy rain is a storm; a flash makes it thunder; when it stops, people are glad.
weather["intensity"] = 0.9
assert wt.category(weather, 400.0) == "storm"
wt.flashed(401.0)
assert wt.category(weather, 402.0) == "thunder"
weather.update(kind="clear", intensity=0.0)
assert wt.category(weather, 410.0) == "after"
assert wt.category(weather, 410.0 + wt.AFTER_RAIN + 1) is None
# Fog with nothing falling is fog; a farmer thinks of his sheep; rain in fog stays rain.
assert wt.category({"kind": "clear", "intensity": 0.0, "fog": 0.6, "wet": 0.0}, 2000.0) == "fog"
assert "Bei dem Nebel find ich meine Schafe nicht wieder." in wt.lines_for("BAU_1", "13", "fog", "fog")
assert wt.category({"kind": "rain", "intensity": 0.5, "fog": 0.6}, 2001.0) == "rain"
assert wt.spell({"kind": "clear"}, 3, 7, "fog") == "fog-3-2"
# A hot day with nothing falling is heat, and the farmer fears for his fields.
assert wt.category({"kind": "clear", "intensity": 0.0, "heat": 0.8, "fog": 0.0}, 2002.0) == "heat"
assert wt.category({"kind": "clear", "intensity": 0.0, "heat": 0.8, "fog": 0.0}, 2003.0, 23) == "night"  # the warm night
assert wt.category({"kind": "clear", "intensity": 0.0, "heat": 0.8, "fog": 0.0, "overcast": 0.4}, 2003.5, 23) is None  # clouded
assert wt.category({"kind": "clear", "intensity": 0.0, "heat": 0.1, "fog": 0.0}, 2003.6, 23) is None   # a mild night
assert wt.category({"kind": "clear", "intensity": 0.0, "heat": 0.8, "fog": 0.0}, 2003.7, 20) is None   # not yet
assert "Bei so einer Nacht steh ich gern Wache." in wt.lines_for("SLD_1", "13", "night", "night")
assert "Wenn's nicht bald regnet, verdorrt uns alles." in wt.lines_for("BAU_1", "13", "heat", "heat")
# Nobody is spoken for in a voice that was never baked, nor during a conversation.
assert wt.lines_for("BAU_1", "02", "rain", "rain") == []
assert "Wenn's so weitergeht, säuft uns das Feld ab." not in wt.lines_for("BAU_1", "13", "after", "rain")
dialog.partner = lambda: farmer
weather.update(kind="snow", intensity=0.5)
assert wt.tick(fake, 900.0, first) is None
# Every line in the bake graphs.
g = wt.graphs()
assert "Arschkalt ist das." in g["weather__07"]["narration"] and g["weather__hero"]["voice"] == "15"
print("weather talk ok")

# Magical weather comes before anything ordinary: a crystal storm after rain is not relief, fire strikes are not thunder.
wt._state.update(was_rain=True, flash_at=4000.0)
assert wt.category({"kind": "crystal", "intensity": 0.8, "wet": 0.9}, 4000.5) == "crystal"
assert wt.category({"kind": "fire", "intensity": 0.8}, 4001.0) == "fire"
assert wt.category({"kind": "motes", "intensity": 0.5}, 4002.0) == "magic"
assert wt.category({"kind": "clear", "intensity": 0.0, "fog": 0.6, "fog_tint": (0.7, 0.4, 1.0)}, 4003.0) == "magic"
assert wt.category({"kind": "clear", "intensity": 0.0, "fog": 0.6, "fog_tint": (1.0, 1.0, 1.0)}, 4004.0) == "fog"
assert "Wasser! Holt Wasser!" in wt.lines_for("VLK_1", "13", "fire", "fire")
assert wt.spell({"kind": "fire"}, 3, 14, "fire") == "fire-3-4"
assert "Der Himmel brennt!" in wt.graphs()["weather__13"]["narration"]
print("weather talk magic ok")

# The earthy lines by who says them: rough men and women, each only in their own voices.
assert "Ich frier mir echt die Eier ab." in wt.lines_for("SLD_1", "13", "snow", "snow")
assert "Ich frier mir echt die Eier ab." not in wt.lines_for("KDF_1", "13", "snow", "snow")
assert "Ich frier mir echt die Eier ab." not in wt.lines_for("VLK_414_HANNA", "17", "snow", "snow")
assert "Ich glaub, heut klimpert's beim Pinkeln." in wt.lines_for("VLK_414_HANNA", "17", "snow", "snow")
assert "Ich glaub, heut klimpert's beim Pinkeln." not in wt.lines_for("VLK_1", "13", "snow", "snow")
g = wt.graphs()
assert "Ich glaub, heut klimpert's beim Pinkeln." in g["weather__16"]["narration"]
assert "Ich glaub, heut klimpert's beim Pinkeln." not in g["weather__13"]["narration"]
assert "Ich frier mir echt die Eier ab." not in g["weather__17"]["narration"]
print("weather talk earthy ok")
