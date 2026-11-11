"""Song progress (arch §8.12, v0.50): each student's record of each song, kept after every attempt
and the same when rebuilt from the stored attempts."""
import json
import random
from datetime import date, datetime, timedelta, timezone

from app import db, engine, song_progress
from app.content import Content

from conftest import PIECES, SKILLS, attempt, piece


def kid(client, parent):
    return client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]


def cond(preset="100", hands="both", written="R", **kw):
    return {"mode": "play", "tempoPreset": preset, "hands": hands, "handsWritten": written, "sectionOnly": False,
            "extraHints": False, "rewinds": 0, **kw}


def play(client, sid, pid, stars, days_ago=0, preset="100", hands="both", written="R", **over):
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    ev = {**attempt()["evaluation"], "accuracyStars": stars}
    a = attempt(studentId=sid, pieceId=pid, startedAt=when.isoformat(), evaluation=ev,
                conditions=cond(preset, hands, written), **over)
    r = client.post("/api/attempts", json=a)
    assert r.status_code == 201, r.text
    return r.json()["effects"]


def record(sid, pid):
    con = db.connect()
    try:
        return song_progress.get(con, sid, pid)
    finally:
        con.close()


def test_a_song_climbs_its_stages_and_never_goes_back(client, parent):
    sid = kid(client, parent)
    assert record(sid, "pa1") is None
    play(client, sid, "pa1", 5.0, completed=False)
    assert record(sid, "pa1")["stage"] == "new"                       # never played to the end
    play(client, sid, "pa1", 2.0, preset="75")
    assert record(sid, "pa1")["stage"] == "learning"
    play(client, sid, "pa1", 3.5, preset="75")
    r = record(sid, "pa1")
    assert r["stage"] == "slow" and r["tempo_reached"] == "75"
    fx = play(client, sid, "pa1", 3.0)
    assert fx["song"] == {"stage": "learned", "was": "slow"}
    assert record(sid, "pa1")["learned_date"] == date.today().isoformat()
    play(client, sid, "pa1", 4.0)
    assert record(sid, "pa1")["stage"] == "solid"
    play(client, sid, "pa1", 2.0)                                      # a weak play doesn't take a stage away
    r = record(sid, "pa1")
    assert r["stage"] == "solid" and r["best"]["both|100"]["acc"] == 4.0 and r["tempo_reached"] == "100"
    fx = play(client, sid, "pa1", 5.0)
    assert fx["song"]["stage"] == "excellent" and record(sid, "pa1")["five_star_date"]
    r = record(sid, "pa1")
    assert r["plays"] == 7 and r["completed_plays"] == 6 and r["best_stars"] == 5.0


def test_a_song_for_both_hands_is_hands_apart_until_played_with_both(client, parent):
    sid = kid(client, parent)
    con = db.connect()
    try:
        a = {"piece_id": "duet", "mode": "play", "completed": True, "started_at": datetime.now(timezone.utc).isoformat(),
             "duration_sec": 30, "tempo_preset": "100", "content_version": "v1", "conditions": cond(hands="R", written="R"),
             "accuracy_stars": 4.0, "timing_stars": 3.0, "per_phrase_errors": [], "section": None, "tricky": None}
        song_progress.update(con, sid, a, "RL")                        # the planned right-hand step
        r = song_progress.get(con, sid, "duet")
        assert r["stage"] == "hands-apart" and r["hands_done"] == ["R"] and r["best_stars"] is None
        song_progress.update(con, sid, {**a, "conditions": cond(hands="L", written="RL"), "accuracy_stars": 3.0}, "RL")
        r = song_progress.get(con, sid, "duet")
        assert r["stage"] == "hands-apart" and r["best_stars"] == 3.0   # one hand chosen by the child is in the collection
        song_progress.update(con, sid, {**a, "conditions": cond(written="RL"), "accuracy_stars": 3.0}, "RL")
        assert song_progress.get(con, sid, "duet")["stage"] == "learned"
    finally:
        con.close()
    play(client, sid, "pa1", 3.0, preset="75")
    songs = client.get(f"/api/students/{sid}/state").json()["songs"]
    assert songs["duet"]["handsDone"] == ["L", "R", "both"] and songs["duet"]["stage"] == "learned"
    assert songs["pa1"] == {"stage": "slow", "best": 3.0, "fullStars": None, "tempoReached": "75", "handsDone": ["both"],
                            "hands": "R", "plays": 1, "lastPlayed": date.today().isoformat(), "learned": None}


