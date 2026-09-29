"""Headless check of the probe's test app: each FluidSynth piece loads its accompaniment-only
stems and plays in Listen mode at 100% and 50%, with no page errors.

    ../../tools/.venv/bin/python check_site.py      # after build_site.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
APP = HERE / "dist" / "app"
ROOT = HERE.parents[1]


def serve():
    os.environ["PIANO_DB"] = str(Path(tempfile.mkdtemp()) / "piano.db")
    os.environ["PIANO_CONTENT"] = str(ROOT / "client" / "dist" / "content")
    sys.path.insert(0, str(ROOT / "api"))
    from starlette.staticfiles import StaticFiles
    from app.main import app
    app.mount("/", StaticFiles(directory=str(APP), html=True), name="client")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}/"


def main() -> int:
    url = serve()
    fails = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 1180, "height": 820})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        for pid in ("canon-in-d--musescore", "blue-danube--generaluser", "ode-to-joy--musescore", "amazing-grace--organ"):
            for preset in ("100", "50"):
                page.goto(url + f"#/play/{pid}")
                page.wait_for_function(f"window.__pm && window.__pm.player.piece.id === '{pid}' && window.__pm.layout", timeout=20000)
                page.get_by_role("button", name=f"{preset}%").click()
                page.get_by_role("button", name="Listen").click()
                page.wait_for_function("__pm.player.state === 'playing'", timeout=30000)
                page.wait_for_timeout(3000)
                st = page.evaluate("({pos: __pm.player.position.logic, stems: __pm.player.hasStems, vocals: !!document.querySelector('button.toggle') && [...document.querySelectorAll('button.toggle')].some(b => b.innerText === 'Vocals')})")
                ok = st["pos"] > 1 and st["stems"] and st["vocals"] == pid.startswith("amazing-grace")
                fails += not ok
                print(("PASS" if ok else "FAIL"), pid, preset, st)
                page.get_by_role("button", name="Pause").click()
        print(("FAIL" if errors else "PASS"), "no page errors", errors[:3])
        fails += bool(errors)
        browser.close()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
