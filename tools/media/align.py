"""Align a YuE2 take to the arrangement's beat grid and check it (arch §10.5 steps 3-5, 7-8).

For one take (vocals.flac, accompaniment.flac and the score.abc YuE2 sang from):
  1. A rough map, in one of two modes (both kept: each won some takes in the sync probe):
       dtw   - DTW of the sung pitch against the score's pitch line (best when YuE2 put words on
               other notes: the melody stays exact);
       words - lyric forced alignment of the known words (best when a repeated melody or the
               lead-in fools the pitch map).
  2. In 3-second windows every 0.5 s, the shift that best lines up the sung pitch curve with the
     score's, within +-0.35 s of the rough map; reliable windows become the time map.
  3. Rubber Band R3 warps the vocal with that map; what's left is measured and the map corrected
     once (Rubber Band lags ~25 ms behind a dense map). Before the first map point the offset is
     held constant. The vocal is muted before the song's first note (the "Oh" lead-in).
  4. Checks on the aligned 100% vocal:
       timing  - a sustained offset (the median over a phrase) above 50 ms fails;
       pitch   - at least 90% of notes on the right pitch (any octave);
       words   - words more than 0.3 s from their notes, found phrase by phrase in the aligned vocal
                 (over 10%, or a stretch of 1.5 s or more in the first 15 s, fails; a shorter one
                 is flagged for the listen), and the first word sung;
       melody  - stretches of 4+ notes sung on the wrong pitch (1.5 s or more fails; shorter is a flag);
       tuning  - within 10 cents of A440 (FluidSynth backings are exact; v0.22);
       bleed   - YuE2 backing left in the demixed vocal: the accompaniment stem found in it, its level
                 against the vocal (v0.22; first threshold -25 dB, tune by listening).
  5. Tempo versions: the same map at 90, 75 and 50% (and the accompaniment too when YuE2's
     backing is kept).
Prototype: feasibility/sync-probe/align.py.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from common import FA_PYTHON, HERE, RUBBERBAND, YUE2_SCRIPTS

sys.path.insert(0, str(YUE2_SCRIPTS))
import abc_tools  # noqa: E402

SR = 22050            # analysis rate
HOP = 256             # 11.6 ms analysis frames
HOP_DTW = 1024        # 46 ms frames for the rough DTW pass
OUT_SR = 48000
WIN = 3.0             # seconds of score per alignment window
MAX_SHIFT = 0.35      # the windows search +-0.35 s around the rough map
MODES = ("dtw", "words")
PASS = {"phraseOffsetMs": 50, "pitch": 0.9, "wordsOff": 0.1, "tuningCents": 10, "bleedDb": -25, "stretchS": 1.5,
        "octaveHeldS": 0.8, "heard": 0.92, "heardFail": 0.8}


# ---------------------------------------------------------------- score and pitch

def score_notes(abc_path: Path):
    score = abc_tools.parse_abc(abc_path.read_text().rstrip("\n"))
    spq = 60.0 / score.bpm
    notes = [(float(on) * spq, float(on + d) * spq, midi) for on, midi, d in score.voices["Vocal"].notes]
    return notes, score.bpm


def sung_pitch(y, hop=HOP):
    f0, voiced, _ = librosa.pyin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
                                 sr=SR, hop_length=hop, frame_length=2048)
    rms_db = librosa.amplitude_to_db(librosa.feature.rms(y=y, hop_length=hop)[0], ref=1.0)
    rms_db = np.pad(rms_db, (0, max(0, len(f0) - len(rms_db))), constant_values=-120)[:len(f0)]
    loud = rms_db > np.percentile(rms_db, 95) - 40          # stem bleed sits ~-75 dBFS
    return np.where(voiced & loud, librosa.hz_to_midi(f0), np.nan)


def load_mono(path):
    y, _ = librosa.load(path, sr=SR, mono=True)
    return y


def pc_cost(a, b):
    A, B = a[:, None], b[None, :]
    d = np.abs((A - B) % 12)
    d = np.minimum(d, 12 - d) / 6.0
    va, vb = ~np.isnan(A), ~np.isnan(B)
    cost = np.where(va & vb, d, np.where(va | vb, 0.6, 0.0))
    return np.nan_to_num(cost, nan=0.6).astype(np.float32)


def rough_onsets(notes, sung_coarse):
    """DTW between the score's pitch line and the sung pitch: each note's rough audio onset."""
    fps = SR / HOP_DTW
    ref = np.full(int(notes[-1][1] * fps) + 1, np.nan)
    for start, end, midi in notes:
        ref[int(start * fps):max(int(start * fps) + 1, int(end * fps))] = midi
    _, path = librosa.sequence.dtw(C=pc_cost(ref, sung_coarse), subseq=False)
    to_audio = {}
    for i, j in path[::-1]:
        to_audio.setdefault(i, []).append(j)
    return np.array([max(to_audio.get(int(s * fps), [int(s * fps)])) / fps for s, _, _ in notes])


def smooth_offsets(offsets, k=9):
    out = np.copy(offsets)
    for i in range(len(offsets)):
        out[i] = np.median(offsets[max(0, i - k // 2):i + k // 2 + 1])
    return out


def score_pitch_at(notes, times):
    starts = np.array([s for s, _, _ in notes])
    ends = np.array([e for _, e, _ in notes])
    midi = np.array([m for _, _, m in notes], dtype=float)
    idx = np.searchsorted(starts, times, side="right") - 1
    ok = (idx >= 0) & (times < ends[np.clip(idx, 0, None)])
    return np.where(ok, midi[np.clip(idx, 0, None)], np.nan)


def local_offsets(sung, notes, centers, predict, win=WIN, max_shift=MAX_SHIFT, scale=1.0):
    """For each window of score time around each center, the shift (s, audio time) that best lines
    up the sung pitch with the score's there, around the predicted audio time. Windows with fewer
    than 2 pitch changes, a poor fit or a second fit almost as good are unreliable."""
    fps = SR / HOP
    shifts = np.arange(-int(max_shift / scale * fps), int(max_shift / scale * fps) + 1)
    results = []
    for c in centers:
        tau = np.arange(c - win / 2, c + win / 2, 1 / fps)
        ref = score_pitch_at(notes, tau)
        changes = sum(1 for i in range(1, len(notes))
                      if c - win / 2 < notes[i][0] < c + win / 2 and notes[i][2] != notes[i - 1][2])
        base = predict(tau) * fps
        idx = np.round(base[None, :] + shifts[:, None]).astype(int)
        valid = (idx >= 0) & (idx < len(sung))
        got = np.where(valid, sung[np.clip(idx, 0, len(sung) - 1)], np.nan)
        R = np.broadcast_to(ref, got.shape)
        d = np.abs((got - R) % 12)
        d = np.minimum(d, 12 - d) / 6.0
        both, one = ~np.isnan(got) & ~np.isnan(R), np.isnan(got) ^ np.isnan(R)
        cost = np.where(both, d, np.where(one, 0.3, 0.0)).mean(axis=1)
        b = int(np.argmin(cost))
        frac = 0.0
        if 0 < b < len(cost) - 1:
            den = cost[b - 1] - 2 * cost[b] + cost[b + 1]
            frac = 0.5 * (cost[b - 1] - cost[b + 1]) / den if den > 1e-9 else 0.0
        delta = (shifts[b] + float(np.clip(frac, -0.5, 0.5))) / fps
        far = np.abs(shifts - shifts[b]) > int(0.15 * fps / scale)
        unique = cost[far].min() - cost[b] if far.any() else 1.0
        reliable = changes >= 2 and cost[b] < 0.3 and unique > 0.005 and 0 < b < len(cost) - 1
        results.append({"score_s": float(c), "audio_s": float(predict(np.array([c]))[0] + delta),
                        "delta_s": float(delta), "cost": float(cost[b]), "reliable": bool(reliable)})
    return results


def lyric_words(audio, words):
    """Word start/end/confidence in the audio (lyric_align.py, in its own venv)."""
    with tempfile.TemporaryDirectory() as tmp:
        wf, of = Path(tmp) / "w.json", Path(tmp) / "o.json"
        wf.write_text(json.dumps(words))
        subprocess.run([str(FA_PYTHON), str(HERE / "lyric_align.py"), str(audio), str(wf), str(of)],
                       check=True, capture_output=True)
        return json.loads(of.read_text())


def forced(w):
    return w["conf"] <= -1.5 or w["end"] - w["start"] < 0.04


def lyric_anchors(lw):
    """(audio_s, score_s) from confidently aligned words, minus isolated spikes, in order."""
    good = [w for w in lw if not forced(w)]
    off = [w["start"] - w["score_s"] for w in good]
    keep = [w for k, w in enumerate(good) if not (0 < k < len(good) - 1 and abs(off[k] - off[k - 1]) > 0.4
            and abs(off[k] - off[k + 1]) > 0.4 and abs(off[k - 1] - off[k + 1]) < 0.4)]
    n = len(keep)
    best, prev = [1] * n, [-1] * n
    for i in range(n):
        for j in range(max(0, i - 40), i):
            if keep[j]["start"] < keep[i]["start"] and keep[j]["score_s"] < keep[i]["score_s"] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = int(np.argmax(best)) if n else -1
    chain = []
    while i >= 0:
        chain.append(keep[i])
        i = prev[i]
    return [(w["start"], w["score_s"]) for w in reversed(chain)]


def map_fn(pts):
    """score time -> audio time through (audio, score) points, constant offset outside them."""
    a = np.array([p[0] for p in pts])
    sc = np.array([p[1] for p in pts])
    return lambda t: np.asarray(t, dtype=float) + np.interp(np.asarray(t, dtype=float), sc, a - sc)


def merge_anchors(pitch_pts, lyric_pts, bias):
    """Pitch anchors where they exist; lyric anchors fill gaps of more than 1 s between them."""
    ps = np.array([p[1] for p in pitch_pts]) if pitch_pts else np.array([])
    pts = list(pitch_pts)
    for a, sc in lyric_pts:
        if not len(ps) or np.min(np.abs(ps - sc)) > 1.0:
            pts.append((a + bias, sc))
    pts.sort(key=lambda p: p[1])
    out = []
    for a, sc in pts:
        if not out or (a > out[-1][0] + 0.02 and sc > out[-1][1] + 0.02):
            out.append((a, sc))
    return out


def anchors_from(windows, audio_len):
    """(audio_s, score_s) points from reliable windows, minus isolated spikes, strictly increasing."""
    rel = [w for w in windows if w["reliable"]]
    if not rel:
        return []
    off = np.array([w["audio_s"] - w["score_s"] for w in rel])
    slope = (rel[-1]["score_s"] - rel[0]["score_s"]) / max(rel[-1]["audio_s"] - rel[0]["audio_s"], 1e-6)
    thr = 0.06 + 0.3 * abs(1 - slope)
    pts = []
    for k, w in enumerate(rel):
        if 0 < k < len(rel) - 1 and abs(off[k] - off[k - 1]) > thr and abs(off[k] - off[k + 1]) > thr \
                and abs(off[k - 1] - off[k + 1]) < thr:
            continue
        a, sc = w["audio_s"], w["score_s"]
        if pts:
            ratio = (sc - pts[-1][1]) / (a - pts[-1][0]) if a > pts[-1][0] else 0
            if not 0.7 * slope < ratio < 1.4 * slope:
                continue
        if 0.05 < a < audio_len - 0.05:
            pts.append((a, sc))
    return pts


def regions(flags, items, min_len=2):
    out, i = [], 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j + 1 < len(flags) and flags[j + 1]:
                j += 1
            if j - i + 1 >= min_len:
                out.append((items[i], items[j]))
            i = j + 1
        else:
            i += 1
    return out


def window_centers(notes, step=0.5):
    t, out = notes[0][0] + 1.0, []
    while t < notes[-1][1] - 1.0:
        out.append(t)
        t += step
    return out


def window_deltas(y, notes, ratio, centers):
    scaled = [(s / ratio, e / ratio, m) for s, e, m in notes]
    return local_offsets(sung_pitch(y), scaled, [c / ratio for c in centers], lambda t: t, win=WIN / ratio, scale=ratio)


def stats(err):
    err = np.asarray(err, dtype=float)
    e = np.abs(err[~np.isnan(err)]) * 1000
    if not len(e):
        return None
    return {"windows": int(len(e)), "median_ms": round(float(np.median(e)), 1), "p95_ms": round(float(np.percentile(e, 95)), 1),
            "share_over_50ms": round(float((e > 50).mean()), 3)}


def pitch_ok(sung, notes):
    fps = SR / HOP
    hits = judged = 0
    for start, end, midi in notes:
        vals = sung[int(start * fps):max(int(start * fps) + 1, int(end * fps))]
        vals = vals[~np.isnan(vals)]
        if len(vals) < 2:
            continue
        judged += 1
        hits += int(round(np.median(vals))) % 12 == midi % 12
    return {"judged": judged, "of": len(notes), "share": round(hits / judged, 3) if judged else None}


# ---------------------------------------------------------------- warping

def warp(src, dst, pts, ratio):
    """Rubber Band R3 with a time map: audio time a -> output time s / ratio. Before the first map
    point the offset is held constant: the input is padded or trimmed, not stretched. A map point in
    the first half second is dropped: one at the very start made Rubber Band's output ~90 ms late."""
    pts = [p for p in pts if p[0] >= 0.5] if sum(p[0] >= 0.5 for p in pts) >= 2 else pts
    a0, s0 = pts[0]
    shift = s0 - a0
    y, sr = sf.read(src, always_2d=True)
    n = int(round(abs(shift) * sr))
    y = np.concatenate([np.zeros((n, y.shape[1]), y.dtype), y]) if shift > 0 else y[n:]
    pts = [(a + shift, s) for a, s in pts]
    length = len(y) / sr
    last_a, last_s = pts[-1]
    total = last_s / ratio + (length - last_a) / ratio
    with tempfile.TemporaryDirectory() as tmp:
        padded = Path(tmp) / "in.wav"
        sf.write(padded, y, sr, subtype="FLOAT")
        mapfile = Path(tmp) / "map.txt"
        mapfile.write_text("".join(f"{int(round(a * OUT_SR))} {int(round(s / ratio * OUT_SR))}\n" for a, s in pts))
        subprocess.run([str(RUBBERBAND), "-3", "-q", "-M", str(mapfile), "-D", f"{total:.6f}", str(padded), str(dst)],
                       check=True, capture_output=True)


