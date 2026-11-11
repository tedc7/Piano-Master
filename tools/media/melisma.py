"""Melismas sung as written (arch §10.5 "Melismas", v0.50).

A melisma is one sung syllable over several notes. YuE2 gets one note per syllable (yue2.py merges a
melisma onto its first pitch), so the take holds one pitch where the staff shows the notes move.
After the take is aligned and chosen, `bend` moves the held pitch onto the written notes in the
vocal stem, at each tempo preset, and leaves the rest of the stem exactly as it was:

  1. the melismas, from the piece's melody as YuE2's export sees it (`melismas`);
  2. the pitch sung over each later note of a melisma, in the stem's mono sum (pYIN);
  3. a bend curve: each later note moves by its written step from the first note, less how far the
     take is from the first note's pitch there (a take doesn't always hold the first pitch);
     raised-cosine slides centred on each note's beat; the bend ends in a gap in the voice (the next
     syllable's consonant) when there is one near the syllable's end (`contour`);
  4. the mono sum resynthesised along the curve by Praat's pitch-synchronous overlap-add
     (parselmouth), which follows a slide even on a sixteenth note and keeps the vowel's colour;
     Each melisma is resynthesised on its own stretch of the take (1.5 s around it): Praat's voicing
     threshold is relative to the loudest part of what it analyses, so on a whole song a quiet
     phrase could come back unbent;
  5. inside each bent melisma the bent mono on both channels, the stereo original everywhere else,
     switched where the two are the same waveform (silence, consonants) or, with no such spot near,
     an equal-power crossfade at the quietest spot (`splice_weights`). Bending each channel by
     itself smears the stereo image (the channels' correlation fell from 0.64 to 0.07).

A piece can choose `media: {melisma: hold}` to keep the held pitch. Results and the listening tests:
feasibility/melisma-probe/RESULTS.md (Nov 10, 2026).
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

import yue2
from common import Piece, nt

SR = 48000
GLIDE_S = 0.08            # the slide from one note of a melisma to the next, at 100% (raised cosine)
GLIDE_SHARE = 0.5         # ...never more than this share of the shorter of the two notes
RETURN_SEARCH_S = 0.10    # the bend ends in a gap in the voice this near the syllable's end
MAX_BEND = 9.0            # semitones: a larger bend means the take sang something else there; left as sung
FLOOR, CEILING, STEP = 90.0, 900.0, 0.005    # Praat's pitch analysis: the voice's range, 5 ms points
ENGINE_NOTE = "melismas bent onto the written notes (Praat overlap-add)"


def method(piece: Piece) -> str:
    """`bend` (the default) or `hold` (the piece's `media: {melisma: hold}`)."""
    m = piece.spec.get("melisma", "bend")
    if m not in ("bend", "hold"):
        raise ValueError(f"{piece.pid}: media.melisma must be bend or hold, not {m!r}")
    return m


def melismas(piece: Piece) -> list[dict]:
    """Every melisma in playback order, in the felt beats YuE2's export uses: {"notes": [the
    syllable's note, then the notes merged into it], "seconds": each note's length at 100%}. Only
    those whose notes change pitch (a tie isn't a melisma)."""
    nota, scale = yue2.felt(piece.nota)
    mel = yue2.merged_melody(nt.unroll(nota))
    spb = 60.0 / piece.bpm / float(scale)
    out, cur = [], None
    for n in mel:
        if n.get("lyric") is not None:
            cur = {"notes": [n]}
            out.append(cur)
        elif cur and cur["notes"][0]["verse"] == n["verse"]:
            last = cur["notes"][-1]
            if last["start"] + last["duration"] == n["start"]:
                cur["notes"].append(n)
    out = [m for m in out if any(x["pitch"] != m["notes"][0]["pitch"] for x in m["notes"][1:])]
    for m in out:
        m["seconds"] = [float(x["duration"]) * spb for x in m["notes"]]
    return out


def stem_time(piece: Piece, pad_song_beats: float, ratio: float = 1.0):
    """felt beat -> seconds in a beat-aligned stem at a preset (time 0 is `pad_song_beats` song
    beats before song beat 0; the preset's stem is the 100% one stretched by 1/ratio)."""
    _, scale = yue2.felt(piece.nota)
    return lambda beat: (float(Fraction(beat)) / float(scale) + pad_song_beats) * 60.0 / piece.bpm / ratio


def pitch_track(y: np.ndarray, sr: int = SR):
    """(midi per 10 ms frame, voiced flags) of a mono signal."""
    import librosa
    f, v, _ = librosa.pyin(y.astype(np.float32), fmin=80, fmax=900, sr=sr, frame_length=2048, hop_length=sr // 100)
    return librosa.hz_to_midi(f), v


def sung(f, v, t0: float, t1: float, lead: float = 0.06, tail: float = 0.03) -> float | None:
    """The pitch sung between t0 and t1 (the median, away from the note's edges); None without voice."""
    if t1 - t0 < lead + tail + 0.04:
        lead, tail = 0.25 * (t1 - t0), 0.15 * (t1 - t0)
    a, b = int((t0 + lead) * 100), int((t1 - tail) * 100)
    seg = f[a:b][v[a:b]] if b > a else np.array([])
    return float(np.nanmedian(seg)) if len(seg) >= 3 else None


def near(d: float) -> float:
    """A pitch difference to the nearest octave: YuE2 often sings an octave from the score."""
    return (d + 6) % 12 - 6


def contour(found: list[dict], at, f, v, glide_s: float = GLIDE_S) -> tuple[list[tuple[float, float]], list[dict]]:
    """The bend as (seconds, semitones) breakpoints, linear between them and 0 outside, and the
    regions it touches (one per melisma bent)."""
    pts: list[tuple[float, float]] = []
    regions = []
    for m in found:
        notes = m["notes"]
        first = notes[0]
        offs, skip = [0.0], False
        for x in notes[1:]:
            s = sung(f, v, at(x["start"]), at(x["start"] + x["duration"]))
            if s is None:
                offs.append(offs[-1])                 # no voice there (a breath): nothing to bend
                continue
            off = (x["pitch"] - first["pitch"]) - near(s - first["pitch"])
            skip |= abs(off) > MAX_BEND
            offs.append(off)
        if skip or not any(abs(o) > 0.25 for o in offs):
            continue
        edges = [at(x["start"]) for x in notes] + [at(notes[-1]["start"] + notes[-1]["duration"])]
        lens = [b - a for a, b in zip(edges, edges[1:])]
        end = edges[-1]
        a, b = int((end - RETURN_SEARCH_S) * 100), int((end + RETURN_SEARCH_S) * 100)
        gap = [k for k in range(max(a, 0), min(b, len(v))) if not v[k]]
        if gap:
            end = min(gap, key=lambda k: abs(k / 100 - edges[-1])) / 100 + 0.005
        steps = [(edges[k], offs[k - 1], offs[k], min(glide_s, GLIDE_SHARE * min(lens[k - 1], lens[k]))) for k in range(1, len(notes))]
        steps.append((end, offs[-1], 0.0, 0.02 if gap else min(glide_s, GLIDE_SHARE * lens[-1])))
        start = steps[0][0] - steps[0][3] / 2
        pts.append((start - 1e-4, 0.0))
        for t, a0, a1, g in steps:
            if a0 == a1:
                continue
            for k in range(13):
                x = k / 12
                pts.append((t - g / 2 + g * x, a0 + (a1 - a0) * (1 - np.cos(np.pi * x)) / 2))
        stop = steps[-1][0] + steps[-1][3] / 2
        pts.append((stop + 1e-4, 0.0))
        regions.append({"start": start, "end": stop, "syllable": first["lyric"]["text"], "songBeat": str(first["start"]),
                        "offsets": [round(o, 2) for o in offs], "endsInGap": bool(gap)})
    pts.sort()
    return pts, regions


def psola(mono: np.ndarray, pts: list[tuple[float, float]], sr: int = SR) -> np.ndarray:
    """The mono signal resynthesised with its pitch moved along the curve (Praat's overlap-add)."""
    import parselmouth
    from parselmouth.praat import call
    if not pts:
        return mono.copy()
    snd = parselmouth.Sound(mono.astype(np.float64), sampling_frequency=sr)
    ts, ss = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    manip = call(snd, "To Manipulation", STEP, FLOOR, CEILING)
    tier = call(manip, "Extract pitch tier")
    n = call(tier, "Get number of points")
    new = call("Create PitchTier", "bent", snd.xmin, snd.xmax)
    for i in range(1, n + 1):
        t = call(tier, "Get time from index", i)
        hz = call(tier, "Get value at index", i)
        call(new, "Add point", t, hz * 2 ** (float(np.interp(t, ts, ss, left=0.0, right=0.0)) / 12))
    call([new, manip], "Replace pitch tier")
    out = call(manip, "Get resynthesis (overlap-add)").values[0]
    if len(out) < len(mono):
        out = np.concatenate([out, mono[len(out):]])
    return out[:len(mono)]


PAD_S = 1.5               # each melisma is resynthesised with this much of the take around it
SEARCH_S = 1.2            # ...and joined within this, so a join is always inside what was resynthesised


def psola_regions(mono: np.ndarray, pts: list[tuple[float, float]], regions: list[dict], sr: int = SR,
                  pad: float = PAD_S) -> np.ndarray:
    """The mono signal with each bent region resynthesised along the curve on its own stretch of
    the take (`pad` seconds around it; overlapping stretches merged). Praat's voicing threshold is
    relative to the loudest part of the sound it analyses: on a whole song a quiet phrase can count
    as unvoiced and come back unbent (Up on the Housetop's "top", just after the muted lead-in,
    Nov 11, 2026), where on its own stretch it is a voice. Elsewhere the signal is the input."""
    out = mono.copy()
    spans: list[list[float]] = []
    for r in sorted(regions, key=lambda r: r["start"]):
        a, b = max(0.0, r["start"] - pad), min(len(mono) / sr, r["end"] + pad)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    for a, b in spans:
        i, j = int(a * sr), int(b * sr)
        seg_pts = [(t - i / sr, x) for t, x in pts if a <= t <= b]
        out[i:j] = psola(mono[i:j], seg_pts, sr)
    return out


def splice_weights(orig: np.ndarray, bent: np.ndarray, regions: list[dict], sr: int = SR, margin: float = 0.03,
                   search: float = SEARCH_S, fade: float = 0.02) -> tuple[np.ndarray, np.ndarray, dict]:
    """Weights for the original and the bent audio: the bent inside each region, the original
    outside it. The resynthesis isn't the same waveform as the input even where the pitch is
    unchanged, so a crossfade inside a vowel would mix two voices out of phase: each region grows
    outward to the nearest spot where the two are the same (40 dB under the sound, or both silent)
    and switches there in 5 ms; with none within `search` seconds, an equal-power crossfade over
    `fade` at the quietest spot it passed. `search` stays inside what `psola_regions` resynthesised."""
    n = min(len(orig), len(bent))
    a, b = orig[:n], bent[:n]
    hop = sr // 200
    k = n // hop
    ea = (a[:k * hop].reshape(k, hop) ** 2).mean(axis=1)
    ed = ((a[:k * hop] - b[:k * hop]).reshape(k, hop) ** 2).mean(axis=1)
    same = ed <= 1e-4 * ea + 1e-9
    same = same & np.roll(same, 1) & np.roll(same, -1)
    w = np.zeros(n)
    loose = np.zeros(n, bool)
    stats = {"clean": 0, "crossfaded": 0}
    spans = []
    for r in regions:
        ends = []
        for t, step in ((r["start"] - margin, -1), (r["end"] + margin, 1)):
            i = min(max(int(t * sr / hop), 0), k - 1)
            j, quiet = i, i
            while 0 < j < k - 1 and abs(j - i) * hop / sr < search and not same[j]:
                if ea[j] < ea[quiet]:
                    quiet = j
                j += step
            clean = bool(same[j])
            stats["clean" if clean else "crossfaded"] += 1
            ends.append(((j if clean else quiet) * hop + hop // 2, clean))
        spans.append(ends)
    for (s0, _), (s1, _) in spans:
        w[s0:s1] = 1.0
    for (s0, c0), (s1, c1) in spans:
        for s, c, rising in ((s0, c0, True), (s1, c1, False)):
            m = int((0.005 if c else fade) * sr / 2)
            lo, hi = max(0, s - m), min(n, s + m)
            if hi - lo < 2 or (w[lo] == 1.0 and w[hi - 1] == 1.0):
                continue
            ramp = np.linspace(0, 1, hi - lo)
            w[lo:hi] = ramp if rising else ramp[::-1]
            loose[lo:hi] = not c
    stats["seconds"] = round(float(w.sum() / sr), 1)
    wa = np.where(loose, np.cos(w * np.pi / 2), 1 - w)
    wb = np.where(loose, np.sin(w * np.pi / 2), w)
    return wa, wb, stats


def on_pitch(notes: list[dict], at, f, v) -> list[int]:
    """[notes on pitch, notes with a voice to measure]: within half a semitone, any octave."""
    ok = tot = 0
    for x in notes:
        s = sung(f, v, at(x["start"]), at(x["start"] + x["duration"]))
        if s is None:
            continue
        tot += 1
        ok += int(abs(near(s - x["pitch"])) <= 0.5)
    return [ok, tot]


def melody(piece: Piece) -> list[dict]:
    """The written melody in playback order, ties merged, in felt beats (melismas and all)."""
    nota, _ = yue2.felt(piece.nota)
    return yue2.merged_melody(nt.unroll(nota))


def bend(y: np.ndarray, sr: int, piece: Piece, found: list[dict], at, ratio: float = 1.0) -> tuple[np.ndarray, dict]:
    """One preset's vocal (frames x channels) with its melismas bent, and what was done. `at` maps a
    felt beat to seconds in this stem."""
    assert sr == SR, f"the aligned stems are {SR} Hz"
    mid = y.mean(axis=1) if y.ndim > 1 else y
    f, v = pitch_track(mid, sr)
    later = [x for m in found for x in m["notes"][1:]]
    rep = {"melismas": len(found), "notesOnPitchBefore": on_pitch(later, at, f, v),
           "melodyOnStaffBefore": on_pitch(melody(piece), at, f, v)}
    pts, regions = contour(found, at, f, v, glide_s=GLIDE_S / ratio)
    rep["bent"] = len(regions)
    if not regions:
        return y, {**rep, "notesOnPitch": rep["notesOnPitchBefore"], "melodyOnStaff": rep["melodyOnStaffBefore"]}
    bent = psola_regions(mid, pts, regions, sr)
    wa, wb, joins = splice_weights(mid, bent, regions, sr)
    n = len(wa)
    if y.ndim > 1:
        out = y.copy()
        out[:n] = y[:n] * wa[:, None] + bent[:n, None] * wb[:, None]
    else:
        out = y.copy()
        out[:n] = y[:n] * wa + bent[:n] * wb
    m2 = out.mean(axis=1) if out.ndim > 1 else out
    f2, v2 = pitch_track(m2, sr)
    return out, {**rep, "joins": joins, "notesOnPitch": on_pitch(later, at, f2, v2), "melodyOnStaff": on_pitch(melody(piece), at, f2, v2),
                 "leftAsSung": len(found) - len(regions)}
