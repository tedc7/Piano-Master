"""The song library and how songs reach it (M7, arch §10.1, §10.7-§10.9).

- **Skill API** (`/api/skill/...`, a Claude skill's token; §10.9): the dev box reads the library, the
  deleted list and the skill map, and submits a package of pieces. Intake checks each piece
  deterministically; a piece that fails is rejected with its report and never staged. The stems
  are uploaded one file at a time, then the package is submitted for review.
- **Review** (`/api/review/...`, the parent): staged songs with their details, notation and stems,
  one song at a time (v0.23). Each waits until the parent approves it, sends it back with what needs
  to change (the skill reads that feedback and resubmits the song, which then replaces it), or never
  allows it (the deleted list). Staging is a separate area (files in <data>/staging/), so nothing
  pending can reach a child (§10.7).
- **Library** (`/api/library/...`, anyone): the approved songs' index, pieces and stems, which
  the app merges with the deployed content; the lesson engine does the same (content.py).
- **Deleted songs** live in the review area too (v0.23): the library holds only approved songs, and
  every other song is a staged item (waiting, sent back for changes, or deleted). "Never allow" in
  the review list and "Delete" in Songs and genres both make a song deleted: intake refuses it
  (title, composer, source ids, melody fingerprint), and its files stay so the parent can send it
  back to review, send it for improvement, or forget it (then it may be imported again).
- **Rules** (§10.1): each child's genre rules (lesson pieces always allowed, every other genre
  blocked until the parent allows it) and song rules, which override the genre.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import analysis, db, fingerprint
from . import content as content_mod
from .parent import require_parent

router = APIRouter()

SLUG = r"^[a-z0-9][a-z0-9-]{0,79}$"
FILE = r"^[A-Za-z0-9_.-]{1,80}\.mp3$"
MAX_MEDIA = 64 * 1024 * 1024
ALWAYS = "lesson-pieces"                    # allowed for every child (§10.1)
NEW_DAYS = 14                               # the "New" badge
# the composition must be public domain or supplied by the parent; the edition openly licensed,
# or the notes retyped and the edition only used to check them (§10.2; the import skill checks the same)
COMPOSITION = {"public-domain", "parent-supplied"}
EDITION = re.compile(r"^(public-domain|CC0|CC BY-SA|CC BY|parent-supplied|retyped)(?![-\w])")
INFO_KEYS = ("level", "hands", "version", "songTitle", "source", "license", "tempoSource", "notes", "flags", "lyrics",
             "checks", "backing", "engine", "warnings")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def folder(*parts: str) -> Path:
    return db.data_dir().joinpath(*parts)


def loads(s: str | None, default: Any = None) -> Any:
    return json.loads(s) if s else default


# ------------------------------------------------------------------------------ tokens (§10.9)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(con, name: str) -> str:
    token = "pmsk_" + secrets.token_urlsafe(32)
    con.execute("INSERT INTO skill_tokens (token_hash, name, created_at) VALUES (?, ?, ?)", (token_hash(token), name, now()))
    return token


def require_skill(authorization: str | None = Header(None)) -> str:
    """A Claude skill's token: it can read and submit, never approve, change rules or delete."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "a skill token is needed (Config > Dev box connection)")
    con = db.connect()
    try:
        r = con.execute("SELECT name FROM skill_tokens WHERE token_hash = ?", (token_hash(token),)).fetchone()
        if not r:
            raise HTTPException(401, "unknown skill token")
        con.execute("UPDATE skill_tokens SET last_used = ? WHERE token_hash = ?", (now(), token_hash(token)))
        return r["name"]
    finally:
        con.close()


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@router.get("/api/skill-tokens", dependencies=[Depends(require_parent)])
def list_tokens():
    con = db.connect()
    try:
        rows = con.execute("SELECT token_hash, name, created_at, last_used FROM skill_tokens ORDER BY created_at").fetchall()
        return {"tokens": [{"id": r["token_hash"][:12], "name": r["name"], "created": r["created_at"], "lastUsed": r["last_used"]}
                           for r in rows]}
    finally:
        con.close()


@router.post("/api/skill-tokens", status_code=201, dependencies=[Depends(require_parent)])
def create_token(body: TokenIn):
    con = db.connect()
    try:
        return {"token": new_token(con, body.name), "name": body.name}
    finally:
        con.close()


@router.delete("/api/skill-tokens/{token_id}", dependencies=[Depends(require_parent)])
def revoke_token(token_id: str):
    con = db.connect()
    try:
        n = con.execute("DELETE FROM skill_tokens WHERE substr(token_hash, 1, 12) = ?", (token_id,)).rowcount
        if not n:
            raise HTTPException(404, "no such token")
        return {"ok": True}
    finally:
        con.close()


# ------------------------------------------------------------------------------ what the library holds

def need_content() -> content_mod.Content:
    c = content_mod.load()
    if c is None:
        raise HTTPException(503, "no content deployed to the API")
    return c


_deployed_prints: tuple[str, dict[str, dict]] | None = None