def mute_before(path, t_end, fade=0.04):
    """Silence a vocal before t_end (the song's first note less a margin): the "Oh" lead-in."""
    y, sr = sf.read(path, always_2d=True)
    k = max(0, int((t_end - fade) * sr))
    y[:k] = 0
    ramp = np.linspace(0, 1, int(fade * sr))[:, None]
    y[k:k + len(ramp)] *= ramp[:len(y[k:k + len(ramp)])]
    sf.write(path, y, sr, subtype="PCM_24")


def sung_check(sung, notes):
    """Melody notes with almost no voiced sound where they should be (dropped words)."""
    fps = SR / HOP
    missing = []
    for i, (start, end, midi) in enumerate(notes):
        seg = sung[int(start * fps):max(int(start * fps) + 1, int((start + 0.7 * (end - start)) * fps))]
        if len(seg) == 0 or np.mean(~np.isnan(seg)) < 0.3:
            missing.append(i)
    return missing


# ---------------------------------------------------------------- the checks

def tuning_cents(y) -> float:
    return round(float(librosa.estimate_tuning(y=y, sr=SR, resolution=0.005)) * 100, 1)


def bleed_db(vocals: Path, accompaniment: Path) -> dict:
    """How much of YuE2's own backing is left in the demixed vocal (v0.22: heard over a FluidSynth
    backing, it could clash). Least squares on the magnitude spectrograms, away from the voice's
    harmonics (60 Hz-5 kHz): the gain g of the accompaniment stem found in the vocal stem, and that
    bleed's level against the vocal. Calibrated on a Five Little Ducks take: as rendered -32 dB;
    with 3% of the backing mixed back in, -29 dB; with 10%, -22 dB (clearly audible)."""
    n_fft, hop = 2048, 512
    v, _ = librosa.load(vocals, sr=SR, mono=True)
    a, _ = librosa.load(accompaniment, sr=SR, mono=True)
    m = min(len(v), len(a))
    v, a = v[:m], a[:m]
    V = np.abs(librosa.stft(v, n_fft=n_fft, hop_length=hop))
    A = np.abs(librosa.stft(a, n_fft=n_fft, hop_length=hop))
    f0, voiced, _ = librosa.pyin(v, fmin=80, fmax=1000, sr=SR, hop_length=hop, frame_length=n_fft)
    k = min(V.shape[1], A.shape[1], len(f0))
    V, A, f0, voiced = V[:, :k], A[:, :k], f0[:k], voiced[:k]
    freqs = librosa.fft_frequencies(sr=SR, n_fft=n_fft)
    mask = np.zeros_like(V, dtype=bool)
    mask[(freqs >= 60) & (freqs <= 5000), :] = True
    for t in np.flatnonzero(voiced & ~np.isnan(f0)):
        h = freqs / f0[t]
        near = (np.abs(h - np.round(h)) * f0[t] < 1.5 * SR / n_fft + 0.03 * freqs) & (np.round(h) >= 1)
        mask[near, t] = False
    g = float(np.sum(V[mask] * A[mask]) / max(float(np.sum(A[mask] ** 2)), 1e-12))
    level = 20 * np.log10(g * float(np.sqrt(np.mean(a ** 2))) / max(float(np.sqrt(np.mean(v ** 2))), 1e-12) + 1e-12)
    return {"db": round(level, 1), "gain": round(g, 4)}


