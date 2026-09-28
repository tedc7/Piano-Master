"""Turn a stored attempt into a performance fixture (arch §7.10, §11.4).

    tools/.venv/bin/python tools/fixture_from_attempt.py                 # list recent attempts
    tools/.venv/bin/python tools/fixture_from_attempt.py <id> <name>     # write client/tests/fixtures/<name>.json

The fixture keeps the key presses of every pass and, as its expected result, what the app scored
at the time. Review the expected stars before committing: a fixture records what *should* happen,
so change them if the parent judged the playing differently (that is the tuning, §7.10).
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://192.168.2.128/api"
CA = Path.home() / "repos" / "Server" / "caddy-root-ca.crt"
OUT = ROOT / "client" / "tests" / "fixtures"


def get(path: str):
    ctx = ssl.create_default_context(cafile=str(CA)) if CA.exists() else ssl._create_unverified_context()
    with urllib.request.urlopen(API + path, context=ctx, timeout=10) as r:
        return json.load(r)


def passes_of(a) -> list[list[dict]]:
    """Key presses per pass, as {beat, pitch, velocity, durMs}; presses outside the clock are dropped."""
    n = len(a["passes"])
    out: list[list[dict]] = [[] for _ in range(n)]
    held: dict[int, dict] = {}
    for e in a["rawEvents"]:
        if e["type"] == "on" and e.get("beat") is not None and 0 <= e["pass"] < n:
            note = {"beat": round(e["beat"], 4), "pitch": e["pitch"], "velocity": e["velocity"], "durMs": 200, "_t": e["t"]}
            out[e["pass"]].append(note)
            held[e["pitch"]] = note
        elif e["type"] == "off" and e.get("pitch") in held:
            note = held.pop(e["pitch"])
            note["durMs"] = round(e["t"] - note["_t"], 1)
    for p in out:
        for note in p:
            note.pop("_t", None)
    return out


def main(argv):
    if len(argv) < 3:
        for a in get("/attempts?limit=30")["attempts"]:
            print(f"{a['id']}  {a['startedAt'][:19]}  {a['pieceId']:<24} {a['mode']:<4} {a['tempoPreset']:>3}%  "
                  f"notes {a['accuracyStars']}  timing {a['timingStars']}  {'done' if a['completed'] else 'stopped'}")
        return 0
    a = get(f"/attempts/{argv[1]}")
    c, e = a["conditions"], a["evaluation"]
    fixture = {
        "description": f"Recorded {a['startedAt'][:10]} ({a['pieceId']}, {c['tempoPreset']}%). Describe what was played.",
        "piece": a["pieceId"],
        "preset": c["tempoPreset"],
        "hands": c["hands"],
        "latencyOffsetMs": a["latencyOffsetMs"],
        "events": passes_of(a),
        "expect": {
            "rewinds": [{} for _ in range(c["rewinds"])],   # compared on their count only
            "completed": a["completed"],
            "matched": e["matched"],
            "extra": e.get("extra"),
            "accuracyStars": e["accuracyStars"],
            "timingStars": e["timingStars"],
        },
    }
    if a.get("section"):
        print("note: a loop attempt; add \"section\": {\"phrases\": [first, last]} by hand", file=sys.stderr)
    path = OUT / f"{argv[2]}.json"
    path.write_text(json.dumps(fixture, indent=1) + "\n")
    print(f"wrote {path.relative_to(ROOT)}: {sum(len(p) for p in fixture['events'])} key presses in {len(fixture['events'])} pass(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
