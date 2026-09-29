"""The hybrid test: Amazing Grace's YuE2 vocal over a FluidSynth backing (MuseScore General) made
from the hymn's own alto, tenor and bass, against the original YuE2 backing.

    .venv/bin/python hymn.py        # -> build/amazing-grace/, report in build/hymn.json

The backing is laid out on the app piece's playback order (2 verses) with the stems' own lead-in
(padBeats 5) and tempo, so it shares the vocal's clock. Checks:
  - tuning: the vocal's and the YuE2 backing's offset from A440 (FluidSynth is exactly A440);
  - timing: for each melody note that changes pitch, when the vocal reaches it (pYIN) against the
    notated time, i.e. how far the aligned vocal sits from the backing's beat;
  - attack lags of the backing parts, before and after starting slow parts early (render.py).
Mixes for listening are the app's own balance: the vocal at 100%, the backing at 200%.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

import backing as bk
import render as rd

HERE = Path(__file__).resolve().parent
ROOT = bk.ROOT
PIECE = ROOT / "client" / "public" / "content" / "pieces" / "amazing-grace-melody.json"
FULL = ROOT / "feasibility" / "sync-probe" / "dist" / "songs" / "amazing-grace" / "notation.json"
STEMS = ROOT / "client" / "public" / "media" / "amazing-grace-melody"
OUT = rd.BUILD / "amazing-grace"
SF2 = rd.SOUNDFONTS["musescore"]
VOICES = {"alto": (0, 2), "tenor": (1, 1), "bass": (1, 2)}      # (staff, voice) in the four-part score


def voice_notes(full: dict, order: list[dict], staff: int, voice: int) -> list[bk.Note]:
    """One voice of the four-part score, on the app piece's playback order (ties merged)."""
    ms = full["measures"]
    out, t, open_ = [], 0.0, {}
    for p in order:
        m = ms[p["measure"]]
        for n in sorted((n for n in full["notes"] if n["staff"] == staff and n["voice"] == voice and bk.in_measure(n, m)),
                        key=lambda n: n["start"]):
            beat = t + n["start"] - m["start"]
            held = open_.pop(n["pitch"], None)
            if held and abs(held.beat + held.dur - beat) < 1e-6:
                held.dur += n["duration"]
                note = held
            else:
                note = bk.Note(beat, n["duration"], n["pitch"], 70)
                out.append(note)
            if n.get("tieToNext"):
                open_[n["pitch"]] = note
        t += m["duration"]
    return out


def styles(full: dict, order: list[dict]) -> dict[str, list[bk.Part]]:
    atb = {k: voice_notes(full, order, *sv) for k, sv in VOICES.items()}
    organ = bk.Part("Church organ (alto, tenor, bass)", 19, volume=80, reverb=70)
    pedal = bk.Part("Organ pedal (bass an octave down)", 19, volume=70, reverb=70)
    strings = bk.Part("Strings (alto, tenor)", 48, volume=85, pan=76)
    cello = bk.Part("Cello (bass)", 42, volume=95, pan=52)
    for k in ("alto", "tenor", "bass"):
        organ.notes += [bk.Note(n.beat, n.dur, n.pitch, 64) for n in atb[k]]
    pedal.notes = [bk.Note(n.beat, n.dur, n.pitch - 12, 60) for n in atb["bass"]]
    for k in ("alto", "tenor"):
        strings.notes += [bk.Note(n.beat, n.dur, n.pitch, 62) for n in atb[k]]
    cello.notes = [bk.Note(n.beat, n.dur, n.pitch, 70) for n in atb["bass"]]
    return {"organ": [organ, pedal], "strings": [strings, cello]}


