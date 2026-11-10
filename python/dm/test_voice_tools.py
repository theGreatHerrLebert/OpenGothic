"""Voice tool tests: the game-audio decoder, resampling, which voices a story needs, and that packs hold no audio.
Run: python3 python/dm/test_voice_tools.py"""

import array
import json
import pathlib
import struct
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import bake_voices as b  # noqa: E402
from dm import library, make_pack  # noqa: E402


def wav(kind, rate, bits, block_align, data):
    fmt = struct.pack("<HHIIHH", kind, 1, rate, rate * 2, block_align, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


# one IMA ADPCM block: start at 100 with step index 0; nibble 0 changes nothing, nibble 7 adds 1+3+7
block = struct.pack("<hBB", 100, 0, 0) + bytes([0x00, 0x07, 0x00, 0x00])
decoded = b._ima_adpcm(block, 8)
assert list(decoded[:3]) == [100, 100, 100] and decoded[3] == 111 and len(decoded) == 9

pcm = array.array("h", [1000] * 4410).tobytes()
out = array.array("h", b._pcm24k(wav(1, 44100, 16, 2, pcm)))
assert len(out) == 2400                                   # 0.1 s at the reference rate
assert all(abs(v - 1000) < 30 for v in out[40:-40])         # a steady signal stays steady away from the edges
try:
    b._pcm24k(b"not audio")
    raise AssertionError("accepted junk")
except ValueError:
    pass

graphs = {"a": {"voice": "05", "start": "x", "nodes": {"x": {"line": "Hallo.", "delivery": "drohend",
                                                            "choices": [{"text": "Ja.", "ends": True}]}}},
          "n": {"voice": "10", "narration": ["Es war einmal."]}}
assert b.needed_voices(graphs) == ["05_drohend", "10", "15"]  # the hero answers in voice 15

assert make_pack.slug("Der heilige Hering") == "der-heilige-hering" and make_pack.slug("Über Öl!") == "ueber-oel"

with tempfile.TemporaryDirectory() as d:
    root = pathlib.Path(d)
    (root / "stories").mkdir()
    library.EXPERIMENT = root
    library.STAGE_FILE = root / "stages.json"
    make_pack.PACKS = root / "packs"
    story = {"title": "Der Probefall", "premise": "p", "hidden_truth": "t", "plot": {}, "plan": [],
             "conversations": {"VLK_1_A": graphs["a"]}}
    (root / "stories" / "s9_9.json").write_text(json.dumps(story), encoding="utf-8")
    (root / "graphs.json").write_text(json.dumps({"s9_9__VLK_1_A": graphs["a"]}), encoding="utf-8")
    path, names, lines = make_pack.build("Der Probefall")
    assert names == ["der-probefall/story.json", "der-probefall/graphs.json", "der-probefall/LIESMICH.md"]
    with zipfile.ZipFile(path) as pack:
        packed = json.loads(pack.read("der-probefall/graphs.json"))
        everything = b"".join(pack.read(n) for n in pack.namelist())
    assert list(packed) == ["der-probefall__VLK_1_A"]
    assert b"s9_9" not in everything                         # the file name says where a story came from
    assert lines == 2
print("ok")
