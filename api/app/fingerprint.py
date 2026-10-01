"""Melody fingerprint (arch §10.8): catches duplicates and deleted songs, even in another key,
tempo or arrangement.

1. Melody line: notes marked as melody (or the highest right-hand note at each moment), in
   playback order, with ties merged and grace notes dropped.
2. Intervals: the semitone steps between consecutive melody notes (key and tempo drop out).
3. Fingerprint: the set of runs of 6 consecutive intervals, as short hashes, leaving out a run
   of one note repeated (it names no tune: v0.27, after beginner studies on Middle C matched each
   other). A song's fingerprint is the union over its arrangements.
4. Similarity: shared runs / runs in the smaller fingerprint (a short excerpt against a full song).
   A fingerprint of fewer than MIN_RUNS runs is too little to judge: no verdict.
5. Rules (first version, tuned in M7): 0.8+ the same song; 0.6-0.8 a possible duplicate.

Pure Python on the §5 notation: the song import skill checks with it on the dev box, and the
server's intake will use the same code (M7).
"""
from __future__ import annotations

import hashlib

RUN = 6
MIN_RUNS = 3
SAME, POSSIBLE = 0.8, 0.6


def melody(nota: dict) -> list[int]:
    """The melody's pitches in playback order (repeats unrolled), ties merged, graces dropped."""
    notes = [n for n in nota["notes"] if not n.get("grace")]
    marked = [n for n in notes if n.get("isMelody")]
    if marked:
        line = marked
    else:
        right = [n for n in notes if n["hand"] == "R"] or notes
        top: dict[float, dict] = {}
        for n in right:
            k = round(float(n["start"]), 4)
            if k not in top or n["pitch"] > top[k]["pitch"]:
                top[k] = n
        line = [top[k] for k in sorted(top)]
    measures = nota["measures"]
    order = nota.get("playbackOrder") or [{"measure": i} for i in range(len(measures))]
    by_measure: dict[int, list[dict]] = {}
    for n in line:
        for i, m in enumerate(measures):
            if m["start"] - 1e-6 <= n["start"] < m["start"] + m["duration"] - 1e-6:
                by_measure.setdefault(i, []).append(n)
                break
    out: list[int] = []
    tied = False
    for p in order:
        for n in sorted(by_measure.get(p["measure"], []), key=lambda n: n["start"]):
            if tied and out and out[-1] == n["pitch"]:
                tied = bool(n.get("tieToNext"))
                continue                         # held on through a tie: one note
            out.append(int(n["pitch"]))
            tied = bool(n.get("tieToNext"))
    return out


def fingerprint(nota: dict) -> set[str]:
    ps = melody(nota)
    steps = [b - a for a, b in zip(ps, ps[1:])]
    return {hashlib.sha1(",".join(map(str, steps[i:i + RUN])).encode()).hexdigest()[:12]
            for i in range(len(steps) - RUN + 1) if any(steps[i:i + RUN])}


def similarity(a: set[str], b: set[str]) -> float:
    if min(len(a), len(b)) < MIN_RUNS:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def verdict(score: float) -> str | None:
    return "same song" if score >= SAME else "possible duplicate" if score >= POSSIBLE else None
