"""YuE2 inputs from a piece's notation, and the renders (arch §10.5 steps 1-2).

The melody goes to YuE2 in its native two-voice ABC (generate-music skill, piano-master profile):
  - unrolled in playback order (every verse), the pickup padded with rests;
  - one Vocal note per sung syllable (a melisma merged onto its first pitch), with the syllables
    sidecar the skill checks;
  - the chord symbols kept on the Vocal voice, so YuE2 sings in the written harmony;
  - a throwaway lead-in bar with one sung "Oh" on another pitch, muted after alignment: without it
    YuE2 starts early and sometimes drops the first word;
  - each phrase moved by whole octaves into a singing range, and the key taken from the notes when
    the signature doesn't name it (the curriculum's black-key songs, written in C with sharps).
The stems' time 0 is ABC beat 0, which is `pad_beats` before playback beat 0 (the app's padBeats).
Prototype: feasibility/sync-probe/convert.py (yue2_export), proven on five songs.
"""
from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from music21 import key as m21key, pitch as m21pitch

from common import GENERATE, YUE2_SCRIPTS, Piece, nt

sys.path.insert(0, str(YUE2_SCRIPTS))
import abc_tools  # noqa: E402  (YuE2's own ABC parser: the attack-count check)

DURATIONS = (48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1)       # YuE2 native ABC length multipliers
ACC = {-2: "__", -1: "_", 0: "=", 1: "^", 2: "^^"}
SHARPS_ORDER, FLATS_ORDER = "FCGDAEB", "BEADGCF"
MAJOR_KEYS = ["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"]
MINOR_KEYS = ["Abm", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "A#m"]
KEYS_FIFTHS = {**{k: i - 7 for i, k in enumerate(MAJOR_KEYS)}, **{k: i - 7 for i, k in enumerate(MINOR_KEYS)}}
SEEDS = tuple(831001 + i for i in range(24))

HOLD = "\u2011"            # a syllable YuE2 would skip inside a word: a hyphen in YuE2's lyrics, none for the aligner


def vowel_run(before: str, syllable: str) -> bool:
    """A syllable that only carries on the vowel the word has reached ("Glo" then "o")."""
    s = syllable.lower().strip(",.;:!?")
    return bool(s) and all(c in "aeiou" for c in s) and before.lower().endswith(s[0])


def sung_ed(before: str, syllable: str) -> bool:
    """An old sung "-ed" on its own note ("look-ed", "bless-ed"), which the joined word would say
    in one syllable ("looked"); after a t or d it's a syllable anyway ("want-ed")."""
    s = syllable.lower().strip(",.;:!?").replace("è", "e").replace("é", "e")
    return s == "ed" and not before.lower().rstrip(HOLD).endswith(("t", "d"))


def tonal_key(nota: dict) -> str:
    """YuE2's K: value: the key the song is in, which can differ from the written signature. Songs
    end on the tonic: the last chord symbol's root, else the lowest note at the last onset."""
    fifths = nota["header"]["keySig"]
    major, minor = MAJOR_KEYS[fifths + 7], MINOR_KEYS[fifths + 7]
    if nota.get("chordSymbols"):
        last = max(nota["chordSymbols"], key=lambda c: c["beat"])["symbol"]
        tonic = m21pitch.Pitch(last[0] + ("#" if last[1:2] == "#" else "-" if last[1:2] == "b" else "")).pitchClass
    else:
        end = max(n["start"] for n in nota["notes"])
        tonic = min(n["pitch"] for n in nota["notes"] if n["start"] == end) % 12
    if tonic in (pc(major), pc(minor[:-1])):
        return minor if tonic == pc(minor[:-1]) and tonic != pc(major) else major
    # the signature names neither (a song on the black keys written in C with sharps): the key on
    # that tonic that holds the most of its notes, major first, sharps for a song spelled in sharps
    # (flats for flats), then the fewest sharps or flats
    held = [n["pitch"] % 12 for n in nota["notes"]]
    sharps = sum(n["spelled"]["alter"] for n in nota["notes"]) >= 0

    def fit(name: str) -> tuple:
        k = m21key.Key(name[:-1].replace("b", "-") if name.endswith("m") else name.replace("b", "-"),
                       "minor" if name.endswith("m") else "major")
        scale = {q.pitchClass for q in k.getPitches()}
        return (-sum(x in scale for x in held), name.endswith("m"), (KEYS_FIFTHS[name] > 0) != sharps, abs(KEYS_FIFTHS[name]))
    names = [k for k in MAJOR_KEYS if pc(k) == tonic] + [k for k in MINOR_KEYS if pc(k[:-1]) == tonic]
    return min(names, key=fit)


