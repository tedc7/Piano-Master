"""Weakness diagnostics (arch §8.8): the five detectors, the pattern lifecycle and the remedies."""
import json
from datetime import date, timedelta

import pytest

from app import db, diagnostics, drills, engine
from app.content import Content

D0 = date(2026, 10, 5)


def melody(names_beats, hand="R"):
    from app.analysis import midi
    ev, t = [], 0.0
    for nm, b, f in names_beats:
        ev.append((t, b, midi(nm), f))
        t += b
    return ev


# a right-hand tune with F4 and E4, eighth pairs, and a hand shift (C position to G position)
TUNE = melody([("C4", 1, 1), ("D4", 1, 2), ("E4", 1, 3), ("F4", 1, 4), ("E4", 0.5, 3), ("D4", 0.5, 2), ("C4", 1, 1), ("F4", 1, 4), ("E4", 1, 3),
               ("G4", 1, 1), ("A4", 1, 2), ("B4", 1, 3), ("G4", 1, 1), ("C4", 1, 1), ("E4", 1, 3), ("D4", 1, 2), ("C4", 1, 1)])
TUNE_NOTA = drills.notation({"R": TUNE})
# hands-together piece
DUET = drills.notation({"R": melody([("C4", 1, 1), ("D4", 1, 2), ("E4", 2, 3)] * 2),
                        "L": melody([("C3", 2, 5), ("G3", 2, 1)] * 2, "L")})

SKILLS = [{"id": "s.r", "name": "R", "sequence": 10, "track": "reading", "prerequisites": [],
           "constraints": {"hands": ["R"], "range": {"R": ["C4", "B4"]}, "durations": [0.5, 1, 2, 4], "timeSigs": ["4/4"], "keySigs": [0]}},
          {"id": "s.l", "name": "L", "sequence": 20, "track": "reading", "prerequisites": ["s.r"],
           "constraints": {"hands": ["L"], "range": {"L": ["C3", "G3"]}, "durations": [1, 2, 4], "timeSigs": ["4/4"], "keySigs": [0]}},
          {"id": "s.t", "name": "T", "sequence": 30, "track": "reading", "prerequisites": ["s.l"],
           "constraints": {"hands": ["R", "L"], "handsTogether": True, "range": {"R": ["C4", "B4"], "L": ["C3", "G3"]},
                           "durations": [1, 2, 4], "timeSigs": ["4/4"], "keySigs": [0]}}]
PIECES = [{"id": "tune", "title": "Tune", "skillId": "s.r", "hands": "R", "tempo": 90, "timeSig": "4/4", "beats": TUNE_NOTA["length"],
           "phrases": 2, "requiredSkills": ["s.r"], "featuredSkills": ["s.r"]},
          {"id": "duet", "title": "Duet", "skillId": "s.t", "hands": "RL", "tempo": 90, "timeSig": "4/4", "beats": DUET["length"],
           "phrases": 1, "requiredSkills": ["s.r", "s.l", "s.t"], "featuredSkills": ["s.t"]}]


def content():
    c = Content.from_json({"skills": SKILLS}, {"contentVersion": "t", "pieces": PIECES})
    c.notations = {"tune": TUNE_NOTA, "duet": DUET}
    return c


@pytest.fixture()
def con(tmp_path):
    path = str(tmp_path / "d.db")
    db.migrate(path)
    c = db.connect(path)
    c.execute("INSERT INTO students (id, name, avatar, start_date, created_at) VALUES ('s', 'A', 'x', ?, ?)", (D0.isoformat(),) * 2)
    c.execute("INSERT INTO devices (id, created_at, last_seen) VALUES ('dev', ?, ?)", (D0.isoformat(),) * 2)
    return c


def results(nota, miss=(), ms=0.0, per_note=None):
    """Every note hit at `ms` (or per_note[i]) except the indexes in `miss`."""
    return [(i, None if i in miss else (per_note(i, n) if per_note else ms)) for i, n in enumerate(nota["notes"])]


