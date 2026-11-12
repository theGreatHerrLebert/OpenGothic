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

# takes: re-sampling never overwrites; only choosing changes what the game plays
with tempfile.TemporaryDirectory() as d:
    saved = (b.voices.VOICE_DIR, b.voices.REF_DIR, b.JOBS)
    b.voices.VOICE_DIR, b.voices.REF_DIR, b.JOBS = pathlib.Path(d), pathlib.Path(d) / "refs", pathlib.Path(d) / "jobs"
    b.voices.REF_DIR.mkdir()
    b._write_mono(b.voices.REF_DIR / "05.wav", array.array("h", [3000, -3000] * 200).tobytes())

    class Model:  # writes a quiet tone, so every take is a valid recording
        def __init__(self):
            self.spoken = 0

        def speak(self, text, reference, target):
            self.spoken += 1
            b._write_mono(target, array.array("h", [100 * self.spoken, -100 * self.spoken] * 100).tobytes())
            return True

    line = ("05", "Probe.", None)
    current = b.voices.audio_path(*line)
    current.parent.mkdir(parents=True)
    b._write_mono(current, array.array("h", [7] * 50).tobytes())
    original = current.read_bytes()
    model = Model()
    assert b.new_take(line, model) == 2                     # the recording in use became take 1
    assert b.list_takes(*line) == [1, 2] and b.chosen_take(*line) == 1 and current.read_bytes() == original
    b.spare_path(*line).parent.mkdir(parents=True)
    b._write_mono(b.spare_path(*line), array.array("h", [1] * 10).tobytes())
    assert b.new_take(line, model) == 3 and model.spoken == 1   # a ready spare is used, nothing is generated
    assert not b.spare_path(*line).exists()
    b.choose_take(line, 3)
    assert current.read_bytes() == (b.takes_dir(*line) / "3.wav").read_bytes() and b.chosen_take(*line) == 3
    try:
        b.discard_take(line, 3)
        raise AssertionError("removed the take in use")
    except ValueError:
        pass
    b.discard_take(line, 2)
    assert b.list_takes(*line) == [1, 3]
    b.choose_take(line, 1)
    assert current.read_bytes() == original                 # any earlier take can come back
    job = b.queue({"kind": "spare", "lines": [list(line)]}, urgent=False)
    urgent = b.queue({"kind": "resample", "lines": [list(line)]})
    assert sorted(p.stem for p in b.JOBS.glob("*.json")) == [urgent, job]   # the user's request goes first
    # every generated line is brightened before it is levelled
    order = []
    real_brighten, real_level = b.brighten, b.level_match
    b.brighten = lambda path: order.append("brighten")
    b.level_match = lambda path, ref: order.append("level")
    assert b._publish(lambda text, reference, target: (target.write_bytes(b"x"), True)[1], "x", "05",
                      b.takes_dir(*line) / "8.wav")
    assert order == ["brighten", "level"]
    b.brighten, b.level_match = real_brighten, real_level
    (b.takes_dir(*line) / "8.wav").unlink()
    # a take appears only when it is complete; a failed one leaves nothing behind
    failing = lambda text, reference, target: (target.write_bytes(b"half"), False)[1]
    assert not b._publish(failing, "x", "05", b.takes_dir(*line) / "9.wav")
    assert not list(b.takes_dir(*line).glob("*9*")) and b.list_takes(*line) == [1, 3]
    # every finished request keeps its own result, so a caller waiting on an older one still finds it
    b.JOBS_DONE = b.JOBS / "done"
    b._finish(job, None, {"takes": [4]})
    b._finish(urgent, "boom", None)
    assert b.job_result(job) == {"state": "done", "error": None, "result": {"takes": [4]}}
    assert b.job_result(urgent)["state"] == "failed" and b.job_result("../../etc") is None
    # an urgent result outlives a burst of spare ones finishing after it (by name it would sort first and go first)
    import os as _os
    for n in range(105):
        spare_job = f"1-{9_000_000 + n}-1"
        b._finish(spare_job, None, None)
        _os.utime(b.JOBS_DONE / f"{spare_job}.json", ns=(10**18 + n, 10**18 + n))
    _os.utime(b.JOBS_DONE / f"{urgent}.json", ns=(10**18 + 200, 10**18 + 200))
    b._finish("1-99999999-1", None, None)
    assert b.job_result(urgent) is not None
    b.voices.VOICE_DIR, b.voices.REF_DIR, b.JOBS = saved
    b.JOBS_DONE = b.JOBS / "done"

# remembering the install works on a fresh checkout, before any runtime folder exists
with tempfile.TemporaryDirectory() as d:
    saved_settings = b.SETTINGS
    b.SETTINGS = pathlib.Path(d) / "fresh" / "dm_runtime" / "settings.json"
    b.remember_game(d)
    assert b.known_game() == str(pathlib.Path(d).resolve())
    b.SETTINGS = saved_settings

assert make_pack.slug("Der heilige Hering") == "der-heilige-hering" and make_pack.slug("Über Öl!") == "ueber-oel"

with tempfile.TemporaryDirectory() as d:
    root = pathlib.Path(d)
    (root / "stories").mkdir()
    library.EXPERIMENT = root
    library.STAGE_FILE = root / "stages.json"
    make_pack.PACKS = root / "packs"
    b.voices.REF_DIR = root / "refs"
    b.voices.REF_DIR.mkdir()
    story = {"title": "Der Probefall", "premise": "p", "hidden_truth": "t", "plot": {}, "plan": [],
             "conversations": {"VLK_1_A": graphs["a"]}}
    (root / "stories" / "s9_9.json").write_text(json.dumps(story), encoding="utf-8")
    (root / "graphs.json").write_text(json.dumps({"s9_9__VLK_1_A": graphs["a"]}), encoding="utf-8")
    try:
        make_pack.build("Der Probefall")                      # voice 05 threatening, but nobody knows its game lines
        raise AssertionError("packed a delivery voice it cannot rebuild")
    except SystemExit:
        pass
    (b.voices.REF_DIR / "05_drohend.keys.json").write_text('["DIA_X_05_01", "DIA_Y_05_02"]', encoding="utf-8")
    path, names, lines = make_pack.build("Der Probefall")
    assert names == ["der-probefall/story.json", "der-probefall/graphs.json", "der-probefall/refs.json",
                     "der-probefall/LIESMICH.md"]
    with zipfile.ZipFile(path) as pack:
        packed = json.loads(pack.read("der-probefall/graphs.json"))
        assert json.loads(pack.read("der-probefall/refs.json")) == {"05_drohend": ["DIA_X_05_01", "DIA_Y_05_02"]}
        everything = b"".join(pack.read(n) for n in pack.namelist())
    assert list(packed) == ["der-probefall__VLK_1_A"]
    assert b"s9_9" not in everything                         # the file name says where a story came from
    assert lines == 2
print("ok")
