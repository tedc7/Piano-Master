"""Harmony check: does the aligned backing play the song's written chords (the chords under the
child's piano part)? Needed because the chord-free ('mel', cot=melody) takes let YuE2 choose the
harmony itself.

    .venv/bin/python harmony.py                    # every aligned take -> build/harmony.json, table on stdout
    .venv/bin/python harmony.py jeanie-mel-s2

For each chord span (from the song's chord symbols, on the aligned 100% backing's score time):
  - chord-tone share: the share of the backing's pitch-class energy on the chord's tones;
  - match: the written chord is the best of the 24 major/minor triads for that span (a relative
    minor/major sharing two tones can win on a sparse bar, so this is a rough rate, compared
    between takes of the same song).
"""
from __future__ import annotations

import json
import re
import sys
from fractions import Fraction
from pathlib import Path

import librosa
import numpy as np
from music21 import harmony

HERE = Path(__file__).resolve().parent
RENDERS, BUILD = HERE / "renders", HERE / "build"
SR, HOP = 22050, 2048
TAKE = re.compile(r"(.+)-(intro|fake|syl|mel)(?:-folk|-spec)?(?:-s\d+)?")
TRIADS = [(r, q) for r in range(12) for q in ((0, 4, 7), (0, 3, 7))]


def chord_pcs(symbol):
    cs = harmony.ChordSymbol(re.sub(r"(^|/)([A-G])b", r"\1\2-", symbol))   # music21 writes flats as '-'
    return sorted({p.pitchClass for p in cs.pitches})


def check(folder: Path, mode: str):
    m = TAKE.fullmatch(folder.name)
    sid, variant = m.group(1), m.group(2)
    amap = json.loads((BUILD / sid / "yue2" / f"abcmap-{variant}.json").read_text())
    if "chords" not in amap:   # older map: the syl take's map has the same song chords
        amap["chords"] = json.loads((BUILD / sid / "yue2" / "abcmap-syl.json").read_text())["chords"]
    pad, bpm = float(Fraction(amap["pad_beats"])), amap["bpm"]
    y, _ = librosa.load(folder / f"aligned-{mode}" / "accompaniment_100.flac", sr=SR, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP)
    t = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=SR, hop_length=HOP)
    song_end = float(Fraction(amap["song_length_beats"]))
    chords = amap["chords"]
    shares, matches, weights = [], [], []
    for i, c in enumerate(chords):
        b0 = float(Fraction(c["song_beat"]))
        b1 = float(Fraction(chords[i + 1]["song_beat"])) if i + 1 < len(chords) else song_end
        s0, s1 = (b0 + pad) * 60 / bpm, (b1 + pad) * 60 / bpm
        sel = (t >= s0 + 0.05) & (t < s1 - 0.05)
        if sel.sum() < 2:
            continue
        v = chroma[:, sel].mean(axis=1)
        if v.sum() <= 0:
            continue
        v = v / v.sum()
        pcs = chord_pcs(c["symbol"])
        shares.append(float(v[pcs].sum()) / len(pcs) * 3)      # normalised to a 3-tone chord
        best = max(TRIADS, key=lambda rq: sum(v[(rq[0] + k) % 12] for k in rq[1]))
        tri = {(best[0] + k) % 12 for k in best[1]}
        matches.append(tri <= set(pcs))
        weights.append(s1 - s0)
    w = np.array(weights)
    return {"take": folder.name, "mode": mode, "spans": len(w),
            "chord_tone_share": round(float(np.average(shares, weights=w)), 3),
            "match": round(float(np.average(matches, weights=w)), 3)}


def main(argv):
    folders = [RENDERS / a for a in argv] if argv else sorted(p for p in RENDERS.iterdir() if TAKE.fullmatch(p.name))
    out_path = BUILD / "harmony.json"
    results = json.loads(out_path.read_text()) if out_path.is_file() else {}
    for folder in folders:
        for mode in ("melody", "words", "dtw"):
            if (folder / f"aligned-{mode}" / "accompaniment_100.flac").is_file():
                r = check(folder, mode)
                results[f"{folder.name}/{mode}"] = r
                print(f"{r['take']:40s} {mode:6s} chord-tone share {r['chord_tone_share']:.2f}  written chord best {r['match']:.0%}")
    out_path.write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
