"""Build the client's content from content/: skill map, pieces (notation) and test media.

    tools/.venv/bin/python tools/build_content.py

Writes client/public/content/ (skillmap.json, index.json, pieces/<id>.json) and copies test
media into client/public/media/. Both are generated and gitignored.

The skill-map checks are the first part of the content loader's validation (arch §6.10):
unique ids and sequence numbers, prerequisites that exist and come earlier. Pieces are checked
against the constraints of the skills that list them; for the placeholder map those are
warnings, since song analysis (M3) will replace the hand-assigned `pieces` lists.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import yaml
from music21 import pitch

import notation as nt

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
OUT = ROOT / "client" / "public" / "content"
MEDIA = ROOT / "client" / "public" / "media"
SYNC_PROBE = ROOT / "feasibility" / "sync-probe" / "dist"
TRACKS = {"reading", "rhythm", "technique", "theory", "repertoire", "musicianship"}
PRESETS = ("100", "90", "75", "50")


class ContentError(Exception):
    pass


def midi(name: str) -> int:
    return pitch.Pitch(name).midi


def load_skill_maps():
    maps = []
    for path in sorted((CONTENT / "skillmap").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        data["file"] = path.name
        maps.append(data)
    return maps


def validate_skill_maps(maps, piece_ids):
    """Returns (skills sorted by sequence, errors, warnings)."""
    errors, warnings, skills = [], [], []
    for m in maps:
        for s in m.get("skills", []):
            skills.append({**s, "map": m["map"], "level": m["level"], "placeholder": bool(m.get("placeholder"))})
    by_id, by_seq = {}, {}
    for s in skills:
        sid = s.get("id")
        if not sid:
            errors.append(f"skill without an id: {s.get('name')}")
            continue
        if sid in by_id:
            errors.append(f"duplicate skill id {sid}")
        by_id[sid] = s
        seq = s.get("sequence")
        if not isinstance(seq, int):
            errors.append(f"{sid}: sequence must be a whole number")
        elif seq in by_seq:
            errors.append(f"{sid}: sequence {seq} already used by {by_seq[seq]}")
        else:
            by_seq[seq] = sid
        if s["placeholder"] and not sid.startswith("placeholder."):
            errors.append(f"{sid}: placeholder skill ids must start with 'placeholder.'")
        if s.get("track") not in TRACKS:
            errors.append(f"{sid}: unknown track {s.get('track')!r}")
    for s in skills:
        sid = s.get("id")
        for p in s.get("prerequisites", []):
            if p not in by_id:
                errors.append(f"{sid}: prerequisite {p} does not exist")
            elif isinstance(s.get("sequence"), int) and by_id[p].get("sequence", 1e9) >= s["sequence"]:
                errors.append(f"{sid}: prerequisite {p} must have a lower sequence number")
        pieces = s.get("pieces", [])
        for p in pieces:
            if p not in piece_ids:
                errors.append(f"{sid}: piece {p} does not exist")
        if len(pieces) < 3:
            (warnings if s["placeholder"] else errors).append(f"{sid}: {len(pieces)} piece(s); the loader will need at least 3 (§6.10)")
    skills.sort(key=lambda s: s.get("sequence", 0))
    return skills, errors, warnings


def check_constraints(piece_id, nota, skill):
    """Notes outside a skill's constraints (the part of song analysis M1 can use)."""
    c, out = skill.get("constraints", {}), []
    hands = set(c.get("hands", ["R", "L"]))
    for hand in sorted({n["hand"] for n in nota["notes"]} - hands):
        out.append(f"uses the {hand} hand")
    for hand, (lo, hi) in (c.get("range") or {}).items():
        ps = [n["pitch"] for n in nota["notes"] if n["hand"] == hand]
        if ps and (min(ps) < midi(lo) or max(ps) > midi(hi)):
            out.append(f"{hand} hand range {pitch.Pitch(midi=min(ps)).nameWithOctave}-{pitch.Pitch(midi=max(ps)).nameWithOctave} is outside {lo}-{hi}")
    allowed = c.get("durations")
    if allowed:
        odd = sorted({float(n["duration"]) for n in nota["notes"]} - {float(d) for d in allowed})
        if odd:
            out.append(f"note lengths {odd} (beats) are not in {allowed}")
    if c.get("timeSigs") and nota["header"]["timeSig"] not in c["timeSigs"]:
        out.append(f"time signature {nota['header']['timeSig']} is not in {c['timeSigs']}")
    if c.get("keySigs") is not None and nota["header"]["keySig"] not in c["keySigs"]:
        out.append(f"key signature {nota['header']['keySig']} is not in {c['keySigs']}")
    return [f"{piece_id} vs {skill['id']}: {x}" for x in out]


