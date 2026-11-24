"""Catching up (v0.56, arch §8.1): each day's session records whether it was planned while the
student was catching up (new skills waiting until the skills behind are mastered), for the note
on Today's Practice and for the New slot's continuation. A column already there is left alone."""
from __future__ import annotations

from pathlib import Path


def run(con, data: Path) -> None:
    have = {r["name"] for r in con.execute("PRAGMA table_info(sessions)")}
    if "catch_up" not in have:
        con.execute("ALTER TABLE sessions ADD COLUMN catch_up INTEGER NOT NULL DEFAULT 0")
