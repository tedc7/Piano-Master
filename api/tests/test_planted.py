"""M6 acceptance (arch §11.4, §12): simulated students with planted error patterns practise for
three weeks through the real lesson engine. Every note of every play is simulated, stored like a
real attempt, and read back by Diagnostics. Each planted pattern must be found, get the right
remedy in the Practice slot, and resolve once the remedies work, or be marked stuck when they
never do.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

import pytest

from app import db, diagnostics, engine
from app.content import Content
from test_diagnostics import DUET, PIECES, SKILLS, TUNE_NOTA

D0 = date(2026, 10, 5)
FADE_AFTER = 3            # remedies done before a fading weakness goes away


@dataclass
class Learner:
    kind: str                         # the planted pattern
    fades: bool = True
    seed: int = 7
    remedies: int = 0
    log: dict = field(default_factory=dict)

    @property
    def weak(self) -> bool:
        return not self.fades or self.remedies < FADE_AFTER


def content() -> Content:
    skills = [{**s, "conceptLesson": False} for s in SKILLS]
    c = Content.from_json({"skills": skills}, {"contentVersion": "p", "pieces": PIECES})
    c.notations = {"tune": TUNE_NOTA, "duet": DUET}
    return c


class World:
    def __init__(self, path: str, learner: Learner):
        db.migrate(path)
        self.con = db.connect(path)
        self.con.execute("PRAGMA synchronous = OFF")
        self.con.execute("INSERT INTO students (id, name, avatar, start_date, created_at) VALUES ('s', 'x', 'x', ?, ?)", (D0.isoformat(),) * 2)
        self.con.execute("INSERT INTO devices (id, created_at, last_seen) VALUES ('dev', 'x', 'x')")
        self.c, self.l = content(), learner
        self.rng = random.Random(learner.seed)
        self.n = 0
        self.shift_notes = {i for i, s in enumerate(diagnostics.annotate(TUNE_NOTA).shift) if s}
        states = engine.load_states(self.con, self.c, "s")
        for sid in ("s.r", "s.l"):
            states[sid].status, states[sid].concept_done = "passed", True
        states["s.t"].status, states["s.t"].concept_done = "current", True
        engine.save_states(self.con, "s", states)

    # --------------------------------------------------------------- one play, note by note
    def notes_for(self, pid: str, nota: dict, hands: str, preset: str) -> tuple[list, list]:
        weak, kind, rng = self.l.weak, self.l.kind, self.rng
        res, wrongs = [], []
        for i, n in enumerate(nota["notes"]):
            if hands != "both" and n["hand"] != hands:
                continue
            miss = rng.random() < 0.03
            ms = rng.gauss(0, 30)
            if weak and kind == "note" and n["pitch"] == 65 and rng.random() < 0.6:
                miss = True
                wrongs.append({"kind": "wrong", "pitch": 67, "expected": 65, "hand": n["hand"], "bar": 1})
            if weak and kind == "rhythm" and n["duration"] == 0.5:
                ms = rng.gauss(-130, 25)
            if weak and kind == "shift" and pid == "tune" and i in self.shift_notes and rng.random() < 0.5:
                miss = True
            if weak and kind == "hands" and pid == "duet" and hands == "both" and rng.random() < 0.35:
                miss = True
            if weak and kind == "tempo" and pid == "tune" and preset in ("90", "100") and rng.random() < 0.3:
                miss = True
            res.append([i, None if miss else round(ms, 1)])
        return res, wrongs

    def play(self, pid: str, today: date, item: dict | None, preset: str = "100", hands: str = "both", mode: str = "play") -> dict:
        if pid.startswith("drill-"):
            nota = json.loads(self.con.execute("SELECT piece FROM drills WHERE id = ?", (pid,)).fetchone()["piece"])["notation"]
        else:
            nota = self.c.notation(pid)
        res, wrongs = self.notes_for(pid, nota, hands, preset)
        raw = sum(1 for _, m in res if m is not None) / max(1, len(res))
        factor = {"100": 1, "90": 0.92, "75": 0.86, "50": 0.78}[preset] * (0.85 if hands != "both" and pid == "duet" else 1)
        acc = raw * factor
        self.n += 1
        self.con.execute(
            "INSERT INTO attempts (id, device_id, student_id, piece_id, arrangement_id, context, mode, completed, started_at, received_at, "
            "tempo_preset, conditions, conditions_factor, raw_accuracy, accuracy, accuracy_stars, per_phrase_errors, note_errors, evaluation, "
            "raw_events, passes, skill_id, item_id, note_results) "
            "VALUES (?, 'dev', 's', ?, ?, 'guided', ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, '{}', '[]', '[]', ?, ?, ?)",
            (f"a{self.n}", pid, pid, mode, f"{today.isoformat()}T12:{self.n % 60:02d}:00", today.isoformat(), preset,
             json.dumps({"hands": hands}), factor, raw, acc, engine.stars(acc), json.dumps(wrongs),
             item.get("skillId") if item else None, item["id"] if item else None, json.dumps(res)))
        info = engine.AttemptInfo(piece_id=pid, day=today, context="guided", mode=mode, accuracy=acc, accuracy_stars=engine.stars(acc),
                                  timing_stars=4.0, duration_sec=60, preset=preset, skill_id=item.get("skillId") if item else None,
                                  item_id=item["id"] if item else None, factor=factor)
        return engine.record_attempt(self.con, self.c, "s", info)

    # --------------------------------------------------------------- a day
    def day(self, k: int) -> None:
        today = D0 + timedelta(days=k)
        s = engine.get_session(self.con, self.c, "s", today)
        focus = [i for i in s["items"] if i["reason"] == "Focus"]
        self.l.log[k] = {"focus": focus, "patterns": diagnostics.patterns(self.con, "s")}
        for it in s["items"]:
            if it["reason"] == "Focus":
                mode = "loop" if it.get("bars") else "play"
                self.play(it["pieceId"], today, it, it["preset"] or "100", it.get("hands") or "both", mode)
            elif it["kind"] == "piece":
                self.play(it["pieceId"], today, it, it["preset"] or "100", it.get("hands") or "both")
            elif it["kind"] == "pick":
                # the student's own choices: the pieces the planted pattern shows up in
                kind = self.l.kind
                if kind == "hands":
                    for h in ("R", "L", "both"):
                        self.play("duet", today, it, "100", h)
                elif kind == "tempo":
                    for pr in ("75", "90"):
                        self.play("tune", today, it, pr)
                else:
                    self.play("tune", today, it)
                    self.play("tune", today, None)
        if focus:
            self.l.remedies += 1            # a day's remedy done: a fading weakness eases after a few

    def run(self, days: int = 21) -> Learner:
        for k in range(days):
            self.day(k)
        return self.l


def first_day(l: Learner, kind: str, pred=lambda it: True) -> int | None:
    return next((k for k, v in sorted(l.log.items()) if any(pred(i) for i in v["focus"])
                 and any(p["kind"] == kind for p in v["patterns"])), None)


REMEDY = {
    "note": lambda i: i["kind"] == "drill" and i["title"].startswith("Reading game"),
    "rhythm": lambda i: i["kind"] == "drill" and i["title"].startswith("Rhythm tap"),
    "hands": lambda i: i.get("hands") in ("R", "L"),
    "shift": lambda i: bool(i.get("bars")) and i["pieceId"] == "tune",
    "tempo": lambda i: i["pieceId"] == "tune" and i["preset"] == "75",
}


@pytest.mark.parametrize("kind", ["note", "rhythm", "hands", "shift", "tempo"])
def test_a_planted_pattern_is_found_remedied_and_resolved(tmp_path, kind):
    l = World(str(tmp_path / "p.db"), Learner(kind)).run()
    k = first_day(l, kind, REMEDY[kind])
    assert k is not None and k <= 4, f"{kind}: first remedy on day {k}"
    final = {p["kind"]: p for p in l.log[max(l.log)]["patterns"]}
    assert final[kind]["status"] == "resolved", final[kind]
    assert len(final[kind]["remediesTried"]) >= 1
    # nothing else was found in a learner who has only this weakness
    others = [p for p in l.log[max(l.log)]["patterns"] if p["kind"] != kind]
    assert not others, others


def test_a_pattern_that_remedies_never_fix_is_marked_stuck(tmp_path):
    l = World(str(tmp_path / "p.db"), Learner("note", fades=False)).run()
    final = {p["kind"]: p for p in l.log[max(l.log)]["patterns"]}
    assert final["note"]["status"] == "stuck" and len(final["note"]["remediesTried"]) >= diagnostics.STUCK_REMEDIES
    # it keeps its remedy in the session, and the parent's report will show it
    assert l.log[max(l.log)]["focus"]
