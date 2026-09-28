"""Piano App API (arch §4, §5, §11): devices, attempts with raw events, and client logs.

Serves everything under /api (Caddy passes the prefix through). Home network only, behind Caddy;
student functions need no login (§11.1). Parent-only reads arrive with parent mode in M4.
"""
from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import db

VERSION = "0.2.0"
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
    studentId: str | None = Field(None, pattern=UUID)
    pieceId: str = Field(pattern=SLUG)
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

@app.get("/api/health")
def health():
    con = db.connect()
    try:
        con.execute("SELECT 1").fetchone()
    finally:
        con.close()
    return {"ok": True, "version": VERSION, "schema": schema_version}


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
def put_device(device_id: str, body: DeviceIn):
    if not re.match(UUID, device_id):
        raise HTTPException(422, "bad device id")
    con = db.connect()
    try:
        touch_device(con, device_id, body)
        row = con.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return device_out(row)
    finally:
        con.close()


def device_out(row) -> dict:
    return {"id": row["id"], "createdAt": row["created_at"], "lastSeen": row["last_seen"],
            "userAgent": row["user_agent"], "clientVersion": row["client_version"], "profile": json.loads(row["profile"])}


@app.post("/api/attempts", status_code=201)
def post_attempt(a: AttemptIn, response: Response):
    con = db.connect()
    try:
        with db.transaction(con):
            if con.execute("SELECT 1 FROM attempts WHERE id = ?", (a.id,)).fetchone():
                response.status_code = 200            # an outbox resend: already stored
                return {"id": a.id, "stored": False}
            touch_device(con, a.deviceId)
            e = a.evaluation
            con.execute(
                "INSERT INTO attempts (id, device_id, student_id, piece_id, arrangement_id, content_version, context, mode, "
                "completed, started_at, received_at, duration_sec, tempo_preset, conditions, conditions_factor, raw_accuracy, "
                "raw_timing, accuracy, timing_score, accuracy_stars, timing_stars, latency_offset_ms, display_offset_ms, section, "
                "per_phrase_errors, note_errors, tricky, evaluation, raw_events, passes, client_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (a.id, a.deviceId, a.studentId, a.pieceId, a.arrangementId or a.pieceId, a.contentVersion, a.context, a.mode,
                 int(a.completed), a.startedAt.isoformat(), now(), a.durationSec, a.conditions.tempoPreset,
                 dumps(a.conditions.model_dump()), e.factor, e.rawAccuracy, e.rawTiming, e.accuracy, e.timing,
                 e.accuracyStars, e.timingStars, a.latencyOffsetMs, a.displayOffsetMs, dumps(a.section),
                 dumps(a.perPhraseErrors), dumps(a.noteErrors), dumps(a.tricky), dumps(e.model_dump()),
                 dumps(a.rawEvents), dumps(a.passes), a.clientVersion),
            )
        return {"id": a.id, "stored": True}
    finally:
        con.close()


SUMMARY = ("id, device_id, student_id, piece_id, mode, completed, started_at, duration_sec, tempo_preset, "
           "conditions_factor, raw_accuracy, raw_timing, accuracy, timing_score, accuracy_stars, timing_stars, tricky")


def attempt_out(row, full: bool) -> dict:
    out = {
        "id": row["id"], "deviceId": row["device_id"], "studentId": row["student_id"], "pieceId": row["piece_id"],
        "mode": row["mode"], "completed": bool(row["completed"]), "startedAt": row["started_at"],
        "durationSec": row["duration_sec"], "tempoPreset": row["tempo_preset"], "conditionsFactor": row["conditions_factor"],
        "rawAccuracy": row["raw_accuracy"], "rawTiming": row["raw_timing"], "accuracy": row["accuracy"],
        "timing": row["timing_score"], "accuracyStars": row["accuracy_stars"], "timingStars": row["timing_stars"],
        "tricky": json.loads(row["tricky"]) if row["tricky"] else None,
    }
    if full:
        for col, key in (("conditions", "conditions"), ("section", "section"), ("per_phrase_errors", "perPhraseErrors"),
                         ("note_errors", "noteErrors"), ("evaluation", "evaluation"), ("raw_events", "rawEvents"),
                         ("passes", "passes")):
            out[key] = json.loads(row[col]) if row[col] else None
        out.update({"arrangementId": row["arrangement_id"], "contentVersion": row["content_version"],
                    "context": row["context"], "receivedAt": row["received_at"], "latencyOffsetMs": row["latency_offset_ms"],
                    "displayOffsetMs": row["display_offset_ms"], "clientVersion": row["client_version"]})
    return out


@app.get("/api/attempts")
def list_attempts(piece_id: str | None = Query(None, pattern=SLUG), device_id: str | None = Query(None, pattern=UUID),
                  limit: int = Query(50, ge=1, le=500)):
    where, args = [], []
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
