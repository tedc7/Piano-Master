"""M5 acceptance (arch §12): weeks of simulated practice produce the expected unlocking, stuck
handling, review timing, polish cadence, backlog handling, and session mix (§11.4)."""
from datetime import date, timedelta

import pytest

from app import engine

from simulator import Learner, Sim, make_map

WEEKS = 8
DAYS = WEEKS * 7
ORDER = {"Review": 0, "New": 1, "Tricky spot": 2, "Support": 2, "Polish": 2, "Your pick": 3}


@pytest.fixture(scope="module")
def content():
    return make_map(n=60)


def run(tmp_path, content, learner, days=DAYS):
    return Sim(str(tmp_path / f"{learner.name}.db"), content, learner).run(days)


@pytest.fixture(scope="module")
def fast(tmp_path_factory, content):
    return run(tmp_path_factory.mktemp("fast"), content, Learner("fast", rate=0.2, start=0.55))


@pytest.fixture(scope="module")
def slow(tmp_path_factory, content):
    return run(tmp_path_factory.mktemp("slow"), content, Learner("slow", rate=0.06, start=0.45, seed=2))


@pytest.fixture(scope="module")
def inconsistent(tmp_path_factory, content):
    # practises about 4 days a week, with a 10-day holiday in weeks 4 and 5
    import random
    rng = random.Random(7)
    days = {d for d in range(DAYS) if rng.random() < 0.6 and not 24 <= d < 34}
    return run(tmp_path_factory.mktemp("inc"), content, Learner("inconsistent", rate=0.15, start=0.52, days=days, seed=3))


@pytest.fixture(scope="module")
def hard(tmp_path_factory, content):
    return run(tmp_path_factory.mktemp("hard"), content,
               Learner("hard", rate=0.15, start=0.52, hard={"sim.10": 0.25}, hard_attempts=14, seed=4))


def test_no_rule_is_broken(fast, slow, inconsistent, hard):
    for log in (fast, slow, inconsistent, hard):
        assert not log.violations, log.violations[:3]
        # no skill ever passes below the standard
        assert all(stars >= engine.PASS_STARS for _, _, stars in log.passes)


def test_unlocking_follows_the_pace_of_the_learner(fast, slow, content):
    assert fast.passed_count[DAYS - 1] > slow.passed_count[DAYS - 1] > 3
    assert fast.passed_count[DAYS - 1] >= slow.passed_count[DAYS - 1] + 10 and fast.passed_count[27] >= 30
    # mastery follows passing, a day or more later (2 separate days)
    first_pass = {s: d for d, s, _ in reversed(fast.passes)}
    assert fast.mastered and all(d > first_pass[s] for d, s in fast.mastered)


def test_the_session_mix_follows_the_slot_order(fast, slow, hard):
    for log in (fast, slow, hard):
        for n, items in log.sessions.items():
            ranks = [ORDER[i["reason"]] for i in items]
            assert ranks == sorted(ranks), (n, [i["reason"] for i in items])
            assert items[-1]["kind"] == "pick"
            nothing_new = not any(i["reason"] == "New" for i in items)
            assert sum(1 for i in items if i["reason"] == "Polish") <= engine.MAX_POLISH or nothing_new


def test_reviews_come_on_the_ladder(fast, slow):
    for log in (fast, slow):
        assert log.mastered
        # a mastered skill's first review is due the next day: it shows up in a session within a few days
        for d, s in log.mastered[:5]:
            if d >= DAYS - 3:
                continue
            later = [n for n, items in log.sessions.items() if n > d and any(i["reason"] == "Review" and i["skillId"] == s for i in items)]
            assert later and later[0] - d <= 3, (log is fast, s, d, later[:3])
    assert len(slow.reviewed) >= 10


def test_polish_comes_back_for_passed_skills(slow):
    polished = {i["skillId"] for items in slow.sessions.values() for i in items if i["reason"] == "Polish"}
    assert polished


def test_a_hard_skill_gets_stuck_and_the_rest_keeps_moving(hard):
    assert "sim.10" in hard.stuck_days
    stuck = hard.stuck_days["sim.10"]
    first, last = stuck[0], stuck[-1]
    # other branches keep progressing while it is stuck
    assert hard.passed_count[last] > hard.passed_count[first]
    during = [hard.sessions[n] for n in hard.sessions if first < n <= last]
    assert during
    for items in during:
        # once per session, short and low pressure
        assert [i["reason"] for i in items if i["skillId"] == "sim.10"] == ["Tricky spot"]
        assert any(i["reason"] == "Support" for i in items)
        support = [i["skillId"] for i in items if i["reason"] == "Support"]
        assert len(support) == len(set(support))                           # one piece per supporting skill
    contact = [next(i for i in items if i["skillId"] == "sim.10") for items in during]
    assert any(i["section"] is not None for i in contact) and any(i["section"] is None and i["preset"] for i in contact)
    # and it passes in the end, at the standard
    assert any(s == "sim.10" for _, s, _ in hard.passes)
    assert last < DAYS - 1


def test_the_target_length_adapts(fast, inconsistent):
    assert all(engine.TARGET_MIN <= t <= engine.TARGET_MAX for log in (fast, inconsistent) for t in log.targets.values())
    assert max(fast.targets.values()) > engine.TARGET_START              # steps up after strong weeks
    back = min(n for n in inconsistent.sessions if n >= 34)
    before = max(n for n in inconsistent.sessions if n < 24)
    assert inconsistent.targets[back] < inconsistent.targets[before]    # steps down after the holiday


def test_a_backlog_after_a_break_is_worked_off_over_days(inconsistent):
    back = sorted(n for n in inconsistent.sessions if n >= 34)
    for n in back[:3]:
        items = inconsistent.sessions[n]
        review = sum(i["est"] for i in items if i["reason"] == "Review")
        # the warm-up keeps to about a quarter of the session (plus the one item that crosses it)
        biggest = max((i["est"] for i in items if i["reason"] == "Review"), default=0)
        assert review <= inconsistent.targets[n] * 60 * engine.SLOTS["review"] + biggest


def test_longer_sessions_hold_more_items(tmp_path, content):
    sim = Sim(str(tmp_path / "len.db"), content, Learner("len", rate=0.15, start=0.52))
    sim.run(10)
    states = engine.load_states(sim.con, content, "s")
    d = date(2026, 10, 5) + timedelta(days=11)
    short, _ = engine.Planner(content, states, d, 10).build()
    long, _ = engine.Planner(content, states, d, 30).build()
    assert len(long) > len(short) + 2
    new = lambda items: sum(1 for i in items if i["reason"] == "New")
    assert new(long) > new(short)                                        # more new material, not only repetition


def test_the_end_of_content_keeps_sessions_full(tmp_path):
    small = make_map(n=9)
    log = Sim(str(tmp_path / "end.db"), small, Learner("end", rate=0.45, start=0.7)).run(40)
    assert log.end_of_content
    for n in log.end_of_content:
        assert sum(1 for i in log.sessions[n] if i["kind"] == "piece") >= 3
