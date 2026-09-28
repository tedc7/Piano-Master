"""Pick the takes for the page: per song, every take x alignment mode is scored from its checks;
the best one-note-per-syllable take becomes the default, and the best earlier (as written) take is
kept for comparison.

    .venv/bin/python select_takes.py        -> build/final_takes.json, and a table on stdout

score = share of melody notes sung on the right pitch
        - share of words more than 0.3 s off the staff
        - 0.1 if the first word was not sung
        - 0.1 if a stretch of words is off the staff in the first 15 s (most noticeable there)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENDERS, BUILD = HERE / "renders", HERE / "build"
VARIANT = {"intro": "intro", "fake": "fake note", "syl": "one note per syllable", "mel": "one note per syllable, no chords"}


MODE_NAMES = {"melody": "words + melody", "words": "words", "dtw": "melody only"}


def describe(take, mode):
    m = re.fullmatch(r"(.+)-(intro|fake|syl|mel)(?:-(folk|spec))?(?:-s(\d+))?", take)
    seed = m.group(4) or "1"
    prompt = {"folk": ", backing prompt: folk trio", "spec": ", backing prompt: specific instruments"}.get(m.group(3), "")
    return f"{VARIANT[m.group(2)]}{prompt}, seed {seed}, aligned by {MODE_NAMES[mode]}"


def early_word_trouble(r):
    """A stretch of words off the staff within the song's first 15 s (the most noticeable place)."""
    for region in r["qa"]["word_regions"]:
        t = float(re.search(r"\(([\d.]+) s\)", region).group(1))
        if t < r["song_start_s"] + 15:
            return True
    return False


def score(r):
    q = r["qa"]
    return (r["pitch_100"]["pitch_ok"] - q["words"]["share_over_300ms"]
            - (0 if r["first_note_sung"] else 0.1) - (0.1 if early_word_trouble(r) else 0))


def main():
    songs = json.loads((HERE / "songs.json").read_text())["songs"]
    final = {}
    for song in songs:
        if not song.get("yue2"):
            continue
        cands = []
        for folder in sorted(RENDERS.glob(song["id"] + "-*")):
            for mode in ("melody", "words", "dtw"):
                f = folder / f"alignment-{mode}.json"
                if f.is_file() and re.fullmatch(re.escape(song["id"]) + r"-(intro|fake|syl|mel)(-s\d+)?", folder.name):
                    r = json.loads(f.read_text())
                    cands.append((score(r), folder.name, mode, r))
        cands.sort(key=lambda c: -c[0])
        print(f"\n{song['title']}")
        for sc, take, mode, r in cands:
            q = r["qa"]
            print(f"  {sc:+.2f}  {take:36s} {mode:6s}  notes on pitch {r['pitch_100']['pitch_ok']:.0%}  "
                  f"words off {q['words']['share_over_300ms']:.0%}  first word {'yes' if r['first_note_sung'] else 'NO'}"
                  f"{'  words off in first 15 s' if early_word_trouble(r) else ''}")
        # the page: the best one-note-per-syllable take (the input rule that won, compare_styles.py),
        # and the best take as written (the earlier inputs) to compare against. The chord-free "mel"
        # takes are left out: their backing matches the written chords less often (harmony.py).
        style = lambda c: re.fullmatch(r".+-(intro|fake|syl|mel)(?:-s\d+)?", c[1]).group(1)
        best = next((c for c in cands if style(c) == "syl"), cands[0])
        other = next(c for c in cands if style(c) in ("intro", "fake"))
        final[song["id"]] = [{"take": c[1], "mode": c[2], "score": round(c[0], 3), "default": i == 0,
                              "label": ("Best: " if i == 0 else "Compare (earlier input): ") + describe(c[1], c[2])}
                             for i, c in enumerate([best, other])]
        # backing prompt test: the default take's score and seed with another style (only the backing
        # prompt differs), aligned the same way, for listening
        seed = re.search(r"-s\d+$", best[1])
        for prompt in ("spec", "folk"):
            take = f"{song['id']}-syl-{prompt}{seed.group(0) if seed else '-s1'}"
            f = RENDERS / take / f"alignment-{best[2]}.json"
            if f.is_file():
                final[song["id"]].append({"take": take, "mode": best[2], "score": round(score(json.loads(f.read_text())), 3),
                                          "default": False, "label": "Backing test: " + describe(take, best[2])})
    (BUILD / "final_takes.json").write_text(json.dumps(final, indent=1) + "\n")


if __name__ == "__main__":
    main()
