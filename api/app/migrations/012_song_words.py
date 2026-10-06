"""Each song's words in its index entry, for the song library's search (v0.35): the songs in the
library and the review area, and the library's index."""
from __future__ import annotations

import json
from pathlib import Path

from app.content import song_words


def run(con, data: Path) -> None:
    for r in con.execute("SELECT piece_id, entry FROM library").fetchall():
        f = data / "library" / r["piece_id"] / "piece.json"
        if f.exists() and (nota := json.loads(f.read_text()).get("notation")):
            entry = json.loads(r["entry"])
            entry["words"] = song_words(nota)
            con.execute("UPDATE library SET entry = ? WHERE piece_id = ?", (json.dumps(entry), r["piece_id"]))
    for r in con.execute("SELECT id, package_id, info FROM staged_items").fetchall():
        f = data / "staging" / r["package_id"] / r["id"] / "piece.json"
        info = json.loads(r["info"])
        if info.get("entry") and f.exists() and (nota := json.loads(f.read_text()).get("notation")):
            info["entry"]["words"] = song_words(nota)
            con.execute("UPDATE staged_items SET info = ? WHERE id = ?", (json.dumps(info), r["id"]))
    if (data / "library" / "index.json").exists():
        from app import library
        library.write_index(con)