def pc(name: str) -> int:
    """a key name's tonic pitch class ("Eb" -> 3)"""
    return m21pitch.Pitch(name.replace("b", "-") if len(name) > 1 else name).pitchClass


SING_LOW, SING_HIGH = 57, 77      # A3..F5: where the vocal is asked to sing


def singable(mel: list[dict], phrases: list) -> list[dict]:
    """Move each hand's passage (its notes until the other hand takes over) by whole octaves so most
    of them lie in SING_LOW..SING_HIGH, the smallest move first: a left hand written two octaves down
    is sung where a voice can sing it. A whole passage moves together, so a leap the song makes
    within it stays a leap ("down an octave" in Pattern Up, Pattern Down had been moved apart, phrase
    by phrase, onto one pitch); only a passage wider than the range is moved phrase by phrase. One
    hand's passage never moves with the other's (Sleepy Owl's "whoo" had gone to C#5 with the left
    hand's bar). The checks compare pitch classes, so the vocal still matches the staff. Returns the
    changes."""
    starts = sorted({Fraction(p) for p in phrases} | {Fraction(0)})
    phrase_of = lambda n: sum(1 for x in starts if x <= n["start"])
    passages: list[list[dict]] = []
    for n in mel:
        if not passages or (n.get("hand") or n.get("staff")) != (passages[-1][0].get("hand") or passages[-1][0].get("staff")):
            passages.append([])
        passages[-1].append(n)
    groups: list[list[dict]] = []
    for ns in passages:
        if max(n["pitch"] for n in ns) - min(n["pitch"] for n in ns) <= SING_HIGH - SING_LOW:
            groups.append(ns)
            continue
        for n in ns:                         # too wide to sing as one: phrase by phrase
            if not groups or groups[-1][0] not in ns or phrase_of(groups[-1][0]) != phrase_of(n):
                groups.append([])
            groups[-1].append(n)
    changes = []
    for ns in groups:
        k = min(range(-3, 4), key=lambda k: (sum(not SING_LOW <= n["pitch"] + 12 * k <= SING_HIGH for n in ns), abs(k)))
        if not k:
            continue
        for n in ns:
            n["pitch"] += 12 * k
            n["spelled"] = {**n["spelled"], "octave": n["spelled"]["octave"] + k}
            if n.get("merged"):
                n["merged"] = [m + 12 * k for m in n["merged"]]
        changes.append({"change": f"sung {abs(k)} octave{'s' if abs(k) > 1 else ''} {'higher' if k > 0 else 'lower'}",
                        "songBeat": str(ns[0]["start"]), "notes": len(ns)})
    return changes


def to_pitch(sp):
    p = m21pitch.Pitch(sp["step"] + str(sp["octave"]))
    if sp["alter"]:
        p.accidental = sp["alter"]
    return p


def spelled(p):
    return {"step": p.step, "alter": int(p.accidental.alter) if p.accidental else 0, "octave": p.octave}


def key_accidentals(fifths):
    acc = {letter: 0 for letter in "CDEFGAB"}
    for letter in (SHARPS_ORDER if fifths > 0 else FLATS_ORDER)[:abs(fifths)]:
        acc[letter] = 1 if fifths > 0 else -1
    return acc


def abc_pitch(sp, state):
    letter, alter, octave = sp["step"], sp["alter"], sp["octave"]
    token = ""
    if state.get(letter) != alter:
        token += ACC[alter]
        state[letter] = alter
    return token + (letter.lower() + "'" * (octave - 5) if octave >= 5 else letter + "," * (4 - octave))


