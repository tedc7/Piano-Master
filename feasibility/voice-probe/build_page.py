"""Build the listening page: level every render to the same loudness, write MP3s, fill the page's data."""
import json, os, sys
import numpy as np, soundfile as sf, pyloudnorm as pyln

OUT = sys.argv[1]
os.makedirs(f"{OUT}/audio", exist_ok=True)
lines = json.load(open("lines.json"))
VOICES = [
    ("kokoro-af_heart", "Kokoro · Heart", "US English, woman. Kokoro's best-rated voice."),
    ("kokoro-af_heart-slow", "Kokoro · Heart, slower", "The same voice at 90% speed, for young listeners."),
    ("kokoro-af_heart-slow80", "Kokoro · Heart, 80%", "The same voice at 80% speed."),
    ("kokoro-af_bella", "Kokoro · Bella", "US English, woman. Brighter."),
    ("kokoro-bf_emma", "Kokoro · Emma", "British English, woman."),
    ("kokoro-am_michael", "Kokoro · Michael", "US English, man."),
    ("chatterbox-default", "Chatterbox", "US English, woman. A larger model with more expression."),
]
voices, stats = [], {}
for key, name, note in VOICES:
    have = []
    for l in lines:
        src = f"out/{key}-{l['id']}.wav"
        if not os.path.exists(src):
            continue
        a, sr = sf.read(src)
        meter = pyln.Meter(sr)
        a = pyln.normalize.loudness(a, meter.integrated_loudness(a), -18.0)
        a = a / max(1.0, np.abs(a).max() / 0.95)
        sf.write(f"{OUT}/audio/{key}-{l['id']}.mp3", a, sr, format="MP3")
        have.append(l["id"])
        stats[key] = stats.get(key, 0.0) + len(a) / sr
    if have:
        voices.append({"key": key, "name": name, "note": note})
data = {"voices": voices, "lines": [{"id": l["id"], "text": l["text"]} for l in lines]}
page = open("page.html").read().replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
open(f"{OUT}/index.html", "w").write(page)
print({k: round(v, 1) for k, v in stats.items()})
