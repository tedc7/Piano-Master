"""Compare the YuE2 input styles on the same songs and seeds (the fake-note lead-in in all three):

    as written  every melody note from the hymnal, chords, cot full (the fake / fake-s2 / fake-s3 takes)
    syl         one Vocal attack per syllable (melismas merged), L:1/32, chords, cot full
    mel         the same without chords, cot melody

    .venv/bin/python compare_styles.py        -> build/compare_styles.json, tables on stdout

Per take, each alignment mode's checks are scored as in select_takes.py and the best mode is kept
(that is what the page would use). The harmony check (harmony.py) is reported separately.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from select_takes import early_word_trouble, score

HERE = Path(__file__).resolve().parent
RENDERS, BUILD = HERE / "renders", HERE / "build"
STYLES = {"as written": "fake", "syl": "syl", "mel": "mel"}
SEEDS = ("", "-s2", "-s3")


def main():
    songs = [s for s in json.loads((HERE / "songs.json").read_text())["songs"] if s.get("yue2")]
    harm = json.loads((BUILD / "harmony.json").read_text())
    rows, summary = [], {}
    for song in songs:
        for style, variant in STYLES.items():
            for seed in SEEDS:
                take = f"{song['id']}-{variant}{seed}"
                cands = []
                for mode in ("melody", "words", "dtw"):
                    f = RENDERS / take / f"alignment-{mode}.json"
                    if f.is_file():
                        r = json.loads(f.read_text())
                        cands.append((score(r), mode, r))
                if not cands:
                    continue
                sc, mode, r = max(cands, key=lambda c: c[0])
                h = harm.get(f"{take}/{mode}", {})
                hd = harm.get(f"{take}/dtw", {})
                rows.append({"song": song["id"], "style": style, "take": take, "best_mode": mode, "score": round(sc, 3),
                             "pitch_ok": r["pitch_100"]["pitch_ok"], "words_off": r["qa"]["words"]["share_over_300ms"],
                             "first_word": r["first_note_sung"], "early_trouble": early_word_trouble(r),
                             "audio_vs_score": round(r["audio_seconds"] / r["score_seconds"], 3),
                             "harmony_share": h.get("chord_tone_share"), "harmony_match": h.get("match"),
                             "harmony_match_dtw": hd.get("match")})
    print(f"{'take':44s} {'mode':6s} score  pitch  words-off  1st  harm")
    for x in rows:
        print(f"{x['take']:44s} {x['best_mode']:6s} {x['score']:+.2f}  {x['pitch_ok']:.0%}   {x['words_off']:5.0%}    "
              f"{'yes' if x['first_word'] else 'NO '}  {x['harmony_match'] if x['harmony_match'] is None else format(x['harmony_match'], '.0%')}")
    print("\nMeans over the seeds (score / notes on pitch / words >0.3 s off / written chord best):")
    print(f"{'song':32s} " + "  ".join(f"{s:>26s}" for s in STYLES))
    for song in songs:
        cells = []
        for style in STYLES:
            xs = [x for x in rows if x["song"] == song["id"] and x["style"] == style]
            if not xs:
                cells.append(f"{'-':>26s}")
                continue
            m = {k: float(np.mean([x[k] for x in xs if x[k] is not None])) for k in ("score", "pitch_ok", "words_off", "harmony_match")}
            summary.setdefault(song["id"], {})[style] = {**{k: round(v, 3) for k, v in m.items()}, "takes": len(xs),
                                                          "best": max(x["score"] for x in xs)}
            cells.append(f"{m['score']:+.2f} / {m['pitch_ok']:.0%} / {m['words_off']:.0%} / {m['harmony_match']:.0%}".rjust(26))
        print(f"{song['id']:32s} " + "  ".join(cells))
    print("\nAll songs:")
    for style in STYLES:
        xs = [x for x in rows if x["style"] == style]
        if xs:
            print(f"  {style:10s} {len(xs):2d} takes  score {np.mean([x['score'] for x in xs]):+.2f}  "
                  f"notes on pitch {np.mean([x['pitch_ok'] for x in xs]):.0%}  words off {np.mean([x['words_off'] for x in xs]):.0%}  "
                  f"written chord best {np.mean([x['harmony_match'] for x in xs]):.0%}  "
                  f"best take per song {np.mean([max(y['score'] for y in xs if y['song'] == s['id']) for s in songs]):+.2f}  "
                  f"first word sung {sum(x['first_word'] for x in xs)}/{len(xs)}")
    (BUILD / "compare_styles.json").write_text(json.dumps({"takes": rows, "means": summary}, indent=1) + "\n")


if __name__ == "__main__":
    main()
