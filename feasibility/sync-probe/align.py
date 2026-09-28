"""Test 3: align YuE2 renders to the score's beat grid, make the tempo versions, and measure the result.

    .venv/bin/python align.py                   # every render in renders/
    .venv/bin/python align.py what-child-is-this

For each renders/<id>/ (vocals.flac, accompaniment.flac, score.abc from YuE2):
  1. Find where the vocal is against the score: DTW on pitch (as in the M0-S spike's
     analyze_vocal.py) for a rough map, then, in 3-second windows every 0.5 s, the time shift
     that best lines up the sung pitch curve with the score's (11.6 ms frames). Picking single
     note onsets was tried first and failed the ruler check (vibrato and breaths fool it).
  2. Build a time map (audio time -> score time) from the reliable windows, dropping outliers.
  3. Warp the vocal, measure what is left, correct the map once (Rubber Band lags ~25 ms behind a
     dense time map), then warp both stems with that one map (Rubber Band R3), at 100/90/75/50%, so
     vocal and accompaniment stay together and land on the grid (arch §10.5 steps 3 and 7).
  4. Measure (arch §10.5 step 3 pass rule: drift over about 50 ms fails):
       - held-out check: a map from every 4th window (2 s apart), measured midway between them;
       - the final 100% and 50% versions, measured in every window;
       - the ruler itself: a known synthetic warp applied to the aligned vocal and measured back;
       - the accompaniment's onsets against the beat grid, before and after;
       - pitch: share of notes sung on the right pitch class (arch §10.5 step 4, bar 90%).
  5. Set levels (vocal -20 dBFS RMS; backing 10 dB under it above 250 Hz, see set_levels) and write
     renders/<id>/aligned/{vocals,accompaniment}_<preset>.flac and renders/<id>/alignment.json.
"""
from __future__ import annotations

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

HERE = Path(__file__).resolve().parent
RENDERS = HERE / "renders"
BUILD = HERE / "build"
RB = HERE / ".rubberband" / "bin" / "rubberband"
sys.path.insert(0, str(Path.home() / "engines/yue2/YuE/skills/yue2-music/scripts"))
import abc_tools  # noqa: E402

SR = 22050            # analysis rate
HOP = 256             # 11.6 ms analysis frames
HOP_DTW = 1024        # 46 ms frames for the rough DTW pass
OUT_SR = 48000
PRESETS = {"100": 1.0, "90": 0.9, "75": 0.75, "50": 0.5}
VOCAL_RMS_DB = -20.0
BACKING_BELOW_DB = 10.0   # backing level under the vocal, measured above 250 Hz (what tablet speakers play)
WIN = 3.0             # seconds of score per alignment window
# melody: the word map sets the rough position, the sung melody decides within +-1.2 s (the voice stays
#         on the notes the student plays; where YuE2 put words on other notes, the words drift and
#         the check reports it). words: pitch may only adjust +-0.35 s (words stay on the staff).
# dtw: round 2's method: a pitch-only DTW map (no words), windows +-0.35 s. Best when YuE2 put words
#      on other notes (the melody stays exact), worst when a repeated melody or the lead-in fools it.
MODES = {"melody": 1.2, "words": 0.35, "dtw": 0.35}
MODE = "melody"


# ---------------------------------------------------------------- score and pitch

def score_notes(abc_path):
    score = abc_tools.parse_abc(Path(abc_path).read_text().rstrip("\n"))
    spq = 60.0 / score.bpm
    notes = [(float(on) * spq, float(on + d) * spq, midi) for on, midi, d in score.voices["Vocal"].notes]
    return notes, score.bpm, float(score.voices["Vocal"].time) * spq


