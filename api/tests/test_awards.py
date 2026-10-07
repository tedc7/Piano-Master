"""M10 rewards (arch §3 "Rewards"): the star collection (each song's best) and medals."""
import json
from datetime import datetime, timedelta, timezone

from conftest import SKILLS, attempt


def kid(client, parent):
    return client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]


def play(client, sid, piece, stars, days_ago=0, **over):
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    ev = {**attempt()["evaluation"], "accuracyStars": stars}
    a = attempt(studentId=sid, pieceId=piece, startedAt=when.isoformat(), evaluation=ev, **over)
    return client.post("/api/attempts", json=a).json()["effects"]


def test_the_star_collection_counts_each_songs_best(client, parent):
    sid = kid(client, parent)
    fx = play(client, sid, "pa1", 3.0)
    assert fx["stars"] == {"total": 3.0, "gained": 3.0} and fx["best"] is None      # a first play is not a "best"
    fx = play(client, sid, "pa1", 2.5)
    assert fx["stars"] == {"total": 3.0, "gained": 0} and fx["best"] is None        # a weaker play takes nothing away
    fx = play(client, sid, "pa1", 4.5)
    assert fx["stars"] == {"total": 4.5, "gained": 1.5} and fx["best"] == {"previous": 3.0, "now": 4.5}
    # section practice, a stopped play and a generated drill aren't in the collection
    assert play(client, sid, "pa2", 5.0, mode="loop")["stars"]["total"] == 4.5
    assert play(client, sid, "pa2", 5.0, completed=False)["stars"]["total"] == 4.5
    assert play(client, sid, "drill-0a1b2c3d4e", 5.0)["stars"]["total"] == 4.5
    fx = play(client, sid, "pb1", 2.0)
    assert fx["stars"] == {"total": 6.5, "gained": 2.0}
    st = client.get(f"/api/students/{sid}/state").json()["rewards"]
    assert st["stars"] == 6.5 and st["starsToday"] == 6.5 and st["songStars"] == {"pa1": 4.5, "pb1": 2.0}
    p = client.get(f"/api/students/{sid}/progress").json()
    assert p["stars"] == 6.5 and p["starsThisWeek"] == 6.5


def test_stars_today_and_this_week_are_what_the_collection_grew_by(client, parent):
    sid = kid(client, parent)
    play(client, sid, "pa1", 3.0, days_ago=10)
    play(client, sid, "pa2", 2.0, days_ago=3)
    play(client, sid, "pa1", 4.0)
    r = client.get(f"/api/students/{sid}/awards").json()["stars"]
    assert r == {"total": 6.0, "today": 1.0, "week": 3.0}


def test_milestone_medals_are_earned_once(client, parent):
    sid = kid(client, parent)
    long = {"durationSec": 360}                       # Free Play makes a practice day after 5 minutes
    fx = play(client, sid, "pa1", 5.0, days_ago=2, **long)
    assert [a["id"] for a in fx["awards"]] == ["fivestar:1"]
    assert fx["awards"][0] | {"date": None} == {"id": "fivestar:1", "kind": "fivestar", "tier": "bronze",
                                                "title": "Five-star songs", "detail": "1 five-star song", "date": None}
    assert play(client, sid, "pa2", 5.0, days_ago=1, **long)["awards"] == []              # 2 five-star songs: no new step
    fx = play(client, sid, "pb1", 3.0, **long)
    assert [a["id"] for a in fx["awards"]] == ["streak:3"]                     # three days in a row
    for p in ("pc1", "pd1"):
        fx = play(client, sid, p, 1.0)
    assert [a["id"] for a in fx["awards"]] == ["songs:5"]
    r = client.get(f"/api/students/{sid}/awards").json()
    streak = next(s for s in r["series"] if s["kind"] == "streak")
    assert streak["value"] == 3 and streak["next"]["at"] == 7 and streak["steps"][0]["earned"]["new"]
    assert r["count"] == 3 and r["unseen"] == 3
    assert client.get(f"/api/students/{sid}/state").json()["rewards"]["unseen"] == 3
    client.post(f"/api/students/{sid}/awards/seen")
    assert client.get(f"/api/students/{sid}/awards").json()["unseen"] == 0


def test_unit_and_level_medals(client, parent, tmp_path):
    """Bronze when every skill of a unit (or level) is passed, silver when every one is mastered,
    gold when every one is mastered with 5 stars."""
    units = {"t.a": "Unit 1 · Start", "t.b": "Unit 1 · Start", "t.c": "Unit 2 · More", "t.d": "Unit 2 · More", "t.e": "Unit 2 · More"}
    skills = [{**s, "level": "Prep A", "unit": units[s["id"]]} for s in SKILLS]
    (tmp_path / "content" / "skillmap.json").write_text(json.dumps({"contentVersion": "test2", "skills": skills}))
    sid = kid(client, parent)
    for skill, piece in (("t.a", "pa1"), ("t.b", "pb1")):
        assert client.post(f"/api/students/{sid}/lessons/{skill}/done", json={}).json()["awards"] == []
        fx = play(client, sid, piece, 3.0, skillId=skill)
        assert fx["passed"] == [skill]
    assert [(a["id"], a["tier"], a["title"], a["detail"]) for a in fx["awards"]] == [
        ("unit:Prep A|Unit 1 · Start:complete", "bronze", "Unit 1 · Start", "Complete")]
    r = client.get(f"/api/students/{sid}/awards").json()
    (lv,) = r["levels"]
    assert (lv["level"], lv["skills"], lv["passed"]) == ("Prep A", 5, 2)
    u1, u2 = lv["units"]
    assert (u1["unit"], u1["skills"], u1["passed"], u1["fivestar"]) == ("Unit 1 · Start", 2, 2, 0)
    assert [m["earned"] is not None for m in u1["medals"]] == [True, False, False]
    assert (u2["skills"], u2["passed"]) == (3, 0) and not lv["medals"][0]["earned"]
    # five stars isn't gold until the skills are mastered too (8.2: 4 stars on 2 separate days)
    play(client, sid, "pa1", 5.0, skillId="t.a")
    fx = play(client, sid, "pb1", 5.0, skillId="t.b")
    assert fx["awards"] == []