def phrase_offsets(windows, phrase_starts_s, song_end_s) -> list[dict]:
    """The median signed offset of the reliable windows in each phrase (arch §10.5 step 3)."""
    bounds = list(phrase_starts_s) + [song_end_s]
    out = []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        d = [w["delta_s"] for w in windows if w["reliable"] and a <= w["score_s"] < b]
        out.append({"phrase": i + 1, "windows": len(d), "medianMs": round(float(np.median(d)) * 1000, 1) if d else None})
    return out


def lyric_words_by_phrase(audio, words, bounds, margin=0.6):
    """lyric_words, phrase by phrase: each phrase's words searched for in that phrase's audio (from
    its start, less a margin, to the next phrase's start plus one). Only for an aligned vocal, which
    is where the score says it is: whole-song alignment of heavily repeated lyrics drifted by seconds."""
    segs = []
    for a, b in zip(bounds, bounds[1:] + [float("inf")]):
        ws = [w for w in words if a - 1e-6 <= w["score_s"] < b - 1e-6]
        if ws:
            segs.append({"start": max(0.0, a - margin), "end": (b if b != float("inf") else ws[-1]["score_s"] + 5) + margin,
                         "words": ws})
    with tempfile.TemporaryDirectory() as tmp:
        wf, of = Path(tmp) / "w.json", Path(tmp) / "o.json"
        wf.write_text(json.dumps({"segments": segs}))
        subprocess.run([str(FA_PYTHON), str(HERE / "lyric_align.py"), str(audio), str(wf), str(of)],
                       check=True, capture_output=True)
        return json.loads(of.read_text())