def vocal_timing(vocal: Path, piece: dict, pad: float, bpm: float) -> dict:
    """ms from each notated melody note (where the pitch changes) to when the vocal reaches that
    pitch (within half a semitone, in any octave, held for about 46 ms), searching from 250 ms
    before to 400 ms after. Also the octave sung."""
    y, sr = librosa.load(vocal, sr=22050, mono=True)
    hop = 256
    f0, voiced, _ = librosa.pyin(y, fmin=75, fmax=900, sr=sr, hop_length=hop)
    midi = librosa.hz_to_midi(f0)
    times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop)
    mel = [n for n in bk.played(piece["notation"], "R")]
    deltas, prev = [], None
    for n in mel:
        if prev is not None and n.pitch == prev:
            prev = n.pitch
            continue
        prev = n.pitch
        t = (n.beat + pad) * 60 / bpm
        pc = np.abs((midi - n.pitch + 6) % 12 - 6)          # any octave: a voice may sing it an octave down
        on = voiced & (pc <= 0.5)
        steady = np.zeros_like(on)
        for k in range(len(on) - 3):                          # held for 4 frames (about 46 ms), not a glide through it
            steady[k] = on[k:k + 4].all()
        win = (times >= t - 0.25) & (times <= t + 0.4) & steady
        if win.any():
            deltas.append(float(times[np.argmax(win)] - t) * 1000)
    d = np.array(deltas)
    sung = midi[voiced & ~np.isnan(midi)]
    octave = round(float(np.median(sung) - np.median([n.pitch for n in mel])) / 12) if len(sung) else None
    return {"octaveOffset": octave, "notes": len(mel), "found": len(d), "medianMs": round(float(np.median(d)), 1),
            "within80ms": round(float((np.abs(d) <= 80).mean()), 3), "within150ms": round(float((np.abs(d) <= 150).mean()), 3), "p10": round(float(np.percentile(d, 10)), 1),
            "p90": round(float(np.percentile(d, 90)), 1)}


def syllable_timing(vocal: Path, piece: dict, pad: float, bpm: float) -> dict:
    """ms from each sung syllable's notated start to the nearest vocal onset (librosa's onset
    detector on the vocal stem) within 250 ms: how far the aligned vocal sits from the beat."""
    nota = piece["notation"]
    y, sr = librosa.load(vocal, sr=22050, mono=True)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True)
    lyr = {(ly["note"], ly["verse"]) for ly in nota["lyrics"]}
    starts, t = [], 0.0
    for p in nota["playbackOrder"]:
        m = nota["measures"][p["measure"]]
        for i, n in enumerate(nota["notes"]):
            if bk.in_measure(n, m) and ((i, p["verse"]) in lyr or (i, 1) in lyr and p["verse"] == 1):
                starts.append(t + n["start"] - m["start"])
        t += m["duration"]
    d = []
    for b in sorted(set(starts)):
        s = (b + pad) * 60 / bpm
        near = onsets[np.abs(onsets - s) <= 0.25]
        if len(near):
            d.append(float(near[np.argmin(np.abs(near - s))] - s) * 1000)
    d = np.array(d)
    return {"syllables": len(set(starts)), "found": len(d), "medianMs": round(float(np.median(d)), 1),
            "within50ms": round(float((np.abs(d) <= 50).mean()), 3), "within100ms": round(float((np.abs(d) <= 100).mean()), 3),
            "p10": round(float(np.percentile(d, 10)), 1), "p90": round(float(np.percentile(d, 90)), 1)}


def mix(vocal: Path, backing: Path | np.ndarray, out: Path) -> None:
    v, sr = sf.read(vocal, always_2d=True)
    b = backing if isinstance(backing, np.ndarray) else sf.read(backing, always_2d=True)[0]
    n = max(len(v), len(b))
    y = np.zeros((n, 2))
    y[: len(v)] += v[:, :2] if v.shape[1] > 1 else np.repeat(v, 2, axis=1)
    y[: len(b)] += 2.0 * (b[:, :2] if b.shape[1] > 1 else np.repeat(b, 2, axis=1))    # the app's backing volume, 200%
    peak = np.abs(y).max()
    rd.mp3(y * (0.95 / peak) if peak > 0.95 else y, out)


