"""Where pre-generated dialogue audio lives. Uses only the standard library."""

import hashlib
import pathlib
import wave

HERO_VOICE = "15"
RUNTIME_DIR = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime"
VOICE_DIR = RUNTIME_DIR / "voices"
REF_DIR = VOICE_DIR / "refs"


def reference_name(voice, delivery=None):
    return f"{voice}_{delivery}" if delivery else voice


def audio_path(voice, text, delivery=None):
    source = f"{voice}\0{delivery}\0{text}" if delivery else f"{voice}\0{text}"
    key = hashlib.sha1(source.encode("utf-8")).hexdigest()[:20]
    return VOICE_DIR / voice / f"{key}.wav"


def lookup(voice, text, delivery=None):
    """Return (path, milliseconds) for baked audio, or ("", 0) to stay silent."""
    if voice is None:
        return "", 0
    path = audio_path(voice, text, delivery)
    try:
        with wave.open(str(path), "rb") as w:
            return str(path), int(w.getnframes() * 1000 / w.getframerate())
    except (OSError, EOFError, wave.Error):
        return "", 0