def sung_pitch(y, hop):
    f0, voiced, _ = librosa.pyin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
                                 sr=SR, hop_length=hop, frame_length=2048)
    rms_db = librosa.amplitude_to_db(librosa.feature.rms(y=y, hop_length=hop)[0], ref=1.0)
    rms_db = np.pad(rms_db, (0, max(0, len(f0) - len(rms_db))), constant_values=-120)[:len(f0)]
    loud = rms_db > np.percentile(rms_db, 95) - 40          # stem bleed sits ~-75 dBFS
    return np.where(voiced & loud, librosa.hz_to_midi(f0), np.nan)


def pc_cost(a, b):
    A, B = a[:, None], b[None, :]
    d = np.abs((A - B) % 12)
    d = np.minimum(d, 12 - d) / 6.0
    va, vb = ~np.isnan(A), ~np.isnan(B)
    cost = np.where(va & vb, d, np.where(va | vb, 0.6, 0.0))
    return np.nan_to_num(cost, nan=0.6).astype(np.float32)


def rough_onsets(notes, sung_coarse):
    """DTW between the score's pitch line and the sung pitch; returns each note's rough audio onset."""
    fps = SR / HOP_DTW
    n_ref = int(notes[-1][1] * fps) + 1
    ref = np.full(n_ref, np.nan)
    for start, end, midi in notes:
        ref[int(start * fps):max(int(start * fps) + 1, int(end * fps))] = midi
    _, path = librosa.sequence.dtw(C=pc_cost(ref, sung_coarse), subseq=False)
    to_audio = {}
    for i, j in path[::-1]:
        to_audio.setdefault(i, []).append(j)
    return np.array([max(to_audio.get(int(s * fps), [int(s * fps)])) / fps for s, _, _ in notes])


