"""Run Kokoro's text-to-phonemes on every lesson line and list words that are likely misread."""
import glob, os, re, yaml
from misaki import en
g2p = en.G2P(trf=False, british=False, fallback=None)
texts = set()
for f in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../content/lessons/*.yaml")):
    for c in yaml.safe_load(open(f))["cards"]:
        for t in [c.get("text")] + [q["text"] for q in c.get("questions") or []] + ([c["contrast"]["text"]] if c.get("contrast") else []):
            if t: texts.add(t)
hits = {}
for t in sorted(texts):
    _, toks = g2p(t)
    for tk in toks:
        w, p = tk.text, tk.phonemes or ""
        bad = (w.lower() == "bass" and "æ" in p) or (w == "A" and p in ("ɐ", "ə")) or not p
        if bad: hits.setdefault((w, p), []).append(t[:90])
for (w, p), ts in hits.items():
    print(f"{w!r} -> {p!r}: {len(ts)} lines, e.g. {ts[0]}")
print(len(texts), "lines scanned")
