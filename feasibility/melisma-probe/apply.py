"""Bend the melismas into a song's approved vocal at every tempo preset, ready to submit as an
update to the live song (a one-off for the songs the parent asked about; the media skill doesn't do
this yet, HANDOFF.md).

    tools/.venv/bin/python feasibility/melisma-probe/apply.py PIECE.yaml [--check]

From the approved take's aligned stems in tools/.media/work/<id>/ (the files the media skill
packaged), for each preset:
  1. the melisma notes' pitch measured in the vocal's mono sum, and the bend curve built, every
     time divided by the preset's ratio (a melisma is short or long by its 100% length);
  2. the mono sum bent with Praat's overlap-add (psola.py);
  3. inside each bent melisma the bent mono on both channels, the stereo original everywhere
     else, joined where the two are the same (melisma.splice_weights);
  4. then exactly the media skill's package step: the end faded (media.song_only), one gain for
     every preset from the 100% vocal, MP3 (synth.mp3).
The accompaniment stems are copied as they are. The approved media folder is first copied to
out/approved/<id>/ (kept: the probe reads the approved stems from there afterwards), then replaced.

--check makes the vocals without bending (no regions) into out/check/<id>/ and compares them with
the approved MP3s: the same take, timeline and level, so only the bend differs.
"""
from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf

import melisma as ml

sys.path.insert(0, str(ml.ROOT / "tools" / "media"))
import align  # noqa: E402
import media  # noqa: E402
import synth  # noqa: E402

ENGINE_NOTE = "melismas bent onto the written notes (Praat overlap-add)"


def make(piece_path: Path, check: bool = False) -> dict:
    piece = ml.common.load(piece_path)
    approved = ml.approved_dir(piece)
    m = json.loads((approved / "media.json").read_text())
    if ENGINE_NOTE in m["engine"]:
        raise SystemExit(f"{piece.pid}: the approved media is already bent")
    take, mode = m["take"].split(" (")[0], m["take"].split("(")[1].rstrip(")")
    choice = json.loads((piece.work / "choice.json").read_text())
    assert (choice["take"], choice["mode"]) == (take, mode), "the work folder's chosen take isn't the approved one"
    folder = piece.work / "renders" / take
    src = folder / f"aligned-{mode}"
    pad = float(Fraction(str(m["padBeats"])))
    full_at = ml.stem_time(piece, pad)
    found = ml.melismas(piece)
    end_s = align.score_notes(folder / "score.abc")[0][-1][1]
    start = int(choice["songStartS"] * ml.SR)
    v100, _ = sf.read(src / "vocals_100.wav", always_2d=True)
    gain = media.VOCAL_DB - media.rms_db(media.song_only(v100, ml.SR, end_s)[start:])

    out = ml.HERE / "out" / ("check" if check else "apply") / piece.pid
    out.mkdir(parents=True, exist_ok=True)
    report = {"piece": piece.pid, "take": m["take"], "melismas": len(found), "presets": {}}
    for key, ratio in ml.common.PRESETS.items():
        y, sr = sf.read(src / f"vocals_{key}.wav", always_2d=True)
        assert sr == ml.SR
        mid = y.mean(axis=1)
        at = lambda beat, r=ratio: full_at(beat) / r
        f, v = ml.pitch_track(mid.astype(np.float32))
        before = ml.on_pitch(found, at, f, v)
        melody_before = ml.melody_on_pitch(piece, at, f, v)
        if check:
            final = y
            rep = {}
        else:
            pts, regions = ml.contour(found, at, f, v, kinds=("bend", "split"), glide_s=ml.GLIDE_S / ratio)
            sf.write(out / f"mid_{key}.wav", mid, sr)
            ml.bend_psola(out / f"mid_{key}.wav", pts, out / f"bent_{key}.wav")
            bent = ml.load_mono(out / f"bent_{key}.wav")
            wa, wb, joins = ml.splice_weights(mid, bent, regions)
            n = len(wa)
            final = y[:n] * wa[:, None] + bent[:n, None] * wb[:, None]
            if n < len(y):
                final = np.concatenate([final, y[n:]])
            f2, v2 = ml.pitch_track(final.mean(axis=1).astype(np.float32))
            rep = {"bent": len(regions), "joins": joins, "melismaNotesAfter": ml.on_pitch(found, at, f2, v2),
                   "melodyAfter": ml.melody_on_pitch(piece, at, f2, v2)}
            (out / f"mid_{key}.wav").unlink()
        synth.mp3(synth.level(media.song_only(final, sr, end_s / ratio), gain), out / f"vocals_{key}.mp3", sr)
        report["presets"][key] = {"melismaNotesBefore": before, "melodyBefore": melody_before, **rep}
        print(f"  {key}%: " + json.dumps(report["presets"][key]), flush=True)

    if check:
        for key in ml.common.PRESETS:
            a = ml.load_mono(approved / f"vocals_{key}.mp3")
            b = ml.load_mono(out / f"vocals_{key}.mp3")
            n = min(len(a), len(b))
            d = 10 * np.log10(np.mean((a[:n] - b[:n]) ** 2) / np.mean(a[:n] ** 2))
            report["presets"][key]["againstApprovedDb"] = round(float(d), 1)
            print(f"  {key}%: rebuilt without a bend, against the approved MP3: {d:.1f} dB (lengths {len(a)} {len(b)})")
        return report

    # keep the approved media, then replace it with the bent version
    keep = ml.HERE / "out" / "approved" / piece.pid
    if not (keep / "media.json").exists():
        shutil.copytree(piece.media_dir, keep)
    for key in ml.common.PRESETS:
        shutil.copy2(out / f"vocals_{key}.mp3", piece.media_dir / f"vocals_{key}.mp3")
    p100 = report["presets"]["100"]
    m["engine"] = f"{m['engine']}; {ENGINE_NOTE}"
    m["made"] = datetime.date.today().isoformat()
    m["melisma"] = {"method": "bend", "engine": "Praat overlap-add (parselmouth)", "melismas": len(found),
                    "bent": p100["bent"], "notesOnPitch": {"before": p100["melismaNotesBefore"], "after": p100["melismaNotesAfter"]},
                    "melodyOnStaff": {"before": p100["melodyBefore"], "after": p100["melodyAfter"]},
                    "presets": {k: {"after": r["melismaNotesAfter"]} for k, r in report["presets"].items()},
                    "probe": "feasibility/melisma-probe/apply.py"}
    flag = (f"melismas bent onto the written notes: {p100['melismaNotesAfter'][0]} of {p100['melismaNotesAfter'][1]} "
            f"melisma notes on pitch (were {p100['melismaNotesBefore'][0]}); listen at the melismas")
    m["check"]["flags"] = [x for x in m["check"].get("flags", []) if not x.startswith("melismas bent")] + [flag]
    for key, pr in m["presets"].items():
        pr["bytes"] = sum((piece.media_dir / pr[s]).stat().st_size for s in ("vocals", "accompaniment") if pr.get(s))
    (piece.media_dir / "media.json").write_text(json.dumps(m, indent=1) + "\n")
    (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pieces", nargs="+", type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    for p in a.pieces:
        print(p.stem, flush=True)
        make(p.resolve(), a.check)
