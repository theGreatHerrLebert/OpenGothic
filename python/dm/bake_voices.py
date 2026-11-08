"""Generates dialogue audio for graphs, skipping lines already baked. Private use only.

    bake_voices.py refs <GOTHIC install> 15:4 09 ...   (voice, optional number of lines)
    bake_voices.py bake <graphs.json>
    bake_voices.py level
    bake_voices.py named <GOTHIC install> <voice>_<delivery> KEY KEY ...   (reference from chosen lines)

graphs.json maps a name to a graph. Run `bake` with the TTS virtualenv's python.
"""

import array
import json
import math
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voices  # noqa: E402

TTS_DIR = voices.RUNTIME_DIR / "tts"
MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
LOUDNESS_BOOST = 1.0  # relative to the original recording of the voice
PEAK_LIMIT = 32000    # keeps scaled audio from clipping


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
    for spec in wanted:
        voice, _, count = spec.partition(":")
        count = int(count or 1)
        pattern = re.compile(rf"_{voice}_\d\d\.WAV$")
        candidates = sorted(
            (abs(len(lines[k[:-4]]) - 90), k) for k in index
            if pattern.search(k) and k[:-4] in lines and "ADDON" not in k
            and 60 <= len(lines[k[:-4]]) <= 130 and not re.search(r"[(\[]", lines[k[:-4]]))
        chosen, speakers = [], set()
        for _, key in candidates:
            if key.split("_")[1] not in speakers:
                speakers.add(key.split("_")[1])
                chosen.append(key)
            if len(chosen) == count:
                break

        frames, params = b"", None
        for key in chosen:
            path, offset, size = index[key]
            with open(path, "rb") as f:
                f.seek(offset)
                raw = f.read(size)
            with tempfile.TemporaryDirectory() as tmp:
                src, dst = pathlib.Path(tmp, "in.wav"), pathlib.Path(tmp, "out.wav")
                src.write_bytes(raw)
                subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1",
                                str(src), str(dst)], check=True)
                with wave.open(str(dst), "rb") as w:
                    params = w.getparams()
                    frames += w.readframes(w.getnframes()) + b"\0\0" * (params.framerate // 3)
            print(voice, key, lines[key[:-4]])

        voices.REF_DIR.mkdir(parents=True, exist_ok=True)
        with wave.open(str(voices.REF_DIR / f"{voice}.wav"), "wb") as w:
            w.setparams(params)
            w.writeframes(frames)
        (voices.REF_DIR / f"{voice}.txt").write_text(" ".join(lines[k[:-4]] for k in chosen), encoding="utf-8")


def named_refs(game, name, keys):
    data = pathlib.Path(game) / "Data"
    index = {}
    for vdf in ("Speech1.vdf", "Speech2.vdf", "Speech_Addon.vdf"):
        index.update(read_vdf_index(data / vdf))
    info = pathlib.Path(game) / "_work/Data/Scripts/_compiled/OUINFO.INF"
    text = info.read_bytes().decode("cp1252", "replace")
    lines = {m[1].upper(): m[2].strip().rstrip("}").strip()
             for m in re.finditer(r'AI_Output\s*\([^"]*"([^"]+)"\)\s*;\s*//\s*([^\r\n]*)', text)}
    frames, params, spoken = b"", None, []
    for key in keys:
        path, offset, size = index[f"{key}.WAV"]
        with open(path, "rb") as f:
            f.seek(offset)
            raw = f.read(size)
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = pathlib.Path(tmp, "in.wav"), pathlib.Path(tmp, "out.wav")
            src.write_bytes(raw)
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1",
                            str(src), str(dst)], check=True)
            with wave.open(str(dst), "rb") as w:
                params = w.getparams()
                frames += w.readframes(w.getnframes()) + b"\0\0" * (params.framerate // 3)
        spoken.append(re.sub(r"\([^)]*\)\s*", "", lines[key]).strip())
    with wave.open(str(voices.REF_DIR / f"{name}.wav"), "wb") as w:
        w.setparams(params)
        w.writeframes(frames)
    (voices.REF_DIR / f"{name}.txt").write_text(" ".join(spoken), encoding="utf-8")
    print(name, " ".join(spoken))


def _samples(path):
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        if params.sampwidth != 2:
            raise ValueError(f"expected 16-bit audio: {path}")
        return params, array.array("h", w.readframes(params.nframes))


def _rms(samples):
    return math.sqrt(sum(v * v for v in samples) / max(len(samples), 1))


def level_match(path, reference_name):
    """Scale a generated line to the loudness of that voice's original recording."""
    _, reference = _samples(voices.REF_DIR / f"{reference_name}.wav")
    params, samples = _samples(path)
    peak = max((abs(v) for v in samples), default=0)
    if not peak or not _rms(samples):
        return 1.0
    gain = min(_rms(reference) / _rms(samples) * LOUDNESS_BOOST, PEAK_LIMIT / peak)
    scaled = array.array("h", (int(v * gain) for v in samples))
    with wave.open(str(path), "wb") as w:
        w.setparams(params)
        w.writeframes(scaled.tobytes())
    return gain


def level_all():
    for voice_dir in sorted(voices.VOICE_DIR.iterdir()):
        if voice_dir.name == "refs" or not voice_dir.is_dir():
            continue
        gains = [level_match(p, voice_dir.name) for p in voice_dir.glob("*.wav")]
        print(voice_dir.name, len(gains), "avg gain %.2f" % (sum(gains) / max(len(gains), 1)))


def spoken_lines(graph):
    voice = graph.get("voice")
    for node in graph["nodes"].values():
        if voice:
            yield voice, node["line"], node.get("delivery")
            if node.get("again"):
                yield voice, node["again"], node.get("delivery")
        for choice in node["choices"]:
            yield voices.HERO_VOICE, choice["text"], None


def bake(path):
    with open(path, encoding="utf-8") as f:
        graphs = json.load(f)
    todo = sorted({line for g in graphs.values() for line in spoken_lines(g)
                   if not voices.audio_path(*line).exists()},
                  key=lambda line: (line[0], line[1], line[2] or ""))
    print(len(todo), "lines to generate")
    env = dict(os.environ, HF_HOME=str(TTS_DIR / "hf"))
    for n, (voice, text, delivery) in enumerate(todo, 1):
        target = voices.audio_path(voice, text, delivery)
        reference = voices.reference_name(voice, delivery)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, "-m", "mlx_audio.tts.generate", "--model", MODEL,
                            "--lang_code", "german", "--text", text,
                            "--ref_audio", str(voices.REF_DIR / f"{reference}.wav"),
                            "--ref_text", (voices.REF_DIR / f"{reference}.txt").read_text(encoding="utf-8"),
                            "--output_path", tmp, "--file_prefix", "line", "--audio_format", "wav"],
                           check=True, env=env, capture_output=True)
            produced = sorted(pathlib.Path(tmp).glob("line*.wav"))
            pathlib.Path(produced[0]).replace(target)
        level_match(target, reference)
        print(f"{n}/{len(todo)} {voice} {text[:50]}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "refs":
        extract_refs(sys.argv[2], sys.argv[3:])
    elif sys.argv[1] == "level":
        level_all()
    elif sys.argv[1] == "named":
        named_refs(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        bake(sys.argv[2])
