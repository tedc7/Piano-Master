"""Song sources -> the arch §5 Arrangement notation.

Adapted from the feasibility converter (feasibility/sync-probe/convert.py), which proved it on
real hymns and songs; the YuE2 export stays there until the media skill (M8) needs it.

Beats are quarter notes in the written score. `phrases` are start beats on the playback
timeline (repeats and verses unrolled), which is what the Play screen rewinds to.
"""
from __future__ import annotations

import math
import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

from music21 import articulations, bar, chord, clef, converter, harmony, spanner

HERE = Path(__file__).resolve().parent
ABC2XML = HERE / ".vendor" / "abc2xml_268" / "abc2xml.py"


def Q(x) -> Fraction:
    return Fraction(x).limit_denominator(4096)


def parse_abc(text: str):
    """ABC -> music21 score, through abc2xml: music21's own ABC reader merges voices and drops lyrics."""
    if not ABC2XML.exists():
        raise FileNotFoundError(f"{ABC2XML} missing: run tools/setup.sh")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "piece.abc"
        src.write_text(text)
        subprocess.run([sys.executable, str(ABC2XML), "-o", tmp, str(src)], check=True, capture_output=True)
        return converter.parse(Path(tmp) / "piece.xml")


def staff_layout(score):
    """[(clef, [parts])]: two piano staves, four SATB staves reduced to two, or one staff."""
    parts = list(score.parts)
    if len(parts) == 4:
        return [("treble", parts[:2]), ("bass", parts[2:])]
    if len(parts) == 2:
        return [("treble", parts[:1]), ("bass", parts[1:])]
    if len(parts) == 1:
        first = parts[0].recurse().getElementsByClass(clef.Clef)
        name = "bass" if first and isinstance(first[0], clef.BassClef) else "treble"
        return [(name, parts)]
    raise ValueError(f"unsupported layout: {len(parts)} parts")


def spelled(p):
    return {"step": p.step, "alter": int(p.accidental.alter) if p.accidental else 0, "octave": p.octave}


def chord_name(pitches):
    """A plain chord symbol (C, Am, G7, D/F#), or None."""
    c = chord.Chord(pitches)
    if len({p.pitchClass for p in c.pitches}) < 3:
        return None
    try:
        root = c.root()
    except Exception:
        return None
    if c.isDominantSeventh():
        suffix = "7"
    else:
        suffix = {"major": "", "minor": "m", "diminished": "dim", "augmented": "aug"}.get(c.quality)
    if suffix is None:
        return None
    name = root.name.replace("-", "b") + suffix
    bass = c.bass().name.replace("-", "b")
    return name + ("/" + bass if bass != root.name.replace("-", "b") else "")


def lyric_text(ly):
    return re.sub(r"^\d+\.\s*", "", (ly.text or "").replace("~", " ")).strip()


def build_notation(score, *, hand_for_single_staff: str = "R", phrase_bars: int = 2, tempo: int | None = None):
    layout = staff_layout(score)
    ref_part = layout[0][1][0]
    ref_measures = list(ref_part.getElementsByClass("Measure"))
    ts0 = ref_part.recurse().getElementsByClass("TimeSignature")[0]
    bar_len = Q(ts0.barDuration.quarterLength)
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
        measures.append(entry)
    pickup = measures[0]["duration"] if measures[0]["duration"] < bar_len else Fraction(0)

    single = len(layout) == 1
    notes, lyrics, warnings = [], [], []
    for staff_no, (clef_name, parts) in enumerate(layout):
        hand = hand_for_single_staff if single else ("R" if staff_no == 0 else "L")
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
                        fingers = [a.fingerNumber for a in el.articulations if isinstance(a, articulations.Fingering)]
                        for pi, (p, member) in enumerate(zip(pitches, members)):
                            tie = member.tie or el.tie
                            entry = {"pitch": p.midi, "spelled": spelled(p), "start": start,
                                     "duration": Q(el.quarterLength), "staff": staff_no,
                                     "hand": hand, "voice": voice}
                            if tie is not None and tie.type in ("start", "continue"):
                                entry["tieToNext"] = True
                            if pi < len(fingers) and fingers[pi] is not None:
                                entry["finger"] = int(fingers[pi])
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
    order_idx = sorted(range(len(notes)), key=lambda i: (notes[i]["start"], notes[i]["staff"], notes[i]["voice"], notes[i]["pitch"]))
    remap = {old: new for new, old in enumerate(order_idx)}
    notes = [notes[i] for i in order_idx]
    for ly in lyrics:
        ly["note"] = remap[ly["note"]]

    chords = []
    for cs in ref_part.recurse().getElementsByClass(harmony.ChordSymbol):
        name = chord_name(cs.pitches)
        if name:
            chords.append({"beat": Q(cs.getOffsetInHierarchy(ref_part)), "symbol": name})

    n_verses = max((ly["verse"] for ly in lyrics), default=1)
    if tempo is None:
        tempo = next((int(round(mm.number)) for mm in score.recurse().getElementsByClass("MetronomeMark")), 80)
    nota = {
        "units": "start and duration are in quarter notes, in the written score",
        "header": {"keySig": fifths, "timeSig": ts0.ratioString, "barLength": bar_len, "tempo": tempo,
                   "pickupBeats": pickup,
                   "range": [min(n["pitch"] for n in notes), max(n["pitch"] for n in notes)],
                   "staves": [c for c, _ in layout]},
        "measures": measures, "notes": notes, "lyrics": lyrics, "chordSymbols": chords,
        "playbackOrder": playback_order(measures, n_verses),
    }
    finish(nota, phrase_bars)
    return nota, warnings


