"""Melisma probe (arch §10.5): shared code. Run with tools/.venv/bin/python.

A melisma is one sung syllable over several notes. The media skill sends YuE2 one note per syllable
(tools/media/yue2.py `syllabic_melody` merges a melisma onto its first pitch), so the singer holds
one pitch where the staff shows a slur. Two ways to get the notes back, used together:

  - BEND (long melismas): YuE2's input stays as it is. After the take is aligned to the beat grid,
    the held pitch is bent onto the written notes, in the vocal stem only.
  - SPLIT (short melismas): each note of the melisma gets a syllable of its own on the same vowel
    ("Chi-ild", "Jo-o-oy"), the v0.33 "Glo-o-o-ria" rule applied by the tool. YuE2 sings every note.

`SHORT_S` decides: a melisma with a note shorter than this (at the 100% tempo) is split, else bent.
"""
from __future__ import annotations

import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "media"))
import common  # noqa: E402
import yue2  # noqa: E402
from common import nt  # noqa: E402

SR = 48000
SHORT_S = 0.30            # a melisma with a note shorter than this is split for YuE2; longer ones are bent
GLIDE_S = 0.08            # the slide from one note of a bent melisma to the next (raised cosine)
GLIDE_SHARE = 0.5         # ...never more than this share of the shorter of the two notes
RETURN_SEARCH_S = 0.10    # the bend ends in a gap in the voice (a consonant, a breath) this near the syllable's end
MAX_BEND = 9.0            # semitones; a larger bend means the take sang something else there: leave it
PROBE_PY = HERE / ".venv" / "bin" / "python"
RUBBERBAND = common.RUBBERBAND
ZW = "​"             # marks a syllable this probe made by splitting (stripped before YuE2 sees it)


# ------------------------------------------------------------------------------ the melismas

def melismas(piece: common.Piece) -> list[dict]:
    """Every melisma in playback order: {"notes": [first, ...rest], "seconds": [each note's length at
    100%], "kind": "bend" | "split"}. Notes are in the melody as YuE2's export sees it (felt beats)."""
    nota, scale = yue2.felt(piece.nota)
    mel = yue2.merged_melody(nt.unroll(nota))
    spb = 60.0 / piece.bpm / float(scale)          # seconds per felt beat at 100%
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
        m["kind"] = "split" if min(m["seconds"]) < SHORT_S else "bend"
        m["scale"] = scale
    return out


def approved_dir(piece: common.Piece) -> Path:
    """Where the approved stems are: the probe's copy (out/approved/<id>/, made by apply.py before
    it replaces a piece's media with the bent version), else the piece's own media folder."""
    keep = HERE / "out" / "approved" / piece.pid
    return keep if (keep / "media.json").exists() else piece.media_dir


def stem_time(piece: common.Piece, pad_song_beats: float):
    """felt beat -> seconds in a beat-aligned 100% stem (time 0 is `pad_song_beats` before song beat 0)."""
    _, scale = yue2.felt(piece.nota)
    return lambda beat: (float(beat) / float(scale) + pad_song_beats) * 60.0 / piece.bpm


# ------------------------------------------------------------------------------ SPLIT: syllables for YuE2

GLIDES = {"oy", "ay", "ey", "uy", "ow", "aw", "ew"}     # the held sound is the first letter ("Jo-o-oy")


def split_syllable(text: str, n: int) -> list[str] | None:
    """A syllable over `n` notes as n syllables on its vowel: "Child", 2 -> ["Chi", "ild"];
    "Joy", 3 -> ["Jo", "o", "oy"]; "sleep", 2 -> ["slee", "eep"]. None when it has no vowel letter."""
    core = text.rstrip(",.;:!?'\"”’")
    tail = text[len(core):]
    low = core.lower()
    i = next((k for k, c in enumerate(low) if c in "aeiou" or (c == "y" and k > 0)), None)
    if i is None:
        return None
    j = i + 1
    while j < len(low) and low[j] in "aeiouy":
        j += 1
    cluster = core[i:j]
    hold = cluster[0] if (cluster.lower() in GLIDES or (len(cluster) > 1 and cluster[-1].lower() == "y")) else cluster
    return [core[:i] + hold] + [hold] * (n - 2) + [cluster + core[j:] + tail]


