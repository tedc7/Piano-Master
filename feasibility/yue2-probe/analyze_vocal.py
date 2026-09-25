"""Timing and pitch check of a rendered vocal against its score (first cut of arch §10.5 steps 3-4).

Run with the engine venv (needs librosa):
    ~/engines/yue2/.venv/bin/python analyze_vocal.py results/garden-morning [results/...]

For each render folder (with score.abc and vocals.flac):
  1. Track the sung pitch (pYIN) and build the score's pitch timeline from the Vocal voice.
  2. Align them with DTW on a pitch-class cost, which stays monotonic, so a repeating
     melody can't be matched to the wrong repeat.
  3. Timing: for each score note, where it lands in the audio (offset = audio - score;
     negative = sung earlier than the score).
  4. Pitch (§10.5 rule): a note passes when the median sung pitch over its aligned span is
     the right pitch class (nearest semitone, any octave). Reported twice: after DTW
     alignment (what §10.5 intends: align, then check) and at the single best constant
     offset (no warping, a stricter baseline).
Writes <render>/analysis.json and prints a summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import librosa
import numpy as np

from build_listen_site import abc_tools

SR, HOP = 22050, 512
FPS = SR / HOP


def score_notes(abc_text):
    score = abc_tools().parse_abc(abc_text)
    spq = 60.0 / score.bpm
    return [(float(on) * spq, float(on + d) * spq, midi) for on, midi, d in score.voices["Vocal"].notes]


def score_track(notes, n_frames):
    ref = np.full(n_frames, np.nan)
    for start, end, midi in notes:
        ref[int(start * FPS):min(int(end * FPS), n_frames)] = midi
    return ref


def pc_cost(a, b):
    """Cost between two MIDI-pitch sequences: pitch-class distance, voicing mismatch."""
    A, B = a[:, None], b[None, :]
    d = np.abs((A - B) % 12)
    d = np.minimum(d, 12 - d) / 6.0                      # 0 same class .. 1 tritone
    va, vb = ~np.isnan(A), ~np.isnan(B)
    cost = np.where(va & vb, d, np.where(va | vb, 0.6, 0.0))
    return np.nan_to_num(cost, nan=0.6).astype(np.float32)


def note_pitch_ok(sung, frames, target):
    vals = sung[frames]
    vals = vals[~np.isnan(vals)]
    if len(vals) < 2:
        return None                                       # nothing sung there
    return int(round(np.median(vals))) % 12 == target % 12


def analyze(folder: Path):
    notes = score_notes((folder / "score.abc").read_text(encoding="utf-8"))
    y, _ = librosa.load(folder / "vocals.flac", sr=SR, mono=True)
    f0, voiced, _ = librosa.pyin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
                                 sr=SR, hop_length=HOP)
    # Energy gate: the separated stem has faint instrument bleed (~-75 dBFS) that pYIN
    # happily tracks; frames 40 dB below the stem's loud passages count as unsung.
    rms_db = librosa.amplitude_to_db(librosa.feature.rms(y=y, hop_length=HOP)[0], ref=1.0)
    rms_db = np.pad(rms_db, (0, max(0, len(f0) - len(rms_db))), constant_values=-120)[:len(f0)]
    loud = rms_db > np.percentile(rms_db, 95) - 40
    sung = np.where(voiced & loud, librosa.hz_to_midi(f0), np.nan)
    ref = score_track(notes, max(len(sung), int(notes[-1][1] * FPS) + 1))

    # DTW alignment: path of (score frame, audio frame)
    _, path = librosa.sequence.dtw(C=pc_cost(ref, sung), subseq=False)
    path = path[::-1]
    to_audio = {}
    for i, j in path:
        to_audio.setdefault(i, []).append(j)

    per_note, offsets = [], []
    for start, end, midi in notes:
        i0, i1 = int(start * FPS), max(int(start * FPS) + 1, int(end * FPS))
        frames = sorted({j for i in range(i0, min(i1, len(ref))) for j in to_audio.get(i, [])})
        onset_audio = max(to_audio.get(i0, [i0])) / FPS   # end of any run the path spends on this frame
        offsets.append(onset_audio - start)
        per_note.append({"score_s": round(start, 2), "offset_s": round(onset_audio - start, 2), "midi": midi,
                         "pitch_ok": note_pitch_ok(sung, np.array(frames, dtype=int), midi) if frames else None})

    # Baseline: best single constant shift, no warping
    best = None
    for shift in np.arange(-5.0, 5.0 + 1e-9, 0.02):
        hits = total = 0
        for start, end, midi in notes:
            a, b = int((start + shift) * FPS), int((end + shift) * FPS)
            if a < 0 or b > len(sung):
                continue
            ok = note_pitch_ok(sung, np.arange(a, max(b, a + 1)), midi)
            total += 1
            hits += bool(ok)
        if total and (best is None or hits / total > best[1]):
            best = (round(float(shift), 2), hits / total)

    judged = [n["pitch_ok"] for n in per_note if n["pitch_ok"] is not None]
    offs = np.array(offsets)
    result = {
        "notes": len(notes),
        "pitch_match_aligned": round(sum(judged) / len(judged), 3) if judged else None,
        "notes_not_sung": sum(n["pitch_ok"] is None for n in per_note),
        "pitch_match_constant_shift": {"shift_s": best[0], "fraction": round(best[1], 3)} if best else None,
        # start/end = median over the first/last 5 notes (single edge notes are unreliable in DTW)
        "timing": {"first_note_offset_s": round(float(np.median(offs[:5])), 2),
                   "last_note_offset_s": round(float(np.median(offs[-5:])), 2),
                   "median_offset_s": round(float(np.median(offs)), 2),
                   "drift_s": round(float(np.median(offs[-5:]) - np.median(offs[:5])), 2),
                   "spread_s": round(float(np.percentile(offs, 95) - np.percentile(offs, 5)), 2)},
        "per_note": per_note,
    }
    (folder / "analysis.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    for arg in sys.argv[1:]:
        r = analyze(Path(arg))
        t = r["timing"]
        print(f"{Path(arg).name}: {r['notes']} notes | pitch OK {r['pitch_match_aligned']:.0%} after alignment "
              f"({r['notes_not_sung']} not sung), {r['pitch_match_constant_shift']['fraction']:.0%} at best constant shift "
              f"{r['pitch_match_constant_shift']['shift_s']:+.2f}s | timing: first {t['first_note_offset_s']:+.2f}s, "
              f"last {t['last_note_offset_s']:+.2f}s, drift {t['drift_s']:+.2f}s, 5-95% spread {t['spread_s']:.2f}s")


if __name__ == "__main__":
    main()
