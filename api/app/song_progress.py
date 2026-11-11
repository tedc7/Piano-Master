"""Song progress (arch §8.12, v0.50): each student's progress on each song, a record of its own
beside the skill states. A skill state says what the child can do; a song's record says what the
child can play, and how far along a song still being learned is.

One function keeps it, `update`, after every stored attempt (students.after_attempt), and the same
function rebuilds it from the stored attempts (`rebuild`, used by migration 015), so the two always
agree. It reads only the attempt itself, the song's hands (R, L or RL) and its phrase starts.

What it holds, per student and song (a piece id; two arrangements are two records):
  - plays, completed plays, seconds, first and last played;
  - hands_done: the hands it has been played to the end with in Play mode (R, L, both): the one-hand
    steps of a new song for both hands (v0.40) read this;
  - best: the best accuracy and timing stars for each way it was played to the end, "<hands>|<preset>"
    ("both" is as written; a song for one hand played with that hand counts as "both");
  - best_stars and day_best: the song's best stars in the star collection, and each day's best
    (the collection's growth today and this week; the same plays the collection always counted);
  - tempo_reached: the fastest preset played as written with 3 stars or more;
  - stage: new, hands-apart, learning, slow, learned, solid, excellent; it never goes back;
  - sections: for each phrase, plays, the last pass's errors, the fewest, the day last practised and
    how often it was the tricky spot; tricky: the last tricky phrase (Play mode), last_preset;
  - learned_date, five_star_date.
Drills and the parent's plays have no record.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

STAGES = ["new", "hands-apart", "learning", "slow", "learned", "solid", "excellent"]
PRESETS = ["50", "75", "90", "100"]
PASS = 3.0
JSON_COLS = {"hands_done": "[]", "best": "{}", "day_best": "{}", "sections": "[]", "tricky": "null"}
COLUMNS = ["student_id", "piece_id", "song_version", "hands", "plays", "completed_plays", "seconds", "first_played",
           "last_played", "hands_done", "best", "best_stars", "day_best", "tempo_reached", "stage", "sections", "tricky",
           "last_preset", "learned_date", "five_star_date"]

SCHEMA = """CREATE TABLE IF NOT EXISTS song_progress (
  student_id      TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  piece_id        TEXT NOT NULL,
  song_version    TEXT,
  hands           TEXT,
  plays           INTEGER NOT NULL DEFAULT 0,
  completed_plays INTEGER NOT NULL DEFAULT 0,
  seconds         REAL NOT NULL DEFAULT 0,
  first_played    TEXT,
  last_played     TEXT,
  hands_done      TEXT NOT NULL DEFAULT '[]',
  best            TEXT NOT NULL DEFAULT '{}',
  best_stars      REAL,
  day_best        TEXT NOT NULL DEFAULT '{}',
  tempo_reached   TEXT,
  stage           TEXT NOT NULL DEFAULT 'new',
  sections        TEXT NOT NULL DEFAULT '[]',
  tricky          TEXT,
  last_preset     TEXT,
  learned_date    TEXT,
  five_star_date  TEXT,
  PRIMARY KEY (student_id, piece_id)
)"""


def local_day(ts: str) -> date:
    """The local calendar day of a stored time (as the star collection counts it)."""
    return datetime.fromisoformat(ts).astimezone().date()


def loads(v, empty: str):
    if isinstance(v, (dict, list)):
        return v
    return json.loads(v or empty)


def blank(student_id: str, piece_id: str) -> dict[str, Any]:
    return {"student_id": student_id, "piece_id": piece_id, "song_version": None, "hands": None, "plays": 0,
            "completed_plays": 0, "seconds": 0.0, "first_played": None, "last_played": None, "hands_done": [],
            "best": {}, "best_stars": None, "day_best": {}, "tempo_reached": None, "stage": "new", "sections": [],
            "tricky": None, "last_preset": None, "learned_date": None, "five_star_date": None}


def row_out(r: sqlite3.Row) -> dict[str, Any]:
    d = {c: r[c] for c in COLUMNS}
    for c, empty in JSON_COLS.items():
        d[c] = loads(d[c], empty)
    return d


def get(con: sqlite3.Connection, student_id: str, piece_id: str) -> dict[str, Any] | None:
    r = con.execute("SELECT * FROM song_progress WHERE student_id = ? AND piece_id = ?", (student_id, piece_id)).fetchone()
    return row_out(r) if r else None


def load(con: sqlite3.Connection, student_id: str) -> dict[str, dict[str, Any]]:
    """Every song's record for a student, by piece id."""
    return {r["piece_id"]: row_out(r) for r in con.execute("SELECT * FROM song_progress WHERE student_id = ?", (student_id,))}