def deployed_pieces() -> dict[str, dict]:
    """The deployed pieces (built into the app): {id: {song, title, composer, genre, fingerprint}}."""
    global _deployed_prints
    d = content_mod.content_dir()
    version = f"{d}:{content_mod.deployed_version() or ''}"
    if _deployed_prints and _deployed_prints[0] == version:
        return _deployed_prints[1]
    out = {}
    for f in sorted((d / "pieces").glob("*.json")):
        p = json.loads(f.read_text())
        out[p["id"]] = {"song": p.get("song") or p["id"], "title": p["title"], "composer": p.get("composer"),
                        "genre": p.get("genre") or ALWAYS, "fingerprint": sorted(fingerprint.fingerprint(p["notation"])),
                        "sourceIds": []}
    _deployed_prints = (version, out)
    return out


def library_rows(con) -> list[dict]:
    return [{"id": r["piece_id"], "song": r["song"], "title": r["title"], "composer": r["composer"], "genre": r["genre"],
             "sourceIds": loads(r["source_ids"], []), "fingerprint": loads(r["fingerprint"], []),
             "approvedAt": r["approved_at"], "entry": loads(r["entry"], {}), "info": loads(r["info"], {})}
            for r in con.execute("SELECT * FROM library ORDER BY approved_at, piece_id")]


def write_index(con) -> None:
    """<data>/library/index.json: the approved pieces' index entries, which the lesson engine and
    the app merge with the deployed content. Its version changes with every approval or deletion."""
    rows = library_rows(con)
    entries = [{**r["entry"], "library": True, "approvedAt": r["approvedAt"]} for r in rows]
    version = hashlib.sha256(json.dumps([(r["id"], r["approvedAt"]) for r in rows]).encode()).hexdigest()[:8]
    lib = folder("library")
    lib.mkdir(parents=True, exist_ok=True)
    tmp = lib / "index.json.tmp"
    tmp.write_text(json.dumps({"version": version, "pieces": entries}))
    tmp.replace(lib / "index.json")


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# ------------------------------------------------------------------------------ intake (§10.3, §10.7)

class ItemIn(BaseModel):
    """One arrangement: the piece as the content build makes it (notation, analysis, media) and
    what the parent sees about it."""
    piece: dict[str, Any]
    info: dict[str, Any] = Field(default_factory=dict)


class PackageIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(None, max_length=4000)
    items: list[ItemIn] = Field(min_length=1, max_length=60)


def media_files(piece: dict) -> list[dict]:
    """The stem files a piece's media names: [{file, bytes}]."""
    out = {}
    for p in ((piece.get("media") or {}).get("presets") or {}).values():
        for stem in ("vocals", "accompaniment"):
            f = p.get(stem)
            if f:
                out[Path(f["url"]).name] = int(f["bytes"])
    return [{"file": k, "bytes": v} for k, v in sorted(out.items())]


