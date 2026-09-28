"""App API: health, devices, attempts (idempotent for the outbox), logs, and migrations."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db, main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PIANO_DB", str(tmp_path / "piano.db"))
    with TestClient(main.app) as c:
        yield c


def attempt(**over):
    a = {
        "id": str(uuid.uuid4()), "deviceId": str(uuid.uuid4()), "pieceId": "twinkle-twinkle", "mode": "play",
        "completed": True, "startedAt": "2026-09-28T10:00:00.000Z", "durationSec": 31.5, "contentVersion": "abc123",
        "conditions": {"mode": "play", "tempoPreset": "75", "hands": "both", "handsWritten": "R", "sectionOnly": False,
                       "extraHints": False, "rewinds": 1},
        "evaluation": {"expected": 42, "matched": 40, "rawAccuracy": 0.95, "rawTiming": 0.9, "factor": 0.817,
                       "accuracy": 0.776, "timing": 0.735, "accuracyStars": 3.0, "timingStars": 2.5, "aids": [], "hint": None},
        "perPhraseErrors": [0, 2, 0], "noteErrors": [{"kind": "missed", "beat": 9, "pitch": 62, "bar": 3}],
        "tricky": {"phrase": 1, "bars": [3, 4]},
        "rawEvents": [{"t": 1000.5, "type": "on", "pitch": 60, "velocity": 80, "beat": 0.02, "pass": 0}],
        "passes": [{"from": 0, "t": 900}], "latencyOffsetMs": 80, "displayOffsetMs": 80,
    }
    a.update(over)
    return a


def test_health_reports_the_schema(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["schema"] == db.migrations()[-1][0]


def test_device_register_and_refresh(client):
    d = str(uuid.uuid4())
    r = client.put(f"/api/devices/{d}", json={"userAgent": "iPad", "clientVersion": "0.2.0"})
    assert r.status_code == 200 and r.json()["userAgent"] == "iPad"
    r = client.put(f"/api/devices/{d}", json={})
    assert r.json()["userAgent"] == "iPad"
    assert client.put("/api/devices/not a uuid", json={}).status_code in (404, 422)


def test_attempt_is_stored_once_and_read_back(client):
    a = attempt()
    r = client.post("/api/attempts", json=a)
    assert r.status_code == 201 and r.json()["stored"] is True
    r = client.post("/api/attempts", json=a)                 # an outbox resend
    assert r.status_code == 200 and r.json()["stored"] is False
    full = client.get(f"/api/attempts/{a['id']}").json()
    assert full["rawEvents"] == a["rawEvents"] and full["tempoPreset"] == "75" and full["accuracyStars"] == 3.0
    assert full["arrangementId"] == "twinkle-twinkle" and full["tricky"] == {"phrase": 1, "bars": [3, 4]}
    lst = client.get("/api/attempts", params={"piece_id": "twinkle-twinkle"}).json()["attempts"]
    assert [x["id"] for x in lst] == [a["id"]] and "rawEvents" not in lst[0]


def test_bad_attempts_are_rejected(client):
    assert client.post("/api/attempts", json=attempt(pieceId="../etc")).status_code == 422
    bad = attempt()
    bad["conditions"]["tempoPreset"] = "60"
    assert client.post("/api/attempts", json=bad).status_code == 422
    assert client.get("/api/attempts/nope").status_code == 404


def test_logs_are_stored_and_listed(client):
    r = client.post("/api/logs", json={"deviceId": str(uuid.uuid4()), "entries": [
        {"time": "2026-09-28T10:00:00Z", "level": "error", "message": "audio start failed", "context": {"state": "suspended"}},
        {"time": "2026-09-28T10:00:01Z", "level": "info", "message": "MIDI connected"}]})
    assert r.status_code == 201 and r.json()["stored"] == 2
    logs = client.get("/api/logs", params={"level": "error"}).json()["logs"]
    assert [x["message"] for x in logs] == ["audio start failed"]


def test_migrations_are_idempotent(tmp_path):
    path = str(tmp_path / "x.db")
    v = db.migrate(path)
    assert db.migrate(path) == v
    con = db.connect(path)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_index_page_lists_attempts_for_people(client):
    a = attempt()
    client.post("/api/attempts", json=a)
    r = client.get("/api/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Piano App API" in r.text and "twinkle-twinkle" in r.text and "★★★" in r.text and a["id"] in r.text
