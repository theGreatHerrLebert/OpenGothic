"""Generates dialogue audio for graphs, skipping lines already baked. Private use only.

    bake_voices.py refs <GOTHIC install> 15 09 ...
    bake_voices.py bake <graphs.json>

graphs.json maps a name to a graph. Run `bake` with the TTS virtualenv's python.
"""

import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voices  # noqa: E402

TTS_DIR = voices.RUNTIME_DIR / "tts"
MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"


def read_vdf_index(path):
    with open(path, "rb") as f:
        header = f.read(296)
        count, root = struct.unpack_from("<I", header, 272)[0], struct.unpack_from("<I", header, 288)[0]
        f.seek(root)
        table = f.read(count * 80)
    index = {}
    for i in range(count):
        name, offset, size, kind, _ = struct.unpack_from("<64sIIII", table, i * 80)
        if not kind & 0x80000000:
            index[name.split(b" ")[0].decode("latin-1").strip().upper()] = (path, offset, size)
    return index


def extract_refs(game, wanted):
    data = pathlib.Path(game) / "Data"
    index = {}
    for name in ("Speech1.vdf", "Speech2.vdf", "Speech_Addon.vdf"):
        index.update(read_vdf_index(data / name))
    info = pathlib.Path(game) / "_work/Data/Scripts/_compiled/OUINFO.INF"
    text = info.read_bytes().decode("cp1252", "replace")
    lines = {m[1].upper(): m[2].strip().rstrip("}").strip()
             for m in re.finditer(r'AI_Output\s*\([^"]*"([^"]+)"\)\s*;\s*//\s*([^\r\n]*)', text)}
    voices.REF_DIR.mkdir(parents=True, exist_ok=True)
    for voice in wanted:
        pattern = re.compile(rf"_{voice}_\d\d\.WAV$")
        candidates = sorted(
            (abs(len(lines[k[:-4]]) - 115), k) for k in index
            if pattern.search(k) and k[:-4] in lines
            and 90 <= len(lines[k[:-4]]) <= 140 and not re.search(r"[(\[]", lines[k[:-4]]))
        key = candidates[0][1]
        path, offset, size = index[key]
        with open(path, "rb") as f:
            f.seek(offset)
            raw = f.read(size)
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(raw)
            tmp.flush()
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1",
                            tmp.name, str(voices.REF_DIR / f"{voice}.wav")], check=True)
        (voices.REF_DIR / f"{voice}.txt").write_text(lines[key[:-4]], encoding="utf-8")
        print(voice, key)


def spoken_lines(graph):
    voice = graph.get("voice")
    for node in graph["nodes"].values():
        if voice:
            yield voice, node["line"]
        for choice in node["choices"]:
            yield voices.HERO_VOICE, choice["text"]


def bake(path):
    with open(path, encoding="utf-8") as f:
        graphs = json.load(f)
    todo = sorted({pair for g in graphs.values() for pair in spoken_lines(g)
                   if not voices.audio_path(*pair).exists()})
    print(len(todo), "lines to generate")
    env = dict(os.environ, HF_HOME=str(TTS_DIR / "hf"))
    for n, (voice, text) in enumerate(todo, 1):
        target = voices.audio_path(voice, text)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, "-m", "mlx_audio.tts.generate", "--model", MODEL,
                            "--lang_code", "german", "--text", text,
                            "--ref_audio", str(voices.REF_DIR / f"{voice}.wav"),
                            "--ref_text", (voices.REF_DIR / f"{voice}.txt").read_text(encoding="utf-8"),
                            "--output_path", tmp, "--file_prefix", "line", "--audio_format", "wav"],
                           check=True, env=env, capture_output=True)
            produced = sorted(pathlib.Path(tmp).glob("line*.wav"))
            pathlib.Path(produced[0]).replace(target)
        print(f"{n}/{len(todo)} {voice} {text[:50]}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "refs":
        extract_refs(sys.argv[2], sys.argv[3:])
    else:
        bake(sys.argv[2])