def save(con: sqlite3.Connection, rec: dict[str, Any]) -> None:
    v = [json.dumps(rec[c]) if c in JSON_COLS else rec[c] for c in COLUMNS]
    con.execute(f"INSERT OR REPLACE INTO song_progress ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})", v)


# ------------------------------------------------------------------------------ the rules

def counts_in_collection(a: dict) -> bool:
    """The star collection's plays (awards, v0.36): completed plays of the whole song, not a planned
    one-hand step of a song for both hands (v0.40), and not a drill."""
    c = a["conditions"]
    return (bool(a["completed"]) and a["mode"] == "play" and a.get("accuracy_stars") is not None
            and not (c.get("hands") in ("R", "L") and c.get("handsWritten") == c.get("hands")))


def hands_key(played: str, piece_hands: str | None) -> str:
    """"both" for the song as written: all its notes, or a song for one hand played with that hand."""
    return "both" if played == "both" or (piece_hands in ("R", "L") and played == piece_hands) else played


def stage_of(rec: dict[str, Any]) -> str:
    """The stage the record has reached now (`update` keeps the highest ever reached)."""
    best = rec["best"]
    full = (best.get("both|100") or {}).get("acc")
    if full is not None and full >= 5:
        return "excellent"
    if full is not None and full >= 4:
        return "solid"
    if full is not None and full >= PASS:
        return "learned"
    written = [b["acc"] for k, b in best.items() if k.startswith("both|")]
    if any(x >= PASS for x in written):
        return "slow"
    if written:
        return "learning"
    if rec["hands"] == "RL" and any(k.startswith(("R|", "L|")) for k in best):
        return "hands-apart"
    return "new"


def tempo_reached(rec: dict[str, Any]) -> str | None:
    ok = [p for p in PRESETS if (rec["best"].get(f"both|{p}") or {}).get("acc", 0) >= PASS]
    return ok[-1] if ok else None


def phrase_spans(phrases: list[float] | None, length: float | None) -> list[tuple[float, float]] | None:
    if not phrases:
        return None
    ends = list(phrases[1:]) + [length if length is not None else float("inf")]
    return [(float(a), float(b)) for a, b in zip(phrases, ends)]