def test_sections_keep_each_phrases_errors_and_the_songs_tricky_spot(client, parent):
    sid = kid(client, parent)
    con = db.connect()
    try:
        # the phrases, as the song's notation gives them: four of 8 beats
        a = {"piece_id": "pa1", "mode": "play", "completed": True, "started_at": datetime.now(timezone.utc).isoformat(),
             "duration_sec": 30, "tempo_preset": "100", "content_version": "v1", "conditions": cond(),
             "accuracy_stars": 3.0, "timing_stars": 3.0, "per_phrase_errors": [0, 4, 1, 0], "section": None,
             "tricky": {"phrase": 1}}
        song_progress.update(con, sid, a, "R", [0, 8, 16, 24], 32)
        loop = {**a, "mode": "loop", "section": {"fromBeat": 8, "toBeat": 16}, "per_phrase_errors": [0, 1, 0, 0], "tricky": None}
        song_progress.update(con, sid, loop, "R", [0, 8, 16, 24], 32)
        r = song_progress.get(con, sid, "pa1")
    finally:
        con.close()
    assert [s["plays"] for s in r["sections"]] == [1, 2, 1, 1]          # the loop played only the second phrase
    assert r["sections"][1] == {"plays": 2, "lastErrors": 1, "fewestErrors": 1, "last": r["last_played"], "tricky": 1}
    assert r["tricky"]["phrase"] == 1                                  # a section's play isn't a tricky spot of the song


def test_keeping_it_play_by_play_and_rebuilding_it_give_the_same_records(client, parent):
    sid = kid(client, parent)
    rng = random.Random(3)
    for n in range(60):
        pid = rng.choice(["pa1", "pa2", "pb1", "drill-0a1b2c3d4e"])
        over = {"completed": rng.random() > 0.15, "mode": rng.choice(["play", "play", "loop"])}
        if rng.random() < 0.2:
            over["tricky"] = None
        play(client, sid, pid, rng.choice([1.0, 2.5, 3.0, 4.0, 4.5, 5.0]), days_ago=rng.randint(0, 9),
             preset=rng.choice(["50", "75", "90", "100"]), hands=rng.choice(["both", "both", "R", "L"]),
             written=rng.choice(["R", "R", "RL"]), **over)
    con = db.connect()
    try:
        kept = song_progress.load(con, sid)
        song_progress.rebuild(con, {p["id"]: {"hands": p["hands"]} for p in PIECES}, sid)
        again = song_progress.load(con, sid)
    finally:
        con.close()
    assert kept == again and "drill-0a1b2c3d4e" not in kept


def test_the_star_collection_from_the_records_is_what_the_attempts_gave(client, parent):
    """The collection read from the songs' records (v0.50) against the reading of every attempt it
    replaced (awards.plays and awards.bests, kept for this comparison)."""
    from app import awards
    sid = kid(client, parent)
    rng = random.Random(8)
    for _ in range(50):
        play(client, sid, rng.choice(["pa1", "pa2", "pb1", "pc1"]), rng.choice([1.5, 3.0, 3.5, 4.5, 5.0]),
             days_ago=rng.randint(0, 12), hands=rng.choice(["both", "both", "R"]), written=rng.choice(["R", "RL"]),
             completed=rng.random() > 0.1, mode=rng.choice(["play", "play", "loop"]))
    con = db.connect()
    try:
        today = date.today()
        rows = awards.plays(con, sid)
        got = awards.collection(con, sid, today)
        assert got["songs"] == awards.bests(rows)
        assert got["today"] == sum(awards.bests(rows).values()) - sum(awards.bests(rows, today).values())
        assert got["week"] == sum(awards.bests(rows).values()) - sum(awards.bests(rows, today - timedelta(days=6)).values())
    finally:
        con.close()


