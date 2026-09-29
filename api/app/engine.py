"""The lesson engine (arch §8): skill states and unlocking, mastery, spaced review and polish,
stuck handling, today's session queue, and the adaptive session length.

Everything takes `today` (the local calendar day) so the practice simulator can run months of
days in seconds. The numbers are the first version from the architecture, tuned with the
simulator and with the children (§7.10, §11.4). Diagnostics and generated drills (M6) are not
here yet: the Practice slot's remedy position stays empty until then.
"""
from __future__ import annotations

import json
import math
import secrets
import sqlite3
from dataclasses import asdict, dataclass, field, fields
from datetime import date, timedelta
from typing import Any

from .content import Content, Piece, Skill

# 8.1, 8.2
PASS_STARS = 3.0
MASTERY_STEP = 0.3
FREE_STEP = 0.15
MASTERY_LEVEL = 0.86                  # 4 stars
MASTERY_DAYS = 2
TRY_ANOTHER_WAY = 3                   # completed attempts at an item without passing
STUCK_ATTEMPTS = 6
# 8.3
REVIEW_DAYS = [1, 3, 7, 14, 30, 60, 120]
GOOD_REVIEW = 4.0
WEAK_REVIEW = 3.0
POLISH_PASSED_DAYS = 3
POLISH_MASTERED_DAYS = 10
MAX_POLISH = 2
# 8.5, 8.6
SLOTS = {"review": 0.25, "new": 0.40, "practice": 0.20, "reward": 0.15}
STUCK_PRACTICE = 0.30
TARGET_START, TARGET_MIN, TARGET_MAX, TARGET_STEP = 15.0, 10.0, 30.0, 2.5
FREE_DAY_SEC = 5 * 60                 # Free Play makes a practice day from 5 minutes (8.7)
# item time estimates, seconds
LESSON_SEC = 180
PICK_SEC = 150
SECTION_SEC = 90
ITEM_OVERHEAD_SEC = 45
# 8.10
RUNWAY_SKILLS, RUNWAY_DAYS = 15, 21
SLOWER = {"100": "90", "90": "75", "75": "50", "50": "50"}
PRESETS = ("50", "75", "90", "100")


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def day(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


# ------------------------------------------------------------------------------ skill states

@dataclass
class SkillState:
    skill_id: str
    status: str = "locked"
    concept_done: bool = False
    capability_hold: bool = False
    mastery: float | None = None
    best_mastery: float | None = None
    best_accuracy_stars: float | None = None
    best_timing_stars: float | None = None
    attempts_without_pass: int = 0
    first_try_day: str | None = None
    stuck: bool = False
    stuck_since: str | None = None
    high_days: list[str] = field(default_factory=list)
    high_timing: bool = False
    passed_date: str | None = None
    mastered_date: str | None = None
    last_practiced: str | None = None
    last_piece_id: str | None = None
    last_preset: str | None = None
    last_tricky_phrase: int | None = None
    review_step: int | None = None
    next_review_date: str | None = None
    last_review_date: str | None = None
    weak_reviews: int = 0
    refresher: bool = False

    @property
    def passed(self) -> bool:
        return self.status in ("passed", "mastered")

    @property
    def counts_passed(self) -> bool:
        """For unlocking: passed, mastered and capability-held skills count as passed (8.1)."""
        return self.passed or self.capability_hold


BOOL = {"concept_done", "capability_hold", "stuck", "high_timing", "refresher"}
COLUMNS = [f.name for f in fields(SkillState)]


def load_states(con: sqlite3.Connection, content: Content, student_id: str) -> dict[str, SkillState]:
    rows = {r["skill_id"]: r for r in con.execute("SELECT * FROM skill_states WHERE student_id = ?", (student_id,))}
    out = {}
    for s in content.order:
        r = rows.get(s.id)
        if r is None:
            out[s.id] = SkillState(s.id)
            continue
        kw = {c: r[c] for c in COLUMNS}
        for c in BOOL:
            kw[c] = bool(kw[c])
        kw["high_days"] = json.loads(kw["high_days"] or "[]")
        out[s.id] = SkillState(**kw)
    return out


def save_states(con: sqlite3.Connection, student_id: str, states: dict[str, SkillState]) -> None:
    cols = ", ".join(COLUMNS)
    marks = ", ".join("?" for _ in COLUMNS)
    rows = []
    for st in states.values():
        v = asdict(st)
        v["high_days"] = json.dumps(v["high_days"])
        rows.append((student_id, *[int(v[c]) if c in BOOL else v[c] for c in COLUMNS]))
    con.executemany(f"INSERT OR REPLACE INTO skill_states (student_id, {cols}) VALUES (?, {marks})", rows)


def device_caps(profile: dict | None) -> dict[str, bool]:
    """What this setup is known to lack. Unknown capabilities are not held against a skill."""
    p = profile or {}
    caps = {}
    if p.get("hasPedal") is not None:
        caps["pedal"] = bool(p["hasPedal"])
    if p.get("velocitySensitive") is not None:
        caps["velocity"] = bool(p["velocitySensitive"])
    if p.get("keyboardSize"):
        caps["88 keys"] = int(p["keyboardSize"]) >= 88
    return caps


def refresh(content: Content, states: dict[str, SkillState], caps: dict[str, bool] | None = None) -> None:
    """Unlocking (8.1): a skill opens when its prerequisites count as passed, and is Current once
    its concept lesson is done. A skill needing a capability this setup lacks is on hold."""
    caps = caps or {}
    for s in content.order:
        st = states[s.id]
        st.capability_hold = any(caps.get(c) is False for c in s.capabilities) and not st.passed
        if st.status == "locked" and prerequisites_met(s, states) and (st.concept_done or not s.has_lesson):
            st.status = "current"


def prerequisites_met(s: Skill, states: dict[str, SkillState]) -> bool:
    return all(states[p].counts_passed for p in s.prerequisites if p in states)


def lesson_open(s: Skill, states: dict[str, SkillState]) -> bool:
    """The lightbulb opens when the prerequisites are passed (§3 "Teaching concepts")."""
    return prerequisites_met(s, states)


def guided_ready(p: Piece, states: dict[str, SkillState], learning: str | None = None) -> bool:
    """Guided sessions may use pieces that need one Current skill beyond the passed ones (8.1).
    `learning` is a skill whose concept lesson comes just before, in the same session."""
    if p.beyond:
        return False
    beyond = [r for r in p.required if r in states and not states[r].counts_passed]
    return len(beyond) == 0 or (len(beyond) == 1 and (states[beyond[0]].status == "current" or beyond[0] == learning))


def library_ready(p: Piece, states: dict[str, SkillState]) -> bool:
    return not p.beyond and all(states[r].counts_passed for r in p.required if r in states)


# ------------------------------------------------------------------------------ attempts

@dataclass
class AttemptInfo:
    """The parts of an attempt the engine uses (arch §5 Attempt)."""
    piece_id: str
    day: date
    context: str = "free"                 # guided or free
    mode: str = "play"                    # play or loop
    completed: bool = True
    accuracy: float = 0.0                 # after the practice-aid factor, 0..1
    accuracy_stars: float = 0.0
    timing_stars: float | None = None
    duration_sec: float = 0.0
    preset: str = "100"
    skill_id: str | None = None           # the skill the session item was for
    item_id: str | None = None
    tricky_phrase: int | None = None
    factor: float = 1.0                   # the practice-aid factor (7.5)
    note_errors: list[dict] = field(default_factory=list)   # {kind: missed or wrong, bar}


def passes(skill: Skill, a: AttemptInfo) -> bool:
    """A completed attempt of the whole item with 3+ accuracy stars; rhythm skills also need 3+
    timing stars in the same attempt (8.1)."""
    if not a.completed or a.mode != "play" or a.accuracy_stars < PASS_STARS:
        return False
    if skill.track == "rhythm":
        return (a.timing_stars or 0) >= PASS_STARS
    return True


def record_attempt(con: sqlite3.Connection, content: Content, student_id: str, a: AttemptInfo,
                   caps: dict[str, bool] | None = None) -> dict[str, Any]:
    """Update practice time, skill states and today's session after one attempt. Returns what
    changed, for the client: skills passed or mastered, and the session item's new state."""
    add_practice(con, student_id, a.day, a.duration_sec, a.context == "guided")
    effects: dict[str, Any] = {"passed": [], "mastered": [], "reviewed": [], "item": None}
    piece = content.pieces.get(a.piece_id)
    states = load_states(con, content, student_id)
    item = find_item(con, student_id, a.item_id, a.day) if a.item_id else None

    if a.completed and piece:
        assigned = a.skill_id if a.skill_id in content.skills else None
        hit = [assigned] if assigned else []
        hit += [f for f in piece.featured if f in content.skills and f not in hit]
        for sid in hit:
            st, skill = states[sid], content.skills[sid]
            if st.status == "locked":
                continue                      # not reachable yet (a map change); nothing to learn from it
            st.last_piece_id = piece.id
            st.last_preset = a.preset
            st.last_practiced = iso(a.day)
            if a.tricky_phrase is not None and a.mode == "play":
                st.last_tricky_phrase = a.tricky_phrase
            if a.mode != "play":
                continue                      # a section is practice: it neither passes nor moves mastery
            step = MASTERY_STEP if (a.context == "guided" or sid == assigned) else FREE_STEP
            st.mastery = a.accuracy if st.mastery is None else st.mastery + step * (a.accuracy - st.mastery)
            st.best_mastery = max(st.best_mastery or 0, st.mastery)
            st.best_accuracy_stars = max(st.best_accuracy_stars or 0, a.accuracy_stars)
            if a.timing_stars is not None:
                st.best_timing_stars = max(st.best_timing_stars or 0, a.timing_stars)

            if st.status == "current":
                if passes(skill, a):
                    st.status, st.passed_date = "passed", iso(a.day)
                    st.stuck, st.stuck_since, st.attempts_without_pass, st.first_try_day = False, None, 0, None
                    effects["passed"].append(sid)
                else:
                    st.attempts_without_pass += 1
                    st.first_try_day = st.first_try_day or iso(a.day)
                    if (st.attempts_without_pass >= STUCK_ATTEMPTS and st.first_try_day != iso(a.day)
                            and not st.stuck):
                        st.stuck, st.stuck_since = True, iso(a.day)

            if st.status == "passed":
                if st.mastery >= MASTERY_LEVEL:
                    if iso(a.day) not in st.high_days:
                        st.high_days.append(iso(a.day))
                    if (a.timing_stars or 0) >= PASS_STARS:
                        st.high_timing = True
                if len(st.high_days) >= MASTERY_DAYS and (st.high_timing or not skill.needs_timing):
                    st.status, st.mastered_date = "mastered", iso(a.day)
                    st.review_step, st.last_review_date = 0, iso(a.day)
                    st.next_review_date = iso(a.day + timedelta(days=REVIEW_DAYS[0]))
                    st.weak_reviews = 0
                    effects["mastered"].append(sid)
            elif st.status == "mastered" and sid not in effects["mastered"]:
                explicit = item is not None and item.get("reason") == "Review" and item.get("skillId") == sid
                if explicit:
                    review(st, a.accuracy_stars, a.day)
                    effects["reviewed"].append(sid)
                elif a.accuracy_stars >= GOOD_REVIEW and implicit_review_due(st, a.day):
                    review(st, a.accuracy_stars, a.day)      # implicit review (8.4): only ever a good one
                    effects["reviewed"].append(sid)

        if a.mode == "play":
            for sid in piece.required:
                st = states.get(sid)
                if (st is None or sid in hit or st.status != "mastered" or not implicit_review_due(st, a.day)
                        or bars_accuracy(piece, sid, a) < MASTERY_LEVEL):
                    continue
                review(st, GOOD_REVIEW, a.day)        # review credit only; its mastery is not changed (8.4)
                effects["reviewed"].append(sid)
        refresh(content, states, caps)
        save_states(con, student_id, states)
        if effects["passed"]:
            continue_new_slot(con, content, student_id, a.day, states, set(effects["passed"]), keep=a.item_id)

    if item is not None:
        effects["item"] = update_item(con, content, student_id, a, item, states)
    return effects


def bars_accuracy(piece: Piece, skill_id: str, a: AttemptInfo) -> float:
    """How well the bars that use a skill went on their own (skill measures, §6.8), after the
    practice-aid factor: 1 less the missed notes and half the wrong ones, per note in those bars."""
    bars = set(piece.skill_measures.get(skill_id, []))
    expected = sum(piece.bar_notes.get(b, 0) for b in bars)
    if not expected:
        return 0.0
    missed = sum(1 for e in a.note_errors if e.get("bar") in bars and e.get("kind") == "missed")
    wrong = sum(1 for e in a.note_errors if e.get("bar") in bars and e.get("kind") == "wrong")
    return max(0.0, 1 - (missed + wrong / 2) / expected) * a.factor


def review(st: SkillState, stars: float, today: date) -> None:
    """The review ladder (8.3)."""
    step = st.review_step or 0
    if stars >= GOOD_REVIEW:
        step = min(step + 1, len(REVIEW_DAYS) - 1)
        st.weak_reviews = 0
    elif stars >= WEAK_REVIEW:
        st.weak_reviews = 0
    else:
        step = 0
        st.weak_reviews += 1
        if st.mastery is not None:
            st.mastery *= 0.9
        if st.weak_reviews >= 2:
            # back to Passed until it meets the mastery rule again; the concept lesson is offered
            st.status, st.refresher = "passed", True
            st.high_days, st.high_timing = [], False
            st.review_step = st.next_review_date = st.mastered_date = None
            st.last_review_date = iso(today)
            return
    st.review_step = step
    st.last_review_date = iso(today)
    st.next_review_date = iso(today + timedelta(days=REVIEW_DAYS[step]))


def implicit_review_due(st: SkillState, today: date) -> bool:
    """A strong use counts as a review once at least half the current interval has passed, so a
    run of good plays on one day cannot climb the whole ladder."""
    last = day(st.last_review_date)
    if last is None:
        return True
    return (today - last).days >= math.ceil(REVIEW_DAYS[st.review_step or 0] / 2)


def lesson_done(con: sqlite3.Connection, content: Content, student_id: str, skill_id: str, today: date,
                item_id: str | None = None, seconds: float = 0, caps: dict[str, bool] | None = None) -> dict[str, Any]:
    """A concept lesson gone through: the skill becomes Current (8.1); a refresher is cleared."""
    if skill_id not in content.skills:
        raise KeyError(skill_id)
    states = load_states(con, content, student_id)
    st = states[skill_id]
    st.concept_done, st.refresher = True, False
    refresh(content, states, caps)
    save_states(con, student_id, states)
    if seconds:
        add_practice(con, student_id, today, seconds, guided=item_id is not None)
    out: dict[str, Any] = {"status": st.status, "item": None}
    item = find_item(con, student_id, item_id, today) if item_id else None
    if item is not None and item["kind"] == "lesson":
        out["item"] = mark_done(con, student_id, item, None)
    return out


# ------------------------------------------------------------------------------ practice days

def add_practice(con: sqlite3.Connection, student_id: str, d: date, seconds: float, guided: bool) -> None:
    target = current_target(con, student_id)
    con.execute("INSERT OR IGNORE INTO practice_days (student_id, date, target_minutes) VALUES (?, ?, ?)",
                (student_id, iso(d), target))
    col = "guided_sec" if guided else "free_sec"
    con.execute(f"UPDATE practice_days SET {col} = {col} + ? WHERE student_id = ? AND date = ?",
                (max(0.0, seconds or 0), student_id, iso(d)))


def current_target(con: sqlite3.Connection, student_id: str) -> float:
    r = con.execute("SELECT target_minutes FROM students WHERE id = ?", (student_id,)).fetchone()
    return float(r[0]) if r else TARGET_START


def practiced(guided_sec: float, free_sec: float) -> bool:
    """A practice day: any Guided practice, or 5+ minutes of Free Play (8.7)."""
    return guided_sec > 0 or free_sec >= FREE_DAY_SEC


def practice_days(con: sqlite3.Connection, student_id: str, since: date, until: date) -> dict[str, sqlite3.Row]:
    return {r["date"]: r for r in con.execute(
        "SELECT * FROM practice_days WHERE student_id = ? AND date >= ? AND date <= ?", (student_id, iso(since), iso(until)))}


def streak(con: sqlite3.Connection, student_id: str, today: date) -> int:
    """Consecutive calendar days with a practice day, up to today (or yesterday, before today's
    practice)."""
    rows = practice_days(con, student_id, today - timedelta(days=400), today)
    done = {d for d, r in rows.items() if practiced(r["guided_sec"], r["free_sec"])}
    d = today if iso(today) in done else today - timedelta(days=1)
    n = 0
    while iso(d) in done:
        n += 1
        d -= timedelta(days=1)
    return n


def adjust_target(con: sqlite3.Connection, content: Content, student_id: str, today: date) -> float:
    """Today's target length (8.6): down 2.5 minutes for every 3 days missed after a gap, up 2.5
    after a strong week; always between 10 and 30 minutes."""
    r = con.execute("SELECT target_minutes, target_checked, start_date FROM students WHERE id = ?", (student_id,)).fetchone()
    target = float(r["target_minutes"])
    checked = day(r["target_checked"]) or day(r["start_date"]) or today
    rows = con.execute("SELECT * FROM practice_days WHERE student_id = ? AND date < ? ORDER BY date DESC LIMIT 60",
                       (student_id, iso(today))).fetchall()
    last = next((x for x in rows if practiced(x["guided_sec"], x["free_sec"])), None)
    if last is not None:
        missed = (today - day(last["date"])).days - 1
        if missed >= 3:
            # measured from the target on the last practice day, so a longer gap never counts twice
            target = max(TARGET_MIN, float(last["target_minutes"]) - TARGET_STEP * (missed // 3))
            checked = today
    if (today - checked).days >= 7:
        since = today - timedelta(days=7)
        week = [x for x in rows if day(x["date"]) >= since]
        days_practiced = sum(1 for x in week if practiced(x["guided_sec"], x["free_sec"]))
        sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE student_id = ? AND date >= ? AND date < ?",
                               (student_id, iso(since), iso(today))).fetchone()[0]
        completed = sum(1 for x in week if x["session_completed"])
        mastered = con.execute("SELECT COUNT(*) FROM skill_states WHERE student_id = ? AND mastered_date >= ? AND mastered_date < ?",
                               (student_id, iso(since), iso(today))).fetchone()[0]
        if days_practiced >= 5 and sessions and completed / sessions >= 0.8 and mastered >= 1:
            target = min(TARGET_MAX, target + TARGET_STEP)
        checked = today
    con.execute("UPDATE students SET target_minutes = ?, target_checked = ? WHERE id = ?", (target, iso(checked), student_id))
    return target


# ------------------------------------------------------------------------------ sessions

def new_item(kind: str, reason: str, *, skill: Skill | None = None, piece: Piece | None = None, title: str | None = None,
             preset: str | None = None, section: int | None = None, est: float = 0) -> dict[str, Any]:
    return {"id": secrets.token_hex(6), "kind": kind, "reason": reason, "skillId": skill.id if skill else None,
            "pieceId": piece.id if piece else None, "title": title or (piece.title if piece else skill.name if skill else ""),
            "preset": preset, "section": section, "est": round(est), "done": False, "result": None, "tries": 0}


def piece_seconds(p: Piece, preset: str | None = None) -> float:
    """About two plays plus getting ready and the result screen."""
    return ITEM_OVERHEAD_SEC + 2 * p.play_seconds(preset or "100")


class Planner:
    """Builds one day's queue in slot order: warm-up review, new, practice, reward (8.5)."""

    def __init__(self, content: Content, states: dict[str, SkillState], today: date, target_minutes: float):
        self.c, self.states, self.today = content, states, today
        self.total = target_minutes * 60
        self.items: list[dict[str, Any]] = []
        self.used: set[str] = set()
        self.polish = 0

    def piece_for(self, s: Skill, *, library: bool = False) -> Piece | None:
        """A piece for the skill, different from the last one used when there is a choice."""
        st = self.states[s.id]
        ok = [p for p in self.c.pieces_of(s.id) if p.id not in self.used
              and (library_ready(p, self.states) if library else guided_ready(p, self.states, learning=s.id))]
        if not ok:
            return None
        fresh = [p for p in ok if p.id != st.last_piece_id]
        return (fresh or ok)[0]

    def add(self, item: dict[str, Any]) -> float:
        self.items.append(item)
        if item["pieceId"]:
            self.used.add(item["pieceId"])
        return item["est"]

    def add_piece(self, reason: str, s: Skill, p: Piece, **kw) -> float:
        est = SECTION_SEC if kw.get("section") is not None else piece_seconds(p, kw.get("preset"))
        return self.add(new_item("piece", reason, skill=s, piece=p, est=est, **kw))

    def build(self) -> tuple[list[dict[str, Any]], bool]:
        c, states, today = self.c, self.states, self.today
        order = [s for s in c.order if not states[s.id].capability_hold]
        stuck = [s for s in order if states[s.id].status == "current" and states[s.id].stuck]
        share = dict(SLOTS)
        if stuck:
            share["new"] -= STUCK_PRACTICE - share["practice"]
            share["practice"] = STUCK_PRACTICE

        # warm-up: due reviews, most overdue and weakest first; refreshers after two weak reviews
        budget = share["review"] * self.total
        spent = 0.0
        for s in order:
            if states[s.id].refresher and spent < budget:
                spent += self.add(new_item("lesson", "Review", skill=s, title=s.name, est=LESSON_SEC))
        due = [s for s in order if states[s.id].status == "mastered" and day(states[s.id].next_review_date) and
               day(states[s.id].next_review_date) <= today]
        due.sort(key=lambda s: (-(today - day(states[s.id].next_review_date)).days, states[s.id].mastery or 0))
        for s in due:
            if spent >= budget:
                break
            p = self.piece_for(s)
            if p:
                spent += self.add_piece("Review", s, p)

        # new: Current skills and open lightbulbs, lowest sequence first; a stuck skill waits in Practice
        budget = share["new"] * self.total + max(0.0, share["review"] * self.total - spent)
        spent = 0.0
        learning = [s for s in order if not states[s.id].stuck and (
            states[s.id].status == "current" or
            (states[s.id].status == "locked" and s.has_lesson and not states[s.id].concept_done and lesson_open(s, states)))]
        nothing_new = not learning
        end_of_content = nothing_new and not stuck
        for s in learning:
            if spent >= budget:
                break
            spent += self.add_new(s)
        # a longer session has room for more of the new skills' pieces
        added = True
        while added and spent < budget * 0.8:
            added = False
            for s in learning:
                if spent >= budget * 0.8:
                    break
                if any(i["skillId"] == s.id for i in self.items):
                    p = self.piece_for(s)
                    if p:
                        spent += self.add_piece("New", s, p)
                        added = True
        left_over = max(0.0, budget - spent)

        # practice: (diagnostic remedy, M6), support for a stuck skill, polish, a tricky spot, polish of mastered skills
        budget = share["practice"] * self.total + left_over
        spent = 0.0
        for s in stuck:
            st = states[s.id]
            p = next((x for x in c.pieces_of(s.id) if guided_ready(x, states)), None)
            if p:
                # short, low-pressure contact: the tricky section one day, the whole piece one preset
                # slower the next (a section alone can never pass the skill)
                since = (today - (day(st.stuck_since) or today)).days
                if st.last_tricky_phrase is not None and st.last_tricky_phrase < p.phrases and since % 2 == 0:
                    spent += self.add_piece("Tricky spot", s, p, section=st.last_tricky_phrase)
                else:
                    spent += self.add_piece("Tricky spot", s, p, preset=SLOWER.get(st.last_preset or "90", "50"))
            for sp in self.support(s):
                if spent >= budget:
                    break
                spent += self.add_piece("Support", c.skills[sp.skill_id] if sp.skill_id in c.skills else s, sp)
        # with nothing new to learn, the New slot's time goes to polish (8.10)
        cap = 10 ** 6 if nothing_new else MAX_POLISH
        polish = sorted((s for s in order if states[s.id].status == "passed" and self.polish_due(s, POLISH_PASSED_DAYS)),
                        key=lambda s: states[s.id].mastery or 0)
        for s in polish:
            if spent >= budget or self.polish >= cap:
                break
            p = self.piece_for(s)
            if p:
                spent += self.add_piece("Polish", s, p)
                self.polish += 1
        for s in order:
            st = states[s.id]
            if spent >= budget:
                break
            if st.status == "current" and not st.stuck and st.last_tricky_phrase is not None:
                p = next((x for x in c.pieces_of(s.id) if x.id == st.last_piece_id), None)
                if p and st.last_tricky_phrase < p.phrases and not any(i["pieceId"] == p.id and i["section"] is not None for i in self.items):
                    spent += self.add(new_item("piece", "Tricky spot", skill=s, piece=p, section=st.last_tricky_phrase,
                                               est=SECTION_SEC))
        mastered = sorted((s for s in order if states[s.id].status == "mastered" and (states[s.id].best_accuracy_stars or 0) < 5
                           and self.polish_due(s, POLISH_MASTERED_DAYS)), key=lambda s: states[s.id].mastery or 0)
        for s in mastered:
            if spent >= budget or self.polish >= cap:
                break
            p = self.piece_for(s)
            if p:
                spent += self.add_piece("Polish", s, p)
                self.polish += 1
        if nothing_new:
            # the New slot's time goes to polish, repertoire and review (8.10)
            for s in order:
                if spent >= budget:
                    break
                if states[s.id].passed and not any(i["skillId"] == s.id for i in self.items):
                    p = self.piece_for(s, library=True)
                    if p:
                        spent += self.add_piece("Polish", s, p)

        # reward: the student's choice from the library, with any time still unplanned
        spare = max(0.0, self.total * (1 - share["reward"]) - sum(i["est"] for i in self.items))
        picks = max(1, min(4, round((share["reward"] * self.total + spare) / (PICK_SEC * 1.5))))
        for _ in range(picks):
            self.add(new_item("pick", "Your pick", title="Any song you like", est=PICK_SEC))
        return self.items, end_of_content

    def add_new(self, s: Skill) -> float:
        st = self.states[s.id]
        spent = 0.0
        if s.has_lesson and not st.concept_done:
            spent += self.add(new_item("lesson", "New", skill=s, title=s.name, est=LESSON_SEC))
        p = self.piece_for(s)
        if p:
            spent += self.add_piece("New", s, p)
        return spent

    def polish_due(self, s: Skill, every: int) -> bool:
        if any(i["skillId"] == s.id for i in self.items):
            return False
        last = day(self.states[s.id].last_practiced)
        return last is None or (self.today - last).days >= every

    def support(self, stuck: Skill) -> list[Piece]:
        """Guided-ready pieces that exercise what the stuck skill builds on (its prerequisites and
        skills on the same track) without needing the stuck skill itself (8.1)."""
        near = set(stuck.prerequisites) | {s.id for s in self.c.order if s.track == stuck.track and s.id != stuck.id}
        out = [p for p in self.c.pieces.values() if p.id not in self.used and stuck.id not in p.required
               and set(p.featured) & near and guided_ready(p, self.states)
               and all(self.states[f].status != "locked" for f in p.featured if f in self.states)]
        out.sort(key=lambda p: self.states[p.featured[0]].last_practiced or "")
        one_each, seen = [], set()
        for p in out:
            if p.featured[0] not in seen:
                seen.add(p.featured[0])
                one_each.append(p)
        return one_each


def load_session(con: sqlite3.Connection, student_id: str, d: date) -> dict[str, Any] | None:
    r = con.execute("SELECT * FROM sessions WHERE student_id = ? AND date = ?", (student_id, iso(d))).fetchone()
    if not r:
        return None
    return {"date": r["date"], "targetMinutes": r["target_minutes"], "items": json.loads(r["queue"]),
            "endOfContent": bool(r["end_of_content"])}


def save_queue(con: sqlite3.Connection, student_id: str, d: str, items: list[dict[str, Any]]) -> None:
    con.execute("UPDATE sessions SET queue = ?, updated_at = datetime('now') WHERE student_id = ? AND date = ?",
                (json.dumps(items), student_id, d))
    done = bool(items) and all(i["done"] for i in items)
    con.execute("UPDATE practice_days SET session_completed = ? WHERE student_id = ? AND date = ?", (int(done), student_id, d))


def get_session(con: sqlite3.Connection, content: Content, student_id: str, today: date,
                caps: dict[str, bool] | None = None) -> dict[str, Any]:
    """Today's session: built on the first request of the day, then resumed on any device (8.5)."""
    s = load_session(con, student_id, today)
    if s is not None:
        return s
    target = adjust_target(con, content, student_id, today)
    states = load_states(con, content, student_id)
    refresh(content, states, caps)
    save_states(con, student_id, states)
    items, end = Planner(content, states, today, target).build()
    con.execute("INSERT INTO sessions (student_id, date, target_minutes, queue, end_of_content, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (student_id, iso(today), target, json.dumps(items), int(end)))
    con.execute("INSERT OR IGNORE INTO practice_days (student_id, date, target_minutes) VALUES (?, ?, ?)",
                (student_id, iso(today), target))
    con.execute("UPDATE practice_days SET target_minutes = ? WHERE student_id = ? AND date = ?", (target, student_id, iso(today)))
    return load_session(con, student_id, today)


def find_item(con: sqlite3.Connection, student_id: str, item_id: str | None, d: date) -> dict[str, Any] | None:
    """The session item, today's or (an outbox resend after midnight) the day before."""
    for when in (d, d - timedelta(days=1)):
        s = load_session(con, student_id, when)
        if s:
            for it in s["items"]:
                if it["id"] == item_id:
                    return {**it, "_date": s["date"]}
    return None


def mark_done(con: sqlite3.Connection, student_id: str, item: dict[str, Any], result: dict | None,
              tries: int | None = None) -> dict[str, Any]:
    s = load_session(con, student_id, date.fromisoformat(item["_date"]))
    for it in s["items"]:
        if it["id"] != item["id"]:
            continue
        it["done"] = True
        if result is not None:
            old = it.get("result")
            if not old or (result.get("accuracyStars") or 0) >= (old.get("accuracyStars") or 0):
                it["result"] = result
        if tries is not None:
            it["tries"] = tries
        save_queue(con, student_id, s["date"], s["items"])
        return it
    return item


def update_item(con: sqlite3.Connection, content: Content, student_id: str, a: AttemptInfo, item: dict[str, Any],
                states: dict[str, SkillState]) -> dict[str, Any] | None:
    """An attempt made for a session item checks it off: a song played to the end, or one time
    round the item's section. Tries count toward "Try it another way" while the skill is not passed."""
    if not a.completed:
        return None
    if item["kind"] == "piece" and item.get("section") is not None:
        if a.mode != "loop":
            return None
    elif a.mode != "play":
        return None
    piece = content.pieces.get(a.piece_id)
    result = {"accuracyStars": a.accuracy_stars, "timingStars": a.timing_stars}
    if item["kind"] == "pick" and piece:
        result["title"] = piece.title
    tries = item.get("tries", 0)
    sid = item.get("skillId")
    if sid in states and not states[sid].passed:
        tries += 1
    return mark_done(con, student_id, item, result, tries)


def continue_new_slot(con: sqlite3.Connection, content: Content, student_id: str, d: date,
                      states: dict[str, SkillState], passed: set[str], keep: str | None = None) -> None:
    """When a Current skill passes mid-session, the New slot continues with the next available
    skill (8.1): its remaining New items (other than the one just played) are replaced."""
    s = load_session(con, student_id, d)
    if not s:
        return
    items = s["items"]
    stale = [i for i, it in enumerate(items) if not it["done"] and it["reason"] == "New" and it["skillId"] in passed
             and it["id"] != keep]
    if not stale:
        return
    queued = {it["skillId"] for it in items}
    p = Planner(content, states, d, s["targetMinutes"])
    p.used = {it["pieceId"] for it in items if it["pieceId"]}
    for s2 in content.order:
        st = states[s2.id]
        if s2.id in queued or st.capability_hold or st.stuck:
            continue
        if st.status == "current" or (st.status == "locked" and s2.has_lesson and not st.concept_done and lesson_open(s2, states)):
            p.add_new(s2)
            break
    # no longer than what it replaces, so a quick learner's session still ends near its target
    room, fresh = sum(items[i]["est"] for i in stale), []
    for it in p.items:
        if fresh and sum(x["est"] for x in fresh) + it["est"] > room * 1.25:
            break
        fresh.append(it)
    at = stale[0]
    rest = [it for i, it in enumerate(items) if i not in stale]
    rest[at:at] = fresh
    save_queue(con, student_id, s["date"], rest)


def skip_item(con: sqlite3.Connection, student_id: str, item_id: str, today: date) -> dict[str, Any] | None:
    """Skip once: the item moves to the end of the queue (8.5)."""
    s = load_session(con, student_id, today)
    if not s:
        return None
    items = s["items"]
    i = next((k for k, it in enumerate(items) if it["id"] == item_id and not it["done"]), None)
    if i is None:
        return s
    it = items.pop(i)
    it["skipped"] = True
    items.append(it)
    save_queue(con, student_id, s["date"], items)
    return load_session(con, student_id, today)


# ------------------------------------------------------------------------------ reports

def skills_out(content: Content, states: dict[str, SkillState], today: date, session: dict | None = None) -> list[dict]:
    in_session = {it["skillId"] for it in (session or {}).get("items", []) if not it["done"]}
    out = []
    for s in content.order:
        st = states[s.id]
        out.append({
            "skillId": s.id, "status": st.status, "lessonOpen": lesson_open(s, states), "conceptDone": st.concept_done,
            "hold": st.capability_hold, "mastery": st.mastery, "bestMastery": st.best_mastery,
            "accuracyStars": st.best_accuracy_stars, "timingStars": st.best_timing_stars, "stuck": st.stuck,
            "due": st.status == "mastered" and bool(st.next_review_date) and day(st.next_review_date) <= today,
            "today": s.id in in_session, "attemptsWithoutPass": st.attempts_without_pass,
            "tryAnotherWay": st.status == "current" and st.attempts_without_pass >= TRY_ANOTHER_WAY,
            "refresher": st.refresher, "nextReview": st.next_review_date,
        })
    return out


def runway(con: sqlite3.Connection, content: Content, student_id: str, states: dict[str, SkillState], today: date) -> dict:
    """Skills left before the end of the authored content, and an estimate at the current pace (8.10)."""
    remaining = [s for s in content.order if not states[s.id].passed and not states[s.id].capability_hold]
    since = today - timedelta(days=28)
    recent = sum(1 for st in states.values() if st.passed_date and day(st.passed_date) >= since)
    per_day = recent / 28
    days_left = round(len(remaining) / per_day) if per_day else None
    return {"remaining": len(remaining), "passedLast28Days": recent, "daysLeft": days_left,
            "alert": len(remaining) < RUNWAY_SKILLS or (days_left is not None and days_left < RUNWAY_DAYS),
            "heldBy": sorted({c for s in content.order if states[s.id].capability_hold for c in s.capabilities})}


def day_out(con: sqlite3.Connection, student_id: str, today: date, session: dict | None) -> dict:
    r = con.execute("SELECT * FROM practice_days WHERE student_id = ? AND date = ?", (student_id, iso(today))).fetchone()
    items = (session or {}).get("items", [])
    return {"date": iso(today), "guidedSec": r["guided_sec"] if r else 0, "freeSec": r["free_sec"] if r else 0,
            "targetMinutes": (session or {}).get("targetMinutes") or current_target(con, student_id),
            "streak": streak(con, student_id, today), "completed": bool(items) and all(i["done"] for i in items)}