def split_units(units):
    out = []
    while units:
        d = next(d for d in DURATIONS if d <= units)
        out.append(d)
        units -= d
    return out


def merged_melody(unrolled):
    """Melody notes in playback order, ties merged."""
    mel = sorted((n for n in unrolled["notes"] if n.get("isMelody")), key=lambda n: n["start"])
    out = []
    for n in mel:
        prev = out[-1] if out else None
        if prev and prev.get("tieToNext") and prev["pitch"] == n["pitch"] and prev["start"] + prev["duration"] == n["start"]:
            prev["duration"] += n["duration"]
            prev["tieToNext"] = n.get("tieToNext", False)
            continue
        out.append(dict(n))
    return out


def syllabic_melody(mel):
    """One Vocal attack per sung syllable: a note without a syllable of its own in its pass (a
    melisma, or a note only another verse sings) joins the note before it, held on that note's
    pitch; after a gap it becomes a rest. Returns the notes and a record of each change."""
    out, changes = [], []
    for n in mel:
        if n.get("lyric") is not None:
            out.append(dict(n))
            continue
        prev = out[-1] if out else None
        if prev and prev["verse"] == n["verse"] and prev["start"] + prev["duration"] == n["start"]:
            changes.append({"change": "merged into the syllable before" if prev["pitch"] != n["pitch"] else "tied",
                            "syllable": prev["lyric"]["text"], "songBeat": str(n["start"]), "pitch": n["pitch"]})
            prev["duration"] += n["duration"]
            prev.setdefault("merged", []).append(n["pitch"])
        else:
            changes.append({"change": "dropped (rest)", "songBeat": str(n["start"]), "pitch": n["pitch"]})
    return out, changes


def felt(nota: dict) -> tuple[dict, Fraction]:
    """The notation on the beat it is felt in, for YuE2, whose tempo is always in quarter notes: a
    song in cut time (2/2 at half = 100) goes as 2/4 at quarter = 100, every length halved, so its
    style says "100 BPM" like the songs YuE2 learned from, not 200. Returns (notation, scale): ABC
    beats = song beats x scale. Other meters are unchanged (scale 1)."""
    num, den = (int(x) for x in nota["header"]["timeSig"].split("/"))
    if den != 2:
        return nota, Fraction(1)
    k = Fraction(1, 2)
    out = copy.deepcopy(nota)
    h = out["header"]
    h.update(timeSig=f"{num}/4", barLength=Fraction(h["barLength"]) * k, pickupBeats=Fraction(h["pickupBeats"]) * k,
             tempo=int(round(h["tempo"] * k)))
    for m in out["measures"]:
        m["start"], m["duration"] = Fraction(m["start"]) * k, Fraction(m["duration"]) * k
        if m.get("timeSig"):
            n2, d2 = m["timeSig"].split("/")
            m["timeSig"] = f"{n2}/{int(d2) * 2}"
    for n in out["notes"]:
        n["start"], n["duration"] = Fraction(n["start"]) * k, Fraction(n["duration"]) * k
    for c in out["chordSymbols"]:
        c["beat"] = Fraction(c["beat"]) * k
    out["phrases"] = [Fraction(x) * k for x in out["phrases"]]
    out["length"] = Fraction(out["length"]) * k
    return out, k