def check_item(con, c: content_mod.Content, item: ItemIn, taken: dict[str, str]) -> dict:
    """The deterministic intake checks (§10.3): the piece is well formed, licensed, on the piano,
    not already in the library (id, melody fingerprint, title and composer), not deleted. Song
    analysis is run again here against the deployed skill map. Returns the checked piece, its
    index entry, errors and warnings."""
    p, info = dict(item.piece), dict(item.info)
    errors, warnings = [], []
    pid = str(p.get("id") or "")
    if not re.match(SLUG, pid):
        errors.append(f"id {pid!r}: lowercase letters, digits and dashes only")
    for k in ("title", "genre", "notation"):
        if not p.get(k):
            errors.append(f"missing {k}")
    if errors:
        return {"pieceId": pid, "errors": errors, "warnings": warnings}
    nota = p["notation"]
    try:
        notes = [n for n in nota["notes"] if not n.get("grace")]
        if not notes or not nota["measures"] or not nota["playbackOrder"] or not nota["phrases"] or not nota.get("length"):
            errors.append("the notation has no notes, measures, playback order or phrases")
        elif any(not 21 <= int(n["pitch"]) <= 108 for n in notes):
            errors.append("a note is off the piano")
        header = nota["header"]
        for k in ("timeSig", "tempo", "keySig"):
            if k not in header:
                errors.append(f"the notation header has no {k}")
    except (KeyError, TypeError, ValueError) as e:
        errors.append(f"the notation isn't in the app's format ({e})")
    if p.get("genre") == ALWAYS or p.get("kind") == "core":
        errors.append("lesson pieces are written for the skill map and deployed with the app, not imported")
    lic = info.get("license") or {}
    if lic.get("composition") not in COMPOSITION:
        errors.append("license.composition must be public-domain or parent-supplied (§10.2)")
    if not EDITION.match(str(lic.get("edition") or "")):
        errors.append(f"license.edition {lic.get('edition')!r} is not an accepted license (§10.2)")
    src = info.get("source") or {}
    if not (src.get("site") and src.get("url")):
        errors.append("source needs the site and URL it came from (§10.4)")
    if errors:
        return {"pieceId": pid, "errors": errors, "warnings": warnings}

    # song analysis against the deployed map (the dev box's is only a proposal)
    skills = c.skill_dicts(set(c.skills))
    an = analysis.analyze(nota, skills)
    song = str(p.get("song") or pid)
    prints = fingerprint.fingerprint(nota)
    deployed = deployed_pieces()
    lib = {r["id"]: r for r in library_rows(con)}
    if pid in deployed or pid in lib:
        errors.append(f"a piece with the id {pid} is already in the library")
    if pid in taken:
        errors.append(f"the package has two pieces with the id {pid}")
    if con.execute("SELECT 1 FROM staged_items WHERE piece_id = ? AND status = 'staged'", (pid,)).fetchone():
        errors.append(f"{pid} is already waiting in the review list: the parent decides on it first")
    src_ids = [str(src["id"])] if src.get("id") else []
    for d in con.execute("SELECT * FROM staged_items WHERE status = 'deleted'"):
        score = fingerprint.similarity(prints, set(loads(d["fingerprint"], [])))
        if score >= fingerprint.SAME or set(src_ids) & set(loads(d["info"], {}).get("sourceIds", [])) or \
                (norm(d["title"]) == norm(p["title"]) and norm(d["composer"]) == norm(p.get("composer"))):
            errors.append(f"deleted by the parent: {d['title']}" + (f" ({d['deleted_reason']})" if d["deleted_reason"] else "") +
                          "; don't offer it again (the parent can send it back for improvement from the review list)")
    for oid, o in {**deployed, **lib}.items():
        if o["song"] == song:
            continue                         # another arrangement of the same song
        score = fingerprint.similarity(prints, set(o.get("fingerprint") or []))
        verdict = fingerprint.verdict(score)
        if verdict == "same song" or set(src_ids) & set(o.get("sourceIds") or []):
            errors.append(f"the same song as {o['title']} ({oid}, melody match {score:.0%}): make it an arrangement of "
                          f"that song (song: {o['song']}) or leave it out")
        elif verdict:
            warnings.append(f"possible duplicate of {o['title']} ({oid}, melody match {score:.0%})")
        elif norm(o["title"]) == norm(p["title"]) and norm(o.get("composer")) == norm(p.get("composer")):
            warnings.append(f"the same title and composer as {oid}")
    if an["beyondMap"]:
        warnings.append("beyond the current skill map: " + ", ".join(an["beyondMap"]) + " (shown as Coming later)")
    files = media_files(p)
    if p.get("media") and not files:
        errors.append("the media names no stem files")
    if p.get("media") and len((p["media"].get("presets") or {})) < 4:
        warnings.append("the media doesn't have all four tempo presets")
    p.update(an)
    p["skillId"] = an["featuredSkills"][0] if an["featuredSkills"] and not an["beyondMap"] else None
    p["kind"] = "library"
    p["contentVersion"] = "lib-" + hashlib.sha256(json.dumps(nota, sort_keys=True).encode()).hexdigest()[:10]
    lo, hi = nota["header"].get("range") or [min(n["pitch"] for n in nota["notes"]), max(n["pitch"] for n in nota["notes"])]
    p["keyboardSize"] = 61 if 36 <= lo and hi <= 96 else 88
    entry = {k: p.get(k) for k in ("id", "title", "composer", "kind", "genre", "level", "hands", "skillId", "keyboardSize",
                                   "song", "songTitle", "version")}
    entry.update(song=song, songTitle=p.get("songTitle") or p["title"], tempo=nota["header"]["tempo"],
                 timeSig=nota["header"]["timeSig"], measures=len(nota["playbackOrder"]), beats=float(nota["length"]),
                 phrases=len(nota["phrases"]), hasMedia=bool(p.get("media")), **an)
    return {"pieceId": pid, "errors": errors, "warnings": warnings, "piece": p, "entry": entry, "song": song,
            "fingerprint": sorted(prints), "files": files, "sourceIds": src_ids}


@router.get("/api/skill/library")
def skill_library(skill: str = Depends(require_skill)):
    """What's already in the library, to avoid duplicates before submitting (§10.9)."""
    con = db.connect()
    try:
        dep = [{"id": k, **v, "deployed": True} for k, v in deployed_pieces().items()]
        lib = [{k: r[k] for k in ("id", "song", "title", "composer", "genre", "sourceIds", "fingerprint", "approvedAt")}
               for r in library_rows(con)]
        return {"pieces": dep + lib}
    finally:
        con.close()


@router.get("/api/skill/deleted")
def skill_deleted(skill: str = Depends(require_skill)):
    con = db.connect()
    try:
        return {"deleted": [{"pieceId": r["piece_id"], "title": r["title"], "composer": r["composer"],
                             "sourceIds": loads(r["info"], {}).get("sourceIds", []), "fingerprint": loads(r["fingerprint"], []),
                             "reason": r["deleted_reason"]}
                            for r in con.execute("SELECT * FROM staged_items WHERE status = 'deleted'")]}
    finally:
        con.close()


