"""Generates dialogue audio for graphs, skipping lines already baked. Private use only.

The voices are cloned from your own Gothic install and never leave your machine.

    bake_voices.py setup                                  (once: installs the speech model's environment)
    bake_voices.py all <GOTHIC install> <graphs.json>     (references for every voice used, then all lines)

    bake_voices.py refs <GOTHIC install> 15:4 09 ...   (voice, optional number of lines)
    bake_voices.py bake <graphs.json>
    bake_voices.py level
    bake_voices.py named <GOTHIC install> <voice>_<delivery> KEY KEY ...   (reference from chosen lines)
    bake_voices.py voice <GOTHIC install> <voice> <lines> <graphs.json>   (new reference length, then its lines again)
    bake_voices.py worker   (started by the inspector: keeps the model loaded and prepares spare takes)

On Apple Silicon the model runs on MLX, everywhere else on PyTorch (CUDA if an NVIDIA card is found, else the
CPU, which is slow). Commands that need the model restart themselves inside the environment `setup` made.
"""

import array
import json
import math
import os
import pathlib
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import status  # noqa: E402
import voices  # noqa: E402

TTS_DIR = voices.RUNTIME_DIR / "tts"
MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
TORCH_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"   # the same model for PyTorch
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
REF_LINES = 2      # game lines per reference voice: 10-15 s, the recommended length; 4 lines sounded no better in a blind test and were slower
REF_RATE = 24000   # sample rate of reference clips
SETTINGS = voices.RUNTIME_DIR / "settings.json"     # remembers the Gothic install, for the inspector's buttons
JOB_STATUS = voices.RUNTIME_DIR / "voice_job.json"  # what the worker is doing, read by the inspector
JOBS = voices.RUNTIME_DIR / "voice_jobs"            # requests to the worker, oldest first, user requests before spares
JOBS_DONE = JOBS / "done"                            # one result per finished request, so no waiting caller misses its own
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


_IMA_STEPS = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88,
              97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
              724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
              4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818,
              18500, 20350, 22385, 24623, 27086, 29794, 32767]
_IMA_INDEX = [-1, -1, -1, -1, 2, 4, 6, 8]


def _ima_adpcm(data, block_align):
    """Decode mono Microsoft IMA ADPCM, the format of Gothic's speech files."""
    out = array.array("h")
    for start in range(0, len(data) - 3, block_align):
        block = data[start:start + block_align]
        sample, index = struct.unpack_from("<hB", block)
        index = min(index, 88)
        out.append(sample)
        for byte in block[4:]:
            for nibble in (byte & 0x0F, byte >> 4):
                step = _IMA_STEPS[index]
                diff = step >> 3
                if nibble & 1:
                    diff += step >> 2
                if nibble & 2:
                    diff += step >> 1
                if nibble & 4:
                    diff += step
                sample = max(-32768, min(32767, sample - diff if nibble & 8 else sample + diff))
                index = max(0, min(88, index + _IMA_INDEX[nibble & 7]))
                out.append(sample)
    return out


def _resample(samples, source_rate, target_rate, half_width=16):
    """Windowed-sinc resampling with a low-pass below the new Nyquist frequency. Plain Python, a few seconds."""
    if source_rate == target_rate:
        return samples
    ratio = target_rate / source_rate
    cutoff = 0.5 * min(1.0, ratio) * 0.94          # in cycles per source sample
    count = int(len(samples) * ratio)
    out = array.array("h", bytes(2 * count))
    for n in range(count):
        t = n / ratio
        centre = int(t)
        acc = 0.0
        for k in range(max(0, centre - half_width + 1), min(len(samples), centre + half_width + 1)):
            x = t - k
            window = 0.5 + 0.5 * math.cos(math.pi * x / half_width)
            acc += samples[k] * (2 * cutoff if x == 0 else math.sin(2 * math.pi * cutoff * x) / (math.pi * x)) * window
        out[n] = max(-32768, min(32767, int(round(acc))))
    return out


