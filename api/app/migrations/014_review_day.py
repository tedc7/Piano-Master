"""A Review item played again the same day is one review, judged on the day's best play (v0.37,
arch §8.3): each skill state keeps the day of its last explicit review, that day's best stars, and
the review ladder as it stood before it. Columns already there are left alone, so the migration can
run again."""
from __future__ import annotations

from pathlib import Path

COLUMNS = {
    "review_day": "TEXT",       # the day of the last explicit review
    "review_best": "REAL",      # that day's best accuracy stars on it
    "review_base": "TEXT",      # JSON: the ladder before that day's review
}


def run(con, data: Path) -> None:
    have = {r["name"] for r in con.execute("PRAGMA table_info(skill_states)")}
    for name, kind in COLUMNS.items():
        if name not in have:
            con.execute(f"ALTER TABLE skill_states ADD COLUMN {name} {kind}")
