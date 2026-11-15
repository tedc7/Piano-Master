"""Song tools (v0.51, songtools.py): a small settings table, and song tools on for a server that
already works with a dev box (it has skill tokens), so it keeps them whatever its next deploy
says. A new server has none, so its song tools are off until a deploy from the dev box turns
them on. Safe to run again."""
from __future__ import annotations

from pathlib import Path


def run(con, data: Path) -> None:
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    if con.execute("SELECT 1 FROM skill_tokens LIMIT 1").fetchone():
        con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('song_tools', 'on')")
