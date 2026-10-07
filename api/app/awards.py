"""Rewards (arch §3 "Rewards", M10): the star collection and medals.

The **star collection** is the sum of each song's best accuracy stars, from completed plays of the
whole song (generated drills and section practice don't count). Playing a song again adds stars
only by beating its best, so the total rewards playing well, not playing the same easy song often.

**Medals** come in bronze, silver, gold and platinum:
- milestone medals, a row of steps for each measure (SERIES): the star collection, the practice
  streak, skills mastered, five-star songs, songs played and hours at the piano;
- unit and level medals: bronze when every skill in it is passed, silver when every one is
  mastered, gold when every one is mastered with 5 stars.

A medal is stored when first earned and never taken back, like the map's best-so-far stars.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from . import engine
from .content import Content

B, S, G, P = "bronze", "silver", "gold", "platinum"

# measure -> (name, the words after a step's number, steps with their tier)
SERIES: dict[str, tuple[str, str, list[tuple[int, str]]]] = {
    "stars": ("Star collection", "stars", [(25, B), (50, B), (100, S), (250, S), (500, G), (1000, G), (2500, P), (5000, P)]),
    "streak": ("Practice streak", "days in a row", [(3, B), (7, B), (14, S), (30, S), (60, G), (100, G), (200, P), (365, P)]),
    "mastered": ("Skills mastered", "skills mastered", [(1, B), (5, B), (10, S), (25, S), (50, G), (100, G), (200, P), (400, P)]),
    "fivestar": ("Five-star songs", "five-star songs", [(1, B), (3, B), (10, S), (25, S), (50, G), (100, G), (250, P)]),
    "songs": ("Songs played", "songs played", [(5, B), (10, B), (25, S), (50, S), (100, G), (250, P)]),
    "hours": ("Time at the piano", "hours", [(1, B), (5, B), (10, S), (25, S), (50, G), (100, G), (250, P), (500, P)]),
}
# unit and level medals, in the order they are earned
GROUP_TIERS = [("complete", B, "Complete"), ("mastered", S, "All mastered"), ("fivestar", G, "All five stars")]


def step_label(kind: str, at: int) -> str:
    words = SERIES[kind][1]
    if at == 1:
        words = {"skills mastered": "skill mastered", "five-star songs": "five-star song", "hours": "hour"}.get(words, words)
    return f"{at} {words}"


# ------------------------------------------------------------------------------ the star collection

def plays(con: sqlite3.Connection, student_id: str) -> list[sqlite3.Row]:
    """Completed plays of whole songs: what the star collection counts."""
    return con.execute(
        "SELECT id, piece_id, accuracy_stars, started_at FROM attempts WHERE student_id = ? AND completed = 1 "
        "AND mode = 'play' AND accuracy_stars IS NOT NULL AND piece_id NOT LIKE 'drill-%'", (student_id,)).fetchall()


def bests(rows, before: date | None = None, skip: str | None = None) -> dict[str, float]:
    """Each song's best accuracy stars, from plays before a day (or all) and leaving one out."""
    out: dict[str, float] = {}
    for r in rows:
        if r["id"] == skip or (before and local_day(r["started_at"]) >= before):
            continue
        out[r["piece_id"]] = max(out.get(r["piece_id"], 0.0), r["accuracy_stars"])
    return out


def local_day(ts: str) -> date:
    return datetime.fromisoformat(ts).astimezone().date()


def collection(con: sqlite3.Connection, student_id: str, today: date) -> dict[str, Any]:
    """The star total, what it grew by today and this week, and each song's best (for the library)."""
    rows = plays(con, student_id)
    now = bests(rows)
    total = sum(now.values())
    return {"total": total, "today": total - sum(bests(rows, today).values()),
            "week": total - sum(bests(rows, today - timedelta(days=6)).values()), "songs": now}


# ------------------------------------------------------------------------------ measures and medals