def build_piece(pid, meta):
    """(notation dict, media dict or None, warnings)"""
    phrase_bars = int(meta.get("phraseBars", 2))
    if "abc" in meta:
        score = nt.parse_abc(meta["abc"])
        hand = "L" if meta.get("hands") == "L" else "R"
        nota, warnings = nt.build_notation(score, hand_for_single_staff=hand, phrase_bars=phrase_bars)
        return nota, None, warnings
    if "syncProbe" in meta:
        return build_sync_probe_piece(pid, meta, phrase_bars)
    raise ContentError(f"{pid}: needs an `abc` block or a `syncProbe` source")


def build_sync_probe_piece(pid, meta, phrase_bars):
    sp = meta["syncProbe"]
    manifest_path = SYNC_PROBE / "manifest.json"
    if not manifest_path.exists():
        raise ContentError(f"{pid}: {manifest_path} missing; build the sync probe first (feasibility/sync-probe/setup.sh)")
    manifest = json.loads(manifest_path.read_text())
    song = next((s for s in manifest["songs"] if s["id"] == sp["song"]), None)
    if song is None or sp["take"] not in song.get("takes", {}):
        raise ContentError(f"{pid}: take {sp['song']}/{sp['take']} not in the sync-probe build")
    take = song["takes"][sp["take"]]
    nota = json.loads((SYNC_PROBE / song["notation"]).read_text())
    for k in ("id", "title", "genre", "source", "chordSymbolsDerived"):
        nota.pop(k, None)
    nota["header"] = {k: v for k, v in nota["header"].items() if k not in ("key", "mode")}
    nota["header"]["tempo"] = take["bpm"]
    nt.melody_only(nota, phrase_bars)
    if meta.get("verses"):
        nt.limit_verses(nota, int(meta["verses"]), phrase_bars)
    dest = MEDIA / pid
    dest.mkdir(parents=True, exist_ok=True)
    presets = {}
    for key in PRESETS:
        st = take["stems"].get(key)
        if not st:
            continue
        entry = {"ratio": st["ratio"]}
        for stem in ("vocals", "accompaniment"):
            src = SYNC_PROBE / st[stem]["url"]
            name = f"{stem}_{key}{src.suffix}"
            if not (dest / name).exists() or (dest / name).stat().st_size != src.stat().st_size:
                shutil.copy2(src, dest / name)
            entry[stem] = {"url": f"media/{pid}/{name}", "bytes": src.stat().st_size}
        presets[key] = entry
    media = {"engine": "YuE2", "take": sp["take"], "padBeats": take["padBeats"], "bpm": take["bpm"],
             "presets": presets, "check": take.get("check")}
    return nota, media, []


def main():
    pieces_meta = {p.stem: yaml.safe_load(p.read_text()) for p in sorted((CONTENT / "pieces").glob("*.yaml"))}
    maps = load_skill_maps()
    skills, errors, warnings = validate_skill_maps(maps, set(pieces_meta))
    if errors:
        print("Skill map errors:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "pieces").mkdir(parents=True)
    skill_of = {p: s["id"] for s in skills for p in s.get("pieces", [])}
    index = []
    for pid, meta in pieces_meta.items():
        try:
            nota, media, w = build_piece(pid, meta)
        except ContentError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        warnings += [f"{pid}: {x}" for x in w]
        for s in skills:
            if pid in s.get("pieces", []):
                warnings += check_constraints(pid, nota, s)
        piece = {"id": pid, "title": meta["title"], "composer": meta.get("composer"), "kind": meta.get("kind", "core"),
                 "genre": meta.get("genre"), "level": meta.get("level"), "hands": meta.get("hands", "R"),
                 "skillId": skill_of.get(pid), "notation": nt.jsonable(nota), "media": media}
        (OUT / "pieces" / f"{pid}.json").write_text(json.dumps(piece, indent=1))
        index.append({k: piece[k] for k in ("id", "title", "composer", "kind", "genre", "level", "hands", "skillId")}
                     | {"tempo": nota["header"]["tempo"], "timeSig": nota["header"]["timeSig"],
                        "measures": len(nota["playbackOrder"]), "hasMedia": media is not None})
        print(f"{pid}: {len(nota['notes'])} notes, {len(nota['playbackOrder'])} bars in playback order, "
              f"{len(nota['phrases'])} phrases" + (f", media {', '.join(media['presets'])}" if media else ""))

    skillmap = {"placeholder": any(m.get("placeholder") for m in maps),
                "maps": [{k: m[k] for k in ("map", "level", "file")} for m in maps],
                "skills": [{k: v for k, v in s.items()} for s in skills]}
    (OUT / "skillmap.json").write_text(json.dumps(skillmap, indent=1))
    (OUT / "index.json").write_text(json.dumps({"pieces": index}, indent=1))
    if warnings:
        print("Warnings:\n  " + "\n  ".join(warnings))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(skills)} skills, {len(index)} pieces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
