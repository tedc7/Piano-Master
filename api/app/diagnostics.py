"""Weakness diagnostics (arch §8.8): mastery shows *that* a skill is weak; Diagnostics finds *why*
from the per-note results of the last 14 days of completed attempts, and the lesson engine puts
one remedy a day into the Practice slot (two when the session is 20 minutes or longer).

| Pattern        | Detected when (first version)                                                  | Remedy                                   |
| -------------- | ------------------------------------------------------------------------------ | ---------------------------------------- |
| Note confusion | The same wrong key for the same written note 3+ times, on 2+ days, in 30%+ of   | A reading drill around the two notes     |
|                | that note's occurrences                                                        |                                          |
| Rhythm         | One rhythm figure: 12+ notes on 2+ days, 70%+ in the same direction (early or   | A rhythm tap drill, then the bars with   |
|                | late), averaging beyond half the on-time window                                 | the metronome                            |
| Hands together | The last 3 hands-together plays of a piece 15+ points below the weaker hand    | The weaker hand alone, then hands        |
|                | alone                                                                          | together one preset slower               |
| Position shift | Over 3+ attempts, the 2 notes after a hand-position change go wrong 2x as often | The bars around the shift, looped        |
|                | as the rest of the piece, and 25%+ of the time                                 |                                          |
| Tempo ceiling  | 3+ plays at two neighbouring presets, the faster 15+ points lower              | The slower preset, then the faster one   |

First-version choices beyond the table (tuned with real data, §7.10): accuracy is before the
practice-aid factor; a rhythm pattern found on every note is "a steady beat" (general rushing or
dragging), and a figure then counts only when it is further off than the rest; a pattern is
resolved when its affected notes score 4 stars (86%) on 2 days after it was found, stuck after 3
remedies or 2 weeks without a good day, and set aside (resolved) when 14 days pass without it
being seen. A resolved pattern is found again only from attempts after it was resolved.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from . import drills
from .analysis import name as note_name
from .content import Content

WINDOW_DAYS = 14
GOOD = 0.86                      # 4 stars
# note confusion
CONFUSION_COUNT, CONFUSION_DAYS, CONFUSION_SHARE = 3, 2, 0.30
# rhythm
RHYTHM_COUNT, RHYTHM_DAYS, RHYTHM_SAME_WAY = 12, 2, 0.70
# hands together, tempo ceiling
POINTS = 0.15
HANDS_LAST, TEMPO_PLAYS = 3, 3
# position shift
SHIFT_ATTEMPTS, SHIFT_RATIO, SHIFT_RATE = 3, 2.0, 0.25
# lifecycle
STUCK_REMEDIES, STUCK_DAYS = 3, 14
PRESETS = ["50", "75", "90", "100"]
SLOWER = {"100": "90", "90": "75", "75": "50", "50": "50"}
ON_TIME_MS = {"prep": 150, "1-2": 120, "3-4": 100, "5+": 80}


def on_time_ms(level: str | None) -> float:
    """The on-time window of the level band (§7.1)."""
    t = (level or "").lower()
    if not t or "prep" in t:
        return ON_TIME_MS["prep"]
    digits = [int(c) for c in t if c.isdigit()]
    n = digits[0] if digits else 1
    return ON_TIME_MS["1-2"] if n <= 2 else ON_TIME_MS["3-4"] if n <= 4 else ON_TIME_MS["5+"]


def day(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


# ------------------------------------------------------------------------------ reading attempts

@dataclass
class Obs:
    """One completed attempt, as Diagnostics reads it."""
    day: date
    piece_id: str
    mode: str                       # play or loop
    preset: str
    hands: str                      # both, R or L
    raw_accuracy: float
    accuracy_stars: float
    skill_id: str | None = None
    results: list[tuple[int, float | None]] = field(default_factory=list)   # [notation index, ms or None]
    wrongs: list[dict] = field(default_factory=list)       # wrong keys paired with the written note


def load_obs(con: sqlite3.Connection, student_id: str, today: date, days: int = WINDOW_DAYS) -> list[Obs]:
    since = datetime.combine(today - timedelta(days=days), datetime.min.time()).astimezone()
    rows = con.execute(
        "SELECT started_at, piece_id, mode, tempo_preset, conditions, raw_accuracy, accuracy_stars, skill_id, note_results, "
        "note_errors FROM attempts WHERE student_id = ? AND completed = 1 AND started_at >= ? ORDER BY started_at",
        (student_id, since.isoformat())).fetchall()
    out = []
    for r in rows:
        d = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00")).astimezone().date()
        if d > today:
            continue
        cond = json.loads(r["conditions"] or "{}")
        errs = json.loads(r["note_errors"] or "[]")
        out.append(Obs(day=d, piece_id=r["piece_id"], mode=r["mode"], preset=r["tempo_preset"], hands=cond.get("hands", "both"),
                       raw_accuracy=r["raw_accuracy"], accuracy_stars=r["accuracy_stars"], skill_id=r["skill_id"],
                       results=[(int(x[0]), x[1]) for x in json.loads(r["note_results"] or "[]")],
                       wrongs=[e for e in errs if e.get("kind") == "wrong" and e.get("expected") is not None]))
    return out


# ------------------------------------------------------------------------------ what each note is

@dataclass
class Annot:
    """One piece's notes, as Diagnostics sees them: pitch, hand, bar, rhythm figures, and whether
    the note is one of the two after a hand-position change."""
    pitch: list[int]
    hand: list[str]
    bar: list[int]
    figures: list[set[str]]
    shift: list[bool]
    shift_at: list[int]              # the note starting each shift
    level: str = ""


def figures_of(notes: list[dict], i: int, prev_end: float | None, beat_unit: float) -> set[str]:
    n = notes[i]
    d, start = float(n["duration"]), float(n["start"])
    out = set()
    if n.get("tuplet"):
        out.add("triplet")
    elif abs(d - 0.5) < 1e-6:
        out.add("eighths")
    elif abs(d - 0.25) < 1e-6:
        out.add("sixteenths")
    elif abs(d - 1.5) < 1e-6 or abs(d - 0.75) < 1e-6:
        out.add("dotted")
    elif abs(d - 1) < 1e-6:
        out.add("quarters")
    if prev_end is not None and start > prev_end + 0.49:
        out.add("after-rest")
    if d >= 1 - 1e-6 and abs(start / beat_unit - round(start / beat_unit)) > 1e-6:
        out.add("offbeat")
    return out


def annotate(nota: dict, level: str = "") -> Annot:
    notes = nota["notes"]
    measures = nota["measures"]
    beat_unit = 1.5 if nota["header"]["timeSig"] in ("6/8", "9/8", "12/8") else 4 / int(nota["header"]["timeSig"].split("/")[1])

    def bar_of(b: float) -> int:
        for m in measures:
            if m["start"] - 1e-6 <= b < m["start"] + m["duration"] - 1e-6:
                return m["number"]
        return measures[-1]["number"]

    figs: list[set[str]] = [set() for _ in notes]
    shift = [False] * len(notes)
    shift_at: list[int] = []
    for h in ("R", "L"):
        mine = sorted((i for i, n in enumerate(notes) if n["hand"] == h), key=lambda i: (notes[i]["start"], notes[i]["pitch"]))
        prev_end: float | None = None
        prev: int | None = None
        for i in mine:
            if prev is not None and abs(notes[i]["start"] - notes[prev]["start"]) < 1e-6:
                figs[i] = set(figs[prev])                   # a chord note: the same figure
            else:
                figs[i] = figures_of(notes, i, prev_end, beat_unit)
                prev_end = max(prev_end or 0.0, max(notes[j]["start"] + notes[j]["duration"] for j in mine
                                                    if abs(notes[j]["start"] - notes[i]["start"]) < 1e-6))
            prev = i
        # hand position: where the thumb would be (in white keys), from the finger numbers
        melody = []
        for i in mine:
            if melody and abs(notes[melody[-1]]["start"] - notes[i]["start"]) < 1e-6:
                continue                                    # one note per chord: the first
            melody.append(i)
        anchor = None
        for k, i in enumerate(melody):
            f = notes[i].get("finger")
            if not f:
                anchor = None
                continue
            p = notes[i]["pitch"]
            wi = (p // 12) * 7 + [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6][p % 12]
            a = wi - (f - 1) if h == "R" else wi + (f - 1)
            if anchor is not None and abs(a - anchor) >= 2:
                shift_at.append(i)
                shift[i] = True
                if k + 1 < len(melody):
                    shift[melody[k + 1]] = True
            anchor = a
    return Annot(pitch=[n["pitch"] for n in notes], hand=[n["hand"] for n in notes],
                 bar=[bar_of(n["start"]) for n in notes], figures=figs, shift=shift, shift_at=shift_at, level=level)


class Pieces:
    """Notation and annotations for the pieces and drills that appear in attempts."""

    def __init__(self, con: sqlite3.Connection, content: Content):
        self.con, self.c = con, content
        self.cache: dict[str, Annot | None] = {}

    def notation(self, pid: str) -> tuple[dict | None, str]:
        if pid.startswith("drill-"):
            r = self.con.execute("SELECT piece FROM drills WHERE id = ?", (pid,)).fetchone()
            if not r:
                return None, ""
            p = json.loads(r["piece"])
            return p["notation"], p.get("level", "")
        p = self.c.pieces.get(pid)
        return self.c.notation(pid), (p.level if p else "")

    def annot(self, pid: str) -> Annot | None:
        if pid not in self.cache:
            nota, level = self.notation(pid)
            self.cache[pid] = annotate(nota, level) if nota else None
        return self.cache[pid]


# ------------------------------------------------------------------------------ detectors

@dataclass
class Found:
    kind: str
    key: str
    details: dict[str, Any]
    skills: set[str]
    occurrences: int


def skills_for(c: Content, o: Obs) -> set[str]:
    out = {o.skill_id} if o.skill_id in c.skills else set()
    p = c.pieces.get(o.piece_id)
    return out | (set(p.featured) if p else set())


def note_confusion(obs: list[Obs], P: Pieces, c: Content) -> list[Found]:
    pairs: Counter = Counter()
    pair_days: dict[tuple, set[date]] = defaultdict(set)
    pair_skills: dict[tuple, set[str]] = defaultdict(set)
    written: Counter = Counter()
    for o in obs:
        a = P.annot(o.piece_id)
        if a is None:
            continue
        for ni, _ in o.results:
            if 0 <= ni < len(a.pitch):
                written[(a.hand[ni], a.pitch[ni])] += 1
        for w in o.wrongs:
            k = (w.get("hand") or "R", int(w["expected"]), int(w["pitch"]))
            pairs[k] += 1
            pair_days[k].add(o.day)
            pair_skills[k] |= skills_for(c, o)
    out = []
    for (hand, exp, played), n in pairs.items():
        of = written[(hand, exp)]
        if n >= CONFUSION_COUNT and len(pair_days[(hand, exp, played)]) >= CONFUSION_DAYS and of and n / of >= CONFUSION_SHARE:
            out.append(Found("note", f"note:{hand}:{exp}>{played}",
                             {"hand": hand, "expected": exp, "played": played, "count": n, "of": of,
                              "text": f"plays {note_name(played)} for {note_name(exp)} ({'left' if hand == 'L' else 'right'} hand)"},
                             pair_skills[(hand, exp, played)], n))
    return out


def timing_points(ms: float, window: float) -> float:
    return 1.0 if abs(ms) <= window else 0.5 if abs(ms) <= 2 * window else 0.0


def rhythm(obs: list[Obs], P: Pieces, c: Content) -> list[Found]:
    by_fig: dict[str, list[tuple[float, date, float]]] = defaultdict(list)     # figure -> (ms, day, window)
    fig_skills: dict[str, set[str]] = defaultdict(set)
    fig_where: dict[str, Counter] = defaultdict(Counter)        # figure -> (piece, bar) -> off-time notes
    for o in obs:
        a = P.annot(o.piece_id)
        if a is None:
            continue
        w = on_time_ms(a.level)
        for ni, ms in o.results:
            if ms is None or not 0 <= ni < len(a.pitch):
                continue
            for f in a.figures[ni] | {"beat"}:
                by_fig[f].append((ms, o.day, w))
                fig_skills[f] |= skills_for(c, o)
                if abs(ms) > w / 2:
                    fig_where[f][(o.piece_id, a.bar[ni])] += 1

    def check(f: str) -> tuple[str, float] | None:
        xs = by_fig.get(f, [])
        if len(xs) < RHYTHM_COUNT or len({d for _, d, _ in xs}) < RHYTHM_DAYS:
            return None
        early = sum(1 for ms, _, _ in xs if ms < 0) / len(xs)
        mean = sum(ms for ms, _, _ in xs) / len(xs)
        way = "early" if early >= RHYTHM_SAME_WAY else "late" if 1 - early >= RHYTHM_SAME_WAY else None
        half = max(w for _, _, w in xs) / 2
        if way and abs(mean) > half and (mean < 0) == (way == "early"):
            return way, mean
        return None

    out = []
    beat = check("beat")
    beat_mean = beat[1] if beat else 0.0
    if beat:
        out.append(("beat", beat))
    for f in sorted(by_fig):
        if f == "beat":
            continue
        r = check(f)
        if r and (not beat or abs(r[1] - beat_mean) > max(w for _, _, w in by_fig[f]) / 2):
            out.append((f, r))
    found = []
    for f, (way, mean) in out:
        where = fig_where[f].most_common(1)
        piece, bar = where[0][0] if where else (None, None)
        found.append(Found("rhythm", f"rhythm:{f}:{way}",
                           {"figure": f, "way": way, "meanMs": round(mean), "notes": len(by_fig[f]), "piece": piece, "bar": bar,
                            "text": f"{way} on {drills.FIGURE_WORDS.get(f, f)} (about {abs(round(mean))} ms)"},
                           fig_skills[f], len(by_fig[f])))
    return found


def hands_together(obs: list[Obs], P: Pieces, c: Content) -> list[Found]:
    out = []
    for pid in {o.piece_id for o in obs}:
        p = c.pieces.get(pid)
        if not p or p.hands != "RL":
            continue
        plays = [o for o in obs if o.piece_id == pid and o.mode == "play"]
        both = [o for o in plays if o.hands == "both"][-HANDS_LAST:]
        sep = {h: [o.raw_accuracy for o in plays if o.hands == h][-HANDS_LAST:] for h in ("R", "L")}
        if len(both) < HANDS_LAST or not sep["R"] or not sep["L"]:
            continue
        acc_both = sum(o.raw_accuracy for o in both) / len(both)
        acc = {h: sum(v) / len(v) for h, v in sep.items()}
        weaker = min(acc, key=acc.get)
        if acc_both <= acc[weaker] - POINTS:
            skills = set().union(*(skills_for(c, o) for o in both))
            out.append(Found("hands", f"hands:{pid}",
                             {"piece": pid, "both": round(acc_both, 3), "R": round(acc["R"], 3), "L": round(acc["L"], 3),
                              "weaker": weaker, "preset": both[-1].preset,
                              "text": f"{p.title}: hands together {round(acc_both * 100)}%, "
                                      f"right {round(acc['R'] * 100)}%, left {round(acc['L'] * 100)}%"},
                             skills, len(both)))
    return out


def position_shift(obs: list[Obs], P: Pieces, c: Content) -> list[Found]:
    out = []
    for pid in {o.piece_id for o in obs}:
        a = P.annot(pid)
        if a is None or not a.shift_at:
            continue
        mine = [o for o in obs if o.piece_id == pid and o.results]
        if len(mine) < SHIFT_ATTEMPTS:
            continue
        s_err = s_n = e_err = e_n = 0
        at_err: Counter = Counter()
        for o in mine:
            for ni, ms in o.results:
                if not 0 <= ni < len(a.shift):
                    continue
                if a.shift[ni]:
                    s_n += 1
                    s_err += ms is None
                    if ms is None:
                        at = max((x for x in a.shift_at if x <= ni), default=ni)
                        at_err[at] += 1
                else:
                    e_n += 1
                    e_err += ms is None
        if not s_n:
            continue
        rate, rest = s_err / s_n, (e_err / e_n if e_n else 0.0)
        if rate >= SHIFT_RATE and rate >= SHIFT_RATIO * rest:
            worst = at_err.most_common(1)[0][0] if at_err else a.shift_at[0]
            b = a.bar[worst]
            bars = [b, b] if b <= 1 else [b - 1, b]
            p = c.pieces.get(pid)
            skills = set().union(*(skills_for(c, o) for o in mine))
            out.append(Found("shift", f"shift:{pid}",
                             {"piece": pid, "rate": round(rate, 3), "rest": round(rest, 3), "bars": bars,
                              "notes": [i for i, s in enumerate(a.shift) if s],
                              "text": f"{p.title if p else pid}: the notes after the hand moves (bar {b}) go wrong "
                                      f"{round(rate * 100)}% of the time"},
                             skills, s_err))
    return out


def tempo_ceiling(obs: list[Obs], P: Pieces, c: Content) -> list[Found]:
    out = []
    for pid in {o.piece_id for o in obs}:
        p = c.pieces.get(pid)
        if not p:
            continue
        plays = [o for o in obs if o.piece_id == pid and o.mode == "play" and o.hands == "both"]
        acc = {}
        for pr in PRESETS:
            xs = [o.raw_accuracy for o in plays if o.preset == pr]
            if len(xs) >= TEMPO_PLAYS:
                acc[pr] = sum(xs) / len(xs)
        for slow, fast in zip(PRESETS, PRESETS[1:]):
            if slow in acc and fast in acc and acc[fast] <= acc[slow] - POINTS:
                skills = set().union(*(skills_for(c, o) for o in plays))
                out.append(Found("tempo", f"tempo:{pid}",
                                 {"piece": pid, "preset": fast, "slower": slow, "fast": round(acc[fast], 3), "slow": round(acc[slow], 3),
                                  "text": f"{p.title}: {round(acc[fast] * 100)}% at {fast}%, {round(acc[slow] * 100)}% at {slow}%"},
                                 skills, sum(1 for o in plays if o.preset in (slow, fast))))
                break                               # the lowest ceiling
    return out


DETECTORS = (note_confusion, rhythm, hands_together, position_shift, tempo_ceiling)


# ------------------------------------------------------------------------------ resolution

def good_day(kind: str, details: dict, day_obs: list[Obs], P: Pieces) -> bool | None:
    """Did the pattern's affected notes or bars score 4 stars on this day? None: no evidence."""
    if kind == "note":
        n = hit = 0
        for o in day_obs:
            a = P.annot(o.piece_id)
            if a is None:
                continue
            for ni, ms in o.results:
                if 0 <= ni < len(a.pitch) and a.pitch[ni] == details["expected"] and a.hand[ni] == details["hand"]:
                    n += 1
                    hit += ms is not None
        return None if n < 3 else hit / n >= GOOD
    if kind == "rhythm":
        pts = []
        for o in day_obs:
            a = P.annot(o.piece_id)
            if a is None:
                continue
            w = on_time_ms(a.level)
            for ni, ms in o.results:
                if ms is not None and 0 <= ni < len(a.pitch) and (details["figure"] == "beat" or details["figure"] in a.figures[ni]):
                    pts.append(timing_points(ms, w))
        return None if len(pts) < 6 else sum(pts) / len(pts) >= GOOD
    if kind == "hands":
        xs = [o for o in day_obs if o.piece_id == details["piece"] and o.mode == "play" and o.hands == "both"]
        return None if not xs else max(o.raw_accuracy for o in xs) >= GOOD
    if kind == "shift":
        n = hit = 0
        for o in day_obs:
            if o.piece_id != details["piece"]:
                continue
            a = P.annot(o.piece_id)
            for ni, ms in o.results:
                if a and 0 <= ni < len(a.shift) and a.shift[ni]:
                    n += 1
                    hit += ms is not None
        return None if n < 4 else hit / n >= GOOD
    if kind == "tempo":
        at = PRESETS.index(details["preset"])
        xs = [o for o in day_obs if o.piece_id == details["piece"] and o.mode == "play" and PRESETS.index(o.preset) >= at]
        return None if not xs else max(o.raw_accuracy for o in xs) >= GOOD
    return None


