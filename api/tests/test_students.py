"""M4: parent login with lockout, students and their settings, favorites, device profiles, and
attempts kept per student."""
import uuid
from datetime import datetime, timedelta, timezone

from app import db

from conftest import attempt


def test_first_pin_logs_in_and_later_logins_check_it(client):
    assert client.get("/api/parent").json()["pinSet"] is False
    assert client.post("/api/parent/login", json={"pin": "1234"}).status_code == 409
    r = client.post("/api/parent/pin", json={"pin": "1234"})
    assert r.status_code == 200 and r.json()["token"]
    assert client.get("/api/parent").json()["pinSet"] is True
    # a second "first PIN" is refused without the parent session and the current PIN
    assert client.post("/api/parent/pin", json={"pin": "9999"}).status_code == 401
    r = client.post("/api/parent/login", json={"pin": "1234"})
    assert r.status_code == 200 and r.json()["autoLogoutMinutes"] == 10
    tok = {"X-Parent-Token": r.json()["token"]}
    assert client.post("/api/parent/pin", json={"pin": "5555", "currentPin": "0000"}, headers=tok).status_code == 403
    assert client.post("/api/parent/pin", json={"pin": "555555", "currentPin": "1234"}, headers=tok).status_code == 200
    assert client.post("/api/parent/login", json={"pin": "1234"}).status_code == 401
    assert client.post("/api/parent/login", json={"pin": "555555"}).status_code == 200
    assert client.post("/api/parent/login", json={"pin": "12"}).status_code == 422


