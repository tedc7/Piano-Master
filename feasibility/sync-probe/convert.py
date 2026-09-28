"""Convert real song sources into the app's notation format and into YuE2 inputs (tests 3 and 4).

    .venv/bin/python convert.py            # every song in songs.json
    .venv/bin/python convert.py jeanie     # one song

For each song, writes build/<id>/:
  notation.json    the arch §5 Arrangement notation (header, measures, notes, lyrics,
                   chord symbols, playback order, phrases). Beats are quarter notes.
  yue2/score.abc   the melody in YuE2's native two-voice ABC, unrolled in playback order
  yue2/lyrics.txt  all verses in playback order, one [Verse] per pass
  yue2/request.json, request-half.json (the same score at half tempo, for test 3b)
  yue2/abcmap.json how ABC time relates to song time (pad before the pickup, bar length)
  report.json      what the converter did and anything it had to guess

Sources: ABC Plus (Open Hymnal) goes through abc2xml first, because music21's own ABC
reader merges the four voices into one part and drops the lyrics. MusicXML is read directly.
"""
from __future__ import annotations

import copy
import json
import math
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from music21 import bar, chord, converter, corpus, harmony, spanner

sys.path.insert(0, str(Path.home() / "engines/yue2/YuE/skills/yue2-music/scripts"))
import abc_tools  # noqa: E402  (YuE2's own ABC parser, for the attack-count check)

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
ABC2XML = HERE / "tools" / "abc2xml_268" / "abc2xml.py"
DURATIONS = (48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1)       # YuE2 native ABC length multipliers
ACC = {-2: "__", -1: "_", 0: "=", 1: "^", 2: "^^"}
NATURAL = dict(zip("CDEFGAB", (0, 2, 4, 5, 7, 9, 11)))
SHARPS_ORDER, FLATS_ORDER = "FCGDAEB", "BEADGCF"


def Q(x) -> Fraction:
    return Fraction(x).limit_denominator(4096)


def load(song):
    src = song["source"]
    if src["kind"] == "abc-plus":
        out = BUILD / "xml"
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(ABC2XML), "-o", str(out), str(HERE / src["path"])],
                       check=True, capture_output=True)
        return converter.parse(out / (Path(src["path"]).stem + ".xml"))
    if src["kind"] == "corpus":
        return corpus.parse(src["path"])
    return converter.parse(HERE / src["path"])


def staff_layout(score):
    """[(clef, [parts])]: two piano staves, four SATB staves reduced to two, or one melody staff."""
    parts = list(score.parts)
    if len(parts) == 4:
        return [("treble", parts[:2]), ("bass", parts[2:])]
    if len(parts) == 2:
        return [("treble", parts[:1]), ("bass", parts[1:])]
    if len(parts) == 1:
        return [("treble", parts)]
    raise ValueError(f"unsupported layout: {len(parts)} parts")


def key_name(k):
    """music21 Key -> YuE2 K: value (Bb, F#m, ...)."""
    tonic = k.tonic.name.replace("-", "b")
    return tonic + ("m" if k.mode == "minor" else "")


def tonal_key(score, layout, ref_part):
    """Key for YuE2's K: field. Songs end on the tonic, so the tonic is the last bass note (or the
    last chord symbol's root, or the last melody note), and the mode comes from the third above it
    in the final sonority; the key analysis only breaks a tie. The written key signature can differ
    (What Child Is This is written with two sharps but is in E minor)."""
    from music21 import key as m21key
    analysed = score.analyze("key")
    last_bass = None
    for _, parts in layout[-1:]:
        ns = list(parts[-1].recurse().notes)
        if ns:
            last_bass = min(ns[-1].pitches, key=lambda p: p.midi)
    symbols = list(ref_part.recurse().getElementsByClass(harmony.ChordSymbol))
    if len(layout) == 1 and symbols:
        tonic = symbols[-1].root()
    elif last_bass is not None and len(layout) > 1:
        tonic = last_bass
    else:
        tonic = list(ref_part.recurse().notes)[-1].pitches[-1]
    end = max(n.getOffsetInHierarchy(p) for _, parts in layout for p in parts for n in p.recurse().notes[-1:])
    pcs = {p.pitchClass for _, parts in layout for part in parts for n in part.recurse().notes
           if n.getOffsetInHierarchy(part) >= end - 1 for p in n.pitches}
    if symbols and len(layout) == 1:
        pcs |= {p.pitchClass for p in symbols[-1].pitches}
    t = tonic.pitchClass
    if (t + 4) % 12 in pcs and (t + 3) % 12 not in pcs:
        mode = "major"
    elif (t + 3) % 12 in pcs and (t + 4) % 12 not in pcs:
        mode = "minor"
    else:
        mode = analysed.mode
    return m21key.Key(tonic.name, mode)


