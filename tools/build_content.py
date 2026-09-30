"""Build the client's content from content/: skill map, pieces (notation) and test media.

    tools/.venv/bin/python tools/build_content.py

Writes client/public/content/ (skillmap.json, index.json, pieces/<id>.json) and copies test
media into client/public/media/. Both are generated and gitignored.

The skill-map checks are the content loader's validation (arch §6.10): unique ids and sequence
numbers, prerequisites that exist and come earlier, constraints that parse, and each skill's
practice pieces. Every piece goes through song analysis (api/app/analysis.py, §6.8), which decides
its required and featured skills, map point and skill measures. A skill's `pieces` list is its
**practice pieces** (v0.25: one concept per Journey bubble, and the bubble's songs): the core
pieces written for it, at least 2, each in one skill's list only. Each must feature the skill and
need nothing beyond it and the skills before it on the map (its prerequisites, and theirs), so it
is Guided-ready as soon as the skill is Current. On the placeholder map these are warnings.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import yaml
from music21 import pitch

import notation as nt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
from app import analysis, fingering  # noqa: E402  (shared with the App API)

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
OUT = ROOT / "client" / "public" / "content"
MEDIA = ROOT / "client" / "public" / "media"
MEDIA_SRC = CONTENT / "media"      # the media skill's stems for library pieces (gitignored, arch §10.5)
SYNC_PROBE = ROOT / "feasibility" / "sync-probe" / "dist"
TRACKS = {"reading", "rhythm", "technique", "theory", "repertoire", "musicianship"}
PRESETS = ("100", "90", "75", "50")
KEYS_61 = (36, 96)          # C2-C7: a 61-key keyboard (arch §2.3); anything outside needs 88 keys


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
    add_book_refs(maps)
    return maps


BOOK_REFS = CONTENT / "private" / "book-refs.yaml"


def add_book_refs(maps):
    """The family's own method-book pages for each skill (arch §6.2; parent mode shows them), from
    content/private/book-refs.yaml, which is never committed: `source` (the books) and `refs`
    (skill id -> [{book, pages}]). Without the file, no skill has book pages."""
    if not BOOK_REFS.exists():
        return
    data = yaml.safe_load(BOOK_REFS.read_text()) or {}
    refs = data.get("refs") or {}
    for m in maps:
        if data.get("source"):
            m["source"] = data["source"]
        for s in m.get("skills", []):
            if s.get("id") in refs:
                s["bookRefs"] = refs[s["id"]]


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
    listed = {}
    for s in skills:
        sid = s.get("id")
        for p in s.get("prerequisites", []):
            if p not in by_id:
                errors.append(f"{sid}: prerequisite {p} does not exist")
            elif isinstance(s.get("sequence"), int) and by_id[p].get("sequence", 1e9) >= s["sequence"]:
                errors.append(f"{sid}: prerequisite {p} must have a lower sequence number")
        for p in s.get("pieces", []):
            if p not in piece_ids:
                errors.append(f"{sid}: piece {p} does not exist")
            elif p in listed:
                errors.append(f"{sid}: piece {p} is already a practice piece of {listed[p]}")
            else:
                listed[p] = sid
        try:
            analysis.Constraints(s)
        except (ValueError, TypeError) as e:
            errors.append(f"{sid}: constraints don't parse ({e})")
    skills.sort(key=lambda s: s.get("sequence", 0))
    return skills, errors, warnings


def ancestors(skills):
    """Each skill's prerequisites, and theirs, all the way back."""
    by_id = {s["id"]: s for s in skills}
    out: dict[str, set[str]] = {}

    def up(sid):
        if sid not in out:
            out[sid] = set()
            for p in by_id.get(sid, {}).get("prerequisites", []):
                out[sid] |= {p} | up(p)
        return out[sid]
    for s in skills:
        up(s["id"])
    return out