def smooth_offsets(times, offsets, k=9):
    """Running median of offsets (rejects single wild DTW matches)."""
    out = np.copy(offsets)
    for i in range(len(offsets)):
        out[i] = np.median(offsets[max(0, i - k // 2):i + k // 2 + 1])
    return out


def score_pitch_at(notes, times):
    """Score pitch (MIDI) at each time, NaN in rests."""
    starts = np.array([s for s, _, _ in notes])
    ends = np.array([e for _, e, _ in notes])
    midi = np.array([m for _, _, m in notes], dtype=float)
    idx = np.searchsorted(starts, times, side="right") - 1
    ok = (idx >= 0) & (times < ends[np.clip(idx, 0, None)])
    return np.where(ok, midi[np.clip(idx, 0, None)], np.nan)


def local_offsets(sung, notes, centers, predict, win=3.0, max_shift=0.3, scale=1.0):
    """For each window of score time [c - win/2, c + win/2], the time shift (s, in audio time) that
    best lines up the sung pitch with the score's pitch there, around the predicted audio time.
    Pitch changes pin the shift down; windows with fewer than 2 changes are marked unreliable."""
    fps = SR / HOP
    shifts = np.arange(-int(max_shift / scale * fps), int(max_shift / scale * fps) + 1)
    starts = np.array([s for s, _, _ in notes])
    results = []
    for c in centers:
        tau = np.arange(c - win / 2, c + win / 2, 1 / fps)
        ref = score_pitch_at(notes, tau)
        # pitch changes whose onset falls inside the window (including the change into its first note)
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
        # ambiguous if another, distinct shift (over 150 ms away) fits almost as well
        far = np.abs(shifts - shifts[b]) > int(0.15 * fps / scale)
        unique = cost[far].min() - cost[b] if far.any() else 1.0
        reliable = changes >= 2 and cost[b] < 0.3 and unique > 0.005 and 0 < b < len(cost) - 1
        results.append({"score_s": float(c), "audio_s": float(predict(np.array([c]))[0] + delta),
                        "delta_s": float(delta), "cost": float(cost[b]), "reliable": bool(reliable)})
    return results


def lyric_words(audio, words):
    """Word start/end/confidence in the audio (lyric_align.py, run in the .fa venv)."""
    with tempfile.TemporaryDirectory() as tmp:
        wf, of = Path(tmp) / "w.json", Path(tmp) / "o.json"
        wf.write_text(json.dumps(words))
        subprocess.run([str(HERE / ".fa/bin/python"), str(HERE / "lyric_align.py"), str(audio), str(wf), str(of)],
                       check=True, capture_output=True)
        return json.loads(of.read_text())


def lyric_anchors(lw):
    """(audio_s, score_s) from confidently aligned words: drop forced words (zero length or very low
    confidence), isolated spikes, and anything that breaks the order (longest increasing run)."""
    good = [w for w in lw if w["conf"] > -1.5 and w["end"] - w["start"] >= 0.04]
    off = [w["start"] - w["score_s"] for w in good]
    keep = [w for k, w in enumerate(good) if not (0 < k < len(good) - 1 and abs(off[k] - off[k - 1]) > 0.4
            and abs(off[k] - off[k + 1]) > 0.4 and abs(off[k - 1] - off[k + 1]) < 0.4)]
    # longest subsequence increasing in both audio and score time
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
    def f(t):
        t = np.asarray(t, dtype=float)
        return t + np.interp(t, sc, a - sc)
    return f


def merge_anchors(pitch_pts, lyric_pts, bias):
    """Pitch anchors where they exist; lyric anchors (shifted by the measured lyric-vs-pitch bias)
    fill any gap of more than 1 s of score time between pitch anchors."""
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


def regions(flags, items, min_len=2):
    """Runs of at least min_len flagged items: [(first, last)]."""
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


def window_centers(notes, step, first=None):
    t = notes[0][0] + 1.0 if first is None else first
    out = []
    while t < notes[-1][1] - 1.0:
        out.append(t)
        t += step
    return out


def window_deltas(y, notes, ratio, centers):
    sung = sung_pitch(y, HOP)
    scaled = [(s / ratio, e / ratio, m) for s, e, m in notes]
    return local_offsets(sung, scaled, [c / ratio for c in centers], lambda t: t, win=WIN / ratio, scale=ratio)


def measure_aligned(y, notes, ratio, centers):
    """Offsets (output time) at window centers of an output that should already be on the grid."""
    res = window_deltas(y, notes, ratio, centers)
    errs = [r["delta_s"] for r in res if r["reliable"]]
    return stats(np.array(errs)), sum(r["reliable"] for r in res), len(res)


def stats(err):
    e = np.abs(err[~np.isnan(err)]) * 1000
    if not len(e):
        return None
    return {"windows": int(len(e)), "median_signed_ms": round(float(np.median(err[~np.isnan(err)])) * 1000, 1), "median_ms": round(float(np.median(e)), 1),
            "p95_ms": round(float(np.percentile(e, 95)), 1), "max_ms": round(float(e.max()), 1),
            "share_over_50ms": round(float((e > 50).mean()), 3)}


def pitch_ok(y, notes_expected):
    sung = sung_pitch(y, HOP)
    fps = SR / HOP
    hits = judged = 0
    for start, end, midi in notes_expected:
        vals = sung[int(start * fps):max(int(start * fps) + 1, int(end * fps))]
        vals = vals[~np.isnan(vals)]
        if len(vals) < 2:
            continue
        judged += 1
        hits += int(round(np.median(vals))) % 12 == midi % 12
    return {"judged": judged, "of": len(notes_expected), "pitch_ok": round(hits / judged, 3) if judged else None}


# ---------------------------------------------------------------- warping

def anchors_from(windows, audio_len):
    """(audio_s, score_s) time-map points from reliable windows, minus outliers, strictly increasing."""
    rel = [w for w in windows if w["reliable"]]
    if not rel:
        return []
    off = np.array([w["audio_s"] - w["score_s"] for w in rel])
    # allowed local stretch is judged against the take's overall pace (a take can run 30% fast)
    slope = (rel[-1]["score_s"] - rel[0]["score_s"]) / max(rel[-1]["audio_s"] - rel[0]["audio_s"], 1e-6)
    pts = []
    thr = 0.06 + 0.3 * abs(1 - slope)
    for k, w in enumerate(rel):
        # drop isolated spikes only: a point that disagrees with both neighbours while they agree.
        # (A median test also threw away real steps, where YuE2 holds a long note longer.)
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


def warp(src, dst, pts, ratio, audio_len):
    """Rubber Band R3 with a time map: audio time a -> output time s / ratio.
    Before the first map point the offset is held constant (no stretch): the input is padded with
    silence when the take starts early, or trimmed when it starts late. Without this, everything
    before the first point was squeezed into the score's start (a 2x stretch on Amazing Grace)."""
    a0, s0 = pts[0]
    shift = s0 - a0                      # > 0: take is early, pad; < 0: take is late, trim
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
        subprocess.run([str(RB), "-3", "-q", "-M", str(mapfile), "-D", f"{total:.6f}", str(padded), str(dst)],
                       check=True, capture_output=True)


def mute_before(path, t_end, fade=0.04):
    """Silence a vocal stem before t_end (the song's first note, less a margin): drops a lead-in
    word and anything YuE2 sang early."""
    y, sr = sf.read(path, always_2d=True)
    k = max(0, int((t_end - fade) * sr))
    y[:k] = 0
    ramp = np.linspace(0, 1, int(fade * sr))[:, None]
    y[k:k + len(ramp)] *= ramp[:len(y[k:k + len(ramp)])]
    sf.write(path, y, sr, subtype="PCM_24")


def sung_check(y, notes):
    """Melody notes with almost no voiced sound where they should be (dropped words)."""
    sung = sung_pitch(y, HOP)
    fps = SR / HOP
    missing = []
    for i, (start, end, midi) in enumerate(notes):
        seg = sung[int(start * fps):max(int(start * fps) + 1, int((start + 0.7 * (end - start)) * fps))]
        if len(seg) == 0 or np.mean(~np.isnan(seg)) < 0.3:
            missing.append(i)
    return missing


def load_mono(path):
    y, _ = librosa.load(path, sr=SR, mono=True)
    return y


def accompaniment_on_grid(path, bpm, ratio, start_s, end_s):
    """Accompaniment onsets against the beat grid: offset of the clearest onset near each beat."""
    y = load_mono(path)
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    fps = SR / HOP
    thresh = np.median(env) + 3 * np.median(np.abs(env - np.median(env)))
    offs, beats = [], 0
    b = start_s
    while b < end_s:
        t = b / ratio
        a, c = int((t - 0.1) * fps), int((t + 0.1) * fps)
        if a >= 0 and c < len(env):
            beats += 1
            k = a + int(np.argmax(env[a:c]))
            if env[k] > thresh:
                offs.append(k / fps - t)
        b += 60.0 / bpm
    offs = np.array(offs)
    if not len(offs):
        return {"beats": beats, "clear_onsets": 0}
    return {"beats": beats, "clear_onsets": int(len(offs)),
            "median_abs_ms": round(float(np.median(np.abs(offs))) * 1000, 1),
            "p95_abs_ms": round(float(np.percentile(np.abs(offs), 95)) * 1000, 1),
            "median_signed_ms": round(float(np.median(offs)) * 1000, 1)}


def band_rms_db(y, sr, lo=250.0):
    import scipy.signal as ss
    sos = ss.butter(4, lo / (sr / 2), "high", output="sos")
    yh = ss.sosfilt(sos, y.mean(axis=1))
    return 20 * np.log10(max(float(np.sqrt(np.mean(yh ** 2))), 1e-12))


def set_levels(vocal_path, backing_path, song_start):
    """Vocal to -20 dBFS RMS. Backing: cut below 120 Hz, then set it BACKING_BELOW_DB under the vocal,
    both measured above 250 Hz over the song itself (not the lead-in). YuE2's backings put 84-99% of
    their energy below 250 Hz, which iPad speakers barely play: plain RMS made them sound silent."""
    import scipy.signal as ss
    v, sr = sf.read(vocal_path, always_2d=True)
    b, _ = sf.read(backing_path, always_2d=True)
    k = int(song_start * sr)
    gv = 10 ** (VOCAL_RMS_DB / 20) / max(float(np.sqrt(np.mean(v[k:] ** 2))), 1e-9)
    v = v * gv
    b = ss.sosfilt(ss.butter(2, 120 / (sr / 2), "high", output="sos"), b, axis=0)
    gb = 10 ** ((band_rms_db(v[k:], sr) - BACKING_BELOW_DB - band_rms_db(b[k:], sr)) / 20)
    b = b * gb
    peak = max(float(np.abs(v).max()), float(np.abs(b).max()))
    if peak > 0.99:
        v, b = v * 0.99 / peak, b * 0.99 / peak
    sf.write(vocal_path, v.astype(np.float32), sr, subtype="PCM_24")
    sf.write(backing_path, b.astype(np.float32), sr, subtype="PCM_24")
    return {"vocals_db": round(20 * np.log10(gv), 1), "backing_db": round(20 * np.log10(gb), 1), "limited": peak > 0.99}


# ---------------------------------------------------------------- per render

def ruler_check(aligned_vocal, notes, centers, workdir):
    """How well the estimator follows a known shift: warp the aligned vocal by a known wobble
    (+-100 ms, 12 s period), measure both versions, and compare the change with the known shift.
    Measuring the difference keeps the vocal's own rubato out of the ruler's error."""
    length = sf.info(aligned_vocal).duration
    pts, t = [], 1.0
    while t < length - 1:
        pts.append((t, t + 0.10 * np.sin(2 * np.pi * t / 12.0)))
        t += 0.25
    dst = workdir / "ruler.wav"
    warp(aligned_vocal, dst, pts, 1.0, length)
    xs, ys = [0] + [p[0] for p in pts], [0] + [p[1] for p in pts]
    base = window_deltas(load_mono(aligned_vocal), notes, 1.0, centers)
    wob = window_deltas(load_mono(dst), notes, 1.0, centers)
    errs = [w["delta_s"] - b["delta_s"] - (float(np.interp(c, xs, ys)) - c)
            for b, w, c in zip(base, wob, centers) if b["reliable"] and w["reliable"]]
    dst.unlink()
    return stats(np.array(errs))


def quality_check(aligned_vocal, words, notes, centers, song_start, result):
    """Two independent looks at the aligned 100% vocal:
    words  - lyric alignment again: each word's start against its score time (a stretch of words
             more than 0.3 s off means the words are not where the staff shows them);
    melody - 4 or more notes in a row sung on the wrong pitch: the melody doesn't match the notes there.
    A stretch where they disagree is YuE2 singing words on the wrong notes: no warp can fix both,
    so the take fails (re-render it)."""
    real = [w for w in words if w["score_s"] >= song_start - 1e-6]
    lw = lyric_words(aligned_vocal, real)
    res = np.array([w["start"] - w["score_s"] for w in lw])
    forced = np.array([w["conf"] <= -1.5 or w["end"] - w["start"] < 0.04 for w in lw])
    typical = float(np.median(res[~forced])) if (~forced).any() else 0.0
    off = np.abs(res - typical) > 0.3
    labels = [f"{w['word']} ({w['score_s']:.1f} s)" for w in lw]
    word_regions = regions(off & ~forced, labels)
    # melody: runs of 4+ judged notes sung on the wrong pitch (the melody doesn't match the notes there)
    y = load_mono(aligned_vocal)
    sung = sung_pitch(y, HOP)
    fps = SR / HOP
    judged = []
    for start, end, midi in notes:
        if start < song_start - 1e-6:
            continue
        vals = sung[int(start * fps):max(int(start * fps) + 1, int(end * fps))]
        vals = vals[~np.isnan(vals)]
        if len(vals) >= 2:
            judged.append((start, int(round(np.median(vals))) % 12 != midi % 12))
    mel_regions = regions([bad for _, bad in judged], [f"{t:.1f} s" for t, _ in judged], min_len=4)
    ok_res = np.abs(res[~forced] - typical)
    reasons = []
    if word_regions:
        reasons.append(f"{len(word_regions)} stretch(es) of words off the staff")
    if mel_regions:
        reasons.append(f"{len(mel_regions)} stretch(es) where the sung melody doesn't match the notes")
    if (result.get("pitch_100") or {}).get("pitch_ok", 1) < 0.9:
        reasons.append("pitch under 90%")
    if not result.get("first_note_sung", True):
        reasons.append("first note not sung")
    return {"pass": not reasons, "reasons": reasons,
            "words": {"checked": int((~forced).sum()), "forced": int(forced.sum()),
                      "typical_offset_ms": round(typical * 1000), "median_ms": round(float(np.median(ok_res)) * 1000),
                      "p95_ms": round(float(np.percentile(ok_res, 95)) * 1000), "share_over_300ms": round(float(off.mean()), 3)},
            "word_regions": [f"{a} .. {b}" for a, b in word_regions],
            "melody_regions": [f"{a} .. {b}" for a, b in mel_regions]}


def take_parts(name):
    """'<song>-<variant>' or '<song>-<variant>-s<seed>' -> (song, variant)."""
    m = re.fullmatch(r"(.+)-(intro|fake|syl|mel)(?:-folk|-spec)?(?:-s\d+)?", name)
    return (m.group(1), m.group(2)) if m else (name, "")


def align_render(folder: Path):
    notes, bpm, score_len = score_notes(folder / "score.abc")
    vocals, acc = folder / "vocals.flac", folder / "accompaniment.flac"
    audio_len = sf.info(vocals).duration
    presets = {"100": 1.0} if folder.name.endswith("-half") else PRESETS
    sid, variant = take_parts(folder.name)
    amap = BUILD / sid / "yue2" / f"abcmap-{variant}.json"
    amap_json = json.loads(amap.read_text())
    pad_beats = float(Fraction(amap_json["pad_beats"]))
    amap_words = amap_json["words"]
    song_start = pad_beats * 60.0 / bpm           # score time of the song's first real note
    y = load_mono(vocals)
    sung = sung_pitch(y, HOP)
    result = {"id": folder.name, "bpm": bpm, "score_seconds": round(score_len, 2),
              "audio_seconds": round(audio_len, 2), "melody_notes": len(notes)}

    # 1. words: where each known lyric word starts (the backbone: words can't be confused by a repeated
    #    melody or a lead-in note on the same pitch, which is how the pitch-only map went wrong)
    words = [{**w, "score_s": float(Fraction(w["beat"])) * 60.0 / bpm} for w in amap_words]
    lw = lyric_words(vocals, words)
    lyric_pts = lyric_anchors(lw)
    result["lyrics"] = {"words": len(lw), "anchors": len(lyric_pts),
                        "forced_words": [w["word"] for w in lw if w["conf"] <= -1.5 or w["end"] - w["start"] < 0.04][:20]}
    if MODE == "dtw":
        starts = np.array([s for s, _, _ in notes])
        rough = rough_onsets(notes, sung[::HOP_DTW // HOP])
        off = smooth_offsets(starts, rough - starts)
        predict = lambda t: t + np.interp(t, starts, off)
    else:
        predict = map_fn(lyric_pts)
    # 2. pitch: windowed pitch alignment, searching only +-0.35 s around the word map
    centers = window_centers(notes, 0.5)
    windows = local_offsets(sung, notes, centers, predict, win=WIN, max_shift=MODES[MODE])
    rel = [w for w in windows if w["reliable"]]
    result["windows"] = {"total": len(windows), "reliable": len(rel)}
    offs = np.array([a - sc for a, sc in lyric_pts])
    result["before"] = {"first_offset_s": round(float(np.median(offs[:5])), 3),
                        "last_offset_s": round(float(np.median(offs[-5:])), 3),
                        "drift_s": round(float(np.median(offs[-5:]) - np.median(offs[:5])), 3),
                        "max_abs_offset_s": round(float(np.abs(offs).max()), 3)}
    pitch_pts = anchors_from(windows, audio_len)
    # lyric starts sit a little before the pitch change (consonants); measure that bias where both exist
    if pitch_pts:
        pf = map_fn(pitch_pts)
        bias = float(np.median([float(pf(sc)) - a for a, sc in lyric_pts])) if lyric_pts else 0.0
    else:
        bias = 0.0
    result["lyric_bias_s"] = round(bias, 3)
    pts = merge_anchors(pitch_pts, [] if MODE == "dtw" else lyric_pts, bias)
    result["anchors"] = {"pitch": len(pitch_pts), "total": len(pts)}
    to_audio = lambda t: np.interp(t, [p[1] for p in pts], [p[0] for p in pts])
    result["pitch_before"] = pitch_ok(y, [(float(to_audio(s)), float(to_audio(e)), m) for s, e, m in notes])
    result["accompaniment_before"] = accompaniment_on_grid(acc, bpm, 1.0, notes[0][0], score_len)

    result["mode"] = MODE
    out = folder / f"aligned-{MODE}"
    out.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="align-"))

    # held-out: a map from every 4th window (2 s apart), measured midway between them
    # (the 3 s windows overlap, so this checks interpolation between anchors, not full independence)
    train = [w for i, w in enumerate(windows) if i % 4 == 0]
    held = [c for i, c in enumerate(centers) if i % 4 == 2]
    warp(vocals, work / "train.wav", merge_anchors(anchors_from(train, audio_len), [] if MODE == "dtw" else lyric_pts, bias),
         1.0, audio_len)
    result["held_out"], *_ = measure_aligned(load_mono(work / "train.wav"), notes, 1.0, held)

    # second pass: measure what is left after the first warp (Rubber Band lags slightly behind a
    # dense time map) and move each target time by the smoothed residual, then warp again
    warp(vocals, work / "pass1.wav", pts, 1.0, audio_len)
    res1 = window_deltas(load_mono(work / "pass1.wav"), notes, 1.0, centers)
    rc = np.array([r["score_s"] for r in res1 if r["reliable"]])
    rd = np.clip(smooth_offsets(rc, np.array([r["delta_s"] for r in res1 if r["reliable"]]), k=5), -0.35, 0.35)
    result["pass1_residual"] = stats(np.array([r["delta_s"] for r in res1 if r["reliable"]]))
    if len(rc):
        pts = [(a, sc - float(np.interp(sc, rc, rd))) for a, sc in pts]
        pts = [p for i, p in enumerate(pts) if i == 0 or (p[0] > pts[i - 1][0] and p[1] > pts[i - 1][1])]
    for name, ratio in presets.items():
        for stem, src in (("vocals", vocals), ("accompaniment", acc)):
            warp(src, out / f"{stem}_{name}.flac", pts, ratio, audio_len)
    real = [i for i, n in enumerate(notes) if n[0] >= song_start - 1e-6]
    for name, ratio in presets.items():
        if song_start > 0:
            mute_before(out / f"vocals_{name}.flac", (song_start - 0.12) / ratio)
    missing = sung_check(load_mono(out / "vocals_100.flac"), [notes[i] for i in real])
    result["song_start_s"] = round(song_start, 3)
    result["first_note_sung"] = 0 not in missing
    result["unsung_notes"] = [{"index": real[i], "score_s": round(notes[real[i]][0], 2), "midi": notes[real[i]][2]} for i in missing]
    for name in ("100", "50"):
        if name not in presets:
            continue
        ratio = presets[name]
        yo = load_mono(out / f"vocals_{name}.flac")
        result[f"after_{name}"], *_ = measure_aligned(yo, notes, ratio, centers)
        result[f"pitch_{name}"] = pitch_ok(yo, [(s / ratio, e / ratio, m) for s, e, m in notes])
        result[f"accompaniment_after_{name}"] = accompaniment_on_grid(
            out / f"accompaniment_{name}.flac", bpm, ratio, notes[0][0], score_len)
    result["qa"] = quality_check(out / "vocals_100.flac", words, notes, centers, song_start, result)
    result["ruler"] = ruler_check(out / "vocals_100.flac", notes, centers, work)

    result["gain_applied"] = {name: set_levels(out / f"vocals_{name}.flac", out / f"accompaniment_{name}.flac",
                                               song_start / ratio) for name, ratio in presets.items()}
    result["map"] = [[round(a, 4), round(s, 4)] for a, s in pts]
    result["levels_version"] = 2
    (folder / f"alignment-{MODE}.json").write_text(json.dumps(result, indent=1) + "\n")
    for f in work.iterdir():
        f.unlink()
    work.rmdir()
    return result


def summary_line(r):
    b, h, ru = r["before"], r["held_out"] or {}, r["ruler"] or {}
    a100, a50 = r.get("after_100") or {}, r.get("after_50") or {}
    q = r.get("qa") or {}
    return (f"{r['id']}: QA {'PASS' if q.get('pass') else 'FAIL ' + '; '.join(q.get('reasons', []))} | words: p95 {(q.get('words') or {}).get('p95_ms')} ms, "
            f"off-staff stretches {q.get('word_regions')} | wrong-melody stretches {q.get('melody_regions')}\n   "
            f"{r['audio_seconds']}s audio / {r['score_seconds']}s score | windows {r['windows']['reliable']}/{r['windows']['total']} "
            f"| before: first {b['first_offset_s']:+.2f}s drift {b['drift_s']:+.2f}s pitch {r['pitch_before']['pitch_ok']} "
            f"| held-out p95 {h.get('p95_ms')} ms | 100%: median {a100.get('median_ms')} p95 {a100.get('p95_ms')} ms "
            f"| 50%: median {a50.get('median_ms')} p95 {a50.get('p95_ms')} ms | ruler median {ru.get('median_ms')} p95 {ru.get('p95_ms')} ms "
            f"| pitch 100% {(r.get('pitch_100') or {}).get('pitch_ok')} 50% {(r.get('pitch_50') or {}).get('pitch_ok')} "
            f"| first note sung {r.get('first_note_sung')}, unsung {len(r.get('unsung_notes', []))}")


def relevel(folder):
    """Redo only the levels of an aligned take (warps and measurements unchanged)."""
    r = json.loads((folder / "alignment.json").read_text())
    if r.get("levels_version") == 2:
        return r["gain_applied"]
    r["gain_applied"] = {name: set_levels(folder / "aligned" / f"vocals_{name}.flac",
                                          folder / "aligned" / f"accompaniment_{name}.flac", r["song_start_s"] / ratio)
                         for name, ratio in PRESETS.items()}
    r["levels_version"] = 2
    (folder / "alignment.json").write_text(json.dumps(r, indent=1) + "\n")
    return r["gain_applied"]


def main(argv):
    global MODE
    if argv[:1] == ["--mode"]:
        MODE, argv = argv[1], argv[2:]
    if argv and argv[0] == "--levels":
        for folder in sorted(p for p in RENDERS.iterdir() if (p / "alignment.json").is_file()):
            print(folder.name, relevel(folder)["100"], flush=True)
        return
    folders = [RENDERS / a for a in argv] if argv else sorted(p for p in RENDERS.iterdir()
                                                               if (p / "report.json").is_file() and take_parts(p.name)[1])
    for folder in folders:
        r = align_render(folder)
        print(summary_line(r), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