def store(con, d: date, pid: str, res, wrongs=(), preset="100", hands="both", mode="play", raw=None, skill=None):
    n = len(res)
    hit = sum(1 for _, m in res if m is not None)
    acc = raw if raw is not None else hit / n
    con.execute(
        "INSERT INTO attempts (id, device_id, student_id, piece_id, arrangement_id, context, mode, completed, started_at, received_at, "
        "tempo_preset, conditions, conditions_factor, raw_accuracy, accuracy, accuracy_stars, per_phrase_errors, note_errors, evaluation, "
        "raw_events, passes, skill_id, note_results) VALUES (?, 'dev', 's', ?, ?, 'guided', ?, 1, ?, ?, ?, ?, 1, ?, ?, ?, '[]', ?, '{}', '[]', '[]', ?, ?)",
        (f"a{con.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]}", pid, pid, mode, f"{d.isoformat()}T12:00:00", d.isoformat(),
         preset, json.dumps({"hands": hands}), acc, acc, engine.stars(acc),
         json.dumps([{"kind": "wrong", **w} for w in wrongs]), skill, json.dumps(res)))


def obs(con, d):
    return diagnostics.load_obs(con, "s", d)


def found(con, d):
    c = content()
    P = diagnostics.Pieces(con, c)
    xs = obs(con, d)
    return {f.key: f for det in diagnostics.DETECTORS for f in det(xs, P, c)}


def test_note_confusion_needs_three_times_on_two_days_and_thirty_percent(con):
    f4 = [i for i, n in enumerate(TUNE_NOTA["notes"]) if n["pitch"] == 65]       # F4 twice per play
    wrong = {"pitch": 67, "expected": 65, "hand": "R"}
    store(con, D0, "tune", results(TUNE_NOTA, miss=f4), [wrong, wrong])
    assert "note:R:65>67" not in found(con, D0), "one day is not enough"
    store(con, D0 + timedelta(days=1), "tune", results(TUNE_NOTA, miss=f4[:1]), [wrong])
    f = found(con, D0 + timedelta(days=1))["note:R:65>67"]
    assert f.details["count"] == 3 and f.details["of"] == 4 and f.skills == {"s.r"}
    assert "plays G4 for F4" in f.details["text"]


def test_rhythm_early_eighths_and_a_general_rush(con):
    notes = TUNE_NOTA["notes"]
    eighths = lambda i, n: -120.0 if n["duration"] == 0.5 else 5.0   # noqa: E731
    for k in range(6):
        store(con, D0 + timedelta(days=k % 2), "tune", results(TUNE_NOTA, per_note=eighths))
    keys = found(con, D0 + timedelta(days=1))
    assert "rhythm:eighths:early" in keys and not any(k.startswith("rhythm:beat") for k in keys)
    assert keys["rhythm:eighths:early"].details["piece"] == "tune"
    # everything early: one "steady beat" pattern, not a pattern for each figure
    con.execute("DELETE FROM attempts")
    for k in range(4):
        store(con, D0 + timedelta(days=k % 2), "tune", results(TUNE_NOTA, ms=-110.0))
    keys = found(con, D0 + timedelta(days=1))
    assert set(k for k in keys if k.startswith("rhythm")) == {"rhythm:beat:early"}
    assert len(notes) * 4 == keys["rhythm:beat:early"].occurrences


def test_hands_together_below_the_weaker_hand(con):
    for h, acc in (("R", 0.95), ("L", 0.9)):
        store(con, D0, "duet", results(DUET), hands=h, raw=acc)
    for k in range(3):
        store(con, D0 + timedelta(days=1), "duet", results(DUET), raw=0.7, preset="90")
    f = found(con, D0 + timedelta(days=1))["hands:duet"]
    assert f.details["weaker"] == "L" and f.details["preset"] == "90"


def test_position_shift_errors_after_the_hand_moves(con):
    a = diagnostics.annotate(TUNE_NOTA)
    assert [TUNE_NOTA["notes"][i]["pitch"] for i in a.shift_at] == [67, 60]      # up to G position, back to C
    after = [i for i, s in enumerate(a.shift) if s]
    for k in range(3):
        store(con, D0 + timedelta(days=k), "tune", results(TUNE_NOTA, miss=after[:2]))
    f = found(con, D0 + timedelta(days=2))["shift:tune"]
    assert f.details["rate"] == 0.5 and f.details["bars"] == [2, 3]