def _pcm24k(raw):
    """A game WAV (IMA ADPCM or 16-bit PCM, mono) as 16-bit PCM at the reference rate."""
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    position, fmt, data = 12, None, None
    while position + 8 <= len(raw):
        tag, size = raw[position:position + 4], struct.unpack_from("<I", raw, position + 4)[0]
        body = raw[position + 8:position + 8 + size]
        if tag == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", body)
        elif tag == b"data":
            data = body
        position += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError("WAV without format or data")
    kind, channels, rate, _, block_align, bits = fmt
    if channels != 1:
        raise ValueError("expected mono speech")
    if kind == 0x11:
        samples = _ima_adpcm(data, block_align)
    elif kind == 1 and bits == 16:
        samples = array.array("h", data[:len(data) // 2 * 2])
    else:
        raise ValueError(f"unsupported WAV format {kind}")
    if sys.byteorder != "little":
        samples.byteswap()
    resampled = _resample(samples, rate, REF_RATE)
    if sys.byteorder != "little":
        resampled.byteswap()
    return resampled.tobytes()


def _write_mono(path, frames):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(REF_RATE)
        w.writeframes(frames)


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

        frames = b""
        for key in chosen:
            path, offset, size = index[key]
            with open(path, "rb") as f:
                f.seek(offset)
                raw = f.read(size)
            frames += _pcm24k(raw) + b"\0\0" * (REF_RATE // 3)
            print(voice, key, lines[key[:-4]])

        if not chosen:
            raise SystemExit(f"no usable lines for voice {voice} in this install")
        _write_mono(voices.REF_DIR / f"{voice}.wav", frames)
        (voices.REF_DIR / f"{voice}.txt").write_text(" ".join(lines[k[:-4]] for k in chosen), encoding="utf-8")
        (voices.REF_DIR / f"{voice}.keys.json").write_text(json.dumps([k[:-4] for k in chosen]), encoding="utf-8")


def named_refs(game, name, keys):
    data = pathlib.Path(game) / "Data"
    index = {}
    for vdf in ("Speech1.vdf", "Speech2.vdf", "Speech_Addon.vdf"):
        index.update(read_vdf_index(data / vdf))
    info = pathlib.Path(game) / "_work/Data/Scripts/_compiled/OUINFO.INF"
    text = info.read_bytes().decode("cp1252", "replace")
    lines = {m[1].upper(): m[2].strip().rstrip("}").strip()
             for m in re.finditer(r'AI_Output\s*\([^"]*"([^"]+)"\)\s*;\s*//\s*([^\r\n]*)', text)}
    frames, spoken = b"", []
    for key in keys:
        path, offset, size = index[f"{key}.WAV"]
        with open(path, "rb") as f:
            f.seek(offset)
            raw = f.read(size)
        frames += _pcm24k(raw) + b"\0\0" * (REF_RATE // 3)
        spoken.append(re.sub(r"\([^)]*\)\s*", "", lines[key]).strip())
    _write_mono(voices.REF_DIR / f"{name}.wav", frames)
    (voices.REF_DIR / f"{name}.txt").write_text(" ".join(spoken), encoding="utf-8")
    # the keys say which game lines were used, so another install can build the same reference (see make_pack)
    (voices.REF_DIR / f"{name}.keys.json").write_text(json.dumps(list(keys)), encoding="utf-8")
    print(name, " ".join(spoken))


def reference_keys(name):
    """The game lines a hand-picked reference was cut from, or None. Older references are matched by their text."""
    saved = voices.REF_DIR / f"{name}.keys.json"
    if saved.exists():
        return json.loads(saved.read_text(encoding="utf-8"))
    text_file, lines_file = voices.REF_DIR / f"{name}.txt", voices.RUNTIME_DIR / "mechanics" / "lines.json"
    if not text_file.exists() or not lines_file.exists():
        return None
    spoken = text_file.read_text(encoding="utf-8")
    voice = name.split("_")[0]
    found = []
    for key, line in json.loads(lines_file.read_text(encoding="utf-8")).items():
        clean = re.sub(r"\([^)]*\)\s*", "", line).strip()
        if key.endswith(tuple(f"_{voice}_{n:02d}" for n in range(100))) and len(clean) > 20 and clean in spoken:
            found.append((spoken.index(clean), key))
    keys = [key for _, key in sorted(found)]
    if not keys or len(" ".join(re.sub(r"\([^)]*\)\s*", "", json.loads(lines_file.read_text(encoding="utf-8"))[k]).strip()
                                for k in keys)) != len(spoken):
        return None  # only a complete match is trustworthy
    saved.write_text(json.dumps(keys), encoding="utf-8")
    return keys


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
    if "narration" in graph:  # {"voice": "10", "narration": ["line", ...]} for narrator lines outside dialogue
        for text in graph["narration"]:
            yield voice, text, None
        return
    for node in graph["nodes"].values():
        if voice:
            yield voice, node["line"], node.get("delivery")
            if node.get("again"):
                yield voice, node["again"], node.get("delivery")
            for variant in node.get("variants", []):
                yield voice, variant["line"], node.get("delivery")
        for choice in node["choices"]:
            yield voices.HERO_VOICE, choice["text"], None


def backend():
    """mlx on Apple Silicon, torch everywhere else. OPENGOTHIC_TTS_BACKEND overrides."""
    chosen = os.environ.get("OPENGOTHIC_TTS_BACKEND")
    if chosen in ("mlx", "torch"):
        return chosen
    return "mlx" if sys.platform == "darwin" and platform.machine() == "arm64" else "torch"


def venv_dir():
    return TTS_DIR / f"venv-{backend()}"


def venv_python():
    venv = venv_dir()
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def setup():
    """Create the speech model's environment. Downloads a few GB on first use."""
    python = venv_python()
    if not python.exists():
        print("creating", venv_dir(), flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir())], check=True)
    pip = [str(python), "-m", "pip", "install", "--upgrade"]
    subprocess.run(pip + ["pip"], check=True)
    if backend() == "mlx":
        subprocess.run(pip + ["mlx-audio"], check=True)
    else:
        if shutil.which("nvidia-smi"):
            subprocess.run(pip + ["torch", "torchaudio", "--index-url", TORCH_CUDA_INDEX], check=True)
        else:
            print("No NVIDIA card found: the voices will be generated on the CPU, which takes minutes per line.",
                  flush=True)
            subprocess.run(pip + ["torch", "torchaudio"], check=True)
        subprocess.run(pip + ["qwen-tts"], check=True)
    print("ready. Next: bake_voices.py all <GOTHIC install> <graphs.json>", flush=True)


def _inside_venv():
    return pathlib.Path(sys.prefix).resolve() == venv_dir().resolve()


def _run_in_venv(argv):
    """Restart this command with the environment's python, which has the speech model installed."""
    python = venv_python()
    if not python.exists():
        raise SystemExit(f"the speech model is not installed yet. Run first:\n  python {pathlib.Path(__file__).name} setup")
    raise SystemExit(subprocess.run([str(python), str(pathlib.Path(__file__).resolve()), *argv]).returncode)


class MlxVoice:
    """The model loaded once for the whole run: starting a process per line cost half of every line's time."""

    def __init__(self):
        os.environ.setdefault("HF_HOME", str(TTS_DIR / "hf"))  # before the import, which reads it
        from mlx_audio.tts.generate import generate_audio
        from mlx_audio.tts.utils import load_model
        self.generate = generate_audio
        self.model = load_model(model_path=MODEL)

    def forget(self, reference):
        pass  # nothing is prepared ahead: every line reads the reference afresh

    def speak(self, text, reference, target):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self.generate(text=text, model=self.model, lang_code="german",
                              ref_audio=str(voices.REF_DIR / f"{reference}.wav"),
                              ref_text=(voices.REF_DIR / f"{reference}.txt").read_text(encoding="utf-8"),
                              output_path=tmp, file_prefix="line", audio_format="wav", verbose=False)
            except Exception as error:  # one bad line must not end the run; the caller retries it once
                print("generation failed:", error, flush=True)
                return False
            produced = sorted(pathlib.Path(tmp).glob("line*.wav"))
            if produced:
                shutil.move(str(produced[0]), str(target))
                return True
        return False


class TorchVoice:
    """The model loaded once, and each reference voice prepared once."""

    def __init__(self):
        os.environ.setdefault("HF_HOME", str(TTS_DIR / "hf"))
        import torch
        from qwen_tts import Qwen3TTSModel
        self.np = __import__("numpy")
        cuda = torch.cuda.is_available()
        self.model = Qwen3TTSModel.from_pretrained(TORCH_MODEL, device_map="cuda:0" if cuda else "cpu",
                                                   dtype=torch.bfloat16 if cuda else torch.float32)
        self.prompts = {}

    def forget(self, reference):
        self.prompts.pop(reference, None)

    def speak(self, text, reference, target):
        if reference not in self.prompts:
            self.prompts[reference] = self.model.create_voice_clone_prompt(
                ref_audio=str(voices.REF_DIR / f"{reference}.wav"),
                ref_text=(voices.REF_DIR / f"{reference}.txt").read_text(encoding="utf-8"))
        audio, rate = self.model.generate_voice_clone(text=text, language="german",
                                                      voice_clone_prompt=self.prompts[reference])
        if not len(audio) or not len(audio[0]):
            return False
        pcm = (self.np.clip(audio[0], -1.0, 1.0) * 32767).astype("<i2")
        with wave.open(str(target), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(rate))
            w.writeframes(pcm.tobytes())
        return True


def needed_voices(graphs):
    """Reference names a set of graphs speaks with."""
    return sorted({voices.reference_name(voice, delivery)
                   for g in graphs.values() for voice, _, delivery in spoken_lines(g) if voice})


def remember_game(game):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)  # a fresh checkout has no runtime folder yet
    SETTINGS.write_text(json.dumps({"game": str(pathlib.Path(game).resolve())}), encoding="utf-8")


def known_game():
    """The Gothic install last used here, or OPENGOTHIC_GAME, or None."""
    if os.environ.get("OPENGOTHIC_GAME"):
        return os.environ["OPENGOTHIC_GAME"]
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))["game"]
    except (OSError, ValueError, KeyError):
        return None


