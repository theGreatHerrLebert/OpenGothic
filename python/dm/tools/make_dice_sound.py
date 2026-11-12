"""The rattle of dice for a thrown gamble (graph.py "dice"): shaken in the fist, thrown on a table, rolling out.

    python3 python/dm/tools/make_dice_sound.py python/dm_runtime/assets/sounds/wuerfel.wav
"""
import sys, wave
import numpy as np
RATE = 22050
rng = np.random.default_rng(3)
out = np.zeros(int(RATE * 1.6))

def click(at, gain, freq, length=0.02):
    n = int(RATE * length)
    t = np.arange(n) / RATE
    noise = rng.normal(0, 1, n)
    tone = np.sin(2 * np.pi * freq * t) * 0.6 + np.sin(2 * np.pi * freq * 1.7 * t) * 0.3
    env = np.exp(-t * 420)
    i = int(at * RATE)
    seg = (noise * 0.5 + tone) * env * gain
    out[i:i + n] += seg[:len(out) - i]

def thud(at, gain):
    n = int(RATE * 0.06); t = np.arange(n) / RATE
    seg = np.sin(2 * np.pi * 140 * t) * np.exp(-t * 60) * gain
    i = int(at * RATE); out[i:i + n] += seg[:len(out) - i]

# shaking in the fist: muffled clicks
for k in range(7):
    click(0.05 + k * 0.07 + rng.uniform(-0.01, 0.01), 0.25, rng.uniform(1800, 2600))
# thrown: impact and tumbling, ticks closer together and quieter
thud(0.62, 0.7)
t, gap, gain = 0.62, 0.09, 0.9
while gain > 0.08:
    for die in range(2):
        click(t + rng.uniform(0, 0.02), gain * rng.uniform(0.7, 1.0), rng.uniform(2800, 4200))
    t += gap; gap *= 0.78; gain *= 0.72
out /= np.max(np.abs(out))
out = np.tanh(out * 4.0) / np.tanh(4.0)   # squeezed: short clicks carry little energy, so make them loud
out *= 0.97
data = (out * 32767).astype("<i2").tobytes()
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(data)
print("written", len(out) / RATE, "s")