def hybrid_export(piece: common.Piece, short_s: float = SHORT_S, export=None) -> tuple[str, str, dict, list[dict]]:
    """yue2.export with the short melismas split onto their vowels (the long ones stay merged, to be
    bent after alignment). Returns (abc, lyrics, abcmap, the melismas). Done by wrapping two functions
    of tools/media/yue2.py for the length of the call, so the probe always runs the real export."""
    export = export or yue2.export             # the real export (render.py swaps yue2.export for this function)
    found = melismas(piece)
    split = {}                                   # (verse, start) of a continuation note -> its lyric
    firsts = {}                                  # (verse, start) of a split melisma's first note -> its lyric
    for m in found:
        if min(m["seconds"]) >= short_s:
            m["kind"] = "bend"
            continue
        first = m["notes"][0]
        parts = split_syllable(first["lyric"]["text"], len(m["notes"]))
        if parts is None:
            m["kind"] = "bend"                   # nothing to hold: leave it merged
            continue
        m["kind"] = "split"
        m["parts"] = parts
        syl = first["lyric"]["syllabic"]
        firsts[(first["verse"], first["start"])] = {**first["lyric"], "text": parts[0],
                                                    "syllabic": "begin" if syl in ("single", "begin") else "middle"}
        for k, x in enumerate(m["notes"][1:], 1):
            last = k == len(m["notes"]) - 1
            split[(x["verse"], x["start"])] = {"text": ZW + parts[k], "verse": first["lyric"].get("verse", first["verse"]),
                                               "syllabic": ("end" if syl in ("single", "end") else "middle") if last else "middle"}
    plain = export(piece.nota, octave=int(piece.spec.get("vocal_octave", 0)), line=piece.spec.get("vocal_line"))[2]

    real_syllabic, real_run = yue2.syllabic_melody, yue2.vowel_run

    def syllabic(mel):
        for n in mel:
            key = (n["verse"], n["start"])
            if key in firsts:
                n["lyric"] = firsts[key]
            elif key in split and n.get("lyric") is None:
                n["lyric"] = split[key]
        return real_syllabic(mel)

    yue2.syllabic_melody = syllabic
    yue2.vowel_run = lambda before, s: s.startswith(ZW) or real_run(before, s)
    try:
        abc, lyrics, abcmap = export(piece.nota, octave=int(piece.spec.get("vocal_octave", 0)), line=piece.spec.get("vocal_line"))
    finally:
        yue2.syllabic_melody, yue2.vowel_run = real_syllabic, real_run
    lyrics = lyrics.replace(ZW, "")
    for s in abcmap["syllables"]:
        s["syllable"] = s["syllable"].replace(ZW, "")
    # the word check and the aligner get the words as written ("Child", not "Chiild"): splitting
    # changes neither the words nor the beats they start on
    assert [w["beat"] for w in plain["words"]] == [w["beat"] for w in abcmap["words"]]
    abcmap["words"] = plain["words"]
    abcmap["melismas"] = [{"kind": m["kind"], "syllable": m["notes"][0]["lyric"]["text"], "parts": m.get("parts"),
                           "songBeat": str(m["notes"][0]["start"]), "seconds": [round(s, 3) for s in m["seconds"]],
                           "pitches": [x["pitch"] for x in m["notes"]]} for m in found]
    return abc, lyrics, abcmap, found


# ------------------------------------------------------------------------------ BEND: the contour