def test_five_wrong_pins_lock_login_and_lockouts_double(client):
    client.post("/api/parent/pin", json={"pin": "1234"})
    for left in (4, 3, 2, 1):
        r = client.post("/api/parent/login", json={"pin": "0000"})
        assert r.status_code == 401 and r.json()["detail"]["triesLeft"] == left
    r = client.post("/api/parent/login", json={"pin": "0000"})
    assert r.status_code == 423
    first = datetime.fromisoformat(r.json()["detail"]["lockedUntil"])
    assert timedelta(minutes=4) < first - datetime.now(timezone.utc) <= timedelta(minutes=5)
    # even the right PIN waits out the lock
    assert client.post("/api/parent/login", json={"pin": "1234"}).status_code == 423
    con = db.connect()
    con.execute("UPDATE parent SET locked_until = ?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),))
    con.close()
    for _ in range(4):
        client.post("/api/parent/login", json={"pin": "0000"})
    second = datetime.fromisoformat(client.post("/api/parent/login", json={"pin": "0000"}).json()["detail"]["lockedUntil"])
    assert timedelta(minutes=9) < second - datetime.now(timezone.utc) <= timedelta(minutes=10)


def test_parent_session_ends_after_idle_time_and_on_logout(client, parent):
    assert client.post("/api/parent/ping", headers=parent).status_code == 200
    con = db.connect()
    con.execute("UPDATE parent_sessions SET last_used = ?", ((datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(),))
    con.close()
    assert client.post("/api/parent/ping", headers=parent).status_code == 401
    tok = {"X-Parent-Token": client.post("/api/parent/login", json={"pin": "2468"}).json()["token"]}
    assert client.post("/api/parent/ping", headers=tok).status_code == 200
    client.post("/api/parent/logout", headers=tok)
    assert client.post("/api/parent/ping", headers=tok).status_code == 401


def test_parent_functions_reject_requests_without_a_parent_session(client, parent):
    sid = client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]
    bad = {"X-Parent-Token": "nope"}
    for h in ({}, bad):
        assert client.post("/api/students", json={"name": "X", "avatar": "🐢"}, headers=h).status_code == 401
        assert client.patch(f"/api/students/{sid}", json={"name": "Y"}, headers=h).status_code == 401
        assert client.delete(f"/api/students/{sid}", headers=h).status_code == 401
        assert client.get("/api/students", params={"all": True}, headers=h).status_code == 401
        assert client.put(f"/api/devices/{uuid.uuid4()}", json={"profile": {"keyboardSize": 88}}, headers=h).status_code == 401
        assert client.put("/api/parent/settings", json={"autoLogoutMinutes": 5}, headers=h).status_code == 401
    assert client.get(f"/api/students/{sid}").status_code in (404, 405)


def test_students_are_added_edited_archived_and_deleted(client, parent):
    a = client.post("/api/students", json={"name": " Ada ", "avatar": "🦊"}, headers=parent).json()
    b = client.post("/api/students", json={"name": "Ben", "avatar": "🐢"}, headers=parent).json()
    assert a["name"] == "Ada" and a["settings"]["rewindBars"] == 2 and a["targetMinutes"] == 15
    assert [s["name"] for s in client.get("/api/students").json()["students"]] == ["Ada", "Ben"]
    r = client.patch(f"/api/students/{a['id']}", json={"settings": {"autoRewind": False, "rewindBars": 3, "backingVolume": 1.5, "otherHand": False}},
                     headers=parent).json()
    assert r["settings"]["autoRewind"] is False and r["settings"]["rewindBars"] == 3 and r["settings"]["backingVolume"] == 1.5
    assert a["settings"]["otherHand"] is True and r["settings"]["otherHand"] is False
    client.patch(f"/api/students/{b['id']}", json={"status": "archived"}, headers=parent)
    assert [s["name"] for s in client.get("/api/students").json()["students"]] == ["Ada"]
    assert len(client.get("/api/students", params={"all": True}, headers=parent).json()["students"]) == 2
    client.post("/api/attempts", json=attempt(studentId=a["id"], pieceId="pa1"))
    client.put(f"/api/students/{a['id']}/favorites/pa1")
    assert client.delete(f"/api/students/{a['id']}", headers=parent).status_code == 200
    assert client.get("/api/attempts", params={"student_id": a["id"]}).json()["attempts"] == []
    con = db.connect()
    assert con.execute("SELECT COUNT(*) FROM favorites").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM skill_states").fetchone()[0] == 0
    con.close()


def test_song_choices_are_remembered_per_student(client, parent):
    a = client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]
    b = client.post("/api/students", json={"name": "Ben", "avatar": "🐢"}, headers=parent).json()["id"]
    client.patch(f"/api/students/{a}/prefs", json={"pieceId": "pa1", "vocalsOff": True, "preset": "75"})
    s = client.patch(f"/api/students/{a}/prefs", json={"pieceId": "pa1", "click": False}).json()["settings"]
    assert s["vocalsOff"] == ["pa1"] and s["presets"] == {"pa1": "75"} and s["metronome"] is False
    # the metronome is one choice for every song (v0.29)
    s = client.patch(f"/api/students/{a}/prefs", json={"pieceId": "pb2", "click": True}).json()["settings"]
    assert s["metronome"] is True and "click" not in s
    other = next(x for x in client.get("/api/students").json()["students"] if x["id"] == b)
    assert other["settings"]["vocalsOff"] == [] and other["settings"]["presets"] == {} and other["settings"]["metronome"] is None
    s = client.patch(f"/api/students/{a}", json={"settings": {"resetSongChoices": True}}, headers=parent).json()["settings"]
    assert s["vocalsOff"] == [] and s["presets"] == {} and s["metronome"] is None
    assert client.patch(f"/api/students/{a}/prefs", json={"pieceId": "pa1", "preset": "60"}).status_code == 422


def test_reading_aloud_is_one_choice_for_every_lesson(client, parent):
    a = client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]
    assert client.get("/api/students").json()["students"][0]["settings"]["autoRead"] is True
    s = client.patch(f"/api/students/{a}/prefs", json={"autoRead": False}).json()["settings"]
    assert s["autoRead"] is False and s["metronome"] is None
    # clearing the song choices leaves it; the parent can set it
    s = client.patch(f"/api/students/{a}", json={"settings": {"resetSongChoices": True}}, headers=parent).json()["settings"]
    assert s["autoRead"] is False
    s = client.patch(f"/api/students/{a}", json={"settings": {"autoRead": True}}, headers=parent).json()["settings"]
    assert s["autoRead"] is True
    # a song's own choices still need the song
    assert client.patch(f"/api/students/{a}/prefs", json={"vocalsOff": True}).status_code == 422


