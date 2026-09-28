#!/usr/bin/env python3
"""Reliable front end for text/score-to-music generation (engine: YuE2).

Standard library only, so any python3 can run it. It validates a request,
applies an optional profile, then runs the engine worker in the engine's own
venv as a separate process (GPU memory is freed when the worker exits).

    python3 generate_music.py --request song.json --out renders/
    python3 generate_music.py --request song.json --out renders/ --seed 7 --dry-run

The last stdout line is always one JSON object (the report, or the error).
Exit codes: 0 ok, 2 invalid request, 3 engine error (incl. out of memory),
4 finished but truncated. See ../references/request-format.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import unicodedata
from fractions import Fraction
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
ENGINE_HOME = Path(os.environ.get("YUE2_HOME", Path.home() / "engines" / "yue2"))
ENGINE_PY = ENGINE_HOME / ".venv" / "bin" / "python"
ABC_TOOLS = ENGINE_HOME / "YuE" / "skills" / "yue2-music" / "scripts" / "abc_tools.py"
WORKER = Path(__file__).resolve().parent / "engine_yue2.py"

FIELDS = {"id", "lyrics", "lyrics_path", "style", "score_abc", "score_abc_path", "plan", "seed",
          "stems", "formats", "profile", "title", "notes", "syllables", "syllables_path",
          # profile fields (only meaningful when a profile uses them)
          "genre", "language", "key", "meter", "tempo_bpm", "vocal_style", "accompaniment_style"}
PLANS = {"auto", "full", "melody", "off"}
FORMATS = {"flac", "wav", "mp3"}
INSTRUMENTAL_SECTIONS = {"intro", "interlude", "outro", "instrumental", "solo", "break", "inst"}
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")


class RequestError(ValueError):
    pass


def check(condition, message):
    if not condition:
        raise RequestError(message)


def emit(obj, code):
    print(json.dumps(obj, ensure_ascii=False))
    return code


def load_abc_tools():
    check(ABC_TOOLS.is_file(), f"engine not installed (missing {ABC_TOOLS}); run scripts/install_engine.sh")
    spec = importlib.util.spec_from_file_location("abc_tools", ABC_TOOLS)
    module = importlib.util.module_from_spec(spec)
    sys.modules["abc_tools"] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


def read_text_field(req, name, base):
    """Return inline text, or the contents of <name>_path (relative to the request file)."""
    inline, path = req.get(name), req.get(f"{name}_path")
    check(not (inline and path), f"give {name} or {name}_path, not both")
    if path:
        file = (base / path).expanduser()
        check(file.is_file(), f"{name}_path not found: {file}")
        return file.read_text(encoding="utf-8")
    return inline


def lyric_sections(lyrics):
    return [m.group(1).strip().lower().split()[0] for m in re.finditer(r"^\s*\[([^\]]+)\]\s*$", lyrics, re.M)]


def abc_sections(abc):
    return [line[2:].strip().lower().split()[0] for line in abc.splitlines() if line.startswith("% ") and line[2:].strip()]


def abc_header(abc, field):
    for line in abc.splitlines():
        if line.startswith(field + ":"):
            return line[len(field) + 1:].strip()
    return None


def normalize_key(key):
    key = key.strip().replace(" major", "").replace("maj", "")
    return re.sub(r"\s*minor$|min$", "m", key)


def letters(text):
    """Letters and digits only, accents removed, case folded (for comparing syllables with lyrics)."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text.casefold() if c.isalnum())


def read_syllables(req, base):
    """The sung syllables in order: `syllables` (a JSON list) or `syllables_path` (a JSON file holding
    that list, or an object with a "syllables" list). Each item is a string, or an object
    {"syllable": str, "beat": onset in quarter notes from the start of the score, as a number or "a/b"}."""
    inline, path = req.get("syllables"), req.get("syllables_path")
    check(not (inline is not None and path), "give syllables or syllables_path, not both")
    if path:
        file = (base / path).expanduser()
        check(file.is_file(), f"syllables_path not found: {file}")
        try:
            inline = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RequestError(f"syllables_path is not valid JSON: {exc}") from exc
        if isinstance(inline, dict):
            inline = inline.get("syllables")
    if inline is None:
        return None
    check(isinstance(inline, list) and inline, "syllables must be a non-empty list")
    rows = []
    for i, item in enumerate(inline):
        if isinstance(item, str):
            item = {"syllable": item}
        check(isinstance(item, dict) and isinstance(item.get("syllable"), str) and item["syllable"].strip(),
              f"syllables[{i}] must be a string or an object with a 'syllable' string")
        beat = item.get("beat")
        if beat is not None:
            try:
                beat = Fraction(str(beat))
            except (ValueError, ZeroDivisionError):
                raise RequestError(f"syllables[{i}].beat is not a number or fraction: {item['beat']!r}") from None
        rows.append({"syllable": item["syllable"].strip(), "beat": beat})
    return rows


