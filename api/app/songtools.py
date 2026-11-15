"""Song tools: whether this piano server makes songs (arch §10.9, §11.7; v0.51).

A server with song tools works with a dev box: the Claude skills submit songs through the Skill
API, and the parent's Needs improvement and "send back" notes go to them. Another family's install
has no dev box. Its songs come only from the app's own releases (the curriculum, and song packs),
which its parent brings into the Review list (library.py, "Songs from the app"). There, everything
that would wait for a dev box is hidden, and the Skill API refuses every call.

Song tools are on when:
- the deploy says so: the dev box's server.env has PIANO_SONG_TOOLS=on, and tools/deploy.sh puts a
  `song-tools` marker into the content it bundles with the API; or
- the server already worked with a dev box before v0.51: migration 017 turns the `song_tools`
  setting on when it finds skill tokens.

A guard, not security: the family owns their server.
"""
from __future__ import annotations

import sqlite3

from . import content, db

MARKER = "song-tools"


def on(con: sqlite3.Connection | None = None) -> bool:
    if (content.content_dir() / MARKER).exists():
        return True
    own = con is None
    con = con or db.connect()
    try:
        r = con.execute("SELECT value FROM settings WHERE key = 'song_tools'").fetchone()
        return bool(r) and r["value"] == "on"
    except sqlite3.OperationalError:          # not migrated yet
        return False
    finally:
        if own:
            con.close()
