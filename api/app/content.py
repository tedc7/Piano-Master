"""The skill map and piece index the lesson engine plans from (arch §6, §6.8).

tools/build_content.py writes skillmap.json, index.json and pieces/<id>.json; deploys copy them
into app/content/ (PIANO_CONTENT overrides the folder), so the server plans from the same content
version the client shows. Diagnostics and the drill generator read each piece's full notation. Each piece's required and featured skills, map point and skill
measures come from song analysis (analysis.py, run by the content build).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent / "content"


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
    kind: str = "core"
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
    folder: Path | None = None                 # where pieces/<id>.json are
    notations: dict[str, dict] = field(default_factory=dict)   # loaded (or given, in tests) full notation

    def notation(self, piece_id: str) -> dict | None:
        """A piece's §5 notation, from pieces/<id>.json; None when it isn't there."""
        if piece_id not in self.notations:
            f = self.folder / "pieces" / f"{piece_id}.json" if self.folder else None
            if f is None or piece_id not in self.pieces or not f.exists():
                return None
            self.notations[piece_id] = json.loads(f.read_text())["notation"]
        return self.notations[piece_id]

    def skill_dicts(self, ids) -> list[dict]:
        """Skill-map entries (id, sequence, constraints) for analysis and the drill generator."""
        return [{"id": s.id, "sequence": s.sequence, "constraints": s.constraints} for s in self.order if s.id in ids]

    @property
    def order(self) -> list[Skill]:
        return sorted(self.skills.values(), key=lambda s: s.sequence)

    def pieces_of(self, skill_id: str) -> list[Piece]:
        """The pieces that feature the skill (song analysis), core pieces first."""
        found = [p for p in self.pieces.values() if skill_id in p.featured and not p.beyond]
        return sorted(found, key=lambda p: (p.kind != "core", p.map_point or 0, p.id))

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
                kind=p.get("kind", "core"), phrases=int(p.get("phrases", 1)),
                beyond=list(p.get("beyondMap", [])), map_point=p.get("mapPoint"),
                skill_measures=dict(p.get("skillMeasures", {})),
                bar_notes={int(k): v for k, v in (p.get("barNotes") or {}).items()}, level=p.get("level") or "")
        return cls(version=index.get("contentVersion", skillmap.get("contentVersion", "")), skills=skills, pieces=pieces,
                   folder=folder)


_cache: tuple[float, Content] | None = None


def content_dir() -> Path:
    return Path(os.environ.get("PIANO_CONTENT", DEFAULT_DIR))


def load() -> Content | None:
    """The deployed content, reloaded when its files change; None if there is none."""
    global _cache
    d = content_dir()
    try:
        mtime = max((d / "skillmap.json").stat().st_mtime, (d / "index.json").stat().st_mtime)
    except OSError:
        return None
    if _cache is None or _cache[0] != mtime:
        c = Content.from_json(json.loads((d / "skillmap.json").read_text()), json.loads((d / "index.json").read_text()), d)
        _cache = (mtime, c)
    return _cache[1]