def finish(nota, phrase_bars):
    """Recompute the derived fields after the notes or playback order change."""
    un = unroll(nota)
    nota["phrases"] = phrases(nota, un, phrase_bars)
    nota["length"] = un["length"]
    hdr = nota["header"]
    hdr["range"] = [min(n["pitch"] for n in nota["notes"]), max(n["pitch"] for n in nota["notes"])]


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
            out.append({**n, "index": idx, "start": t + n["start"] - m["start"], "verse": p["verse"], "lyric": ly})
        t += m["duration"]
    return {"notes": out, "entries": entries, "length": t}


def phrases(nota, un, phrase_bars):
    """Phrase starts (playback beats): every `phrase_bars` bars of the metric grid (2 at Prep levels,
    4 from Level 1, arch §3), moved back to take in pickup notes that start a word or follow a gap."""
    bar_len, pickup = nota["header"]["barLength"], nota["header"]["pickupBeats"]
    played = sorted(un["notes"], key=lambda n: n["start"])
    starts = []
    for n in played:
        if not starts or n["start"] > starts[-1]:
            starts.append(n["start"])
    onsets = starts
    if not onsets:
        return [Fraction(0)]
    first = onsets[0]
    downbeat = pickup + max(0, math.ceil((first - pickup) / bar_len)) * bar_len
    has_lyrics = any(n.get("lyric") for n in played)
    lyric_at = {n["start"]: n.get("lyric") for n in played if n.get("isMelody")}
    median = sorted(n["duration"] for n in played)[len(played) // 2]
    out = [Fraction(0)]
    boundary = downbeat + phrase_bars * bar_len
    while boundary < un["length"] - bar_len / 2:
        choice = boundary
        # a pickup starts within about a beat and a half of the bar line
        window = [t for t in onsets if boundary - min(bar_len / 2, 1.5) < t < boundary]
        for t in reversed(window):
            before = [n for n in played if n["start"] < t]
            prev_end = max((n["start"] + n["duration"] for n in before), default=None)
            gap = prev_end is None or prev_end < t
            long_before = bool(before) and max(n["duration"] for n in before if n["start"] == before[-1]["start"]) >= 2 * median
            ly = lyric_at.get(t)
            word_start = (ly is not None and ly["syllabic"] in ("single", "begin")) if has_lyrics else True
            if (gap or long_before) and word_start:
                choice = t
                break
        out.append(choice)
        boundary += phrase_bars * bar_len
    return out


def melody_only(nota, phrase_bars):
    """The arrangement a child plays from a full score: the top line of the upper staff, right hand."""
    keep = [i for i, n in enumerate(nota["notes"]) if n.get("isMelody")]
    remap = {old: new for new, old in enumerate(keep)}
    nota["notes"] = [{**nota["notes"][i], "staff": 0, "voice": 1, "hand": "R"} for i in keep]
    nota["lyrics"] = [{**ly, "note": remap[ly["note"]]} for ly in nota["lyrics"] if ly["note"] in remap]
    nota["header"]["staves"] = ["treble"]
    finish(nota, phrase_bars)
    return nota


def limit_verses(nota, verses, phrase_bars):
    nota["playbackOrder"] = [p for p in nota["playbackOrder"] if p["verse"] <= verses]
    finish(nota, phrase_bars)
    return nota


def jsonable(obj):
    if isinstance(obj, Fraction):
        return float(obj)
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj
