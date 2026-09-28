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
from pathlib import Path

import uvicorn

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "client" / "dist"
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

# Plays the piece's expected notes when the song clock reaches them, optionally skipping some
# beats, until the attempt finishes (or `untilRewinds` rewinds have happened).
AUTOPLAY = """
([skip, untilRewinds, maxSeconds]) => new Promise((resolve) => {
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
        if (skip.some((b) => Math.abs(b - n.beat) < 1e-6)) continue;
        window.__midiSend([0x90, n.pitch, 80]);
        setTimeout(() => window.__midiSend([0x80, n.pitch, 0]), 120);
      }
    }
    const done = st === "finished" || (untilRewinds && rewinds >= untilRewinds) || performance.now() - t0 > maxSeconds * 1000;
    if (done) { clearInterval(timer); resolve({ state: st, rewinds, debug: player.debug() }); }
  }, 4);
})
"""


def serve():
    """The App API plus the built client at /, on a free local port, with a throwaway database."""
    os.environ["PIANO_DB"] = str(Path(tempfile.mkdtemp()) / "piano.db")
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
        check(page.locator("button.main").is_disabled(), "no piano: Play is disabled in Play mode")
        page.get_by_role("button", name="Listen").click()
        check(not page.locator("button.main").is_disabled(), "no piano: Play is enabled in Listen mode")
        ctx.close()

        # 2. with the scripted keyboard
        ctx = browser.new_context(**ipad)
        ctx.add_init_script(FAKE_MIDI)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.goto(url)
        page.wait_for_selector(".skill")
        page.wait_for_timeout(300)
        check(page.locator(".skill").count() == 5, "home: 5 placeholder skills listed")
        check(page.locator(".card").count() == 6, "home: 6 pieces listed")
        check(page.get_by_text("Test Piano").count() > 0, "home: the real piano is chosen, virtual ports skipped")
        page.screenshot(path=str(OUT / "home.png"))

        index = json.loads((DIST / "content" / "index.json").read_text())
        for piece in index["pieces"]:
            open_piece(page, piece["id"])
            lay = page.evaluate("({p: __pm.layout.problems, w: __pm.layout.width, h: __pm.layout.height, ms: __pm.layout.renderMs, "
                                "els: __pm.layout.noteEls.filter(Boolean).length, n: __pm.tl.notes.length, lyr: __pm.layout.lyrics.length})")
            report[piece["id"]] = lay
            check(not lay["p"], f"{piece['id']}: staff renders with no problems ({lay['w']}x{lay['h']} px, {lay['ms']:.0f} ms)")
            check(lay["els"] == lay["n"], f"{piece['id']}: every note has a note-head element ({lay['els']}/{lay['n']})")
            page.screenshot(path=str(OUT / f"play-{piece['id']}.png"))

        # 3. Twinkle played cleanly at 100%: no rewinds, every note matched
        open_piece(page, "twinkle-twinkle")
        page.get_by_role("button", name="100%").click()
        page.locator("button.main").click()
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "twinkle-playing.png"))
        r = page.evaluate(AUTOPLAY, [[], 0, 60])
        res = page.evaluate("__pm.player.debug()")
        check(r["state"] == "finished", f"twinkle clean run: finishes ({r['state']})")
        check(r["rewinds"] == 0 and res["matcher"]["hits"] == res["matcher"]["expected"] and res["matcher"]["wrong"] == 0,
              f"twinkle clean run: no rewinds, all notes matched ({res['matcher']}, rewinds {r['rewinds']})")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "twinkle-result.png"))
        check(page.locator(".result").count() == 1, "twinkle clean run: result card shown")
        check(page.locator('.result [aria-label="Notes: 5 of 5 stars"]').count() == 1 and
              page.locator('.result [aria-label="Timing: 5 of 5 stars"]').count() == 1, "twinkle clean run: 5 stars for notes and timing")
        page.wait_for_function("fetch('api/attempts?piece_id=twinkle-twinkle').then(r => r.json()).then(j => j.attempts.length > 0)", timeout=15000)
        stored = page.evaluate("fetch('api/attempts?piece_id=twinkle-twinkle').then(r => r.json())")["attempts"]
        check(len(stored) == 1 and stored[0]["completed"] and stored[0]["accuracyStars"] == 5 and stored[0]["tempoPreset"] == "100",
              f"twinkle clean run: attempt stored by the API ({[(a['completed'], a['accuracyStars']) for a in stored]})")
        full = page.evaluate(f"fetch('api/attempts/{stored[0]['id']}').then(r => r.json())") if stored else {}
        check(len([e for e in full.get("rawEvents", []) if e["type"] == "on"]) == 42, "twinkle clean run: all 42 key presses stored as raw events")

        # 4. Hot Cross Buns with two missed notes in phrase 1: one rewind, then a clean pass
        open_piece(page, "hot-cross-buns")
        page.get_by_role("button", name="100%").click()
        page.locator("button.main").click()
        r = page.evaluate(AUTOPLAY, [[4, 5], 1, 30])
        check(r["rewinds"] == 1 and r["debug"]["rewinds"][0] == 1, f"hot cross buns: 2 misses in the first phrase rewind it once ({r['debug']['rewinds']})")
        page.wait_for_timeout(250)
        page.screenshot(path=str(OUT / "hcb-glide.png"))
        r = page.evaluate(AUTOPLAY, [[], 0, 40])
        res = r["debug"]["matcher"]
        check(r["state"] == "finished" and res["hits"] == res["expected"], f"hot cross buns: clean second pass counts ({res})")
        page.wait_for_selector(".result")
        page.screenshot(path=str(OUT / "hcb-result.png"))
        check(page.locator('.result [aria-label="Notes: 4.5 of 5 stars"]').count() == 1, "hot cross buns: one rewind caps notes at 4.5 stars")
        check(page.get_by_text("Practice mode: 1 rewind").count() == 1, "hot cross buns: practice-mode chip lists the rewind")
        page.get_by_role("button", name="Practice tricky part").click()
        page.wait_for_function("__pm.player.mode === 'loop' && __pm.player.preset === '90'")
        check(page.get_by_text("Bars 1–2").count() > 0, "tricky part: loops bars 1-2 at the next slower preset (90%)")
        r = page.evaluate(AUTOPLAY, [[], 1, 30])
        page.wait_for_selector(".loopnote")
        page.screenshot(path=str(OUT / "hcb-loop.png"))
        check("6 of 6 notes" in page.locator(".loopnote").inner_text(), f"tricky part: a clean loop pass shows its result ({page.locator('.loopnote').inner_text()})")
        page.wait_for_function("fetch('api/attempts?piece_id=hot-cross-buns').then(r => r.json()).then(j => j.attempts.some(a => a.mode === 'loop'))", timeout=15000)
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

        # 5. Mary with nothing played: a lost-place rewind at the next bar line
        open_piece(page, "mary-had-a-little-lamb")
        page.get_by_role("button", name="100%").click()
        page.locator("button.main").click()
        r = page.evaluate("""() => new Promise((res) => { const t0 = performance.now(); const i = setInterval(() => {
            const pl = __pm.player; if (pl.state === 'gliding' || performance.now() - t0 > 15000) { clearInterval(i);
            res({ state: pl.state, beat: pl.position.logic, rw: pl.debug().rewinds }); } }, 5); })""")
        check(r["state"] == "gliding" and abs(r["beat"] - 4) < 0.2, f"mary: silence rewinds at the bar line after 2 beats ({r})")
        page.get_by_role("button", name="Pause").click()

        # 6. Amazing Grace in Listen mode with the YuE2 stems at 50%
        open_piece(page, "amazing-grace-melody")
        page.get_by_role("button", name="Listen").click()
        page.get_by_role("button", name="50%").click()
        page.locator("button.main").click()
        page.wait_for_function("__pm.player.state === 'playing'", timeout=30000)
        page.wait_for_timeout(6000)
        pos = page.evaluate("__pm.player.position")
        page.screenshot(path=str(OUT / "grace-listen.png"))
        check(pos["logic"] > 2, f"amazing grace: stems load and the song moves at 50% (beat {pos['logic']:.2f})")
        page.get_by_role("button", name="Pause").click()
        page.get_by_role("button", name="Settings").click()
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT / "settings.png"))

        check(not errors, "no page errors" + (": " + "; ".join(errors[:5]) if errors else ""))
        browser.close()
    server.should_exit = True
    (OUT / "report.json").write_text(json.dumps(report, indent=1))
    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
