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
    # a song written for the curriculum comes the same way (v0.27): our own music
    ours = item("our-study", genre="studies", pitches=[72, 71, 69, 67, 65, 64, 62, 60, 72, 71, 69, 67, 65, 64, 62, 60])
    ours["info"]["license"] = {"composition": "original", "edition": "original"}
    pkg, sub = stage(client, skill, item(), bad_license, ours)
    by = {i["pieceId"]: i for i in pkg["items"]}
    assert by["new-song"]["accepted"] and not by["nc-song"]["accepted"] and by["our-study"]["accepted"]
    assert "not an accepted license" in by["nc-song"]["errors"][0]
    assert sub["staged"] == 2


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
    assert added(client) == []
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
    assert added(client) == ["new-song"] and next(e for e in idx["pieces"] if e["id"] == "new-song")["new"] and idx["version"]
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


def added(client):
    """The library's songs beyond the test map's (the seed)."""
    from conftest import PIECES
    seed = {p["id"] for p in PIECES}
    return [e["id"] for e in client.get("/api/library").json()["pieces"] if e["id"] not in seed]


def test_the_seed_comes_in_once_as_approved_and_never_new(client, parent):
    from conftest import PIECES
    from app import library
    idx = client.get("/api/library").json()["pieces"]
    assert {e["id"] for e in idx} == {p["id"] for p in PIECES} and not any(e["new"] for e in idx)
    assert library.adopt_seed() == []                       # a later start brings nothing
    client.post("/api/library/songs/pa1/delete", json={}, headers=parent)
    assert library.adopt_seed() == []                       # nor a song the parent deleted


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
        assert "pa1" in library.content_for(con, kid, lib).pieces                   # the map's practice songs are allowed
        assert "free1" not in library.content_for(con, kid, lib).pieces             # its genre (studies) isn't
        assert client.put(f"/api/students/{kid}/rules/genres/kids", json={"allowed": True}, headers=parent).status_code == 200
        assert "new-song" in library.content_for(con, kid, lib).pieces
        client.put(f"/api/students/{kid}/rules/songs/new-song", json={"allowed": False}, headers=parent)   # a song rule overrides
        assert "new-song" not in library.content_for(con, kid, lib).pieces
    finally:
        con.close()
    r = client.get(f"/api/students/{kid}/rules").json()
    assert r["songs"] == {"new-song": False} and "pa1" in r["curriculum"] and "free1" not in r["curriculum"]
    client.put(f"/api/students/{kid}/rules/songs/pa1", json={"allowed": False}, headers=parent)    # even a practice song
    con = db.connect()
    try:
        assert "pa1" not in library.content_for(con, kid, content.load()).pieces
    finally:
        con.close()
    rules = client.get("/api/rules", headers=parent).json()
    assert "kids" in rules["genres"] and rules["students"][0]["genres"] == {"kids": True}
    assert client.put(f"/api/students/{kid}/rules/genres/kids", json={"allowed": True}).status_code == 401


def test_deleting_a_song_moves_it_to_the_review_areas_deleted_songs(client, parent, skill):
    approve_all(client, parent, skill, item())
    assert client.post("/api/library/songs/new-song/delete", json={"reason": "too hard"}).status_code == 401
    d = client.post("/api/library/songs/new-song/delete", json={"reason": "too hard"}, headers=parent).json()
    assert d["deleted"] == ["new-song"] and added(client) == []
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
    assert added(client) == []
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


def test_a_map_change_re_analyses_the_library(client, parent, skill, tmp_path):
    """§6.10: a song beyond the map when it was approved unlocks once a deploy adds a skill that
    allows it, and Content and analysis lists it."""
    from conftest import SKILLS, PIECES, write_content
    stage(client, skill, item())
    iid = client.get("/api/review", headers=parent).json()["items"][0]["id"]
    client.post(f"/api/review/items/{iid}/approve", headers=parent)
    lib = {p["id"]: p for p in client.get("/api/library").json()["pieces"]}
    assert lib["new-song"]["beyondMap"] and lib["new-song"]["skillId"] is None
    first = client.get("/api/library/analysis", headers=parent).json()
    assert first["changes"] == []                     # analysed at approval, against this map

    reach = {"id": "t.f", "name": "Skill F", "sequence": 60, "track": "reading", "prerequisites": ["t.a"], "pieces": [],
             "constraints": {"hands": ["R"], "range": {"R": ["C4", "C5"]}, "durations": [1], "timeSigs": ["4/4"],
                             "keySigs": [0], "intervals": [1, 2, 3, 4, 5, 7, 8]}}
    write_content(tmp_path / "content", skills=SKILLS + [reach], pieces=PIECES, version="test2")
    after = client.get("/api/library/analysis", headers=parent).json()
    assert after["mapHash"] != first["mapHash"] and after["songs"] == 1
    assert [c["pieceId"] for c in after["changes"]] == ["new-song"]
    assert after["changes"][0]["after"] == {"requiredSkills": ["t.f"], "beyondMap": []}
    lib = {p["id"]: p for p in client.get("/api/library").json()["pieces"]}
    assert lib["new-song"]["requiredSkills"] == ["t.f"] and lib["new-song"]["skillId"] == "t.f"
    assert client.get("/api/library/pieces/new-song").json()["requiredSkills"] == ["t.f"]
    # the same map again: nothing to do, and the record stays
    assert client.get("/api/library/analysis", headers=parent).json()["analysedAt"] == after["analysedAt"]
    assert client.get("/api/library/analysis").status_code == 401


