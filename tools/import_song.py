"""The song import skill's tools (arch §10.4), on the dev box. The skill's instructions are in
.claude/skills/import-song/SKILL.md; this script does the deterministic parts.

    tools/.venv/bin/python tools/import_song.py convert SOURCE --id ID --batch NAME   # a draft piece from MusicXML/kern/MIDI/ABC
    tools/.venv/bin/python tools/import_song.py check PATH...                         # files or batch folders
    tools/.venv/bin/python tools/import_song.py compare PIECE.yaml REFERENCE [--line melody|R|L|all] [--part N] [--transpose N]
    tools/.venv/bin/python tools/import_song.py report content/incoming/NAME          # REVIEW.md for the parent
    tools/.venv/bin/python tools/import_song.py promote content/incoming/NAME ID...   # after the parent approves

Batches live in content/incoming/<name>/, which the content build and deploys ignore. `check`
runs the content build's own code on each piece (notation, analysis against the current skill
map, finger numbers, keyboard range) and adds the import checks: bar lengths, source and license
fields, duplicates by melody fingerprint (§10.8) against the library and the batch, and the
deleted list (content/deleted.yaml). Until the Skill API and staging exist (M7), approved pieces
are promoted into content/pieces/ and go live with the next deploy.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

import build_content as bc
import notation as nt
from app import analysis, fingerprint  # noqa: E402  (build_content put api/ on the path)

ROOT = bc.ROOT
CONTENT = bc.CONTENT
INCOMING = CONTENT / "incoming"
DELETED = CONTENT / "deleted.yaml"
XML2ABC = ROOT / "tools" / ".vendor" / "xml2abc_177" / "xml2abc.py"
# the edition's license (§10.2): these, optionally with a version ("CC BY-SA 3.0"), or "retyped
# from …" when the notes were retyped from a public-domain composition and only checked against
# the edition. Anything else (non-commercial, no-derivatives, unknown) is refused.
EDITION = re.compile(r"^(public-domain|CC0|CC BY-SA|CC BY|parent-supplied|retyped)(?![-\w])")
FIELDS = ("title", "composer", "kind", "genre", "level", "hands")


def rel(p: Path) -> str:
    """A path for people: relative to the repository when it is inside it."""
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


# ------------------------------------------------------------------------------ convert

def to_abc(src: Path) -> str:
    """ABC text for a source file: MusicXML through xml2abc; kern, MIDI and MEI through music21
    to MusicXML first (MIDI is quantized and has no spelling or voices: low confidence)."""
    ext = src.suffix.lower()
    if ext == ".abc":
        return src.read_text()
    with tempfile.TemporaryDirectory() as tmp:
        xml = src
        if ext not in (".xml", ".musicxml", ".mxl"):
            from music21 import converter
            score = converter.parse(str(src))
            xml = Path(tmp) / (src.stem + ".musicxml")
            score.write("musicxml", fp=str(xml))
        subprocess.run([sys.executable, str(XML2ABC), "-m", "0", "-b", "4", "--noped", "-o", tmp, str(xml)],
                       check=True, capture_output=True, text=True)
        out = next(Path(tmp).glob("*.abc"))
        return out.read_text()


def convert(args) -> int:
    src = Path(args.source)
    abc = to_abc(src)
    abc = re.sub(r"(?m)^T:.*$", f"T:{args.title or args.id}", abc, count=1)
    staves = len(set(re.findall(r"(?m)^V:(\S+)[ \t]+\S", abc)))     # voice definitions, not the bare V: switches
    hands = "RL" if staves >= 2 else "R"
    batch = INCOMING / args.batch
    batch.mkdir(parents=True, exist_ok=True)
    out = batch / f"{args.id}.yaml"
    if out.exists() and not args.force:
        print(f"{out} exists (--force to replace)", file=sys.stderr)
        return 2
    low = " MIDI has no spelling, voices or ties: check every bar against the score." if src.suffix.lower() in (".mid", ".midi") else ""
    meta = {
        "title": args.title or "TODO", "composer": args.composer or "TODO", "kind": "library", "genre": args.genre or "TODO",
        "level": "TODO", "hands": hands, "phraseBars": 4,
        "source": {"site": "TODO", "url": "TODO", "file": src.name},
        "license": {"composition": "public-domain", "edition": "TODO"},
    }
    head = (f"# Draft converted from {src.name} by tools/import_song.py convert.{low}\n"
            "# Fill in the TODOs, arrange it to its level (.claude/skills/import-song/references/arranging.md),\n"
            "# then run `check` and `compare` against the source.\n")
    body = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    out.write_text(head + body + "abc: |\n" + "".join(f"  {line}\n" for line in abc.strip().splitlines()))
    print(f"wrote {rel(out)} ({hands}, {len(abc.splitlines())} ABC lines)")
    return 0


# ------------------------------------------------------------------------------ check

def skill_map():
    maps = bc.load_skill_maps()
    skills, errors, _ = bc.validate_skill_maps(maps, {p.stem for p in (CONTENT / "pieces").glob("*.yaml")})
    if errors:
        raise SystemExit("skill map errors:\n  " + "\n  ".join(errors))
    return skills, {s["id"]: analysis.Constraints(s) for s in skills}


def bar_problems(nota: dict) -> list[str]:
    """Bars whose length isn't the time signature's (a pickup and a short last bar are allowed),
    and notes running past their bar line without a tie."""
    out = []
    ms = nota["measures"]
    ts = nota["header"]["timeSig"]
    for i, m in enumerate(ms):
        ts = m.get("timeSig", ts)
        num, den = (int(x) for x in ts.split("/"))
        want = num * 4 / den
        if abs(m["duration"] - want) > 1e-6 and not (i == 0 and nota["header"]["pickupBeats"]) and i != len(ms) - 1:
            out.append(f"bar {m['number']} lasts {m['duration']:g} beats, {ts} needs {want:g}")
    for n in nota["notes"]:
        m = next((x for x in ms if x["start"] - 1e-6 <= n["start"] < x["start"] + x["duration"] - 1e-6), None)
        if m and n["start"] + n["duration"] > m["start"] + m["duration"] + 1e-6 and not n.get("tieToNext"):
            out.append(f"bar {m['number']}: a note runs past the bar line")
    return out


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def library_prints() -> dict[str, tuple[str, set[str]]]:
    """Fingerprints of every piece in the library: {id: (song key, fingerprint)}."""
    out = {}
    for path in sorted((CONTENT / "pieces").glob("*.yaml")):
        meta = yaml.safe_load(path.read_text())
        built = bc.OUT / "pieces" / f"{path.stem}.json"
        try:
            nota = json.loads(built.read_text())["notation"] if built.exists() else nt.jsonable(bc.build_piece(path.stem, meta)[0])
        except Exception:        # a piece the build can't read is the build's problem, not the import's
            continue
        out[path.stem] = (meta.get("song", path.stem), fingerprint.fingerprint(nota))
    return out


def gather(paths: list[str]) -> list[Path]:
    files = []
    for p in (Path(x).resolve() for x in paths):
        files += sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    return files


def check_files(files: list[Path]) -> list[dict]:
    skills, parsed = skill_map()
    deleted = yaml.safe_load(DELETED.read_text()) if DELETED.exists() else []
    lib = library_prints()
    results, prints = [], {}
    for f in files:
        pid = f.stem
        r = {"id": pid, "file": str(rel(f)), "errors": [], "warnings": [], "summary": {}}
        results.append(r)
        try:
            meta = yaml.safe_load(f.read_text())
        except yaml.YAMLError as e:
            r["errors"].append(f"not valid YAML: {e}")
            continue
        for k in FIELDS:
            if not meta.get(k) or str(meta.get(k)).startswith("TODO"):
                r["errors"].append(f"`{k}` is missing")
        if meta.get("kind", "library") == "library":
            src, lic = meta.get("source") or {}, meta.get("license") or {}
            if not src.get("url") or "TODO" in str(src):
                r["errors"].append("`source` needs the site and URL it came from (§10.4)")
            ed = str(lic.get("edition", ""))
            if lic.get("composition") not in ("public-domain", "parent-supplied"):
                r["errors"].append("`license.composition` must be public-domain or parent-supplied (§10.2)")
            if not EDITION.match(ed):
                r["errors"].append(f"`license.edition` {ed or '(missing)'!r} is not an accepted license "
                                   "(public-domain, CC0, CC BY, CC BY-SA, parent-supplied, or 'retyped from …')")
        for d in deleted or []:
            if norm(d.get("title")) == norm(meta.get("title")) and norm(d.get("composer")) == norm(meta.get("composer")):
                r["errors"].append(f"on the deleted list ({d.get('reason') or 'no reason given'}): never add it again")
        if pid in lib:
            r["warnings"].append("a piece with this id is already in the library: promoting it would replace it")
        try:
            piece, entry, w = bc.make_piece(pid, meta, skills, parsed, "check")
        except Exception as e:           # a build error is the most useful thing to report
            r["errors"].append(f"does not build: {e}")
            continue
        r["warnings"] += w
        nota = piece["notation"]
        r["errors"] += bar_problems(nota)
        fp = fingerprint.fingerprint(nota)
        prints[pid] = (meta.get("song", pid), fp)
        for other, (song, ofp) in list(lib.items()) + [(k, v) for k, v in prints.items() if k != pid]:
            if other == pid or song == meta.get("song", pid):
                continue
            v = fingerprint.verdict(fingerprint.similarity(fp, ofp))
            if v:
                (r["errors"] if v == "same song" and other in lib else r["warnings"]).append(f"{v} as {other}")
        lo, hi = nota["header"]["range"]
        r["summary"] = {
            "title": meta.get("title"), "composer": meta.get("composer"), "level": meta.get("level"), "hands": entry["hands"],
            "bars": len(nota["measures"]), "notes": len(nota["notes"]), "tempo": nota["header"]["tempo"],
            "timeSig": nota["header"]["timeSig"], "range": f"{analysis.name(lo)}-{analysis.name(hi)}",
            "keyboardSize": entry["keyboardSize"], "mapPoint": entry["mapPoint"], "featured": entry["featuredSkills"],
            "beyondMap": entry["beyondMap"], "fingering": piece["fingeringSource"], "source": meta.get("source"),
            "license": meta.get("license"), "song": meta.get("song"), "version": meta.get("version"),
            "graces": len(nota.get("graces") or []), "tuplets": sum(1 for n in nota["notes"] if n.get("tuplet")),
        }
    return results


def check(args) -> int:
    results = check_files(gather(args.paths))
    if args.json:
        print(json.dumps(results, indent=1, ensure_ascii=False))
    else:
        for r in results:
            s = r["summary"]
            state = "ERROR" if r["errors"] else "warn " if r["warnings"] else "ok   "
            line = f"{state} {r['id']}"
            if s:
                where = f"beyond the map ({'; '.join(s['beyondMap'])})" if s["beyondMap"] else f"map point {s['mapPoint']}"
                line += f": {s['bars']} bars, {s['notes']} notes, {s['range']}, {s['keyboardSize']} keys, {where}"
            print(line)
            for e in r["errors"]:
                print(f"    error: {e}")
            for w in r["warnings"]:
                print(f"    warning: {w}")
        n_err = sum(1 for r in results if r["errors"])
        print(f"\n{len(results)} piece(s), {n_err} with errors")
    return 1 if any(r["errors"] for r in results) else 0


# ------------------------------------------------------------------------------ compare

def piece_line(nota: dict, which: str) -> list[tuple[int, int]]:
    """(pitch, written bar) in playback order: the melody, one hand, or every note (chords low to high)."""
    if which == "melody":
        ps = fingerprint.melody(nota)
        return [(p, 0) for p in ps]
    ms = nota["measures"]
    notes = [n for n in nota["notes"] if (which == "all" or n["hand"] == which)]
    by_m: dict[int, list[dict]] = {}
    for n in notes:
        i = next((k for k, m in enumerate(ms) if m["start"] - 1e-6 <= n["start"] < m["start"] + m["duration"] - 1e-6), None)
        if i is not None:
            by_m.setdefault(i, []).append(n)
    out, held = [], set()
    for p in nota["playbackOrder"]:
        for n in sorted(by_m.get(p["measure"], []), key=lambda n: (n["start"], n["pitch"])):
            key = (n["pitch"], n["staff"], n["voice"])
            if key in held:                       # held on through a tie: not a new note
                if not n.get("tieToNext"):
                    held.discard(key)
                continue
            if n.get("tieToNext"):
                held.add(key)
            out.append((int(n["pitch"]), ms[p["measure"]]["number"]))
    return out


def reference_line(path: Path, which: str, part: int | None) -> list[int]:
    from music21 import chord, converter, note
    s = converter.parse(str(path))
    try:
        s = s.expandRepeats()
    except Exception:
        pass                              # no repeats, or ones music21 can't expand: compare as written
    parts = list(s.parts) or [s]
    if part is not None:
        chosen = [parts[part]]
    elif which == "L" and len(parts) > 1:
        chosen = [parts[1]]
    elif which in ("R", "melody"):
        chosen = [parts[0]]
    else:
        chosen = parts
    events: dict[float, list[int]] = {}
    for p in chosen:
        for el in p.flatten().notes:
            if el.tie is not None and el.tie.type in ("stop", "continue"):
                continue
            ps = [x.pitch.midi for x in (el.notes if isinstance(el, chord.Chord) else [el])] if not isinstance(el, note.Unpitched) else []
            events.setdefault(round(float(el.getOffsetInHierarchy(s)), 4), []).extend(ps)
    out = []
    for t in sorted(events):
        ps = sorted(events[t])
        out += [ps[-1]] if which == "melody" else ps
    return out


def compare(args) -> int:
    f = Path(args.piece)
    meta = yaml.safe_load(f.read_text())
    nota = nt.jsonable(bc.build_piece(f.stem, meta)[0])
    mine = piece_line(nota, args.line)
    ref = [p + args.transpose for p in reference_line(Path(args.reference), args.line, args.part)]
    a = [p for p, _ in mine]
    sm = difflib.SequenceMatcher(a=a, b=ref, autojunk=False)
    same = sum(bl.size for bl in sm.get_matching_blocks())
    print(f"{f.stem} ({args.line}): {len(a)} notes; reference {Path(args.reference).name}: {len(ref)} notes")
    print(f"{same} of the piece's {len(a)} notes line up with the reference ({same / max(1, len(a)):.0%})")
    shown = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        bar = mine[i1][1] if i1 < len(mine) else mine[-1][1] if mine else 0
        where = f"bar {bar}" if bar else f"note {i1 + 1}"
        mn = " ".join(analysis.name(p) for p in a[i1:i2][:8]) or "-"
        rn = " ".join(analysis.name(p) for p in ref[j1:j2][:8]) or "-"
        print(f"  {where}: piece {mn}  reference {rn}  ({op})")
        shown += 1
        if shown >= args.limit:
            print("  …")
            break
    return 0 if same / max(1, len(a)) >= args.pass_at else 1


# ------------------------------------------------------------------------------ report and promote

def report(args) -> int:
    batch = Path(args.batch)
    results = check_files(gather([str(batch)]))
    lines = [f"# Review: {batch.name}", "",
             "For the parent: each piece below was checked by `tools/import_song.py check`. Say which to add;",
             "only those are promoted into the library. Nothing in this folder reaches a child.", "",
             "| Piece | Composer | Level | Hands | Bars | Range | Where it sits | Source | License | Problems |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["summary"] or {}
        where = ("beyond the map: " + "; ".join(s.get("beyondMap") or [])) if s.get("beyondMap") else f"map point {s.get('mapPoint')}"
        src = (s.get("source") or {}).get("site", "")
        lic = (s.get("license") or {}).get("edition", "")
        probs = "; ".join(r["errors"] + r["warnings"]) or "none"
        lines.append(f"| {s.get('title', r['id'])} (`{r['id']}`) | {s.get('composer', '')} | {s.get('level', '')} | {s.get('hands', '')} | "
                     f"{s.get('bars', '')} | {s.get('range', '')} ({s.get('keyboardSize', '')} keys) | {where} | {src} | {lic} | {probs} |")
    out = batch / "REVIEW.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {rel(out)}: {len(results)} piece(s), {sum(1 for r in results if r['errors'])} with errors")
    return 0


def promote(args) -> int:
    batch = Path(args.batch)
    files = sorted(batch.glob("*.yaml")) if args.all else [batch / f"{i}.yaml" for i in args.ids]
    missing = [f for f in files if not f.exists()]
    if missing:
        print("not in the batch: " + ", ".join(f.stem for f in missing), file=sys.stderr)
        return 2
    results = check_files(files)
    bad = [r for r in results if r["errors"]]
    if bad:
        for r in bad:
            print(f"{r['id']}: " + "; ".join(r["errors"]), file=sys.stderr)
        print("fix these first: nothing was promoted", file=sys.stderr)
        return 1
    for f in files:
        dest = CONTENT / "pieces" / f.name
        if dest.exists() and not args.replace:
            print(f"{rel(dest)} exists (--replace to overwrite)", file=sys.stderr)
            return 2
    for f in files:
        shutil.move(str(f), CONTENT / "pieces" / f.name)
        print(f"promoted {f.stem}")
    print("next: tools/.venv/bin/python tools/build_content.py, then tools/deploy.sh")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="a draft piece YAML from MusicXML, kern, MIDI, MEI or ABC")
    c.add_argument("source")
    c.add_argument("--id", required=True)
    c.add_argument("--batch", required=True, help="content/incoming/<batch>/")
    c.add_argument("--title")
    c.add_argument("--composer")
    c.add_argument("--genre")
    c.add_argument("--force", action="store_true")
    k = sub.add_parser("check", help="check pieces or batch folders")
    k.add_argument("paths", nargs="+")
    k.add_argument("--json", action="store_true")
    m = sub.add_parser("compare", help="compare a piece's notes with a reference file")
    m.add_argument("piece")
    m.add_argument("reference")
    m.add_argument("--line", choices=["melody", "R", "L", "all"], default="melody")
    m.add_argument("--part", type=int, help="the reference's part to compare (0 = the first)")
    m.add_argument("--transpose", type=int, default=0, help="semitones to move the reference by")
    m.add_argument("--limit", type=int, default=15, help="differences to list")
    m.add_argument("--pass-at", type=float, default=0.95, help="exit 0 when at least this share lines up")
    r = sub.add_parser("report", help="write REVIEW.md for a batch")
    r.add_argument("batch")
    p = sub.add_parser("promote", help="move approved pieces into content/pieces/")
    p.add_argument("batch")
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--replace", action="store_true")
    args = ap.parse_args(argv)
    return {"convert": convert, "check": check, "compare": compare, "report": report, "promote": promote}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
