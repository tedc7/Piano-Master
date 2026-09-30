"""M7: the Skill API's intake, staging and the parent's review, the library, the deleted list,
and each child's genre and song rules (arch §10.1, §10.7-§10.9)."""
import copy

import pytest

from app import content

MELODY = [60, 62, 64, 65, 67, 69, 67, 65, 64, 62, 60, 64, 67, 72, 71, 69]


def notation(pitches=MELODY):
    notes = [{"pitch": p, "start": float(i), "duration": 1.0, "staff": 0, "hand": "R", "voice": 1, "isMelody": True,
              "spelled": {"step": "C", "alter": 0, "octave": 4}} for i, p in enumerate(pitches)]
    bars = len(pitches) // 4
    return {"header": {"keySig": 0, "timeSig": "4/4", "barLength": 4, "tempo": 100, "pickupBeats": 0,
                       "range": [min(pitches), max(pitches)], "staves": ["treble"]},
            "measures": [{"number": i + 1, "start": 4.0 * i, "duration": 4.0} for i in range(bars)],
            "notes": notes, "lyrics": [], "chordSymbols": [], "graces": [],
            "playbackOrder": [{"measure": i, "verse": 1, "pass": 1} for i in range(bars)], "phrases": [0.0, 8.0], "length": 4.0 * bars}


def item(pid="new-song", title="New Song", genre="kids", pitches=MELODY, media=True, **info):
    piece = {"id": pid, "title": title, "composer": "Trad.", "kind": "library", "genre": genre, "level": "Level 1", "hands": "R",
             "song": pid, "notation": notation(pitches), "media": None}
    if media:
        piece["media"] = {"engine": "test", "take": "s1", "padBeats": 1.0, "bpm": 100,
                          "presets": {k: {"ratio": int(k) / 100, "accompaniment": {"url": f"media/{pid}/accompaniment_{k}.mp3", "bytes": 5}}
                                      for k in ("100", "90", "75", "50")}}
    return {"piece": piece, "info": {"license": {"composition": "public-domain", "edition": "public-domain"},
                                     "source": {"site": "test", "url": "https://example.org", "id": f"src-{pid}"}, **info}}


@pytest.fixture()
def skill(client, parent):
    r = client.post("/api/skill-tokens", json={"name": "media"}, headers=parent)
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}


def stage(client, skill, *items, upload=True):
    r = client.post("/api/skill/packages", json={"name": "batch", "notes": "test batch", "items": list(items)}, headers=skill)
    assert r.status_code == 201, r.text
    pkg = r.json()
    for it in pkg["items"]:
        for m in it["media"] if upload else []:
            u = client.put(f"/api/skill/packages/{pkg['id']}/items/{it['itemId']}/media/{m['file']}", content=b"x" * m["bytes"], headers=skill)
            assert u.status_code == 200, u.text
    return pkg, client.post(f"/api/skill/packages/{pkg['id']}/submit", headers=skill).json()


