"""Basic YuE2 feasibility tests (M0-S, basic). Run with the engine venv:

    ~/engines/yue2/.venv/bin/python run_tests.py            # all tests
    ~/engines/yue2/.venv/bin/python run_tests.py --only 5   # just the input-contract test

generate_music.py itself is run with the system python3 (it must need only the stdlib).
Renders go to results/<id>/; a summary goes to results/summary.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import soundfile as sf

HERE = Path(__file__).resolve().parent
REQ = HERE / "requests"
RESULTS = HERE / "results"
ENGINE = Path.home() / "engines" / "yue2"
GENERATE = Path.home() / ".claude" / "skills" / "generate-music" / "scripts" / "generate_music.py"
FALLBACKS = [{"offload_ar": True}, {"offload_ar": True, "quantization": "fp8"}]

summary = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "tests": {}}


def log(msg):
    print(msg, flush=True)


def generate(request, out=RESULTS, extra=()):
    """Run the front end; return (exit code, last-line JSON)."""
    cmd = ["python3", str(GENERATE), "--request", str(REQ / request), "--out", str(out), *extra]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    return proc.returncode, (json.loads(lines[-1]) if lines else {})


def render_with_fallback(request):
    """Render; on out-of-memory, step through FALLBACKS in engine.json (recorded)."""
    engine_file = ENGINE / "engine.json"
    attempts = []
    for step in [None, *FALLBACKS]:
        if step:
            settings = {**json.loads(engine_file.read_text()), **step}
            engine_file.write_text(json.dumps(settings, indent=2) + "\n")
            log(f"  out of memory -> engine.json now {step}")
        rid = json.loads((REQ / request).read_text())["id"]
        out_dir = RESULTS / rid
        if out_dir.exists():  # a failed attempt leaves files; keep them under a numbered name
            out_dir.rename(RESULTS / f"{rid}.failed-{len(attempts)}")
        code, result = generate(request)
        attempts.append({"settings_change": step, "exit": code, "status": result.get("status"),
                         "out_of_memory": result.get("out_of_memory", False)})
        if not (code == 3 and result.get("out_of_memory")):
            return code, result, attempts
    return code, result, attempts


def audio_info(folder, name):
    path = folder / f"{name}.flac"
    if not path.is_file():
        return None
    info = sf.info(path)
    return {"seconds": round(info.frames / info.samplerate, 2), "frames": info.frames}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def record(num, name, passed, **details):
    summary["tests"][num] = {"name": name, "pass": passed, **details}
    log(f"TEST {num} {name}: {'PASS' if passed else 'FAIL'}  {json.dumps(details)[:600]}")


def test1():
    doctor = json.loads((ENGINE / "doctor.json").read_text())
    import torch
    arch = torch.cuda.get_arch_list()
    cap = "sm_%d%d" % torch.cuda.get_device_capability(0)
    ok = doctor["dependencies_ready"] and cap in arch and torch.cuda.is_bf16_supported() and bool(doctor.get("weights"))
    record(1, "environment", ok, gpu=torch.cuda.get_device_name(0), capability=cap, torch=torch.__version__,
           cuda=torch.version.cuda, weights_verified=bool(doctor.get("weights")))


def render_test(num, name, request, expect_stems):
    code, rep, attempts = render_with_fallback(request)
    folder = Path(rep.get("output", RESULTS / json.loads((REQ / request).read_text())["id"]))
    details = {"exit": code, "attempts": attempts, "engine_settings": json.loads((ENGINE / "engine.json").read_text())}
    ok = code == 0 and rep.get("status") == "complete"
    if rep.get("status") == "complete":
        details.update(audio_seconds=rep["audio_seconds"], timing=rep["timing_seconds"],
                       peak_vram_gib=rep["peak_vram_gib"], truncated=rep["truncated"], levels=rep["levels"],
                       request_id=rep["request_id"], cot=rep["cot"])
        ok = ok and rep["audio_seconds"] > 10 and rep["levels"]["mix"]["rms_dbfs"] > -40
        if expect_stems:
            mix = audio_info(folder, "mix")
            stems = {n: audio_info(folder, n) for n in ("vocals", "accompaniment")}
            same_len = all(s and s["frames"] == mix["frames"] for s in stems.values())
            audible = all(rep["levels"][n]["rms_dbfs"] > -45 for n in stems)
            details.update(stems_same_length=same_len, stems_audible=audible)
            ok = ok and same_len and audible
    else:
        details["failure"] = {k: rep.get(k) for k in ("stage", "type", "reason", "error")}
    record(num, name, ok, output=str(folder), **details)
    return rep


def test5():
    checks = {}
    for req in ("bad-tempo.json", "bad-abc.json"):
        code, rep = generate(req, out=RESULTS / "contract")
        checks[req] = {"exit": code, "error": rep.get("error")}
    code, rep = generate("autumn-road.json")  # results/autumn-road already exists from test 2
    checks["rerun-into-existing-folder"] = {"exit": code, "error": rep.get("error")}
    a, b = (RESULTS / "autumn-road" / "report.json"), (RESULTS / "autumn-road-stems" / "report.json")
    if a.is_file() and b.is_file():
        ra, rb = json.loads(a.read_text()), json.loads(b.read_text())
        # request_id hashes the whole request including its id, so it differs between these two
        # (ids differ); reproducibility is judged on the audio itself.
        checks["request_ids"] = [ra["request_id"][:12], rb["request_id"][:12]]
        checks["same-seed-identical-audio"] = sha(RESULTS / "autumn-road/yue2/audio.flac") == sha(RESULTS / "autumn-road-stems/yue2/audio.flac")
    ok = all(v["exit"] == 2 for k, v in checks.items() if isinstance(v, dict)) and checks.get("same-seed-identical-audio", False)
    record(5, "input contract", ok, **checks)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--only", type=int, action="append")
    args = p.parse_args()
    RESULTS.mkdir(exist_ok=True)
    tests = {1: test1,
             2: lambda: render_test(2, "generic text-to-song", "autumn-road.json", False),
             3: lambda: render_test(3, "generic with stems (same request+seed)", "autumn-road-stems.json", True),
             4: lambda: render_test(4, "piano-master profile, supplied melody", "garden-morning.json", True),
             5: test5}
    for num, fn in tests.items():
        if not args.only or num in args.only:
            fn()
    summary["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    target = RESULTS / "summary.json"
    old = json.loads(target.read_text()) if target.is_file() else {"tests": {}}
    old["tests"].update({str(k): v for k, v in summary["tests"].items()})
    old.update({k: v for k, v in summary.items() if k != "tests"})
    target.write_text(json.dumps(old, indent=2) + "\n")
    failed = [n for n, t in summary["tests"].items() if not t["pass"]]
    log(f"\n{len(summary['tests']) - len(failed)}/{len(summary['tests'])} passed" + (f"; failed: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