@router.get("/api/skill/skill-map")
def skill_map(skill: str = Depends(require_skill)):
    d = content_mod.content_dir()
    if not (d / "skillmap.json").exists():
        raise HTTPException(503, "no content deployed to the API")
    return json.loads((d / "skillmap.json").read_text())


@router.post("/api/skill/packages", status_code=201)
def submit_package(body: PackageIn, skill: str = Depends(require_skill)):
    """Intake: every piece is checked; those that pass wait for their stems (PUT .../media/<file>),
    then POST .../submit stages them for the parent. The report comes back straight away."""
    c = need_content()
    con = db.connect()
    try:
        pkg = uuid.uuid4().hex[:12]
        items, taken = [], {}
        with db.transaction(con):
            con.execute("INSERT INTO packages (id, name, skill, notes, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
                        (pkg, body.name, skill, body.notes, now()))
            for it in body.items:
                r = check_item(con, c, it, taken)
                iid = uuid.uuid4().hex[:12]
                ok = not r["errors"]
                p = r.get("piece") or it.piece
                info = {k: it.info.get(k) for k in INFO_KEYS if it.info.get(k) is not None}
                con.execute("INSERT INTO staged_items (id, package_id, piece_id, song, title, composer, genre, info, report, "
                            "fingerprint, media, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (iid, pkg, r["pieceId"], r.get("song") or r["pieceId"], str(p.get("title") or ""), p.get("composer"),
                             str(p.get("genre") or ""), json.dumps({**info, "entry": r.get("entry"), "sourceIds": r.get("sourceIds", [])}),
                             json.dumps({"errors": r["errors"], "warnings": r["warnings"]}), json.dumps(r.get("fingerprint", [])),
                             json.dumps(r.get("files", [])), "open" if ok else "rejected"))
                if ok:
                    taken[r["pieceId"]] = r["song"]
                    d = folder("staging", pkg, iid)
                    (d / "media").mkdir(parents=True, exist_ok=True)
                    (d / "piece.json").write_text(json.dumps(p))
                items.append({"itemId": iid, "pieceId": r["pieceId"], "accepted": ok, "errors": r["errors"],
                              "warnings": r["warnings"], "media": r.get("files", []) if ok else []})
        return {"id": pkg, "items": items}
    finally:
        con.close()


@router.put("/api/skill/packages/{pkg}/items/{item}/media/{file}")
async def upload_media(pkg: str, item: str, file: str, request: Request, skill: str = Depends(require_skill)):
    if not re.match(FILE, file):
        raise HTTPException(422, "stems are MP3 files with plain names")
    con = db.connect()
    try:
        r = con.execute("SELECT s.media, s.status, p.status AS pstatus FROM staged_items s JOIN packages p ON p.id = s.package_id "
                        "WHERE s.id = ? AND s.package_id = ?", (item, pkg)).fetchone()
        if not r or r["status"] != "open" or r["pstatus"] != "open":
            raise HTTPException(404, "no such item waiting for its stems")
        want = {m["file"]: m["bytes"] for m in loads(r["media"], [])}
        if file not in want:
            raise HTTPException(422, f"{file} isn't one of this piece's stems")
    finally:
        con.close()
    dest = folder("staging", pkg, item, "media", file)
    tmp = dest.with_suffix(".part")
    size = 0
    with tmp.open("wb") as f:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_MEDIA:
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, "stem too large")
            f.write(chunk)
    if size != want[file]:
        tmp.unlink(missing_ok=True)
        raise HTTPException(422, f"{file}: got {size} bytes, the piece says {want[file]}")
    tmp.replace(dest)
    return {"ok": True, "bytes": size}


@router.post("/api/skill/packages/{pkg}/submit")
def stage_package(pkg: str, skill: str = Depends(require_skill)):
    """Stage the package's accepted pieces for the parent's review, once each has all its stems."""
    con = db.connect()
    try:
        p = con.execute("SELECT * FROM packages WHERE id = ?", (pkg,)).fetchone()
        if not p or p["status"] != "open":
            raise HTTPException(404, "no such open package")
        report = []
        with db.transaction(con):
            for r in con.execute("SELECT * FROM staged_items WHERE package_id = ? AND status = 'open'", (pkg,)).fetchall():
                missing = [m["file"] for m in loads(r["media"], []) if not folder("staging", pkg, r["id"], "media", m["file"]).exists()]
                if missing:
                    rep = loads(r["report"], {})
                    rep["errors"] = rep.get("errors", []) + [f"stems not uploaded: {', '.join(missing)}"]
                    con.execute("UPDATE staged_items SET status = 'rejected', report = ? WHERE id = ?", (json.dumps(rep), r["id"]))
                    shutil.rmtree(folder("staging", pkg, r["id"]), ignore_errors=True)
                    report.append({"itemId": r["id"], "pieceId": r["piece_id"], "staged": False, "errors": rep["errors"]})
                else:
                    # a resubmission replaces the song the parent sent back, and carries its feedback
                    old = con.execute("SELECT id, package_id FROM staged_items WHERE piece_id = ? AND status = 'needs-work' "
                                      "ORDER BY decided_at DESC", (r["piece_id"],)).fetchone()
                    con.execute("UPDATE staged_items SET status = 'staged', replaces = ? WHERE id = ?", (old["id"] if old else None, r["id"]))
                    if old:
                        con.execute("UPDATE staged_items SET status = 'resubmitted' WHERE id = ?", (old["id"],))
                        shutil.rmtree(folder("staging", old["package_id"], old["id"]), ignore_errors=True)
                        close_if_done(con, old["package_id"])
                    report.append({"itemId": r["id"], "pieceId": r["piece_id"], "staged": True, "replaces": old["id"] if old else None})
            staged = sum(x["staged"] for x in report)
            con.execute("UPDATE packages SET status = ?, submitted_at = ? WHERE id = ?", ("staged" if staged else "done", now(), pkg))
        return {"id": pkg, "staged": staged, "items": report}
    finally:
        con.close()