def coverage(skills, analyses, kinds):
    """Each skill's practice pieces (its `pieces` list, see the module docstring): at least 2 core
    pieces (§6.8, §6.10), each featuring the skill and needing only it and the skills before it.
    Errors on a real map, warnings on the placeholder map. Returns (errors, warnings, pieces
    featuring each skill, from the analysis)."""
    errors, warnings = [], []
    featuring = {s["id"]: [p for p, a in analyses.items() if s["id"] in a["featuredSkills"]] for s in skills}
    before = ancestors(skills)
    names = {s["id"] for s in skills}
    for s in skills:
        out = warnings if s.get("placeholder") else errors
        practice = [p for p in s.get("pieces", []) if p in analyses]
        core = [p for p in practice if kinds.get(p, "core") == "core"]
        if len(core) < 2:
            out.append(f"{s['id']}: {len(core)} core practice piece(s); the loader needs at least 2 (§6.10)")
        for p in practice:
            a = analyses[p]
            if a.get("beyondMap"):
                out.append(f"{s['id']}: practice piece {p} is beyond the map ({', '.join(a['beyondMap'])})")
            elif s["id"] not in a["featuredSkills"]:
                out.append(f"{s['id']}: practice piece {p} features {a['featuredSkills']}, not this skill")
            late = [r for r in a["requiredSkills"] if r in names and r != s["id"] and r not in before[s["id"]]]
            if late:
                out.append(f"{s['id']}: practice piece {p} needs {', '.join(late)}, which isn't before it on the map")
    return errors, warnings, featuring


def build_piece(pid, meta, media_root=None):
    """(notation dict, media dict or None, warnings)"""
    phrase_bars = int(meta.get("phraseBars", 2))
    if "abc" in meta:
        nota, warnings = full_notation(meta)
        if meta.get("play") == "melody":
            # a full score (a hymn's four parts): the child plays the top line; the media skill
            # keeps the other voices for the backing (arch §10.5)
            nt.melody_only(nota, phrase_bars)
        if meta.get("verses"):
            nt.limit_verses(nota, int(meta["verses"]), phrase_bars)
        if meta.get("letters"):
            # a pre-staff piece (Prep A Units 1 to 3): every note head carries its letter name, and
            # the analysis credits its notes to the pre-staff skills (analysis.py)
            nota["header"]["letters"] = True
        if meta.get("dynamics"):
            add_dynamics(nota, meta["dynamics"])
        # `_noMedia`: the media skill building the notation it makes the media for
        return nota, None if meta.get("_noMedia") else media_for(pid, nota, media_root), warnings
    if "syncProbe" in meta:
        return build_sync_probe_piece(pid, meta, phrase_bars)
    raise ContentError(f"{pid}: needs an `abc` block or a `syncProbe` source")


# how hard the app's piano plays each dynamic mark (a MIDI velocity; the player scales its level by it)
DYNAMIC_VELOCITY = {"pp": 30, "p": 45, "mp": 60, "mf": 75, "f": 100, "ff": 115}


def add_dynamics(nota, marks):
    """`dynamics: {1: f, 5: p}` in a piece's header (the ABC reader drops !f!): each mark from the
    start of that written bar, drawn under the music (arch §5 dynamics[]); every note from there
    to the next mark gets its velocity, so Listen plays it loud or soft."""
    starts = {m["number"]: m["start"] for m in nota["measures"]}
    out = []
    for bar, mark in marks.items():
        if int(bar) not in starts:
            raise ContentError(f"dynamics: there is no bar {bar}")
        if mark not in DYNAMIC_VELOCITY:
            raise ContentError(f"dynamics: {mark!r} is not one of {', '.join(DYNAMIC_VELOCITY)}")
        out.append({"beat": starts[int(bar)], "mark": mark})
    out.sort(key=lambda d: d["beat"])
    nota["dynamics"] = out
    for n in nota["notes"]:
        at = [d for d in out if d["beat"] <= n["start"] + 1e-6]
        if at:
            n["velocity"] = DYNAMIC_VELOCITY[at[-1]["mark"]]


def full_notation(meta):
    """The whole written score of an `abc:` piece, before `play: melody` or `verses:` cut it."""
    score = nt.parse_abc(meta["abc"])
    hand = "L" if meta.get("hands") == "L" else "R"
    return nt.build_notation(score, hand_for_single_staff=hand, phrase_bars=int(meta.get("phraseBars", 2)))


