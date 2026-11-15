"""v0.51: a piano server without song tools (another family's install, arch §11.7). Its songs come
with the app ("Songs from the app"), and its parent brings them into the review list and approves
every one; a skill whose songs aren't approved yet waits for a song and holds nothing up."""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import db, main

from conftest import SKILLS, attempt, write_content
from test_library import item

CURRICULUM = ["pa1", "pa2", "pb1", "pc1", "pd1", "pe1"]
# the test map, with the first skill's notes written out, so the songs are on the map (not beyond it)
HOME_SKILLS = [{**SKILLS[0], "constraints": {"hands": ["R"], "range": {"R": ["C4", "G4"]}, "durations": [1],
                                            "timeSigs": ["4/4"], "keySigs": [0]}}, *SKILLS[1:]]
STEMS = ("100", "90", "75", "50")


def write_group(content, songs, name="curriculum", kind="curriculum", shift=0, display=None):
    """<content>/available/<name>/ as a deploy writes it from content/library/ (or a song pack)."""
    d = content / "available" / name
    (d / "media").mkdir(parents=True, exist_ok=True)
    (d / "group.json").write_text(json.dumps({"name": "Curriculum" if kind == "curriculum" else name, "kind": kind}))
    entries = []
    for i, pid in enumerate(songs):
        it = item(pid, f"Song {pid}", genre="studies", pitches=[60 + (i + shift) % 5, 62, 64, 65, 67, 65, 64, 62])
        piece = {**it["piece"], "info": it["info"], "display": display or {"fingers": None, "letters": None}}
        (d / f"{pid}.json").write_text(json.dumps(piece))
        (d / "media" / pid).mkdir(exist_ok=True)
        for k in STEMS:
            (d / "media" / pid / f"accompaniment_{k}.mp3").write_bytes(b"x" * 5)
        entries.append({"id": pid, "title": piece["title"]})
    (d / "index.json").write_text(json.dumps({"pieces": entries}))
    return d


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Another family's server: no song tools, no songs in the library, the app's songs available."""
    monkeypatch.setenv("PIANO_DB", str(tmp_path / "piano.db"))
    write_content(tmp_path / "content", skills=HOME_SKILLS, pieces=[], song_tools=False)
    write_group(tmp_path / "content", CURRICULUM, display={"fingers": False, "letters": True})
    monkeypatch.setenv("PIANO_CONTENT", str(tmp_path / "content"))
    with TestClient(main.app) as c:
        c.content = tmp_path / "content"
        yield c


@pytest.fixture()
def hp(home):
    r = home.post("/api/parent/pin", json={"pin": "2468"})
    return {"X-Parent-Token": r.json()["token"]}


def app_songs(client, hp):
    return client.get("/api/review", headers=hp).json()["appSongs"]


def test_without_song_tools_nothing_waits_for_a_dev_box(home, hp):
    assert home.get("/api/health").json()["songTools"] is False
    assert home.get("/api/parent").json()["songTools"] is False
    assert home.post("/api/skill-tokens", json={"name": "x"}, headers=hp).status_code == 403
    r = home.get("/api/skill/library", headers={"Authorization": "Bearer pmsk_anything"})
    assert r.status_code == 403 and "song tools are off" in r.json()["detail"]
    review = home.get("/api/review", headers=hp).json()
    assert review["songTools"] is False and review["items"] == []


def test_a_server_with_skill_tokens_keeps_its_song_tools(tmp_path):
    """Migration 017: our server, which already works with a dev box, keeps its song tools
    whatever its next deploy carries; a new server starts without them."""
    path = str(tmp_path / "p.db")
    db.migrate(path)
    con = db.connect(path)
    assert not con.execute("SELECT 1 FROM settings").fetchone()
    con.execute("DROP TABLE settings")
    con.execute("PRAGMA user_version = 16")
    con.execute("INSERT INTO skill_tokens (token_hash, name, created_at) VALUES ('h', 'dev box', '2026-10-01')")
    con.close()
    db.migrate(path)
    con = db.connect(path)
    assert con.execute("SELECT value FROM settings WHERE key = 'song_tools'").fetchone()["value"] == "on"
    con.close()


def test_the_app_songs_come_in_through_the_review_list(home, hp):
    g = app_songs(home, hp)
    assert [x["id"] for x in g] == ["curriculum"] and g[0]["counts"]["new"] == 6
    assert home.get("/api/library").json()["pieces"] == []          # nothing approved by itself
    r = home.post("/api/review/app-songs/curriculum/import", headers=hp).json()
    assert r["staged"] == 6 and r["refused"] == [] and r["updates"] == 0
    review = home.get("/api/review", headers=hp).json()
    assert len(review["items"]) == 6 and review["appSongs"][0]["counts"]["waiting"] == 6
    assert home.post("/api/review/app-songs/curriculum/import", headers=hp).status_code == 409   # nothing new
    # one listened to and approved by itself, then the rest all at once
    first = review["items"][0]
    assert home.post(f"/api/review/items/{first['id']}/approve", headers=hp).status_code == 200
    pkg = review["packages"][0]["id"]
    r = home.post(f"/api/review/packages/{pkg}/approve", headers=hp).json()
    assert len(r["approved"]) == 5
    lib = home.get("/api/library").json()["pieces"]
    assert sorted(e["id"] for e in lib) == sorted(CURRICULUM)
    assert not any(e["new"] for e in lib)                           # the app's own songs: no New badge
    assert app_songs(home, hp)[0]["counts"]["unchanged"] == 6
    # the helper choices the songs came with
    assert home.get("/api/library/pieces/pa1").json()["display"] == {"fingers": False, "letters": True}
    assert home.post(f"/api/review/packages/{pkg}/approve", headers=hp).status_code == 404


def test_a_newer_version_from_the_app_is_an_update_the_parent_decides_on(home, hp):
    home.post("/api/review/app-songs/curriculum/import", headers=hp)
    pkg = home.get("/api/review", headers=hp).json()["packages"][0]["id"]
    home.post(f"/api/review/packages/{pkg}/approve", headers=hp)
    write_group(home.content, CURRICULUM, shift=1)                  # a later release changed every song's notes
    g = app_songs(home, hp)[0]
    assert g["counts"]["update"] == 6
    r = home.post("/api/review/app-songs/curriculum/import", headers=hp).json()
    assert r["staged"] == 6 and r["updates"] == 6
    items = home.get("/api/review", headers=hp).json()["items"]
    assert all(it["live"] == it["pieceId"] for it in items) and items[0]["changes"]["bars"]
    # the parent keeps one song as it was: that version isn't offered again
    keep = next(it for it in items if it["pieceId"] == "pa1")
    assert home.post(f"/api/review/items/{keep['id']}/discard", headers=hp).status_code == 200
    states = {s["id"]: s["state"] for s in app_songs(home, hp)[0]["songs"]}
    assert "pa1" not in states                                      # declined: not listed as new or changed
    assert app_songs(home, hp)[0]["counts"]["declined"] == 1
    before = home.get("/api/library/pieces/pb1").json()["notation"]["notes"][0]["pitch"]
    upd = next(it for it in items if it["pieceId"] == "pb1")
    assert home.post(f"/api/review/items/{upd['id']}/approve", headers=hp).json()["updated"]
    assert home.get("/api/library/pieces/pb1").json()["notation"]["notes"][0]["pitch"] != before
    # a still newer version of the declined song is offered again
    write_group(home.content, CURRICULUM, shift=2)
    assert {s["id"]: s["state"] for s in app_songs(home, hp)[0]["songs"]}["pa1"] == "update"


def test_a_song_the_parent_deleted_never_comes_back(home, hp):
    home.post("/api/review/app-songs/curriculum/import", headers=hp)
    review = home.get("/api/review", headers=hp).json()
    never = next(it for it in review["items"] if it["pieceId"] == "pc1")
    home.post(f"/api/review/items/{never['id']}/never", headers=hp, json={})
    home.post(f"/api/review/packages/{review['packages'][0]['id']}/approve", headers=hp)
    home.post("/api/library/songs/pd1/delete", headers=hp, json={})
    g = app_songs(home, hp)[0]
    assert g["counts"]["deleted"] == 2 and g["counts"]["new"] == 0
    write_group(home.content, CURRICULUM, shift=1)                  # even a newer version
    g = app_songs(home, hp)[0]
    assert g["counts"]["deleted"] == 2 and {s["id"] for s in g["songs"]} == {"pa1", "pa2", "pb1", "pe1"}


def test_needs_improvement_is_refused_without_song_tools(home, hp):
    home.post("/api/review/app-songs/curriculum/import", headers=hp)
    review = home.get("/api/review", headers=hp).json()
    it = review["items"][0]
    assert home.post(f"/api/review/items/{it['id']}/improve", headers=hp, json={"feedback": "too fast"}).status_code == 403
    home.post(f"/api/review/packages/{review['packages'][0]['id']}/approve", headers=hp)
    assert home.post("/api/library/pieces/pa1/improve", headers=hp, json={"feedback": "too fast"}).status_code == 403
    assert home.post("/api/library/improve", headers=hp, json={"pieces": ["pa1"], "feedback": "too fast"}).status_code == 403


def test_with_song_tools_there_are_no_app_songs(client, parent):
    """Our server: its songs come from the dev box, so a bundle (there should be none) isn't offered."""
    review = client.get("/api/review", headers=parent).json()
    assert review["songTools"] is True and review["appSongs"] == []


