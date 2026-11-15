"""Chord symbols drawn as grace notes (v0.51). Until v0.51 the notation converter (tools/notation.py)
read every chord symbol ("Am" above a note), which music21 holds as a chord of no length, as grace
notes too, so each song with chord symbols drew its chords' notes as grace-note clusters before
the melody (26 approved songs, Nov 15, 2026). The converter is fixed; this takes those grace notes
out of the songs already in the library and the review area. Only from a song whose every grace
note sits on one of its chord symbols' beats: a song with a grace note anywhere else is left as it
is. Each changed song's version (a hash of its notation) is worked out again, in its piece and its
index entry. Safe to run again: a song with no grace notes is left alone."""
from __future__ import annotations

import json
from pathlib import Path


def cleaned(piece: dict) -> bool:
    nota = piece.get("notation") or {}
    graces = nota.get("graces") or []
    beats = {float(c["beat"]) for c in nota.get("chordSymbols") or [] if "beat" in c}
    if not graces or not beats or any(float(g["start"]) not in beats for g in graces):
        return False
    nota["graces"] = []
    return True


def run(con, data: Path) -> None:
    from app.content import song_version
    versions = {}
    for f in sorted(data.glob("library/*/piece.json")) + sorted(data.glob("staging/*/*/piece.json")):
        piece = json.loads(f.read_text())
        if not cleaned(piece):
            continue
        if piece.get("contentVersion"):
            piece["contentVersion"] = song_version(piece["notation"])
        if f.parts[-3] == "library":
            versions[f.parent.name] = song_version(piece["notation"])
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(piece))
        tmp.replace(f)
    for pid, v in versions.items():
        r = con.execute("SELECT entry FROM library WHERE piece_id = ?", (pid,)).fetchone()
        if r:
            entry = json.loads(r["entry"] or "{}")
            entry["contentVersion"] = v
            con.execute("UPDATE library SET entry = ? WHERE piece_id = ?", (json.dumps(entry), pid))
    if versions:
        from app import library
        library.write_index(con)