def export(nota: dict, denom: int = 32, octave: int = 0) -> tuple[str, str, dict]:
    """(native ABC, lyrics, abcmap) for YuE2: one attack per syllable, chords, the "Oh" lead-in.
    abcmap's beats are ABC beats; `songPadBeats` is the lead-in in the song's own beats."""
    nota, scale = felt(nota)
    h = nota["header"]
    bar_len, pickup = Fraction(h["barLength"]), Fraction(h["pickupBeats"])
    pad = (bar_len - pickup) % bar_len
    unrolled = nt.unroll(nota)
    mel, changes = syllabic_melody(merged_melody(unrolled))
    if not mel:
        raise ValueError("no sung syllables: the vocal needs lyrics under the melody")
    changes += singable(mel, nota["phrases"])
    if octave:      # the piece's `media: {vocal_octave: N}`: the whole vocal N octaves away, leaps kept
        for n in mel:
            n["pitch"] += 12 * octave
            n["spelled"] = {**n["spelled"], "octave": n["spelled"]["octave"] + octave}
            if n.get("merged"):
                n["merged"] = [m + 12 * octave for m in n["merged"]]
        changes.append({"change": f"the whole vocal {abs(octave)} octave{'s' if abs(octave) > 1 else ''} "
                                  f"{'higher' if octave > 0 else 'lower'} (vocal_octave)", "songBeat": "0", "notes": len(mel)})
    for n in mel:
        n["abc_start"] = n["start"] + pad
    total = Fraction(math.ceil((unrolled["length"] + pad) / bar_len)) * bar_len

    # chord symbols on the ABC timeline, once per pass through their measure
    chords = []
    for e in unrolled["entries"]:
        m = nota["measures"][e["measure"]]
        for c in nota["chordSymbols"]:
            if m["start"] <= c["beat"] < m["start"] + m["duration"]:
                chords.append((e["start"] + c["beat"] - m["start"] + pad, c["symbol"]))
    chords.sort()
    chords = [c for i, c in enumerate(chords) if i == 0 or c[1] != chords[i - 1][1]]
    unit = Fraction(4, denom)
    k_name = tonal_key(nota)
    fifths = KEYS_FIFTHS[k_name]
    bars, chord_at = [], dict(chords)
    for b in range(int(total / bar_len)):
        b0, b1 = b * bar_len, (b + 1) * bar_len
        cuts = sorted({b0, b1} | {c for c in chord_at if b0 < c < b1} |
                      {n["abc_start"] for n in mel if b0 < n["abc_start"] < b1} |
                      {n["abc_start"] + n["duration"] for n in mel if b0 < n["abc_start"] + n["duration"] < b1})
        state = key_accidentals(fifths)
        tokens, sounding = [], False
        for s, e in zip(cuts, cuts[1:]):
            n = next((n for n in mel if n["abc_start"] <= s < n["abc_start"] + n["duration"]), None)
            prefix = f'"{chord_at[s]}"' if s in chord_at else ""
            units = split_units(int((e - s) / unit))
            if n is None:
                tokens.append(prefix + "".join(f"z{u if u > 1 else ''}" for u in units))
                continue
            pieces = [abc_pitch(n["spelled"], state) + (str(u) if u > 1 else "") for u in units]
            tokens.append(prefix + "-".join(pieces) + ("-" if e < n["abc_start"] + n["duration"] else ""))
            sounding = True
        body = "".join(tokens)
        if not sounding and not any(b0 <= c < b1 for c in chord_at):
            body = "Z"
        bars.append(body)

    song_pad = pad

    def verse_at(t):
        song_t = t - song_pad
        for e in reversed(unrolled["entries"]):
            if e["start"] <= max(song_t, Fraction(0)):
                return e["verse"]
        return 1
    labels = [verse_at(b * bar_len) for b in range(len(bars))]

    # the lead-in bar: a held "Oh" on the tonic (or its fifth when the song starts on the tonic),
    # below the first note, so the aligner can't take it for the first word
    state = key_accidentals(fifths)
    num, den = (int(x) for x in h["timeSig"].split("/"))
    held = Fraction(3, 2) if den == 8 and num % 3 == 0 else Fraction(2)
    kk = m21key.Key(k_name[:-1] if k_name.endswith("m") else k_name, "minor" if k_name.endswith("m") else "major")
    first = to_pitch(mel[0]["spelled"])
    oh = copy.deepcopy(kk.tonic if kk.tonic.pitchClass != first.pitchClass else kk.getDominant())
    oh.octave = first.octave
    while oh.midi >= first.midi:
        oh.octave -= 1
    if first.midi - oh.midi > 9:
        oh.octave += 1
    units = int(held / unit)
    body = f'"{k_name}"' + abc_pitch(spelled(oh), state) + (str(units) if units > 1 else "") + "".join(
        f"z{u if u > 1 else ''}" for u in split_units(int((bar_len - held) / unit)))
    bars, labels = [body] + bars, [labels[0]] + labels
    pad += bar_len

    lines = ["X:1", "T:", f"M:{h['timeSig']}", f"L:1/{denom}", f"Q:1/4={h['tempo']}",
             'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"',
             'V: Ins clef=treble name="Ins Melody" snm="Inst."', f"K:{k_name}"]
    i = 0
    while i < len(bars):
        j = i
        while j < len(bars) and j - i < 4 and labels[j] == labels[i]:
            j += 1
        if i == 0 or labels[i] != labels[i - 1]:
            lines.append("% verse")
        lines += ["V: Vocal", "|".join(bars[i:j]) + "|", "V: Ins", f"Z{j - i if j - i > 1 else ''}|"]
        i = j
    abc = "\n".join(lines) + "\n"

    # lyrics: words per verse, a new line at each phrase start (at the next word, when a phrase
    # starts inside one). A word's syllables are joined ("it-sy" -> "itsy"), except a run on one
    # vowel ("Glo-o-o-o-ri-a"), which keeps a hyphen before each note, so YuE2 sings every note of it
    # instead of one long "Glooooria" (the Christmas batch's Gloria, Oct 6, 2026), and a sung "-ed"
    # ("look-ed", not "looked": The First Noel's verse 2 ran a syllable early after it, Oct 6, 2026)
    phrase_starts = set(Fraction(p) for p in nota["phrases"])
    verses, word_starts, breaks = {}, {}, set()
    for n in mel:
        v = verse_at(n["abc_start"])
        ly = n["lyric"]
        line = verses.setdefault(v, [[]])
        if n["start"] in phrase_starts:
            breaks.add(v)
        cur = line[-1]
        if cur and cur[-1].endswith("⁠"):
            prev = cur[-1][:-1]
            hyphen = vowel_run(prev, ly["text"]) or sung_ed(prev, ly["text"])
            cur[-1] = prev + (HOLD if hyphen else "") + ly["text"]
        else:
            if v in breaks and cur:
                line.append([])
                cur = line[-1]
            breaks.discard(v)
            cur.append(ly["text"])
            word_starts.setdefault(v, []).append(n["start"] + pad)
        if ly["syllabic"] in ("begin", "middle"):
            cur[-1] += "⁠"
    verses[sorted(verses)[0]][0].insert(0, "Oh,")
    words = [{"word": "Oh,", "beat": "0"}]
    for i, v in enumerate(sorted(verses)):
        # the lead-in "Oh," only: a song's own "Oh," (When the Saints, Jingle Bells) is a word on its
        # note, and leaving it out paired every later word with the beat of the one before (Oct 7, 2026)
        flat = [w.replace("⁠", "").replace(HOLD, "") for line in verses[v] for w in line][1 if i == 0 else 0:]
        words += [{"word": w, "beat": str(b), "verse": v} for w, b in zip(flat, word_starts.get(v, []))]
    lyrics = []
    for v in sorted(verses):
        lyrics.append("[Verse]")
        lyrics += [" ".join(w.replace("⁠", "").replace(HOLD, "-") for w in ws) for ws in verses[v] if ws]
        lyrics.append("")
    shift = pad - song_pad
    syllables = [{"verse": n["verse"], "syllable": n["lyric"]["text"], "pitch": n["pitch"],
                  "beat": str(n["abc_start"] + shift), "duration": str(n["duration"])} for n in mel]
    # the Vocal attacks YuE2 will read (ties merged by its own parser): one per syllable, on its beat
    parsed = abc_tools.parse_abc(abc.rstrip("\n")).voices["Vocal"].notes
    want = [Fraction(0)] + [n["abc_start"] + shift for n in mel]
    if [Fraction(on) for on, _, _ in parsed] != want:
        raise ValueError("the Vocal attacks don't match the syllables")
    abcmap = {"padBeats": str(pad), "songPadBeats": str(pad / scale), "scale": str(scale),
              "barBeats": str(bar_len), "bpm": h["tempo"], "key": k_name,
              "songLengthBeats": str(unrolled["length"]), "abcLengthBeats": str(total + bar_len),
              "note": "song beat = ABC beat - padBeats; beats are quarter notes; bar 1 is the sung 'Oh' lead-in",
              "melodyChanges": changes, "words": words, "syllables": syllables,
              "chords": [{"songBeat": str(c[0] - song_pad), "symbol": c[1]} for c in chords]}
    return abc, "\n".join(lyrics).strip() + "\n", abcmap