def update(con: sqlite3.Connection, student_id: str, a: dict[str, Any], piece_hands: str | None = None,
           phrases: list[float] | None = None, length: float | None = None) -> dict[str, Any] | None:
    """Add one stored attempt to the student's record of its song. `a` holds the attempt's columns
    (conditions, per_phrase_errors, section and tricky decoded). Returns the song's collection stars
    before and after, and its stage before and after; None for a drill."""
    pid = a["piece_id"]
    if pid.startswith("drill-"):
        return None
    rec = get(con, student_id, pid) or blank(student_id, pid)
    before_stars, before_stage = rec["best_stars"], rec["stage"]
    rec["hands"] = piece_hands or rec["hands"]
    day = local_day(a["started_at"]).isoformat()
    c = a["conditions"]
    rec["plays"] += 1
    rec["seconds"] = round(rec["seconds"] + float(a.get("duration_sec") or 0), 1)
    rec["first_played"] = min(filter(None, [rec["first_played"], day]))
    rec["last_played"] = max(filter(None, [rec["last_played"], day]))
    rec["song_version"] = a.get("content_version") or rec["song_version"]
    rec["last_preset"] = a.get("tempo_preset") or c.get("tempoPreset") or rec["last_preset"]
    done = bool(a["completed"])
    if done:
        rec["completed_plays"] += 1
    if done and a["mode"] == "play":
        h = c.get("hands") or "both"
        if h not in rec["hands_done"]:
            rec["hands_done"].append(h)
        key = f"{hands_key(h, rec['hands'])}|{c.get('tempoPreset') or a.get('tempo_preset') or '100'}"
        b = rec["best"].get(key) or {}
        acc, tim = a.get("accuracy_stars"), a.get("timing_stars")
        if acc is not None and acc > b.get("acc", -1):
            b.update(acc=acc, day=day)
        if tim is not None and tim > (b.get("tim") if b.get("tim") is not None else -1):
            b["tim"] = tim
        if b:
            rec["best"][key] = b
    if counts_in_collection(a):
        rec["best_stars"] = max(rec["best_stars"] or 0.0, float(a["accuracy_stars"]))
        rec["day_best"][day] = max(rec["day_best"].get(day, 0.0), float(a["accuracy_stars"]))
    if a["mode"] == "play" and a.get("tricky") and a["tricky"].get("phrase") is not None:
        rec["tricky"] = {"phrase": int(a["tricky"]["phrase"]), "day": day}
    # sections: each phrase the attempt played, by its last pass's errors
    spans = phrase_spans(phrases, length)
    errs = a.get("per_phrase_errors") or []
    if spans and rec["sections"] and len(rec["sections"]) != len(spans):
        rec["sections"] = []                 # a live update changed the song's phrases: its sections start again
    if done and spans and errs:
        while len(rec["sections"]) < len(spans):
            rec["sections"].append({"plays": 0, "lastErrors": None, "fewestErrors": None, "last": None, "tricky": 0})
        sec = a.get("section")
        lo, hi = (sec["fromBeat"], sec["toBeat"]) if a["mode"] == "loop" and sec else (spans[0][0], spans[-1][1])
        tp = (a.get("tricky") or {}).get("phrase")
        for i, (s0, s1) in enumerate(spans):
            if i >= len(errs) or s1 <= lo + 1e-6 or s0 >= hi - 1e-6:
                continue
            x = rec["sections"][i]
            x["plays"] += 1
            x["lastErrors"] = int(errs[i])
            x["fewestErrors"] = int(errs[i]) if x["fewestErrors"] is None else min(x["fewestErrors"], int(errs[i]))
            x["last"] = day
            if tp == i:
                x["tricky"] += 1
    rec["tempo_reached"] = tempo_reached(rec)
    now = stage_of(rec)
    if STAGES.index(now) > STAGES.index(rec["stage"]):
        rec["stage"] = now
    if STAGES.index(rec["stage"]) >= STAGES.index("learned") and not rec["learned_date"]:
        rec["learned_date"] = day
    if rec["stage"] == "excellent" and not rec["five_star_date"]:
        rec["five_star_date"] = day
    save(con, rec)
    return {"before": before_stars, "after": rec["best_stars"], "stageBefore": before_stage, "stage": rec["stage"]}


def attempt_dict(r: sqlite3.Row) -> dict[str, Any]:
    """A stored attempt's row, as `update` reads it."""
    return {"piece_id": r["piece_id"], "mode": r["mode"], "completed": r["completed"], "started_at": r["started_at"],
            "duration_sec": r["duration_sec"], "tempo_preset": r["tempo_preset"], "content_version": r["content_version"],
            "conditions": loads(r["conditions"], "{}"), "accuracy_stars": r["accuracy_stars"], "timing_stars": r["timing_stars"],
            "per_phrase_errors": loads(r["per_phrase_errors"], "[]"), "section": loads(r["section"], "null"),
            "tricky": loads(r["tricky"], "null")}


