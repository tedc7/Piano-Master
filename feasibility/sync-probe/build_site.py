"""Build the sync test page (tests 2, 3 and 4) into dist/, ready to deploy as https://<piano-server>/sync/.

    .venv/bin/python build_site.py

dist/
  index.html, vexflow-bravura.js       the page and VexFlow 4.2.5 (served locally, no CDN)
  manifest.json                        songs, stems, sizes, alignment summaries
  songs/<id>/notation.json             arch §5 notation from convert.py
  songs/<id>/<take>-<mode>_{vocals,accompaniment}_<preset>.mp3   aligned stems, 128 kbps
      per song: the best take and the best of the other alignment mode (select_takes.py)
      presets: 100, 90, 75, 50 (Rubber Band, from the 100% take)
"""
from __future__ import annotations

import json
import re
import shutil
from fractions import Fraction
from pathlib import Path

import soundfile as sf

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
RENDERS = HERE / "renders"
BUILD = HERE / "build"
VEXFLOW = HERE.parent / "render-probe" / "vexflow-bravura.js"
RATIOS = {"100": 1.0, "90": 0.9, "75": 0.75, "50": 0.5}


def mp3(src: Path, dst: Path):
    y, sr = sf.read(src, always_2d=True)
    sf.write(dst, y, sr, format="MP3", bitrate_mode="CONSTANT", compression_level=0.5)
    return dst.stat().st_size


def summary(al):
    if not al:
        return None
    keep = ("audio_seconds", "score_seconds", "windows", "anchors", "before", "held_out", "after_100", "after_50",
            "ruler", "pitch_before", "pitch_100", "pitch_50", "accompaniment_before", "accompaniment_after_100")
    return {k: al.get(k) for k in keep if k in al}


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "songs").mkdir(parents=True)
    shutil.copy(HERE / "site" / "index.html", DIST / "index.html")
    shutil.copy(VEXFLOW, DIST / "vexflow-bravura.js")
    config = json.loads((HERE / "songs.json").read_text())
    final = json.loads((BUILD / "final_takes.json").read_text())
    songs = []
    for song in config["songs"]:
        sid = song["id"]
        out = DIST / "songs" / sid
        out.mkdir()
        shutil.copy(BUILD / sid / "notation.json", out / "notation.json")
        entry = {"id": sid, "title": song["title"], "genre": song["genre"], "tests": song["tests"],
                 "source": song["source"]["from"], "notation": f"songs/{sid}/notation.json"}
        entry["takes"] = {}
        for pick in final.get(sid, []):
            take, mode = pick["take"], pick["mode"]
            folder = RENDERS / take
            variant = re.fullmatch(r".+-(intro|fake|syl|mel)(?:-folk|-spec)?(?:-s\d+)?", take).group(1)
            m = json.loads((BUILD / sid / "yue2" / f"abcmap-{variant}.json").read_text())
            al = json.loads((folder / f"alignment-{mode}.json").read_text())
            key = f"{take}-{mode}"
            t = {"label": pick["label"], "default": pick["default"], "padBeats": float(Fraction(m["pad_beats"])),
                 "bpm": m["bpm"], "stems": {}}
            for preset in ("100", "90", "75", "50"):
                files = {}
                for stem in ("vocals", "accompaniment"):
                    dst = out / f"{key}_{stem}_{preset}.mp3"
                    files[stem] = {"url": f"songs/{sid}/{dst.name}",
                                   "bytes": mp3(folder / f"aligned-{mode}" / f"{stem}_{preset}.flac", dst)}
                t["stems"][preset] = {"ratio": RATIOS[preset], **files}
            q = al["qa"]
            t["check"] = {"notesOnPitch": al["pitch_100"]["pitch_ok"], "wordsOff": q["words"]["share_over_300ms"],
                          "firstWordSung": al["first_note_sung"], "wordStretches": q["word_regions"],
                          "melodyStretches": q["melody_regions"], "startOffset": al["before"]["first_offset_s"]}
            entry["takes"][key] = t
        songs.append(entry)
        print(sid, {v: sum(p[s]["bytes"] for p in t["stems"].values() for s in ("vocals", "accompaniment")) // 1024
                    for v, t in entry["takes"].items()}, "KB")
    (DIST / "manifest.json").write_text(json.dumps({"songs": songs}, indent=1) + "\n")


if __name__ == "__main__":
    main()
