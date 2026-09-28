"""Planning test (open question in "YuE2 Lyrics & Melody Input - Agent Instructions"): let YuE2 write
its own melody for our hymn lyrics (no ABC supplied) and count its Vocal attacks per sung syllable,
to see whether one attack per syllable matches its habits. Plans only, no audio.

    HF_HOME=~/engines/yue2/hf-home HF_HUB_OFFLINE=1 ~/engines/yue2/.venv/bin/python plan_test.py
        -> build/plan_test/<song>-<cot>.abc and build/plan_test/summary.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
ENGINE = Path.home() / "engines" / "yue2"
sys.path.insert(0, str(ENGINE / "YuE" / "skills" / "yue2-music" / "scripts"))
import abc_tools  # noqa: E402

SONGS = ["amazing-grace", "what-child-is-this", "it-came-upon-a-midnight-clear", "jeanie"]
RUNS = [("melody", 831001), ("full", 831001)]


def main():
    from yue2 import YuE2Pipeline
    engine = json.loads((ENGINE / "engine.json").read_text())
    installed = json.loads((ENGINE / "INSTALLED.json").read_text())
    outdir = BUILD / "plan_test"
    outdir.mkdir(exist_ok=True)
    summary = {}
    with YuE2Pipeline.from_pretrained(installed["model"]["path"], vae=installed["vae"]["path"], device="cuda",
                                      local_files_only=True, memory_budget_gib=engine["memory_budget_gib"]) as pipe:
        for sid in SONGS:
            ydir = BUILD / sid / "yue2"
            lyrics = (ydir / "lyrics-intro.txt").read_text()          # no fake "Oh"
            style = json.loads((HERE / "renders" / f"{sid}-syl" / "report.json").read_text())["style"]
            syl = json.loads((ydir / "abcmap-syl.json").read_text())["syllable_count"]
            for cot, seed in RUNS:
                plan = pipe.plan(style=style, lyrics=lyrics, cot=cot, seed=seed, id=f"{sid}-{cot}")
                abc = plan.abc
                (outdir / f"{sid}-{cot}.abc").write_text(abc)
                try:
                    score = abc_tools.parse_abc(abc.rstrip("\n"))
                    attacks = len(score.voices["Vocal"].notes)
                    bpm = score.bpm
                except Exception as e:   # a plan outside the checker's dialect
                    attacks, bpm = len(re.findall(r"(?<![-a-zA-Z\"])[A-Ga-g][,']*\d*", abc)), None
                    print(f"{sid} {cot}: parse failed ({e}); rough count")
                summary[f"{sid}-{cot}"] = {"syllables": syl, "vocal_attacks": attacks,
                                           "attacks_per_syllable": round(attacks / syl, 3), "planned_bpm": bpm,
                                           "sections": [l[1:].strip() for l in abc.splitlines() if l.startswith("%")]}
                print(sid, cot, summary[f"{sid}-{cot}"]["syllables"], "syllables,", attacks, "attacks", flush=True)
    (outdir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")


if __name__ == "__main__":
    main()