def heard(folder: Path, words: list[str]) -> dict:
    """Whisper's hearing of a take (hear.py): {"heard": transcript, "share": 0-1}. The transcript
    is kept in folder/heard.json, one per take whatever the alignment mode."""
    f = folder / "heard.json"
    if not f.exists():
        with tempfile.TemporaryDirectory() as tmp:
            of = Path(tmp) / "o.json"
            subprocess.run([str(FA_PYTHON), str(HERE / "hear.py"), str(folder / "vocals.flac"), str(of)],
                           check=True, capture_output=True)
            f.write_text(of.read_text())
    text = json.loads(f.read_text())["heard"]
    return {"heard": text, "share": heard_share(words, text)}


def heard_share(words: list[str], text: str) -> float:
    """The share of the words' letters Whisper heard, in order. Letters, not whole words, as the
    lesson voice's check compares: "drop and list" for "drop and lift" is one letter off, not a
    missing word, and a sung "B and C" comes back as "BNC". In order, so a take that sings the song
    again after the end (YuE2 sometimes does) loses nothing."""
    want = re.sub(r"[^a-z0-9]", "", " ".join(words).lower())
    got = re.sub(r"[^a-z0-9]", "", text.lower())
    blocks = difflib.SequenceMatcher(None, want, got, autojunk=False).get_matching_blocks()
    return round(sum(b.size for b in blocks) / max(1, len(want)), 3)


