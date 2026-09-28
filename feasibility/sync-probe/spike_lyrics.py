"""Spike: does lyric forced alignment catch what the pitch-only aligner got wrong?

    .venv/bin/python spike_lyrics.py [take ...]

For each take in renders/ (raw vocals.flac), aligns the known words (lyric_align.py in .fa), then
compares each word's sung start with where the pitch-based time map (alignment.json "map", the
map actually used for the page) puts that word. Prints the first words and every stretch where
the two disagree by more than 0.3 s, and writes renders/<take>/lyric_spike.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RENDERS, BUILD = HERE / "renders", HERE / "build"


def lyric_times(audio, words, out):
    wf = out.with_suffix(".words.json")
    wf.write_text(json.dumps(words))
    subprocess.run([str(HERE / ".fa/bin/python"), str(HERE / "lyric_align.py"), str(audio), str(wf), str(out)],
                   check=True, capture_output=True)
    wf.unlink()
    return json.loads(out.read_text())


def spike(take):
    folder = RENDERS / take
    sid, _, variant = take.rpartition("-")
    amap = json.loads((BUILD / sid / "yue2" / f"abcmap-{variant}.json").read_text())
    bpm = amap["bpm"]
    words = [{**w, "score_s": float(Fraction(w["beat"])) * 60 / bpm} for w in amap["words"]]
    got = lyric_times(folder / "vocals.flac", words, folder / "lyric_spike.json")
    m = np.array(json.loads((folder / "alignment.json").read_text())["map"])     # [audio, score]
    # where the pitch map puts each word (constant offset outside the map, as the warp does)
    def pitch_audio(s):
        if s <= m[0, 1]:
            return s + (m[0, 0] - m[0, 1])
        if s >= m[-1, 1]:
            return s + (m[-1, 0] - m[-1, 1])
        return float(np.interp(s, m[:, 1], m[:, 0]))
    rows = []
    for w in got:
        pa = pitch_audio(w["score_s"])
        rows.append({**w, "pitch_map_s": round(pa, 3), "diff_s": round(w["start"] - pa, 3)})
    (folder / "lyric_spike.json").write_text(json.dumps(rows, indent=1) + "\n")
    diffs = np.array([r["diff_s"] for r in rows])
    confs = np.array([r["conf"] for r in rows])
    print(f"\n== {take}: {len(rows)} words | lyric vs pitch map: median |diff| {np.median(np.abs(diffs)):.2f} s, "
          f"words off > 0.3 s: {int((np.abs(diffs) > 0.3).sum())} | conf median {np.median(confs):.2f}, "
          f"lowest {np.sort(confs)[:3].round(2).tolist()}")
    for r in rows[:8]:
        print(f"   {r['word']:10s} score {r['score_s']:6.2f}  sung {r['start']:6.2f}-{r['end']:6.2f}  "
              f"pitch map {r['pitch_map_s']:6.2f}  diff {r['diff_s']:+.2f}  conf {r['conf']:.2f}")
    # stretches of disagreement
    bad = np.abs(diffs) > 0.3
    i = 0
    while i < len(rows):
        if bad[i]:
            j = i
            while j + 1 < len(rows) and bad[j + 1]:
                j += 1
            if j - i >= 1:
                print(f"   disagree words {i}-{j} ({rows[i]['word']} .. {rows[j]['word']}), score {rows[i]['score_s']:.1f}-"
                      f"{rows[j]['score_s']:.1f} s, lyric minus pitch map {np.median(diffs[i:j + 1]):+.2f} s")
            i = j + 1
        else:
            i += 1


if __name__ == "__main__":
    takes = sys.argv[1:] or sorted(p.name for p in RENDERS.iterdir() if (p / "alignment.json").is_file() and p.name != "v1")
    for t in takes:
        spike(t)