def main() -> int:
    piece = json.loads(PIECE.read_text())
    full = json.loads(FULL.read_text())
    media = piece["media"]
    pad, bpm = float(media["padBeats"]), float(media["bpm"])
    assert len(full["measures"]) == len(piece["notation"]["measures"]), "the four-part score and the app piece differ"
    order = piece["notation"]["playbackOrder"]
    report = {"tuningCents": {}, "vocalTiming": {}, "styles": {}}
    for f in ("vocals_100.mp3", "accompaniment_100.mp3"):
        y, sr = librosa.load(STEMS / f, sr=22050, mono=True)
        report["tuningCents"][f] = round(float(librosa.estimate_tuning(y=y, sr=sr, resolution=0.005)) * 100, 1)
    report["vocalTiming"] = vocal_timing(STEMS / "vocals_100.mp3", piece, pad, bpm)
    report["syllableTiming"] = {f: syllable_timing(STEMS / f, piece, pad, bpm) for f in ("vocals_100.mp3", "accompaniment_100.mp3")}
    OUT.mkdir(parents=True, exist_ok=True)
    mix(STEMS / "vocals_100.mp3", STEMS / "accompaniment_100.mp3", OUT / "mix_yue2_100.mp3")
    for name, parts in styles(full, order).items():
        out = OUT / name
        (out / "tmp").mkdir(parents=True, exist_ok=True)
        r = report["styles"][name] = {"parts": [p.name for p in parts], "lags": {}, "leadMs": {}, "presets": {}}
        leads: dict[str, float] = {}
        for i, p in enumerate(parts):
            mid, wav = out / "tmp" / f"part{i}.mid", out / "tmp" / f"part{i}.wav"
            rd.midi([p], bpm, mid, pad=pad)
            rd.fluid(SF2, mid, wav)
            y, _ = sf.read(wav, always_2d=True)
            lags = rd.attack_lags(y, sorted({round((n.beat + pad) * 60 / bpm, 4) for n in p.notes}))
            med = float(np.median(lags)) if lags else 0.0
            leads[p.name] = min(rd.MAX_LEAD_MS, med) if med >= 20 else 0.0
            r["lags"][p.name] = round(med, 1)
        r["leadMs"] = {k: round(v) for k, v in leads.items()}
        gain = None
        for key, ratio in rd.PRESETS.items():
            mid, wav = out / "tmp" / f"backing_{key}.mid", out / "tmp" / f"backing_{key}.wav"
            rd.midi(parts, bpm * ratio, mid, leads, pad=pad)
            secs = rd.fluid(SF2, mid, wav)
            y, _ = sf.read(wav, always_2d=True)
            gain = rd.TARGET_DB - rd.active_db(y) if gain is None else gain
            y = rd.level(y, gain)
            r["presets"][key] = {"ratio": ratio, "renderSec": round(secs, 2), "seconds": round(len(y) / rd.SR, 2),
                                 "bytes": rd.mp3(y, out / f"accompaniment_{key}.mp3")}
        mix(STEMS / "vocals_100.mp3", out / "accompaniment_100.mp3", OUT / f"mix_{name}_100.mp3")
        mix(STEMS / "vocals_50.mp3", out / "accompaniment_50.mp3", OUT / f"mix_{name}_50.mp3")
        print(f"{name}: lags {r['lags']} -> leads {r['leadMs']}; " +
              ", ".join(f"{k}% {v['seconds']}s" for k, v in r["presets"].items()))
    mix(STEMS / "vocals_50.mp3", STEMS / "accompaniment_50.mp3", OUT / "mix_yue2_50.mp3")
    (rd.BUILD / "hymn.json").write_text(json.dumps(report, indent=1))
    print("tuning (cents from A440):", report["tuningCents"])
    print("vocal pitch against the beat:", report["vocalTiming"])
    for f, v in report["syllableTiming"].items():
        print(f"syllable onsets against the beat ({f}):", v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