def test_the_migration_fills_the_records_from_the_attempts_already_stored(tmp_path):
    path = str(tmp_path / "m.db")
    db.migrate(path)
    con = db.connect(path)
    con.execute("INSERT INTO students (id, name, avatar, start_date, created_at) VALUES ('s1', 'Ada', 'x', '2026-10-01', '2026-10-01')")
    con.execute("INSERT INTO devices (id, created_at, last_seen) VALUES ('dev', '2026-10-01', '2026-10-01')")
    for n, (pid, stars, preset) in enumerate([("pa1", 2.0, "75"), ("pa1", 4.0, "100"), ("pb1", 3.0, "50")]):
        con.execute(
            "INSERT INTO attempts (id, device_id, student_id, piece_id, arrangement_id, context, mode, completed, started_at, "
            "received_at, tempo_preset, conditions, conditions_factor, raw_accuracy, accuracy, accuracy_stars, per_phrase_errors, "
            "note_errors, evaluation, raw_events, passes) VALUES (?, 'dev', 's1', ?, ?, 'free', 'play', 1, ?, ?, ?, ?, 1, 1, 1, ?, "
            "'[1, 0]', '[]', '{}', '[]', '[]')",
            (f"a{n}", pid, pid, f"2026-10-0{n + 2}T10:00:00+00:00", "2026-10-05", preset, json.dumps(cond(preset)), stars))
    con.execute("DELETE FROM song_progress")
    # the library's files give each song's hands and phrases (the migration runs before the content loads)
    lib = tmp_path / "library"
    (lib / "pa1").mkdir(parents=True)
    (lib / "index.json").write_text(json.dumps({"pieces": [{"id": "pa1", "hands": "R"}]}))
    (lib / "pa1" / "piece.json").write_text(json.dumps({"notation": {"phrases": [0, 8], "length": 16}}))
    import importlib.util
    spec = importlib.util.spec_from_file_location("m015", db.MIGRATIONS / "015_song_progress.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.run(con, tmp_path)
    recs = song_progress.load(con, "s1")
    con.close()
    assert recs["pa1"]["stage"] == "solid" and recs["pa1"]["best_stars"] == 4.0 and recs["pa1"]["hands"] == "R"
    assert [s["plays"] for s in recs["pa1"]["sections"]] == [2, 2]
    assert recs["pb1"]["stage"] == "slow" and recs["pb1"]["sections"] == []      # not in the library: no phrases


def test_a_stuck_skills_tricky_spot_is_its_own_songs_phrase(tmp_path):
    """Until v0.50 the tricky phrase was kept on the skill, so a stuck skill's Tricky spot item could
    take another song's phrase number."""
    path = str(tmp_path / "e.db")
    db.migrate(path)
    con = db.connect(path)
    content = Content.from_json({"skills": SKILLS}, {"contentVersion": "t", "pieces": PIECES})
    st = {s.id: engine.SkillState(s.id) for s in content.order}
    st["t.a"].status, st["t.a"].stuck, st["t.a"].stuck_since = "current", True, "2026-10-05"
    st["t.a"].last_piece_id, st["t.a"].last_tricky_phrase = "pa2", 3          # pa2's phrase, from the skill
    # pa1 is the song the item uses; its own record says its tricky phrase is 1
    songs = {"pa1": {**song_progress.blank("s1", "pa1"), "tricky": {"phrase": 1, "day": "2026-10-05"}, "last_preset": "90"}}
    items, _ = engine.Planner(content, st, date(2026, 10, 5), 20, songs=songs).build()
    spot = next(i for i in items if i["reason"] == "Tricky spot")
    assert spot["pieceId"] == "pa1" and spot["section"] == 1
    # no record for the song, and the skill's last song was another: the whole song one preset slower
    items, _ = engine.Planner(content, st, date(2026, 10, 5), 20).build()
    spot = next(i for i in items if i["reason"] == "Tricky spot")
    assert spot["pieceId"] == "pa1" and spot["section"] is None
    con.close()


def test_the_progress_report_lists_the_songs_learned(client, parent):
    sid = kid(client, parent)
    play(client, sid, "pa1", 3.0)
    play(client, sid, "pb1", 2.0)
    play(client, sid, "pc1", 4.5, days_ago=8)
    r = client.get(f"/api/students/{sid}/progress").json()
    assert [(x["pieceId"], x["stage"]) for x in r["songsLearned"]] == [("pa1", "learned"), ("pc1", "solid")]
    assert [w["songsLearned"] for w in r["weeks"]] == [0, 0, 1, 1]


def test_an_attempts_later_scorer_stars_reach_its_skill(client, parent):
    """v0.50 (§7.7): the client's evaluation carries a star row for each scorer it ran."""
    sid = kid(client, parent)
    client.post(f"/api/students/{sid}/lessons/t.a/done", json={})
    ev = {**attempt()["evaluation"], "accuracyStars": 4.0,
          "scorers": [{"id": "notes", "label": "Notes", "score": 0.9, "stars": 4.0},
                      {"id": "timing", "label": "Timing", "score": 0.8, "stars": 3.0},
                      {"id": "dynamics", "label": "Loud and soft", "score": 0.7, "stars": 2.5}]}
    a = attempt(studentId=sid, pieceId="pa1", evaluation=ev, skillId="t.a", conditions=cond(),
                startedAt=datetime.now(timezone.utc).isoformat())
    assert client.post("/api/attempts", json=a).status_code == 201
    con = db.connect()
    try:
        r = con.execute("SELECT best_scorer_stars FROM skill_states WHERE student_id = ? AND skill_id = 't.a'", (sid,)).fetchone()
    finally:
        con.close()
    assert json.loads(r[0]) == {"dynamics": 2.5}