def check_syllables(rows, score, lyrics):
    """One Vocal attack per sung syllable. YuE2 pairs lyric syllables with Vocal notes by itself (there
    is no alignment channel); extra notes let it drift words onto the wrong notes. Checks the count,
    each syllable's beat when given, and that the syllables spell the lyrics."""
    check(score is not None, "syllables need a score (score_abc or score_abc_path) to check against")
    attacks = score.voices["Vocal"].notes          # [onset, midi, duration], ties merged, quarter notes
    if len(attacks) != len(rows):
        where = next((i for i, (a, r) in enumerate(zip(attacks, rows)) if r["beat"] is not None and a[0] != r["beat"]), None)
        hint = (f"; the first extra or missing note is at beat {attacks[where][0]}, where syllable {where + 1} "
                f"{rows[where]['syllable']!r} expects beat {rows[where]['beat']}" if where is not None else "")
        check(False, f"{len(attacks)} Vocal attacks (ties merged) but {len(rows)} sung syllables: give each syllable "
                     f"exactly one Vocal note. Merge a melisma onto its first pitch, tie repeated notes of one "
                     f"syllable, split a note for an extra syllable (references/abc-quickref.md){hint}")
    for i, (a, r) in enumerate(zip(attacks, rows)):
        check(r["beat"] is None or a[0] == r["beat"],
              f"syllable {i + 1} {r['syllable']!r} is at beat {r['beat']} but its Vocal attack is at beat {a[0]}")
    sung = letters(re.sub(r"^\s*\[[^\]]+\]\s*$", "", lyrics, flags=re.M))
    spelled = letters("".join(r["syllable"] for r in rows))
    if sung != spelled:
        i = next((k for k, (x, y) in enumerate(zip(sung, spelled)) if x != y), min(len(sung), len(spelled)))
        check(False, f"the syllables don't spell the lyrics: from letter {i}, lyrics {sung[max(0, i - 10):i + 15]!r} "
                     f"vs syllables {spelled[max(0, i - 10):i + 15]!r}")
    return {"syllables": len(rows), "vocal_attacks": len(attacks),
            "beats_checked": sum(r["beat"] is not None for r in rows)}


def apply_profile(req, abc, score):
    name = req.get("profile")
    if not name:
        check(isinstance(req.get("style"), str) and req["style"].strip(), "style is required (free-text description)")
        return req["style"].strip(), None
    file = SKILL_DIR / "profiles" / f"{name}.json"
    check(file.is_file(), f"unknown profile {name!r} (no {file})")
    profile = json.loads(file.read_text(encoding="utf-8"))
    for field in profile.get("required", []):
        check(req.get(field) not in (None, ""), f"profile {name}: {field} is required")
    for field, value in profile.get("force", {}).items():
        check(req.get(field, value) == value, f"profile {name}: {field} must be {value!r}")
        req[field] = value
    genres = profile.get("genres", {})
    genre = genres.get(req.get("genre")) if genres else None
    if genres:
        check(genre is not None, f"profile {name}: genre must be one of {sorted(genres)}")
    parts = {
        "language": req.get("language", ""),
        "genre_style": (genre or {}).get("style", ""),
        "vocal_style": req.get("vocal_style") or (genre or {}).get("vocal", ""),
        "accompaniment_style": req.get("accompaniment_style") or (genre or {}).get("accompaniment", ""),
        "tempo_bpm": req.get("tempo_bpm", ""),
    }
    style = profile["style_template"].format(**parts)
    style = re.sub(r"(,\s*){2,}", ", ", style).strip(" ,")
    checks = set(profile.get("checks", []))
    if "abc_matches_header" in checks and abc:
        check(score.bpm == int(req["tempo_bpm"]), f"tempo_bpm {req['tempo_bpm']} != ABC Q: {score.bpm}")
        check(abc_header(abc, "M") == str(req["meter"]), f"meter {req['meter']} != ABC M: {abc_header(abc, 'M')}")
        check(normalize_key(abc_header(abc, "K")) == normalize_key(str(req["key"])),
              f"key {req['key']} != ABC K: {abc_header(abc, 'K')}")
    if "abc_sections_match_lyrics" in checks and abc:
        sung = [s for s in abc_sections(abc) if s not in INSTRUMENTAL_SECTIONS]
        words = [s for s in lyric_sections(req["lyrics"]) if s not in INSTRUMENTAL_SECTIONS]
        check(sung == words, f"ABC sections {sung} don't match lyric sections {words}")
    return style, name


