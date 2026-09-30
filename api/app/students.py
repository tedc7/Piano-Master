"""Students, their settings and favorites (M4), and the lesson engine's view of each student:
skill states, today's session, practice days and the progress report (M5). Arch §5, §8.

Student functions need no login (§11.1): choosing a student is enough. Adding, editing,
archiving and deleting students, and the settings a parent sets, need a parent session.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pydantic import BaseModel, Field

from . import content as content_mod
from . import db, diagnostics, engine, library
from .parent import is_parent, require_parent

router = APIRouter()

UUID = r"^[0-9a-fA-F-]{8,64}$"
SLUG = r"^[A-Za-z0-9_.-]{1,100}$"
PRESET = r"^(50|75|90|100)$"

# Student.settings (arch §5); the parent sets the first four, the Play screen remembers the rest per song
DEFAULTS: dict[str, Any] = {"autoRewind": True, "rewindBars": 2, "backingVolume": 2.0, "otherHand": True, "vocalsOff": [],
                            "click": {}, "presets": {}}


def today() -> date:
    """The local calendar day on the server (TZ), which is what every "day" means (8.6)."""
    return datetime.now().astimezone().date()


def local_day(ts: datetime) -> date:
    return ts.astimezone().date()


def settings_of(raw: str | None) -> dict[str, Any]:
    s = {**DEFAULTS, **json.loads(raw or "{}")}
    s["vocalsOff"], s["click"], s["presets"] = list(s["vocalsOff"]), dict(s["click"]), dict(s["presets"])
    return s


def student_out(r) -> dict[str, Any]:
    return {"id": r["id"], "name": r["name"], "avatar": r["avatar"], "status": r["status"], "startDate": r["start_date"],
            "settings": settings_of(r["settings"]), "targetMinutes": r["target_minutes"]}


def get_student(con, student_id: str):
    r = con.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if not r:
        raise HTTPException(404, "no such student")
    return r


def need_content() -> content_mod.Content:
    c = content_mod.load()
    if c is None:
        raise HTTPException(503, "no content deployed to the API")
    return c


def caps_for(con, device_id: str | None) -> dict[str, bool]:
    if not device_id:
        return {}
    r = con.execute("SELECT profile FROM devices WHERE id = ?", (device_id,)).fetchone()
    return engine.device_caps(json.loads(r["profile"]) if r else None)


# ------------------------------------------------------------------------------ models

class StudentIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    avatar: str = Field(min_length=1, max_length=16)


class StudentSettingsIn(BaseModel):
    autoRewind: bool | None = None
    rewindBars: int | None = Field(None, ge=1, le=8)
    backingVolume: float | None = Field(None, ge=0, le=3)
    otherHand: bool | None = None       # one-hand practice: the app plays the other hand
    resetSongChoices: bool = False


class StudentPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=40)
    avatar: str | None = Field(None, min_length=1, max_length=16)
    status: Literal["active", "archived"] | None = None
    sort: int | None = None
    settings: StudentSettingsIn | None = None


class SongPrefIn(BaseModel):
    """What the Play screen remembers per song (arch §3): vocals, metronome and tempo preset."""
    pieceId: str = Field(pattern=SLUG)
    vocalsOff: bool | None = None
    click: bool | None = None
    preset: str | None = Field(None, pattern=PRESET)


class CheckIn(BaseModel):
    """A concept lesson's Check cards (7.8): 1 point right first time, 0.5 the second time."""
    questions: int = Field(ge=0, le=200)
    points: float = Field(ge=0, le=200)


class LessonDoneIn(BaseModel):
    itemId: str | None = Field(None, max_length=40)
    seconds: float = Field(0, ge=0, le=3600)
    deviceId: str | None = Field(None, pattern=UUID)
    check: CheckIn | None = None


class SkipIn(BaseModel):
    itemId: str = Field(max_length=40)


# ------------------------------------------------------------------------------ students (M4)

