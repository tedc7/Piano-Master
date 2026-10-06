"""Render every lesson line with one Kokoro voice: total time and MP3 size."""
import glob, os, re, time, yaml, numpy as np, soundfile as sf
from kokoro import KPipeline
texts = set()
for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../content/lessons/*.yaml")):
    for c in yaml.safe_load(open(f))["cards"]:
        for t in [c.get("text")] + [q["text"] for q in c.get("questions") or []] + ([c["contrast"]["text"]] if c.get("contrast") else []):
            if t: texts.add(t)
texts |= {"You did it!", "All right!", "Let's look at it again.", "Perfect!", "Nice listening!", "Good try! Listen again and play it back."}
p = KPipeline(lang_code="a", device="cuda")
t0 = time.time(); total = 0
for i, t in enumerate(sorted(texts)):
    say = re.sub(r"\b[Bb]ass\b", lambda m: f"[{m.group(0)}](/bˈAs/)", t)
    a = np.concatenate([r.audio.cpu().numpy() for r in p(say, voice="af_heart")])
    total += len(a) / 24000
    sf.write(f"full/{i:03d}.mp3", a, 24000, format="MP3")
print(f"{len(texts)} lines, {total/60:.1f} min of speech, rendered in {time.time()-t0:.0f} s")