# ------------------------------------------------------------------------------ running it

def pattern_out(r: sqlite3.Row) -> dict[str, Any]:
    return {"id": r["id"], "kind": r["kind"], "key": r["key"], "details": json.loads(r["details"]),
            "skillIds": json.loads(r["skill_ids"]), "occurrences": r["occurrences"], "firstSeen": r["first_seen"],
            "lastSeen": r["last_seen"], "remediesTried": json.loads(r["remedies_tried"]),
            "goodDays": json.loads(r["good_days"]), "status": r["status"], "resolvedDate": r["resolved_date"]}


def patterns(con: sqlite3.Connection, student_id: str, open_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM error_patterns WHERE student_id = ?" + (" AND status != 'resolved'" if open_only else "") + \
          " ORDER BY first_seen, id"
    return [pattern_out(r) for r in con.execute(sql, (student_id,))]


def run(con: sqlite3.Connection, content: Content, student_id: str, today: date) -> list[dict[str, Any]]:
    """Find the patterns in the last 14 days, update each one's status, and return them all."""
    obs = load_obs(con, student_id, today)
    P = Pieces(con, content)
    existing = {r["key"]: r for r in con.execute("SELECT * FROM error_patterns WHERE student_id = ?", (student_id,))}
    for det in DETECTORS:
        # a resolved pattern is found again only from attempts after it was resolved
        for f in det(obs, P, content):
            r = existing.get(f.key)
            if r is not None and r["status"] == "resolved":
                later = [o for o in obs if o.day > day(r["resolved_date"])]
                if not any(g.key == f.key for g in det(later, P, content)):
                    continue
                con.execute("UPDATE error_patterns SET status = 'active', first_seen = ?, remedies_tried = '[]', good_days = '[]', "
                            "resolved_date = NULL WHERE id = ?", (today.isoformat(), r["id"]))
            if r is None:
                con.execute("INSERT INTO error_patterns (id, student_id, kind, key, details, skill_ids, occurrences, first_seen, last_seen) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            ("pat-" + secrets.token_hex(5), student_id, f.kind, f.key, json.dumps(f.details), json.dumps(sorted(f.skills)),
                             f.occurrences, today.isoformat(), today.isoformat()))
            else:
                con.execute("UPDATE error_patterns SET details = ?, skill_ids = ?, occurrences = ?, last_seen = ? WHERE id = ?",
                            (json.dumps(f.details), json.dumps(sorted(f.skills)), f.occurrences, today.isoformat(), r["id"]))
    by_day: dict[date, list[Obs]] = defaultdict(list)
    for o in obs:
        by_day[o.day].append(o)
    for r in con.execute("SELECT * FROM error_patterns WHERE student_id = ? AND status != 'resolved'", (student_id,)).fetchall():
        first = day(r["first_seen"])
        details = json.loads(r["details"])
        good = set(json.loads(r["good_days"]))
        for d, xs in by_day.items():
            if d > first and good_day(r["kind"], details, xs, P):
                good.add(d.isoformat())
        remedies = json.loads(r["remedies_tried"])
        if len(good) >= 2:
            status, resolved = "resolved", max(good)
        elif (today - day(r["last_seen"])).days > WINDOW_DAYS:
            status, resolved = "resolved", today.isoformat()     # not seen for 14 days: set aside
        elif good:
            status, resolved = "improving", None
        elif len(remedies) >= STUCK_REMEDIES or (today - first).days >= STUCK_DAYS:
            status, resolved = "stuck", None
        else:
            status, resolved = "active", None
        con.execute("UPDATE error_patterns SET good_days = ?, status = ?, resolved_date = ? WHERE id = ?",
                    (json.dumps(sorted(good)), status, resolved, r["id"]))
    return patterns(con, student_id)


