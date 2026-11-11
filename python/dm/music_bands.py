"""Per-frame band energy of a music track, worked out once so a trip can hit with the music without analysing audio
while the game runs. After Solaris's gen_fft.py.

    python3 python/dm/music_bands.py <track.wav>     writes <track.wav>.bands next to it (needs ffmpeg and numpy)

A .bands file holds, for every 1/60 s, four 32-bit floats: bass, mid, treble and kick, each scaled so the track's
loud parts sit near 1. Kick is how sharply the bass rises from one frame to the next. Reading needs neither numpy nor
ffmpeg, so the game can do it.
"""

import array
import pathlib
import subprocess
import sys

RATE = 44100
FPS = 60
WINDOW = RATE // FPS
BANDS = ((20, 250), (250, 2000), (2000, 16000))
FIELDS = 4


def make(path):
    import numpy as np
    pcm = subprocess.run(["ffmpeg", "-v", "quiet", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(RATE),
                          "pipe:1"], capture_output=True, check=True).stdout
    samples = np.frombuffer(pcm, dtype=np.float32)
    frames = len(samples) // WINDOW
    windowed = samples[:frames * WINDOW].reshape(frames, WINDOW) * np.hanning(WINDOW)
    spectrum = np.abs(np.fft.rfft(windowed, axis=1))
    freqs = np.fft.rfftfreq(WINDOW, 1 / RATE)
    bands = np.stack([spectrum[:, (freqs >= lo) & (freqs < hi)].mean(axis=1) for lo, hi in BANDS], axis=1)
    kick = np.maximum(0, np.diff(bands[:, 0], prepend=bands[0, 0]))
    out = np.concatenate([bands, kick[:, None]], axis=1)
    out /= np.maximum(np.percentile(out, 95, axis=0), 1e-9)   # loud parts near 1, so every track hits alike
    target = pathlib.Path(str(path) + ".bands")
    target.write_bytes(np.clip(out, 0, 2).astype("<f4").tobytes())
    period, phase = _beat_grid(out[:, 3])
    pathlib.Path(str(path) + ".beat").write_text(f"{period:.5f} {phase:.5f}\n", encoding="utf-8")
    return target, frames


def _beat_grid(kick):
    """The steady beat that best fits the kick: (seconds per beat, seconds to the first). Tempo from autocorrelation
    between 75 and 120 BPM, then period and phase refined so the grid lands on the most kick energy."""
    import numpy as np
    k = kick - kick.mean()
    ac = np.correlate(k, k, "full")[len(k) - 1:]
    lags = np.arange(len(ac)) / FPS
    window = (lags >= 0.5) & (lags <= 0.8)
    rough = lags[window][np.argmax(ac[window])]

    def landing(period, phase):
        frames = (np.arange(phase, len(kick) / FPS, period) * FPS).astype(int)
        return kick[frames[frames < len(kick)]].mean()

    return max(((landing(p, f), p, f) for p in np.arange(rough - 0.02, rough + 0.02, 0.0005)
                for f in np.arange(0, p, 1 / FPS)))[1:]


def beat(path):
    """(seconds per beat, seconds to the first beat) for a track, or None."""
    target = pathlib.Path(str(path) + ".beat")
    if not target.is_file():
        return None
    period, phase = (float(x) for x in target.read_text(encoding="utf-8").split())
    return period, phase


def load(path):
    """The bands for a track, or None if it has none."""
    target = pathlib.Path(str(path) + ".bands")
    if not target.is_file():
        return None
    values = array.array("f")
    values.frombytes(target.read_bytes())
    return values


def at(values, seconds):
    """(bass, mid, treble, kick) at a time in the track; zeros outside it."""
    frame = int(seconds * FPS)
    if values is None or frame < 0 or (frame + 1) * FIELDS > len(values):
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(values[frame * FIELDS:(frame + 1) * FIELDS])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    written, count = make(sys.argv[1])
    print(f"{count} frames ({count / FPS:.1f} s) written to {written}")
