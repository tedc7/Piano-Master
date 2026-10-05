"""Before a deploy: the skill map may name only songs the parent has approved (arch §6.10, v0.27).

    tools/.venv/bin/python tools/library_check.py              # the piano server's library
    tools/.venv/bin/python tools/library_check.py --seeding    # the deploy brings content/library/ in as approved

Every song lives in the piano server's library, and the map deploys with the app, naming each
skill's practice songs by id. This compares the built map (client/public/content/skillmap.json)
with the library (GET /api/library): a practice song that isn't there stops the deploy; submit it
(tools/import_song.py submit) and approve it first. A practice song whose notes changed here since
it was approved is only a warning: the children keep the approved one until the change goes
through the review list too.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import server_config as sc

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "client" / "public" / "content" / "skillmap.json"
SONGS = ROOT / "build" / "songs" / "index.json"
SEED = ROOT / "content" / "library" / "index.json"     # the approved curriculum songs a new install starts with


def library() -> dict[str, dict]:
    with urllib.request.urlopen(sc.server() + "/api/library", context=sc.ssl_context(), timeout=30) as r:
        return {e["id"]: e for e in json.loads(r.read())["pieces"]}


def main(argv: list[str]) -> int:
    seeding = "--seeding" in argv
    skills = json.loads(MAP.read_text())["skills"]
    built = {e["id"]: e for e in json.loads(SONGS.read_text())["pieces"]}
    seed = {e["id"] for e in json.loads(SEED.read_text())["pieces"]} if seeding and SEED.exists() else set()
    try:
        lib = library()
    except OSError as e:
        print(sc.cert_failure(e) or f"can't read the library on {sc.server()} ({e})", file=sys.stderr)
        return 1
    missing, changed = [], []
    for s in skills:
        for pid in s.get("pieces", []):
            if pid not in lib:
                if pid not in seed:
                    missing.append(f"{pid} ({s['id']})")
            elif pid in built and lib[pid].get("contentVersion") and built[pid].get("contentVersion") != lib[pid]["contentVersion"]:
                changed.append(pid)
    for pid in changed:
        print(f"warning: {pid} changed here since it was approved; the children keep the approved one until the change "
              f"is submitted and approved (tools/import_song.py submit content/pieces {pid})")
    if missing:
        print("the map names songs that aren't in the library: submit and approve them first\n  " + "\n  ".join(missing),
              file=sys.stderr)
        return 1
    print(f"library check: every practice song on the map is in the library ({len(lib)} songs"
          + (", with content/library/ as the seed" if seeding else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