_job = {"id": None, "finished": None, "result": None}


def _report(state, done=0, total=0, message="", error=None, result=None):
    temporary = JOB_STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps({"state": state, "done": done, "total": total, "message": message, "error": error,
                                     "job": _job["id"], "finished": _job["finished"], "result": result},
                                    ensure_ascii=False),
                         encoding="utf-8")
    temporary.replace(JOB_STATUS)


def job_result(job_id):
    """The outcome of a finished request, or None while it is queued or running."""
    if not re.fullmatch(r"[0-9]-[0-9]+-[0-9]+", job_id or ""):
        return None
    try:
        return json.loads((JOBS_DONE / f"{job_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _finish(job_id, error, result):
    JOBS_DONE.mkdir(parents=True, exist_ok=True)
    temporary = JOBS_DONE / f"{job_id}.tmp"
    temporary.write_text(json.dumps({"state": "failed" if error else "done", "error": error, "result": result},
                                    ensure_ascii=False), encoding="utf-8")
    temporary.replace(JOBS_DONE / f"{job_id}.json")
    # Keep the recent ones by when they finished: by name, every urgent result (0-...) sorts before every spare one
    # (1-...) and was the first to go, while its caller was still waiting for it.
    for old in sorted(JOBS_DONE.glob("*.json"), key=lambda f: f.stat().st_mtime_ns)[:-100]:
        old.unlink(missing_ok=True)


def _publish(speak, text, reference, target):
    """Generates into a private file and moves it into place only when written and levelled, so nobody can list,
    play or choose a half-written take."""
    partial = target.with_name(f".{target.stem}.{os.getpid()}.partial.wav")
    try:
        if not any(speak(text, reference, partial) for _attempt in range(2)):
            return False
        level_match(partial, reference)
        os.replace(partial, target)
        return True
    finally:
        partial.unlink(missing_ok=True)


def spare_path(voice, text, delivery=None):
    """A take made ahead of time, so re-sampling can show it at once. Kept apart from the recordings."""
    target = voices.audio_path(voice, text, delivery)
    return target.parent / "spare" / target.name


# Takes: re-sampling never overwrites. Every take of a line is kept in takes/<recording>/<n>.wav, and the recording the
# game plays is a copy of the chosen one, so a worse take costs nothing and any earlier one can come back.

def takes_dir(voice, text, delivery=None):
    target = voices.audio_path(voice, text, delivery)
    return target.parent / "takes" / target.stem


def list_takes(voice, text, delivery=None):
    folder = takes_dir(voice, text, delivery)
    return sorted(int(p.stem) for p in folder.glob("*.wav") if p.stem.isdigit()) if folder.exists() else []


def chosen_take(voice, text, delivery=None):
    marker = takes_dir(voice, text, delivery) / "chosen"
    try:
        return int(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _keep_current(line):
    """Before the first new take, the recording as it is becomes take 1."""
    folder, current = takes_dir(*line), voices.audio_path(*line)
    if not list_takes(*line) and current.exists():
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(current, folder / "1.wav")
        (folder / "chosen").write_text("1", encoding="utf-8")


def choose_take(line, number):
    """Makes a take the recording the game plays."""
    source = takes_dir(*line) / f"{number}.wav"
    if not source.exists():
        raise ValueError("no such take")
    target = voices.audio_path(*line)
    temporary = target.with_name(f".{target.stem}.{os.getpid()}.{threading.get_ident()}.choosing.wav")
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)
    (takes_dir(*line) / "chosen").write_text(str(number), encoding="utf-8")


def discard_take(line, number):
    if number == chosen_take(*line):
        raise ValueError("the take in use cannot be removed")
    (takes_dir(*line) / f"{number}.wav").unlink(missing_ok=True)


def new_take(line, model):
    """One more take of a line, from the spare one if it is ready. Returns its number, or None."""
    _keep_current(line)
    folder = takes_dir(*line)
    folder.mkdir(parents=True, exist_ok=True)
    number = max(list_takes(*line), default=0) + 1
    target, spare = folder / f"{number}.wav", spare_path(*line)
    if spare.exists():
        os.replace(spare, target)
        return number
    return number if _publish(model.speak, line[1], voices.reference_name(line[0], line[2]), target) else None


def load_voice_model():
    return MlxVoice() if backend() == "mlx" else TorchVoice()


def speak_all(lines, quest=None, model=None):
    """Generates each missing (voice, text, delivery). Returns the lines that failed."""
    if not lines:
        return []
    model = model or load_voice_model()
    failed = []
    for n, (voice, text, delivery) in enumerate(lines, 1):
        target = voices.audio_path(voice, text, delivery)
        reference = voices.reference_name(voice, delivery)
        target.parent.mkdir(parents=True, exist_ok=True)
        # written privately and moved into place when complete, so nobody plays a half-written line
        made = _publish(model.speak, text, reference, target)
        if not made:  # one bad line must not cost the rest of the story
            failed.append((voice, text))
            print(f"{n}/{len(lines)} FAILED {voice} {text[:50]}", flush=True)
            continue
        print(f"{n}/{len(lines)} {voice} {text[:50]}", flush=True)
        status.report("Stimmen", n, len(lines), quest)
        _report("running", n, len(lines), text)
    status.report("bereit", quest=quest)
    return failed


def bake(path, quest=None):
    with open(path, encoding="utf-8") as f:
        graphs = json.load(f)
    todo = sorted({line for g in graphs.values() for line in spoken_lines(g)
                   if not voices.audio_path(*line).exists()},
                  key=lambda line: (line[0], line[1], line[2] or ""))
    print(len(todo), "lines to generate", flush=True)
    missing = [name for name in needed_voices(graphs) if not (voices.REF_DIR / f"{name}.wav").exists()]
    if missing:
        raise SystemExit("missing reference voices: " + " ".join(missing) + ". Run `all` or `refs` first.")
    failed = speak_all(todo, quest)
    print(f"{len(todo) - len(failed)} generated, {len(failed)} failed", flush=True)
    if failed:
        sys.exit(1)


def voice_lines(graphs, voice):
    """Every line a voice speaks in these graphs, without a delivery of its own."""
    return sorted({line for g in graphs.values() for line in spoken_lines(g) if line[0] == voice and not line[2]},
                  key=lambda line: line[1])


def rebuild_voice(game, voice, count, graphs, quest=None, model=None):
    """A new reference from `count` game lines, then a new take of every line of that voice in the graphs, put in use.
    The earlier takes and the earlier reference (<voice>.previous.*) are kept, so the change can be undone."""
    if not 1 <= count <= 6:
        raise ValueError("a reference is built from 1 to 6 game lines")
    if "_" in voice:
        raise ValueError("a voice with a delivery is built from hand-picked lines, see `named`")
    for suffix in (".wav", ".txt", ".keys.json"):
        current = voices.REF_DIR / f"{voice}{suffix}"
        if current.exists():
            shutil.copyfile(current, voices.REF_DIR / f"{voice}.previous{suffix}")
    for old in (voices.VOICE_DIR / voice / "spare").glob("*.wav"):
        old.unlink()  # spare takes from the old reference no longer fit
    extract_refs(game, [f"{voice}:{count}"])
    lines = [line for line in voice_lines(graphs, voice) if voices.audio_path(*line).exists()]
    model = model or load_voice_model()
    model.forget(voice)  # a model that prepared the old reference must not keep using it
    failed = []
    for n, line in enumerate(lines, 1):
        number = new_take(line, model)
        if number is None:
            failed.append(line)
        else:
            choose_take(line, number)
        _report("running", n, len(lines), line[1])
        status.report("Stimmen", n, len(lines), quest)
    status.report("bereit", quest=quest)
    return failed


def queue(job, urgent=True):
    """Hands a request to the worker. Urgent ones (the user waits) run before spare takes."""
    JOBS.mkdir(parents=True, exist_ok=True)
    name = f"{0 if urgent else 1}-{time.time_ns()}-{os.getpid()}"
    temporary = JOBS / f"{name}.tmp"
    temporary.write_text(json.dumps({**job, "id": name}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(JOBS / f"{name}.json")
    return name


def _new_takes(lines, model):
    """A new take for each line, without touching the one in use. Then the next spare is prepared."""
    failed, made = [], []
    for n, line in enumerate(lines, 1):
        number = new_take(line, model)
        if number is None:
            failed.append(line)
        made.append(number)
        _report("running", n, len(lines), line[1])
    queue({"kind": "spare", "lines": [list(line) for line in lines]}, urgent=False)
    _job["result"] = {"takes": made}
    return failed


def _spares(lines, model):
    for voice, text, delivery in lines:
        spare = spare_path(voice, text, delivery)
        reference = voices.reference_name(voice, delivery)
        if spare.exists() or not voices.audio_path(voice, text, delivery).exists():
            continue
        spare.parent.mkdir(parents=True, exist_ok=True)
        _publish(model.speak, text, reference, spare)
    return []


def run_job(job, model):
    """One request: resample (lines), spare (lines) or reference (voice, count, graphs)."""
    lines = [tuple(line) for line in job.get("lines", [])]
    if job["kind"] == "resample":
        return _new_takes(lines, model)
    if job["kind"] == "spare":
        return _spares(lines, model)
    if job["kind"] == "speak":   # a line whose text was just edited
        return speak_all([line for line in lines if not voices.audio_path(*line).exists()], model=model)
    if job["kind"] == "reference":
        game = known_game()
        if not game:
            raise ValueError("unknown Gothic install: run bake_voices.py all once, or set OPENGOTHIC_GAME")
        return rebuild_voice(game, job["voice"], int(job["count"]), job["graphs"], model=model)
    raise ValueError("unknown job")


def _end_with_parent():
    """The inspector keeps a pipe to our stdin. When it goes away, however it ends, reading returns, and so do we.
    Unlike watching the parent's process id, this works on Windows too."""
    def watch():
        try:
            sys.stdin.buffer.read()
        finally:
            os._exit(0)
    threading.Thread(target=watch, daemon=True).start()


def worker():
    """Keeps the model loaded and works through requests. Ends when the inspector that started it is gone."""
    _end_with_parent()
    JOBS.mkdir(parents=True, exist_ok=True)
    _report("loading")
    model = load_voice_model()
    _report("idle")
    while True:
        pending = sorted(JOBS.glob("*.json"))
        if not pending:
            time.sleep(0.15)
            continue
        path = pending[0]
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            continue
        path.unlink(missing_ok=True)
        _job["id"], _job["result"] = job.get("id"), None
        quiet = job["kind"] == "spare"   # spare takes happen behind the user's back
        if not quiet:
            _report("running", 0, 0, "starting")
        try:
            failed = run_job(job, model)
            error = f"{len(failed)} lines failed" if failed else None
        except (Exception, SystemExit) as problem:  # the inspector shows why; the worker keeps going
            error = str(problem) or type(problem).__name__
        _finish(job.get("id"), error, _job["result"])
        if not quiet or error:
            _job["finished"] = job.get("id")
            _report("failed" if error else "done", error=error, result=_job["result"])


def bake_all(game, path, quest=None):
    """Everything a newcomer needs: reference voices from their own install for every voice used, then the lines."""
    remember_game(game)
    with open(path, encoding="utf-8") as f:
        graphs = json.load(f)
    named = [name for name in needed_voices(graphs) if "_" in name]
    missing_named = [name for name in named if not (voices.REF_DIR / f"{name}.wav").exists()]
    keys_file = pathlib.Path(path).with_name("refs.json")   # shipped by make_pack: which game lines to use
    shipped = json.loads(keys_file.read_text(encoding="utf-8")) if keys_file.exists() else {}
    for name in missing_named:
        if name not in shipped:
            raise SystemExit(f"voice {name} needs hand-picked lines, see `named`")
        print("reference voice from your install:", name, flush=True)
        named_refs(game, name, shipped[name])
    plain = [name for name in needed_voices(graphs) if "_" not in name and not (voices.REF_DIR / f"{name}.wav").exists()]
    if plain:
        print("reference voices from your install:", " ".join(plain), flush=True)
        extract_refs(game, [f"{name}:{REF_LINES}" for name in plain])
    bake(path, quest)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    if command in ("bake", "all", "voice", "worker") and not _inside_venv():
        _run_in_venv(sys.argv[1:])
    if command == "setup":
        setup()
    elif command == "all" and len(sys.argv) >= 4:
        bake_all(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif command == "worker":
        worker()
    elif command == "voice" and len(sys.argv) == 6:
        remember_game(sys.argv[2])
        with open(sys.argv[5], encoding="utf-8") as f:
            lost = rebuild_voice(sys.argv[2], sys.argv[3], int(sys.argv[4]), json.load(f))
        sys.exit(1 if lost else 0)
    elif command in ("help", "all", "voice") or len(sys.argv) < 3 and command != "level":
        print(__doc__)
    elif sys.argv[1] == "refs":
        remember_game(sys.argv[2])
        extract_refs(sys.argv[2], sys.argv[3:])
    elif sys.argv[1] == "level":
        level_all()
    elif sys.argv[1] == "named":
        named_refs(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        bake(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
