"""Parent login (arch §3 "Parent mode", §11.1): the PIN is checked here against a stored scrypt
hash. 5 wrong tries lock parent login for 5 minutes, doubling with each further lockout. A
parent session ends after the auto-logout time without a request, or on logout.

The client holds the session token in memory only and sends it as X-Parent-Token.
A forgotten PIN is cleared on the server: `python -m app.admin reset-pin` in the container.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import db

PIN = r"^\d{4,8}$"
MAX_TRIES = 5
LOCK_MINUTES = 5
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}

router = APIRouter()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pin.encode(), salt=salt, dklen=32, **SCRYPT)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_pin(pin: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, salt, want = stored.split("$")
        got = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), dklen=32, **SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(got.hex(), want)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def parent_row(con):
    return con.execute("SELECT * FROM parent WHERE id = 1").fetchone()


def session_ok(con, token: str | None) -> bool:
    """A live parent session: refreshes its last use. Expired sessions are removed."""
    if not token:
        return False
    minutes = parent_row(con)["auto_logout_minutes"]
    cutoff = (utcnow() - timedelta(minutes=minutes)).isoformat()
    con.execute("DELETE FROM parent_sessions WHERE last_used < ?", (cutoff,))
    th = token_hash(token)
    if not con.execute("SELECT 1 FROM parent_sessions WHERE token_hash = ?", (th,)).fetchone():
        return False
    con.execute("UPDATE parent_sessions SET last_used = ? WHERE token_hash = ?", (utcnow().isoformat(), th))
    return True


def require_parent(x_parent_token: str | None = Header(default=None)) -> None:
    """Dependency for parent-only routes: 401 without a live parent session."""
    con = db.connect()
    try:
        if not session_ok(con, x_parent_token):
            raise HTTPException(401, "parent login needed")
    finally:
        con.close()


def is_parent(token: str | None) -> bool:
    con = db.connect()
    try:
        return session_ok(con, token)
    finally:
        con.close()


class PinIn(BaseModel):
    pin: str = Field(pattern=PIN)


class PinChange(BaseModel):
    pin: str = Field(pattern=PIN)
    currentPin: str | None = Field(None, pattern=PIN)


class ParentSettingsIn(BaseModel):
    autoLogoutMinutes: int = Field(ge=2, le=60)


@router.get("/api/parent")
def parent_info():
    con = db.connect()
    try:
        r = parent_row(con)
        locked = r["locked_until"] and r["locked_until"] > utcnow().isoformat()
        return {"pinSet": bool(r["pin_hash"]), "lockedUntil": r["locked_until"] if locked else None,
                "autoLogoutMinutes": r["auto_logout_minutes"]}
    finally:
        con.close()


@router.post("/api/parent/login")
def login(body: PinIn):
    con = db.connect()
    try:
        with db.transaction(con):
            r = parent_row(con)
            if not r["pin_hash"]:
                raise HTTPException(409, "no PIN set yet")
            now = utcnow()
            if r["locked_until"] and r["locked_until"] > now.isoformat():
                raise HTTPException(423, {"message": "parent login is locked", "lockedUntil": r["locked_until"]})
            if check_pin(body.pin, r["pin_hash"]):
                con.execute("UPDATE parent SET failed_attempts = 0, lockouts = 0, locked_until = NULL WHERE id = 1")
                token = secrets.token_urlsafe(32)
                con.execute("INSERT INTO parent_sessions (token_hash, created_at, last_used) VALUES (?, ?, ?)",
                            (token_hash(token), now.isoformat(), now.isoformat()))
                return {"token": token, "autoLogoutMinutes": r["auto_logout_minutes"]}
            failed = r["failed_attempts"] + 1
            if failed >= MAX_TRIES:
                lockouts = r["lockouts"] + 1
                until = (now + timedelta(minutes=LOCK_MINUTES * 2 ** (lockouts - 1))).isoformat()
                con.execute("UPDATE parent SET failed_attempts = 0, lockouts = ?, locked_until = ? WHERE id = 1", (lockouts, until))
                locked = {"message": "too many wrong PINs", "lockedUntil": until}
            else:
                con.execute("UPDATE parent SET failed_attempts = ? WHERE id = 1", (failed,))
                locked = None
        # outside the transaction, so the failed try is kept
        if locked:
            raise HTTPException(423, locked)
        raise HTTPException(401, {"message": "wrong PIN", "triesLeft": MAX_TRIES - failed})
    finally:
        con.close()


@router.post("/api/parent/logout")
def logout(x_parent_token: str | None = Header(default=None)):
    con = db.connect()
    try:
        if x_parent_token:
            con.execute("DELETE FROM parent_sessions WHERE token_hash = ?", (token_hash(x_parent_token),))
        return {"ok": True}
    finally:
        con.close()


@router.post("/api/parent/ping", dependencies=[Depends(require_parent)])
def ping():
    """Keeps the parent session alive while the parent is using Config without other requests."""
    return {"ok": True}


@router.post("/api/parent/pin")
def set_pin(body: PinChange, x_parent_token: str | None = Header(default=None)):
    """Choose the first PIN (open, once), or change it (parent session and the current PIN)."""
    con = db.connect()
    try:
        with db.transaction(con):
            r = parent_row(con)
            if r["pin_hash"]:
                if not session_ok(con, x_parent_token):
                    raise HTTPException(401, "parent login needed")
                if not body.currentPin or not check_pin(body.currentPin, r["pin_hash"]):
                    raise HTTPException(403, "the current PIN is not right")
            con.execute("UPDATE parent SET pin_hash = ?, failed_attempts = 0, lockouts = 0, locked_until = NULL WHERE id = 1",
                        (hash_pin(body.pin),))
            token = None
            if not r["pin_hash"]:
                # the first PIN logs the parent in, to add the students
                token = secrets.token_urlsafe(32)
                now = utcnow().isoformat()
                con.execute("INSERT INTO parent_sessions (token_hash, created_at, last_used) VALUES (?, ?, ?)",
                            (token_hash(token), now, now))
        return {"ok": True, "token": token, "autoLogoutMinutes": r["auto_logout_minutes"]}
    finally:
        con.close()


@router.put("/api/parent/settings", dependencies=[Depends(require_parent)])
def parent_settings(body: ParentSettingsIn):
    con = db.connect()
    try:
        con.execute("UPDATE parent SET auto_logout_minutes = ? WHERE id = 1", (body.autoLogoutMinutes,))
        return {"autoLogoutMinutes": body.autoLogoutMinutes}
    finally:
        con.close()
