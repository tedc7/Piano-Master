"""Trial: render lesson lines with Kokoro-82M in a few voices, and print the phonemes it chose."""
import json, sys, time
import numpy as np, soundfile as sf, torch
from kokoro import KPipeline

lines = json.load(open("lines.json"))
voices = sys.argv[1].split(",") if len(sys.argv) > 1 else ["af_heart", "af_bella", "bf_emma", "am_michael"]
speed = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
field = sys.argv[3] if len(sys.argv) > 3 else "text"
tag = sys.argv[4] if len(sys.argv) > 4 else ""
pipes = {}
for v in voices:
    lang = v[0]                       # a: American English, b: British English
    pipes.setdefault(lang, KPipeline(lang_code=lang, device="cuda"))
    t0 = time.time(); total = 0.0
    for l in lines:
        text = l.get(field) or l["text"]
        chunks, phon = [], []
        for r in pipes[lang](text, voice=v, speed=speed):
            chunks.append(r.audio.cpu().numpy()); phon.append(r.phonemes)
        a = np.concatenate(chunks)
        total += len(a) / 24000
        sf.write(f"out/kokoro-{v}{tag}-{l['id']}.wav", a, 24000)
        if v == voices[0]: print(l["id"], "|", " ".join(phon))
    print(f"{v}: {total:.1f} s of speech in {time.time() - t0:.1f} s")
