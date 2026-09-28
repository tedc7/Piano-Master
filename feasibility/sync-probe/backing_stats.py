"""How much does YuE2's backing vary, within a song and between takes? Measured on the raw stems
(before our level setting), in 3 s windows every 1 s over the sung part of the song.

    .venv/bin/python backing_stats.py        -> build/backing_stats.json, table on stdout

  level vs vocal    backing minus vocal RMS above 250 Hz (what tablet speakers play), dB
  level range       backing level above 250 Hz, p90 - p10 of the windows, dB (swell within the song)
  bass share        share of backing energy below 250 Hz (bass the iPad barely plays)
  timbre change     median distance between each window's spectral shape (8 octave bands) and the
                    take's average shape: how much the instrumentation changes within the song
The earlier spike's takes (yue2-probe) are included for comparison.
"""
from __future__ import annotations

import json
from pathlib import Path

import librosa
import numpy as np

HERE = Path(__file__).resolve().parent
SPIKE = HERE.parent / "yue2-probe" / "results"
SR, WIN, HOP = 22050, 3.0, 1.0
EDGES = [0, 125, 250, 500, 1000, 2000, 4000, 8000, 11025]


def band_windows(path, start, end):
    y, _ = librosa.load(path, sr=SR, mono=True)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512)) ** 2
    f = librosa.fft_frequencies(sr=SR, n_fft=2048)
    t = librosa.frames_to_time(np.arange(S.shape[1]), sr=SR, hop_length=512)
    bands = np.stack([S[(f >= lo) & (f < hi)].sum(axis=0) for lo, hi in zip(EDGES, EDGES[1:])])
    out = []
    w0 = start
    while w0 + WIN <= min(end, t[-1]):
        sel = (t >= w0) & (t < w0 + WIN)
        out.append(bands[:, sel].mean(axis=1))
        w0 += HOP
    return np.array(out)


def stats(folder, start=0.0, end=None):
    acc, voc = folder / "accompaniment.flac", folder / "vocals.flac"
    end = end or librosa.get_duration(path=acc)
    a, v = band_windows(acc, start, end), band_windows(voc, start, end)
    db = lambda x: 10 * np.log10(np.maximum(x, 1e-12))
    a_hi, v_hi = a[:, 2:].sum(axis=1), v[:, 2:].sum(axis=1)
    level = db(a_hi)
    shape = db(a[:, 2:] / a_hi[:, None])        # spectral shape above 250 Hz, level removed
    return {"level_vs_vocal_db": round(float(db(a_hi.mean()) - db(v_hi.mean())), 1),
            "level_range_db": round(float(np.percentile(level, 90) - np.percentile(level, 10)), 1),
            "bass_share": round(float(a[:, :2].sum() / a.sum()), 2),
            "timbre_change_db": round(float(np.median(np.abs(shape - shape.mean(axis=0)).mean(axis=1))), 2),
            "shape": [round(float(x), 1) for x in shape.mean(axis=0)]}


def main():
    rows = {}
    songs = ["amazing-grace", "what-child-is-this", "it-came-upon-a-midnight-clear", "jeanie"]
    for sid in songs:
        for k in ("", "-s2", "-s3"):
            folder = HERE / "renders" / f"{sid}-syl{k}"
            al = json.loads((folder / "alignment-dtw.json").read_text())
            # the song part of the raw take: from its first to its last map point (audio time)
            start, end = al["map"][0][0] + 2.0, al["map"][-1][0]
            rows[folder.name] = {"style": json.loads((folder / "report.json").read_text())["style"], **stats(folder, start, end)}
    for name in ("autumn-road-stems", "garden-morning", "garden-morning-intro"):
        folder = SPIKE / name
        if (folder / "accompaniment.flac").is_file():
            rows[name] = {"style": json.loads((folder / "report.json").read_text())["style"], **stats(folder)}
    print(f"{'take':40s} vs vocal  range  bass  timbre")
    for name, r in rows.items():
        print(f"{name:40s} {r['level_vs_vocal_db']:+6.1f}  {r['level_range_db']:5.1f}  {r['bass_share']:.0%}   {r['timbre_change_db']:.2f}")
    # between seeds of the same song: spread of level vs vocal, and distance between average shapes
    print("\nBetween seeds (same song, same prompt):")
    for sid in songs:
        rs = [rows[f"{sid}-syl{k}"] for k in ("", "-s2", "-s3")]
        lv = [r["level_vs_vocal_db"] for r in rs]
        sh = np.array([r["shape"] for r in rs])
        print(f"  {sid:32s} level vs vocal {min(lv):+.1f} .. {max(lv):+.1f} dB   shape spread {np.abs(sh - sh.mean(axis=0)).mean():.2f} dB")
    # prompt test: same score, lyrics and seed, only the style differs (build/<song>/yue2/backing/).
    # All measured the same way here: the whole take minus the first 3 s and last 5 s.
    print("\nBacking prompt test (seeds 1 and 3):")
    for sid in ("amazing-grace", "what-child-is-this"):
        for label, pattern in (("profile (as rendered)", f"{sid}-syl{{k}}"), ("specific", f"{sid}-syl-spec{{k}}"),
                               ("folk trio", f"{sid}-syl-folk{{k}}")):
            rs = []
            for k in (1, 3):
                name = pattern.format(k="" if k == 1 and pattern.endswith("-syl{k}") else f"-s{k}")
                folder = HERE / "renders" / name
                if (folder / "accompaniment.flac").is_file():
                    end = librosa.get_duration(path=folder / "accompaniment.flac") - 5.0
                    r = stats(folder, 3.0, end)
                    rows[name + "/prompt-test"] = {"style": json.loads((folder / "report.json").read_text())["style"], **r}
                    rs.append(r)
            if rs:
                f = lambda key, fmt: " / ".join(format(r[key], fmt) for r in rs)
                print(f"  {sid:20s} {label:22s} vs vocal {f('level_vs_vocal_db', '+.1f'):14s} "
                      f"range {f('level_range_db', '.1f'):11s} bass {f('bass_share', '.0%'):9s} "
                      f"timbre {f('timbre_change_db', '.1f')}")
    (HERE / "build" / "backing_stats.json").write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main()
