"""Bend the melismas into a beat-aligned vocal and measure the result.

    tools/.venv/bin/python feasibility/melisma-probe/bend.py PIECE.yaml [--vocal FILE --pad BEATS] [--kinds bend,split]
                                                               [--engines psola,rubberband] [--out DIR]

Without --vocal it takes the piece's approved 100% vocal (<media dir>/vocals_100.mp3, pad from
media.json). Writes, per engine, <out>/<piece>/vocal_<engine>.wav (the bent audio spliced into the
original) and report.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import soundfile as sf

import melisma as ml


def run(piece_path: Path, vocal: Path | None, pad: float | None, kinds: tuple[str, ...], engines: list[str], out: Path,
        glide_s: float = ml.GLIDE_S, preset: str = "100") -> dict:
    """`preset`: bend that tempo version (its file is the 100% one slowed, so every time and the
    slides are longer by the same ratio)."""
    ratio = ml.common.PRESETS[preset]
    piece = ml.common.load(piece_path)
    if vocal is None:
        media = json.loads((ml.approved_dir(piece) / "media.json").read_text())
        vocal, pad = ml.approved_dir(piece) / f"vocals_{preset}.mp3", float(media["padBeats"])
    out = out / (piece.pid if preset == "100" else f"{piece.pid}-{preset}")
    out.mkdir(parents=True, exist_ok=True)
    full = ml.stem_time(piece, pad)
    at = lambda beat: full(beat) / ratio
    found = ml.melismas(piece)            # short or long is decided at the 100% tempo, whatever the preset
    y = ml.load_mono(vocal)
    src = out / "vocal_in.wav"
    sf.write(src, y, ml.SR)
    f, v = ml.pitch_track(y)
    pts, regions = ml.contour(found, at, f, v, kinds=kinds, glide_s=glide_s / ratio)
    chosen = [m for m in found if m["kind"] in kinds]
    rep = {"piece": piece.pid, "preset": preset, "vocal": str(vocal), "melismas": len(found),
           "bend": sum(m["kind"] == "bend" for m in found), "split": sum(m["kind"] == "split" for m in found),
           "bentHere": len(regions), "endsInGap": sum(r["endsInGap"] for r in regions),
           "before": {"melismaNotes": ml.on_pitch(chosen, at, f, v), "melody": ml.melody_on_pitch(piece, at, f, v)},
           "engines": {}, "regions": regions}
    for e in engines:
        raw = out / f"raw_{e}.wav"
        (ml.bend_psola if e == "psola" else ml.bend_rubberband)(src, pts, raw)
        z = ml.load_mono(raw)
        rough_raw = ml.roughness(y, z, regions)
        mixed, joins = ml.splice(y, z, regions)
        sf.write(out / f"vocal_{e}.wav", mixed, ml.SR)
        f2, v2 = ml.pitch_track(mixed)
        rep["engines"][e] = {"melismaNotes": ml.on_pitch(chosen, at, f2, v2), "melody": ml.melody_on_pitch(piece, at, f2, v2),
                             "unspliced": rough_raw, "spliced": ml.roughness(y, mixed, regions), "joins": joins}
    (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("piece", type=Path)
    ap.add_argument("--vocal", type=Path)
    ap.add_argument("--pad", type=float, help="the stem's lead-in in song beats (with --vocal)")
    ap.add_argument("--kinds", default="bend", help="which melismas to bend: bend, split or bend,split")
    ap.add_argument("--engines", default="psola,rubberband")
    ap.add_argument("--glide", type=float, default=ml.GLIDE_S)
    ap.add_argument("--preset", default="100", choices=list(ml.common.PRESETS), help="which tempo version of the approved vocal")
    ap.add_argument("--out", type=Path, default=ml.HERE / "out" / "bend")
    a = ap.parse_args()
    r = run(a.piece.resolve(), a.vocal, a.pad, tuple(a.kinds.split(",")), a.engines.split(","), a.out, a.glide, a.preset)
    r.pop("regions")
    print(json.dumps(r))
