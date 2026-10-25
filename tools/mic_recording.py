"""Fetch the microphone recordings sent from Config > Piano check (arch §4 "Microphone input",
v0.38), for tuning the note detector to a real keyboard and device.

    tools/.venv/bin/python tools/mic_recording.py              # list the recordings on the server
    tools/.venv/bin/python tools/mic_recording.py <id> [dir]   # write <dir>/<id>.wav, <id>.out.wav and <id>.json

Each recording is in the piano server's client log as 5-second parts of 16-bit audio; the first
part also has the keys the app heard (ms from the start), what the browser applied to the
microphone, and where it was made (the piano check, or a song on the Play screen). Recordings since
v0.43 also have what the app played meanwhile (<id>.out.wav), which the detector compares with
what it hears. The log keeps them 90 days. Written to tests-output/mic/ unless a folder is given.
tools/mic_replay.ts then replays one through the detector and scores it against the keys played.
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.request
import wave
from pathlib import Path

from server_config import server, ssl_context

OUT = Path(__file__).resolve().parent.parent / "tests-output" / "mic"


def recordings() -> dict[str, list[dict]]:
    with urllib.request.urlopen(server() + "/api/logs?limit=1000", context=ssl_context()) as r:
        logs = json.loads(r.read())["logs"]
    by_id: dict[str, list[dict]] = {}
    for entry in logs:
        if entry["message"] == "mic recording" and isinstance(entry.get("context"), dict):
            entry["context"]["time"] = entry["time"]
            by_id.setdefault(entry["context"]["id"], []).append(entry["context"])
    return by_id


def main() -> int:
    found = recordings()
    if len(sys.argv) < 2:
        for rid, parts in sorted(found.items(), key=lambda kv: min(p["time"] for p in kv[1])):
            first = next((p for p in parts if p["part"] == 0), {})
            on = [k for k in first.get("keys", []) if k["type"] == "on"]
            vp = first.get("settings", {}).get("voiceProcessing")
            print(f"{rid}  {min(p['time'] for p in parts)[:19]}  {len(parts)}/{parts[0]['parts']} parts  "
                  f"{len(on)} keys heard  voice processing {vp}")
        return 0
    rid = next((r for r in found if r.startswith(sys.argv[1])), None)
    if not rid:
        raise SystemExit(f"no recording {sys.argv[1]}")
    parts = sorted(found[rid], key=lambda p: p["part"])
    if len(parts) != parts[0]["parts"]:
        raise SystemExit(f"recording {rid} has {len(parts)} of {parts[0]['parts']} parts")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT
    out.mkdir(parents=True, exist_ok=True)
    for name, field in ((f"{rid}.wav", "pcm16"), (f"{rid}.out.wav", "out16")):
        if field not in parts[0]:
            continue
        with wave.open(str(out / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(parts[0]["rate"]))
            for p in parts:
                w.writeframes(base64.b64decode(p[field]))
    (out / f"{rid}.json").write_text(json.dumps({"rate": parts[0]["rate"], "time": parts[0]["time"], "keys": parts[0].get("keys", []),
                                                  "settings": parts[0].get("settings", {}), "context": parts[0].get("context")}, indent=1))
    print(f"wrote {out / rid}.wav" + (" and .out.wav" if "out16" in parts[0] else "") + " and .json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
