"""Song progress (v0.50, arch §8.12): each student's record of each song, beside the skill states.
The table is made and filled by replaying every stored attempt in order, with each library song's
hands and phrases from the library's files, exactly as the API keeps it after each new attempt
(song_progress.update). Running it again rebuilds the same records."""
from __future__ import annotations

from pathlib import Path

from app import song_progress


def run(con, data: Path) -> None:
    con.execute(song_progress.SCHEMA)
    song_progress.rebuild(con, song_progress.songs_in_library(data))