def test_favorites_follow_the_student(client, parent):
    a = client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]
    client.put(f"/api/students/{a}/favorites/pa1")
    assert client.put(f"/api/students/{a}/favorites/pb1").json()["favorites"] == ["pa1", "pb1"]
    assert client.delete(f"/api/students/{a}/favorites/pa1").json()["favorites"] == ["pb1"]
    assert client.get(f"/api/students/{a}/state").json()["favorites"] == ["pb1"]
    assert client.put(f"/api/students/{a}/favorites/..%2Fx").status_code in (404, 422)


def test_device_profile_is_set_by_the_parent(client, parent):
    d = str(uuid.uuid4())
    client.put(f"/api/devices/{d}", json={"userAgent": "iPad"})
    r = client.put(f"/api/devices/{d}", json={"profile": {"displayOffsetMs": 80, "keyboardSize": 88}}, headers=parent)
    assert r.status_code == 200
    assert client.get(f"/api/devices/{d}").json()["profile"] == {"displayOffsetMs": 80, "keyboardSize": 88}
    client.put(f"/api/devices/{d}", json={"clientVersion": "0.4.0"})           # a plain refresh keeps the profile
    assert client.get(f"/api/devices/{d}").json()["profile"]["keyboardSize"] == 88


def test_attempts_are_kept_per_student(client, parent):
    a = client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]
    b = client.post("/api/students", json={"name": "Ben", "avatar": "🐢"}, headers=parent).json()["id"]
    client.post("/api/attempts", json=attempt(studentId=a, pieceId="pa1"))
    client.post("/api/attempts", json=attempt(studentId=b, pieceId="pa2"))
    client.post("/api/attempts", json=attempt(pieceId="pa1"))                   # the parent: nobody's
    assert [x["pieceId"] for x in client.get("/api/attempts", params={"student_id": a}).json()["attempts"]] == ["pa1"]
    assert [x["pieceId"] for x in client.get("/api/attempts", params={"student_id": b}).json()["attempts"]] == ["pa2"]
    assert client.post("/api/attempts", json=attempt(studentId=str(uuid.uuid4()))).status_code == 422


def test_a_guided_session_through_the_api(client, parent):
    """M5 through the API: today's session, a concept lesson, an attempt for an item, skip, and
    the progress report; the session is resumed from any device the same day."""
    sid = client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]
    st = client.get(f"/api/students/{sid}/state").json()
    items = st["session"]["items"]
    assert items[0]["kind"] == "lesson" and items[0]["skillId"] == "t.a" and st["day"]["targetMinutes"] == 15
    skills = {s["skillId"]: s for s in st["skills"]}
    assert skills["t.a"]["status"] == "locked" and skills["t.a"]["lessonOpen"]
    r = client.post(f"/api/students/{sid}/lessons/t.a/done", json={"itemId": items[0]["id"], "seconds": 120}).json()
    assert r["status"] == "current" and r["item"]["done"]
    piece_item = next(i for i in items if i["kind"] == "piece")
    a = attempt(studentId=sid, pieceId=piece_item["pieceId"], skillId="t.a", itemId=piece_item["id"], context="guided",
                startedAt=datetime.now(timezone.utc).isoformat())
    fx = client.post("/api/attempts", json=a).json()["effects"]
    assert fx["passed"] == ["t.a"] and fx["item"]["done"] and fx["item"]["result"]["accuracyStars"] == 3.0
    # an outbox resend changes nothing
    assert client.post("/api/attempts", json=a).json()["stored"] is False
    st = client.get(f"/api/students/{sid}/state", params={"device_id": str(uuid.uuid4())}).json()
    assert {s["skillId"]: s for s in st["skills"]}["t.a"]["status"] == "passed"
    assert st["day"]["guidedSec"] == 120 + 31.5 and st["day"]["streak"] == 1
    todo = [i for i in st["session"]["items"] if not i["done"]]
    s = client.post(f"/api/students/{sid}/session/skip", json={"itemId": todo[0]["id"]}).json()["session"]
    assert s["items"][-1]["id"] == todo[0]["id"]
    p = client.get(f"/api/students/{sid}/progress").json()
    assert p["counts"]["passed"] == 1 and p["days"][-1]["practiced"] and p["recent"][0]["context"] == "guided"
    assert p["runway"]["remaining"] == 4 and p["runway"]["alert"]
