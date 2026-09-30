"""Shared paths, constants and piece loading for the media skill (arch §10.5).

A piece's media is made for its notation as the child sees it (the app's playback order, verses
unrolled). The backing can also use the full written score: a hymn played as melody only keeps
its alto, tenor and bass for the strings (`play: melody`).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import build_content as bc  # noqa: E402
import notation as nt  # noqa: E402

M = TOOLS / ".media"
FLUIDSYNTH = M / "fluidsynth" / "bin" / "fluidsynth"
RUBBERBAND = M / "rubberband" / "bin" / "rubberband"
FA_PYTHON = M / "fa" / "bin" / "python"
SOUNDFONT = M / "soundfonts" / "MuseScore_General.sf3"
WORK = M / "work"                           # YuE2 renders and alignment runs, per piece
YUE2_SCRIPTS = Path.home() / "engines/yue2/YuE/skills/yue2-music/scripts"
GENERATE = Path.home() / ".claude/skills/generate-music/scripts/generate_music.py"

PRESETS = {"100": 1.0, "90": 0.9, "75": 0.75, "50": 0.5}
SR = 48000
PAD_BEATS = 1.0             # an instrumental piece's lead-in: a note on beat 0 can start early

# the piece's `genre` -> the generate-music piano-master profile's genre (its style table) and the
# default FluidSynth backing style (arch §10.5 genre table). "yue2": keep YuE2's own backing.
GENRES = {
    "hymns": ("Hymns", "hymn-strings"),
    "holiday": ("Holiday", "pad"),
    "folk": ("Folk", "yue2"),
    "kids": ("Nursery and kids' songs", "kids"),
    "classical": ("Classical", "pad"),
    "pop": ("Movie/TV, Pop", "pad"),
    "lesson-pieces": ("Lesson pieces", "kids"),
}


@dataclass
class Piece:
    pid: str
    path: Path              # the piece file
    meta: dict
    nota: dict              # the notation the child plays (Fractions)
    full: dict              # the whole written score (all voices)
    media_dir: Path         # where its media.json and stems go

    @property
    def title(self) -> str:
        return self.meta["title"]

    @property
    def spec(self) -> dict:
        return self.meta.get("media") or {}

    @property
    def genre(self) -> tuple[str, str]:
        return GENRES.get(self.meta.get("genre"), ("Lesson pieces", "pad"))

    @property
    def bpm(self) -> float:
        return float(self.nota["header"]["tempo"])

    @property
    def has_words(self) -> bool:
        return bool(self.nota["lyrics"])

    @property
    def work(self) -> Path:
        return WORK / self.pid


def media_dir_for(path: Path) -> Path:
    """content/pieces/x.yaml -> content/media/x/; content/incoming/<batch>/x.yaml -> .../<batch>/media/x/"""
    path = path.resolve()
    if path.parent == (ROOT / "content" / "pieces").resolve():
        return ROOT / "content" / "media" / path.stem
    return path.parent / "media" / path.stem


def load(path: Path) -> Piece:
    meta = yaml.safe_load(path.read_text())
    if "abc" not in meta:
        raise bc.ContentError(f"{path.stem}: the media skill needs an `abc:` piece")
    nota, _, _ = bc.build_piece(path.stem, {**meta, "_noMedia": True})
    full, _ = bc.full_notation(meta)
    if meta.get("verses"):
        nt.limit_verses(full, int(meta["verses"]), int(meta.get("phraseBars", 2)))
    return Piece(path.stem, path, meta, nota, full, media_dir_for(path))


def pieces(args: list[str]) -> list[Piece]:
    """Piece files, or batch folders (every .yaml in them), or ids in content/pieces/."""
    out = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            out += [load(f) for f in sorted(p.glob("*.yaml"))]
        elif p.suffix == ".yaml":
            out.append(load(p))
        else:
            out.append(load(ROOT / "content" / "pieces" / f"{a}.yaml"))
    return out