def pitch_track(y: np.ndarray, sr: int = SR):
    """(midi per 10 ms frame, voiced flags) of a vocal stem."""
    import librosa
    f, v, _ = librosa.pyin(y, fmin=80, fmax=900, sr=sr, frame_length=2048, hop_length=sr // 100)
    return librosa.hz_to_midi(f), v


def sung(f, v, t0: float, t1: float, lead: float = 0.06, tail: float = 0.03) -> float | None:
    """The pitch sung between t0 and t1 (median, away from the note's edges); None if not enough voice."""
    if t1 - t0 < lead + tail + 0.04:
        lead, tail = 0.25 * (t1 - t0), 0.15 * (t1 - t0)
    a, b = int((t0 + lead) * 100), int((t1 - tail) * 100)
    seg = f[a:b][v[a:b]] if b > a else np.array([])
    return float(np.nanmedian(seg)) if len(seg) >= 3 else None


def near(d: float) -> float:
    """A pitch difference to the nearest octave: YuE2 often sings an octave away from the score."""
    return (d + 6) % 12 - 6


def contour(found: list[dict], at, f, v, kinds=("bend",), glide_s: float = GLIDE_S) -> tuple[list[tuple[float, float]], list[dict]]:
    """The bend as (seconds, semitones) breakpoints, linear between them and 0 outside, and the
    regions it touches. Each later note of a melisma is bent by (its written pitch - the pitch sung
    there), so a take that didn't quite hold the first pitch still lands on the staff. Slides are
    raised cosines centred on the note's beat; the bend ends in the nearest gap in the voice (the
    next syllable's consonant) when there is one near the syllable's end, where it can't be heard."""
    pts: list[tuple[float, float]] = []
    regions = []
    for m in found:
        if m["kind"] not in kinds:
            continue
        notes = m["notes"]
        first = notes[0]
        offs, skip = [0.0], False
        for x in notes[1:]:
            t0, t1 = at(x["start"]), at(x["start"] + x["duration"])
            s = sung(f, v, t0, t1)
            if s is None:
                offs.append(offs[-1])                 # no voice there (a breath): nothing to bend
                continue
            # the written step from the first note, less how far the take is from the first note's
            # pitch here (0 when it held it, in whatever octave it sings)
            off = (x["pitch"] - first["pitch"]) - near(s - first["pitch"])
            if abs(off) > MAX_BEND:
                skip = True
            offs.append(off)
        if skip or not any(abs(o) > 0.25 for o in offs):
            continue
        edges = [at(x["start"]) for x in notes] + [at(notes[-1]["start"] + notes[-1]["duration"])]
        lens = [b - a for a, b in zip(edges, edges[1:])]
        # the end: in a gap in the voice near the syllable's end, else centred on it
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
            for k in range(13):                       # a raised cosine: no corner at either end
                x = k / 12
                pts.append((t - g / 2 + g * x, a0 + (a1 - a0) * (1 - np.cos(np.pi * x)) / 2))
        stop = steps[-1][0] + steps[-1][3] / 2
        pts.append((stop + 1e-4, 0.0))
        regions.append({"start": start, "end": stop, "syllable": first["lyric"]["text"], "songBeat": str(first["start"]),
                        "offsets": [round(o, 2) for o in offs], "endsInGap": bool(gap)})
    pts.sort()
    return pts, regions


# ------------------------------------------------------------------------------ BEND: two engines

def bend_psola(src: Path, pts, dst: Path) -> None:
    """Pitch-synchronous overlap-add (Praat, through parselmouth, in the probe's own venv): the voice's
    own pitch periods are moved closer together or further apart, so the vowel's colour stays, the
    slide is continuous, and audio whose pitch isn't changed comes back as it went in."""
    f = dst.with_suffix(".contour.json")
    f.write_text(json.dumps(pts))
    subprocess.run([str(PROBE_PY), str(HERE / "psola.py"), str(src), str(f), str(dst)], check=True)


def bend_rubberband(src: Path, pts, dst: Path) -> None:
    """Rubber Band's pitch map with formant preservation. It implies realtime mode and runs the
    whole file through the stretcher."""
    f = dst.with_suffix(".pitchmap.txt")
    rows = [(0, 0.0)] + [(max(0, int(t * SR)), s) for t, s in pts]
    seen, lines = set(), []
    for fr, s in rows:
        if fr not in seen:
            seen.add(fr)
            lines.append(f"{fr} {s:.3f}\n")
    f.write_text("".join(lines))
    subprocess.run([str(RUBBERBAND), "-q", "-3", "--formant", "-t", "1", "--pitchmap", str(f), str(src), str(dst)],
                   check=True, capture_output=True)


def splice(orig: np.ndarray, bent: np.ndarray, regions: list[dict], sr: int = SR, margin: float = 0.03,
           search: float = 3.0, fade: float = 0.02) -> tuple[np.ndarray, dict]:
    wa, wb, stats = splice_weights(orig, bent, regions, sr, margin, search, fade)
    n = len(wa)
    return orig[:n] * wa + bent[:n] * wb, stats


def splice_weights(orig: np.ndarray, bent: np.ndarray, regions: list[dict], sr: int = SR, margin: float = 0.03,
                   search: float = 3.0, fade: float = 0.02) -> tuple[np.ndarray, np.ndarray, dict]:
    """The bent audio inside each region, the original everywhere else, so outside the melismas the
    stem is exactly the approved one. The overlap-add output isn't the same waveform as the input
    even where the pitch is unchanged (the periods are laid again), so a crossfade in the middle of
    a vowel would mix two voices out of phase. Each region therefore grows outward to the nearest
    spot where the two are the same (silence, or sound the resynthesis copied: consonants, breaths)
    and switches there; with none within `search` seconds, it crossfades over `fade` at the quietest
    spot it passed. Returns the original's and the bent audio's weights, and how the joins were made
    (`splice` applies them; a stereo stem applies them to each channel against the bent mono)."""
    n = min(len(orig), len(bent))
    a, b = orig[:n], bent[:n]
    hop = sr // 200                                    # 5 ms frames
    k = n // hop
    ea = (a[:k * hop].reshape(k, hop) ** 2).mean(axis=1)
    ed = ((a[:k * hop] - b[:k * hop]).reshape(k, hop) ** 2).mean(axis=1)
    same = (ed <= 1e-4 * ea + 1e-9)                    # 40 dB under the sound, or both silent
    same = same & np.roll(same, 1) & np.roll(same, -1)  # three frames in a row
    w = np.zeros(n)                                     # the bent audio's share
    loose = np.zeros(n, bool)                           # inside a crossfade of two unlike waveforms
    stats = {"clean": 0, "crossfaded": 0, "seconds": 0.0}
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
    for (s0, c0), (s1, c1) in spans:
        w[s0:s1] = 1.0
    for (s0, c0), (s1, c1) in spans:                   # ramps: 5 ms where the two are the same, `fade` otherwise
        for s, c, rising in ((s0, c0, True), (s1, c1, False)):
            m = int((0.005 if c else fade) * sr / 2)
            lo, hi = max(0, s - m), min(n, s + m)
            if hi - lo < 2 or (w[lo] == 1.0 and w[hi - 1] == 1.0):
                continue                              # inside another region's span
            ramp = np.linspace(0, 1, hi - lo)
            w[lo:hi] = ramp if rising else ramp[::-1]
            loose[lo:hi] = not c
    stats["seconds"] = round(float(w.sum() / sr), 1)
    # unlike waveforms add in power, not in amplitude: an equal-power crossfade keeps the level
    wa = np.where(loose, np.cos(w * np.pi / 2), 1 - w)
    wb = np.where(loose, np.sin(w * np.pi / 2), w)
    return wa, wb, stats


# ------------------------------------------------------------------------------ measures

def on_pitch(found: list[dict], at, f, v, which: str = "later") -> tuple[int, int]:
    """(notes on pitch, notes with a voice to measure): the melismas' later notes ("later"), or all
    of their notes ("all"). On pitch: within half a semitone of the written note, any octave."""
    ok = tot = 0
    for m in found:
        for x in (m["notes"][1:] if which == "later" else m["notes"]):
            s = sung(f, v, at(x["start"]), at(x["start"] + x["duration"]))
            if s is None:
                continue
            tot += 1
            ok += int(abs(near(s - x["pitch"])) <= 0.5)
    return ok, tot


def melody_on_pitch(piece: common.Piece, at, f, v) -> tuple[int, int]:
    """The same for every note of the written melody (ties merged), melismas and all: what the child
    hears against the staff."""
    nota, _ = yue2.felt(piece.nota)
    ok = tot = 0
    for x in yue2.merged_melody(nt.unroll(nota)):
        s = sung(f, v, at(x["start"]), at(x["start"] + x["duration"]))
        if s is None:
            continue
        tot += 1
        ok += int(abs(near(s - x["pitch"])) <= 0.5)
    return ok, tot


def roughness(y_in: np.ndarray, y_out: np.ndarray, regions: list[dict], sr: int = SR) -> dict:
    """A stand-in for "tics", to compare versions (the ear decides): inside the bent regions, how much
    more broadband onset energy (above 3 kHz) the output has than the input, and the steepest pitch
    slope; outside them, how far the output is from the input."""
    import librosa
    n = min(len(y_in), len(y_out))
    a, b = y_in[:n], y_out[:n]

    def flux(y):
        S = np.abs(librosa.stft(y, n_fft=512, hop_length=128))[32:]
        return np.maximum(0, np.diff(np.log1p(50 * S), axis=1)).sum(axis=0)
    fa, fb = flux(a), flux(b)
    inside = np.zeros(len(fa), bool)
    for r in regions:
        inside[int((r["start"] - 0.05) * sr / 128):int((r["end"] + 0.05) * sr / 128)] = True
    extra = fb[inside] - fa[inside]
    spikes = int(np.sum(extra > 6 * np.std(fa)))
    mask = np.ones(n, bool)
    for r in regions:
        mask[max(0, int((r["start"] - 0.1) * sr)):int((r["end"] + 0.1) * sr)] = False
    diff = a[mask] - b[mask]
    rel = 10 * np.log10(max(float(np.mean(diff ** 2)), 1e-20) / max(float(np.mean(a[mask] ** 2)), 1e-20))
    return {"onsetSpikesInRegions": spikes, "extraOnsetEnergy": round(float(np.mean(np.maximum(extra, 0))), 2),
            "changeOutsideRegionsDb": round(rel, 1)}


def load_mono(path: Path, sr: int = SR) -> np.ndarray:
    import librosa
    y, _ = librosa.load(path, sr=sr, mono=True)
    return y