@router.get("/api/students")
def list_students(all: bool = False, x_parent_token: str | None = Header(default=None)):
    if all and not is_parent(x_parent_token):
        raise HTTPException(401, "parent login needed")
    con = db.connect()
    try:
        sql = "SELECT * FROM students" + ("" if all else " WHERE status = 'active'") + " ORDER BY sort, created_at"
        return {"students": [student_out(r) for r in con.execute(sql)]}
    finally:
        con.close()


@router.post("/api/students", status_code=201, dependencies=[Depends(require_parent)])
def add_student(body: StudentIn):
    con = db.connect()
    try:
        sid = str(uuid.uuid4())
        n = con.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM students").fetchone()[0]
        con.execute("INSERT INTO students (id, name, avatar, start_date, sort, created_at, target_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (sid, body.name.strip(), body.avatar, today().isoformat(), n, datetime.now().astimezone().isoformat(),
                     engine.TARGET_START))
        return student_out(get_student(con, sid))
    finally:
        con.close()


@router.patch("/api/students/{student_id}", dependencies=[Depends(require_parent)])
def edit_student(student_id: str, body: StudentPatch):
    con = db.connect()
    try:
        with db.transaction(con):
            r = get_student(con, student_id)
            s = settings_of(r["settings"])
            if body.settings:
                for k in ("autoRewind", "rewindBars", "backingVolume", "otherHand"):
                    v = getattr(body.settings, k)
                    if v is not None:
                        s[k] = v
                if body.settings.resetSongChoices:
                    s["vocalsOff"], s["click"], s["presets"] = [], {}, {}
            con.execute("UPDATE students SET name = ?, avatar = ?, status = ?, sort = ?, settings = ? WHERE id = ?",
                        ((body.name or r["name"]).strip(), body.avatar or r["avatar"], body.status or r["status"],
                         r["sort"] if body.sort is None else body.sort, json.dumps(s), student_id))
        return student_out(get_student(con, student_id))
    finally:
        con.close()


@router.delete("/api/students/{student_id}", dependencies=[Depends(require_parent)])
def delete_student(student_id: str):
    """Deletes the student and everything recorded for them (arch §3: students can be deleted)."""
    con = db.connect()
    try:
        with db.transaction(con):
            get_student(con, student_id)
            con.execute("DELETE FROM attempts WHERE student_id = ?", (student_id,))
            con.execute("UPDATE client_logs SET student_id = NULL WHERE student_id = ?", (student_id,))
            con.execute("DELETE FROM students WHERE id = ?", (student_id,))   # the rest cascades
        return {"deleted": student_id}
    finally:
        con.close()


@router.patch("/api/students/{student_id}/prefs")
def song_pref(student_id: str, body: SongPrefIn):
    con = db.connect()
    try:
        with db.transaction(con):
            s = settings_of(get_student(con, student_id)["settings"])
            p = body.pieceId
            if body.vocalsOff is not None:
                s["vocalsOff"] = [x for x in s["vocalsOff"] if x != p] + ([p] if body.vocalsOff else [])
            if body.click is not None:
                s["click"][p] = body.click
            if body.preset is not None:
                s["presets"][p] = body.preset
            con.execute("UPDATE students SET settings = ? WHERE id = ?", (json.dumps(s), student_id))
        return {"settings": s}
    finally:
        con.close()


@router.put("/api/students/{student_id}/favorites/{piece_id}")
def add_favorite(student_id: str, piece_id: str = Path(pattern=SLUG)):
    con = db.connect()
    try:
        get_student(con, student_id)
        con.execute("INSERT OR IGNORE INTO favorites (student_id, piece_id, added_at) VALUES (?, ?, ?)",
                    (student_id, piece_id, datetime.now().astimezone().isoformat()))
        return {"favorites": favorites(con, student_id)}
    finally:
        con.close()


@router.delete("/api/students/{student_id}/favorites/{piece_id}")
def remove_favorite(student_id: str, piece_id: str = Path(pattern=SLUG)):
    con = db.connect()
    try:
        get_student(con, student_id)
        con.execute("DELETE FROM favorites WHERE student_id = ? AND piece_id = ?", (student_id, piece_id))
        return {"favorites": favorites(con, student_id)}
    finally:
        con.close()


