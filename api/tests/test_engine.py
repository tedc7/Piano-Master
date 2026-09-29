"""M5 lesson engine rules (arch §8), driven directly with explicit days."""
from datetime import date, timedelta

import pytest

from app import db, engine
from app.content import Content
from app.engine import AttemptInfo

from conftest import PIECES, SKILLS, piece

D0 = date(2026, 10, 5)            # a Monday


@pytest.fixture()
def con(tmp_path):
    path = str(tmp_path / "e.db")
    db.migrate(path)
    c = db.connect(path)
    c.execute("INSERT INTO students (id, name, avatar, start_date, created_at) VALUES ('s1', 'Ada', 'x', ?, ?)",
              (D0.isoformat(), D0.isoformat()))
    yield c
    c.close()


@pytest.fixture()
def content():
    return Content.from_json({"skills": SKILLS}, {"contentVersion": "t", "pieces": PIECES})


def play(con, content, pid, d, stars=3.0, timing=3.0, acc=None, context="guided", item=None, skill=None, mode="play",
         completed=True, tricky=None, preset="100"):
    acc = acc if acc is not None else stars / 5 * 0.95 + 0.05
    a = AttemptInfo(piece_id=pid, day=d, context=context, mode=mode, completed=completed, accuracy=acc,
                    accuracy_stars=stars, timing_stars=timing, duration_sec=60, skill_id=skill,
                    item_id=item["id"] if item else None, tricky_phrase=tricky, preset=preset)
    return engine.record_attempt(con, content, "s1", a)


def states(con, content):
    return engine.load_states(con, content, "s1")


def learn(con, content, sid, d):
    engine.lesson_done(con, content, "s1", sid, d)


def test_a_new_student_starts_with_the_first_lightbulb(con, content):
    s = engine.get_session(con, content, "s1", D0)
    kinds = [(i["kind"], i["reason"], i["skillId"]) for i in s["items"]]
    assert kinds[:2] == [("lesson", "New", "t.a"), ("piece", "New", "t.a")] and kinds[-1][0] == "pick"
    st = states(con, content)
    assert st["t.a"].status == "locked"
    out = {x["skillId"]: x for x in engine.skills_out(content, st, D0)}
    assert out["t.a"]["lessonOpen"] and not out["t.b"]["lessonOpen"]
    assert engine.lesson_done(con, content, "s1", "t.a", D0)["status"] == "current"
    # the same day's session is resumed, not rebuilt
    assert engine.get_session(con, content, "s1", D0)["items"][0]["id"] == s["items"][0]["id"]


def test_passing_opens_the_branches_and_needs_three_stars(con, content):
    learn(con, content, "t.a", D0)
    play(con, content, "pa1", D0, stars=2.5)
    assert states(con, content)["t.a"].status == "current"
    fx = play(con, content, "pa1", D0, stars=3.0, timing=1.0)
    st = states(con, content)
    assert fx["passed"] == ["t.a"] and st["t.a"].status == "passed" and st["t.a"].attempts_without_pass == 0
    out = {x["skillId"]: x for x in engine.skills_out(content, st, D0)}
    assert out["t.b"]["lessonOpen"] and out["t.c"]["lessonOpen"] and not out["t.d"]["lessonOpen"]   # d also needs c


def test_a_section_or_an_unfinished_play_never_passes(con, content):
    learn(con, content, "t.a", D0)
    play(con, content, "pa1", D0, stars=5, mode="loop")
    play(con, content, "pa1", D0, stars=5, completed=False)
    assert states(con, content)["t.a"].status == "current"


def test_rhythm_skills_also_need_three_timing_stars(con, content):
    for sid in ("t.a", "t.b"):
        learn(con, content, sid, D0)
        play(con, content, f"p{sid[-1]}1", D0, stars=4)
    learn(con, content, "t.e", D0)
    play(con, content, "pe1", D0, stars=5, timing=2.5)
    assert states(con, content)["t.e"].status == "current"
    play(con, content, "pe1", D0, stars=3, timing=3)
    assert states(con, content)["t.e"].status == "passed"


