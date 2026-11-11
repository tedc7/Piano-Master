"""The later scorers (v0.50, arch §7.7): each skill state keeps the best stars from each scorer
beyond notes and timing (Loud and soft, ...). A column already there is left alone."""
from __future__ import annotations

from pathlib import Path


def run(con, data: Path) -> None:
    have = {r["name"] for r in con.execute("PRAGMA table_info(skill_states)")}
    if "best_scorer_stars" not in have:
        con.execute("ALTER TABLE skill_states ADD COLUMN best_scorer_stars TEXT NOT NULL DEFAULT '{}'")
