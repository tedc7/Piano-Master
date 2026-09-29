"""Shared fixtures: an API client on a throwaway database, with a small branching skill map."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app import main

# the placeholder map's shape: a -> b, a -> c, (a, c) -> d, b -> e (rhythm)
SKILLS = [
    {"id": "t.a", "name": "Skill A", "sequence": 10, "track": "reading", "prerequisites": [], "pieces": ["pa1", "pa2"]},
    {"id": "t.b", "name": "Skill B", "sequence": 20, "track": "technique", "prerequisites": ["t.a"], "pieces": ["pb1"]},
    {"id": "t.c", "name": "Skill C", "sequence": 30, "track": "reading", "prerequisites": ["t.a"], "pieces": ["pc1"]},
    {"id": "t.d", "name": "Skill D", "sequence": 40, "track": "reading", "prerequisites": ["t.a", "t.c"], "pieces": ["pd1"]},
    {"id": "t.e", "name": "Skill E", "sequence": 50, "track": "rhythm", "prerequisites": ["t.b"], "pieces": ["pe1"]},
]


def piece(pid, skill, title=None):
    return {"id": pid, "title": title or pid, "kind": "core", "hands": "R", "skillId": skill, "tempo": 100, "timeSig": "4/4",
            "measures": 8, "beats": 32, "phrases": 4, "requiredSkills": [skill] if skill else [],
            "featuredSkills": [skill] if skill else [], "hasMedia": False}


PIECES = [piece("pa1", "t.a"), piece("pa2", "t.a"), piece("pb1", "t.b"), piece("pc1", "t.c"), piece("pd1", "t.d"),
          piece("pe1", "t.e"), piece("free1", None, "A free song")]


def write_content(d, skills=SKILLS, pieces=PIECES, version="test1"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "skillmap.json").write_text(json.dumps({"contentVersion": version, "skills": skills}))
    (d / "index.json").write_text(json.dumps({"contentVersion": version, "pieces": pieces}))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PIANO_DB", str(tmp_path / "piano.db"))
    write_content(tmp_path / "content")
    monkeypatch.setenv("PIANO_CONTENT", str(tmp_path / "content"))
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def parent(client):
    """Headers for a logged-in parent (PIN 2468)."""
    r = client.post("/api/parent/pin", json={"pin": "2468"})
    assert r.status_code == 200
    return {"X-Parent-Token": r.json()["token"]}


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