def check_words(aligned: Path, words, song_start, phrase_s=None):
    real = [w for w in words if w["score_s"] >= song_start - 1e-6]
    lw = lyric_words_by_phrase(aligned, real, phrase_s) if phrase_s else lyric_words(aligned, real)
    res = np.array([w["start"] - w["score_s"] for w in lw])
    fz = np.array([forced(w) for w in lw])
    typical = float(np.median(res[~fz])) if (~fz).any() else 0.0
    # a word the aligner can't place with confidence counts as off too: it's usually a garbled
    # word (v0.30: Steady Steps' last "stomp"s, which the check had left out). Letter names ("E,
    # D, C") are the exception: the aligner can't place a one-letter word however it's sung (Pattern
    # Up, Pattern Down: 16 of 22 words), so they're left for the listen.
    letter = np.array([re.fullmatch(r"[A-G][#b♯♭]?[,.!?;:]*", w["word"].strip()) is not None for w in lw], dtype=bool)
    off = ((np.abs(res - typical) > 0.3) & ~fz) | (fz & ~letter)
    judged = ~(fz & letter)
    labels = [f"{w['word']} ({w['score_s']:.1f} s)" for w in lw]
    ok_res = np.abs(res[~fz] - typical) if (~fz).any() else np.array([0.0])
    return {"checked": int((~fz).sum()), "forced": int(fz.sum()), "lettersUnjudged": int((fz & letter).sum()),
            "typicalOffsetMs": round(typical * 1000),
            "p95Ms": round(float(np.percentile(ok_res, 95)) * 1000), "shareOver300ms": round(float(off[judged].mean()) if judged.any() else 0.0, 3),
            "stretches": [f"{a} .. {b}" for a, b in regions(off, labels)],
            "firstStretchS": next((w["score_s"] for w, o in zip(lw, off) if o), None)}