def test_mastery_is_a_running_value_with_best_so_far(con, content):
    learn(con, content, "t.a", D0)
    play(con, content, "pa1", D0, acc=0.6, stars=3)
    assert states(con, content)["t.a"].mastery == pytest.approx(0.6)       # the first attempt sets it
    play(con, content, "pa1", D0, acc=1.0, stars=5)
    st = states(con, content)["t.a"]
    assert st.mastery == pytest.approx(0.6 + 0.3 * 0.4) and st.best_accuracy_stars == 5
    play(con, content, "pa1", D0, acc=0.2, stars=1)
    st = states(con, content)["t.a"]
    assert st.mastery < 0.72 and st.best_mastery == pytest.approx(0.72) and st.best_accuracy_stars == 5
    # Free Play: half the step, for the song's featured skills
    before = st.mastery
    play(con, content, "pa2", D0, acc=1.0, stars=5, context="free")
    assert states(con, content)["t.a"].mastery == pytest.approx(before + 0.15 * (1 - before))


def test_mastered_needs_two_days_at_four_stars_and_timing(con, content):
    learn(con, content, "t.a", D0)
    play(con, content, "pa1", D0, acc=0.95, stars=5, timing=2)
    play(con, content, "pa1", D0, acc=0.95, stars=5, timing=2)
    assert states(con, content)["t.a"].status == "passed"                  # one day only
    play(con, content, "pa1", D0 + timedelta(days=1), acc=0.95, stars=5, timing=2.5)
    assert states(con, content)["t.a"].status == "passed"                  # no attempt with 3+ timing stars yet
    fx = play(con, content, "pa1", D0 + timedelta(days=1), acc=0.95, stars=5, timing=3.5)
    st = states(con, content)["t.a"]
    assert fx["mastered"] == ["t.a"] and st.status == "mastered"
    assert st.review_step == 0 and st.next_review_date == (D0 + timedelta(days=2)).isoformat()


def master(con, content, sid="t.a", pid="pa1", d=D0):
    learn(con, content, sid, d)
    play(con, content, pid, d, acc=0.95, stars=5, timing=4)
    play(con, content, pid, d + timedelta(days=1), acc=0.95, stars=5, timing=4)
    assert states(con, content)[sid].status == "mastered"
    return d + timedelta(days=1)


def review_item(con, content, d, sid):
    s = engine.get_session(con, content, "s1", d)
    return next(i for i in s["items"] if i["reason"] == "Review" and i["skillId"] == sid)


def test_the_review_ladder(con, content):
    d = master(con, content)                       # mastered on D0+1: review due D0+2
    d += timedelta(days=1)
    it = review_item(con, content, d, "t.a")
    play(con, content, it["pieceId"], d, stars=4.5, item=it, skill="t.a")
    st = states(con, content)["t.a"]
    assert st.review_step == 1 and st.next_review_date == (d + timedelta(days=3)).isoformat()
    d += timedelta(days=3)
    it = review_item(con, content, d, "t.a")
    play(con, content, it["pieceId"], d, stars=3.5, item=it, skill="t.a")   # OK: same interval
    st = states(con, content)["t.a"]
    assert st.review_step == 1 and st.next_review_date == (d + timedelta(days=3)).isoformat()
    d += timedelta(days=3)
    it = review_item(con, content, d, "t.a")
    m = states(con, content)["t.a"].mastery
    play(con, content, it["pieceId"], d, stars=2.5, acc=m, item=it, skill="t.a")   # weak: back to 1 day, mastery -10%
    st = states(con, content)["t.a"]
    assert st.review_step == 0 and st.next_review_date == (d + timedelta(days=1)).isoformat()
    assert st.mastery == pytest.approx(m * 0.9) and st.status == "mastered"
    d += timedelta(days=1)
    it = review_item(con, content, d, "t.a")
    play(con, content, it["pieceId"], d, stars=2, acc=0.5, item=it, skill="t.a")   # two weak in a row
    st = states(con, content)["t.a"]
    assert st.status == "passed" and st.refresher and st.next_review_date is None and st.best_accuracy_stars == 5
    s = engine.get_session(con, content, "s1", d + timedelta(days=1))
    assert s["items"][0]["kind"] == "lesson" and s["items"][0]["reason"] == "Review" and s["items"][0]["skillId"] == "t.a"


def test_a_strong_play_counts_as_an_implicit_review(con, content):
    d = master(con, content)
    play(con, content, "pa2", d, stars=5, context="free")                    # the same day: too soon
    assert states(con, content)["t.a"].review_step == 0
    play(con, content, "pa2", d + timedelta(days=1), stars=4, context="free")
    assert states(con, content)["t.a"].review_step == 1
    play(con, content, "pa2", d + timedelta(days=2), stars=3.5, context="free")   # not strong: no review
    assert states(con, content)["t.a"].review_step == 1