def measures(con: sqlite3.Connection, content: Content, student_id: str, today: date,
             states: dict[str, engine.SkillState] | None = None, songs: dict[str, float] | None = None) -> dict[str, float]:
    states = states or engine.load_states(con, content, student_id)
    songs = songs if songs is not None else bests(plays(con, student_id))
    secs = con.execute("SELECT COALESCE(SUM(guided_sec + free_sec), 0) FROM practice_days WHERE student_id = ?",
                       (student_id,)).fetchone()[0]
    return {
        "stars": sum(songs.values()),
        "streak": engine.streak(con, student_id, today),
        "mastered": sum(1 for st in states.values() if st.status == "mastered" or st.mastered_date),
        "fivestar": sum(1 for v in songs.values() if v >= 5),
        "songs": len(songs),
        "hours": secs / 3600,
    }


def groups(content: Content, states: dict[str, engine.SkillState]) -> list[dict[str, Any]]:
    """Each level, and each unit in it, with how far the student is through it. A skill on
    capability hold (8.1) is left out: it can't be played on this setup."""
    def mastered(st: engine.SkillState) -> bool:
        return st.status == "mastered" or bool(st.mastered_date)

    def tally(skills) -> dict[str, Any]:
        live = [states[s.id] for s in skills if not states[s.id].capability_hold]
        return {"skills": len(live),
                "passed": sum(1 for st in live if st.passed),
                "mastered": sum(1 for st in live if mastered(st)),
                "fivestar": sum(1 for st in live if mastered(st) and (st.best_accuracy_stars or 0) >= 5)}
    out: list[dict[str, Any]] = []
    for s in content.order:
        if s.id not in states:
            continue
        if not out or out[-1]["level"] != (s.level or "Skills"):
            out.append({"level": s.level or "Skills", "skills_": [], "units": []})
        lv = out[-1]
        lv["skills_"].append(s)
        if s.unit:
            u = next((u for u in lv["units"] if u["unit"] == s.unit), None)
            if u is None:
                u = {"unit": s.unit, "skills_": []}
                lv["units"].append(u)
            u["skills_"].append(s)
    for lv in out:
        lv.update(tally(lv.pop("skills_")))
        for u in lv["units"]:
            u.update(tally(u.pop("skills_")))
    return out


def reached(g: dict[str, Any]) -> list[tuple[str, str, str]]:
    """The unit or level medals a tally has reached."""
    n = g["skills"]
    have = {"complete": g["passed"], "mastered": g["mastered"], "fivestar": g["fivestar"]}
    return [t for t in GROUP_TIERS if n and have[t[0]] >= n]