def to_pitch(sp):
    from music21 import pitch
    p = pitch.Pitch(sp["step"] + str(sp["octave"]))
    if sp["alter"]:
        p.accidental = sp["alter"]
    return p


def spelled(p):
    return {"step": p.step, "alter": int(p.accidental.alter) if p.accidental else 0, "octave": p.octave}


def chord_name(pitches):
    """A chord symbol in YuE2's allowed vocabulary, or None."""
    c = chord.Chord(pitches)
    if len({p.pitchClass for p in c.pitches}) < 3:
        return None
    try:
        root = c.root()
    except Exception:
        return None
    if c.isDominantSeventh():
        suffix = "7"
    elif c.isDiminishedSeventh():
        suffix = "dim7"
    elif c.isHalfDiminishedSeventh():
        suffix = "m7b5"
    else:
        suffix = {"major": "", "minor": "m", "diminished": "dim", "augmented": "aug"}.get(c.quality)
    if suffix is None:
        return None
    name = root.name.replace("-", "b") + suffix
    bass = c.bass().name.replace("-", "b")
    return name + ("/" + bass if bass != root.name.replace("-", "b") else "")


def lyric_text(ly):
    return re.sub(r"^\d+\.\s*", "", (ly.text or "").replace("~", " ")).strip()


def build_notation(song, score):
    layout = staff_layout(score)
    ref_part = layout[0][1][0]
    ref_measures = list(ref_part.getElementsByClass("Measure"))
    ts0 = ref_part.recurse().getElementsByClass("TimeSignature")[0]
    bar_len = Q(ts0.barDuration.quarterLength)
    k = tonal_key(score, layout, ref_part)
    ks = ref_part.recurse().getElementsByClass("KeySignature")
    fifths = ks[0].sharps if ks else 0

    brackets = {}
    for rb in ref_part.recurse().getElementsByClass(spanner.RepeatBracket):
        for m in rb.getSpannedElements():
            brackets[id(m)] = [int(n) for n in re.findall(r"\d+", str(rb.number))]

    measures = []
    for m in ref_measures:
        entry = {"number": m.number, "start": Q(m.offset), "duration": Q(m.duration.quarterLength)}
        if m.timeSignature is not None and m is not ref_measures[0]:
            entry["timeSig"] = m.timeSignature.ratioString
        if m.keySignature is not None and m is not ref_measures[0]:
            entry["keySig"] = m.keySignature.sharps
        if isinstance(m.leftBarline, bar.Repeat) and m.leftBarline.direction == "start":
            entry["repeatStart"] = True
        if isinstance(m.rightBarline, bar.Repeat) and m.rightBarline.direction == "end":
            entry["repeatEnd"] = True
        if id(m) in brackets:
            entry["volta"] = brackets[id(m)]
        fermata = any(any(e.classes[0] == "Fermata" for e in n.expressions) for n in m.recurse().notes)
        if fermata:
            entry["fermata"] = True
        measures.append(entry)
    pickup = measures[0]["duration"] if measures[0]["duration"] < bar_len else Fraction(0)

    notes, lyrics, warnings = [], [], []
    for staff_no, (clef, parts) in enumerate(layout):
        voice_base = 0
        for part in parts:
            part_measures = list(part.getElementsByClass("Measure"))
            if len(part_measures) != len(measures):
                warnings.append(f"staff {staff_no} part has {len(part_measures)} measures, expected {len(measures)}")
            n_voices = 1
            for mi, m in enumerate(part_measures[:len(measures)]):
                containers = list(m.voices) or [m]
                n_voices = max(n_voices, len(containers))
                for vi, cont in enumerate(containers):
                    voice = voice_base + vi + 1
                    for el in cont.notes:
                        if el.duration.isGrace or el.quarterLength == 0:
                            continue
                        start = measures[mi]["start"] + Q(el.offset)
                        pitches = sorted(el.pitches, key=lambda p: p.midi)
                        members = list(el.notes) if el.isChord else [el]
                        members.sort(key=lambda n: n.pitch.midi)
                        for pi, (p, member) in enumerate(zip(pitches, members)):
                            tie = member.tie or el.tie
                            entry = {"pitch": p.midi, "spelled": spelled(p), "start": start,
                                     "duration": Q(el.quarterLength), "staff": staff_no,
                                     "hand": "R" if staff_no == 0 else "L", "voice": voice}
                            if tie is not None and tie.type in ("start", "continue"):
                                entry["tieToNext"] = True
                            is_top = pi == len(pitches) - 1
                            if staff_no == 0 and voice == 1 and is_top:
                                entry["isMelody"] = True
                                for ly in el.lyrics:
                                    text = lyric_text(ly)
                                    if text:
                                        lyrics.append({"note": len(notes), "verse": ly.number or 1, "text": text,
                                                       "syllabic": ly.syllabic or "single"})
                            if any(e.classes[0] == "Fermata" for e in el.expressions):
                                entry["fermata"] = True
                            notes.append(entry)
            voice_base += n_voices
    notes_order = sorted(range(len(notes)), key=lambda i: (notes[i]["start"], notes[i]["staff"], notes[i]["voice"], notes[i]["pitch"]))
    remap = {old: new for new, old in enumerate(notes_order)}
    notes = [notes[i] for i in notes_order]
    for ly in lyrics:
        ly["note"] = remap[ly["note"]]

    # Chord symbols: from the source, or derived from the harmony of all voices (hymns).
    chords, derived = [], False
    for cs in ref_part.recurse().getElementsByClass(harmony.ChordSymbol):
        name = chord_name(cs.pitches)
        if name:
            chords.append({"beat": Q(cs.getOffsetInHierarchy(ref_part)), "symbol": name})
    if not chords and len(layout) > 1:
        derived = True
        beat = Fraction(3, 2) if ts0.denominator == 8 and ts0.numerator % 3 == 0 else Fraction(1)
        end = measures[-1]["start"] + measures[-1]["duration"]
        # beats on the metric grid: bar lines fall at pickup + k * bar length
        t, last = pickup - math.floor(pickup / beat) * beat, None
        while t < end:
            sounding = [to_pitch(n["spelled"]) for n in notes if n["start"] <= t < n["start"] + n["duration"]]
            name = chord_name(sounding) if sounding else None
            if name and name != last:
                chords.append({"beat": t, "symbol": name, "derived": True})
                last = name
            t += beat

    n_verses = max((ly["verse"] for ly in lyrics), default=1)
    order = playback_order(measures, n_verses)
    tempo = song.get("tempo_qpm") or next((int(round(mm.number)) for mm in score.recurse().getElementsByClass("MetronomeMark")), 80)

    nota = {
        "id": song["id"], "title": song["title"], "genre": song["genre"],
        "source": song["source"],
        "units": "start and duration are in quarter notes (beats of a quarter), in the written score",
        "header": {"keySig": fifths, "key": key_name(k), "mode": k.mode, "timeSig": ts0.ratioString,
                   "barLength": bar_len, "tempo": tempo, "pickupBeats": pickup,
                   "range": [min(n["pitch"] for n in notes), max(n["pitch"] for n in notes)],
                   "staves": [clef for clef, _ in layout]},
        "measures": measures, "notes": notes, "lyrics": lyrics,
        "chordSymbols": chords, "chordSymbolsDerived": derived,
        "playbackOrder": order,
    }
    unrolled = unroll(nota)
    nota["phrases"] = phrases(nota, unrolled)
    nota["length"] = unrolled["length"]
    return nota, warnings