def test_try_another_way_after_three_tries_and_stuck_after_six_over_two_days(con, content):
    learn(con, content, "t.a", D0)
    s = engine.get_session(con, content, "s1", D0)
    it = next(i for i in s["items"] if i["kind"] == "piece")
    for _ in range(3):
        fx = play(con, content, it["pieceId"], D0, stars=2, item=it, skill="t.a")
    assert fx["item"]["tries"] == 3 and fx["item"]["done"]
    out = {x["skillId"]: x for x in engine.skills_out(content, states(con, content), D0)}
    assert out["t.a"]["tryAnotherWay"] and not out["t.a"]["stuck"]
    for _ in range(3):
        play(con, content, "pa1", D0, stars=2, tricky=1)
    assert not states(con, content)["t.a"].stuck                            # 6 attempts, but one day
    play(con, content, "pa1", D0 + timedelta(days=1), stars=2, tricky=1)
    st = states(con, content)["t.a"]
    assert st.stuck and st.stuck_since == (D0 + timedelta(days=1)).isoformat()
    play(con, content, "pa1", D0 + timedelta(days=2), stars=3)
    st = states(con, content)["t.a"]
    assert st.status == "passed" and not st.stuck


def test_a_stuck_skill_gets_support_practice_and_other_branches_continue(con, content):
    learn(con, content, "t.a", D0)
    play(con, content, "pa1", D0, stars=4)
    for sid in ("t.b", "t.c"):
        learn(con, content, sid, D0)
    for k in range(6):
        play(con, content, "pb1", D0 + timedelta(days=k % 2), stars=1.5, tricky=2)
    assert states(con, content)["t.b"].stuck
    s = engine.get_session(con, content, "s1", D0 + timedelta(days=2))
    reasons = [(i["reason"], i["skillId"], i["section"]) for i in s["items"]]
    tricky = [i for i in s["items"] if i["skillId"] == "t.b"]
    # once, short: the whole piece one preset slower one day, the tricky section the next
    assert [(i["reason"], i["section"], i["preset"]) for i in tricky] == [("Tricky spot", None, "90")]
    nxt = [i for i in engine.get_session(con, content, "s1", D0 + timedelta(days=3))["items"] if i["skillId"] == "t.b"]
    assert [(i["reason"], i["section"]) for i in nxt] == [("Tricky spot", 2)]
    assert ("New", "t.c", None) in reasons                                  # the other branch keeps its place
    support = [i for i in s["items"] if i["reason"] == "Support"]
    assert support and all(i["skillId"] == "t.a" for i in support)          # b builds on a, and needs nothing stuck


def test_passing_mid_session_moves_the_new_slot_on(con, content):
    s = engine.get_session(con, content, "s1", D0)
    engine.lesson_done(con, content, "s1", "t.a", D0, s["items"][0]["id"])
    s = engine.get_session(con, content, "s1", D0)
    it = next(i for i in s["items"] if i["kind"] == "piece" and i["skillId"] == "t.a")
    new_a = [i for i in s["items"] if i["reason"] == "New" and i["skillId"] == "t.a" and i["id"] != it["id"] and not i["done"]]
    assert new_a                                                         # the second t.a piece
    play(con, content, it["pieceId"], D0, stars=4, item=it, skill="t.a")
    after = engine.get_session(con, content, "s1", D0)["items"]
    assert not any(i["id"] in {x["id"] for x in new_a} for i in after)
    assert next(i for i in after if i["id"] == it["id"])["done"]            # the item played is checked off
    nxt = [i for i in after if not i["done"] and i["reason"] == "New"]
    assert nxt and nxt[0]["skillId"] == "t.b" and nxt[0]["kind"] == "lesson"   # lowest sequence first


def test_a_capability_hold_skips_the_skill_and_counts_as_passed(con, tmp_path):
    skills = [dict(SKILLS[0]), {"id": "t.p", "name": "Pedal", "sequence": 15, "track": "technique", "prerequisites": ["t.a"],
                                "requiredCapabilities": ["pedal"], "pieces": ["pp1"]},
              {"id": "t.q", "name": "After pedal", "sequence": 18, "track": "reading", "prerequisites": ["t.p"], "pieces": ["pq1"]}]
    c = Content.from_json({"skills": skills}, {"pieces": [piece("pa1", "t.a"), piece("pp1", "t.p"), piece("pq1", "t.q")]})
    learn(con, c, "t.a", D0)
    play(con, c, "pa1", D0, stars=4)
    caps = engine.device_caps({"hasPedal": False})
    s = engine.get_session(con, c, "s1", D0 + timedelta(days=1), caps)
    assert "t.p" not in {i["skillId"] for i in s["items"]}
    assert ("lesson", "t.q") in {(i["kind"], i["skillId"]) for i in s["items"]}
    st = engine.load_states(con, c, "s1")
    engine.refresh(c, st, caps)
    assert st["t.p"].capability_hold
    engine.refresh(c, st, engine.device_caps({"hasPedal": True}))
    assert not st["t.p"].capability_hold