def test_tempo_ceiling_between_neighbouring_presets(con):
    for k in range(3):
        store(con, D0 + timedelta(days=k), "tune", results(TUNE_NOTA), preset="75", raw=0.95)
        store(con, D0 + timedelta(days=k), "tune", results(TUNE_NOTA), preset="100", raw=0.75)
    assert "tempo:tune" not in found(con, D0 + timedelta(days=2)), "90% was never played: not neighbours"
    for k in range(3):
        store(con, D0 + timedelta(days=k), "tune", results(TUNE_NOTA), preset="90", raw=0.78)
    f = found(con, D0 + timedelta(days=2))["tempo:tune"]
    assert (f.details["slower"], f.details["preset"]) == ("75", "90")


def plant_confusion(con, d0):
    f4 = [i for i, n in enumerate(TUNE_NOTA["notes"]) if n["pitch"] == 65]
    w = {"pitch": 67, "expected": 65, "hand": "R"}
    store(con, d0, "tune", results(TUNE_NOTA, miss=f4), [w, w], skill="s.r")
    store(con, d0 + timedelta(days=1), "tune", results(TUNE_NOTA, miss=f4[:1]), [w], skill="s.r")


def test_a_pattern_is_resolved_by_two_good_days_and_stuck_after_three_remedies(con):
    c = content()
    plant_confusion(con, D0)
    p = diagnostics.run(con, c, "s", D0 + timedelta(days=1))[0]
    assert p["status"] == "active" and p["kind"] == "note"
    for k in (2, 3, 4):
        diagnostics.remedy_tried(con, p["id"], D0 + timedelta(days=k))
    assert diagnostics.run(con, c, "s", D0 + timedelta(days=4))[0]["status"] == "stuck"
    store(con, D0 + timedelta(days=5), "tune", results(TUNE_NOTA))
    store(con, D0 + timedelta(days=5), "tune", results(TUNE_NOTA))
    assert diagnostics.run(con, c, "s", D0 + timedelta(days=5))[0]["status"] == "improving"
    store(con, D0 + timedelta(days=6), "tune", results(TUNE_NOTA))
    store(con, D0 + timedelta(days=6), "tune", results(TUNE_NOTA))
    p = diagnostics.run(con, c, "s", D0 + timedelta(days=6))[0]
    assert p["status"] == "resolved" and p["resolvedDate"] == (D0 + timedelta(days=6)).isoformat()
    # the old mistakes are still in the 14 days, but it is found again only from new ones
    assert diagnostics.run(con, c, "s", D0 + timedelta(days=7))[0]["status"] == "resolved"


def test_remedies_go_first_in_the_practice_slot_and_count_when_done(con):
    c = content()
    plant_confusion(con, D0)
    today = D0 + timedelta(days=2)
    states = engine.load_states(con, c, "s")
    states["s.r"].status = "current"
    engine.save_states(con, "s", states)
    s = engine.get_session(con, c, "s", today)
    focus = [i for i in s["items"] if i["reason"] == "Focus"]
    assert len(focus) == 1 and focus[0]["kind"] == "drill" and focus[0]["title"] == "Reading game: F and G"
    drill = json.loads(con.execute("SELECT piece FROM drills WHERE id = ?", (focus[0]["pieceId"],)).fetchone()["piece"])
    assert drill["kind"] == "drill" and drill["drill"]["patternId"] == focus[0]["patternId"]
    # playing the drill checks the item off and counts as a remedy tried
    info = engine.AttemptInfo(piece_id=drill["id"], day=today, context="guided", accuracy=0.9, accuracy_stars=4, item_id=focus[0]["id"])
    fx = engine.record_attempt(con, c, "s", info)
    assert fx["item"]["done"] and fx["passed"] == []
    assert diagnostics.patterns(con, "s")[0]["remediesTried"] == [today.isoformat()]