def media_for(pid, nota, media_root=None):
    """The piece's stems from the media skill (content/media/<pid>/media.json, arch §10.5, or
    <media_root>/<pid>/ for a batch under review), copied into the client; None when it has none.
    The stems were made for this notation: a piece whose playback length or tempo changed since is
    an error (re-run the media skill)."""
    src = (media_root or MEDIA_SRC) / pid
    if not (src / "media.json").exists():
        return None
    media = json.loads((src / "media.json").read_text())
    if abs(float(media["beats"]) - float(nota["length"])) > 1e-6 or abs(float(media["bpm"]) - float(nota["header"]["tempo"])) > 0.5:
        raise ContentError(f"{pid}: its media was made for {media['beats']} beats at {media['bpm']} a minute, the piece now "
                           f"has {float(nota['length'])} at {nota['header']['tempo']}; re-run the media skill (tools/media/media.py)")
    dest = MEDIA / pid
    dest.mkdir(parents=True, exist_ok=True)
    presets = {}
    for key, p in media["presets"].items():
        entry = {"ratio": p["ratio"]}
        for stem in ("vocals", "accompaniment"):
            if not p.get(stem):
                continue
            f = src / p[stem]
            if not (dest / f.name).exists() or (dest / f.name).stat().st_size != f.stat().st_size:
                shutil.copy2(f, dest / f.name)
            entry[stem] = {"url": f"media/{pid}/{f.name}", "bytes": f.stat().st_size}
        presets[key] = entry
    return {"engine": media["engine"], "take": media.get("take"), "padBeats": media["padBeats"], "bpm": media["bpm"],
            "presets": presets, "check": media.get("check")}


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


LESSONS = CONTENT / "lessons"
CARD_KINDS = {"explain", "show", "hear", "try", "check", "echo", "watch"}


def parse_notes(text, rests=False):
    """'C4 D4:2 [C4,E4,G4]' -> [{pitches, spelled, beats}]: a note or chord, and its beats (default 1).
    With `rests` (what the lesson plays, not what the child plays), `r` or `r:2` is a silence."""
    out = []
    for tok in str(text).split():
        m = re.fullmatch(r"(\[[^\]]+\]|[^:\s]+)(?::([\d.]+))?", tok)
        if not m:
            raise ValueError(f"can't read {tok!r}")
        if rests and m.group(1) == "r":
            out.append({"pitches": [], "spelled": [], "beats": float(m.group(2) or 1)})
            continue
        names = m.group(1).strip("[]").split(",")
        pitches = [analysis.midi(n) for n in names]
        spelled = []
        for n in names:
            nm = re.fullmatch(r"([A-Ga-g])([#♯b♭]*)(-?\d+)", n.strip())
            spelled.append({"step": nm.group(1).upper(), "alter": sum(1 if c in "#♯" else -1 for c in nm.group(2)),
                            "octave": int(nm.group(3))})
        if any(not 21 <= p <= 108 for p in pitches):
            raise ValueError(f"{tok} is off the piano")
        out.append({"pitches": pitches, "spelled": spelled, "beats": float(m.group(2) or 1)})
    return out


def check_question(q):
    """A Check question: find a key (`answer: C4`), or tap one of `choices` (`answer: "3"`), after
    optionally hearing something (`hear: C4 E4 G4`: an identify question, §7.8)."""
    if "choices" in q:
        choices = [str(x) for x in q["choices"]]
        if str(q["answer"]) not in choices:
            raise ValueError(f"answer {q['answer']!r} is not one of the choices")
        out = {"text": q["text"], "choices": choices, "answer": str(q["answer"])}
    else:
        out = {"text": q["text"], "answer": parse_notes(q["answer"])[0]}
    if q.get("hear"):
        out["hear"] = parse_notes(q["hear"], rests=True)
    return out