def test_skill_api_needs_a_token_and_cannot_approve(client, skill):
    assert client.get("/api/skill/library").status_code == 401
    assert client.get("/api/skill/library", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/skill/library", headers=skill).status_code == 200
    pkg, _ = stage(client, skill, item())
    iid = pkg["items"][0]["itemId"]
    assert client.post(f"/api/review/items/{iid}/approve", headers=skill).status_code == 401
    assert client.get("/api/review", headers=skill).status_code == 401


def test_intake_rejects_bad_pieces_with_a_report(client, skill):
    bad_license = item("nc-song", pitches=[60, 67, 64, 72, 71, 62, 65, 69, 60, 67, 64, 72, 71, 62, 65, 69])
    bad_license["info"]["license"]["edition"] = "CC BY-NC-SA 4.0"
    lesson = item("lesson-song", genre="lesson-pieces", pitches=[72, 71, 69, 67, 65, 64, 62, 60, 72, 71, 69, 67, 65, 64, 62, 60])
    pkg, sub = stage(client, skill, item(), bad_license, lesson)
    by = {i["pieceId"]: i for i in pkg["items"]}
    assert by["new-song"]["accepted"] and not by["nc-song"]["accepted"] and not by["lesson-song"]["accepted"]
    assert "not an accepted license" in by["nc-song"]["errors"][0]
    assert sub["staged"] == 1


def test_missing_stems_keep_a_song_out_of_staging(client, skill):
    _, sub = stage(client, skill, item(), upload=False)
    assert sub["staged"] == 0 and "stems not uploaded" in sub["items"][0]["errors"][0]


def test_a_stem_of_the_wrong_size_is_refused(client, skill):
    r = client.post("/api/skill/packages", json={"name": "b", "items": [item()]}, headers=skill).json()
    i = r["items"][0]
    u = client.put(f"/api/skill/packages/{r['id']}/items/{i['itemId']}/media/accompaniment_100.mp3", content=b"xx", headers=skill)
    assert u.status_code == 422


def test_review_approve_and_the_library(client, parent, skill):
    pkg, sub = stage(client, skill, item(), item("other-song", "Other", pitches=[72, 69, 65, 62, 60, 64, 67, 71, 72, 69, 65, 62, 60, 64, 67, 71]))
    assert sub["staged"] == 2
    # staged songs are the parent's only: not in the library, not readable without the parent
    assert client.get("/api/library").json()["pieces"] == []
    flat = client.get("/api/review", headers=parent).json()["items"]
    assert [(i["pieceId"], i["package"]) for i in flat] == [("new-song", "batch"), ("other-song", "batch")]
    rv = client.get("/api/review", headers=parent).json()["packages"]
    assert [p["name"] for p in rv] == ["batch"] and len(rv[0]["items"]) == 2
    first = rv[0]["items"][0]
    assert client.get(f"/api/review/items/{first['id']}/piece").status_code == 401
    p = client.get(f"/api/review/items/{first['id']}/piece", headers=parent).json()
    assert p["id"].startswith("staged--") and p["media"]["presets"]["100"]["accompaniment"]["url"].startswith("/api/review/items/")
    assert client.get(p["media"]["presets"]["100"]["accompaniment"]["url"], headers=parent).content == b"xxxxx"
    # approve one: the other keeps waiting until the parent decides on it (v0.23)
    other = rv[0]["items"][1]
    assert client.post(f"/api/review/items/{first['id']}/approve", headers=parent).json() == {"approved": "new-song"}
    left = client.get("/api/review", headers=parent).json()["packages"]
    assert [i["pieceId"] for i in left[0]["items"]] == ["other-song"]
    assert client.post(f"/api/review/items/{first['id']}/approve", headers=parent).status_code == 404     # decided already
    assert client.post(f"/api/review/items/{other['id']}/never", json={}, headers=parent).json() == {"never": "other-song"}
    idx = client.get("/api/library").json()
    assert [e["id"] for e in idx["pieces"]] == ["new-song"] and idx["pieces"][0]["new"] and idx["version"]
    lp = client.get("/api/library/pieces/new-song").json()
    url = lp["media"]["presets"]["50"]["accompaniment"]["url"]
    assert url == "/api/library/media/new-song/accompaniment_50.mp3"
    r = client.get(url, headers={"Range": "bytes=0-1"})
    assert r.status_code == 206 and r.content == b"xx"          # iOS audio needs range requests
    assert client.get("/api/review", headers=parent).json()["packages"] == []
    # the engine sees it; the version carries the library's
    c = content.load()
    assert "new-song" in c.pieces and c.version.endswith("+" + idx["version"]) and c.notation("new-song")["length"] == 16.0
    # never allowed: intake refuses it next time
    again = client.post("/api/skill/packages", json={"name": "b2", "items": [item("other-song-2", "Other", pitches=[72, 69, 65, 62, 60, 64, 67, 71, 72, 69, 65, 62, 60, 64, 67, 71])]},
                        headers=skill).json()
    assert not again["items"][0]["accepted"] and "deleted by the parent" in again["items"][0]["errors"][0]


def approve_all(client, parent, skill, *items):
    stage(client, skill, *items)
    for i in client.get("/api/review", headers=parent).json()["packages"][0]["items"]:
        assert client.post(f"/api/review/items/{i['id']}/approve", headers=parent).status_code == 200


def test_intake_catches_duplicates_by_melody(client, parent, skill):
    approve_all(client, parent, skill, item())
    dup = client.post("/api/skill/packages", json={"name": "b", "items": [item("copy-song", "Copy")]}, headers=skill).json()["items"][0]
    assert not dup["accepted"] and "the same song as New Song" in dup["errors"][0]
    # another arrangement of the same song is fine
    arr = item("new-song-easy", "New Song (easy)")
    arr["piece"]["song"] = "new-song"
    ok = client.post("/api/skill/packages", json={"name": "b", "items": [arr]}, headers=skill).json()["items"][0]
    assert ok["accepted"], ok


def test_rules_block_other_genres_until_allowed(client, parent, skill):
    approve_all(client, parent, skill, item())
    kid = client.post("/api/students", json={"name": "Cleo", "avatar": "🦊"}, headers=parent).json()["id"]
    lib = content.load()
    from app import db, library
    con = db.connect()
    try:
        assert "new-song" not in library.content_for(con, kid, lib).pieces          # kids' songs start blocked
        assert "pa1" in library.content_for(con, kid, lib).pieces                   # lesson pieces are always allowed
        assert client.put(f"/api/students/{kid}/rules/genres/kids", json={"allowed": True}, headers=parent).status_code == 200
        assert "new-song" in library.content_for(con, kid, lib).pieces
        client.put(f"/api/students/{kid}/rules/songs/new-song", json={"allowed": False}, headers=parent)   # a song rule overrides
        assert "new-song" not in library.content_for(con, kid, lib).pieces
    finally:
        con.close()
    assert client.get(f"/api/students/{kid}/rules").json()["songs"] == {"new-song": False}
    assert client.put(f"/api/students/{kid}/rules/genres/lesson-pieces", json={"allowed": False}, headers=parent).status_code == 422
    rules = client.get("/api/rules", headers=parent).json()
    assert "kids" in rules["genres"] and rules["students"][0]["genres"] == {"kids": True}
    assert client.put(f"/api/students/{kid}/rules/genres/kids", json={"allowed": True}).status_code == 401


def test_deleting_a_song_moves_it_to_the_review_areas_deleted_songs(client, parent, skill):
    approve_all(client, parent, skill, item())
    assert client.post("/api/library/songs/new-song/delete", json={"reason": "too hard"}).status_code == 401
    d = client.post("/api/library/songs/new-song/delete", json={"reason": "too hard"}, headers=parent).json()
    assert d["deleted"] == ["new-song"] and client.get("/api/library").json()["pieces"] == []
    assert client.get("/api/library/pieces/new-song").status_code == 404
    gone = client.get("/api/review", headers=parent).json()["deleted"]
    assert [(g["pieceId"], g["deletedFrom"], g["deletedReason"], g["hasFiles"]) for g in gone] == [("new-song", "library", "too hard", True)]
    # still listenable, and refused by intake
    assert client.get(f"/api/review/items/{gone[0]['id']}/piece", headers=parent).status_code == 200
    again = client.post("/api/skill/packages", json={"name": "b", "items": [item("new-song-2", "New Song")]}, headers=skill).json()["items"][0]
    assert not again["accepted"] and "deleted by the parent" in again["errors"][0]
    assert [x["pieceId"] for x in client.get("/api/skill/deleted", headers=skill).json()["deleted"]] == ["new-song"]
    # back to review, then approved again: in the library once more, with its stems
    assert client.post(f"/api/review/items/{gone[0]['id']}/restore", headers=parent).json() == {"waiting": "new-song"}
    waiting = client.get("/api/review", headers=parent).json()
    assert [i["pieceId"] for i in waiting["items"]] == ["new-song"] and waiting["deleted"] == []
    client.post(f"/api/review/items/{waiting['items'][0]['id']}/approve", headers=parent)
    assert client.get("/api/library/media/new-song/accompaniment_100.mp3").status_code == 200
    # delete again, then forget it: intake takes it once more
    client.post("/api/library/songs/new-song/delete", json={}, headers=parent)
    gone = client.get("/api/review", headers=parent).json()["deleted"]
    assert client.post(f"/api/review/items/{gone[0]['id']}/forget", headers=parent).json() == {"forgotten": "new-song"}
    assert client.get("/api/review", headers=parent).json()["deleted"] == []
    ok = client.post("/api/skill/packages", json={"name": "b", "items": [copy.deepcopy(item())]}, headers=skill).json()["items"][0]
    assert ok["accepted"], ok


def test_a_deleted_song_can_be_sent_for_improvement(client, parent, skill):
    pkg, _ = stage(client, skill, item())
    iid = pkg["items"][0]["itemId"]
    client.post(f"/api/review/items/{iid}/never", json={}, headers=parent)
    rv = client.get("/api/review", headers=parent).json()
    assert rv["items"] == [] and rv["deleted"][0]["deletedFrom"] == "review"
    client.post(f"/api/review/items/{iid}/improve", json={"feedback": "Slower, and in G."}, headers=parent)
    assert [f["feedback"] for f in client.get("/api/skill/feedback", headers=skill).json()["feedback"]] == ["Slower, and in G."]
    _, sub = stage(client, skill, item())                        # the fix is accepted, and replaces it
    assert sub["staged"] == 1 and sub["items"][0]["replaces"] == iid


def test_student_state_offers_only_allowed_songs(client, parent, skill):
    approve_all(client, parent, skill, item())
    kid = client.post("/api/students", json={"name": "Max", "avatar": "🐯"}, headers=parent).json()["id"]
    s = client.get(f"/api/students/{kid}/state").json()
    assert s["contentVersion"].count("+") == 1


def test_tokens_are_listed_and_revoked(client, parent, skill):
    toks = client.get("/api/skill-tokens", headers=parent).json()["tokens"]
    assert [t["name"] for t in toks] == ["media"]
    assert client.delete(f"/api/skill-tokens/{toks[0]['id']}", headers=parent).status_code == 200
    assert client.get("/api/skill/library", headers=skill).status_code == 401


def test_needs_improvement_feedback_goes_to_the_skill_and_the_fix_replaces_it(client, parent, skill):
    pkg, _ = stage(client, skill, item())
    iid = pkg["items"][0]["itemId"]
    assert client.post(f"/api/review/items/{iid}/improve", json={"feedback": ""}, headers=parent).status_code == 422
    r = client.post(f"/api/review/items/{iid}/improve", json={"feedback": "Too fast: the words run together."}, headers=parent)
    assert r.json() == {"sentBack": "new-song"}
    rv = client.get("/api/review", headers=parent).json()
    assert rv["packages"] == [] and rv["sentBack"][0]["feedback"] == "Too fast: the words run together."
    # the parent can still listen to what they sent back; nothing reaches the library
    assert client.get(f"/api/review/items/{iid}/piece", headers=parent).status_code == 200
    assert client.get("/api/library").json()["pieces"] == []
    fb = client.get("/api/skill/feedback", headers=skill).json()["feedback"]
    assert [(f["pieceId"], f["feedback"]) for f in fb] == [("new-song", "Too fast: the words run together.")]
    # the fixed song, resubmitted under the same id, replaces it and carries the feedback
    _, sub = stage(client, skill, item())
    assert sub["items"][0]["replaces"] == iid
    rv = client.get("/api/review", headers=parent).json()
    new = rv["packages"][0]["items"][0]
    assert rv["sentBack"] == [] and new["previousFeedback"]["feedback"] == "Too fast: the words run together."
    assert client.get("/api/skill/feedback", headers=skill).json()["feedback"] == []
    assert client.get(f"/api/review/items/{iid}/piece", headers=parent).status_code == 404


def test_a_song_waiting_for_review_cant_be_submitted_twice(client, skill):
    stage(client, skill, item())
    again = client.post("/api/skill/packages", json={"name": "b", "items": [item()]}, headers=skill).json()["items"][0]
    assert not again["accepted"] and "already waiting" in again["errors"][0]
