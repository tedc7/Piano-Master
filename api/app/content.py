"""The skill map and the songs the lesson engine plans from (arch §6, §6.8).

The skill map deploys with the app: tools/build_content.py writes skillmap.json, and deploys copy
it into app/content/ (PIANO_CONTENT overrides the folder), so the server plans from the map the
client shows. Every song is in the library (v0.27): the songs the parent approved from the review
list (arch §10.7), whatever made them. The library module keeps their index in
<data>/library/index.json and each song in <data>/library/<id>/piece.json, and analyses each one
against the deployed map (analysis.py): its required and featured skills, map point and skill
measures. The content version is "<map>+<library>". Diagnostics and the drill generator read each
song's full notation. A skill's `pieces` are its practice songs (its Journey bubble's songs): the
curriculum, which every child may play.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent / "content"


def song_version(nota: dict) -> str:
    """A song's version: a hash of its notes, which every attempt records. Attempts on other
    versions of the notes can't be matched note by note (Diagnostics)."""
    return "lib-" + hashlib.sha256(json.dumps(nota, sort_keys=True).encode()).hexdigest()[:10]


@dataclass
class Skill:
    id: str
    name: str
    sequence: int
    track: str
    prerequisites: list[str]
    level: str = ""
    capabilities: list[str] = field(default_factory=list)
    has_lesson: bool = True            # every skill has a concept lesson unless the map says not
    pieces: list[str] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)     # as in the skill map (analysis.Constraints parses them)

    @property
    def needs_timing(self) -> bool:
        """Theory skills have no play-along part, so mastery needs only the accuracy rule (8.2)."""
        return self.track != "theory"


@dataclass
class Piece:
    id: str
    title: str
    skill_id: str | None
    required: list[str]
    featured: list[str]
    beats: float
    tempo: float
    hands: str = "R"
    phrases: int = 1
    beyond: list[str] = field(default_factory=list)     # needs what no skill covers yet (§6.8)
    map_point: int | None = None
    skill_measures: dict[str, list[int]] = field(default_factory=dict)
    bar_notes: dict[int, int] = field(default_factory=dict)     # notes to play per written bar
    level: str = ""

    def play_seconds(self, preset: str = "100") -> float:
        return self.beats * 60 / (self.tempo * int(preset) / 100)


