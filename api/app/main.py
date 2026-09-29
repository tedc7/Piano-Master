"""Piano App API (arch §4, §5, §11): devices, attempts with raw events, client logs, and (in
parent.py and students.py) parent login, students and the lesson engine.

Serves everything under /api (Caddy passes the prefix through). Home network only, behind Caddy;
student functions need no login (§11.1); parent functions need a parent session.
"""
from __future__ import annotations

import html
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import content, db, parent, students

VERSION = "0.3.0"
MAX_BODY = 4 * 1024 * 1024          # an attempt with every key press is well under this
LOG_DAYS = 90                       # client logs are kept for 90 days (§11.3)
UUID = r"^[0-9a-fA-F-]{8,64}$"
SLUG = r"^[A-Za-z0-9_.-]{1,100}$"

schema_version = 0


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global schema_version
    schema_version = db.migrate()
    yield


app = FastAPI(title="Piano App API", version=VERSION, lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.include_router(parent.router)
app.include_router(students.router)


@app.middleware("http")
async def limit_body(request: Request, call_next):
    size = request.headers.get("content-length")
    if size and size.isdigit() and int(size) > MAX_BODY:
        return JSONResponse({"detail": "request too large"}, status_code=413)
    return await call_next(request)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def dumps(v: Any) -> str | None:
    return None if v is None else json.dumps(v, separators=(",", ":"))


# ------------------------------------------------------------------------------------ models

class Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class DeviceIn(BaseModel):
    userAgent: str | None = Field(None, max_length=500)
    clientVersion: str | None = Field(None, max_length=40)
    profile: dict[str, Any] | None = None


class Conditions(Loose):
    mode: str
    tempoPreset: Literal["100", "90", "75", "50"]
    hands: Literal["both", "R", "L"]
    handsWritten: Literal["R", "L", "RL"]
    sectionOnly: bool
    extraHints: bool
    rewinds: int = Field(ge=0)


class Evaluation(Loose):
    expected: int = Field(ge=0)
    matched: int = Field(ge=0)
    rawAccuracy: float
    rawTiming: float | None
    factor: float
    accuracy: float
    timing: float | None
    accuracyStars: float = Field(ge=0, le=5)
    timingStars: float | None = Field(None, ge=0, le=5)


class AttemptIn(BaseModel):
    id: str = Field(pattern=UUID)
    deviceId: str = Field(pattern=UUID)
    studentId: str | None = Field(None, pattern=UUID)   # none for the parent: those plays are never a student's
    pieceId: str = Field(pattern=SLUG)
    skillId: str | None = Field(None, max_length=120)    # the skill the session item was for
    itemId: str | None = Field(None, max_length=40)      # the session item (Guided)
    arrangementId: str | None = Field(None, pattern=SLUG)
    contentVersion: str | None = Field(None, max_length=64)
    context: Literal["guided", "free"] = "free"
    mode: Literal["play", "loop"]
    completed: bool
    startedAt: datetime
    durationSec: float | None = Field(None, ge=0)
    conditions: Conditions
    evaluation: Evaluation
    latencyOffsetMs: float | None = None
    displayOffsetMs: float | None = None
    section: dict[str, float] | None = None
    perPhraseErrors: list[int] = Field(default_factory=list, max_length=2000)
    noteErrors: list[dict[str, Any]] = Field(default_factory=list, max_length=20000)
    tricky: dict[str, Any] | None = None
    rawEvents: list[dict[str, Any]] = Field(default_factory=list, max_length=50000)
    passes: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    clientVersion: str | None = Field(None, max_length=40)


class LogEntry(BaseModel):
    time: datetime
    level: Literal["info", "warning", "error"]
    message: str = Field(max_length=2000)
    context: Any = None


class LogsIn(BaseModel):
    deviceId: str | None = Field(None, pattern=UUID)
    studentId: str | None = Field(None, pattern=UUID)
    entries: list[LogEntry] = Field(max_length=500)


# ------------------------------------------------------------------------------------ routes

def local_time(iso: str | None) -> str:
    """A stored UTC time in the server's time zone (TZ), for people to read."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%b %d %H:%M")
    except ValueError:
        return iso


def stars_text(v: float | None) -> str:
    if v is None:
        return "–"
    return "★" * int(v) + ("½" if v % 1 else "")


@app.get("/api/", response_class=HTMLResponse)
def index():
    """A page for people: what the API is, recent attempts and problems, and the JSON endpoints."""
    con = db.connect()
    try:
        attempts = con.execute(
            "SELECT started_at, piece_id, mode, tempo_preset, completed, accuracy_stars, timing_stars, conditions_factor, "
            "raw_accuracy, id FROM attempts ORDER BY started_at DESC LIMIT 25").fetchall()
        counts = con.execute("SELECT COUNT(*), COUNT(DISTINCT device_id) FROM attempts").fetchone()
        devices = con.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        kids = con.execute("SELECT COUNT(*) FROM students WHERE status = 'active'").fetchone()[0]
        problems = con.execute(
            "SELECT time, level, message FROM client_logs WHERE level != 'info' ORDER BY id DESC LIMIT 10").fetchall()
    finally:
        con.close()
    e = html.escape
    c = content.load()
    cv = c.version if c else None
    rows = "".join(
        f"<tr><td>{e(local_time(a['started_at']))}</td><td>{e(a['piece_id'])}</td><td>{e(a['mode'])}</td>"
        f"<td>{e(a['tempo_preset'])}%</td><td>{'done' if a['completed'] else 'stopped'}</td>"
        f"<td class=s>{stars_text(a['accuracy_stars'])}</td><td class=s>{stars_text(a['timing_stars'])}</td>"
        f"<td>{a['raw_accuracy'] * 100:.0f}% × {a['conditions_factor']:.2f}</td>"
        f"<td><a href='attempts/{e(a['id'])}'>json</a></td></tr>"
        for a in attempts) or "<tr><td colspan=9>No attempts yet: they arrive when a piece is played in Play or Loop mode.</td></tr>"
    probs = "".join(f"<li>{e(local_time(x['time']))} <b>{e(x['level'])}</b> {e(x['message'])}</li>" for x in problems) \
        or "<li>None</li>"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1"><title>Piano App API</title>
<style>
 body {{ font: 16px/1.4 -apple-system, "Segoe UI", Roboto, sans-serif; margin: 24px; color: #1f1f24; background: #f7f5f0; }}
 table {{ border-collapse: collapse; background: #fff; }} td, th {{ padding: 6px 10px; border-bottom: 1px solid #e2dfd7; text-align: left; }}
 .s {{ color: #d99a00; white-space: nowrap; }} code {{ background: #ecebe6; padding: 1px 5px; border-radius: 4px; }}
 .muted {{ color: #6c6a72; }}
</style></head><body>
<h1>Piano App API</h1>
<p>Version {VERSION}, database schema {schema_version}, content {e(cv or "not deployed")}. {kids} student(s);
{counts[0]} attempts from {counts[1]} device(s); {devices} device(s) registered.
The app itself is at <a href="/app/">/app/</a>.</p>
<h2>Recent attempts</h2>
<table><tr><th>Started</th><th>Piece</th><th>Mode</th><th>Tempo</th><th></th><th>Notes</th><th>Timing</th><th>Accuracy × aids</th><th></th></tr>{rows}</table>
<h2>Recent problems (client warnings and errors)</h2><ul>{probs}</ul>
<h2>Endpoints (JSON)</h2>
<ul>
 <li><a href="health">GET /api/health</a></li>
 <li><a href="attempts">GET /api/attempts</a> <span class=muted>?piece_id=… &amp;device_id=… &amp;student_id=… &amp;limit=…</span>, and <code>GET /api/attempts/&lt;id&gt;</code> with every key press</li>
 <li><a href="students">GET /api/students</a>, and per student <code>/state</code> (skills and today's session) and <code>/progress</code></li>
 <li><a href="logs">GET /api/logs</a> <span class=muted>?level=error</span></li>
 <li><code>POST /api/attempts</code>, <code>PUT /api/devices/&lt;id&gt;</code>, <code>POST /api/logs</code>: used by the app</li>
 <li><a href="docs">Interactive docs</a> <span class=muted>(loads its script from the internet)</span></li>
</ul>
</body></html>"""


@app.get("/api/health")
def health():
    con = db.connect()
    try:
        con.execute("SELECT 1").fetchone()
    finally:
        con.close()
    c = content.load()
    return {"ok": True, "version": VERSION, "schema": schema_version, "contentVersion": c.version if c else None}


def touch_device(con, device_id: str, body: DeviceIn | None = None) -> None:
    t = now()
    con.execute(
        "INSERT INTO devices (id, created_at, last_seen, user_agent, client_version, profile) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen, "
        "user_agent = COALESCE(excluded.user_agent, devices.user_agent), "
        "client_version = COALESCE(excluded.client_version, devices.client_version)",
        (device_id, t, t, body.userAgent if body else None, body.clientVersion if body else None,
         dumps(body.profile) if body and body.profile else "{}"),
    )
    if body and body.profile is not None:
        con.execute("UPDATE devices SET profile = ? WHERE id = ?", (dumps(body.profile), device_id))


@app.put("/api/devices/{device_id}")
def put_device(device_id: str, body: DeviceIn, x_parent_token: str | None = Header(default=None)):
    """Registers the device; the DeviceProfile (its settings) changes only in parent mode."""
    if not re.match(UUID, device_id):
        raise HTTPException(422, "bad device id")
    if body.profile is not None and not parent.is_parent(x_parent_token):
        raise HTTPException(401, "parent login needed to change device settings")
    con = db.connect()
    try:
        touch_device(con, device_id, body)
        row = con.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return device_out(row)
    finally:
        con.close()


@app.get("/api/devices/{device_id}")
def get_device(device_id: str):
    con = db.connect()
    try:
        row = con.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no such device")
        return device_out(row)
    finally:
        con.close()


def device_out(row) -> dict:
    return {"id": row["id"], "createdAt": row["created_at"], "lastSeen": row["last_seen"],
            "userAgent": row["user_agent"], "clientVersion": row["client_version"], "profile": json.loads(row["profile"])}


@app.post("/api/attempts", status_code=201)
def post_attempt(a: AttemptIn, response: Response):
    """Stores an attempt once (outbox resends are harmless) and, for a student, updates their
    practice time, skill states and today's session in the same transaction."""
    con = db.connect()
    try:
        with db.transaction(con):
            if con.execute("SELECT 1 FROM attempts WHERE id = ?", (a.id,)).fetchone():
                response.status_code = 200            # an outbox resend: already stored
                return {"id": a.id, "stored": False}
            if a.studentId and not con.execute("SELECT 1 FROM students WHERE id = ?", (a.studentId,)).fetchone():
                raise HTTPException(422, "no such student")
            touch_device(con, a.deviceId)
            e = a.evaluation
            con.execute(
                "INSERT INTO attempts (id, device_id, student_id, piece_id, arrangement_id, content_version, context, mode, "
                "completed, started_at, received_at, duration_sec, tempo_preset, conditions, conditions_factor, raw_accuracy, "
                "raw_timing, accuracy, timing_score, accuracy_stars, timing_stars, latency_offset_ms, display_offset_ms, section, "
                "per_phrase_errors, note_errors, tricky, evaluation, raw_events, passes, client_version, skill_id, item_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (a.id, a.deviceId, a.studentId, a.pieceId, a.arrangementId or a.pieceId, a.contentVersion, a.context, a.mode,
                 int(a.completed), a.startedAt.isoformat(), now(), a.durationSec, a.conditions.tempoPreset,
                 dumps(a.conditions.model_dump()), e.factor, e.rawAccuracy, e.rawTiming, e.accuracy, e.timing,
                 e.accuracyStars, e.timingStars, a.latencyOffsetMs, a.displayOffsetMs, dumps(a.section),
                 dumps(a.perPhraseErrors), dumps(a.noteErrors), dumps(a.tricky), dumps(e.model_dump()),
                 dumps(a.rawEvents), dumps(a.passes), a.clientVersion, a.skillId, a.itemId),
            )
            effects = students.after_attempt(con, a.studentId, a, content.load()) if a.studentId else None
        return {"id": a.id, "stored": True, "effects": effects}
    finally:
        con.close()


