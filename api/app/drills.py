"""The drill generator (arch §6.6, §8.9): short practice pieces built from parameters, in the same
§5 notation as the content build writes, so the Play screen plays and scores them unchanged.

Every drill uses only material from skills the student has passed (their constraints' notes per
hand, note lengths, time and key signatures), so its output counts as parent-approved (§1). The
one exception is the note a reading drill is about: it comes from a piece the student is already
practising.

Kinds (first version):
- reading: a short melody that keeps returning to a note the student confuses, with the note it
  is confused with nearby (the note-confusion remedy, §8.8)
- rhythm: one rhythm figure over and over on one key; any key counts, only timing matters (§7.8
  rhythm tapping; the rhythm remedy)
- scale, arpeggio, five-finger: technique drills with the standard fingerings (fingering.py)
Shift drills and tempo ramps loop bars of the piece itself at chosen presets, so they need no
generated notes (diagnostics.py builds those session items).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from . import fingering
from .analysis import Constraints, midi, name

SHARP_NAMES = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
SHARP_ALTER = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]
FLAT_NAMES = ["C", "D", "D", "E", "E", "F", "G", "G", "A", "A", "B", "B"]
FLAT_ALTER = [0, -1, 0, -1, 0, 0, -1, 0, -1, 0, -1, 0]
DEFAULT_RANGE = {"R": (midi("C4"), midi("G4")), "L": (midi("C3"), midi("G3"))}
DRILL_TEMPO = 80

# Rhythm figures (diagnostics.figures names them); each is one bar of 4/4 as (duration, sounded)
FIGURE_BARS: dict[str, list[tuple[float, bool]]] = {
    "eighths": [(0.5, True), (0.5, True), (1, True), (0.5, True), (0.5, True), (1, True)],
    "dotted": [(1.5, True), (0.5, True), (1.5, True), (0.5, True)],
    "after-rest": [(1, False), (1, True), (1, False), (1, True)],
    "sixteenths": [(0.25, True)] * 4 + [(1, True)] + [(0.25, True)] * 4 + [(1, True)],
    "triplet": [(1 / 3, True)] * 3 + [(1, True)] + [(1 / 3, True)] * 3 + [(1, True)],
    "offbeat": [(0.5, True), (1, True), (1, True), (1, True), (0.5, True)],
    "quarters": [(1, True)] * 4,
    "beat": [(1, True)] * 4,
}
FIGURE_WORDS = {"eighths": "eighth notes", "dotted": "dotted notes", "after-rest": "notes after a rest",
                "sixteenths": "sixteenth notes", "triplet": "triplets", "offbeat": "off-beat notes",
                "quarters": "quarter notes", "beat": "a steady beat"}


def spell(p: int, key_sig: int = 0) -> dict[str, Any]:
    names, alters = (FLAT_NAMES, FLAT_ALTER) if key_sig < 0 else (SHARP_NAMES, SHARP_ALTER)
    return {"step": names[p % 12], "alter": alters[p % 12], "octave": p // 12 - 1}


@dataclass
class Material:
    """What the student's passed skills allow (their constraints, merged)."""
    ranges: dict[str, tuple[int, int]] = field(default_factory=dict)
    durations: set[float] = field(default_factory=set)
    time_sigs: set[str] = field(default_factory=set)
    key_sigs: set[int] = field(default_factory=set)

    @classmethod
    def from_skills(cls, skills: list[dict]) -> "Material":
        m = cls()
        for s in skills:
            c = Constraints(s)
            for h, (lo, hi) in c.range.items():
                if h in c.hands:
                    a, b = m.ranges.get(h, (lo, hi))
                    m.ranges[h] = (min(a, lo), max(b, hi))
            m.durations |= c.durations
            m.time_sigs |= c.time_sigs
            m.key_sigs |= c.key_sigs
        return m

    def range_for(self, hand: str) -> tuple[int, int]:
        return self.ranges.get(hand) or DEFAULT_RANGE[hand]

    def pitches(self, hand: str, key_sig: int = 0) -> list[int]:
        """The keys in reach for the hand: the white keys, or the scale of the key signature."""
        lo, hi = self.range_for(hand)
        tonic = (7 * key_sig) % 12            # C for 0, G for 1, F for -1...
        scale = {(tonic + s) % 12 for s in fingering.MAJOR}
        return [p for p in range(lo, hi + 1) if p % 12 in scale]