@router.get("/api/skill/packages/{pkg}")
def package_status(pkg: str, skill: str = Depends(require_skill)):
    con = db.connect()
    try:
        p = con.execute("SELECT * FROM packages WHERE id = ?", (pkg,)).fetchone()
        if not p:
            raise HTTPException(404, "no such package")
        return {"id": pkg, "status": p["status"], "items": [
            {"itemId": r["id"], "pieceId": r["piece_id"], "status": r["status"], **loads(r["report"], {})}
            for r in con.execute("SELECT * FROM staged_items WHERE package_id = ?", (pkg,))]}
    finally:
        con.close()


# ------------------------------------------------------------------------------ the parent's review (§10.7)

def staged_piece(con, item: str, statuses=("staged", "needs-work", "deleted")) -> tuple[Any, dict]:
    r = con.execute("SELECT * FROM staged_items WHERE id = ?", (item,)).fetchone()
    if not r or r["status"] not in statuses:
        raise HTTPException(404, "no such song waiting for review")
    f = folder("staging", r["package_id"], item, "piece.json")
    if not f.exists():
        raise HTTPException(404, "this song's files are gone (deleted before v0.23)")
    return r, json.loads(f.read_text())


def with_media_urls(piece: dict, base: str) -> dict:
    """The piece with its stems' URLs pointing at `base` (the staging or library files)."""
    p = json.loads(json.dumps(piece))
    for pr in ((p.get("media") or {}).get("presets") or {}).values():
        for stem in ("vocals", "accompaniment"):
            if pr.get(stem):
                pr[stem]["url"] = f"{base}/{Path(pr[stem]['url']).name}"
    return p


def item_out(con, r) -> dict:
    info = loads(r["info"], {})
    entry = info.pop("entry", None) or {}
    out = {"id": r["id"], "pieceId": r["piece_id"], "song": r["song"], "title": r["title"], "composer": r["composer"],
           "genre": r["genre"], "status": r["status"], "info": info, "report": loads(r["report"], {}),
           "hasMedia": bool(loads(r["media"], [])), "feedback": r["feedback"], "decidedAt": r["decided_at"],
           "deletedFrom": r["deleted_from"], "deletedReason": r["deleted_reason"],
           "hasFiles": folder("staging", r["package_id"], r["id"], "piece.json").exists(),
           "summary": {k: entry.get(k) for k in ("hands", "timeSig", "tempo", "beats", "measures", "keyboardSize",
                                                  "mapPoint", "beyondMap", "featuredSkills", "skillId")}}
    if r["replaces"]:
        old = con.execute("SELECT feedback, decided_at FROM staged_items WHERE id = ?", (r["replaces"],)).fetchone()
        if old:
            out["previousFeedback"] = {"feedback": old["feedback"], "decidedAt": old["decided_at"]}
    return out


@router.get("/api/review", dependencies=[Depends(require_parent)])
def review_list():
    """What waits for the parent (§10.7), one song at a time: staged songs, newest batch first, and
    the songs sent back for changes with the parent's feedback. Nothing leaves the list until the
    parent decides on it."""
    con = db.connect()
    try:
        out = []
        for p in con.execute("SELECT * FROM packages WHERE status = 'staged' ORDER BY submitted_at DESC").fetchall():
            items = [item_out(con, r) for r in con.execute(
                "SELECT * FROM staged_items WHERE package_id = ? AND status = 'staged' ORDER BY rowid", (p["id"],))]
            if items:
                out.append({"id": p["id"], "name": p["name"], "skill": p["skill"], "notes": p["notes"], "submitted": p["submitted_at"],
                            "items": items})
        sent_back = [item_out(con, r) for r in con.execute(
            "SELECT * FROM staged_items WHERE status = 'needs-work' ORDER BY decided_at DESC")]
        # the review list itself: every song waiting, in the order they arrived, each with its batch
        items = [{**item_out(con, r), "package": r["package"], "submitted": r["submitted_at"]} for r in con.execute(
            "SELECT s.*, p.name AS package, p.submitted_at FROM staged_items s JOIN packages p ON p.id = s.package_id "
            "WHERE s.status = 'staged' ORDER BY p.submitted_at, s.rowid")]
        deleted = [item_out(con, r) for r in con.execute(
            "SELECT * FROM staged_items WHERE status = 'deleted' ORDER BY decided_at DESC")]
        return {"items": items, "packages": out, "sentBack": sent_back, "deleted": deleted}
    finally:
        con.close()