def sung_octave(y, start: float, end: float, midi: int) -> int | None:
    """The octave a note was sung in, against the one asked for (-1, 0, +1), from the voice's
    spectrum: the lowest of the note an octave down, as asked, and an octave up that carries real
    energy is the sung fundamental (a voice has nothing below its fundamental). The pitch tracker
    can't tell octaves on these voices: it read most of Pattern Up, Pattern Down at C2-E2 (v0.30)."""
    seg = y[int((start + 0.05) * SR):int((end - 0.05) * SR)]
    if len(seg) < int(0.15 * SR):
        return None
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1 / SR)
    f = 440.0 * 2 ** ((midi - 69) / 12)
    energy = [float(spec[(freqs > f * 2 ** k * 0.97) & (freqs < f * 2 ** k * 1.03)].max(initial=0.0)) for k in (-1, 0, 1)]
    top = max(energy)
    if top <= 0:
        return None
    return next(k for k, e in zip((-1, 0, 1), energy) if e >= 0.25 * top)


def octave_jumps(y, notes) -> list[dict]:
    """Notes sung in another octave from the rest of the take, against the notes asked for: a voice
    that sings the whole song an octave away is fine, but one that doesn't follow the song's own
    leaps isn't (Sleepy Owl's "whoo"; Pattern Up, Pattern Down's climb sung going down)."""
    got = [(s, e, k) for s, e, m in notes if (k := sung_octave(y, s, e, m)) is not None]
    if not got:
        return []
    usual = int(np.median([g[2] for g in got]))
    return [{"start": round(s, 2), "seconds": round(e - s, 2), "octaves": k - usual} for s, e, k in got if k != usual]


def melody_stretches(sung, notes, song_start):
    fps = SR / HOP
    judged = []
    for start, end, midi in notes:
        if start < song_start - 1e-6:
            continue
        vals = sung[int(start * fps):max(int(start * fps) + 1, int(end * fps))]
        vals = vals[~np.isnan(vals)]
        if len(vals) >= 2:
            judged.append((start, int(round(np.median(vals))) % 12 != midi % 12))
    return [f"{a} .. {b}" for a, b in regions([bad for _, bad in judged], [f"{t:.1f} s" for t, _ in judged], min_len=4)]


# ---------------------------------------------------------------- per take

