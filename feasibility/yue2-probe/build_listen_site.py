"""Build the iPad listening page from finished generate_music.py renders.

Run with the engine venv (needs numpy + soundfile):
    ~/engines/yue2/.venv/bin/python build_listen_site.py results/autumn-road results/garden-morning ...

Writes listen-dist/: index.html, manifest.json, and <id>/{mix,vocals,accompaniment,reference}.mp3.
The reference track is a plain synthesized tone of the Vocal line in each render's score.abc.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ENGINE = Path.home() / "engines" / "yue2"
SR = 48000
MP3 = dict(format="MP3", subtype="MPEG_LAYER_III")


def abc_tools():
    path = ENGINE / "YuE" / "skills" / "yue2-music" / "scripts" / "abc_tools.py"
    spec = importlib.util.spec_from_file_location("abc_tools", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["abc_tools"] = module
    spec.loader.exec_module(module)
    return module


def synth_reference(abc_text: str, length_seconds: float | None) -> np.ndarray:
    """Soft organ-like tone for each sounding Vocal note, timed from the score."""
    score = abc_tools().parse_abc(abc_text)
    spq = 60.0 / score.bpm                                    # seconds per quarter note
    end = float(score.voices["Vocal"].time) * spq
    total = max(end, length_seconds or 0) + 0.5
    out = np.zeros(int(total * SR), dtype=np.float32)
    for onset, midi, dur in score.voices["Vocal"].notes:
        start, seconds = float(onset) * spq, float(dur) * spq
        n = int(seconds * SR)
        t = np.arange(n) / SR
        f = 440.0 * 2 ** ((midi - 69) / 12)
        wave = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
        env = np.minimum(1.0, t / 0.015) * np.minimum(1.0, (seconds - t) / 0.06).clip(0) * (0.75 + 0.25 * np.exp(-t * 3))
        i = int(start * SR)
        out[i:i + n] += (0.22 * wave * env).astype(np.float32)[: len(out) - i]
    return np.stack([out, out], axis=1)


def measure_timing(abc_text: str, vocals_path: Path, fps=50, window=20, step=10, search=5) -> dict | None:
    """How far the sung vocal sits from the score's timing, in sliding windows.

    Compares singing on/off (vocal stem above -45 dBFS) with the score's Vocal notes and
    finds the best shift per window. Negative = the audio sings earlier than the score.
    """
    score = abc_tools().parse_abc(abc_text)
    spq = 60.0 / score.bpm
    v, sr = sf.read(vocals_path, dtype="float32")
    v = v.mean(axis=1) if v.ndim == 2 else v
    hop = sr // fps
    env = np.sqrt(np.add.reduceat(v ** 2, np.arange(0, len(v), hop)) / hop)
    pad = search * fps
    act = np.pad((20 * np.log10(env + 1e-9) > -45).astype(float), pad)
    ref = np.zeros(len(act) - 2 * pad)
    for onset, _, dur in score.voices["Vocal"].notes:
        a, b = int(float(onset) * spq * fps), int(float(onset + dur) * spq * fps)
        ref[a:min(b, len(ref))] = 1
    windows = []
    for start in range(0, len(ref) - window * fps + 1, step * fps):
        r = ref[start:start + window * fps]
        if r.sum() < 2 * fps:
            continue
        shifts = range(-pad, pad + 1)
        best = max(shifts, key=lambda k: np.dot(r, act[pad + start + k: pad + start + k + len(r)]))
        windows.append({"score_seconds": start / fps, "offset": round(best / fps, 2)})
    if not windows:
        return None
    return {"offset_first": windows[0]["offset"], "offset_last": windows[-1]["offset"], "windows": windows}


def to_mp3(src_dir: Path, name: str, dest: Path) -> bool:
    mp3, flac = src_dir / f"{name}.mp3", src_dir / f"{name}.flac"
    if mp3.is_file():
        shutil.copyfile(mp3, dest)
    elif flac.is_file():
        audio, rate = sf.read(flac, dtype="float32")
        sf.write(dest, audio, rate, **MP3)
    else:
        return False
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("renders", nargs="+", type=Path, help="render folders containing report.json")
    p.add_argument("--out", type=Path, default=HERE / "listen-dist")
    args = p.parse_args()

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    shutil.copyfile(HERE / "listen" / "index.html", args.out / "index.html")
    installed = json.loads((ENGINE / "INSTALLED.json").read_text())
    renders = []
    for folder in args.renders:
        report = json.loads((folder / "report.json").read_text())
        job = json.loads((folder / "job.json").read_text())
        rid = report["id"]
        dest = args.out / rid
        dest.mkdir()
        tracks = {}
        for name in ("mix", "vocals", "accompaniment"):
            if to_mp3(folder, name, dest / f"{name}.mp3"):
                tracks[name] = f"{rid}/{name}.mp3"
        score_file = folder / "score.abc"
        score_text = score_file.read_text(encoding="utf-8") if score_file.is_file() else None
        if score_text:
            try:
                sf.write(dest / "reference.mp3", synth_reference(score_text, report.get("audio_seconds")), SR, **MP3)
                tracks["reference"] = f"{rid}/reference.mp3"
            except Exception as exc:  # a model-planned score may fall outside the checker's dialect
                print(f"{rid}: no reference melody ({exc})", file=sys.stderr)
        timing = None
        analysis = folder / "analysis.json"      # from analyze_vocal.py (pitch-based DTW); preferred
        if analysis.is_file():
            a = json.loads(analysis.read_text())
            timing = {"offset_first": a["timing"]["first_note_offset_s"], "offset_last": a["timing"]["last_note_offset_s"],
                      "pitch_match": a["pitch_match_aligned"], "method": "pitch DTW"}
        elif score_text and (folder / "vocals.flac").is_file():
            try:
                timing = measure_timing(score_text, folder / "vocals.flac")
            except Exception as exc:
                print(f"{rid}: no timing measurement ({exc})", file=sys.stderr)
        t = report.get("timing_seconds", {})
        renders.append({
            "id": rid, "title": report.get("title") or rid, "profile": report.get("profile"),
            "style": report["style"], "cot": report["cot"], "seed": report["seed"],
            "score_supplied": report.get("score_supplied", False), "truncated": report.get("truncated", False),
            "audio_seconds": report.get("audio_seconds"),
            "render_seconds": round(t.get("yue2_total", 0) + t.get("stems", 0), 1),
            "peak_vram_gib": (report.get("peak_vram_gib") or {}).get("yue2"),
            "lyrics": job["lyrics"], "score_abc": score_text, "tracks": tracks, "timing": timing,
        })
        print(f"{rid}: {sorted(tracks)}; timing vs score {timing and {k: v for k, v in timing.items() if k != 'windows'}}")
    manifest = {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "engine": {"packages": installed["packages"], "yue_commit": installed["yue_commit"],
                   "gpu": (installed.get("cuda") or [{}])[0].get("name")},
        "renders": renders,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"built {args.out} ({len(renders)} renders)")


if __name__ == "__main__":
    main()
