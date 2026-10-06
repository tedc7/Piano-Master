"""Intelligibility: transcribe every clip with Whisper and score its word error rate against the written line."""
import json, re, glob, sys
import jiwer, librosa
from faster_whisper import WhisperModel
m = WhisperModel("small.en", device="cpu", compute_type="int8")
lines = json.load(open("lines.json"))
NUM = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five"}
def norm(t):
    t = t.lower().replace("4/4", "four four").replace("3/4", "three four").replace("-", " ")
    t = re.sub(r"[^\w\s']", " ", t)
    return " ".join(NUM.get(w, w) for w in t.split())
voices = sys.argv[1:] or sorted({re.match(r"out/(.+)-" + "(" + "|".join(re.escape(l["id"]) for l in lines) + r")\.wav", f).group(1) for f in glob.glob("out/*.wav")})
for v in voices:
    errs, bad = [], []
    for l in lines:
        segs, _ = m.transcribe(librosa.load(f"out/{v}-{l['id']}.wav", sr=16000)[0], language="en", beam_size=5)
        hyp = " ".join(s.text for s in segs)
        w = jiwer.wer(norm(l["text"]), norm(hyp)) if norm(hyp) else 1.0
        errs.append(w)
        if w > 0.08: bad.append(f"    {l['id']} ({w:.0%}): {hyp.strip()}")
    print(f"{v}: mean WER {sum(errs)/len(errs):.1%}")
    print("\n".join(bad))