def write_inputs(piece: Piece) -> Path:
    """build the YuE2 inputs in the piece's work folder; returns the folder."""
    out = piece.work / "yue2"
    out.mkdir(parents=True, exist_ok=True)
    abc, lyrics, abcmap = export(piece.nota, octave=int(piece.spec.get("vocal_octave", 0)))
    (out / "score.abc").write_text(abc)
    (out / "lyrics.txt").write_text(lyrics)
    (out / "abcmap.json").write_text(json.dumps(abcmap, indent=1, ensure_ascii=False) + "\n")
    rows = [{"syllable": "Oh", "beat": "0"}] + [{"syllable": r["syllable"], "beat": r["beat"]} for r in abcmap["syllables"]]
    (out / "syllables.json").write_text(json.dumps({"syllables": rows}, ensure_ascii=False, indent=0) + "\n")
    spec = piece.spec
    meter = abc.split("\nM:")[1].split("\n")[0]
    for i, seed in enumerate(SEEDS, 1):
        req = {"id": f"{piece.pid}-s{i}", "title": piece.title, "profile": "piano-master", "genre": piece.genre[0],
               "language": "English", "key": abcmap["key"], "meter": meter, "tempo_bpm": abcmap["bpm"], "score_abc_path": "score.abc", "lyrics_path": "lyrics.txt",
               "syllables_path": "syllables.json", "seed": seed, "formats": ["flac"]}
        for k in ("vocal_style", "accompaniment_style"):        # a parent's style change for this song
            if spec.get(k):
                req[k] = spec[k]
        (out / f"request-s{i}.json").write_text(json.dumps(req, indent=1) + "\n")
    return out