def test_each_kind_has_the_right_remedy(con):
    c = content()
    states = engine.load_states(con, c, "s")
    for sid in states:
        states[sid].status = "passed"
    m = drills.Material.from_skills(c.skill_dicts(list(states)))
    mk = lambda kind, **d: {"id": "pat-00001", "kind": kind, "details": d}   # noqa: E731
    items = lambda p: diagnostics.remedy_for(con, c, "s", p, m, D0, engine.new_item, engine.piece_seconds)  # noqa: E731
    rh = items(mk("rhythm", figure="eighths", way="early", piece="tune", bar=2))
    assert [i["kind"] for i in rh] == ["drill", "piece"] and rh[1]["bars"] == [2, 3] and rh[1]["click"] is True
    hands = items(mk("hands", piece="duet", weaker="L", preset="90"))
    assert [(i.get("hands"), i["preset"]) for i in hands] == [("L", "90"), ("both", "75")]
    assert items(mk("shift", piece="tune", bars=[2, 3]))[0]["bars"] == [2, 3]
    assert [i["preset"] for i in items(mk("tempo", piece="tune", preset="90", slower="75"))] == ["75", "90"]
    tap = json.loads(con.execute("SELECT piece FROM drills WHERE kind = 'rhythm'").fetchone()["piece"])
    assert tap["drill"]["anyKey"] == 60 and tap["title"] == "Rhythm tap: eighth notes"


def test_the_api_stores_note_results_and_serves_the_remedy_drill(client, parent, tmp_path, monkeypatch):
    import os
    from pathlib import Path

    from conftest import attempt, write_content
    folder = Path(os.environ["PIANO_CONTENT"])
    theory = {"id": "s.th", "name": "Th", "sequence": 40, "track": "theory", "prerequisites": []}
    write_content(folder, SKILLS + [theory], PIECES, version="t2")
    (folder / "pieces").mkdir(exist_ok=True)
    (folder / "pieces" / "tune.json").write_text(json.dumps({"id": "tune", "notation": TUNE_NOTA}))
    sid = client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]
    # yesterday and the day before: F4 played as G4
    f4 = [i for i, n in enumerate(TUNE_NOTA["notes"]) if n["pitch"] == 65]
    today = date.today()
    for k, miss in ((2, f4), (1, f4[:1])):
        when = f"{(today - timedelta(days=k)).isoformat()}T12:00:00.000+00:00"
        a = attempt(studentId=sid, pieceId="tune", startedAt=when, noteResults=[[i, None if i in miss else 5.0] for i in range(len(TUNE_NOTA["notes"]))],
                    noteErrors=[{"kind": "wrong", "beat": 3, "pitch": 67, "expected": 65, "hand": "R", "bar": 1}] * len(miss))
        assert client.post("/api/attempts", json=a).status_code == 201
    stored = client.get(f"/api/attempts/{a['id']}").json()
    assert stored["noteResults"][0] == [0, 5.0]
    s = client.get(f"/api/students/{sid}/state").json()["session"]
    focus = [i for i in s["items"] if i["reason"] == "Focus"]
    assert focus and focus[0]["kind"] == "drill", [i["reason"] for i in s["items"]]
    drill = client.get(f"/api/students/{sid}/drills/{focus[0]['pieceId']}").json()
    assert drill["notation"]["notes"] and drill["drill"]["kind"] == "reading"
    assert client.get(f"/api/students/other/drills/{focus[0]['pieceId']}").status_code == 404
    done = client.post("/api/attempts", json=attempt(studentId=sid, pieceId=drill["id"], itemId=focus[0]["id"], context="guided",
                                                      startedAt=f"{today.isoformat()}T12:00:00.000+00:00")).json()
    assert done["effects"]["item"]["done"]
    rep = client.get(f"/api/students/{sid}/progress").json()
    assert rep["patterns"][0]["kind"] == "note" and rep["patterns"][0]["remediesTried"] == [today.isoformat()]
    # a theory skill's lesson Check: 3 of 4 first time and 1 the second time = 87.5%, 4 stars, passed
    client.post(f"/api/students/{sid}/lessons/s.r/done", json={})
    r = client.post(f"/api/students/{sid}/lessons/s.th/done", json={"check": {"questions": 4, "points": 3.5}}).json()
    assert r["check"]["stars"] == 4.0 and r["status"] == "passed"