def check(con: sqlite3.Connection, content: Content, student_id: str, today: date,
          states: dict[str, engine.SkillState] | None = None) -> list[dict[str, Any]]:
    """Store every medal now reached and not yet earned; returns the new ones, the most important
    first (a level, then units, then milestones, highest tier first)."""
    states = states or engine.load_states(con, content, student_id)
    have = {r[0] for r in con.execute("SELECT id FROM awards WHERE student_id = ?", (student_id,))}
    new: list[dict[str, Any]] = []

    def earn(aid: str, kind: str, tier: str, title: str, detail: str) -> None:
        if aid not in have:
            new.append({"id": aid, "kind": kind, "tier": tier, "title": title, "detail": detail, "date": today.isoformat()})

    for lv in groups(content, states):
        for key, tier, words in reached(lv):
            earn(f"level:{lv['level']}:{key}", "level", tier, lv["level"], words)
        for u in lv["units"]:
            for key, tier, words in reached(u):
                earn(f"unit:{lv['level']}|{u['unit']}:{key}", "unit", tier, u["unit"], words)
    m = measures(con, content, student_id, today, states)
    for kind, (name, _, steps) in SERIES.items():
        for at, tier in steps:
            if m[kind] >= at:
                earn(f"{kind}:{at}", kind, tier, name, step_label(kind, at))
    for a in new:
        con.execute("INSERT INTO awards (student_id, id, kind, tier, title, detail, earned_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (student_id, a["id"], a["kind"], a["tier"], a["title"], a["detail"], a["date"]))
    rank = {"level": 0, "unit": 1}
    tiers = [B, S, G, P]
    return sorted(new, key=lambda a: (rank.get(a["kind"], 2), -tiers.index(a["tier"])))


def after_attempt(con: sqlite3.Connection, content: Content, student_id: str, attempt_id: str, piece_id: str,
                  today: date) -> dict[str, Any]:
    """What an attempt added, for the result screen: new medals, the stars it added to the
    collection, and the song's personal best when it beat it."""
    rows = plays(con, student_id)
    now, before = bests(rows), bests(rows, skip=attempt_id)
    out: dict[str, Any] = {"awards": check(con, content, student_id, today),
                           "stars": {"total": sum(now.values()), "gained": now.get(piece_id, 0) - before.get(piece_id, 0)},
                           "best": None}
    if piece_id in before and now.get(piece_id, 0) > before[piece_id]:
        out["best"] = {"previous": before[piece_id], "now": now[piece_id]}
    return out


def summary(con: sqlite3.Connection, student_id: str, today: date) -> dict[str, Any]:
    """For every screen (the student's state): the star total, today's growth, each song's best,
    and how many medals the student hasn't looked at yet."""
    c = collection(con, student_id, today)
    unseen = con.execute("SELECT COUNT(*) FROM awards WHERE student_id = ? AND seen = 0", (student_id,)).fetchone()[0]
    return {"stars": c["total"], "starsToday": c["today"], "songStars": c["songs"], "unseen": unseen}


def report(con: sqlite3.Connection, content: Content, student_id: str, today: date) -> dict[str, Any]:
    """The trophy case (My Progress): the collection, each milestone row with its next step, and
    each level and unit with its medals."""
    states = engine.load_states(con, content, student_id)
    c = collection(con, student_id, today)
    m = measures(con, content, student_id, today, states, c["songs"])
    earned = {r["id"]: r for r in con.execute("SELECT * FROM awards WHERE student_id = ?", (student_id,))}

    def medal(aid: str) -> dict[str, Any] | None:
        r = earned.get(aid)
        return {"date": r["earned_date"], "new": not r["seen"]} if r else None

    series = []
    for kind, (name, _, steps) in SERIES.items():
        rows = [{"at": at, "tier": tier, "label": step_label(kind, at), "earned": medal(f"{kind}:{at}")} for at, tier in steps]
        nxt = next((r for r in rows if not r["earned"] and m[kind] < r["at"]), None)
        series.append({"kind": kind, "name": name, "value": round(m[kind], 1), "steps": rows, "next": nxt})
    levels = []
    for lv in groups(content, states):
        lv["medals"] = [{"key": k, "tier": t, "label": w, "earned": medal(f"level:{lv['level']}:{k}")} for k, t, w in GROUP_TIERS]
        for u in lv["units"]:
            u["medals"] = [{"key": k, "tier": t, "label": w, "earned": medal(f"unit:{lv['level']}|{u['unit']}:{k}")}
                           for k, t, w in GROUP_TIERS]
        levels.append(lv)
    recent = [{"id": r["id"], "kind": r["kind"], "tier": r["tier"], "title": r["title"], "detail": r["detail"],
               "date": r["earned_date"], "new": not r["seen"]}
              for r in sorted(earned.values(), key=lambda r: (r["earned_date"], r["id"]), reverse=True)[:8]]
    return {"stars": {"total": c["total"], "today": c["today"], "week": c["week"]},
            "series": series, "levels": levels, "recent": recent, "count": len(earned),
            "unseen": sum(1 for r in earned.values() if not r["seen"])}


def mark_seen(con: sqlite3.Connection, student_id: str) -> None:
    con.execute("UPDATE awards SET seen = 1 WHERE student_id = ? AND seen = 0", (student_id,))
