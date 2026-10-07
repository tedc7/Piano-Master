"""The media skill's tools (arch §10.5): a sung vocal and a backing for each arrangement.

    tools/.venv/bin/python tools/media/media.py plan PIECES...      # what each piece gets, no rendering
    tools/.venv/bin/python tools/media/media.py make PIECES...      # everything below, in order
    tools/.venv/bin/python tools/media/media.py vocal PIECES...     # YuE2 takes, aligned and checked; the best chosen
    tools/.venv/bin/python tools/media/media.py backing PIECES...   # the FluidSynth backing at the four tempo presets
    tools/.venv/bin/python tools/media/media.py package PIECES...   # levels, MP3s and media.json
    tools/.venv/bin/python tools/media/media.py report BATCH        # MEDIA.md: the checks, for the parent

PIECES are piece files, batch folders (content/incoming/<batch>/) or library ids. What a piece gets
(the v0.22 decision):
  - words: a YuE2 vocal (2 takes, a third if neither passes; every take aligned in two modes and the
    best kept). No words: no vocal.
  - backing notes (other voices, chord symbols or a left hand): a FluidSynth backing with MuseScore
    General in the genre's style, or the style in the piece's `media: {backing: …}`.
  - words but no backing notes (or the style `yue2`): YuE2's own backing, aligned with the vocal.
  - the style `none` (the default for `genre: studies`, the curriculum songs): the vocal alone; the app's
    own piano plays the music.
Stems go to content/media/<id>/ for library pieces, and to <batch>/media/<id>/ for a batch (moved
with the piece by `import_song.py promote`). Work files (renders, alignments) are in
tools/.media/work/<id>/. The content build copies the stems into the client.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import align  # noqa: E402
import backing as bk  # noqa: E402
import synth  # noqa: E402
import yue2  # noqa: E402
from common import PAD_BEATS, PRESETS, ROOT, SR, Piece, pieces  # noqa: E402

VOCAL_DB = -20.0            # the vocal's RMS over the song (the sync probe's level, kept for v0.22)
YUE2_BACKING_BELOW_DB = 10.0   # YuE2's backing under the vocal above 250 Hz; the app plays backings at 200%
END_TAIL_S, END_FADE_S = 0.6, 0.4   # what's kept after the last note's end (its release), then faded out
TAKES = 2
MAX_TAKES = 3             # arch §10.5: re-render up to 3 tries


def rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def song_only(y: np.ndarray, sr: int, end_s: float) -> np.ndarray:
    """A YuE2 stem ending with the song: the last note's release kept, then faded to silence. Takes
    often sing on after the song ends, sometimes the whole song again (Up and Down the Staff: 4 s at
    full voice, Oct 7, 2026); the length stays, so every preset still lines up with the playback."""
    a, b = int((end_s + END_TAIL_S) * sr), int((end_s + END_TAIL_S + END_FADE_S) * sr)
    y = y.copy()
    if a < len(y):
        y[a:b] *= np.linspace(1.0, 0.0, len(y[a:b]))[:, None]
        y[b:] = 0
    return y


def plan_of(piece: Piece) -> dict:
    style = bk.style_of(piece)
    vocal = piece.has_words and (piece.spec.get("vocal", "yue2") != "none")
    if style == "none":     # a vocal alone: the app's own piano plays the music (the curriculum songs, v0.30)
        return {"vocal": vocal, "backing": None, "style": "none", "parts": [],
                "why": None if vocal else "no words, and the backing style is none"}
    try:
        name, parts = bk.parts_for(piece)
        why = None
    except bk.StyleError as e:
        name, parts, why = "yue2", [], str(e)
    if not vocal and name == "yue2":
        return {"vocal": False, "backing": None, "why": why or "no words and no backing notes: the app's own piano only"}
    return {"vocal": vocal, "backing": "yue2" if name == "yue2" else "fluidsynth", "style": style if name != "yue2" else "yue2",
            "parts": [p.describe() for p in parts], "why": why}


# ------------------------------------------------------------------------------ vocal

def vocal(piece: Piece, takes: int = TAKES, max_takes: int = MAX_TAKES, skip: frozenset[int] = frozenset()) -> dict | None:
    """Render, align and check YuE2 takes; the best (take, mode) goes to work/<id>/choice.json."""
    if not plan_of(piece)["vocal"]:
        return None
    ydir = yue2.write_inputs(piece)
    abcmap = json.loads((ydir / "abcmap.json").read_text())
    phrases = [Fraction(p) * Fraction(abcmap.get("scale", "1")) for p in piece.nota["phrases"]]   # in ABC beats
    results = []

    def run(take: int):
        if take in skip:          # a take the parent heard and sent back (--skip-take)
            print(f"  take {take}: skipped", flush=True)
            return
        r = yue2.render(piece, take)
        if r.get("exit", 0) not in (0, None) or r.get("status") not in ("ok", "complete", None):
            print(f"  take {take}: render failed: {r.get('error') or r.get('reason') or r}", flush=True)
            return
        folder = piece.work / "renders" / f"{piece.pid}-s{take}"
        h = align.heard(folder, [w["word"] for w in abcmap["words"][1:]])   # the words, after the lead-in "Oh,"
        for mode in align.MODES:
            f = folder / f"alignment-{mode}.json"
            a = json.loads(f.read_text()) if f.exists() else None
            if a is None or a.get("wordsIn", abcmap["words"]) != abcmap["words"]:   # aligned to other words: again
                a = align.align(folder, abcmap, phrases, mode)
            a["wordsIn"] = abcmap["words"]
            if a.get("error"):
                print(f"  take {take} ({mode}): {a['error']}", flush=True)
                continue
            a["heard"] = {"heard": h["heard"], "share": h["share"]}
            a["checks"] = align.verdict(a)                     # judged by the current rules
            a["score"] = align.score(a)
            f.write_text(json.dumps(a, indent=1) + "\n")
            results.append(a)
            c = a["checks"]
            print(f"  take {take} ({mode}): score {a['score']:+.2f}, on pitch {a['pitch']['share']:.0%}, "
                  f"words off {a['words']['shareOver300ms']:.0%}, worst phrase {c['worstPhraseMs']:.0f} ms, "
                  f"heard {h['share']:.0%}, tuning {a['tuningCents']:+} c, bleed {a['bleed']['db']} dB: {'PASS' if c['pass'] else 'FAIL: ' + '; '.join(c['reasons'])}"
                  + (f" (flag: {'; '.join(c['flags'])})" if c["flags"] else ""),
                  flush=True)

    for t in range(1, takes + 1):
        run(t)
    t = takes
    while not any(r["checks"]["pass"] for r in results) and t < min(max_takes, len(yue2.SEEDS)):
        t += 1
        print(f"  no take passed: rendering take {t}", flush=True)
        run(t)
    if not results:
        raise RuntimeError(f"{piece.pid}: no usable YuE2 take")
    best = max(results, key=lambda r: (r["checks"]["pass"], r["score"]))
    choice = {"take": best["take"], "mode": best["mode"], "pass": best["checks"]["pass"], "score": best["score"],
              "padBeats": abcmap.get("songPadBeats", abcmap["padBeats"]), "bpm": piece.bpm, "songStartS": best["songStartS"],
              "candidates": [{"take": r["take"], "mode": r["mode"], "score": r["score"], "pass": r["checks"]["pass"],
                              "reasons": r["checks"]["reasons"]} for r in sorted(results, key=lambda r: -r["score"])]}
    (piece.work / "choice.json").write_text(json.dumps(choice, indent=1) + "\n")
    print(f"  chosen: {best['take']} ({best['mode']}), {'passes' if best['checks']['pass'] else 'FAILS: ' + '; '.join(best['checks']['reasons'])}", flush=True)
    return choice


# ------------------------------------------------------------------------------ backing

def pad_beats(piece: Piece) -> float:
    """The stems' lead-in: the vocal's (its "Oh" bar and the pickup's rests), else one beat."""
    f = piece.work / "yue2" / "abcmap.json"
    if plan_of(piece)["vocal"] and f.exists():
        m = json.loads(f.read_text())
        return float(Fraction(m.get("songPadBeats", m["padBeats"])))
    return PAD_BEATS


def backing(piece: Piece) -> dict | None:
    plan = plan_of(piece)
    if plan["backing"] != "fluidsynth":
        return None
    name, parts = bk.parts_for(piece)
    rep = synth.render(parts, piece.bpm, pad_beats(piece), piece.work / "backing")
    rep["style"] = name
    (piece.work / "backing" / "report.json").write_text(json.dumps(rep, indent=1) + "\n")
    print(f"  backing ({name}): {', '.join(p.name for p in parts)}; worst part {rep['timing']['worstPartMedianMs']} ms "
          f"after starting early {rep['leadMs']}; " + ", ".join(f"{k}% {v['seconds']} s" for k, v in rep["presets"].items()), flush=True)
    return rep


# ------------------------------------------------------------------------------ package

def rms_db(y: np.ndarray) -> float:
    return 20 * np.log10(max(float(np.sqrt(np.mean(y ** 2))), 1e-12))


def package(piece: Piece) -> dict:
    """Stems at every preset, levelled, as MP3 in the piece's media folder, and media.json."""
    plan = plan_of(piece)
    out = piece.media_dir
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    presets = {k: {"ratio": r} for k, r in PRESETS.items()}
    media = {"engine": None, "take": None, "padBeats": pad_beats(piece), "bpm": piece.bpm,
             "beats": float(piece.nota["length"]), "made": datetime.date.today().isoformat(), "plan": plan,
             "presets": presets, "check": None}
    engines = []
    choice = None
    if plan["vocal"]:
        choice = json.loads((piece.work / "choice.json").read_text())
        folder = piece.work / "renders" / choice["take"]
        keep_yue2 = plan["backing"] == "yue2"
        align.tempo_versions(folder, choice["mode"], PRESETS, choice["songStartS"], keep_yue2)
        a = json.loads((folder / f"alignment-{choice['mode']}.json").read_text())
        slow = align.check_preset(folder, choice["mode"], "50", PRESETS["50"])
        src = folder / f"aligned-{choice['mode']}"
        start = int(choice["songStartS"] * SR)
        end_s = align.score_notes(folder / "score.abc")[0][-1][1]     # the last note's end, at 100%
        v100, _ = sf.read(src / "vocals_100.wav", always_2d=True)
        v100 = song_only(v100, SR, end_s)
        gain = VOCAL_DB - rms_db(v100[start:])                        # one gain for every preset
        for key, ratio in PRESETS.items():
            v, sr = sf.read(src / f"vocals_{key}.wav", always_2d=True)
            synth.mp3(synth.level(song_only(v, sr, end_s / ratio), gain), out / f"vocals_{key}.mp3", sr)
            presets[key]["vocals"] = f"vocals_{key}.mp3"
        if keep_yue2:
            import scipy.signal as ss
            hp = lambda y, sr: ss.sosfilt(ss.butter(2, 120 / (sr / 2), "high", output="sos"), y, axis=0)
            b100, sr = sf.read(src / "accompaniment_100.wav", always_2d=True)
            bgain = None
            for key, ratio in PRESETS.items():
                b, sr = sf.read(src / f"accompaniment_{key}.wav", always_2d=True)
                b = hp(song_only(b, sr, end_s / ratio), sr)
                if bgain is None:
                    k = int(choice["songStartS"] * sr)
                    bgain = align_band(v100[k:] * 10 ** (gain / 20), sr) - YUE2_BACKING_BELOW_DB - align_band(b[k:], sr)
                synth.mp3(synth.level(b, bgain), out / f"accompaniment_{key}.mp3", sr)
                presets[key]["accompaniment"] = f"accompaniment_{key}.mp3"
            engines.append("YuE2 vocal and backing")
        else:
            engines.append("YuE2 vocal")
        media["take"] = f"{choice['take']} ({choice['mode']})"
        media["check"] = {"notesOnPitch": a["pitch"]["share"], "wordsOff": a["words"]["shareOver300ms"],
                          "wordsHeard": (a.get("heard") or {}).get("share"), "heard": (a.get("heard") or {}).get("heard"),
                          "firstWordSung": a["firstWordSung"], "wordStretches": a["words"]["stretches"],
                          "melodyStretches": a["melodyStretches"], "worstPhraseMs": a["checks"]["worstPhraseMs"],
                          "grid100": a["after"], "grid50": slow,
                          "tuningCents": a["tuningCents"], "bleedDb": a["bleed"]["db"], "pass": a["checks"]["pass"],
                          "reasons": a["checks"]["reasons"], "flags": a["checks"]["flags"]}
    if plan["backing"] == "fluidsynth":
        rep = json.loads((piece.work / "backing" / "report.json").read_text())
        for key, p in rep["presets"].items():
            shutil.copy2(piece.work / "backing" / p["file"], out / p["file"])
            presets[key]["accompaniment"] = p["file"]
        engines.append(f"FluidSynth backing ({rep['style']}, MuseScore General)")
        media["backing"] = {"style": rep["style"], "parts": rep["parts"], "leadMs": rep["leadMs"], "timing": rep["timing"]}
    if not engines:
        shutil.rmtree(out)
        return {}
    media["engine"] = " + ".join(engines)
    if not plan["vocal"]:
        media["take"] = media["backing"]["style"]
    for p in presets.values():
        p["bytes"] = sum((out / p[s]).stat().st_size for s in ("vocals", "accompaniment") if p.get(s))
    (out / "media.json").write_text(json.dumps(media, indent=1) + "\n")
    size = sum(p["bytes"] for p in presets.values()) / 1e6
    print(f"  packaged {rel(out)}: {media['engine']}, {size:.1f} MB for four presets", flush=True)
    return media


def align_band(y: np.ndarray, sr: int, lo: float = 250.0) -> float:
    import scipy.signal as ss
    yh = ss.sosfilt(ss.butter(4, lo / (sr / 2), "high", output="sos"), y.mean(axis=1))
    return rms_db(yh)


# ------------------------------------------------------------------------------ report

def report(batch: Path) -> Path:
    """MEDIA.md in the batch: each piece's media and its checks, for the parent's review."""
    rows = ["# Media for this batch", "",
            "Made by the media skill (arch §10.5): a YuE2 vocal for songs with words, and a FluidSynth backing "
            "(MuseScore General) from the piece's own backing notes. Listen before approving: the checks find "
            "timing, pitch and word problems, not whether it sounds good.", "",
            "| Piece | Vocal | Backing | Checks |", "| --- | --- | --- | --- |"]
    for f in sorted(batch.glob("*.yaml")):
        mj = batch / "media" / f.stem / "media.json"
        if not mj.exists():
            rows.append(f"| {f.stem} | none | none | no media made |")
            continue
        m = json.loads(mj.read_text())
        c = m.get("check") or {}
        vocal = (f"{m['take']}: {c['notesOnPitch']:.0%} of notes on pitch, {c['wordsOff']:.0%} of words off the staff, "
                 + (f"{c['wordsHeard']:.0%} of words heard by Whisper, " if c.get("wordsHeard") is not None else "") +
                 f"on the beat within {c['grid100']['median_ms']:.0f} ms at 100% and {c['grid50']['median_ms']:.0f} ms at 50% "
                 f"(median), tuning {c['tuningCents']:+} cents") if c else "none"
        b = m.get("backing")
        back = f"{b['style']}: " + ", ".join(p["name"] for p in b["parts"]) if b else ("YuE2's own" if "backing" in m["engine"] else "none")
        checks = "pass" if (not c or c["pass"]) and (not b or b["timing"]["pass"]) else \
            "; ".join((c.get("reasons") or []) + ([] if not b or b["timing"]["pass"] else [f"backing {b['timing']['worstPartMedianMs']} ms off"]))
        if c and c.get("flags"):
            checks += "; listen for: " + "; ".join(c["flags"])
        rows.append(f"| {f.stem} | {vocal} | {back} | {checks} |")
    out = batch / "MEDIA.md"
    out.write_text("\n".join(rows) + "\n")
    return out


# ------------------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("plan", "make", "vocal", "backing", "package", "report"))
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--takes", type=int, default=TAKES, help="YuE2 takes to render first (default 2)")
    ap.add_argument("--max-takes", type=int, default=MAX_TAKES, help="takes to try before keeping the best failing one (default 3, at most 24)")
    ap.add_argument("--skip-take", type=int, action="append", default=[], help="a take the parent sent back: never chosen (repeatable)")
    args = ap.parse_args(argv)
    if args.cmd == "report":
        for t in args.targets:
            print(f"wrote {rel(report(Path(t)))}")
        return 0
    failed: list[str] = []
    for piece in pieces(args.targets):
        print(f"{piece.pid} ({piece.title})", flush=True)
        if args.cmd == "plan":
            p = plan_of(piece)
            print(f"  vocal: {'YuE2' if p['vocal'] else 'none'}; backing: {p['backing'] or 'none'}"
                  + (f" ({p['style']}: {', '.join(x['name'] for x in p['parts'])})" if p.get("parts") else "")
                  + (f"; {p['why']}" if p.get("why") else ""))
            continue
        if args.cmd in ("vocal", "make"):
            try:
                vocal(piece, args.takes, args.max_takes, frozenset(args.skip_take))
            except RuntimeError as e:          # one song without a usable take doesn't stop the batch
                print(f"  {e}: nothing packaged", flush=True)
                failed.append(piece.pid)
                continue
        if args.cmd in ("backing", "make"):
            backing(piece)
        if args.cmd in ("package", "make"):
            package(piece)
    if failed:
        print(f"no usable vocal take: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
