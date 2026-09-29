"""The practice simulator (arch §11.4): simulated students practise for weeks on a generated
branching skill map, driving the real lesson engine day by day, while invariants are checked.

A learner has an ability per skill that grows with each attempt. `rate` is how fast, `days` is
which days they practise, and `hard` skills grow much more slowly and stay below the pass
standard for their first `hard_attempts` tries.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from app import db, engine
from app.content import Content

TRACKS = ["reading", "technique", "rhythm"]
STARS = [(0.96, 5), (0.92, 4.5), (0.86, 4), (0.80, 3.5), (0.74, 3), (0.66, 2.5), (0.58, 2), (0.50, 1.5)]


def stars_for(acc: float) -> float:
    return next((s for lo, s in STARS if acc >= lo), 1.0)


def make_map(n: int = 45, pieces_per_skill: int = 3, free: int = 4, join: int = 9) -> Content:
    """Three tracks side by side; each skill needs the one before it on its track, and every
    `join`th skill joins the tracks (it needs the latest skill on each)."""
    skills, pieces, last = [], [], {}
    for i in range(n):
        track = TRACKS[i % 3]
        pre = [last[track]] if track in last else []
        if i and i % join == 0:
            pre = sorted({*pre, *last.values()})
        sid = f"sim.{i:02d}"
        ids = [f"{sid}.p{k}" for k in range(pieces_per_skill)]
        skills.append({"id": sid, "name": f"Skill {i}", "sequence": 10 * (i + 1), "track": track, "prerequisites": pre,
                       "pieces": ids})
        for pid in ids:
            pieces.append({"id": pid, "title": pid, "skillId": sid, "tempo": 100, "timeSig": "4/4", "measures": 8,
                           "beats": 32, "phrases": 4, "requiredSkills": [sid], "featuredSkills": [sid]})
        last[track] = sid
    for k in range(free):
        pieces.append({"id": f"free.{k}", "title": f"Free {k}", "skillId": None, "tempo": 100, "timeSig": "4/4",
                       "measures": 8, "beats": 32, "phrases": 4, "requiredSkills": [], "featuredSkills": []})
    return Content.from_json({"skills": skills}, {"contentVersion": "sim", "pieces": pieces})


@dataclass
class Learner:
    name: str
    rate: float = 0.25                       # share of the gap to 1.0 closed per attempt
    start: float = 0.55                      # ability on a new skill
    days: set[int] | None = None             # practice days (day numbers); None = every day
    hard: dict[str, float] = field(default_factory=dict)   # skill -> rate multiplier
    hard_attempts: int = 12
    seed: int = 1


@dataclass
class Log:
    """What happened, for the assertions."""
    sessions: dict[int, list[dict]] = field(default_factory=dict)       # day -> the queue as first planned
    played: dict[int, list[dict]] = field(default_factory=dict)         # day -> items as finished
    passes: list[tuple[int, str, float]] = field(default_factory=list)  # (day, skill, stars)
    mastered: list[tuple[int, str]] = field(default_factory=list)
    reviewed: list[tuple[int, str]] = field(default_factory=list)
    stuck_days: dict[str, list[int]] = field(default_factory=dict)
    passed_count: dict[int, int] = field(default_factory=dict)          # day -> skills passed so far
    targets: dict[int, float] = field(default_factory=dict)
    end_of_content: list[int] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


class Sim:
    def __init__(self, path: str, content: Content, learner: Learner, start: date = date(2026, 10, 5)):
        db.migrate(path)
        self.con = db.connect(path)
        self.con.execute("PRAGMA synchronous = OFF")      # a throwaway database: no need to wait for the disk
        self.c, self.l, self.d0 = content, learner, start
        self.rng = random.Random(learner.seed)
        self.ability: dict[str, float] = {}
        self.tries: dict[str, int] = {}
        self.log = Log()
        self.con.execute("INSERT INTO students (id, name, avatar, start_date, created_at) VALUES (?, ?, 'x', ?, ?)",
                         ("s", learner.name, start.isoformat(), start.isoformat()))

    def play(self, pid: str, today: date, item: dict | None, mode: str = "play", preset: str = "100") -> dict:
        p = self.c.pieces[pid]
        sid = p.skill_id
        acc = 0.97
        if sid:
            a = self.ability.setdefault(sid, self.l.start)
            n = self.tries.get(sid, 0)
            self.tries[sid] = n + 1
            rate = self.l.rate * self.l.hard.get(sid, 1.0)
            if sid in self.l.hard and n < self.l.hard_attempts:
                a = min(a, 0.70)                       # below the pass standard for a while
            acc = max(0.2, min(1.0, a + self.rng.uniform(-0.07, 0.05)))
            if preset != "100":
                acc *= 0.9                             # the practice-aid factor of a slower preset
            self.ability[sid] = a + rate * (1 - a)
        st = stars_for(acc)
        tim = max(0.5, st - self.rng.choice([0, 0.5, 1.0]))
        info = engine.AttemptInfo(piece_id=pid, day=today, context="guided", mode=mode, completed=True, accuracy=acc,
                                  accuracy_stars=st, timing_stars=tim, duration_sec=p.play_seconds() * 1.3,
                                  preset=preset, skill_id=item["skillId"] if item else sid,
                                  item_id=item["id"] if item else None, tricky_phrase=1 if st < 4 else None)
        fx = engine.record_attempt(self.con, self.c, "s", info)
        n = (today - self.d0).days
        for s in fx["passed"]:
            self.log.passes.append((n, s, st))
        for s in fx["mastered"]:
            self.log.mastered.append((n, s))
        for s in fx["reviewed"]:
            self.log.reviewed.append((n, s))
        return fx

    def day(self, n: int) -> None:
        today = self.d0 + timedelta(days=n)
        s = engine.get_session(self.con, self.c, "s", today)
        self.log.sessions[n] = [dict(i) for i in s["items"]]
        self.log.targets[n] = s["targetMinutes"]
        if s["endOfContent"]:
            self.log.end_of_content.append(n)
        budget = s["targetMinutes"] * 60 * 1.2
        used = 0.0
        done: list[dict] = []
        for _ in range(60):
            items = engine.load_session(self.con, "s", today)["items"]
            it = next((i for i in items if not i["done"]), None)
            if it is None or used > budget:
                break
            if it["kind"] == "lesson":
                engine.lesson_done(self.con, self.c, "s", it["skillId"], today, it["id"], engine.LESSON_SEC)
                used += engine.LESSON_SEC
            elif it["kind"] == "piece":
                mode = "loop" if it["section"] is not None else "play"
                for _k in range(3):                    # up to three tries, then move on
                    fx = self.play(it["pieceId"], today, it, mode, it["preset"] or "100")
                    used += self.c.pieces[it["pieceId"]].play_seconds() * 1.3
                    if mode == "loop" or fx["passed"] or engine.load_states(self.con, self.c, "s")[it["skillId"]].passed:
                        break
            else:
                states = engine.load_states(self.con, self.c, "s")
                ready = [p for p in self.c.pieces.values() if engine.library_ready(p, states)]
                self.play(self.rng.choice(ready).id, today, it)
                used += 60
            done.append(it)
            self.check(today)
        self.log.played[n] = done

    def check(self, today: date) -> None:
        states = engine.load_states(self.con, self.c, "s")
        for s in self.c.order:
            st = states[s.id]
            if st.status != "locked" and not engine.prerequisites_met(s, states):
                self.log.violations.append(f"{today}: {s.id} is {st.status} before its prerequisites")

    def run(self, days: int) -> Log:
        for n in range(days):
            if self.l.days is None or n in self.l.days:
                self.day(n)
            states = engine.load_states(self.con, self.c, "s")
            self.log.passed_count[n] = sum(1 for st in states.values() if st.passed)
            for sid, st in states.items():
                if st.stuck:
                    self.log.stuck_days.setdefault(sid, []).append(n)
        return self.log
