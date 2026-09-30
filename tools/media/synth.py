"""Render backing parts with FluidSynth and MuseScore General (arch §10.5 steps 3-5).

- Each tempo preset is rendered natively at its own tempo (no stretching), after `pad` beats of
  lead-in, so stem time 0 is `pad` beats before playback beat 0 (the app's padBeats).
- Timing: each part is rendered alone and its attack measured (ms from the notated start until the
  sound has risen 30% of the way to its peak). Slow parts (bowed strings) then start that much
  early, up to 250 ms, as sample-library players do; the lag is measured again. Pass: every part's
  median within 20 ms of its beat.
- Level: one gain for all presets, setting the 100% render to about -26 dB RMS where it plays.
Prototype: feasibility/fluid-probe/render.py.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

from backing import Part
from common import FLUIDSYNTH, PRESETS, SOUNDFONT, SR

TARGET_DB = -26.0
TPB = 480
MAX_LEAD_MS = 250
TIMING_PASS_MS = 20


def midi(parts: list[Part], bpm: float, path: Path, pad: float, leads: dict[str, float] | None = None) -> None:
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
            b = max(0.0, n.beat + pad - early)
            on, off = round(b * TPB), round((n.beat + pad - early + n.dur) * TPB)
            events.append((on, 1, mido.Message("note_on", channel=ch, note=n.pitch, velocity=n.vel)))
            events.append((max(off, on + 1), 0, mido.Message("note_off", channel=ch, note=n.pitch, velocity=0)))
        now = 0
        for t, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
            tr.append(msg.copy(time=t - now))
            now = t
        mf.tracks.append(tr)
    mf.save(str(path))


def fluid(mid: Path, wav: Path) -> float:
    t0 = time.monotonic()
    subprocess.run([str(FLUIDSYNTH), "-ni", "-q", "-F", str(wav), "-r", str(SR), "-g", "0.5",
                    "-o", "synth.reverb.active=1", "-o", "synth.chorus.active=0", str(SOUNDFONT), str(mid)],
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


def mp3(y: np.ndarray, path: Path, sr: int = SR) -> int:
    sf.write(path, y, sr, format="MP3", bitrate_mode="CONSTANT", compression_level=0.5)
    return path.stat().st_size


def attack_lags(y: np.ndarray, starts: list[float], frac: float = 0.3, early: float = 0.0) -> list[float]:
    """For each notated start (seconds), ms from the notated start until the envelope has risen
    `frac` of the way to its peak, for a note that began `early` seconds before it."""
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


def lag_stats(lags: list[float]) -> dict:
    if not lags:
        return {"median": None, "p90": None, "notes": 0}
    return {"median": round(float(np.median(lags)), 1), "p90": round(float(np.percentile(lags, 90)), 1), "notes": len(lags)}


def render(parts: list[Part], bpm: float, pad: float, out: Path, presets: dict[str, float] = PRESETS) -> dict:
    """accompaniment_<preset>.mp3 in `out`, and a report: parts, leads, timing, gain, sizes."""
    out.mkdir(parents=True, exist_ok=True)
    rep = {"parts": [p.describe() for p in parts], "lagsBefore": {}, "lagsAfter": {}, "leadMs": {}, "presets": {}}
    leads: dict[str, float] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for when, key in (("before", "lagsBefore"), ("after", "lagsAfter")):
            for i, p in enumerate(parts):
                mid, wav = tmp / f"part{i}-{when}.mid", tmp / f"part{i}-{when}.wav"
                midi([p], bpm, mid, pad, leads)
                fluid(mid, wav)
                y, _ = sf.read(wav, always_2d=True)
                starts = sorted({round((n.beat + pad) * 60 / bpm, 4) for n in p.notes})
                st = lag_stats(attack_lags(y, starts, early=leads.get(p.name, 0.0) / 1000))
                rep[key][p.name] = st
                if when == "before":
                    med = st["median"] or 0.0
                    leads[p.name] = min(MAX_LEAD_MS, med) if med >= 20 else 0.0
        rep["leadMs"] = {k: round(v) for k, v in leads.items()}
        worst = max((abs(v["median"]) for v in rep["lagsAfter"].values() if v["median"] is not None), default=0.0)
        rep["timing"] = {"worstPartMedianMs": worst, "pass": worst <= TIMING_PASS_MS}
        gain = None
        for key, ratio in presets.items():
            mid, wav = tmp / f"backing_{key}.mid", tmp / f"backing_{key}.wav"
            midi(parts, bpm * ratio, mid, pad, leads)
            secs = fluid(mid, wav)
            y, _ = sf.read(wav, always_2d=True)
            gain = TARGET_DB - active_db(y) if gain is None else gain     # one gain for every preset
            y = level(y, gain)
            rep["presets"][key] = {"ratio": ratio, "renderSec": round(secs, 2), "seconds": round(len(y) / SR, 2),
                                   "file": f"accompaniment_{key}.mp3", "bytes": mp3(y, out / f"accompaniment_{key}.mp3")}
        rep["gainDb"] = round(gain, 1)
    return rep