@router.get("/api/review/items/{item}/piece", dependencies=[Depends(require_parent)])
def review_piece(item: str):
    con = db.connect()
    try:
        r, piece = staged_piece(con, item)
        p = with_media_urls(piece, f"/api/review/items/{item}/media")
        p["id"] = f"staged--{item}"                  # a staged song is never a library song, even in an attempt
        p["title"] = f"{piece['title']} (review)"
        return p
    finally:
        con.close()


@router.get("/api/review/items/{item}/media/{file}", dependencies=[Depends(require_parent)])
def review_media(item: str, file: str):
    if not re.match(FILE, file):
        raise HTTPException(404, "no such file")
    con = db.connect()
    try:
        r, _ = staged_piece(con, item)
        f = folder("staging", r["package_id"], item, "media", file)
    finally:
        con.close()
    if not f.exists():
        raise HTTPException(404, "no such file")
    return FileResponse(f, media_type="audio/mpeg")


def close_if_done(con, pkg: str) -> None:
    """A package is done once none of its songs waits for the parent."""
    if not con.execute("SELECT 1 FROM staged_items WHERE package_id = ? AND status = 'staged'", (pkg,)).fetchone():
        con.execute("UPDATE packages SET status = 'done', reviewed_at = COALESCE(reviewed_at, ?) WHERE id = ? AND status = 'staged'",
                    (now(), pkg))


def waiting(con, item: str, statuses=("staged",)):
    r = con.execute("SELECT * FROM staged_items WHERE id = ?", (item,)).fetchone()
    if not r or r["status"] not in statuses:
        raise HTTPException(404, "that song isn't waiting for this")
    return r


@router.post("/api/review/items/{item}/approve", dependencies=[Depends(require_parent)])
def approve_item(item: str):
    """Add one staged song to the library: it follows each child's genre rules and shows as New."""
    con = db.connect()
    try:
        r = waiting(con, item)
        t = now()
        info = loads(r["info"], {})
        with db.transaction(con):
            src, dest = folder("staging", r["package_id"], item), folder("library", r["piece_id"])
            piece = with_media_urls(json.loads((src / "piece.json").read_text()), f"/api/library/media/{r['piece_id']}")
            shutil.rmtree(dest, ignore_errors=True)
            shutil.move(str(src), dest)
            (dest / "piece.json").write_text(json.dumps(piece))
            entry = {**(info.pop("entry", None) or {}), "hasMedia": bool(piece.get("media"))}
            con.execute("INSERT OR REPLACE INTO library (piece_id, song, title, composer, genre, source_ids, fingerprint, info, "
                        "entry, approved_at, package_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (r["piece_id"], r["song"], r["title"], r["composer"], r["genre"], json.dumps(info.get("sourceIds", [])),
                         r["fingerprint"], json.dumps(info), json.dumps(entry), t, r["package_id"]))
            con.execute("UPDATE staged_items SET status = 'approved', decided_at = ? WHERE id = ?", (t, item))
            close_if_done(con, r["package_id"])
            write_index(con)
        return {"approved": r["piece_id"]}
    finally:
        con.close()


class FeedbackIn(BaseModel):
    feedback: str = Field(min_length=3, max_length=4000)


@router.post("/api/review/items/{item}/improve", dependencies=[Depends(require_parent)])
def improve_item(item: str, body: FeedbackIn):
    """Send a song back with what needs to change. It leaves the waiting list; the feedback waits
    for the Claude skills (GET /api/skill/feedback), and the fixed song, resubmitted under the same
    id, replaces it and shows this feedback beside it."""
    con = db.connect()
    try:
        r = waiting(con, item, ("staged", "deleted"))       # a deleted song can be corrected too
        if not folder("staging", r["package_id"], item, "piece.json").exists():
            raise HTTPException(409, "this song's files are gone: forget it, and the skills can import it again")
        with db.transaction(con):
            con.execute("UPDATE staged_items SET status = 'needs-work', feedback = ?, decided_at = ?, deleted_from = NULL, "
                        "deleted_reason = NULL WHERE id = ?",
                        (body.feedback.strip(), now(), item))
            close_if_done(con, r["package_id"])
        return {"sentBack": r["piece_id"]}
    finally:
        con.close()


class NeverIn(BaseModel):
    reason: str | None = Field(None, max_length=200)


