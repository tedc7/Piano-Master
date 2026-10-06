"""The Holiday genre is now Christmas (v0.35): the songs in the library and the review area, their
files and index, and each child's genre rule (an allowed Holiday stays allowed as Christmas)."""
from __future__ import annotations

import json
from pathlib import Path

OLD, NEW = "holiday", "christmas"


def run(con, data: Path) -> None:
    for table, key in (("library", "piece_id"), ("staged_items", "id")):
        for r in con.execute(f"SELECT {key}, genre, {'entry' if table == 'library' else 'info'} AS j FROM {table}").fetchall():
            j = json.loads(r["j"]) if r["j"] else {}
            entry = j if table == "library" else j.get("entry") or {}
            if r["genre"] != OLD and entry.get("genre") != OLD:
                continue
            if entry.get("genre") == OLD:
                entry["genre"] = NEW
            col = "entry" if table == "library" else "info"
            con.execute(f"UPDATE {table} SET genre = ?, {col} = ? WHERE {key} = ?",
                        (NEW if r["genre"] == OLD else r["genre"], json.dumps(j), r[key]))
    con.execute("UPDATE genre_rules SET genre = ? WHERE genre = ? AND NOT EXISTS "
                "(SELECT 1 FROM genre_rules g WHERE g.student_id = genre_rules.student_id AND g.genre = ?)", (NEW, OLD, NEW))
    con.execute("DELETE FROM genre_rules WHERE genre = ?", (OLD,))
    for f in [*data.glob("library/*/piece.json"), *data.glob("staging/*/*/piece.json")]:
        p = json.loads(f.read_text())
        if p.get("genre") == OLD:
            p["genre"] = NEW
            f.write_text(json.dumps(p))
    if (data / "library" / "index.json").exists():
        from app import library
        library.write_index(con)