def favorites(con, student_id: str) -> list[str]:
    return [r[0] for r in con.execute("SELECT piece_id FROM favorites WHERE student_id = ? ORDER BY added_at", (student_id,))]


# ------------------------------------------------------------------------------ lesson engine (M5)

@router.get("/api/students/{student_id}/state")
def student_state(student_id: str, device_id: str | None = Query(None, pattern=UUID)):
    """Everything the student's screens need: skill states, today's session (built on the first
    request of the day), today's practice time and streak, and favorites."""
    c = need_content()
    con = db.connect()
    try:
        c = library.content_for(con, student_id, c)       # only the songs this child is allowed (§10.1)
        with db.transaction(con):
            r = get_student(con, student_id)
            t = today()
            caps = caps_for(con, device_id)
            session = engine.get_session(con, c, student_id, t, caps)
            states = engine.load_states(con, c, student_id)
            engine.refresh(c, states, caps)
            return {"student": student_out(r), "contentVersion": c.version,
                    "skills": engine.skills_out(c, states, t, session), "session": session,
                    "day": engine.day_out(con, student_id, t, session), "favorites": favorites(con, student_id)}
    finally:
        con.close()


@router.post("/api/students/{student_id}/lessons/{skill_id}/done")
def lesson_done(student_id: str, skill_id: str, body: LessonDoneIn):
    c = need_content()
    con = db.connect()
    try:
        c = library.content_for(con, student_id, c)
        with db.transaction(con):
            get_student(con, student_id)
            try:
                return engine.lesson_done(con, c, student_id, skill_id, today(), body.itemId, body.seconds,
                                          caps_for(con, body.deviceId),
                                          (body.check.questions, body.check.points) if body.check else None)
            except KeyError:
                raise HTTPException(404, "no such skill")
    finally:
        con.close()


@router.post("/api/students/{student_id}/session/skip")
def skip(student_id: str, body: SkipIn):
    con = db.connect()
    try:
        with db.transaction(con):
            get_student(con, student_id)
            s = engine.skip_item(con, student_id, body.itemId, today())
            if s is None:
                raise HTTPException(404, "no session today")
            return {"session": s}
    finally:
        con.close()


@router.get("/api/students/{student_id}/drills/{drill_id}")
def get_drill(student_id: str, drill_id: str = Path(pattern=SLUG)):
    """A generated drill (8.9), as a piece the Play screen plays like any other."""
    con = db.connect()
    try:
        r = con.execute("SELECT piece FROM drills WHERE id = ? AND student_id = ?", (drill_id, student_id)).fetchone()
        if not r:
            raise HTTPException(404, "no such drill")
        return json.loads(r["piece"])
    finally:
        con.close()