def playback_order(measures, n_verses):
    """Expand repeats and first/second endings; a strophic song without repeats plays once per verse."""
    if not any(m.get("repeatStart") or m.get("repeatEnd") for m in measures):
        return [{"measure": i, "verse": v} for v in range(1, n_verses + 1) for i in range(len(measures))]
    order, i, start, passno = [], 0, 0, 1
    while i < len(measures):
        m = measures[i]
        if m.get("repeatStart") and start != i:
            start, passno = i, 1
        if m.get("volta") and passno not in m["volta"]:
            i += 1
            continue
        order.append({"measure": i, "verse": passno})
        if m.get("repeatEnd") and passno < 2:
            passno += 1
            i = start
            continue
        i += 1
    return order


def unroll(nota):
    """Notes in playback order on the song timeline (beat 0 = first sounding measure's start)."""
    measures, notes = nota["measures"], nota["notes"]
    lyr_by_note = {}
    for ly in nota["lyrics"]:
        lyr_by_note.setdefault(ly["note"], {})[ly["verse"]] = ly
    plays = {}
    for p in nota["playbackOrder"]:
        plays[p["measure"]] = plays.get(p["measure"], 0) + 1
    by_measure = {}
    for idx, n in enumerate(notes):
        for mi, m in enumerate(measures):
            if m["start"] <= n["start"] < m["start"] + m["duration"]:
                by_measure.setdefault(mi, []).append(idx)
                break
    t, out, entries = Fraction(0), [], []
    for p in nota["playbackOrder"]:
        m = measures[p["measure"]]
        entries.append({"start": t, **p, "duration": m["duration"]})
        for idx in by_measure.get(p["measure"], []):
            n = notes[idx]
            lyr = lyr_by_note.get(idx, {})
            ly = lyr.get(p["verse"])
            if ly is None and len(lyr) == 1 and plays[p["measure"]] == 1:
                ly = next(iter(lyr.values()))
            out.append({**n, "index": idx, "start": t + n["start"] - m["start"], "verse": p["verse"],
                        "lyric": ly})
        t += m["duration"]
    return {"notes": out, "entries": entries, "length": t}