@router.post("/api/review/items/{item}/never", dependencies=[Depends(require_parent)])
def never_item(item: str, body: NeverIn):
    """Never allow this song: it's deleted, so intake refuses it. It stays in the review area's
    Deleted songs, where it can go back to review, be sent for improvement, or be forgotten."""
    con = db.connect()
    try:
        r = waiting(con, item)
        with db.transaction(con):
            con.execute("UPDATE staged_items SET status = 'deleted', decided_at = ?, deleted_from = 'review', deleted_reason = ? "
                        "WHERE id = ?", (now(), body.reason, item))
            close_if_done(con, r["package_id"])
        return {"never": r["piece_id"]}
    finally:
        con.close()


@router.post("/api/review/items/{item}/restore", dependencies=[Depends(require_parent)])
def back_to_review(item: str):
    """A deleted song back onto the waiting list, where the parent can approve it again."""
    con = db.connect()
    try:
        r = waiting(con, item, ("deleted",))
        if not folder("staging", r["package_id"], item, "piece.json").exists():
            raise HTTPException(409, "this song's files are gone: forget it, and the skills can import it again")
        if con.execute("SELECT 1 FROM staged_items WHERE piece_id = ? AND status = 'staged'", (r["piece_id"],)).fetchone():
            raise HTTPException(409, "another version of this song is already waiting for review")
        with db.transaction(con):
            con.execute("UPDATE staged_items SET status = 'staged', deleted_from = NULL, deleted_reason = NULL WHERE id = ?", (item,))
            con.execute("UPDATE packages SET status = 'staged' WHERE id = ?", (r["package_id"],))
        return {"waiting": r["piece_id"]}
    finally:
        con.close()


@router.post("/api/review/items/{item}/forget", dependencies=[Depends(require_parent)])
def forget_item(item: str):
    """Forget a deleted song: its files and record go, and the skills may offer it again."""
    con = db.connect()
    try:
        r = waiting(con, item, ("deleted",))
        with db.transaction(con):
            con.execute("UPDATE staged_items SET status = 'forgotten', decided_at = ? WHERE id = ?", (now(), item))
        shutil.rmtree(folder("staging", r["package_id"], item), ignore_errors=True)
        return {"forgotten": r["piece_id"]}
    finally:
        con.close()


@router.get("/api/skill/feedback")
def skill_feedback(skill: str = Depends(require_skill)):
    """Songs the parent sent back, with what needs to change (§10.7): the skill fixes each one and
    submits it again under the same id, which replaces it in the review list."""
    con = db.connect()
    try:
        rows = con.execute("SELECT s.*, p.name AS package FROM staged_items s JOIN packages p ON p.id = s.package_id "
                           "WHERE s.status = 'needs-work' ORDER BY s.decided_at").fetchall()
        return {"feedback": [{"itemId": r["id"], "pieceId": r["piece_id"], "title": r["title"], "package": r["package"],
                              "feedback": r["feedback"], "sentBack": r["decided_at"]} for r in rows]}
    finally:
        con.close()


# ------------------------------------------------------------------------------ the library (§10.1)

@router.get("/api/library")
def library_index():
    """The approved songs' index entries (merged into the app's content), with the library version."""
    f = content_mod.library_index()
    if not f.exists():
        return {"version": "", "pieces": []}
    idx = json.loads(f.read_text())
    cutoff = datetime.now(timezone.utc).timestamp() - NEW_DAYS * 86400
    for e in idx["pieces"]:
        e["new"] = datetime.fromisoformat(e["approvedAt"]).timestamp() >= cutoff
    return idx


@router.get("/api/library/pieces/{pid}")
def library_piece(pid: str):
    f = folder("library", pid, "piece.json")
    if not re.match(SLUG, pid) or not f.exists():
        raise HTTPException(404, "no such song")
    return json.loads(f.read_text())


@router.get("/api/library/media/{pid}/{file}")
def library_media(pid: str, file: str):
    f = folder("library", pid, "media", file)
    if not re.match(SLUG, pid) or not re.match(FILE, file) or not f.exists():
        raise HTTPException(404, "no such file")
    return FileResponse(f, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})


class DeleteIn(BaseModel):
    reason: str | None = Field(None, max_length=200)


@router.post("/api/library/songs/{song}/delete", dependencies=[Depends(require_parent)])
def delete_song(song: str, body: DeleteIn):
    """Take a song and all its arrangements out of the library (§10.1): each goes back to the review
    area as a deleted song, with its files, so the library holds only approved songs. From there
    the parent can send it back to review, send it for improvement, or forget it."""
    con = db.connect()
    try:
        rows = con.execute("SELECT * FROM library WHERE song = ?", (song,)).fetchall()
        if not rows:
            raise HTTPException(404, "no such song in the library")
        pkg, t = uuid.uuid4().hex[:12], now()
        moved = []
        with db.transaction(con):
            con.execute("INSERT INTO packages (id, name, skill, notes, status, created_at, submitted_at, reviewed_at) "
                        "VALUES (?, ?, 'parent', NULL, 'done', ?, ?, ?)", (pkg, f"Deleted from the library: {rows[0]['title']}", t, t, t))
            for r in rows:
                iid = uuid.uuid4().hex[:12]
                src, dest = folder("library", r["piece_id"]), folder("staging", pkg, iid)
                media = []
                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), dest)
                    media = media_files(json.loads((dest / "piece.json").read_text()))
                info = {**loads(r["info"], {}), "entry": loads(r["entry"], {})}
                con.execute("INSERT INTO staged_items (id, package_id, piece_id, song, title, composer, genre, info, report, fingerprint, "
                            "media, status, decided_at, deleted_from, deleted_reason) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, 'deleted', ?, 'library', ?)",
                            (iid, pkg, r["piece_id"], r["song"], r["title"], r["composer"], r["genre"], json.dumps(info),
                             r["fingerprint"], json.dumps(media), t, body.reason))
                moved.append(r["piece_id"])
            con.execute("DELETE FROM library WHERE song = ?", (song,))
            write_index(con)
        return {"deleted": moved}
    finally:
        con.close()


