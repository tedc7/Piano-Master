"""End-to-end check of the built client and the App API in headless Chromium at iPad A16 size.

    tools/.venv/bin/python tools/check_app.py            # serves client/dist and the API locally

The API runs in-process with a temporary database, and serves client/dist at / like Caddy does.

Web MIDI is replaced by a scripted keyboard here, in the test only (arch §11.4: "real screens
with scripted playing"); the app itself only ever reads a real piano through Web MIDI.
Screenshots go to tests-output/.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import uvicorn

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "client" / "dist"
SONGS = ROOT / "build" / "songs"           # every song, built (tools/build_content.py); the library's seed here
OUT = ROOT / "tests-output"

FAKE_MIDI = """
(() => {
  const mk = (id, name) => ({ id, name, state: "connected", type: "input", onmidimessage: null });
  const inputs = new Map([["1", mk("1", "MIDIWeb Out / 5of12")], ["2", mk("2", "Network Session 1")], ["3", mk("3", "Test Piano")]]);
  const access = { inputs, outputs: new Map(), onstatechange: null, sysexEnabled: false };
  navigator.requestMIDIAccess = () => Promise.resolve(access);
  window.__midiSend = (bytes, name = "Test Piano") => {
    for (const i of inputs.values()) {
      if (i.name === name && i.onmidimessage) i.onmidimessage({ data: new Uint8Array(bytes), timeStamp: performance.now() });
    }
  };
})();
"""

# Plays the piece's expected notes when the song clock reaches them, until the attempt finishes
# (or `untilRewinds` rewinds have happened). Notes at the `skip` beats are left out, or, with
# `wrongKeys`, played a semitone too high.
AUTOPLAY = """
([skip, untilRewinds, maxSeconds, wrongKeys]) => new Promise((resolve) => {
  const pm = window.__pm, tl = pm.tl, player = pm.player;
  let next = 0, lastState = null, rewinds = 0, t0 = performance.now();
  const notes = tl.notes.filter((n) => !n.tieContinuation);
  const timer = setInterval(() => {
    const st = player.state, pos = player.position.logic;
    if (st === "gliding" && lastState !== "gliding") rewinds++;
    // after a rewind, replay from its target
    if (st === "countin" && lastState === "gliding") {
      const from = player.debug().passStart;
      next = notes.findIndex((n) => n.beat >= from - 1e-6);
    }
    lastState = st;
    if (st === "playing" || st === "countin") {
      while (next < notes.length && notes[next].beat <= pos + 1e-6) {
        const n = notes[next++];
        let pitch = n.pitch;
        if (skip.some((b) => Math.abs(b - n.beat) < 1e-6)) { if (!wrongKeys) continue; pitch += 1; }
        window.__midiSend([0x90, pitch, 80]);
        setTimeout(() => window.__midiSend([0x80, pitch, 0]), 120);
      }
    }
    const done = st === "finished" || (untilRewinds && rewinds >= untilRewinds) || performance.now() - t0 > maxSeconds * 1000;
    if (done) { clearInterval(timer); resolve({ state: st, rewinds, debug: player.debug() }); }
  }, 4);
})
"""


# Test-only notation (never content): triplets, grace notes, the left hand crossing onto the
# treble staff ("_L"), a clef change, and a repeat; then a first bar packed with sixteenths.
NOTATION_ABC = """X:1
M:4/4
L:1/8
Q:1/4=90
K:G
%%score {RH LH}
V:RH clef=treble
V:LH clef=bass
[V:RH] |: (3DEF G2 {f}g2 "_L"B2 | (3ABc (3dcB A4 :| G8 |]
[V:LH] |: G,,8 | D,8 :| [K:clef=treble] G8 |]
"""
WIDE_ABC = """X:1
M:4/4
L:1/16
Q:1/4=60
K:C
CEGc eGce CEGc eGce | c16 |]
"""


def test_piece(pid, abc, hands):
    sys.path.insert(0, str(ROOT / "tools"))
    import notation as nt
    nota, _ = nt.build_notation(nt.parse_abc(abc), phrase_bars=2)
    return {"id": pid, "title": pid, "kind": "song", "hands": hands, "notation": nt.jsonable(nota), "media": None}


def wait_api(page, js: str, timeout: float = 15000) -> None:
    """Wait until `js` (an expression that fetches from the API) resolves to something truthy.
    Polls with evaluate, which awaits the promise (a pending promise must not count as true)."""
    t0 = time.monotonic()
    while not page.evaluate(js):
        if (time.monotonic() - t0) * 1000 > timeout:
            raise TimeoutError(f"waited {timeout / 1000:g} s for {js}")
        page.wait_for_timeout(100)


def plant_rushed_quarters() -> str:
    """A student whose last two days of Hot Cross Buns rushed every quarter note by 140 ms, written
    straight into the check's throwaway database (the MIDI keyboard's data, in advance). Prep A has
    no eighth notes, so the quarter notes are the rushed figure."""
    import sqlite3
    from datetime import date, datetime, timedelta
    notes = json.loads((SONGS / "hot-cross-buns.json").read_text())["notation"]["notes"]
    res = [[i, -140 if n["duration"] == 1 else 0] for i, n in enumerate(notes)]
    con = sqlite3.connect(os.environ["PIANO_DB"])
    sid, now = str(uuid.uuid4()), datetime.now().astimezone()
    con.execute("INSERT INTO students (id, name, avatar, start_date, sort, created_at) VALUES (?, 'Cleo', '🐢', ?, 9, ?)",
                (sid, (date.today() - timedelta(days=3)).isoformat(), now.isoformat()))
    con.execute("INSERT OR IGNORE INTO devices (id, created_at, last_seen) VALUES ('planted', ?, ?)", (now.isoformat(),) * 2)
    for k in (2, 1):
        when = (now - timedelta(days=k)).isoformat()
        con.execute(
            "INSERT INTO attempts (id, device_id, student_id, piece_id, arrangement_id, context, mode, completed, started_at, received_at, "
            "tempo_preset, conditions, conditions_factor, raw_accuracy, accuracy, accuracy_stars, per_phrase_errors, note_errors, "
            "evaluation, raw_events, passes, note_results) VALUES (?, 'planted', ?, 'hot-cross-buns', 'hot-cross-buns', 'guided', "
            "'play', 1, ?, ?, '100', '{\"hands\": \"both\"}', 1, 1, 1, 5, '[]', '[]', '{}', '[]', '[]', ?)",
            (str(uuid.uuid4()), sid, when, when, json.dumps(res)))
    con.commit()
    con.close()
    return sid


def serve():
    """The App API plus the built client at /, on a free local port, with a throwaway database. The
    API plans from the built skill map, and its library starts with every built song, as a deploy's
    seed brings them in (v0.27)."""
    tmp = Path(tempfile.mkdtemp())
    os.environ["PIANO_DB"] = str(tmp / "piano.db")
    content = tmp / "content"
    content.mkdir()
    (content / "skillmap.json").write_text((DIST / "content" / "skillmap.json").read_text())
    (content / "seed").symlink_to(SONGS)
    os.environ["PIANO_CONTENT"] = str(content)
    sys.path.insert(0, str(ROOT / "api"))
    from starlette.staticfiles import StaticFiles
    from app.main import app
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="client")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}/"


def main():
    if not (DIST / "index.html").exists():
        print("build first: (cd client && npm run build)", file=sys.stderr)
        return 1
    OUT.mkdir(exist_ok=True)
    server, url = serve()
    failures, report = [], {}

    def open_piece(page, pid):
        page.goto(url + f"#/play/{pid}")
        page.wait_for_function(f"window.__pm && window.__pm.player.piece.id === '{pid}' && window.__pm.layout")

    def check(ok, what):
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            failures.append(what)

    def review_flow(page, tab, tile):
        """M7 end to end (arch §10.7, §10.9): a skill submits two songs through the Skill API; they
        wait in the parent's review list and play from staging in the Play screen. One is approved
        (into the library, with a New badge); the other stays until it's decided, then goes back with
        the parent's note, which the skill reads."""
        from app import db, library
        con = db.connect()
        try:
            token = library.new_token(con, "check_app")
        finally:
            con.close()
        pitches = [60, 62, 64, 65, 67, 69, 71, 72, 71, 69, 67, 65, 64, 62, 64, 60]
        notes = [{"pitch": q, "start": float(i), "duration": 1.0, "staff": 0, "hand": "R", "voice": 1, "isMelody": True,
                  "spelled": {"step": "CDEFGAB"[[0, 2, 4, 5, 7, 9, 11].index(q % 12)], "alter": 0, "octave": q // 12 - 1}}
                 for i, q in enumerate(pitches)]
        nota = {"header": {"keySig": 0, "timeSig": "4/4", "barLength": 4, "tempo": 100, "pickupBeats": 0, "range": [60, 72],
                           "staves": ["treble"]},
                "measures": [{"number": i + 1, "start": 4.0 * i, "duration": 4.0} for i in range(4)], "notes": notes, "lyrics": [],
                "chordSymbols": [], "graces": [], "playbackOrder": [{"measure": i, "verse": 1, "pass": 1} for i in range(4)],
                "phrases": [0.0, 8.0], "length": 16.0}
        other = json.loads(json.dumps(nota))
        for n, q in zip(other["notes"], [72, 67, 64, 60, 62, 65, 69, 72, 71, 67, 62, 59, 60, 64, 67, 72]):
            n["pitch"] = q
            n["spelled"] = {"step": "CDEFGAB"[[0, 2, 4, 5, 7, 9, 11].index(q % 12)], "alter": 0, "octave": q // 12 - 1}
        other["header"]["range"] = [59, 72]
        song = lambda pid, title, n: {
            "piece": {"id": pid, "title": title, "composer": "Test", "kind": "library", "genre": "kids", "level": "Level 1", "hands": "R",
                      "notation": n, "media": None},
            "info": {"license": {"composition": "public-domain", "edition": "public-domain"}, "source": {"site": "test", "url": "https://example.org"},
                     "level": "Level 1", "lyrics": "(none)"}}
        body = {"name": "check batch", "notes": "Test songs from check_app.",
                "items": [song("check-scale-song", "Scale Song", nota), song("check-leap-song", "Leap Song", other)]}
        def call(method, path, data=None):
            req = urllib.request.Request(url + path, data=json.dumps(data).encode() if data is not None else (b"" if method == "POST" else None),
                                         method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        pkg = call("POST", "api/skill/packages", body)
        staged = call("POST", f"api/skill/packages/{pkg['id']}/submit")
        check(all(i["accepted"] for i in pkg["items"]) and staged["staged"] == 2, f"skill api: two songs pass intake and are staged ({staged})")
        page.get_by_role("button", name="‹ Config").click()
        tile("Review list").click()
        page.wait_for_selector("text=Scale Song")
        page.locator(".item", has_text="Scale Song").get_by_role("button", name="▶ Listen and play").click()
        page.wait_for_function("window.__pm && window.__pm.layout && window.__pm.player.piece.id.startsWith('staged--')")
        check(page.evaluate("__pm.player.piece.title") == "Scale Song (review)", "review list: a staged song opens in the Play screen")
        page.get_by_role("button", name="‹ Back").click()
        page.wait_for_selector("text=Scale Song")
        row = lambda title: page.locator(".item", has_text=title)
        row("Scale Song").get_by_role("button", name="Approve").click()
        page.wait_for_selector("text=is in the library")
        check(row("Leap Song").count() == 1 and page.get_by_text("Waiting for you (1)").count() == 1,
              "review list: approving one song leaves the others waiting")
        row("Leap Song").get_by_role("button", name="Needs improvement").click()
        page.locator("textarea").fill("Too fast: the words run together.")
        page.get_by_role("button", name="Send back").click()
        page.wait_for_selector("text=Sent back for changes (1)")
        fb = call("GET", "api/skill/feedback")["feedback"]
        check([(f["pieceId"], f["feedback"]) for f in fb] == [("check-leap-song", "Too fast: the words run together.")],
              f"review list: Needs improvement sends the note to the skills ({fb})")
        tab("Songs").click()
        page.wait_for_selector(".song")
        card = page.locator(".song", has_text="Scale Song")
        check(card.count() == 1 and card.locator(".new").count() == 1, "review list: the approved song is in Songs, marked New")
        # updating a live song (v0.27): Needs improvement in the Play screen's gear pop-up; the fix comes back
        # as an update with what changed; approving it replaces the song in place
        page.goto(url + "#/play/check-scale-song")
        page.wait_for_function("window.__pm && window.__pm.layout && window.__pm.player.piece.id === 'check-scale-song'")
        page.get_by_role("button", name="Song and settings").click()
        page.wait_for_selector("#improve-note")
        check(page.locator("#improve-note").input_value() == "", "update: no bar in the note before the song has moved")
        page.locator("#improve-note").fill("Bar 2: end on G, not C.")
        page.locator(".sheet").get_by_role("button", name="Needs improvement").click()
        page.wait_for_selector("text=The children keep this version until you approve the fix")
        page.screenshot(path=str(OUT / "update-asked.png"))
        # finger numbers and letter names, switched for this song for every child (v0.29)
        sheet = page.locator(".sheet")
        check(not sheet.get_by_label("Finger numbers").is_checked() and not sheet.get_by_label("Letter names").is_checked(),
              "helpers: a Level 1 song starts with finger numbers and letter names off")
        sheet.get_by_label("Letter names").check()
        page.wait_for_selector(".helpers >> text=Saved.")
        sheet.get_by_label("Finger numbers").check()
        page.wait_for_timeout(400)
        letters_now = page.locator(".note-letter").count()
        with urllib.request.urlopen(url + "api/library/pieces/check-scale-song") as r:
            shown = json.loads(r.read())["display"]
        check(letters_now > 0 and shown == {"fingers": True, "letters": True},
              f"helpers: the switches redraw the staff and are saved for the song ({letters_now} letters, {shown})")
        # a tap outside the gear pop-up closes it and does nothing else
        page.mouse.click(6, page.viewport_size["height"] // 2)
        page.wait_for_timeout(200)
        check(page.locator(".sheet").count() == 0 and page.evaluate("__pm.player.position.display") <= 0,
              "gear pop-up: a tap outside closes it, and the song doesn't start")
        page.goto(url + "#/library")
        page.wait_for_selector(".song")
        page.goto(url + "#/play/check-scale-song")
        page.wait_for_function("window.__pm && window.__pm.layout && window.__pm.player.piece.id === 'check-scale-song'")
        check(page.locator(".note-letter").count() == letters_now, "helpers: the song keeps them when it opens again")
        # a song played only on black keys: letter names start off; switched on, the black keys are named
        page.goto(url + "#/play/canyon-echo")
        page.wait_for_function("window.__pm && window.__pm.layout && window.__pm.player.piece.id === 'canyon-echo'")
        page.get_by_role("button", name="Song and settings").click()
        sheet = page.locator(".sheet")
        off = not sheet.get_by_label("Letter names").is_checked() and page.locator(".note-letter").count() == 0
        sheet.get_by_label("Letter names").check()
        page.wait_for_selector(".helpers >> text=Saved.")
        names = sorted(set(page.evaluate("[...document.querySelectorAll('.note-letter')].map((e) => e.textContent)")))
        check(off and names == ["C♯", "D♯"], f"helpers: a black-key song starts without letters; switched on, it shows {names}")
        page.screenshot(path=str(OUT / "black-key-letters.png"))
        page.mouse.click(6, page.viewport_size["height"] // 2)
        fb = {f["pieceId"]: f for f in call("GET", "api/skill/feedback")["feedback"]}
        check(fb.get("check-scale-song", {}).get("live") is True, f"update: the request reaches the skills as a live song ({list(fb)})")
        fixed = json.loads(json.dumps(nota))
        for n, q in zip(fixed["notes"][4:8], [67, 69, 71, 67]):
            n["pitch"] = q
            n["spelled"] = {"step": "CDEFGAB"[[0, 2, 4, 5, 7, 9, 11].index(q % 12)], "alter": 0, "octave": q // 12 - 1}
        pkg = call("POST", "api/skill/packages", {"name": "fix", "items": [song("check-scale-song", "Scale Song", fixed)]})
        staged = call("POST", f"api/skill/packages/{pkg['id']}/submit")
        check(pkg["items"][0]["accepted"] and staged["staged"] == 1, f"update: intake takes the fix under the same id ({pkg['items'][0]['errors']})")
        page.goto(url + "#/config/review")
        page.wait_for_selector("text=Update to a live song")
        up = page.locator(".item", has_text="Update to a live song")
        check(up.get_by_text("Changes from the live song: notes in bar 2").count() == 1 and up.get_by_text("end on G").count() == 1,
              "update: the review list shows what changed beside the note")
        check(up.get_by_role("button", name="Never allow").count() == 0 and up.get_by_role("button", name="Discard update").count() == 1,
              "update: an update can be discarded, never deleted from here")
        page.screenshot(path=str(OUT / "update-review.png"))
        up.get_by_role("button", name="Approve update").click()
        page.wait_for_selector("text=is updated")
        with urllib.request.urlopen(url + "api/library/pieces/check-scale-song") as r:
            now_pitches = [n["pitch"] for n in json.loads(r.read())["notation"]["notes"][4:8]]
        check(now_pitches == [67, 69, 71, 67], f"update: approving it replaces the live song ({now_pitches})")
        # deleting it from the library moves it to the review list's Deleted songs, from where it can come back
        tab("Config").click()
        tile("Songs and genres").click()
        page.locator(".song", has_text="Scale Song").get_by_role("button", name="Delete…").click()
        page.get_by_role("button", name="Delete (to the Review list's Deleted songs)").click()
        page.wait_for_selector("text=is out of the library")
        page.get_by_role("button", name="‹ Config").click()
        tile("Review list").click()
        page.wait_for_selector("text=Deleted songs (1)")
        gone = page.locator(".item", has_text="deleted from the library")
        check(gone.count() == 1, "songs and genres: a deleted song moves to the review list's Deleted songs")
        gone.get_by_role("button", name="Back to review").click()
        page.wait_for_selector("text=is waiting for you again")
        check(page.get_by_text("Waiting for you (1)").count() == 1 and page.get_by_text("Deleted songs (").count() == 0,
              "review list: a deleted song goes back to the waiting list")

    def navigation(page):
        """The screens around the Play screen (arch §3) on a new piano server, through M4 and M5:
        the first parent PIN, adding students, Today's Practice from the lesson engine, a concept
        lesson and a song checked off, the Journey map and Songs following the skill states,
        separate progress for each child, "Try it another way", and the parent's pages."""
        tab = lambda name: page.locator("nav.tabbar button", has_text=name)
        tile = lambda name: page.locator(".tile").filter(has=page.locator(".tile-name", has_text=name))
        pad = lambda digits: [page.locator(".pad").get_by_role("button", name=d, exact=True).click() for d in digits]

        def do_lesson(wrong_first=False):
            """Go through a concept lesson: play the lit keys on Try, tap the answers on Check, play
            the phrase back on Echo. Returns whether a wrong answer went back to Show, and the
            Check and Echo points (arch §7.8) just before the end."""
            page.wait_for_function("window.__lesson && window.__lesson.card")
            went_back = False
            points = {}
            for _ in range(40):
                kind = page.evaluate("__lesson.card.kind")
                if kind == "try":
                    for _k in range(20):
                        if page.evaluate("__lesson.done"):
                            break
                        page.wait_for_selector(".keys [data-pitch].kb-t-R, .keys [data-pitch].kb-t-L")
                        pitches = page.evaluate("[...document.querySelectorAll('.keys .kb-t-R, .keys .kb-t-L')].map(k => +k.dataset.pitch)")
                        page.evaluate("ps => { for (const p of ps) __midiSend([0x90, p, 80]); for (const p of ps) __midiSend([0x80, p, 0]); }", pitches)
                        page.wait_for_timeout(50)
                elif kind == "check":
                    while not page.evaluate("__lesson.done"):
                        q = page.evaluate("__lesson.card.questions[__lesson.progress]")
                        if isinstance(q["answer"], str):
                            wrong = next(c for c in q["choices"] if c != q["answer"])
                            if wrong_first and not went_back:
                                page.locator(".choice", has_text=wrong).click()
                                page.wait_for_function("__lesson.card.kind === 'show'", timeout=5000)
                                went_back = True
                                break
                            page.locator(".choice", has_text=q["answer"]).click()
                            page.wait_for_timeout(700)
                            continue
                        want = q["answer"]["pitches"][0]
                        if wrong_first and not went_back:
                            page.locator(f".keys [data-pitch='{want + 1}']").dispatch_event("pointerdown")
                            page.wait_for_function("__lesson.card.kind === 'show'", timeout=5000)
                            went_back = True
                            break
                        page.locator(f".keys [data-pitch='{want}']").dispatch_event("pointerdown")
                        page.wait_for_timeout(700)
                    if page.evaluate("__lesson.card.kind") == "show":
                        continue
                elif kind == "echo":
                    # the card is read and "Here it is" said first (Auto-read on); a key pressed before the
                    # phrase is played, or while it is, doesn't count
                    page.wait_for_function("__lesson.heard.thisCard && performance.now() > __lesson.heard.until + 300", timeout=60000)
                    echo_cues.append(([x["text"] for x in page.evaluate("__lesson.voice.log")[-2:]], page.evaluate("[__lesson.card.text, __lesson.voice.autoRead]")))
                    for ps in page.evaluate("__lesson.card.play.map(n => n.pitches)"):
                        page.evaluate("ps => { for (const p of ps) __midiSend([0x90, p, 80]); for (const p of ps) __midiSend([0x80, p, 0]); }", ps)
                        page.wait_for_timeout(120)
                    page.wait_for_function("__lesson.echo.result !== null", timeout=5000)
                if page.locator("button.next").is_disabled():
                    raise AssertionError(f"lesson: can't leave the {kind} card")
                last = page.evaluate("__lesson.step === document.querySelectorAll('.steps .dot').length - 1")
                if last:
                    points = page.evaluate("__lesson.points")
                page.locator("button.next").click()
                if last:
                    return went_back, points
                page.wait_for_timeout(100)
            raise AssertionError("lesson: never finished")

        echo_cues = []

        def ok_pin(digits):
            pad(digits)
            page.get_by_role("button", name="OK").click()

        check(page.locator(".student").count() == 1 and page.get_by_text("No players yet").count() == 1,
              "picker: a new piano server has only the Parent card")
        page.locator(".student.parent").click()
        page.wait_for_selector("text=Choose a parent PIN")
        ok_pin("2468")
        page.wait_for_selector("text=Enter it again")
        ok_pin("2468")
        page.wait_for_selector(".tile")
        check(page.locator(".status .player.parent").count() == 1, "parent: choosing the first PIN logs the parent in")
        tile("Students").click()
        for name, av in (("Ada", "🦊"), ("Ben", "🐢")):
            page.get_by_role("button", name="＋ Add a student").click()
            page.get_by_placeholder("First name").fill(name)
            page.get_by_role("button", name=f"Avatar {av}").click()
            page.get_by_role("button", name="Save").click()
            page.wait_for_selector(f".student h2:text-is('{name}')")
        # Ben practises with auto-rewind off (a per-student setting)
        ben = page.locator(".panel.student", has=page.locator("h2", has_text="Ben"))
        ben.get_by_role("button", name="On").click()
        page.wait_for_function("[...document.querySelectorAll('.panel.student')].some(p => p.innerText.includes('Ben') && p.innerText.includes('Off'))")
        page.screenshot(path=str(OUT / "nav-config-students.png"))
        page.get_by_role("button", name="Switch player").click()
        page.wait_for_selector("button.student.parent")        # the picker, not the Students page
        page.wait_for_selector("button.student >> text=Ben")
        n = page.locator("button.student").count()
        check(n == 3, f"picker: the two students added and the parent ({n})")
        page.screenshot(path=str(OUT / "nav-picker.png"))

        # Ada: the lesson engine starts her with the first lightbulb
        page.locator(".student", has_text="Ada").click()
        page.wait_for_selector(".path .bubble")
        up = page.locator(".upnext").inner_text()
        check("New idea" in up and "Sitting at the piano" in up, f"practice: a new student starts with the first concept lesson ({up[:60]!r})")
        n_items = page.locator(".path .bubble").count()
        page.screenshot(path=str(OUT / "nav-session.png"))
        page.get_by_role("button", name="Start").click()
        page.wait_for_selector(".card-big")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "lesson-explain.png"))
        # reading aloud (v0.34): a card is read by the lesson voice's recording a moment after it shows;
        # Read it to me becomes Stop reading while it reads; Auto-read is the student's, for every lesson
        voice = lambda: page.evaluate("__lesson.voice")
        read_btn = page.locator("button.read")
        check(voice()["log"] == [], "lesson voice: a new card isn't read the moment it shows")
        page.wait_for_function("__lesson.voice.log.length > 0", timeout=4000)
        first = page.evaluate("__lesson.card.text")
        check(voice()["log"][0] == {"text": first, "by": "recording"},
              f"lesson voice: the card is read by its recording after a moment ({voice()['log'][:1]})")
        check(voice()["speaking"] and read_btn.inner_text().strip() == "⏹ Stop reading",
              f"lesson voice: Read it to me becomes Stop reading while it reads ({read_btn.inner_text()!r})")
        read_btn.click()
        check(not voice()["speaking"] and read_btn.inner_text().strip() == "🔊 Read it to me", "lesson voice: Stop reading stops it")
        read_btn.click()
        page.wait_for_function("__lesson.voice.log.length === 2 && __lesson.voice.speaking", timeout=4000)
        check(voice()["log"][1]["text"] == first, "lesson voice: Read it to me reads the card again")
        page.locator("button.autoread").click()
        check(not voice()["speaking"] and not voice()["autoRead"] and page.locator("button.autoread.off").count() == 1,
              "lesson voice: turning Auto-read off stops the reading")
        page.get_by_role("button", name="Next ›").click()
        page.wait_for_timeout(1500)
        check(len(voice()["log"]) == 2, "lesson voice: with Auto-read off the next card isn't read")
        ada = next(x for x in page.evaluate("fetch('api/students').then(r => r.json())")["students"] if x["name"] == "Ada")
        check(ada["settings"]["autoRead"] is False, "lesson voice: Auto-read is remembered in the student's settings")
        page.locator("button.autoread").click()
        page.wait_for_function("__lesson.voice.log.length === 3", timeout=4000)
        check(voice()["autoRead"] and voice()["log"][2]["text"] == page.evaluate("__lesson.card.text"),
              "lesson voice: turning Auto-read on reads the card")
        page.get_by_role("button", name="‹ Back").click()
        page.wait_for_timeout(200)
        backs = 0
        while page.evaluate("__lesson.card.kind") != "show":            # past the explain cards
            page.get_by_role("button", name="Next ›").click()
            page.wait_for_timeout(200)
            backs += 1
        page.wait_for_selector(".mini svg")
        # with Auto-read on, a Show card is read, then says "I'll show you", then plays its keys
        lit = "document.querySelectorAll('.mini .pm-glow').length + document.querySelectorAll('.keys .kb-t-R').length"
        show_text = page.evaluate("__lesson.card.text")
        page.wait_for_function("t => __lesson.voice.log.some(x => x.text === t)", arg=show_text, timeout=4000)
        check(page.evaluate(lit) == 0, "lesson voice: a Show card is read before its keys play")
        page.wait_for_function(lit + " > 0", timeout=30000)
        page.screenshot(path=str(OUT / "lesson-show.png"))
        check([x["text"] for x in voice()["log"][-2:]] == [show_text, "I'll show you."],
              f"lesson: Show lights the keys and the staff notes after the card is read and \"I'll show you\" ({voice()['log'][-2:]})")
        n_said = len(voice()["log"])
        page.get_by_role("button", name="👀 Show me again").click()
        page.wait_for_function(f"__lesson.voice.log.length === {n_said + 1}", timeout=4000)
        check(voice()["log"][-1]["text"] == "I'll show you." and page.evaluate(lit) == 0,
              "lesson voice: Show me again says \"I'll show you\" first")
        page.wait_for_function(lit + " > 0", timeout=8000)
        check(True, "lesson voice: then Show me again plays the keys")
        for _ in range(backs):
            page.get_by_role("button", name="‹ Back").click()
            page.wait_for_timeout(150)
        _, pts = do_lesson()
        said, (echo_text, _) = echo_cues[0]
        check(said == [echo_text, "Here it is."], f"lesson voice: an Echo card is read, then says \"Here it is\", then plays its phrase ({said})")
        check(sorted(pts.values()) == [1] * 5 and any(k.endswith("/echo") for k in pts),
              f"lesson: the echo card and the Check questions each earn a point, right first time ({pts})")
        page.wait_for_selector(".path .bubble.done")
        index = json.loads((SONGS / "index.json").read_text())["pieces"]
        skillmap = json.loads((DIST / "content" / "skillmap.json").read_text())["skills"]
        sitting = next(s for s in skillmap if s["id"] == "prep-a.sitting")["pieces"]
        firsts = {p["id"]: p["title"] for p in index if p["id"] in sitting}
        up = page.locator(".upnext").inner_text()
        check(any(t in up for t in firsts.values()), f"practice: after the lesson (played on the piano), one of its songs is up next ({up[:60]!r})")

        page.get_by_role("button", name="Start").click()
        page.wait_for_function("window.__pm && window.__pm.player.piece && window.__pm.layout")
        first = page.evaluate("__pm.player.piece.id")
        check(first in firsts, f"practice: the song is one of the first skill's ({first})")
        check(page.get_by_role("button", name="Settings").count() == 0, "play: no test settings for a student")
        page.get_by_role("button", name="100%").click()
        page.locator(".modes button").first.click()
        r = page.evaluate(AUTOPLAY, [[], 0, 40, False])
        check(r["state"] == "finished", f"practice: the song is played to the end ({r['state']})")
        page.wait_for_selector(".result")
        check(page.get_by_role("button", name="Next ›").count() == 1, "practice: the result card offers Next")
        page.get_by_role("button", name="‹ Back").click()   # leaving by Back still checks the item off
        page.wait_for_selector(".bubble.done >> nth=1")
        check(page.locator(".bubble.done").count() == 2 and page.locator('.node [aria-label="♪: 5 of 5 stars"]').count() == 1,
              "practice: the lesson and the song are checked off, the song with its 5 stars")
        wait_api(page, f"fetch('api/attempts?piece_id={first}').then(r => r.json()).then(j => j.attempts.some(a => a.studentId))", timeout=15000)
        stored = page.evaluate(f"fetch('api/attempts?piece_id={first}').then(r => r.json())")["attempts"][0]
        check(stored["context"] == "guided" and stored["itemId"] and stored["skillId"] == "prep-a.sitting",
              f"practice: the attempt is stored for Ada's session item ({stored['context']}, {stored['skillId']})")
        page.wait_for_timeout(600)          # the state refresh after the attempt reached the server
        page.screenshot(path=str(OUT / "nav-session-progress.png"))

        tab("Journey").click()
        page.wait_for_selector(".map .bubble")
        page.wait_for_timeout(300)
        states = page.evaluate("[...document.querySelectorAll('.map .bubble')].map(b => [...b.classList].find(c => ['locked', 'open', 'current', 'passed', 'mastered'].includes(c)))")
        check(states.count("passed") == 1 and states.count("open") == 2 and states.count("locked") == len(states) - 3 and len(states) == 46,
              f"journey: the first skill passed, its two branches ready to learn, the rest locked ({states})")
        check(page.locator(".map .unit", has_text="Unit 9").count() == 2, "journey: each bubble shows its unit")
        page.screenshot(path=str(OUT / "nav-journey.png"))
        check(page.locator(".bulb").count() == 0, "journey: one bubble per skill, no separate lightbulb (v0.29)")
        page.locator(".bubble.locked").first.click()
        check(page.get_by_text("Unlocks after:").count() == 1, "journey: a locked bubble says what it needs")
        page.locator(".map .name").first.click()
        check(page.locator(".sheet").count() == 0, "journey: a tap outside the pop-up closes it")

        tab("Songs").click()
        page.wait_for_selector(".song")
        opened = page.locator(".song .card:not([disabled])").count()
        # a child sees the map's practice songs, and other genres only once the parent allows them
        # (M7, arch §10.1; v0.27); songs with no skill yet need nothing, so they're open too
        pieces = json.loads((SONGS / "index.json").read_text())["pieces"]
        practice = {x for s in json.loads((DIST / "content" / "skillmap.json").read_text())["skills"] for x in s["pieces"]}
        mine = [p for p in pieces if p["id"] in practice]
        free = sum(1 for p in mine if not p.get("skillId"))
        songs = len({p.get("song") or p["id"] for p in mine})      # arrangements of one song share a row
        check(page.locator(".song").count() == songs and opened == len(firsts) + free,
              f"songs: the passed skill's {len(firsts)} songs are open, plus {free} with no skill ({opened} open, {songs} songs); other genres hidden")
        page.locator(".heart").first.click()
        page.get_by_role("button", name="♥ Favorites").click()
        check(page.locator(".song").count() == 1, "songs: a favorite shows under Favorites")
        page.get_by_role("button", name="All songs").click()
        soon = page.locator(".soon", has_text="Coming soon").all_inner_texts()
        check(soon and all(t.startswith("Coming soon · unlocks with ") and ", then " not in t for t in soon),
              f"songs: a locked song names the one skill that unlocks it ({soon[:2]})")
        # the search finds a song by its words, and the genre choice narrows to one genre (v0.35)
        search = page.get_by_label("Find a song or its words")
        # a song the child can open, found by a word of its lyrics that isn't in its title
        sung, word = next((x, w) for x in mine if x.get("words") and (x["id"] in firsts or not x.get("skillId"))
                          for w in x["words"].replace(",", " ").split() if len(w) >= 4 and w.lower() not in x["title"].lower())
        search.fill(word)
        titles = page.locator(".song .card-title").all_inner_texts()
        check(any(t.startswith(sung.get("songTitle") or sung["title"]) for t in titles) and len(titles) < songs,
              f"songs: searching for '{word}' finds {sung['title']} by its words ({len(titles)} of {songs} songs)")
        search.fill("zzzz no such song")
        check(page.locator(".song").count() == 0 and page.get_by_text("No songs match.").count() == 1, "songs: a search with no match says so")
        page.get_by_role("button", name="Show every song").click()
        check(page.locator(".song").count() == songs and search.input_value() == "", "songs: Show every song clears the search")
        genre = sorted({x.get("genre") for x in mine if x.get("genre") and x.get("genre") != "studies"})[0]
        page.get_by_label("Genre").select_option(genre)
        n = len({x.get("song") or x["id"] for x in mine if x.get("genre") == genre})
        check(page.locator(".song").count() == n, f"songs: the genre choice shows only {genre} ({page.locator('.song').count()} of {n})")
        # All songs clears everything that narrows the list: Favorites, the search and the genre
        page.get_by_role("button", name="♥ Favorites").click()
        page.get_by_label("Genre").select_option(genre)
        search.fill(word)
        all_sel = lambda: "sel" in (page.get_by_role("button", name="All songs").get_attribute("class") or "")
        check(not all_sel(), "songs: All songs is grayed out while the list is narrowed")
        page.get_by_role("button", name="All songs").click()
        check(all_sel(), "songs: All songs is highlighted when every song shows")
        check(page.locator(".song").count() == songs and search.input_value() == "" and page.get_by_label("Genre").input_value() == "",
              "songs: All songs clears the favorites, the search and the genre")
        page.screenshot(path=str(OUT / "nav-songs.png"))
        search.fill(word)
        page.locator(".song .card:not([disabled])").first.click()
        page.wait_for_function("window.__pm && window.__pm.layout")
        page.get_by_role("button", name="‹ Back").click()
        page.wait_for_selector(".song")
        check(search.input_value() == word and page.locator(".song").count() < songs, "play: ‹ Back returns to the song library with its search")
        search.fill("")
        page.locator(".song .card:not([disabled])").first.click()
        page.wait_for_function("window.__pm && window.__pm.layout")
        page.get_by_role("button", name="‹ Back").click()
        page.wait_for_selector(".song")
        check(page.url.endswith("#/library"), "play: ‹ Back returns to the song library")
        # back in the same state: the library scrolled where it was
        page.evaluate("document.querySelector('main.body').scrollTop = 600")
        page.wait_for_timeout(200)
        page.evaluate("[...document.querySelectorAll('.song .card:not([disabled])')].pop().click()")   # without scrolling to it
        page.wait_for_function("window.__pm && window.__pm.layout")
        page.get_by_role("button", name="‹ Back").click()
        page.wait_for_selector(".song")
        page.wait_for_timeout(500)
        top = page.evaluate("document.querySelector('main.body').scrollTop")
        check(abs(top - 600) <= 2, f"play: ‹ Back returns to the song library scrolled where it was ({top})")
        tab("Journey").click()
        page.wait_for_selector(".map .bubble")
        tab("Songs").click()
        page.wait_for_selector(".song")
        page.wait_for_timeout(300)
        check(page.evaluate("document.querySelector('main.body').scrollTop") == 0, "the tab bar opens a screen fresh")

        tab("My Progress").click()
        page.wait_for_selector(".counts")
        counts = page.locator(".counts div").all_inner_texts()
        check(any(c.startswith("1") and "passed" in c for c in counts), f"my progress: one skill passed ({counts})")
        page.screenshot(path=str(OUT / "nav-progress.png"))

        # Ben: his own progress, and "Try it another way" after 3 tries without passing
        page.get_by_role("button", name="Switch player").click()
        page.locator(".student", has_text="Ben").click()
        page.wait_for_selector(".path .bubble")
        check("New idea" in page.locator(".upnext").inner_text() and page.locator(".bubble.done").count() == 0,
              "practice: Ben's progress is separate from Ada's")
        page.get_by_role("button", name="Start").click()
        went_back, pts = do_lesson(wrong_first=True)
        check(went_back, "lesson: a wrong answer on Check goes back to Show")
        check(sorted(pts.values()) == [0.5, 1, 1, 1, 1], f"lesson: right on the second try earns half a point ({pts})")
        page.wait_for_selector(".path .bubble.done")
        page.get_by_role("button", name="Start").click()
        page.wait_for_function("window.__pm && window.__pm.player.piece && window.__pm.layout")
        check(page.evaluate("__pm.player.piece.id") in firsts, "practice: Ben's song is one of the first skill's")
        page.get_by_role("button", name="100%").click()
        skip = page.evaluate("__pm.tl.notes.filter((n, i) => i % 3 !== 0).map(n => n.beat)")
        for k in range(3):
            if k == 0:
                page.locator(".modes button").first.click()
            else:
                page.get_by_role("button", name="Play again").click()
            r = page.evaluate(AUTOPLAY, [skip, 0, 40, False])
            page.wait_for_selector(".result")
        rw = page.evaluate("__pm.player.debug().rewinds")
        check(sum(rw) == 0, f"ben: auto-rewind is off for him (rewinds per phrase {rw})")
        page.screenshot(path=str(OUT / "ben-result.png"))
        check(page.get_by_role("button", name="Try it another way").count() == 1, "result: after 3 tries without passing, Try it another way")
        page.get_by_role("button", name="Try it another way").click()
        choices = page.locator(".choices button").all_inner_texts()
        check(any("Listen first" in c for c in choices) and any("Slower" in c for c in choices) and any("See the idea again" in c for c in choices),
              f"result: the gentle choices ({choices})")
        page.screenshot(path=str(OUT / "ben-another-way.png"))
        page.locator(".choices button", has_text="Try something else").click()
        page.wait_for_selector(".path .bubble")

        # the parent
        page.get_by_role("button", name="Switch player").click()
        page.locator(".student.parent").click()
        page.wait_for_selector(".pad")
        ok_pin("1111")
        page.wait_for_selector("text=tries left")
        check(page.get_by_text("4 tries left").count() == 1, "parent: a wrong PIN says how many tries are left")
        ok_pin("2468")
        page.wait_for_selector(".tile")
        labels = page.locator("nav.tabbar .tab").all_inner_texts()
        check(any("Config" in t for t in labels) and not any("Practice" in t for t in labels), f"parent: the PIN logs in, with a Config tab ({labels})")
        page.screenshot(path=str(OUT / "nav-config.png"))
        tile("Progress reports").click()
        page.wait_for_selector(".counts")
        page.wait_for_selector("text=Content runway")
        check("left in the authored map" in page.locator("main").inner_text(), "reports: a child's full report, with the content runway")
        page.screenshot(path=str(OUT / "nav-config-reports.png"))
        page.get_by_role("button", name="‹ Config").click()

        tile("Piano check").click()
        page.wait_for_selector(".midi")
        page.evaluate("""() => { for (const [p, v] of [[60, 30], [64, 100], [67, 70]]) __midiSend([0x90, p, v]);
                                 __midiSend([0xb0, 64, 127]); for (const p of [60, 64, 67]) __midiSend([0x80, p, 0]); }""")
        page.wait_for_timeout(200)
        text = page.locator(".midi").inner_text()
        check("3 of 88 keys heard" in text and "Most keys at once: 3" in text and "responds to touch" in text and "down (127)" in text,
              "piano check: keys, chord, velocity and pedal are counted")
        page.screenshot(path=str(OUT / "nav-config-midi.png"))
        page.get_by_role("button", name="‹ Config").click()

        # latency calibration: the scripted keyboard taps 40 ms after each click is heard
        tile("Latency calibration").click()
        page.get_by_role("button", name="Start").click()
        page.evaluate("""() => new Promise((res) => { const c = window.__calib, done = new Set();
            const i = setInterval(() => { const now = c.heardNow();
              c.clicks.forEach((t, k) => { if (!done.has(k) && now >= t + 0.040) { done.add(k); __midiSend([0x90, 60, 80]); __midiSend([0x80, 60, 0]); } });
              if (c.state === 'done') { clearInterval(i); res(); } }, 2); })""")
        cal = page.evaluate("__calib.result")
        check(cal["ok"] and cal["steady"] and abs(cal["offsetMs"] - 40) <= 6 and cal["used"] == 24,
              f"calibration: 24 taps 40 ms late measure a steady offset ({cal['offsetMs']} ms, spread {cal['spreadMs']} ms)")
        page.screenshot(path=str(OUT / "nav-config-calibrate.png"))
        page.get_by_role("button", name=f"Use {cal['offsetMs']} ms").click()
        page.wait_for_timeout(300)
        dev = page.evaluate("fetch('api/devices/' + JSON.parse(localStorage.getItem('pm.device.v1'))).then(r => r.json())")
        check(dev.get("profile", {}).get("latencyOffsetMs") == cal["offsetMs"] and dev["profile"].get("latencySpreadMs") == cal["spreadMs"],
              f"calibration: the offset and spread are saved to the DeviceProfile ({dev.get('profile', {}).get('latencyOffsetMs')})")
        page.get_by_role("button", name="‹ Config").click()
        tile("Device settings").click()
        page.get_by_role("button", name="88 keys").click()
        page.wait_for_timeout(300)
        dev = page.evaluate("fetch('api/devices/' + JSON.parse(localStorage.getItem('pm.device.v1'))).then(r => r.json())")
        check(dev.get("profile", {}).get("keyboardSize") == 88, f"device settings: copied to the DeviceProfile ({dev.get('profile')})")
        page.get_by_role("button", name="‹ Config").click()
        tile("App status").click()
        page.wait_for_selector("text=✓ running")
        page.screenshot(path=str(OUT / "nav-config-status.png"))
        page.get_by_role("button", name="‹ Config").click()
        tile("Work requests").click()
        page.wait_for_selector(".placeholder")
        check(page.get_by_text("coming in a later version").count() == 1, "config: placeholder pages say when they come (a potential feature)")
        page.get_by_role("button", name="‹ Config").click()
        tile("Review list").click()
        page.wait_for_selector("text=Waiting for you")
        page.wait_for_selector("text=Nothing waiting", timeout=10000)
        check(page.get_by_text("Waiting for you (0)").count() == 1, "review list: empty on a new server (M7)")
        page.get_by_role("button", name="‹ Config").click()
        tile("Dev box connection").click()
        page.wait_for_selector("text=What this is")
        check(page.get_by_role("button", name="Make a token").count() == 1, "dev box connection: the skill tokens, under Settings")
        page.get_by_role("button", name="‹ Config").click()
        tile("Songs and genres").click()
        page.wait_for_selector("text=Genres")
        hymns = page.locator("tr", has_text="Hymns").locator("button.toggle").first
        hymns.click()
        page.wait_for_timeout(400)
        check(hymns.inner_text().strip() == "Allowed", "songs and genres: a genre allowed for a child (M7)")
        review_flow(page, tab, tile)
        tab("Songs").click()
        page.wait_for_selector(".song")
        check(page.locator(".song .card[disabled]").count() == 0, "parent: every song opens")
        # parent mode: every bubble opens, and a skill shows the family's own book pages when the private
        # file has them (content/private/book-refs.yaml, never committed), and none otherwise
        tab("Journey").click()
        page.wait_for_selector(".map .bubble")
        page.locator(".node", has_text="The quarter rest").locator(".bubble").click()
        refs = page.locator(".sheet .refs").inner_text() if page.locator(".sheet .refs").count() else ""
        built = json.loads((DIST / "content" / "skillmap.json").read_text())["skills"]
        want = next(s for s in built if s["id"] == "prep-a.quarter-rest").get("bookRefs") or []
        check((f"{want[0]['book']} p.{want[0]['pages']}" in refs) if want else refs == "",
              f"journey: parent mode shows the skill's own book pages, if any ({refs!r})")
        # back from a song: the map scrolled where it was, with the same pop-up open
        page.evaluate("document.querySelector('.map-body').scrollLeft = 500")
        page.wait_for_timeout(200)
        left = page.evaluate("document.querySelector('.map-body').scrollLeft")
        page.evaluate("document.querySelectorAll('.sheet .card')[1].click()")
        page.wait_for_function("window.__pm && window.__pm.layout")
        page.get_by_role("button", name="‹ Back").click()
        page.wait_for_selector(".sheet")
        page.wait_for_timeout(500)
        back = (page.locator(".sheet h2").inner_text(), page.evaluate("document.querySelector('.map-body').scrollLeft"))
        check(back[0] == "The quarter rest" and left > 0 and abs(back[1] - left) <= 2,
              f"play: ‹ Back returns to the Journey as it was left ({back}, scrolled {left})")
        page.get_by_role("button", name="Close").click()
        # the 3/4 lesson's identify questions: tap an answer, after listening to a phrase
        page.goto(url + "#/lesson/prep-a.three-four")
        # a Hear card is read, then says "Here it is", then plays its tune by itself (Auto-read on)
        page.wait_for_function("window.__lesson && window.__lesson.card")
        while page.evaluate("__lesson.card.kind") != "hear":
            page.get_by_role("button", name="Next ›").click()
            page.wait_for_timeout(150)
        hear_text = page.evaluate("__lesson.card.text")
        page.wait_for_function("t => __lesson.voice.log.some(x => x.text === t)", arg=hear_text, timeout=4000)
        check(not page.evaluate("__lesson.heard.thisCard"), "lesson voice: a Hear card is read before its tune plays")
        page.wait_for_function("__lesson.heard.thisCard", timeout=30000)
        said = [x["text"] for x in page.evaluate("__lesson.voice.log")[-2:]]
        check(said == [hear_text, "Here it is."], f"lesson voice: then it says \"Here it is\" and plays the tune by itself ({said})")
        _, pts = do_lesson()
        check(len(pts) == 3 and sum(pts.values()) == 3, f"lesson: tap-an-answer questions score like key questions ({pts})")
        page.goto(url + "#/config")
        tab("Config").click()
        tile("Journey render test").click()
        page.wait_for_function("window.__journeyTest", timeout=15000)
        report["journey-render-test"] = page.evaluate("window.__journeyTest")
        check(page.locator(".map .bubble").count() == 200, f"journey render test: 200 bubbles ({report['journey-render-test']})")
        page.screenshot(path=str(OUT / "journey-200.png"))
        page.get_by_role("button", name="Switch player").click()
        page.wait_for_selector(".student")
        page.goto(url + "#/config")
        page.wait_for_selector(".pad")
        check(page.locator(".status .player.parent").count() == 0, "parent: Switch player logs the parent out")

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        ipad = dict(viewport={"width": 1180, "height": 820}, device_scale_factor=2, has_touch=True)

        # 1. no piano: Play mode refuses, Listen works
        ctx = browser.new_context(**ipad)
        ctx.add_init_script("navigator.requestMIDIAccess = () => Promise.resolve({ inputs: new Map([['1', {name: 'MIDIWeb Out / 5of12', state: 'connected'}]]), outputs: new Map(), onstatechange: null });")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        open_piece(page, "twinkle-twinkle")
        check(page.get_by_text("No piano connected").count() > 0, "no piano: status strip says so (virtual port ignored)")
        play_btn, listen_btn = page.locator(".modes button").nth(0), page.locator(".modes button").nth(1)
        check(play_btn.is_disabled() and not listen_btn.is_disabled(), "no piano: Play is disabled, Listen is not")
        listen_btn.click()
        page.wait_for_function("__pm.player.running")
        check(listen_btn.inner_text() == "Pause", "listen: one tap starts it, and the button becomes Pause")
        page.wait_for_timeout(1500)
        listen_btn.click()
        check(page.evaluate("__pm.player.state") == "paused" and listen_btn.inner_text() == "Listen", "listen: Pause pauses, and the button says Listen again")
        ctx.close()

        # 2. with the scripted keyboard
        ctx = browser.new_context(**ipad)
        ctx.add_init_script(FAKE_MIDI)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        # the deliberate wrong PIN is a 401 the browser logs; anything else counts
        page.on("console", lambda m: m.type == "error" and "status of 401" not in m.text and errors.append(m.text))
        page.goto(url)
        page.wait_for_selector(".student")
        page.wait_for_timeout(300)
        check(page.get_by_text("Test Piano").count() > 0, "picker: the real piano is chosen, virtual ports skipped")
        navigation(page)

        index = json.loads((SONGS / "index.json").read_text())
        for piece in index["pieces"]:
            open_piece(page, piece["id"])
            lay = page.evaluate("({p: __pm.layout.problems, w: __pm.layout.width, h: __pm.layout.height, ms: __pm.layout.renderMs, "
                                "els: __pm.layout.noteEls.filter(Boolean).length, n: __pm.tl.notes.length, lyr: __pm.layout.lyrics.length})")
            report[piece["id"]] = lay
            check(not lay["p"], f"{piece['id']}: staff renders with no problems ({lay['w']}x{lay['h']} px, {lay['ms']:.0f} ms)")
            check(lay["els"] == lay["n"], f"{piece['id']}: every note has a note-head element ({lay['els']}/{lay['n']})")
            page.screenshot(path=str(OUT / f"play-{piece['id']}.png"))

        # 2b. notation features on a test-only piece, and the idle view of a dense first bar
        for pid, abc, hands in (("test-notation", NOTATION_ABC, "RL"), ("test-wide", WIDE_ABC, "R")):
            body = test_piece(pid, abc, hands)
            page.route(f"**/api/library/pieces/{pid}", lambda route, _request=None, b=body: route.fulfill(json=b))
        open_piece(page, "test-notation")
        lay = page.evaluate("""() => ({ p: __pm.layout.problems, els: __pm.layout.noteEls.filter(Boolean).length, n: __pm.tl.notes.length,
            beats: __pm.tl.notes.filter(n => n.staff === 0).slice(0, 3).map(n => +n.beat.toFixed(3)),
            left: __pm.tl.notes.filter(n => n.staff === 0 && n.hand === 'L').length,
            graces: __pm.layout.graces,
            text: document.querySelector('.strip svg').textContent })""")
        page.screenshot(path=str(OUT / "test-notation.png"))
        check(not lay["p"] and lay["els"] == lay["n"], f"notation test: draws with no problems, every note drawn ({lay['p'][:2]}, {lay['els']}/{lay['n']})")
        check(lay["beats"] == [0.0, 0.333, 0.667], f"notation test: a triplet's notes fall on thirds of the beat ({lay['beats']})")
        check(lay["graces"] > 0 and lay["left"] == 2, f"notation test: grace notes drawn, the crossing note is the left hand's ({lay['graces']}, {lay['left']})")
        check("verse" not in lay["text"], "notation test: a repeat in a piece without words isn't labelled 'verse 2'")
        open_piece(page, "test-wide")
        first = page.evaluate("() => { const r = __pm.layout.noteEls[0].getBoundingClientRect(), s = document.querySelector('.stage').getBoundingClientRect(); return [r.left, s.right]; }")
        check(first[0] < first[1] - 100, f"dense first bar: bar 1 is on screen before Play (first note at {first[0]:.0f}, stage ends {first[1]:.0f})")

        # letter names (pre-staff pieces): under the note heads, never on them, and the heads the usual size
        head_px = "() => Math.max(...__pm.layout.noteEls.filter(Boolean).map((e) => e.getBoundingClientRect().height))"
        open_piece(page, "twinkle-twinkle")
        plain = page.evaluate(head_px)
        open_piece(page, "musical-alphabet")
        lt = page.evaluate("""() => {
            const heads = __pm.layout.noteEls.filter(Boolean).map((e) => e.getBoundingClientRect());
            const ls = [...document.querySelectorAll('.note-letter')].map((e) => e.getBoundingClientRect());
            const hit = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
            return { n: ls.length, on: ls.filter((l) => heads.some((h) => hit(l, h))).length,
                     h: Math.max(...heads.map((h) => h.height)) }; }""")
        page.screenshot(path=str(OUT / "letters.png"))
        check(lt["n"] >= 20 and lt["on"] == 0 and abs(lt["h"] - plain) < 1,
              f"letter names: under the note heads, none on a head, heads the usual size ({lt['n']} letters, {lt['on']} on a head, "
              f"head {lt['h']:.1f}px, {plain:.1f}px without letters)")

        # the metronome: one choice for every song (v0.29)
        metro = lambda: "off" not in (page.get_by_role("button", name="Metro").get_attribute("class") or "")
        on = metro()
        page.get_by_role("button", name="Metro").click()
        open_piece(page, "musical-alphabet")
        check(metro() is not on, "metronome: turned off on one song, it stays off on the next")
        page.get_by_role("button", name="Metro").click()
        open_piece(page, "twinkle-twinkle")
        check(metro() is on, "metronome: turned back on, it's on for every song")

        # chord symbols: off for a beginner until turned on, then one choice for every song (v0.35)
        chords_shown = "() => [...document.querySelectorAll('.strip .chord')].filter((e) => getComputedStyle(e).display !== 'none').length"
        open_piece(page, "mary-had-a-little-lamb")
        n = page.locator(".strip .chord").count()
        check(n > 0 and page.evaluate(chords_shown) == 0, f"chords: drawn but hidden until the student turns them on ({n} symbols)")
        page.get_by_role("button", name="Chords").click()
        check(page.evaluate(chords_shown) == n, "chords: the Chords button shows them at once")
        open_piece(page, "london-bridge")
        check(page.evaluate(chords_shown) > 0, "chords: turned on for one song, they show on the next")
        open_piece(page, "twinkle-twinkle")
        check(page.get_by_role("button", name="Chords").count() == 0, "chords: no Chords button on a song without chord symbols")
        open_piece(page, "london-bridge")
        page.get_by_role("button", name="Chords").click()
        check(page.evaluate(chords_shown) == 0, "chords: turned off again")

        # 3. Twinkle played cleanly at 100%: no rewinds, every note matched
        open_piece(page, "twinkle-twinkle")
        page.get_by_role("button", name="100%").click()
        page.locator(".modes button").first.click()
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "twinkle-playing.png"))
        r = page.evaluate(AUTOPLAY, [[], 0, 60, False])
        res = page.evaluate("__pm.player.debug()")
        check(r["state"] == "finished", f"twinkle clean run: finishes ({r['state']})")
        check(r["rewinds"] == 0 and res["matcher"]["hits"] == res["matcher"]["expected"] and res["matcher"]["wrong"] == 0,
              f"twinkle clean run: no rewinds, all notes matched ({res['matcher']}, rewinds {r['rewinds']})")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "twinkle-result.png"))
        check(page.locator(".result").count() == 1, "twinkle clean run: result card shown")
        check(page.locator('.result [aria-label="Notes: 5 of 5 stars"]').count() == 1 and
              page.locator('.result [aria-label="Timing: 5 of 5 stars"]').count() == 1, "twinkle clean run: 5 stars for notes and timing")
        wait_api(page, "fetch('api/attempts?piece_id=twinkle-twinkle').then(r => r.json()).then(j => j.attempts.length > 0)", timeout=15000)
        stored = page.evaluate("fetch('api/attempts?piece_id=twinkle-twinkle').then(r => r.json())")["attempts"]
        check(len(stored) == 1 and stored[0]["completed"] and stored[0]["accuracyStars"] == 5 and stored[0]["tempoPreset"] == "100",
              f"twinkle clean run: attempt stored by the API ({[(a['completed'], a['accuracyStars']) for a in stored]})")
        full = page.evaluate(f"fetch('api/attempts/{stored[0]['id']}').then(r => r.json())") if stored else {}
        check(len([e for e in full.get("rawEvents", []) if e["type"] == "on"]) == 42, "twinkle clean run: all 42 key presses stored as raw events")
        page.get_by_role("button", name="Rewind").click()
        page.wait_for_timeout(100)
        st = page.evaluate("({s: __pm.player.state, b: __pm.player.position.display})")
        check(st["s"] == "idle" and st["b"] < 0 and page.locator(".result").count() == 0, f"rewind after the end: back to the start, ready to play ({st})")

        # 4. Hot Cross Buns with three wrong keys in the first phrase (6 errors): one rewind, then a clean pass
        open_piece(page, "hot-cross-buns")
        page.get_by_role("button", name="100%").click()
        page.locator(".modes button").first.click()
        r = page.evaluate(AUTOPLAY, [[4, 5, 6], 1, 30, True])
        check(r["rewinds"] == 1 and r["debug"]["rewinds"][0] == 1, f"hot cross buns: 3 wrong keys in the first phrase rewind it once ({r['debug']['rewinds']})")
        page.wait_for_timeout(250)
        page.screenshot(path=str(OUT / "hcb-glide.png"))
        r = page.evaluate(AUTOPLAY, [[], 0, 40, False])
        res = r["debug"]["matcher"]
        check(r["state"] == "finished" and res["hits"] == res["expected"], f"hot cross buns: clean second pass counts ({res})")
        page.wait_for_selector(".result")
        page.screenshot(path=str(OUT / "hcb-result.png"))
        check(page.locator('.result [aria-label="Notes: 4.5 of 5 stars"]').count() == 1, "hot cross buns: one rewind caps notes at 4.5 stars")
        check(page.get_by_text("Practice mode: 1 rewind").count() == 1, "hot cross buns: practice-mode chip lists the rewind")
        page.get_by_role("button", name="Practice tricky part").click()
        page.wait_for_function("__pm.player.mode === 'play' && __pm.player.section && __pm.player.preset === '90'")
        check(page.get_by_text("Bars 1–2").count() > 0, "tricky part: loops bars 1-2 at the next slower preset (90%)")
        r = page.evaluate(AUTOPLAY, [[], 1, 30, False])
        page.wait_for_selector(".loopnote")
        page.screenshot(path=str(OUT / "hcb-loop.png"))
        check("6 of 6 notes" in page.locator(".loopnote").inner_text(), f"tricky part: a clean loop pass shows its result ({page.locator('.loopnote').inner_text()})")
        wait_api(page, "fetch('api/attempts?piece_id=hot-cross-buns').then(r => r.json()).then(j => j.attempts.some(a => a.mode === 'loop'))", timeout=15000)
        loops = [a for a in page.evaluate("fetch('api/attempts?piece_id=hot-cross-buns').then(r => r.json())")["attempts"] if a["mode"] == "loop"]
        check(len(loops) == 1 and loops[0]["accuracyStars"] == 3.5 and loops[0]["tempoPreset"] == "90",
              f"tricky part: loop pass stored as a section attempt (0.9 x 0.92 = 83%, 3.5 stars: {[(a['accuracyStars'], a['tempoPreset']) for a in loops]})")
        page.get_by_role("button", name="Pause").click()

        # 4b. Echo Song, right hand only: the left hand's notes are shown faintly
        open_piece(page, "echo-song")
        page.get_by_role("button", name="Both hands").click()
        faint = page.evaluate("__pm.tl.notes.filter(n => __pm.layout.noteEls[n.id].classList.contains('pm-other')).map(n => n.hand)")
        check(len(faint) == 13 and set(faint) == {"L"}, f"echo song: right hand only dims the 13 left-hand notes ({len(faint)})")
        page.screenshot(path=str(OUT / "echo-right-hand.png"))
        # playing the right hand, the app plays the left hand on its sampled piano
        page.evaluate("__pm.audio.pianoLog.length = 0")
        page.get_by_role("button", name="100%").click()
        page.locator(".modes button").first.click()
        page.evaluate(AUTOPLAY, [[], 0, 30, False])
        heard = page.evaluate("__pm.audio.pianoLog")
        left = set(page.evaluate("__pm.tl.notes.filter(n => n.hand === 'L').map(n => n.pitch)"))
        check(len(heard) == 13 and all(h["sampled"] and h["pitch"] in left for h in heard),
              f"echo song: the app plays the 13 left-hand notes on the sampled piano ({len(heard)}, sampled {sum(h['sampled'] for h in heard)})")
        bars = page.locator(".loopbars")
        check(bars.inner_text() == "All bars", "bars: all bars by default")
        page.get_by_role("button", name="Later bars").click()
        first = bars.inner_text()
        page.get_by_role("button", name="Later bars").click()
        second = bars.inner_text()
        page.get_by_role("button", name="Earlier bars").click()
        page.get_by_role("button", name="Earlier bars").click()
        check(first.startswith("Bar") and second.startswith("Bar") and first != second and bars.inner_text() == "All bars",
              f"bars: step through the sections and back to all bars ({first}, {second})")

        # 4c. Rewind while listening: glide back 2 bars from the current bar; while paused, the resume point moves
        open_piece(page, "twinkle-twinkle")
        page.get_by_role("button", name="100%").click()
        page.locator(".modes button").nth(1).click()
        page.wait_for_function("__pm.player.state === 'playing' && __pm.player.position.logic > 13", timeout=20000)
        exp = page.evaluate("""() => { const L = __pm.tl.barLines, b = __pm.player.position.logic; let i = 0;
            while (i + 1 < L.length && L[i + 1] <= b + 0.05) i++; return L[Math.max(0, i - 2)]; }""")
        page.get_by_role("button", name="Rewind").click()
        st = page.evaluate("({s: __pm.player.state, to: __pm.player.resumeBeat})")
        check(st["s"] == "gliding" and st["to"] == exp, f"rewind while listening: glides back 2 bars (to beat {st['to']}, expected {exp})")
        page.wait_for_function("__pm.player.state === 'playing'", timeout=10000)
        page.get_by_role("button", name="Pause").click()
        before = page.evaluate("__pm.player.position.display")
        page.get_by_role("button", name="Rewind").click()
        after = page.evaluate("__pm.player.position.display")
        check(page.evaluate("__pm.player.state") == "paused" and after < before, f"rewind while paused: stays paused, further back ({before:.2f} -> {after:.2f})")

        # 4d. Dragging the staff (v0.33): a tap does nothing; a drag pauses, shows the bar, and on
        # letting go plays on from the nearest bar line in the same mode
        def drag_staff(a, b):
            """Drag across the staff from `a` to `b` (fractions of its width)."""
            box = page.locator(".stage").bounding_box()
            x, y = box["x"] + box["width"] * a, box["y"] + box["height"] * 0.3
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * b, y, steps=16)
            held = page.evaluate("({s: __pm.player.state, b: __pm.player.position.display, label: document.querySelector('.dragbar')?.textContent ?? null})")
            page.mouse.up()
            return held

        open_piece(page, "mary-had-a-little-lamb")
        page.get_by_role("button", name="100%").click()
        before = page.evaluate("__pm.player.position.display")
        box = page.locator(".stage").bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.3)
        page.wait_for_timeout(200)
        check(page.evaluate("__pm.player.state") == "idle" and page.evaluate("__pm.player.position.display") == before,
              "drag: a tap on the staff changes nothing")
        page.locator(".modes button").nth(1).click()
        page.wait_for_function("__pm.player.state === 'playing' && __pm.player.position.logic > 13", timeout=20000)
        at = page.evaluate("__pm.player.position.display")
        held = drag_staff(0.5, 0.75)
        page.screenshot(path=str(OUT / "drag-held.png"))
        check(held["s"] == "paused" and held["b"] < at - 1 and (held["label"] or "").startswith("Bar "),
              f"drag while listening: the music pauses, the staff follows back, and the bar shows ({held}, from {at:.2f})")
        page.wait_for_function("__pm.player.state === 'countin' || __pm.player.state === 'playing'", timeout=10000)
        r = page.evaluate("({from: __pm.player.debug().passStart, lines: __pm.tl.barLines, mode: __pm.player.mode})")
        check(r["from"] in r["lines"] and r["from"] < at and r["mode"] == "listen",
              f"drag while listening: listens on from the bar line nearest where it was let go (beat {r['from']})")
        page.wait_for_function("__pm.player.state === 'playing'", timeout=10000)
        page.get_by_role("button", name="Pause").click()

        open_piece(page, "twinkle-twinkle")
        page.get_by_role("button", name="100%").click()
        page.locator(".modes button").first.click()
        page.evaluate(AUTOPLAY, [[], 0, 7, False])
        a0 = page.evaluate("__pm.player.debug().attempt")
        held = drag_staff(0.5, 0.7)
        page.wait_for_function("__pm.player.state === 'countin' || __pm.player.state === 'playing'", timeout=10000)
        d = page.evaluate("__pm.player.debug()")
        check(held["s"] == "paused" and d["attempt"]["id"] == a0["id"] and d["attempt"]["rewinds"] == a0["rewinds"] + 1 and d["state"] in ("countin", "playing"),
              f"drag back while playing: a rewind in the same attempt, like the Rewind button ({a0} -> {d['attempt']})")
        page.get_by_role("button", name="Pause").click()

        page.goto(url + "#/library")              # leave the song, so it opens afresh
        open_piece(page, "twinkle-twinkle")
        page.get_by_role("button", name="100%").click()
        drag_staff(0.9, 0.05)
        page.wait_for_function("__pm.player.state === 'gliding' || __pm.player.state === 'countin'", timeout=5000)
        start = page.evaluate("__pm.player.debug().attempt.start")
        r = page.evaluate(AUTOPLAY, [[], 0, 60, False])
        later = page.evaluate(f"__pm.tl.notes.filter(n => !n.tieContinuation && n.beat >= {start} - 1e-6).length")
        m = r["debug"]["matcher"]
        check(start > 0 and r["state"] == "finished" and m["expected"] == later and m["hits"] == later,
              f"drag ahead from the start: plays from that bar to the end, scoring only those notes (from beat {start}, {m})")
        page.wait_for_selector(".result")
        page.screenshot(path=str(OUT / "drag-result.png"))
        check(page.get_by_text("Practice mode: one section").count() == 1, "drag ahead: the result says it was part of the song")
        wait_api(page, "fetch('api/attempts?piece_id=twinkle-twinkle').then(r => r.json()).then(j => j.attempts.some(a => a.mode === 'loop'))", timeout=15000)
        part = [a for a in page.evaluate("fetch('api/attempts?piece_id=twinkle-twinkle').then(r => r.json())")["attempts"] if a["mode"] == "loop"]
        full = page.evaluate(f"fetch('api/attempts/{part[0]['id']}').then(r => r.json())") if part else {}
        check(len(part) == 1 and part[0]["completed"] and full.get("section") == {"fromBeat": start, "toBeat": page.evaluate("__pm.tl.length")},
              f"drag ahead: stored as practice of part of the song, which never passes a skill ({len(part)}, {full.get('section')})")

        # 5. Mary with nothing played: a lost-place rewind at the next bar line
        open_piece(page, "mary-had-a-little-lamb")
        page.get_by_role("button", name="100%").click()
        page.locator(".modes button").first.click()
        r = page.evaluate("""() => new Promise((res) => { const t0 = performance.now(); const i = setInterval(() => {
            const pl = __pm.player; if (pl.state === 'gliding' || performance.now() - t0 > 15000) { clearInterval(i);
            res({ state: pl.state, beat: pl.position.logic, rw: pl.debug().rewinds }); } }, 5); })""")
        check(r["state"] == "gliding" and abs(r["beat"] - 4) < 0.2, f"mary: silence rewinds at the bar line after 2 beats ({r})")
        page.get_by_role("button", name="Pause").click()

        # 6. Amazing Grace in Listen mode with the YuE2 stems at 50%
        open_piece(page, "amazing-grace-melody")
        page.get_by_role("button", name="50%").click()
        page.get_by_role("button", name="Listen").click()
        page.wait_for_function("__pm.player.state === 'playing'", timeout=30000)
        page.wait_for_timeout(6000)
        pos = page.evaluate("__pm.player.position")
        page.screenshot(path=str(OUT / "grace-listen.png"))
        check(pos["logic"] > 2, f"amazing grace: stems load and the song moves at 50% (beat {pos['logic']:.2f})")
        page.get_by_role("button", name="Pause").click()

        # 6b. a curriculum song with a vocal and no backing (v0.30): its stems load and it plays
        if (SONGS / "media" / "steady-steps" / "vocals_100.mp3").exists():
            open_piece(page, "steady-steps")
            page.get_by_role("button", name="Listen").click()
            page.wait_for_function("__pm.player.state === 'playing'", timeout=30000)
            page.wait_for_timeout(4000)
            r = page.evaluate("({ beat: __pm.player.position.logic, vocals: !!__pm.player.stems?.vocals, backing: !!__pm.player.stems?.accompaniment })")
            check(r["beat"] > 2 and r["vocals"] and not r["backing"], f"steady steps: a vocal without a backing loads and plays ({r})")
            page.get_by_role("button", name="Pause").click()
        else:
            print("skip: steady-steps has no media here (tools/media/media.py make steady-steps)")

        # 7. Diagnostics (M6): two days of rushed eighth notes, planted for a new student, give
        # today's session a rhythm tap drill; any key counts, and playing it checks the item off
        sid = plant_rushed_quarters()
        page.goto(url)
        page.wait_for_selector(".student")
        page.locator(".student", has_text="Cleo").click()
        page.wait_for_selector(".path .bubble")
        for _ in range(10):                     # skip what comes before the remedy (skipped items go to the end)
            items = page.evaluate(f"fetch('api/students/{sid}/state').then(r => r.json()).then(j => j.session.items)")
            nxt = next(i for i in items if not i["done"])
            if nxt["reason"] == "Focus":
                break
            page.evaluate(f"fetch('api/students/{sid}/session/skip', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{itemId: '{nxt['id']}'}})}})")
        focus = [i for i in items if i["reason"] == "Focus"]
        check([i["kind"] for i in focus] == ["drill", "piece"] and focus[1].get("click") is True and focus[1].get("bars"),
              f"diagnostics: rushed quarter notes get a rhythm tap drill, then the bars with the metronome ({[(i['kind'], i['title']) for i in focus]})")
        page.reload()
        page.wait_for_selector(".upnext, .student")
        if page.locator(".student", has_text="Cleo").count():
            page.locator(".student", has_text="Cleo").click()
        page.wait_for_selector(".upnext")
        try:            # the cached session shows first; the refresh from the server follows
            page.wait_for_function("document.querySelector('.upnext').innerText.toLowerCase().includes('focus')", timeout=10000)
        except Exception:
            pass
        check("focus" in page.locator(".upnext").inner_text().lower(), f"diagnostics: the remedy is up next, as Focus ({page.locator('.upnext').inner_text()[:50]!r})")
        page.get_by_role("button", name="Start").click()
        page.wait_for_function("window.__pm && window.__pm.player.piece.kind === 'drill' && window.__pm.layout")
        page.get_by_role("button", name="100%").click()
        page.locator(".modes button").first.click()
        beats = page.evaluate("__pm.tl.notes.map(n => n.beat)")
        res = page.evaluate(AUTOPLAY, [beats, 0, 40, True])          # every note a semitone off: any key counts
        m = res["debug"]["matcher"]
        check(res["state"] == "finished" and m["hits"] == m["expected"] and m["wrong"] == 0,
              f"diagnostics: the tap drill counts any key ({m})")
        wait_api(page, f"fetch('api/students/{sid}/state').then(r => r.json()).then(j => j.session.items.find(i => i.id === '{focus[0]['id']}').done)", timeout=10000)
        page.screenshot(path=str(OUT / "drill-rhythm.png"))
        check(True, "diagnostics: playing the drill checks the Focus item off")

        check(not errors, "no page errors" + (": " + "; ".join(errors[:5]) if errors else ""))
        browser.close()
    server.should_exit = True
    (OUT / "report.json").write_text(json.dumps(report, indent=1))
    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
