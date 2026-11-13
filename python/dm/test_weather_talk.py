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