SUMMARY = ("id, device_id, student_id, piece_id, mode, completed, started_at, duration_sec, tempo_preset, "
           "conditions_factor, raw_accuracy, raw_timing, accuracy, timing_score, accuracy_stars, timing_stars, tricky, "
           "context, skill_id, item_id")


def attempt_out(row, full: bool) -> dict:
    out = {
        "id": row["id"], "deviceId": row["device_id"], "studentId": row["student_id"], "pieceId": row["piece_id"],
        "mode": row["mode"], "completed": bool(row["completed"]), "startedAt": row["started_at"],
        "durationSec": row["duration_sec"], "tempoPreset": row["tempo_preset"], "conditionsFactor": row["conditions_factor"],
        "rawAccuracy": row["raw_accuracy"], "rawTiming": row["raw_timing"], "accuracy": row["accuracy"],
        "timing": row["timing_score"], "accuracyStars": row["accuracy_stars"], "timingStars": row["timing_stars"],
        "tricky": json.loads(row["tricky"]) if row["tricky"] else None,
        "context": row["context"], "skillId": row["skill_id"], "itemId": row["item_id"],
    }
    if full:
        for col, key in (("conditions", "conditions"), ("section", "section"), ("per_phrase_errors", "perPhraseErrors"),
                         ("note_errors", "noteErrors"), ("evaluation", "evaluation"), ("raw_events", "rawEvents"),
                         ("passes", "passes")):
            out[key] = json.loads(row[col]) if row[col] else None
        out.update({"arrangementId": row["arrangement_id"], "contentVersion": row["content_version"],
                    "receivedAt": row["received_at"], "latencyOffsetMs": row["latency_offset_ms"],
                    "displayOffsetMs": row["display_offset_ms"], "clientVersion": row["client_version"]})
    return out


