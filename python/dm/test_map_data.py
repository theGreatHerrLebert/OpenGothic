"""Map data tests: numbers the decompiler printed as names, routines, and map pages. Run: python3 python/dm/test_map_data.py"""

import pathlib
import struct
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import map_data as m  # noqa: E402

# an integer equal to a symbol's index comes out as that symbol's name
symbols = {"DIA_SOMETHING_EXIT": 28000}
assert m._number("-DIA_SOMETHING_EXIT", symbols) == -28000
assert m._number("50500", symbols) == 50500 and m._number("-42500", symbols) == -42500

records = [{"do": 'TA_STAND_DRINKING(20, 0, 1, 30, "NW_PUB")'}, {"do": 'TA_SLEEP(1, 30, 20, 0, "NW_BED")'},
           {"do": "NPC_DEFAULT()"}, {"do": 'TA_SIT_BENCH(8, 0, 9, 0, "NOWHERE")'}]
entries = m.schedule(records, {"NW_PUB": (10, -20), "NW_BED": (30, 40)})
assert [(e["activity"], e["from"], e["to"], e["x"]) for e in entries] == [
    ("STAND_DRINKING", 1200, 90, 10), ("SLEEP", 90, 1200, 30), ("SIT_BENCH", 480, 540, None)]  # unknown spots stay unplaced

calls = {"STARTUP_A": [{"do": "STARTUP_A_PART()"}, {"do": 'WLD_INSERTNPC(X, "WP1")'}],
         "STARTUP_A_PART": [{"do": 'WLD_INSERTNPC(Y, "WP2")'}, {"do": "STARTUP_A()"}],  # cycles do not loop
         }
folded = m.calls_in("STARTUP_A", lambda name: calls.get(name, []))
assert [r["do"] for r in folded] == ['WLD_INSERTNPC(Y, "WP2")', 'WLD_INSERTNPC(X, "WP1")']

# "run this chapter block once" guards are no condition; real ones are kept
assert m.conditions({"if": ["(ENTERNW_KAPITEL3 == FALSE)", "NPC_ISDEAD(X)"]}) == ["NPC_ISDEAD(X)"]
assert m.conditions({"if": ["(ENTERNW_KAPITEL3 == FALSE)"]}) == [] and m.conditions({}) == []
assert m.REMOVE.match("B_REMOVENPC(LOTHAR)")[1] == "LOTHAR" and m.REMOVE.match("B_KILLNPC(X)")
assert m.ALIAS.match("BENNET = HLP_GETNPC(SLD_809_BENNET)").groups() == ("BENNET", "SLD_809_BENNET")

# a world without a map gets one from the bounds of its waypoints, kept to their proportions
stand_in = m.schematic("ISLAND.ZEN", {"A": (0, 0), "B": (1000, 2000)}, width=100, margin=0)
assert (stand_in["left"], stand_in["right"], stand_in["top"], stand_in["bottom"]) == (0, 1000, 2000, 0)
assert stand_in["height"] == 200 and stand_in["schematic"] and m.schematic("EMPTY.ZEN", {}) is None

# a 2×1 TGA, bottom row first, blue-green-red-alpha
tga = bytes([0, 0, 2]) + bytes(9) + struct.pack("<HHBB", 2, 1, 32, 8) + bytes([255, 0, 0, 255, 0, 255, 0, 128])
png, width, height = m.tga_to_png(tga)
assert (width, height) == (2, 1) and png.startswith(b"\x89PNG")
idat = png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8]
assert zlib.decompress(idat) == bytes([0, 0, 0, 255, 255, 0, 255, 0, 128])  # filter byte, then RGBA
print("ok")
