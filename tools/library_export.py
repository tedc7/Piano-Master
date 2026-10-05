"""Keep the approved curriculum songs in the repo, for a fresh install (arch §12, v0.31).

    tools/.venv/bin/python tools/library_export.py            # bring content/library/ up to date with the server
    tools/.venv/bin/python tools/library_export.py --check    # only say what differs (exit 1 if anything does)
    tools/.venv/bin/python tools/library_export.py --verify   # offline: content/library/ is complete for the map

Every song the app plays lives in the piano server's library, and reaches it only through the
parent's review. content/library/ is a copy of the curriculum's part of it, exactly as approved,
in the seed format a new server adopts on its first start (library.adopt_seed, via
`tools/deploy.sh --seed-songs`; docs/fresh-install.md):

    index.json               {"pieces": [the library's index entries]}
    <id>.json                the approved piece, with "info" (license, source) and "display" (the
                             parent's finger-number and letter-name choices)
    media/<id>/<stem>.mp3    its stems (Git LFS, .gitattributes)

Which songs: every song the skill map names (client/public/content/skillmap.json: build it first).
A song is copied only when its source in content/pieces/ is our own or public domain, so a song a
parent supplied for private family use never reaches the public repo. Other library songs stay on
the server and in its backup.

Safe to run again: unchanged songs are left as they are, a changed song's files are replaced, and
songs no longer on the map (or no longer in the library) are removed. Run it after the parent
approves curriculum songs, then commit content/library/.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

import server_config as sc

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "library"
PIECES = ROOT / "content" / "pieces"
MAP = ROOT / "client" / "public" / "content" / "skillmap.json"
PUBLIC = ("original", "public-domain")
LFS_POINTER = b"version https://git-lfs"


def fetch(path: str, raw: bool = False):
    req = urllib.request.Request(sc.server() + path, headers={"Authorization": f"Bearer {sc.skill_token()}"})
    try:
        with urllib.request.urlopen(req, context=sc.ssl_context(), timeout=120) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GET {path}: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        raise SystemExit(sc.cert_failure(e) or f"GET {path}: {e.reason}")
    return body if raw else json.loads(body)


def map_songs() -> list[str]:
    if not MAP.exists():
        raise SystemExit(f"no built skill map at {MAP.relative_to(ROOT)}: run tools/build_content.py first")
    out: list[str] = []
    for s in json.loads(MAP.read_text())["skills"]:
        out += [p for p in s.get("pieces", []) if p not in out]
    return out


def publishable(pid: str) -> str | None:
    """None if the song may go in the public repo, else why not."""
    f = PIECES / f"{pid}.yaml"
    if not f.exists():
        return "its source isn't in content/pieces/"
    comp = ((yaml.safe_load(f.read_text()) or {}).get("license") or {}).get("composition")
    return None if comp in PUBLIC else f"its composition's license is {comp!r}, not our own or public domain"


def dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def stems(piece: dict) -> list[dict]:
    """[{file, bytes}] the piece's media names (as the API's library.media_files)."""
    out = {}
    for p in ((piece.get("media") or {}).get("presets") or {}).values():
        for stem in ("vocals", "accompaniment"):
            if p.get(stem):
                out[Path(p[stem]["url"]).name] = int(p[stem]["bytes"])
    return [{"file": k, "bytes": v} for k, v in sorted(out.items())]


def local_problems(pid: str) -> list[str]:
    """What's missing or wrong in content/library/ for one song (offline)."""
    f = OUT / f"{pid}.json"
    if not f.exists():
        return [f"{pid}: not in content/library/"]
    out = []
    for s in stems(json.loads(f.read_text())):
        m = OUT / "media" / pid / s["file"]
        if not m.exists():
            out.append(f"{pid}: {s['file']} is missing")
        elif m.open("rb").read(len(LFS_POINTER)) == LFS_POINTER:
            out.append(f"{pid}: {s['file']} is a Git LFS pointer (git lfs pull)")
        elif m.stat().st_size != s["bytes"]:
            out.append(f"{pid}: {s['file']} is {m.stat().st_size} bytes, the piece says {s['bytes']}")
    return out


def verify() -> int:
    songs = map_songs()
    idx = json.loads((OUT / "index.json").read_text())["pieces"] if (OUT / "index.json").exists() else []
    have = {e["id"] for e in idx}
    problems = [f"{pid}: not in index.json" for pid in songs if pid not in have]
    for pid in songs:
        problems += local_problems(pid)
    for p in problems:
        print(p, file=sys.stderr)
    with_media = sum(1 for e in idx if stems(json.loads((OUT / f"{e['id']}.json").read_text())))
    if problems:
        print(f"content/library/ isn't ready for a fresh install: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"content/library/ is complete: {len(songs)} curriculum songs, {with_media} with stems")
    return 0


def export(check: bool) -> int:
    songs = map_songs()
    lib = {e["id"]: e for e in fetch("/api/skill/library")["pieces"]}
    missing = [pid for pid in songs if pid not in lib]
    if missing:
        print("the map names songs that aren't in the library (approve them first): " + ", ".join(missing), file=sys.stderr)
        return 1
    blocked = {pid: why for pid in songs if (why := publishable(pid))}
    for pid, why in blocked.items():
        print(f"skip {pid}: {why}", file=sys.stderr)
    want = [pid for pid in songs if pid not in blocked]
    old = {e["id"]: e for e in json.loads((OUT / "index.json").read_text())["pieces"]} if (OUT / "index.json").exists() else {}
    changes, entries = [], []
    for pid in want:
        got = fetch(f"/api/skill/library/{pid}")
        piece = {**got["piece"], "info": got["info"], "display": got["display"]}
        entry = {**got["entry"], "approvedAt": got["approvedAt"]}
        entries.append(entry)
        f = OUT / f"{pid}.json"
        text = dump(piece)
        same = f.exists() and f.read_text() == text and old.get(pid) == entry and not local_problems(pid)
        if same:
            continue
        changes.append(f"{'update' if pid in old else 'add'} {pid}" + (f" ({len(got['files'])} stems)" if got["files"] else ""))
        if check:
            continue
        mdir = OUT / "media" / pid
        if mdir.exists():
            shutil.rmtree(mdir)
        for s in got["files"]:
            data = fetch(f"/api/library/media/{pid}/{s['file']}", raw=True)
            if len(data) != s["bytes"]:
                raise SystemExit(f"{pid}/{s['file']}: got {len(data)} bytes, the library says {s['bytes']}")
            mdir.mkdir(parents=True, exist_ok=True)
            (mdir / s["file"]).write_bytes(data)
        OUT.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    gone = sorted(set(old) - set(want))
    changes += [f"remove {pid}" for pid in gone]
    if not check:
        for pid in gone:
            (OUT / f"{pid}.json").unlink(missing_ok=True)
            shutil.rmtree(OUT / "media" / pid, ignore_errors=True)
        index = dump({"pieces": entries})
        if not (OUT / "index.json").exists() or (OUT / "index.json").read_text() != index:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "index.json").write_text(index)
    for c in changes:
        print(("would " if check else "") + c)
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) if OUT.exists() else 0
    digest = hashlib.sha256((OUT / "index.json").read_bytes()).hexdigest()[:8] if (OUT / "index.json").exists() else "-"
    print(f"{'differs from' if changes else 'matches'} the server's library: {len(want)} curriculum songs"
          + (f", {len(blocked)} skipped" if blocked else "") + f"; content/library/ {size / 1e6:.1f} MB, index {digest}")
    return 1 if check and changes else 0


def main(argv: list[str]) -> int:
    if "--verify" in argv:
        return verify()
    return export(check="--check" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
