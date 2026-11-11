"""Render hybrid takes with YuE2 and finish them: short melismas split onto their vowel in YuE2's
input, long ones bent after alignment.

    tools/.venv/bin/python feasibility/melisma-probe/render.py PIECE.yaml [--short 0.3] [--takes 2] [--max-takes 3]

Runs the media skill's own vocal step (tools/media/media.py `vocal`: YuE2 takes, alignment in both
modes, every check, the best take chosen) with the hybrid export in place of yue2.export, in the
probe's own work folder (out/work-<short>/<piece>/), so nothing of the real pipeline's is touched.
Then bends the long melismas into the chosen take and measures every melisma against the staff.
GPU: one render at a time.
"""
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

import soundfile as sf

import melisma as ml

sys.path.insert(0, str(ml.ROOT / "tools" / "media"))
import media  # noqa: E402


def run(piece_path: Path, short_s: float, takes: int, max_takes: int) -> dict:
    piece = ml.common.load(piece_path)
    ml.common.WORK = ml.HERE / "out" / f"work-{short_s:g}"
    real = ml.yue2.export
    found: list[dict] = []

    def export(nota, octave=0, line=None):
        abc, lyrics, abcmap, f = ml.hybrid_export(piece, short_s, export=real)
        found[:] = f
        return abc, lyrics, abcmap

    ml.yue2.export = export
    try:
        choice = media.vocal(piece, takes, max_takes)
    finally:
        ml.yue2.export = real
    folder = piece.work / "renders" / choice["take"]
    vocal = folder / f"aligned-{choice['mode']}" / "vocals_100.wav"
    a = json.loads((folder / f"alignment-{choice['mode']}.json").read_text())
    pad = float(Fraction(str(choice["padBeats"])))
    at = ml.stem_time(piece, pad)
    out = piece.work / "final"
    out.mkdir(exist_ok=True)
    y = ml.load_mono(vocal)
    sf.write(out / "vocal_in.wav", y, ml.SR)
    f, v = ml.pitch_track(y)
    kinds = lambda k: [m for m in found if m["kind"] == k]
    pts, regions = ml.contour(found, at, f, v, kinds=("bend",))
    rep = {"piece": piece.pid, "shortS": short_s, "take": choice["take"], "mode": choice["mode"], "pass": choice["pass"],
           "candidates": choice["candidates"], "padBeats": pad,
           "checks": {"notesOnPitchOfLineSent": a["pitch"]["share"], "wordsOff": a["words"]["shareOver300ms"],
                      "wordsHeard": (a.get("heard") or {}).get("share"), "worstPhraseMs": a["checks"]["worstPhraseMs"],
                      "reasons": a["checks"]["reasons"], "flags": a["checks"]["flags"]},
           "melismas": {"split": len(kinds("split")), "bend": len(kinds("bend"))},
           "asRendered": {"splitNotes": ml.on_pitch(kinds("split"), at, f, v), "bendNotes": ml.on_pitch(kinds("bend"), at, f, v),
                          "melody": ml.melody_on_pitch(piece, at, f, v)}}
    final = y
    if regions:
        ml.bend_psola(out / "vocal_in.wav", pts, out / "raw_psola.wav")
        z = ml.load_mono(out / "raw_psola.wav")
        final, joins = ml.splice(y, z, regions)
        f, v = ml.pitch_track(final)
        rep["bent"] = {"regions": len(regions), "joins": joins, "bendNotes": ml.on_pitch(kinds("bend"), at, f, v),
                       "splitNotes": ml.on_pitch(kinds("split"), at, f, v), "melody": ml.melody_on_pitch(piece, at, f, v)}
    sf.write(out / "vocal_hybrid.wav", final, ml.SR)
    (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("piece", type=Path)
    ap.add_argument("--short", type=float, default=ml.SHORT_S, help="melismas with a note shorter than this (s) are split")
    ap.add_argument("--takes", type=int, default=2)
    ap.add_argument("--max-takes", type=int, default=3)
    a = ap.parse_args()
    print(json.dumps(run(a.piece.resolve(), a.short, a.takes, a.max_takes)))