def build_lesson(path, skill_ids):
    """A concept lesson (arch §3, §6.9): YAML cards -> the JSON the lesson screen plays."""
    data = yaml.safe_load(path.read_text())
    sid = data.get("skill")
    if sid not in skill_ids:
        raise ContentError(f"{path.name}: skill {sid!r} is not in the skill map")
    cards = []
    for i, c in enumerate(data.get("cards") or []):
        kind = c.get("kind")
        where = f"{path.name} card {i + 1}"
        if kind not in CARD_KINDS:
            raise ContentError(f"{where}: unknown kind {kind!r}")
        card = {"kind": kind, "text": c.get("text", "")}
        try:
            if kind in ("show", "try"):
                card["notes"] = parse_notes(c["notes"])
                fingers = c.get("fingers")
                if fingers is not None and len(fingers) != len(card["notes"]):
                    raise ValueError("fingers and notes differ in length")
                card.update(fingers=fingers, hand=c.get("hand", "R"), clef=c.get("clef", "treble"))
            if kind == "hear":
                # `level` (0 to 1): how hard the app's piano plays it, for loud and soft (forte, piano)
                card.update(play=parse_notes(c["play"], rests=True), tempo=c.get("tempo", 90), level=c.get("level", 1))
                if c.get("contrast"):
                    card["contrast"] = {"text": c["contrast"].get("text", ""),
                                        "play": parse_notes(c["contrast"]["play"], rests=True),
                                        "level": c["contrast"].get("level", 1)}
            if kind == "check":
                card["questions"] = [check_question(q) for q in c["questions"]]
            if kind == "echo":
                card.update(play=parse_notes(c["play"]), tempo=c.get("tempo", 80))
                if not 2 <= len(card["play"]) <= 8:
                    raise ValueError("an echo phrase has 2 to 8 notes (arch §7.8)")
            if kind == "watch":
                card["video"] = c["video"]
        except (KeyError, ValueError) as e:
            raise ContentError(f"{where}: {e}")
        cards.append(card)
    kinds = [c["kind"] for c in cards]
    if "explain" not in kinds:
        raise ContentError(f"{path.name}: needs an explain card")
    return {"skill": sid, "title": data.get("title", sid), "cards": cards}


def content_version() -> str:
    """A short hash of every content source file: stored with each attempt (arch §5 ContentVersion)."""
    h = hashlib.sha256()
    for p in sorted([*CONTENT.glob("skillmap/*.yaml"), *CONTENT.glob("pieces/*.yaml"),
                     *CONTENT.glob("lessons/*.yaml"), *CONTENT.glob("private/*.yaml")]):   # not content/incoming/
        h.update(str(p.relative_to(CONTENT)).encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:12]


ANALYSIS_KEYS = ("barNotes", "requiredSkills", "featuredSkills", "mapPoint", "skillMeasures", "beyondMap")


def make_piece(pid, meta, skills, parsed, version, written_for=None, media_root=None):
    """One piece built, analysed and fingered, as the client and the API read it: (piece,
    index entry, warnings). Also used by the song import skill's checks (tools/import_song.py)."""
    nota, media, warnings = build_piece(pid, meta, media_root)
    warnings = list(warnings)
    lo, hi = nota["header"]["range"]
    keyboard = 61 if KEYS_61[0] <= lo and hi <= KEYS_61[1] else 88
    if keyboard == 88:
        warnings.append(f"range {pitch.Pitch(midi=lo).nameWithOctave}-{pitch.Pitch(midi=hi).nameWithOctave} "
                        "goes beyond C2-C7, so it needs an 88-key keyboard")
    an = analysis.analyze(nt.jsonable(nota), skills, parsed, written_for)
    # finger numbers for every note without one (§8.9), in a hand position: the one of the skill it
    # was written for, else of its newest featured skill, when that skill has one
    by_id = {s["id"]: s for s in skills}
    positions = [((by_id.get(k) or {}).get("constraints") or {}).get("position") for k in [written_for, *an["featuredSkills"][:1]]]
    fing = fingering.generate(nota, next((x for x in positions if x), None))
    warnings += fing["flagged"]
    piece = {"id": pid, "title": meta["title"], "composer": meta.get("composer"), "kind": meta.get("kind", "core"),
             # several arrangements of one song (arch §5 Song -> Arrangements): `song` ties them, `version` names each
             "song": meta.get("song", pid), "songTitle": meta.get("songTitle", meta["title"]), "version": meta.get("version"),
             "genre": meta.get("genre"), "level": meta.get("level"), "hands": meta.get("hands", "R"),
             # the skill it practises: the one it was written for, else the newest featured skill (§6.8)
             "skillId": None if an["beyondMap"] or not an["featuredSkills"] else
                        written_for if written_for in an["featuredSkills"] else an["featuredSkills"][0],
             "contentVersion": version, "keyboardSize": keyboard, "fingeringSource": fing["source"], **an,
             "notation": nt.jsonable(nota), "media": media}
    entry = ({k: piece[k] for k in ("id", "title", "composer", "kind", "genre", "level", "hands", "skillId", "keyboardSize",
                                    "song", "songTitle", "version")}
             | {"tempo": nota["header"]["tempo"], "timeSig": nota["header"]["timeSig"],
                "measures": len(nota["playbackOrder"]), "beats": float(nota["length"]), "phrases": len(nota["phrases"]),
                "hasMedia": media is not None} | an)
    return piece, entry, warnings


