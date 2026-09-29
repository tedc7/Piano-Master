"""Render each test piece's backing with FluidSynth, at the four tempo presets, with each SoundFont.

    .venv/bin/python render.py                 # all pieces -> build/, report in build/report.json

For each piece and SoundFont:
  - accompaniment_{100,90,75,50}.mp3: the backing alone, rendered natively at each tempo (no time
    stretching), levelled to the YuE2 accompaniment stems (about -26 dB RMS where it plays);
  - with_piano_100.mp3: the backing plus the piano part on the SoundFont's piano, for listening
    without the keyboard;
  - timing: for each backing part rendered alone, how long after each notated start the sound
    reaches 30% of its rise (attack lag). Slow instruments (bowed strings) then start that much
    early, as sample-library players do, and the lag is measured again. Stems begin one beat before
    playback beat 0 (the app's padBeats), so a note on beat 0 can start early too.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

import backing as bk

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FLUIDSYNTH = HERE / ".fluidsynth" / "bin" / "fluidsynth"
SOUNDFONTS = {"musescore": HERE / "soundfonts" / "MuseScore_General.sf3",
              "generaluser": HERE / "soundfonts" / "GeneralUser-GS.sf2"}
PRESETS = {"100": 1.0, "90": 0.9, "75": 0.75, "50": 0.5}
SR = 48000
TARGET_DB = -26.0
TPB = 480
PAD_BEATS = 1.0            # stem time 0 is one beat before playback beat 0
MAX_LEAD_MS = 250


def midi(parts: list[bk.Part], bpm: float, path: Path, leads: dict[str, float] | None = None,
         pad: float = PAD_BEATS) -> None:
    """A MIDI file of the parts at `bpm`, after `pad` beats of silence, each part starting
    `leads[name]` ms early."""
    mf = mido.MidiFile(ticks_per_beat=TPB)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=int(round(60e6 / bpm)), time=0))
    mf.tracks.append(meta)
    for ch, part in enumerate(parts):
        ch = ch if ch < 9 else ch + 1                  # skip the drum channel
        tr = mido.MidiTrack()
        tr.append(mido.Message("program_change", channel=ch, program=part.program, time=0))
        for cc, v in ((7, part.volume), (10, part.pan), (91, part.reverb), (93, 0)):
            tr.append(mido.Message("control_change", channel=ch, control=cc, value=v, time=0))
        events = []
        early = (leads or {}).get(part.name, 0.0) / 1000 * bpm / 60          # ms -> beats at this tempo
        for n in part.notes:
            b = n.beat + pad - early
            on, off = round(b * TPB), round((b + n.dur) * TPB)
            events.append((on, 1, mido.Message("note_on", channel=ch, note=n.pitch, velocity=n.vel)))
            events.append((off, 0, mido.Message("note_off", channel=ch, note=n.pitch, velocity=0)))
        now = 0
        for t, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
            tr.append(msg.copy(time=t - now))
            now = t
        mf.tracks.append(tr)
    mf.save(str(path))


def fluid(sf2: Path, mid: Path, wav: Path) -> float:
    t0 = time.monotonic()
    subprocess.run([str(FLUIDSYNTH), "-ni", "-q", "-F", str(wav), "-r", str(SR), "-g", "0.5",
                    "-o", "synth.reverb.active=1", "-o", "synth.chorus.active=0", str(sf2), str(mid)],
                   check=True, capture_output=True)
    return time.monotonic() - t0


def active_db(y: np.ndarray) -> float:
    m = y.mean(axis=1)
    fr = m[: len(m) // 2048 * 2048].reshape(-1, 2048)
    rms = np.sqrt((fr ** 2).mean(axis=1))
    act = rms[rms > 10 ** (-50 / 20)]
    return float(20 * np.log10(np.median(act))) if len(act) else -120.0


def level(y: np.ndarray, gain_db: float) -> np.ndarray:
    y = y * 10 ** (gain_db / 20)
    peak = np.abs(y).max()
    return y * (0.95 / peak) if peak > 0.95 else y


def mp3(y: np.ndarray, path: Path) -> int:
    sf.write(path, y, SR, format="MP3", bitrate_mode="CONSTANT", compression_level=0.5)
    return path.stat().st_size


def attack_lags(y: np.ndarray, starts: list[float], frac: float = 0.3, early: float = 0.0) -> list[float]:
    """For each notated start (seconds), ms from the notated start until the envelope has risen
    `frac` of the way to its peak, for a note that began `early` seconds before it (the level
    just before the note began is the baseline)."""
    env = np.abs(y.mean(axis=1))
    win = int(SR * 0.005)
    env = np.convolve(env, np.ones(win) / win, mode="same")
    out = []
    for s in starts:
        a, b = int((s - early) * SR), int((s - early + 0.4) * SR)
        if b >= len(env) or a < 0:
            continue
        base, seg = env[max(0, a - win)], env[a:b]
        peak = seg.max()
        if peak < base * 1.5 or peak < 1e-3:
            continue                     # no clear new attack (a held note, or masked)
        mark = base + (peak - base) * frac
        out.append(float(np.argmax(seg >= mark) / SR * 1000) - early * 1000)
    return out


def piano_part(nota: dict) -> bk.Part:
    p = bk.Part("Piano (the student's part)", 0, volume=110, reverb=30)
    for h in ("R", "L"):
        p.notes += [bk.Note(n.beat, n.dur, n.pitch, 80) for n in bk.played(nota, h)]
    return p


def main(only: list[str]) -> int:
    report = {}
    for pid, make in bk.PIECES.items():
        if only and pid not in only:
            continue
        meta, nota = bk.load(pid)
        parts = make(nota)
        bpm = float(nota["header"]["tempo"])
        rep = report.setdefault(pid, {"title": meta["title"], "bpm": bpm, "beats": nota["length"],
                                      "parts": [{"name": p.name, "program": p.program, "notes": len(p.notes)} for p in parts],
                                      "soundfonts": {}})
        for sfname, sf2 in SOUNDFONTS.items():
            out = BUILD / pid / sfname
            (out / "tmp").mkdir(parents=True, exist_ok=True)
            r = rep["soundfonts"][sfname] = {"presets": {}, "lags": {}, "lagsAfter": {}, "leadMs": {}}
            # attack lag per part, each rendered alone at 100%; slow parts then start early
            leads: dict[str, float] = {}
            for when, key in (("before", "lags"), ("after", "lagsAfter")):
                for i, p in enumerate(parts):
                    mid, wav = out / "tmp" / f"part{i}-{when}.mid", out / "tmp" / f"part{i}-{when}.wav"
                    midi([p], bpm, mid, leads)
                    fluid(sf2, mid, wav)
                    y, _ = sf.read(wav, always_2d=True)
                    starts = sorted({round((n.beat + PAD_BEATS) * 60 / bpm, 4) for n in p.notes})
                    lags = attack_lags(y, starts, early=leads.get(p.name, 0.0) / 1000)
                    med = float(np.median(lags)) if lags else 0.0
                    r[key][p.name] = {"median": round(med, 1) if lags else None,
                                      "p90": round(float(np.percentile(lags, 90)), 1) if lags else None, "notes": len(lags)}
                    if when == "before":
                        leads[p.name] = min(MAX_LEAD_MS, med) if med >= 20 else 0.0
            r["leadMs"] = {k: round(v) for k, v in leads.items()}
            gain = None
            for key, ratio in PRESETS.items():
                mid, wav = out / "tmp" / f"backing_{key}.mid", out / "tmp" / f"backing_{key}.wav"
                midi(parts, bpm * ratio, mid, leads)
                secs = fluid(sf2, mid, wav)
                y, _ = sf.read(wav, always_2d=True)
                gain = TARGET_DB - active_db(y) if gain is None else gain    # one gain for all presets
                y = level(y, gain)
                notated = (nota["length"] + PAD_BEATS) * 60 / (bpm * ratio)
                r["presets"][key] = {"ratio": ratio, "renderSec": round(secs, 2), "seconds": round(len(y) / SR, 2),
                                     "notatedSec": round(notated, 2), "bytes": mp3(y, out / f"accompaniment_{key}.mp3")}
            r["gainDb"] = round(gain, 1)
            # the backing with the piano part, for listening without the keyboard
            mid, wav = out / "tmp" / "with_piano.mid", out / "tmp" / "with_piano.wav"
            midi(parts + [piano_part(nota)], bpm, mid, leads)
            fluid(sf2, mid, wav)
            y, _ = sf.read(wav, always_2d=True)
            mp3(level(y, TARGET_DB + 6 - active_db(y)), out / "with_piano_100.mp3")
            print(f"{pid} / {sfname}: " + ", ".join(f"{k}% {v['seconds']}s ({v['bytes'] // 1024} KB, {v['renderSec']}s)"
                                                    for k, v in r["presets"].items()))
            print("    attack lag ms, median before -> after starting early: " +
                  "; ".join(f"{k}: {v['median']} -> {r['lagsAfter'][k]['median']} (lead {r['leadMs'][k]})" for k, v in r["lags"].items()))
    BUILD.mkdir(exist_ok=True)
    old = json.loads((BUILD / "report.json").read_text()) if (BUILD / "report.json").exists() else {}
    (BUILD / "report.json").write_text(json.dumps({**old, **report}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