def state(client, sid):
    return client.get(f"/api/students/{sid}/state").json()


def fresh_day(client, sid):
    con = db.connect()                    # today's session was planned before the approvals
    con.execute("DELETE FROM sessions")
    con.close()
    return state(client, sid)


def approve_all_but(client, hp, *keep):
    client.post("/api/review/app-songs/curriculum/import", headers=hp)
    for it in client.get("/api/review", headers=hp).json()["items"]:
        if it["pieceId"] not in keep:
            client.post(f"/api/review/items/{it['id']}/approve", headers=hp)


def test_day_one_with_no_songs_says_they_are_waiting(home, hp):
    sid = home.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=hp).json()["id"]
    st = state(home, sid)
    assert all(s["waiting"] for s in st["skills"])                  # nothing approved yet
    items = st["session"]["items"]
    assert [i["kind"] for i in items] == ["needed"] and items[0]["done"]   # and no "Your pick" with no songs
    assert items[0]["title"].startswith("Waiting for songs") and not st["session"]["endOfContent"]
    # the parent approves the songs the same day: the next load plans the day again, with them
    approve_all_but(home, hp)
    items = state(home, sid)["session"]["items"]
    assert [(i["kind"], i["skillId"]) for i in items][:2] == [("lesson", "t.a"), ("piece", "t.a")]
    assert any(i["kind"] == "pick" for i in items) and not any(i["kind"] == "needed" for i in items)