def stale(folder: Path, inputs: Path) -> bool:
    """A render folder made from another score or other lyrics than the current inputs."""
    job = folder / "job.json"
    if not (folder / "score.abc").exists() or not job.exists():
        return True
    lyrics = json.loads(job.read_text()).get("lyrics", "")
    return (folder / "score.abc").read_text().strip() != (inputs / "score.abc").read_text().strip() or \
        (isinstance(lyrics, str) and lyrics.strip() and lyrics.strip() != (inputs / "lyrics.txt").read_text().strip())


def render(piece: Piece, take: int, dry_run: bool = False) -> dict:
    """Render take `take` (1-3: the seed) into work/<pid>/renders/<pid>-s<take>/, unless it's there."""
    req = piece.work / "yue2" / f"request-s{take}.json"
    renders = piece.work / "renders"
    folder = renders / f"{piece.pid}-s{take}"
    if folder.exists() and (stale(folder, piece.work / "yue2") or not (folder / "report.json").exists()):
        shutil.rmtree(folder)          # made from other inputs (the piece changed), or cut off: render again
    if (folder / "report.json").exists() and not dry_run:
        return json.loads((folder / "report.json").read_text())
    renders.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(GENERATE), "--request", str(req), "--out", str(renders)] + (["--dry-run"] if dry_run else [])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    (renders / f"{piece.pid}-s{take}.log").write_text(proc.stderr)
    last = (proc.stdout.strip().splitlines() or ["{}"])[-1]
    result = json.loads(last) if last.startswith("{") else {"status": "error", "error": proc.stdout[-500:]}
    result["exit"] = proc.returncode
    return result