FIXED = [60, 62, 64, 65, 64, 64, 67, 65, 64, 62, 60, 64, 67, 72, 71, 69]          # bar 2 changed (67 69 -> 64 64)


def test_updating_a_live_song(client, parent, skill):
    """v0.27: Needs improvement on a library song; the fix comes back under the same id as an update,
    with what changed; approving it replaces the live song in place, discarding keeps it."""
    approve_all(client, parent, skill, item())
    before = next(e for e in client.get("/api/library").json()["pieces"] if e["id"] == "new-song")
    # without a request, the same id is refused
    r = client.post("/api/skill/packages", json={"name": "b", "items": [item(pitches=FIXED)]}, headers=skill).json()["items"][0]
    assert not r["accepted"] and "already in the library" in r["errors"][0]
    # the parent asks; one request at a time
    assert client.post("/api/library/pieces/new-song/improve", json={"feedback": "Bar 2: G A should be E E"}).status_code == 401
    asked = client.post("/api/library/pieces/new-song/improve", json={"feedback": "Bar 2: G A should be E E"}, headers=parent)
    assert asked.status_code == 201 and asked.json()["update"]["status"] == "needs-work"
    assert client.post("/api/library/pieces/new-song/improve", json={"feedback": "again"}, headers=parent).status_code == 409
    assert client.post("/api/library/pieces/nope/improve", json={"feedback": "what?"}, headers=parent).status_code == 404
    fb = client.get("/api/skill/feedback", headers=skill).json()["feedback"]
    assert [(f["pieceId"], f["live"], f["feedback"]) for f in fb] == [("new-song", True, "Bar 2: G A should be E E")]
    # the fix: staged as an update, beside the note, with what changed; the children keep the live song
    _, sub = stage(client, skill, item(pitches=FIXED))
    assert sub["staged"] == 1
    waiting_items = client.get("/api/review", headers=parent).json()["items"]
    up = next(i for i in waiting_items if i["pieceId"] == "new-song")
    assert up["live"] == "new-song" and up["previousFeedback"]["feedback"] == "Bar 2: G A should be E E"
    assert up["changes"]["bars"] == [2] and up["changes"]["tempo"] == [100, 100] and not up["changes"]["media"]
    assert client.get("/api/library/pieces/new-song").json()["notation"]["notes"][4]["pitch"] == 67      # still live
    assert client.get("/api/library/pieces/new-song/improve", headers=parent).json()["update"]["status"] == "staged"
    assert client.post(f"/api/review/items/{up['id']}/never", json={}, headers=parent).status_code == 409   # not for an update
    # approved: replaced in place, the same song (first approval kept, so no New badge again)
    assert client.post(f"/api/review/items/{up['id']}/approve", headers=parent).json() == {"approved": "new-song", "updated": True}
    after = next(e for e in client.get("/api/library").json()["pieces"] if e["id"] == "new-song")
    assert after["approvedAt"] == before["approvedAt"] and after["updatedAt"] and after["contentVersion"] != before["contentVersion"]
    assert client.get("/api/library/pieces/new-song").json()["notation"]["notes"][4]["pitch"] == 64
    assert client.get("/api/library/pieces/new-song/improve", headers=parent).json()["update"] is None
    # discard: the live song stays as it is
    client.post("/api/library/pieces/new-song/improve", json={"feedback": "Slower, please"}, headers=parent)
    item_fast = item(pitches=FIXED)
    item_fast["piece"]["notation"]["header"]["tempo"] = 80
    stage(client, skill, item_fast)
    up = next(i for i in client.get("/api/review", headers=parent).json()["items"] if i["pieceId"] == "new-song")
    assert up["changes"]["tempo"] == [100, 80]
    assert client.post(f"/api/review/items/{up['id']}/discard", headers=parent).json() == {"kept": "new-song"}
    assert client.get("/api/library/pieces/new-song").json()["notation"]["header"]["tempo"] == 100
    assert not any(i["pieceId"] == "new-song" for i in client.get("/api/review", headers=parent).json()["items"])
    # deleting the song cancels a request still waiting for its fix
    client.post("/api/library/pieces/new-song/improve", json={"feedback": "One more thing"}, headers=parent)
    client.post("/api/library/songs/new-song/delete", json={}, headers=parent)
    assert client.get("/api/skill/feedback", headers=skill).json()["feedback"] == []