@dataclass
class Content:
    version: str
    skills: dict[str, Skill]
    pieces: dict[str, Piece]
    folder: Path | None = None                 # the deployed content (skillmap.json)
    notations: dict[str, dict] = field(default_factory=dict)   # loaded (or given, in tests) full notation
    paths: dict[str, Path] = field(default_factory=dict)       # each song's piece.json in the library
    genres: dict[str, str] = field(default_factory=dict)       # piece id -> genre (for each child's rules)
    songs: dict[str, str] = field(default_factory=dict)        # piece id -> song (arrangements share one)
    versions: dict[str, str] = field(default_factory=dict)     # piece id -> its notes' version (song_version)

    def notation(self, piece_id: str) -> dict | None:
        """A song's §5 notation, from the library; None when it isn't there."""
        if piece_id not in self.notations:
            f = self.paths.get(piece_id)
            if f is None or piece_id not in self.pieces or not f.exists():
                return None
            nota = json.loads(f.read_text()).get("notation")
            if nota is None:
                return None
            self.notations[piece_id] = nota
        return self.notations[piece_id]

    @property
    def curriculum(self) -> set[str]:
        """The songs the map uses: every skill's practice songs. Every child may play them."""
        return {p for s in self.skills.values() for p in s.pieces}

    def practice_of(self, piece_id: str) -> str | None:
        """The skill a song is a practice song of (the one it was written for), if any."""
        return next((s.id for s in self.order if piece_id in s.pieces), None)

    def skill_dicts(self, ids) -> list[dict]:
        """Skill-map entries (id, sequence, constraints) for analysis and the drill generator."""
        return [{"id": s.id, "sequence": s.sequence, "constraints": s.constraints} for s in self.order if s.id in ids]

    @property
    def order(self) -> list[Skill]:
        return sorted(self.skills.values(), key=lambda s: s.sequence)

    def only(self, keep) -> "Content":
        """The same content with only the pieces keep(piece id) allows (a child's rules)."""
        return Content(version=self.version, skills=self.skills, pieces={k: p for k, p in self.pieces.items() if keep(k)},
                       folder=self.folder, notations=self.notations, paths=self.paths, genres=self.genres, songs=self.songs,
                       versions=self.versions)

    def pieces_of(self, skill_id: str) -> list[Piece]:
        """The songs that feature the skill (song analysis), its practice songs first."""
        s = self.skills.get(skill_id)
        practice = set(s.pieces) if s else set()
        found = [p for p in self.pieces.values() if skill_id in p.featured and not p.beyond]
        return sorted(found, key=lambda p: (p.id not in practice, p.map_point or 0, p.id))

    @classmethod
    def from_json(cls, skillmap: dict, index: dict, folder: Path | None = None) -> "Content":
        skills = {}
        for s in skillmap["skills"]:
            skills[s["id"]] = Skill(
                id=s["id"], name=s["name"], sequence=int(s["sequence"]), track=s.get("track", "reading"),
                prerequisites=list(s.get("prerequisites", [])), level=s.get("level", ""),
                capabilities=list(s.get("requiredCapabilities", [])), has_lesson=s.get("conceptLesson", True) is not False,
                pieces=list(s.get("pieces", [])), constraints=dict(s.get("constraints") or {}))
        pieces = {}
        for p in index["pieces"]:
            sid = p.get("skillId")
            num, den = (int(x) for x in p.get("timeSig", "4/4").split("/"))
            beats = p.get("beats") or p.get("measures", 8) * num * 4 / den
            pieces[p["id"]] = Piece(
                id=p["id"], title=p["title"], skill_id=sid,
                required=list(p.get("requiredSkills", [sid] if sid else [])),
                featured=list(p.get("featuredSkills", [sid] if sid else [])),
                beats=float(beats), tempo=float(p.get("tempo", 100)), hands=p.get("hands", "R"),
                phrases=int(p.get("phrases", 1)),
                beyond=list(p.get("beyondMap", [])), map_point=p.get("mapPoint"),
                skill_measures=dict(p.get("skillMeasures", {})),
                bar_notes={int(k): v for k, v in (p.get("barNotes") or {}).items()}, level=p.get("level") or "")
        return cls(version=index.get("contentVersion", skillmap.get("contentVersion", "")), skills=skills, pieces=pieces,
                   folder=folder, genres={p["id"]: p.get("genre") or "" for p in index["pieces"]},
                   songs={p["id"]: p.get("song") or p["id"] for p in index["pieces"]},
                   versions={p["id"]: p["contentVersion"] for p in index["pieces"] if p.get("contentVersion")})


_cache: tuple[tuple, Content] | None = None


def content_dir() -> Path:
    return Path(os.environ.get("PIANO_CONTENT", DEFAULT_DIR))


def library_index() -> Path:
    from .db import data_dir
    return data_dir() / "library" / "index.json"


def deployed_version() -> str | None:
    """The deployed skill map's content version."""
    try:
        return json.loads((content_dir() / "skillmap.json").read_text()).get("contentVersion")
    except OSError:
        return None


def load() -> Content | None:
    """The deployed skill map and the library's songs, reloaded when either changes; None if no
    skill map is deployed."""
    global _cache
    d, lib = content_dir(), library_index()
    try:
        key = (str(d), str(lib), (d / "skillmap.json").stat().st_mtime, lib.stat().st_mtime if lib.exists() else 0.0)
    except OSError:
        return None
    if _cache is None or _cache[0] != key:
        skillmap = json.loads((d / "skillmap.json").read_text())
        extra = json.loads(lib.read_text()) if lib.exists() else {"version": "", "pieces": []}
        index = {"contentVersion": f"{skillmap.get('contentVersion', '')}+{extra.get('version', '')}", "pieces": extra["pieces"]}
        c = Content.from_json(skillmap, index, d)
        c.paths = {p["id"]: lib.parent / p["id"] / "piece.json" for p in extra["pieces"]}
        _cache = (key, c)
    return _cache[1]