def remedy_tried(con: sqlite3.Connection, pattern_id: str, today: date) -> None:
    r = con.execute("SELECT remedies_tried FROM error_patterns WHERE id = ?", (pattern_id,)).fetchone()
    if r is None:
        return
    tried = json.loads(r["remedies_tried"])
    if today.isoformat() not in tried:
        tried.append(today.isoformat())
        con.execute("UPDATE error_patterns SET remedies_tried = ? WHERE id = ?", (json.dumps(tried), pattern_id))


# ------------------------------------------------------------------------------ remedies

def choose(open_patterns: list[dict], states: dict, how_many: int) -> list[dict]:
    """Priority (§8.8): patterns affecting a stuck or Current skill, then the most occurrences,
    then the oldest."""
    def key(p: dict):
        hot = any(sid in states and (states[sid].stuck or states[sid].status == "current") for sid in p["skillIds"])
        return (not hot, -p["occurrences"], p["firstSeen"])
    return sorted(open_patterns, key=key)[:how_many]


def remedy_items(con: sqlite3.Connection, content: Content, student_id: str, states: dict, today: date,
                 target_minutes: float, new_item, piece_seconds) -> list[dict[str, Any]]:
    """Session items for today's remedies (§8.8): one pattern, two from 20 minutes. `new_item` and
    `piece_seconds` are the engine's, passed in to keep the import one way."""
    open_ = [p for p in patterns(con, student_id, open_only=True)]
    if not open_:
        return []
    passed = [sid for sid, st in states.items() if st.counts_passed]
    material = drills.Material.from_skills(content.skill_dicts(passed))
    items: list[dict[str, Any]] = []
    for p in choose(open_, states, 2 if target_minutes >= 20 else 1):
        items += remedy_for(con, content, student_id, p, material, today, new_item, piece_seconds)
    return items