def main():
    version = content_version()
    pieces_meta = {p.stem: yaml.safe_load(p.read_text()) for p in sorted((CONTENT / "pieces").glob("*.yaml"))}
    maps = load_skill_maps()
    skills, errors, warnings = validate_skill_maps(maps, set(pieces_meta))
    if errors:
        print("Skill map errors:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "pieces").mkdir(parents=True)
    written_for = {p: s["id"] for s in skills for p in s.get("pieces", [])}
    parsed = {s["id"]: analysis.Constraints(s) for s in skills}
    index, analyses, kinds = [], {}, {}
    for pid, meta in pieces_meta.items():
        try:
            piece, entry, w = make_piece(pid, meta, skills, parsed, version, written_for.get(pid))
        except ContentError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        warnings += [f"{pid}: {x}" for x in w]
        nota, media, an = piece["notation"], piece["media"], {k: piece[k] for k in ANALYSIS_KEYS}
        analyses[pid], kinds[pid] = an, meta.get("kind", "core")
        (OUT / "pieces" / f"{pid}.json").write_text(json.dumps(piece, indent=1))
        index.append(entry)
        print(f"{pid}: {len(nota['notes'])} notes, {len(nota['playbackOrder'])} bars in playback order, "
              f"{len(nota['phrases'])} phrases" + (f", media {', '.join(media['presets'])}" if media else ""))

    # concept lessons: one for every skill unless the map says `conceptLesson: false` (§6.10)
    (OUT / "lessons").mkdir()
    lessons = {}
    for path in sorted(LESSONS.glob("*.yaml")):
        try:
            lesson = build_lesson(path, {s["id"] for s in skills})
        except ContentError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if lesson["skill"] in lessons:
            print(f"error: two lessons for {lesson['skill']}", file=sys.stderr)
            return 1
        lessons[lesson["skill"]] = lesson
        (OUT / "lessons" / f"{lesson['skill']}.json").write_text(json.dumps(lesson, indent=1))
    for s in skills:
        if s.get("conceptLesson", True) is not False and s["id"] not in lessons:
            msg = f"{s['id']}: no concept lesson in content/lessons/"
            if not s.get("placeholder"):
                print(f"error: {msg}", file=sys.stderr)
                return 1
            warnings.append(msg)

    cov_errors, cov_warnings, featuring = coverage(skills, analyses, kinds)
    warnings += cov_warnings
    if cov_errors:
        print("Coverage errors:\n  " + "\n  ".join(cov_errors), file=sys.stderr)
        return 1
    # `pieces` in the built map: each skill's practice pieces (its bubble's songs); `featuring`: every
    # piece the analysis says features it, which the engine also uses for review
    skillmap = {"contentVersion": version, "placeholder": any(m.get("placeholder") for m in maps),
                "maps": [{k: m[k] for k in ("map", "level", "file", "source") if k in m} for m in maps],
                "skills": [{**s, "pieces": s.get("pieces", []), "featuring": featuring[s["id"]], "lesson": s["id"] in lessons}
                           for s in skills]}
    (OUT / "skillmap.json").write_text(json.dumps(skillmap, indent=1))
    (OUT / "index.json").write_text(json.dumps({"contentVersion": version, "pieces": index}, indent=1))
    if warnings:
        print("Warnings:\n  " + "\n  ".join(warnings))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(skills)} skills, {len(index)} pieces, {len(lessons)} lessons, "
          f"content version {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