def align(folder: Path, abcmap: dict, phrases: list, mode: str) -> dict:
    """Align one take in one mode: folder/aligned-<mode>/vocals_100.wav and the checks."""
    notes, bpm = score_notes(folder / "score.abc")
    vocals = folder / "vocals.flac"
    audio_len = sf.info(vocals).duration
    pad = float(Fraction(abcmap["padBeats"]))
    song_start = pad * 60.0 / bpm
    y = load_mono(vocals)
    sung = sung_pitch(y)
    words = [{**w, "score_s": float(Fraction(w["beat"])) * 60.0 / bpm} for w in abcmap["words"]]
    r = {"take": folder.name, "mode": mode, "bpm": bpm, "audioSeconds": round(audio_len, 2), "songStartS": round(song_start, 3)}
    lyric_pts = lyric_anchors(lyric_words(vocals, words))
    if mode == "dtw":
        starts = np.array([s for s, _, _ in notes])
        off = smooth_offsets(rough_onsets(notes, sung[::HOP_DTW // HOP]) - starts)
        predict = lambda t: np.asarray(t, dtype=float) + np.interp(t, starts, off)
    else:
        if len(lyric_pts) < 3:
            return {**r, "error": "too few words placed for a word map"}
        predict = map_fn(lyric_pts)
    centers = window_centers(notes)
    windows = local_offsets(sung, notes, centers, predict)
    pitch_pts = anchors_from(windows, audio_len)
    if len(pitch_pts) < 2:
        # a melody of repeated notes ("walk, walk, walk, walk" on one key) has too few pitch changes
        # for any window: in the word mode, its words place it (each one a clear attack)
        if mode != "words" or len(lyric_pts) < 3:
            return {**r, "error": "too few reliable windows to align"}
        pitch_pts, r["wordsOnly"] = lyric_pts, True
    pf = map_fn(pitch_pts)
    bias = float(np.median([float(pf(sc)) - a for a, sc in lyric_pts])) if lyric_pts else 0.0
    pts = merge_anchors(pitch_pts, [] if mode == "dtw" else lyric_pts, bias)
    offs = np.array([a - sc for a, sc in pts])
    r["before"] = {"firstOffsetS": round(float(np.median(offs[:5])), 3), "driftS": round(float(np.median(offs[-5:]) - np.median(offs[:5])), 3)}
    out = folder / f"aligned-{mode}"
    out.mkdir(exist_ok=True)
    # second pass: measure what the first warp left and correct the map once; keep the first
    # map if the correction made it worse
    warp(vocals, out / "vocals_100.wav", pts, 1.0)
    res1 = window_deltas(load_mono(out / "vocals_100.wav"), notes, 1.0, centers)
    r["pass1"] = stats([x["delta_s"] for x in res1 if x["reliable"]])
    rc = np.array([x["score_s"] for x in res1 if x["reliable"]])
    if len(rc):
        rd = np.clip(smooth_offsets(np.array([x["delta_s"] for x in res1 if x["reliable"]]), k=5), -0.35, 0.35)
        fixed = [(a, sc - float(np.interp(sc, rc, rd))) for a, sc in pts]
        fixed = [p for i, p in enumerate(fixed) if i == 0 or (p[0] > fixed[i - 1][0] and p[1] > fixed[i - 1][1])]
        warp(vocals, out / "pass2.wav", fixed, 1.0)
        res2 = window_deltas(load_mono(out / "pass2.wav"), notes, 1.0, centers)
        r["pass2"] = stats([x["delta_s"] for x in res2 if x["reliable"]])
        if r["pass2"] and r["pass1"] and r["pass2"]["median_ms"] <= r["pass1"]["median_ms"]:
            pts = fixed
            (out / "pass2.wav").replace(out / "vocals_100.wav")
        else:
            (out / "pass2.wav").unlink()
    ya = load_mono(out / "vocals_100.wav")
    mute_before(out / "vocals_100.wav", song_start - 0.12)
    ya = load_mono(out / "vocals_100.wav")
    sung_a = sung_pitch(ya)
    real = [n for n in notes if n[0] >= song_start - 1e-6]
    after = window_deltas(ya, notes, 1.0, centers)
    r["after"] = stats([x["delta_s"] for x in after if x["reliable"]])
    phrase_s = [song_start + float(p) * 60 / bpm for p in phrases]
    r["phrases"] = phrase_offsets(after, phrase_s, notes[-1][1])
    r["pitch"] = pitch_ok(sung_a, real)
    r["octaveJumps"] = octave_jumps(ya, real)
    missing = sung_check(sung_a, real)
    r["firstWordSung"] = 0 not in missing
    r["unsungNotes"] = len(missing)
    r["words"] = check_words(out / "vocals_100.wav", words, song_start, phrase_s)
    r["melodyStretches"] = melody_stretches(sung_a, notes, song_start)
    r["tuningCents"] = tuning_cents(ya[int(song_start * SR):])
    r["bleed"] = bleed_db(vocals, folder / "accompaniment.flac")
    r["map"] = [[round(a, 4), round(s, 4)] for a, s in pts]
    r["checks"] = verdict(r)
    r["score"] = score(r)
    (folder / f"alignment-{mode}.json").write_text(json.dumps(r, indent=1, default=lambda o: o.item()) + "\n")
    return r


def verdict(r) -> dict:
    """Each check's pass or fail (arch §10.5), the reasons a take fails, and flags for the parent's
    listen. Words off the staff fail a take only when there are many (over 10%) or in the first 15 s,
    the most noticeable place; a short stretch elsewhere is flagged (the sync probe's best takes had
    2-10% of words off, and a two-word stretch shouldn't cost a re-render)."""
    worst = max((abs(p["medianMs"]) for p in r["phrases"] if p["medianMs"] is not None), default=0.0)
    w = r["words"]
    # a slip fails only when it lasts: counted in notes or words, the rules tuned on slow hymns
    # failed fast songs for sub-second slips (v0.23); shorter ones are flagged for the listen
    long_mel = [x for x in r["melodyStretches"] if span_s(x) >= PASS["stretchS"]]
    early_words = [x for x in w["stretches"] if stretch_times(x)[0] < r["songStartS"] + 15]
    early = any(span_s(x) >= PASS["stretchS"] for x in early_words)
    # what Whisper heard (heard_share, Oct 7, 2026): scattered words the aligner can't place are its
    # own misses when Whisper hears the words, so they pass a take; a lasting stretch is a real drift
    # (The First Noel's syllable behind) wherever it is; and a take Whisper can't make out fails,
    # however its words were placed
    h = r.get("heard")
    clear = h is not None and h["share"] >= PASS["heard"]
    drift = any(span_s(x) >= PASS["stretchS"] for x in w["stretches"])
    checks = {
        "timing": bool(worst <= PASS["phraseOffsetMs"]),
        "pitch": (r["pitch"]["share"] or 0) >= PASS["pitch"],
        "firstWord": r["firstWordSung"],
        "words": bool((w["shareOver300ms"] <= PASS["wordsOff"] or (clear and not drift)) and not early),
        "heard": h is None or h["share"] >= PASS["heardFail"],
        "melody": not long_mel,
        "tuning": bool(abs(r["tuningCents"]) <= PASS["tuningCents"]),
        "bleed": bool(r["bleed"]["db"] <= PASS["bleedDb"]),
        "octave": not [j for j in r.get("octaveJumps", []) if j["seconds"] >= PASS["octaveHeldS"]],
    }
    reasons, flags = [], []
    if not checks["timing"]:
        reasons.append(f"a phrase sits {worst:.0f} ms off the beat")
    if not checks["pitch"]:
        reasons.append(f"notes on pitch {r['pitch']['share']:.0%} (needs 90%)")
    if not checks["firstWord"]:
        reasons.append("the first word isn't sung")
    if not checks["words"]:
        reasons.append(f"words off the staff: {w['shareOver300ms']:.0%}" + (", in the first 15 s" if early else ""))
    elif w["stretches"]:
        flags.append("words off the staff at " + "; ".join(w["stretches"]))
    if not checks["heard"]:
        reasons.append(f"Whisper heard {h['share']:.0%} of the words: \"{h['heard'][:120]}\"")
    elif h is not None and not clear:
        flags.append(f"Whisper heard {h['share']:.0%} of the words: \"{h['heard'][:120]}\"")
    if not checks["melody"]:
        reasons.append("the sung melody doesn't match the notes at " + "; ".join(long_mel))
    elif r["melodyStretches"]:
        flags.append("a short melody slip at " + "; ".join(r["melodyStretches"]))
    if not checks["tuning"]:
        reasons.append(f"tuned {r['tuningCents']:+} cents from A440")
    if not checks["bleed"]:
        reasons.append(f"backing left in the vocal at {r['bleed']['db']} dB")
    jumps = r.get("octaveJumps", [])
    if not checks["octave"]:
        reasons.append("a held note sung in another octave from the rest at " + "; ".join(
            f"{j['start']:.1f} s ({j['octaves']:+d})" for j in jumps if j["seconds"] >= PASS["octaveHeldS"]))
    elif jumps:
        flags.append("a short note sung in another octave at " + "; ".join(f"{j['start']:.1f} s" for j in jumps))
    if w.get("lettersUnjudged"):
        flags.append(f"{w['lettersUnjudged']} letter names the word check can't place: listen to them")
    if r.get("wordsOnly"):
        flags.append("timed by its words only (its notes repeat too much for the beat check): listen for the beat")
    return {**checks, "pass": all(checks.values()), "worstPhraseMs": worst, "reasons": reasons, "flags": flags}


def stretch_times(label: str) -> tuple[float, float]:
    """The first and last times (s) in a stretch label: "the (101.8 s) .. five (102.3 s)" or "21.0 s .. 21.9 s"."""
    ts = [float(x) for x in re.findall(r"([\d.]+) s\b", label)]
    return (ts[0], ts[-1]) if ts else (0.0, 0.0)


def span_s(label: str) -> float:
    a, b = stretch_times(label)
    return b - a


def score(r) -> float:
    """For choosing between takes: notes on pitch, less words off the staff and words Whisper didn't
    hear, less 0.1 for a missing first word and 0.1 for words off the staff in the first 15 s (the
    most noticeable place)."""
    early = r["words"]["firstStretchS"] is not None and r["words"]["firstStretchS"] < r["songStartS"] + 15
    missed = 1 - r["heard"]["share"] if r.get("heard") else 0
    return round((r["pitch"]["share"] or 0) - r["words"]["shareOver300ms"] - missed - (0 if r["firstWordSung"] else 0.1)
                 - (0.1 if early else 0) - (0.05 if not r["checks"]["timing"] else 0), 3)


def tempo_versions(folder: Path, mode: str, presets: dict[str, float], song_start: float, with_backing: bool) -> None:
    """The chosen take's other presets from the same map (and YuE2's accompaniment when kept)."""
    r = json.loads((folder / f"alignment-{mode}.json").read_text())
    pts = [tuple(p) for p in r["map"]]
    out = folder / f"aligned-{mode}"
    for key, ratio in presets.items():
        v = out / f"vocals_{key}.wav"
        if key != "100" or not v.exists():
            warp(folder / "vocals.flac", v, pts, ratio)
            mute_before(v, (song_start - 0.12) / ratio)
        if with_backing:
            warp(folder / "accompaniment.flac", out / f"accompaniment_{key}.wav", pts, ratio)


def check_preset(folder: Path, mode: str, key: str, ratio: float) -> dict:
    """The chosen take's vocal at a slower preset, measured against the grid at that tempo (the M8
    acceptance: on the beat at every preset). Offsets are in the stretched time the child hears."""
    notes, _ = score_notes(folder / "score.abc")
    y = load_mono(folder / f"aligned-{mode}" / f"vocals_{key}.wav")
    res = window_deltas(y, notes, ratio, window_centers(notes))
    return stats([x["delta_s"] for x in res if x["reliable"]]) or {}


def take_label(name: str) -> str:
    m = re.search(r"-s(\d+)$", name)
    return f"seed {m.group(1)}" if m else name