def test_diagnostics_reads_only_attempts_on_the_current_notes(client, parent):
    from conftest import attempt
    from datetime import date
    from app import db, diagnostics
    sid = client.post("/api/students", json={"name": "Ada", "avatar": "🦊"}, headers=parent).json()["id"]
    for v in ("lib-old", "lib-new"):
        client.post("/api/attempts", json=attempt(studentId=sid, pieceId="pa1", contentVersion=v, startedAt=f"{date.today()}T10:00:00.000Z"))
    con = db.connect()
    try:
        assert len(diagnostics.load_obs(con, sid, date.today())) == 2
        assert len(diagnostics.load_obs(con, sid, date.today(), versions={"pa1": "lib-new"})) == 1
    finally:
        con.close()


def test_two_of_our_own_studies_are_never_duplicates(client, parent, skill):
    """v0.27: studies on a few keys share their melody's shape by design; the duplicate check is for imports."""
    mine = lambda pid: {**item(pid, pid.title()), "info": {**item(pid)["info"], "license": {"composition": "original", "edition": "original"}}}
    approve_all(client, parent, skill, mine("study-one"))
    twin = client.post("/api/skill/packages", json={"name": "b", "items": [mine("study-two")]}, headers=skill).json()["items"][0]
    assert twin["accepted"], twin
    copy = client.post("/api/skill/packages", json={"name": "b", "items": [item("copied-song", "Copied")]}, headers=skill).json()["items"][0]
    assert not copy["accepted"] and "the same song as" in copy["errors"][0]          # an import still is


def test_a_songs_finger_numbers_and_letters_are_switched_for_every_child(client, parent):
    assert client.get("/api/library/pieces/pa1").json()["display"] == {"fingers": None, "letters": None}
    assert client.put("/api/library/pieces/pa1/display", json={"letters": True}).status_code == 401
    r = client.put("/api/library/pieces/pa1/display", json={"letters": True}, headers=parent)
    assert r.json()["display"] == {"fingers": None, "letters": True}
    client.put("/api/library/pieces/pa1/display", json={"fingers": False}, headers=parent)
    assert client.get("/api/library/pieces/pa1").json()["display"] == {"fingers": False, "letters": True}
    client.put("/api/library/pieces/pa1/display", json={"letters": None}, headers=parent)      # back to the default
    assert client.get("/api/library/pieces/pa1").json()["display"] == {"fingers": False, "letters": None}
    assert client.put("/api/library/pieces/nope/display", json={"fingers": True}, headers=parent).status_code == 404


def test_an_approved_song_exported_to_the_repo_seeds_a_new_install(client, parent, skill, tmp_path, monkeypatch):
    """tools/library_export.py files the approved songs in content/library/ (v0.31); a new server's
    first start adopts them as approved, with their stems and the parent's helper choices."""
    import json
    from fastapi.testclient import TestClient
    from app import main
    from conftest import write_content
    approve_all(client, parent, skill, item())
    assert client.put("/api/library/pieces/new-song/display", json={"letters": True}, headers=parent).status_code == 200
    assert client.get("/api/skill/library/new-song").status_code == 401
    got = client.get("/api/skill/library/new-song", headers=skill).json()
    assert got["info"]["license"]["composition"] == "public-domain" and got["display"] == {"fingers": None, "letters": True}
    assert [f["file"] for f in got["files"]] == [f"accompaniment_{k}.mp3" for k in ("100", "50", "75", "90")]
    # the export's files, as the seed a new install deploys
    new = tmp_path / "new"
    write_content(new / "content", pieces=[got["entry"]])
    seed = new / "content" / "seed"
    (seed / "new-song.json").write_text(json.dumps({**got["piece"], "info": got["info"], "display": got["display"]}))
    (seed / "media" / "new-song").mkdir(parents=True)
    for f in got["files"]:
        (seed / "media" / "new-song" / f["file"]).write_bytes(client.get(f"/api/library/media/new-song/{f['file']}").content)
    monkeypatch.setenv("PIANO_DB", str(new / "piano.db"))
    monkeypatch.setenv("PIANO_CONTENT", str(new / "content"))
    with TestClient(main.app) as fresh:
        assert [e["id"] for e in fresh.get("/api/library").json()["pieces"]] == ["new-song"]
        p = fresh.get("/api/library/pieces/new-song").json()
        assert p["display"] == {"fingers": None, "letters": True}
        assert fresh.get(p["media"]["presets"]["100"]["accompaniment"]["url"]).content == b"x" * 5
    with TestClient(main.app) as again:                     # a second start brings nothing more
        assert len(again.get("/api/library").json()["pieces"]) == 1
