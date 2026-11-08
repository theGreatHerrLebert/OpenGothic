"""Where pre-generated dialogue audio lives. Uses only the standard library."""

import hashlib
import pathlib
import wave

HERO_VOICE = "15"
RUNTIME_DIR = pathlib.Path(__file__).resolve().parent.parent / "dm_runtime"
VOICE_DIR = RUNTIME_DIR / "voices"
REF_DIR = VOICE_DIR / "refs"


def audio_path(voice, text):
    key = hashlib.sha1(f"{voice}\0{text}".encode("utf-8")).hexdigest()[:20]
    return VOICE_DIR / voice / f"{key}.wav"


def lookup(voice, text):
    """Return (path, milliseconds) for baked audio, or ("", 0) to stay silent."""
    if voice is None:
        return "", 0
    path = audio_path(voice, text)
    try:
        with wave.open(str(path), "rb") as w:
            return str(path), int(w.getnframes() * 1000 / w.getframerate())
    except (OSError, EOFError, wave.Error):
        return "", 0