def test_end_of_content_keeps_the_session_full(con, content):
    d = D0
    for s in SKILLS:
        learn(con, content, s["id"], d)
        play(con, content, s["pieces"][0], d, stars=4, timing=4)
    assert all(st.passed for st in states(con, content).values())
    s = engine.get_session(con, content, "s1", d + timedelta(days=4))
    assert s["endOfContent"] and len([i for i in s["items"] if i["kind"] == "piece"]) >= 3
    assert engine.runway(con, content, "s1", states(con, content), d)["remaining"] == 0


def test_skip_moves_an_item_to_the_end(con, content):
    s = engine.get_session(con, content, "s1", D0)
    first = s["items"][0]["id"]
    s = engine.skip_item(con, "s1", first, D0)
    assert s["items"][-1]["id"] == first and s["items"][-1]["skipped"]


def test_practice_days_streak_and_target_length(con, content):
    for k in range(5):
        engine.add_practice(con, "s1", D0 + timedelta(days=k), 600, True)
    assert engine.streak(con, "s1", D0 + timedelta(days=4)) == 5
    assert engine.streak(con, "s1", D0 + timedelta(days=5)) == 5          # before today's practice
    engine.add_practice(con, "s1", D0 + timedelta(days=5), 200, False)    # under 5 minutes of Free Play: not a practice day
    assert engine.streak(con, "s1", D0 + timedelta(days=5)) == 5
    assert engine.streak(con, "s1", D0 + timedelta(days=6)) == 0
    # 7 days missed after the last practice day: 2 steps down (2.5 each)
    t = engine.adjust_target(con, content, "s1", D0 + timedelta(days=12))
    assert t == 10.0
    con.execute("UPDATE students SET target_minutes = 20")
    t = engine.adjust_target(con, content, "s1", D0 + timedelta(days=12))
    assert t == 10.0                                                      # measured from the last practice day, not twice


def test_a_strong_week_steps_the_target_up(con, content):
    master(con, content)                                                 # mastered on D0 + 1
    for k in range(7):
        d = D0 + timedelta(days=k)
        engine.get_session(con, content, "s1", d)
        engine.add_practice(con, "s1", d, 900, True)
        con.execute("UPDATE practice_days SET session_completed = 1 WHERE student_id = 's1' AND date = ?", (d.isoformat(),))
    assert engine.adjust_target(con, content, "s1", D0 + timedelta(days=7)) == 17.5
    assert engine.adjust_target(con, content, "s1", D0 + timedelta(days=8)) == 17.5   # once a week


def test_other_required_skills_get_review_credit_from_their_own_bars(con, content):
    # pd1 needs t.a in bars 1-2 and features t.d in bars 3-4 (skill measures, §6.8)
    pd1 = content.pieces["pd1"]
    pd1.required, pd1.skill_measures = ["t.a", "t.c", "t.d"], {"t.a": [1, 2], "t.d": [3, 4]}
    pd1.bar_notes = {1: 4, 2: 4, 3: 4, 4: 4}
    d = master(con, content)                                   # t.a mastered: first review due the next day
    d += timedelta(days=1)
    step = states(con, content)["t.a"].review_step
    m = states(con, content)["t.a"].mastery
    info = AttemptInfo(piece_id="pd1", day=d, context="free", accuracy=0.7, accuracy_stars=2.5, timing_stars=2,
                       note_errors=[{"kind": "missed", "bar": 3}, {"kind": "wrong", "bar": 4}] * 2)
    fx = engine.record_attempt(con, content, "s1", info)
    st = states(con, content)["t.a"]
    assert "t.a" in fx["reviewed"] and st.review_step == step + 1 and st.mastery == m   # credit only
    d += timedelta(days=3)
    info = AttemptInfo(piece_id="pd1", day=d, context="free", accuracy=0.7, accuracy_stars=2.5,
                       note_errors=[{"kind": "missed", "bar": 1}] * 3)       # 5 of 8 in its bars: weak
    fx = engine.record_attempt(con, content, "s1", info)
    assert "t.a" not in fx["reviewed"]
