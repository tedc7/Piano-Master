"""Smoke-test dist/ in headless Chromium before deploying to the iPad.

    .venv/bin/python check_page.py [--play]

Serves dist/ locally, opens the page at the iPad A16's full-screen size (1180 x 820, 2x),
renders every song's staff, reports each render's stats and problems, and saves screenshots of
the staff (start, middle, end) to check/ for a visual review. With --play it also plays each song
with audio for 12 s, rewinds once and switches tempo, and prints the run results.
Headless Chromium is not the iPad: frame rates and audio latency here mean nothing for the test.
"""
from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
DIST, OUT = HERE / "dist", HERE / "check"


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    play = "--play" in sys.argv
    OUT.mkdir(exist_ok=True)
    httpd = serve()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1180, "height": 820}, device_scale_factor=2)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(url)
        page.wait_for_function("window.__probe && window.__probe.layout", timeout=60000)
        ids = page.eval_on_selector_all("#song option", "os => os.map(o => o.value)")
        for sid in ids:
            page.select_option("#song", sid)
            page.wait_for_function(f"window.__probe.song.id === '{sid}' && window.__probe.layout && "
                                   f"document.getElementById('stMsg').textContent.startsWith('Staff')", timeout=120000)
            info = page.evaluate("""() => { const l = window.__probe.layout;
                return {measures: l.measures, width: l.width, ms: Math.round(l.renderMs), tick: l.tickables,
                        lyrics: l.lyrics.length, problems: l.problems}; }""")
            print(f"{sid}: {info['measures']} measures, {info['width']} px, {info['ms']} ms, {info['tick']} notes/rests, "
                  f"{info['lyrics']} lyric syllables, problems {len(info['problems'])}")
            for prob in info["problems"][:10]:
                print("   ", prob)
            page.click("#check")
            page.evaluate("document.getElementById('panel').hidden = true")
            width = info["width"]
            for name, frac in (("start", 0.0), ("middle", 0.45), ("end", 0.93)):
                pos = int(max(0, width * frac))
                page.evaluate(f"document.getElementById('strip').style.transform = 'translate3d(-{pos}px,0,0)'")
                page.locator("#stage").screenshot(path=str(OUT / f"{sid}-{name}.png"))
            page.click("#check")
            page.evaluate("document.getElementById('panel').hidden = true")
            if play and info["measures"] and page.is_enabled("#play"):
                page.click("#play")
                page.wait_for_timeout(9000)
                page.click("#rewind")
                page.wait_for_timeout(3000)
                options = page.eval_on_selector_all("#preset option", "os => os.map(o => o.value)")
                if "50" in options:
                    page.select_option("#preset", "50")
                    page.wait_for_timeout(4000)
                page.click("#play")
                page.wait_for_timeout(300)
                print(page.inner_text("#panel").split("STAFF")[0].strip())
                page.evaluate("document.getElementById('panel').hidden = true")
                page.select_option("#preset", "100") if "100" in options else None
        print("page errors:", errors or "none")
        browser.close()
    httpd.shutdown()


if __name__ == "__main__":
    main()