def build_job(args):
    path = Path(args.request).expanduser().resolve()
    check(path.is_file(), f"request file not found: {path}")
    try:
        req = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RequestError(f"request is not valid JSON: {exc}") from exc
    check(isinstance(req, dict), "request must be a JSON object")
    for key in ("seed", "profile"):
        if getattr(args, key) is not None:
            req[key] = getattr(args, key)
    unknown = set(req) - FIELDS
    check(not unknown, f"unknown request fields: {sorted(unknown)}")

    check(isinstance(req.get("id"), str) and ID_RE.fullmatch(req["id"]), "id must be filename-safe (letters, digits, _ . -)")
    req["lyrics"] = read_text_field(req, "lyrics", path.parent)
    check(isinstance(req["lyrics"], str) and req["lyrics"].strip(), "lyrics (or lyrics_path) is required")
    check(lyric_sections(req["lyrics"]), "lyrics need section tags on their own lines, e.g. [Verse] / [Chorus]")
    plan = req.get("plan", "auto")
    check(plan in PLANS, f"plan must be one of {sorted(PLANS)}")
    seed = req.get("seed", 831001)
    check(type(seed) is int and 0 <= seed < 2**63, "seed must be a non-negative integer")
    formats = req.get("formats", ["flac"])
    check(isinstance(formats, list) and formats and set(formats) <= FORMATS, f"formats must be a list from {sorted(FORMATS)}")
    check(isinstance(req.get("stems", False), bool), "stems must be true or false")

    abc = read_text_field(req, "score_abc", path.parent)
    score = None
    if abc:
        check(plan != "off", "plan 'off' cannot take a score; use auto, full or melody")
        tools = load_abc_tools()
        try:
            score = tools.parse_abc(abc.replace("\r\n", "\n").rstrip("\n"))
        except tools.AbcError as exc:
            raise RequestError(f"score_abc is not valid native YuE2 ABC: {exc}") from exc
        abc = score.text
    req["score_abc"] = abc  # so profiles see a score given by path too
    syllables = read_syllables(req, path.parent)
    req["syllables"] = syllables  # so profiles see syllables given by path too
    syllable_check = check_syllables(syllables, score, req["lyrics"]) if syllables is not None else None
    style, profile = apply_profile(req, abc, score)

    if plan == "auto":
        plan = ("full" if score.voices["Vocal"].chords else "melody") if score else "full"
    check(not (plan == "melody" and score and score.voices["Vocal"].chords),
          "plan 'melody' needs a chord-free score (or use plan 'full')")

    return {
        "id": req["id"], "title": req.get("title"), "profile": profile,
        "style": style, "lyrics": req["lyrics"], "cot": plan, "seed": seed, "abc": abc,
        "stems": req.get("stems", False), "formats": formats, "syllable_check": syllable_check,
        "score_nominal_seconds": float(score.voices["Vocal"].time * 60 / score.bpm) if score else None,
        "request_file": str(path),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--request", required=True, help="request JSON file")
    p.add_argument("--out", required=True, help="parent folder; output goes to <out>/<id>/")
    p.add_argument("--seed", type=int)
    p.add_argument("--profile")
    p.add_argument("--dry-run", action="store_true", help="validate and print the engine job, no GPU")
    args = p.parse_args(argv)

    try:
        job = build_job(args)
        out = Path(args.out).expanduser().resolve() / job["id"]
        check(not (out.exists() and any(out.iterdir())), f"output folder is not empty: {out} (use a new id or --out)")
    except RequestError as exc:
        return emit({"status": "invalid", "error": str(exc)}, 2)
    if args.dry_run:
        return emit({"status": "valid", "output": str(out), "job": {k: v for k, v in job.items() if k != "lyrics"}}, 0)
    if not ENGINE_PY.is_file():
        return emit({"status": "failed", "error": f"engine venv missing at {ENGINE_PY}; run scripts/install_engine.sh"}, 3)

    out.mkdir(parents=True, exist_ok=True)
    job["out_dir"] = str(out)
    job["engine_home"] = str(ENGINE_HOME)
    (out / "job.json").write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    env = dict(os.environ, HF_HOME=str(ENGINE_HOME / "hf-home"), TORCH_HOME=str(ENGINE_HOME / "torch-home"),
               HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True")
    proc = subprocess.run([str(ENGINE_PY), str(WORKER), str(out / "job.json")], env=env)  # progress -> stderr

    report_file = out / "report.json"
    if proc.returncode != 0 or not report_file.is_file():
        failure = out / "failure.json"
        detail = json.loads(failure.read_text()) if failure.is_file() else {"reason": f"worker exit {proc.returncode}"}
        return emit({"status": "failed", "output": str(out), **detail}, 3)
    report = json.loads(report_file.read_text(encoding="utf-8"))
    return emit(report, 4 if report.get("truncated") else 0)


if __name__ == "__main__":
    sys.exit(main())