def notation(events: dict[str, list[tuple[float, float, int, int | None]]], *, time_sig: str = "4/4", key_sig: int = 0,
             tempo: float = DRILL_TEMPO, phrase_bars: int = 2) -> dict[str, Any]:
    """§5 notation from each hand's events (start, duration, pitch, finger), in quarter-note beats."""
    num, den = (int(x) for x in time_sig.split("/"))
    bar = num * 4 / den
    hands = [h for h in ("R", "L") if events.get(h)]
    staves = ["treble" if h == "R" else "bass" for h in hands]
    notes = []
    for h in hands:
        for start, dur, p, f in events[h]:
            n = {"pitch": p, "spelled": spell(p, key_sig), "start": round(start, 6), "duration": round(dur, 6),
                 "staff": hands.index(h), "hand": h, "voice": 1, "isMelody": h == hands[0]}
            if f:
                n["finger"] = f
            if abs(dur * 3 - round(dur * 3)) < 1e-6 and abs(dur - round(dur * 2) / 2) > 1e-6:
                n["tuplet"] = [3, 2]
            notes.append(n)
    notes.sort(key=lambda n: (n["start"], n["pitch"]))
    end = max(n["start"] + n["duration"] for n in notes)
    count = max(1, int(-(-end // bar)))
    measures = [{"number": i + 1, "start": i * bar, "duration": bar} for i in range(count)]
    lo, hi = min(n["pitch"] for n in notes), max(n["pitch"] for n in notes)
    return {
        "header": {"keySig": key_sig, "timeSig": time_sig, "barLength": bar, "tempo": tempo, "pickupBeats": 0.0,
                   "range": [lo, hi], "staves": staves},
        "measures": measures, "notes": notes, "lyrics": [], "chordSymbols": [], "graces": [],
        "playbackOrder": [{"measure": i, "verse": 1, "pass": 1} for i in range(count)],
        "phrases": [i * bar for i in range(0, count, phrase_bars)], "length": count * bar,
    }


def piece(drill_id: str, title: str, nota: dict, drill: dict[str, Any], level: str = "Prep A") -> dict[str, Any]:
    hands = {n["hand"] for n in nota["notes"]}
    return {"id": drill_id, "title": title, "kind": "drill", "level": level, "hands": "RL" if len(hands) > 1 else hands.pop(),
            "skillId": None, "notation": nota, "media": None, "drill": drill}


def _bar_length(m: Material) -> tuple[str, float]:
    ts = "4/4" if not m.time_sigs or "4/4" in m.time_sigs else sorted(m.time_sigs)[0]
    num, den = (int(x) for x in ts.split("/"))
    return ts, num * 4 / den


def reading(focus: int, confused: int | None, hand: str, m: Material, seed: int = 0, bars: int = 4) -> tuple[str, dict]:
    """A melody that keeps coming back to `focus`, with `confused` beside it when it is in reach."""
    rng = random.Random(seed)
    key = 0 if not m.key_sigs or 0 in m.key_sigs else sorted(m.key_sigs)[0]
    ts, bar = _bar_length(m)
    longer = sorted(d for d in m.durations if d >= 0.5)
    beat = 1.0 if not longer or 1.0 in longer else longer[0]
    reach = [p for p in m.pitches(hand, key) if abs(p - focus) <= 5 and p != focus]
    if confused is not None and confused != focus and m.range_for(hand)[0] <= confused <= m.range_for(hand)[1]:
        partner = confused
    else:
        partner = rng.choice(reach) if reach else focus
    others = [p for p in reach if p != partner] or [partner]
    per_bar = int(round(bar / beat))
    events, t = [], 0.0
    for b in range(bars):
        last = b == bars - 1
        seq = []
        for k in range(per_bar):
            if k % 2 == 0:
                seq.append(focus)
            else:
                seq.append(partner if (b + k // 2) % 2 == 0 else rng.choice(others))
        if last:                                   # end on the focus note, held
            seq = seq[:max(1, per_bar - 2)] + [focus]
        for k, p in enumerate(seq):
            dur = beat if not (last and k == len(seq) - 1) else bar - beat * (len(seq) - 1)
            events.append((t, dur, p, None))
            t += dur
    nota = notation({hand: events}, time_sig=ts, key_sig=key)
    fingering.generate(nota)
    words = f"{name(focus)[:-1]} and {name(partner)[:-1]}" if partner != focus else name(focus)[:-1]
    return f"Reading game: {words}", nota


def rhythm(figure: str, hand: str, m: Material, bars: int = 4) -> tuple[str, dict, int]:
    """One rhythm figure repeated on one key (the middle of the hand's reach); any key counts."""
    lo, hi = m.range_for(hand)
    key_pitches = m.pitches(hand, 0) or [lo]
    pitch = key_pitches[len(key_pitches) // 2] if hand == "L" else key_pitches[0]
    pattern = FIGURE_BARS.get(figure, FIGURE_BARS["quarters"])
    events, t = [], 0.0
    for _ in range(bars):
        for dur, sounded in pattern:
            if sounded:
                events.append((t, dur, pitch, None))
            t += dur
    nota = notation({hand: events}, time_sig="4/4")
    return f"Rhythm tap: {FIGURE_WORDS.get(figure, figure)}", nota, pitch


def scale(tonic: int, mode: str, hand: str, octaves: int = 1) -> tuple[str, dict] | None:
    """Up and down in quarter notes, ending on a whole note, with the table fingering."""
    up = fingering.scale_pitches(tonic, mode, octaves)
    fu = fingering.scale_fingering(tonic, mode, hand, octaves)
    if fu is None:
        return None
    down = up[-2::-1]
    fd = fingering.scale_fingering(tonic, mode, hand, octaves, down=True)[1:]
    seq = list(zip(up + down, fu + fd))
    events, t = [], 0.0
    for k, (p, f) in enumerate(seq):
        dur = 4.0 - (t % 4) if k == len(seq) - 1 else 1.0
        events.append((t, dur, p, f))
        t += dur
    key = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 5: -1, 10: -2, 3: -3, 8: -4, 1: -5}.get(tonic % 12 if mode == "major" else (tonic + 3) % 12, 0)
    nota = notation({hand: events}, key_sig=key)
    return f"{name(tonic)[:-1]} {mode} scale, {'right' if hand == 'R' else 'left'} hand", nota


def arpeggio(tonic: int, mode: str, hand: str, octaves: int = 1) -> tuple[str, dict] | None:
    fs = fingering.arpeggio_fingering(tonic, hand, octaves)
    if fs is None:
        return None
    third = 4 if mode == "major" else 3
    up = [tonic + 12 * o + s for o in range(octaves) for s in (0, third, 7)] + [tonic + 12 * octaves]
    seq = list(zip(up + up[-2::-1], fs + fs[-2::-1]))
    events, t = [], 0.0
    for k, (p, f) in enumerate(seq):
        dur = 4.0 - (t % 4) if k == len(seq) - 1 else 1.0
        events.append((t, dur, p, f))
        t += dur
    nota = notation({hand: events})
    return f"{name(tonic)[:-1]} {mode} arpeggio, {'right' if hand == 'R' else 'left'} hand", nota


def five_finger(base: int, hand: str) -> tuple[str, dict]:
    """The five-finger position from `base` up and back down (C D E F G F E D C)."""
    whites = [p for p in range(base, base + 12) if p % 12 not in fingering.BLACK][:5]
    seq = whites + whites[-2::-1]
    fs = [fingering.position_finger(p, base, hand) for p in seq]
    events = [(float(k), 1.0 if k < len(seq) - 1 else 4.0 - (k % 4), p, f) for k, (p, f) in enumerate(zip(seq, fs))]
    nota = notation({hand: events})
    return f"{name(base)[:-1]} position, {'right' if hand == 'R' else 'left'} hand", nota