# ------------------------------------------------------------------------------ rules per child (§10.1)

def rules_of(con, student_id: str) -> tuple[dict[str, bool], dict[str, bool]]:
    genres = {r["genre"]: bool(r["allowed"]) for r in con.execute("SELECT genre, allowed FROM genre_rules WHERE student_id = ?", (student_id,))}
    songs = {r["song"]: bool(r["allowed"]) for r in con.execute("SELECT song, allowed FROM song_rules WHERE student_id = ?", (student_id,))}
    return genres, songs


def allowed(genres: dict[str, bool], songs: dict[str, bool], genre: str | None, song: str) -> bool:
    """A song rule overrides the genre rule; lesson pieces are always allowed; any other genre is
    blocked until the parent allows it (§10.1)."""
    if song in songs:
        return songs[song]
    g = genre or ALWAYS
    return True if g == ALWAYS else genres.get(g, False)


def content_for(con, student_id: str | None, c: content_mod.Content) -> content_mod.Content:
    """The content a child may be offered: their rules applied (the parent sees everything)."""
    if not student_id:
        return c
    genres, songs = rules_of(con, student_id)
    return c.only(lambda pid: allowed(genres, songs, c.genres.get(pid), c.songs.get(pid, pid)))


@router.get("/api/students/{student_id}/rules")
def student_rules(student_id: str):
    """A child's rules, for the app to show only their allowed songs (anyone; not a secret)."""
    con = db.connect()
    try:
        genres, songs = rules_of(con, student_id)
        return {"always": ALWAYS, "genres": genres, "songs": songs}
    finally:
        con.close()


@router.get("/api/rules", dependencies=[Depends(require_parent)])
def all_rules():
    """Every genre and song in the library, and each child's rules (Config > Songs and genres)."""
    c = need_content()
    con = db.connect()
    try:
        songs: dict[str, dict] = {}
        for pid, p in c.pieces.items():
            s = c.songs.get(pid, pid)
            g = c.genres.get(pid) or ALWAYS
            songs.setdefault(s, {"song": s, "title": p.title, "genre": g, "pieces": []})["pieces"].append(pid)
        lib = {r["song"] for r in con.execute("SELECT song FROM library")}
        for s in songs.values():
            s["library"] = s["song"] in lib
        students = []
        for st in con.execute("SELECT id, name, avatar FROM students WHERE status = 'active' ORDER BY sort, created_at"):
            genres, srules = rules_of(con, st["id"])
            students.append({"id": st["id"], "name": st["name"], "avatar": st["avatar"], "genres": genres, "songs": srules})
        return {"always": ALWAYS, "genres": sorted({s["genre"] for s in songs.values()}), "songs": sorted(songs.values(), key=lambda s: s["title"]),
                "students": students}
    finally:
        con.close()


class RuleIn(BaseModel):
    allowed: bool | None = None           # null clears a song rule (the genre decides again)


@router.put("/api/students/{student_id}/rules/genres/{genre}", dependencies=[Depends(require_parent)])
def set_genre_rule(student_id: str, genre: str, body: RuleIn):
    if genre == ALWAYS:
        raise HTTPException(422, "lesson pieces are always allowed")
    con = db.connect()
    try:
        if not con.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone():
            raise HTTPException(404, "no such student")
        if body.allowed is None:
            con.execute("DELETE FROM genre_rules WHERE student_id = ? AND genre = ?", (student_id, genre))
        else:
            con.execute("INSERT OR REPLACE INTO genre_rules (student_id, genre, allowed) VALUES (?, ?, ?)", (student_id, genre, int(body.allowed)))
        return {"ok": True}
    finally:
        con.close()


@router.put("/api/students/{student_id}/rules/songs/{song}", dependencies=[Depends(require_parent)])
def set_song_rule(student_id: str, song: str, body: RuleIn):
    con = db.connect()
    try:
        if not con.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone():
            raise HTTPException(404, "no such student")
        if body.allowed is None:
            con.execute("DELETE FROM song_rules WHERE student_id = ? AND song = ?", (student_id, song))
        else:
            con.execute("INSERT OR REPLACE INTO song_rules (student_id, song, allowed) VALUES (?, ?, ?)", (student_id, song, int(body.allowed)))
        return {"ok": True}
    finally:
        con.close()