def test_a_skill_waiting_for_a_song_holds_nothing_up(home, hp):
    """t.b's only song (pb1) isn't approved: t.b waits, and t.e (after t.b) opens once t.a, before
    t.b, is passed, never sooner."""
    sid = home.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=hp).json()["id"]
    approve_all_but(home, hp, "pb1")
    st = fresh_day(home, sid)
    skills = {s["skillId"]: s for s in st["skills"]}
    assert skills["t.b"]["waiting"] and not any(skills[x]["waiting"] for x in ("t.a", "t.c", "t.d", "t.e"))
    assert not skills["t.e"]["lessonOpen"]                          # t.a isn't passed: no skipping ahead
    items = st["session"]["items"]
    assert not any(i["skillId"] == "t.b" for i in items)
    item = next(i for i in items if i["kind"] == "piece" and i["skillId"] == "t.a")
    home.post(f"/api/students/{sid}/lessons/t.a/done", json={})
    a = attempt(studentId=sid, pieceId=item["pieceId"], skillId="t.a", itemId=item["id"], context="guided",
                startedAt=datetime.now(timezone.utc).isoformat())
    assert home.post("/api/attempts", json=a).json()["effects"]["passed"] == ["t.a"]
    skills = {s["skillId"]: s for s in fresh_day(home, sid)["skills"]}
    assert skills["t.e"]["lessonOpen"] and skills["t.c"]["lessonOpen"] and skills["t.b"]["status"] == "locked"
    items = fresh_day(home, sid)["session"]["items"]
    assert {"t.c", "t.e"} <= {i["skillId"] for i in items if i["reason"] == "New"}
    assert not any(i["skillId"] == "t.b" for i in items)
    # its song approved at last: t.b is taught like any other skill
    pb1 = next(it for it in home.get("/api/review", headers=hp).json()["items"] if it["pieceId"] == "pb1")
    home.post(f"/api/review/items/{pb1['id']}/approve", headers=hp)
    st = fresh_day(home, sid)
    assert not {s["skillId"]: s for s in st["skills"]}["t.b"]["waiting"]
    assert ("lesson", "t.b") in [(i["kind"], i["skillId"]) for i in st["session"]["items"]]


def test_chord_symbols_drawn_as_grace_notes_are_taken_out_of_the_library(tmp_path, monkeypatch):
    """Migration 018: a library song whose grace notes all sit on its chord symbols' beats (the
    converter's old mistake) loses them, with its version worked out again; one with a grace note
    anywhere else is left as it is."""
    import importlib.util
    from app import content
    path = str(tmp_path / "p.db")
    db.migrate(path)
    con = db.connect(path)
    nota = lambda graces: {"notes": [{"pitch": 60, "start": 0.0}], "chordSymbols": [{"beat": 0, "symbol": "C"}, {"beat": 4, "symbol": "G"}],
                           "graces": graces}
    g = lambda start, pitch: {"pitch": pitch, "start": start}
    pieces = {"bogus": nota([g(0.0, 48), g(0.0, 52), g(4.0, 55)]), "real": nota([g(0.0, 48), g(2.5, 79)])}
    for pid, n in pieces.items():
        d = tmp_path / "library" / pid
        d.mkdir(parents=True)
        (d / "piece.json").write_text(json.dumps({"id": pid, "notation": n, "contentVersion": "old"}))
        con.execute("INSERT INTO library (piece_id, song, title, genre, fingerprint, info, entry, approved_at) "
                    "VALUES (?, ?, ?, 'kids', '[]', '{}', ?, 't')",
                    (pid, pid, pid, json.dumps({"id": pid, "contentVersion": "old"})))
    spec = importlib.util.spec_from_file_location("m018", db.MIGRATIONS / "018_chord_symbol_graces.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setenv("PIANO_DB", path)
    m.run(con, tmp_path)
    bogus = json.loads((tmp_path / "library/bogus/piece.json").read_text())
    real = json.loads((tmp_path / "library/real/piece.json").read_text())
    assert bogus["notation"]["graces"] == [] and bogus["contentVersion"] == content.song_version(bogus["notation"])
    assert len(real["notation"]["graces"]) == 2 and real["contentVersion"] == "old"
    entry = json.loads(con.execute("SELECT entry FROM library WHERE piece_id = 'bogus'").fetchone()["entry"])
    assert entry["contentVersion"] == bogus["contentVersion"]
    con.close()