def merged_melody(unrolled):
    """Melody notes with ties merged."""
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


def phrases(nota, unrolled):
    """Phrase starts (song beats): every 4 bars of the metric grid, moved back to include pickup notes."""
    bar_len, pickup = nota["header"]["barLength"], nota["header"]["pickupBeats"]
    mel = merged_melody(unrolled)
    starts = [Fraction(0)]
    # the first phrase's downbeat: the first bar line at or after the first sung note (a pickup
    # may be written as a short first measure, or as a full measure that starts with rests)
    first = mel[0]["start"] if mel else Fraction(0)
    downbeat = pickup + max(0, math.ceil((first - pickup) / bar_len)) * bar_len
    boundary = downbeat + 4 * bar_len
    median = sorted(n["duration"] for n in mel)[len(mel) // 2]
    while boundary < unrolled["length"] - bar_len:
        choice = boundary
        window = [i for i, n in enumerate(mel) if boundary - bar_len < n["start"] < boundary]
        for i in reversed(window):
            prev = mel[i - 1] if i else None
            gap = prev is None or prev["start"] + prev["duration"] < mel[i]["start"]
            long_before = prev is not None and prev["duration"] >= 2 * median
            ly = mel[i].get("lyric")
            word_start = ly is None if not any(n.get("lyric") for n in mel) else (
                ly is not None and ly["syllabic"] in ("single", "begin"))
            if (gap or long_before) and word_start:
                choice = mel[i]["start"]
                break
        starts.append(choice)
        boundary += 4 * bar_len
    return starts


# ---------------------------------------------------------------- YuE2 native ABC

def intro(k_name, time_sig, bar_len, unit, fifths, n_bars):
    """n_bars of instrumental intro: the tonic chord, then the dominant seventh in the last bar,
    as chord symbols on Vocal rests and a one-note-per-beat arpeggio on Ins."""
    from music21 import key as m21key
    k = m21key.Key(k_name[:-1] if k_name.endswith("m") else k_name, "minor" if k_name.endswith("m") else "major")
    tonic = k_name
    dom = k.getDominant().name.replace("-", "b") + "7"
    num, den = (int(x) for x in time_sig.split("/"))
    beat = Fraction(3, 2) if den == 8 and num % 3 == 0 else Fraction(4, den)
    per_beat = int(beat / unit)
    vocal, ins = [], []
    for b in range(n_bars):
        symbol = dom if b == n_bars - 1 and n_bars > 1 else tonic
        cs = harmony.ChordSymbol(symbol.replace("b", "-") if len(symbol) > 1 and symbol[1] == "b" else symbol)
        tones = []
        for p in cs.pitches[:3]:
            q = copy.deepcopy(p)          # transpose() would respell D# as Eb
            q.octave = 4
            tones.append(q)
        tones.sort(key=lambda q: q.midi)
        order = [0, 1, 2, 1]
        state = key_accidentals(fifths)
        notes = []
        for i in range(int(bar_len / beat)):
            q = tones[order[i % 4]]
            notes.append(abc_pitch(spelled(q), state) + (str(per_beat) if per_beat > 1 else ""))
        vocal.append(f'"{symbol}"' + "".join(f"z{u if u > 1 else ''}" for u in split_units(int(bar_len / unit))))
        ins.append("".join(notes))
    return vocal, ins


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
    if octave >= 5:
        token += letter.lower() + "'" * (octave - 5)
    else:
        token += letter + "," * (4 - octave)
    return token


def split_units(units):
    out = []
    while units:
        d = next(d for d in DURATIONS if d <= units)
        out.append(d)
        units -= d
    return out


def syllabic_melody(mel):
    """One Vocal attack per sung syllable (YuE2 Lyrics & Melody Input, sections 2 and 4): a note with no
    syllable of its own in its pass (a melisma, or a note only another verse sings) joins the note
    before it, held on that note's pitch; with a gap before it, it becomes a rest. Returns the notes
    and one change record per merged or dropped note."""
    out, changes = [], []
    for n in mel:
        if n.get("lyric") is not None:
            out.append(dict(n))
            continue
        prev = out[-1] if out else None
        if prev and prev["verse"] == n["verse"] and prev["start"] + prev["duration"] == n["start"]:
            changes.append({"change": "merged into the syllable before" if prev["pitch"] != n["pitch"] else "tied",
                            "syllable": prev["lyric"]["text"], "song_beat": str(n["start"]), "pitch": n["pitch"],
                            "into_pitch": prev["pitch"]})
            prev["duration"] += n["duration"]
            prev.setdefault("merged", []).append(n["pitch"])
        else:
            changes.append({"change": "dropped (rest)", "song_beat": str(n["start"]), "pitch": n["pitch"]})
    return out, changes


def yue2_export(nota, unrolled, lead_in=None, syllabic=False, denom=None, with_chords=True):
    h = nota["header"]
    bar_len, pickup = h["barLength"], h["pickupBeats"]
    pad = (bar_len - pickup) % bar_len
    mel = merged_melody(unrolled)
    changes = []
    if syllabic:
        mel, changes = syllabic_melody(mel)
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
    song_chords = [{"song_beat": str(c[0] - pad), "symbol": c[1]} for c in chords]   # for the harmony check
    if not with_chords:
        chords = []   # cot="melody" needs chord-free ABC; YuE2 then chooses the harmony itself

    points = {Fraction(0), total} | {n["abc_start"] for n in mel} | {n["abc_start"] + n["duration"] for n in mel}
    points |= {c[0] for c in chords} | {k * bar_len for k in range(int(total / bar_len) + 1)}
    denom = denom or next(d for d in (16, 32, 64) if all((p * d / 4).denominator == 1 for p in points))
    unit = Fraction(4, denom)

    k_name = h["key"]
    fifths = KEYS_FIFTHS[k_name]
    bars = []
    chord_at = dict(chords)
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
            pieces = []
            for u in units:
                pieces.append(abc_pitch(n["spelled"], state) + (str(u) if u > 1 else ""))
            continues = e < n["abc_start"] + n["duration"]
            tokens.append(prefix + "-".join(pieces) + ("-" if continues else ""))
            sounding = True
        body = "".join(tokens)
        if not sounding and not any(b0 <= c < b1 for c in chord_at):
            body = "Z"
        bars.append(body)

    # sections: one per pass (verse) of the song, by the pass sounding at each bar's start
    song_pad = pad

    def verse_at(t):
        song_t = t - song_pad
        for e in reversed(unrolled["entries"]):
            if e["start"] <= max(song_t, Fraction(0)):
                return e["verse"]
        return 1
    labels = [verse_at(b * bar_len) for b in range(len(bars))]

    # instrumental intro: YuE2 ignores leading rests and dropped the pickup word after them
    # ("What", "It"), so give it bars of tonic and dominant before the pickup bar
    ins = ["Z"] * len(bars)
    fake_word = None
    if lead_in == "intro":
        vocal_intro, ins_intro = intro(k_name, h["timeSig"], bar_len, unit, fifths, 2)
        bars, ins, labels = vocal_intro + bars, ins_intro + ins, ["intro"] * 2 + labels
        pad += 2 * bar_len
    elif lead_in == "fake":
        # one extra bar with a throwaway sung "Oh" on the first melody pitch, removed after alignment,
        # so YuE2's first-word habits (rushing or dropping it) fall on it and not on the real pickup
        state = key_accidentals(fifths)
        num, den = (int(x) for x in h["timeSig"].split("/"))
        held = Fraction(3, 2) if den == 8 and num % 3 == 0 else Fraction(2)
        # not on the first word's pitch: on the same pitch the pitch aligner took the held "Oh" for the
        # first word. Use the tonic (or its fifth when the song starts on the tonic), below the first note
        from music21 import key as m21key
        kk = m21key.Key(k_name[:-1] if k_name.endswith("m") else k_name, "minor" if k_name.endswith("m") else "major")
        first = to_pitch(mel[0]["spelled"])
        target = kk.tonic if kk.tonic.pitchClass != first.pitchClass else kk.getDominant()
        oh = copy.deepcopy(target)
        oh.octave = first.octave
        while oh.midi >= first.midi:
            oh.octave -= 1
        if first.midi - oh.midi > 9:
            oh.octave += 1
        note = abc_pitch(spelled(oh), state)
        units = int(held / unit)
        body = (f'"{k_name}"' if with_chords else "") + note + (str(units) if units > 1 else "") + "".join(
            f"z{u if u > 1 else ''}" for u in split_units(int((bar_len - held) / unit)))
        bars, ins, labels = [body] + bars, ["Z"] + ins, [labels[0]] + labels
        pad += bar_len
        fake_word = "Oh,"

    lines = ["X:1", "T:", f"M:{h['timeSig']}", f"L:1/{denom}", f"Q:1/4={h['tempo']}",
             'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"',
             'V: Ins clef=treble name="Ins Melody" snm="Inst."', f"K:{k_name}"]
    i = 0
    while i < len(bars):
        j = i
        while j < len(bars) and j - i < 4 and labels[j] == labels[i]:
            j += 1
        if i == 0 or labels[i] != labels[i - 1]:
            lines.append("% intro" if labels[i] == "intro" else "% verse")
        rests = all(b == "Z" for b in ins[i:j])
        lines += ["V: Vocal", "|".join(bars[i:j]) + "|", "V: Ins",
                  (f"Z{j - i if j - i > 1 else ''}|" if rests else "|".join(ins[i:j]) + "|")]
        i = j
    abc = "\n".join(lines) + "\n"

    # lyrics: words per verse, a new line at each phrase start
    phrase_starts = set(nota["phrases"])
    verses, word_starts = {}, {}
    for n in mel:
        v = verse_at(n["abc_start"])
        if n.get("lyric") is None:
            continue
        ly = n["lyric"]
        line = verses.setdefault(v, [[]])
        if n["start"] in phrase_starts and line[-1]:
            line.append([])
        cur = line[-1]
        text = ly["text"]
        if cur and cur[-1].endswith("⁠"):
            cur[-1] = cur[-1][:-1] + text
        else:
            cur.append(text)
            word_starts.setdefault(v, []).append(n["start"] + pad)   # ABC beat where the word starts
        if ly["syllabic"] in ("begin", "middle"):
            cur[-1] += "⁠"
    if fake_word and verses:
        first = sorted(verses)[0]
        verses[first][0].insert(0, fake_word)
    # every sung word with the ABC beat it starts on, in lyric order (for aligning the words)
    word_list = [{"word": "Oh,", "beat": 0}] if fake_word else []
    for v in sorted(verses):
        flat = [w.replace("⁠", "") for line in verses[v] for w in line if w != fake_word]
        word_list += [{"word": w, "beat": b, "verse": v} for w, b in zip(flat, word_starts.get(v, []))]
    lyrics = []
    for v in sorted(verses):
        lyrics.append("[Verse]")
        for words in verses[v]:
            if words:
                lyrics.append(" ".join(w.replace("⁠", "") for w in words))
        lyrics.append("")
    # sidecar: one row per sung syllable and its Vocal attack (never sent to YuE2)
    shift = pad - song_pad
    syllables = [{"verse": n["verse"], "syllable": n["lyric"]["text"], "pitch": n["pitch"],
                  "beat": str(n["abc_start"] + shift), "duration": str(n["duration"]),
                  **({"merged_pitches": n["merged"]} if n.get("merged") else {})}
                 for n in mel if n.get("lyric") is not None]
    if syllabic:
        # pre-render check: the Vocal attacks YuE2 will read (ties merged, by the upstream parser) are
        # exactly one per syllable, on the syllables' beats
        parsed = abc_tools.parse_abc(abc.rstrip("\n")).voices["Vocal"].notes
        want = ([Fraction(0)] if fake_word else []) + [n["abc_start"] + shift for n in mel]
        assert [Fraction(on) for on, _, _ in parsed] == want, "Vocal attacks don't match the syllables"
        assert len(syllables) == len(mel), "a Vocal note has no syllable"
        # not checked per section: a pickup syllable sits in the previous section's last bar (sections
        # start at barlines), which is also how YuE2's own plans place pickups
    abcmap = {"lead_in": lead_in, "fake_note_beats": str(bar_len) if fake_word else None, "pad_beats": str(pad), "bar_beats": str(bar_len), "bpm": h["tempo"], "unit_quarter": str(unit),
              "song_length_beats": str(unrolled["length"]), "abc_length_beats": str(total),
              "note": "song beat = ABC beat - pad_beats; beats are quarter notes",
              "syllabic": syllabic, "chords_in_abc": with_chords, "vocal_attacks": len(mel), "syllable_count": len(syllables),
              "melody_changes": changes, "chords": song_chords,
              "words": [{**w, "beat": str(w["beat"])} for w in word_list], "syllables": syllables}
    return abc, "\n".join(lyrics).strip() + "\n", abcmap, k_name


KEYS_FIFTHS = {**{k: i - 7 for i, k in enumerate(["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"])},
               **{k: i - 7 for i, k in enumerate(["Abm", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "A#m"])}}


def jsonable(obj):
    if isinstance(obj, Fraction):
        return float(obj) if obj.denominator in (1, 2, 4, 8, 16, 32, 64) else round(float(obj), 6)
    raise TypeError(type(obj).__name__)


def main(argv):
    config = json.loads((HERE / "songs.json").read_text())
    wanted = set(argv)
    for song in config["songs"]:
        if wanted and song["id"] not in wanted:
            continue
        out = BUILD / song["id"]
        out.mkdir(parents=True, exist_ok=True)
        score = load(song)
        nota, warnings = build_notation(song, score)
        unrolled = unroll(nota)
        (out / "notation.json").write_text(json.dumps(nota, default=jsonable, ensure_ascii=False, indent=1) + "\n")
        report = {"id": song["id"], "measures": len(nota["measures"]), "notes": len(nota["notes"]),
                  "lyrics": len(nota["lyrics"]), "verses": max((l["verse"] for l in nota["lyrics"]), default=0),
                  "playback_measures": len(nota["playbackOrder"]), "length_beats": float(unrolled["length"]),
                  "length_seconds_100": round(float(unrolled["length"]) * 60 / nota["header"]["tempo"], 1),
                  "key": nota["header"]["key"], "time": nota["header"]["timeSig"],
                  "pickup_beats": float(nota["header"]["pickupBeats"]),
                  "chord_symbols": len(nota["chordSymbols"]), "chords_derived": nota["chordSymbolsDerived"],
                  "phrases": len(nota["phrases"]), "warnings": warnings}
        if song.get("yue2"):
            ydir = out / "yue2"
            ydir.mkdir(exist_ok=True)
            h = nota["header"]
            # input styles from "YuE2 Lyrics & Melody Input - Agent Instructions" (repo root), both with
            # the fake lead-in: syl = one attack per syllable, L:1/32, chords (cot full);
            # mel = the same without chords (cot melody)
            styles = {"syl": dict(syllabic=True, denom=32), "mel": dict(syllabic=True, denom=32, with_chords=False)}
            takes = [(v, 1) for v in song.get("lead_in_variants", [None])] + \
                [("fake", k) for k in song.get("extra_fake_seeds", [])] + \
                [(st, k) for st in song.get("input_styles", []) for k in [1] + song.get("extra_fake_seeds", [])]
            for variant, seed_no in takes:
                opts = styles.get(variant, {})
                abc, lyrics, abcmap, k_name = yue2_export(nota, unrolled, "fake" if opts else variant, **opts)
                abcmap["input_style"] = variant if opts else "as written"
                sfx = (f"-{variant}" if variant else "") + (f"-s{seed_no}" if seed_no > 1 else "")
                (ydir / f"score{sfx}.abc").write_text(abc)
                (ydir / f"lyrics{sfx}.txt").write_text(lyrics)
                (ydir / f"abcmap{sfx}.json").write_text(json.dumps(abcmap, indent=1) + "\n")
                req = {"id": song["id"] + sfx, "title": song["title"], "profile": "piano-master", "genre": song["genre"],
                       "language": "English", "key": k_name, "meter": h["timeSig"], "tempo_bpm": h["tempo"],
                       "score_abc_path": f"score{sfx}.abc", "lyrics_path": f"lyrics{sfx}.txt",
                       "seed": 831000 + seed_no, "formats": ["flac"]}
                if opts:
                    # the skill's one-attack-per-syllable check (generate-music, piano-master profile)
                    rows = ([{"syllable": "Oh", "beat": "0"}] if abcmap["fake_note_beats"] else []) + \
                        [{"syllable": r["syllable"], "beat": r["beat"]} for r in abcmap["syllables"]]
                    (ydir / f"syllables{sfx}.json").write_text(json.dumps({"syllables": rows}, ensure_ascii=False, indent=0) + "\n")
                    req["syllables_path"] = f"syllables{sfx}.json"
                (ydir / f"request{sfx}.json").write_text(json.dumps(req, indent=1) + "\n")
                report[f"abc_bars{sfx}"] = abc.count("|") // 2
                report[f"pad_beats{sfx}"] = abcmap["pad_beats"]
        (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps(report))


if __name__ == "__main__":
    main(sys.argv[1:])