@router.get("/api/students/{student_id}/progress")
def progress(student_id: str):
    """The progress report (8.11), for My Progress and the parent's reports: skills, star trends,
    practice days, strengths by track, working-on areas, error patterns (8.8; found again for the
    report), and the content runway."""
    c = need_content()
    con = db.connect()
    try:
        r = get_student(con, student_id)
        t = today()
        with db.transaction(con):
            found = diagnostics.run(con, c, student_id, t)
        states = engine.load_states(con, c, student_id)
        engine.refresh(c, states)
        since = t - timedelta(days=27)
        rows = engine.practice_days(con, student_id, since, t)
        days = []
        for i in range(28):
            d = (since + timedelta(days=i)).isoformat()
            x = rows.get(d)
            g, f = (x["guided_sec"], x["free_sec"]) if x else (0, 0)
            days.append({"date": d, "guidedSec": g, "freeSec": f, "practiced": engine.practiced(g, f),
                         "sessionCompleted": bool(x and x["session_completed"])})
        attempts = con.execute(
            "SELECT started_at, piece_id, mode, completed, tempo_preset, accuracy_stars, timing_stars, context FROM attempts "
            "WHERE student_id = ? AND started_at >= ? ORDER BY started_at DESC",
            (student_id, (datetime.now().astimezone() - timedelta(days=28)).isoformat())).fetchall()
        weeks = []
        for w in range(4):
            lo, hi = t - timedelta(days=7 * (w + 1) - 1), t - timedelta(days=7 * w)
            xs = [a for a in attempts if a["completed"] and a["mode"] == "play" and
                  lo <= local_day(datetime.fromisoformat(a["started_at"])) <= hi]
            acc = [a["accuracy_stars"] for a in xs]
            tim = [a["timing_stars"] for a in xs if a["timing_stars"] is not None]
            weeks.insert(0, {"from": lo.isoformat(), "plays": len(xs), "accuracyStars": sum(acc) / len(acc) if acc else None,
                             "timingStars": sum(tim) / len(tim) if tim else None})
        week_ago = t - timedelta(days=6)
        stars_week = sum(a["accuracy_stars"] for a in attempts if a["completed"] and a["mode"] == "play"
                         and local_day(datetime.fromisoformat(a["started_at"])) >= week_ago)
        tracks: dict[str, list[float]] = {}
        for s in c.order:
            m = states[s.id].best_mastery
            if m is not None:
                tracks.setdefault(s.track, []).append(m)
        by_track = sorted(({"track": k, "mastery": sum(v) / len(v), "skills": len(v)} for k, v in tracks.items()),
                          key=lambda x: -x["mastery"])
        name = {s.id: s.name for s in c.order}
        stuck_skills = [name[k] for k, st in states.items() if st.stuck]
        working = [name[k] for k, st in states.items() if st.status == "current"]
        great = [name[k] for k, st in sorted(states.items(), key=lambda kv: -(kv[1].best_mastery or 0))
                 if st.status == "mastered" or (st.passed and (st.best_mastery or 0) >= engine.MASTERY_LEVEL)][:3]
        mastered_week = [name[k] for k, st in states.items() if st.mastered_date and engine.day(st.mastered_date) >= week_ago]
        counts = {k: sum(1 for st in states.values() if st.status == k) for k in ("locked", "current", "passed", "mastered")}
        return {
            "student": student_out(r), "skills": engine.skills_out(c, states, t), "counts": counts,
            "days": days, "streak": engine.streak(con, student_id, t), "starsThisWeek": stars_week,
            "weeks": weeks, "tracks": by_track, "greatAt": great, "workingOn": working, "stuck": stuck_skills,
            "masteredThisWeek": mastered_week, "targetMinutes": r["target_minutes"],
            "guidedMinutes28": round(sum(d["guidedSec"] for d in days) / 60, 1),
            "freeMinutes28": round(sum(d["freeSec"] for d in days) / 60, 1),
            "runway": engine.runway(con, c, student_id, states, t),
            "patterns": [p for p in found if p["status"] != "resolved" or (p["resolvedDate"] or "") >= (t - timedelta(days=28)).isoformat()],
            "recent": [{"startedAt": a["started_at"], "pieceId": a["piece_id"], "mode": a["mode"], "completed": bool(a["completed"]),
                        "tempoPreset": a["tempo_preset"], "accuracyStars": a["accuracy_stars"], "timingStars": a["timing_stars"],
                        "context": a["context"]} for a in attempts[:12]],
        }
    finally:
        con.close()


def after_attempt(con, student_id: str, a, content: content_mod.Content | None) -> dict[str, Any] | None:
    """Called by POST /api/attempts inside its transaction, for a student's attempt."""
    if content is None:
        return None
    e = a.evaluation
    info = engine.AttemptInfo(
        piece_id=a.pieceId, day=local_day(a.startedAt), context=a.context, mode=a.mode, completed=a.completed,
        accuracy=e.accuracy, accuracy_stars=e.accuracyStars, timing_stars=e.timingStars, duration_sec=a.durationSec or 0,
        preset=a.conditions.tempoPreset, skill_id=a.skillId, item_id=a.itemId,
        tricky_phrase=(a.tricky or {}).get("phrase"), factor=e.factor,
        note_errors=[{"kind": x.get("kind"), "bar": x.get("bar")} for x in a.noteErrors])
    return engine.record_attempt(con, content, student_id, info, caps_for(con, a.deviceId))