@app.get("/api/attempts")
def list_attempts(piece_id: str | None = Query(None, pattern=SLUG), device_id: str | None = Query(None, pattern=UUID),
                  student_id: str | None = Query(None, pattern=UUID), limit: int = Query(50, ge=1, le=500)):
    where, args = [], []
    if student_id:
        where.append("student_id = ?"); args.append(student_id)
    if piece_id:
        where.append("piece_id = ?"); args.append(piece_id)
    if device_id:
        where.append("device_id = ?"); args.append(device_id)
    sql = f"SELECT {SUMMARY} FROM attempts" + (" WHERE " + " AND ".join(where) if where else "") + \
          " ORDER BY started_at DESC LIMIT ?"
    con = db.connect()
    try:
        return {"attempts": [attempt_out(r, False) for r in con.execute(sql, (*args, limit))]}
    finally:
        con.close()


@app.get("/api/attempts/{attempt_id}")
def get_attempt(attempt_id: str):
    con = db.connect()
    try:
        row = con.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no such attempt")
        return attempt_out(row, True)
    finally:
        con.close()


@app.post("/api/logs", status_code=201)
def post_logs(body: LogsIn):
    t = now()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOG_DAYS)).isoformat()
    con = db.connect()
    try:
        with db.transaction(con):
            con.executemany(
                "INSERT INTO client_logs (time, received_at, device_id, student_id, level, message, context) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(e.time.isoformat(), t, body.deviceId, body.studentId, e.level, e.message, dumps(e.context)) for e in body.entries],
            )
            con.execute("DELETE FROM client_logs WHERE received_at < ?", (cutoff,))
        return {"stored": len(body.entries)}
    finally:
        con.close()


@app.get("/api/logs")
def list_logs(level: Literal["info", "warning", "error"] | None = None, limit: int = Query(100, ge=1, le=1000)):
    con = db.connect()
    try:
        sql = "SELECT * FROM client_logs" + (" WHERE level = ?" if level else "") + " ORDER BY id DESC LIMIT ?"
        rows = con.execute(sql, ((level,) if level else ()) + (limit,)).fetchall()
        return {"logs": [{"time": r["time"], "receivedAt": r["received_at"], "deviceId": r["device_id"], "level": r["level"],
                          "message": r["message"], "context": json.loads(r["context"]) if r["context"] else None} for r in rows]}
    finally:
        con.close()