def _drill(con, student_id: str, pattern: dict, kind: str, title: str, nota: dict, extra: dict, today: date) -> dict:
    did = "drill-" + secrets.token_hex(5)
    piece = drills.piece(did, title, nota, {"kind": kind, "patternId": pattern["id"], **extra})
    con.execute("INSERT INTO drills (id, student_id, pattern_id, kind, piece, created) VALUES (?, ?, ?, ?, ?, ?)",
                (did, student_id, pattern["id"], kind, json.dumps(piece), today.isoformat()))
    return piece


def remedy_for(con, content: Content, student_id: str, p: dict, material: drills.Material, today: date,
               new_item, piece_seconds) -> list[dict[str, Any]]:
    d, kind = p["details"], p["kind"]
    tag = {"patternId": p["id"]}

    def drill_item(piece: dict) -> dict:
        beats = piece["notation"]["length"]
        est = 45 + 2 * beats * 60 / piece["notation"]["header"]["tempo"]
        return {**new_item("drill", "Focus", title=piece["title"], est=est), "pieceId": piece["id"], **tag}

    def piece_item(pid: str, **kw) -> dict | None:
        pc = content.pieces.get(pid)
        if pc is None or pc.beyond:
            return None
        bars = kw.pop("bars", None)
        hands = kw.pop("hands", None)
        click = kw.pop("click", None)
        est = 90 if bars else piece_seconds(pc, kw.get("preset"))
        it = new_item("piece", "Focus", piece=pc, est=est, **kw)
        return {**it, **tag, **({"bars": bars} if bars else {}), **({"hands": hands} if hands else {}),
                **({"click": click} if click is not None else {})}

    out: list[dict | None] = []
    if kind == "note":
        title, nota = drills.reading(d["expected"], d["played"], d["hand"], material, seed=int(p["id"].split("-")[-1], 16) & 0xFFFF)
        out.append(drill_item(_drill(con, student_id, p, "reading", title, nota, {}, today)))
    elif kind == "rhythm":
        hand = "R" if "R" in material.ranges or not material.ranges else sorted(material.ranges)[0]
        title, nota, pitch = drills.rhythm(d["figure"], hand, material)
        out.append(drill_item(_drill(con, student_id, p, "rhythm", title, nota, {"anyKey": pitch}, today)))
        if d.get("piece") and d.get("bar"):
            out.append(piece_item(d["piece"], bars=[d["bar"], d["bar"] + 1], click=True))
    elif kind == "hands":
        out.append(piece_item(d["piece"], hands=d["weaker"], preset=d.get("preset")))
        out.append(piece_item(d["piece"], hands="both", preset=SLOWER.get(d.get("preset") or "100", "50")))
    elif kind == "shift":
        out.append(piece_item(d["piece"], bars=d["bars"], preset=None))
    elif kind == "tempo":
        out.append(piece_item(d["piece"], preset=d["slower"]))
        out.append(piece_item(d["piece"], preset=d["preset"]))
    return [x for x in out if x]