def rebuild(con: sqlite3.Connection, songs: dict[str, dict[str, Any]], student_id: str | None = None) -> int:
    """Every student's records (or one student's) again from the stored attempts, in the order they
    were stored. `songs`: piece id -> {"hands", "phrases", "length"}, for the songs known (a removed
    song's attempts still count; its sections aren't kept). Returns the attempts replayed."""
    where, args = ("WHERE student_id = ?", (student_id,)) if student_id else ("WHERE student_id IS NOT NULL", ())
    con.execute(f"DELETE FROM song_progress {where}", args)
    n = 0
    # only students that exist (a record needs its student): a stray attempt can't stop the API starting
    for r in con.execute(f"SELECT * FROM attempts {where} AND student_id IN (SELECT id FROM students) ORDER BY rowid", args).fetchall():
        s = songs.get(r["piece_id"]) or {}
        update(con, r["student_id"], attempt_dict(r), s.get("hands"), s.get("phrases"), s.get("length"))
        n += 1
    return n


def songs_in_library(data: Path) -> dict[str, dict[str, Any]]:
    """Each library song's hands and phrases, from the library's files (for the migration, which
    runs before the content is loaded)."""
    out: dict[str, dict[str, Any]] = {}
    lib = data / "library"
    try:
        index = json.loads((lib / "index.json").read_text())
    except (OSError, ValueError):
        return out
    for p in index.get("pieces", []):
        entry: dict[str, Any] = {"hands": p.get("hands")}
        try:
            nota = json.loads((lib / p["id"] / "piece.json").read_text()).get("notation") or {}
            entry.update(phrases=nota.get("phrases"), length=nota.get("length"))
        except (OSError, ValueError):
            pass
        out[p["id"]] = entry
    return out


# ------------------------------------------------------------------------------ reads

def hands_done(con: sqlite3.Connection, student_id: str) -> dict[str, set[str]]:
    """The hands the student has played each song to the end with, in Play mode (engine.Planner)."""
    return {r["piece_id"]: set(loads(r["hands_done"], "[]"))
            for r in con.execute("SELECT piece_id, hands_done FROM song_progress WHERE student_id = ?", (student_id,))}


def collection(con: sqlite3.Connection, student_id: str, since: list[date]) -> tuple[dict[str, float], list[dict[str, float]]]:
    """Each song's best stars in the collection now, and as they stood before each day in `since`."""
    now: dict[str, float] = {}
    then: list[dict[str, float]] = [{} for _ in since]
    for r in con.execute("SELECT piece_id, best_stars, day_best FROM song_progress WHERE student_id = ? AND best_stars IS NOT NULL",
                         (student_id,)):
        now[r["piece_id"]] = r["best_stars"]
        days = loads(r["day_best"], "{}")
        for i, d in enumerate(since):
            xs = [v for k, v in days.items() if k < d.isoformat()]
            if xs:
                then[i][r["piece_id"]] = max(xs)
    return now, then


def summary(rec: dict[str, Any]) -> dict[str, Any]:
    """What the student's screens show of a song: its stage and the facts its next step comes from."""
    full = rec["best"].get("both|100") or {}
    return {"stage": rec["stage"], "best": rec["best_stars"], "fullStars": full.get("acc"), "tempoReached": rec["tempo_reached"],
            "handsDone": sorted(rec["hands_done"]), "hands": rec["hands"], "plays": rec["plays"], "lastPlayed": rec["last_played"],
            "learned": rec["learned_date"]}


def summaries(con: sqlite3.Connection, student_id: str) -> dict[str, dict[str, Any]]:
    return {pid: summary(r) for pid, r in load(con, student_id).items()}
