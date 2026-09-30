"""Song analysis (arch §6.8): which skills an arrangement needs, read from its notes.

Every skill's constraints list what a piece may contain once that skill is learned: pitches per
hand (`range`, and `pitches` for keys that aren't next to each other, such as black-key groups),
note lengths (`durations`), time and key signatures, which hands (`hands`), and whether the hands
play at once (`handsTogether`: `held` when one hand holds a note of 2 beats or more under the
other, `true` for any). Since the real Prep A map (v0.24) a skill can also allow melodic
`intervals` (1 a repeat, 2 a step, 3 a skip...), `chords` (two or more notes at once in one hand:
`true` for any, or the sizes allowed, `[5]` for C and G together, measured bottom note to top),
`ties` and `rests` (a silence inside the piece); these are only read when some skill in the map
names them, so an older map analyses as before. A skill with `letters: true` is a pre-staff skill
(Prep A Units 1 to 3): its pitches count only in letter-named pieces (`letters` in the notation
header), whose notes are read by their letter names, not from the staff. Each thing an arrangement uses is credited to
the earliest skill (lowest sequence) whose constraints allow it; those skills are its **required
skills**. Anything no skill allows is **beyond the map**: the arrangement can't unlock until the
map grows to cover it. Also recorded: the **map point** (the highest sequence among the required
skills), the **featured skills** (the newest one, and the next newest when its notes or hands
are in at least half the bars; a time signature, key or note length alone doesn't make a skill
featured), the **skill measures** (which bars use each required skill, for implicit review,
§8.4) and the notes to play in each bar, counting repeats (to score those bars on their own).

Some skills are ideas the notes can't show: sitting at the piano, finger numbers, the measure, a
dynamic mark (v0.25, one concept per Journey bubble). Their constraints allow nothing (at most a
hand `position`, for finger numbers), so no piece is ever credited to them; instead the pieces
**written for** one (its `pieces` list in the skill map) practise it: the build passes
`written_for`, and the skill joins those pieces' required skills, first among their featured
skills, with every bar as its skill measures.

Pure Python on the §5 notation (no music21), so the content build on the dev box and the App API
share it.
"""
from __future__ import annotations

import re
from typing import Any

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
HAND_WORD = {"R": "right", "L": "left"}
HANDS_WORD = {"together": "together", "held": "together over a held note", "turns": "taking turns"}
INTERVAL_WORD = {1: "repeats", 2: "2nds", 3: "3rds", 5: "5ths", 8: "octaves"}


def midi(name: str) -> int:
    """'C4' -> 60, 'F#3' -> 54, 'Bb2' -> 46 (also ♯ and ♭)."""
    m = re.fullmatch(r"([A-Ga-g])([#♯b♭-]*)(-?\d+)", name.strip())
    if not m:
        raise ValueError(f"not a note name: {name!r}")
    alter = sum(1 if c in "#♯" else -1 for c in m.group(2))
    return 12 * (int(m.group(3)) + 1) + STEPS[m.group(1).upper()] + alter


def name(p: int) -> str:
    return f"{NAMES[p % 12]}{p // 12 - 1}"


def dur_key(d: float) -> float:
    return round(float(d), 4)


# constraint keys that switch on a kind of feature for the whole map (see the module docstring)
OPTIONAL = {"intervals": "interval", "chords": "chord", "ties": "tie", "rests": "rest", "letters": "letters"}


class Constraints:
    """One skill's constraints, parsed. Raises ValueError for a bad one (the loader's check)."""

    def __init__(self, skill: dict):
        c = skill.get("constraints") or {}
        self.hands = set(c.get("hands") or [])
        self.range = {h: (midi(lo), midi(hi)) for h, (lo, hi) in (c.get("range") or {}).items()}
        self.pitches = {h: {midi(n) for n in names} for h, names in (c.get("pitches") or {}).items()}
        self.durations = {dur_key(d) for d in c.get("durations") or []}
        self.time_sigs = set(c.get("timeSigs") or [])
        self.key_sigs = set(c.get("keySigs") or [])
        together = c.get("handsTogether")
        if together not in (None, False, True, "held"):
            raise ValueError(f"{skill.get('id')}: handsTogether is true, false or held, not {together!r}")
        self.hands_together = together          # None/False, "held", or True (any)
        self.intervals = {int(i) for i in c.get("intervals") or []}
        ch = c.get("chords")
        self.chords: bool | set[int] = {int(i) for i in ch} if isinstance(ch, list) else bool(ch)
        self.ties = bool(c.get("ties"))
        self.rests = bool(c.get("rests"))
        self.letters = bool(c.get("letters"))
        self.mentions = {kind for key, kind in OPTIONAL.items() if key in c}
        if together == "held":
            self.mentions.add("held")
        for h in [*self.range, *self.pitches]:
            if h not in ("R", "L"):
                raise ValueError(f"{skill.get('id')}: range or pitches for unknown hand {h!r}")
        for h in self.range:
            if self.range[h][0] > self.range[h][1]:
                raise ValueError(f"{skill.get('id')}: range {h} is upside down")
        if any(i < 1 or i > 15 for i in self.intervals):
            raise ValueError(f"{skill.get('id')}: intervals are 1 (a repeat), 2 (a step), 3 (a skip)... up to 15")

    @property
    def sees_nothing(self) -> bool:
        """An idea the notes can't show (see the module docstring): it allows no feature at all."""
        return not (self.hands or self.range or self.pitches or self.durations or self.time_sigs or self.key_sigs
                    or self.hands_together or self.intervals or self.chords or self.ties or self.rests)

    def has_pitch(self, hand: str, p: int) -> bool:
        r = self.range.get(hand)
        return hand in self.hands and ((r is not None and r[0] <= p <= r[1]) or p in self.pitches.get(hand, ()))

    def allows(self, feature: tuple) -> bool:
        kind = feature[0]
        if kind == "pitch":                     # read from the staff: never by a pre-staff skill
            return not self.letters and self.has_pitch(feature[1], feature[2])
        if kind == "lpitch":                    # a letter-named note: any skill that has the key
            return self.has_pitch(feature[1], feature[2])
        if kind == "interval":
            return feature[1] in self.hands and feature[2] in self.intervals
        if kind == "chord":
            if feature[1] not in self.hands:
                return False
            return self.chords is True or (isinstance(self.chords, set) and feature[2] in self.chords)
        if kind == "tie":
            return self.ties
        if kind == "rest":
            return self.rests
        if kind == "dur":
            return any(abs(feature[1] - d) < 1e-3 for d in self.durations)
        if kind == "time":
            return feature[1] in self.time_sigs
        if kind == "key":
            return feature[1] in self.key_sigs
        if kind == "hands":
            if feature[1] == "together":
                return self.hands_together is True
            if feature[1] == "held":
                return self.hands_together in (True, "held")
            return {"R", "L"} <= self.hands          # taking turns
        return False


def diatonic(n: dict) -> int:
    """A note's place on the staff (C4 = 28), from its spelling, or from its key for a bare pitch."""
    sp = n.get("spelled")
    if sp:
        return 7 * int(sp["octave"]) + "CDEFGAB".index(sp["step"].upper())
    p = int(n["pitch"])
    return 7 * (p // 12 - 1) + [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6][p % 12]


def features(nota: dict, kinds: set[str] | None = None) -> dict[tuple, set[int]]:
    """Everything the arrangement uses -> the written bar numbers that use it. `kinds` are the
    optional kinds of feature the skill map uses (Constraints.mentions); None reads none of them."""
    kinds = kinds or set()
    measures = nota["measures"]
    notes = nota["notes"]
    letters = bool(nota["header"].get("letters")) and "letters" in kinds

    def bar_of(beat: float) -> int:
        for m in measures:
            if m["start"] - 1e-6 <= beat < m["start"] + m["duration"] - 1e-6:
                return m["number"]
        return measures[-1]["number"]

    out: dict[tuple, set[int]] = {}

    def add(f: tuple, bar: int) -> None:
        out.setdefault(f, set()).add(bar)

    played = [n for n in notes if not n.get("grace")]     # ornaments are drawn, not played for the score
    for n in played:
        b = bar_of(n["start"])
        add(("lpitch" if letters else "pitch", n["hand"], int(n["pitch"])), b)
        add(("dur", dur_key(n["duration"])), b)
        if "tie" in kinds and (n.get("tieToNext") or n.get("tieFrom")):
            add(("tie",), b)
    if not letters and kinds & {"interval", "chord"}:
        for hand in ("R", "L"):
            at: dict[float, list[dict]] = {}
            for n in played:
                if n["hand"] == hand and not n.get("tieFrom"):
                    at.setdefault(round(float(n["start"]), 4), []).append(n)
            prev = None
            for start in sorted(at):
                group = at[start]
                if len(group) > 1 and "chord" in kinds:
                    span = max(diatonic(n) for n in group) - min(diatonic(n) for n in group) + 1
                    add(("chord", hand, span), bar_of(start))
                if len(group) == 1 and prev is not None and "interval" in kinds:
                    add(("interval", hand, abs(diatonic(group[0]) - diatonic(prev)) + 1), bar_of(start))
                prev = group[0] if len(group) == 1 else None
    if "rest" in kinds and measures:
        # a silence inside the piece: no note sounding, from the first bar's start to the last bar's end
        t = float(measures[0]["start"])
        end = float(measures[-1]["start"] + measures[-1]["duration"])
        for n in sorted(played, key=lambda x: x["start"]):
            if n["start"] > t + 1e-6:
                add(("rest",), bar_of(t))
            t = max(t, float(n["start"] + n["duration"]))
        if end > t + 1e-6:
            add(("rest",), bar_of(t))
    time_sig, key_sig = nota["header"]["timeSig"], nota["header"]["keySig"]
    for m in measures:
        time_sig = m.get("timeSig", time_sig)
        key_sig = m.get("keySig", key_sig)
        add(("time", time_sig), m["number"])
        add(("key", key_sig), m["number"])
    hands = {n["hand"] for n in notes}
    if hands >= {"R", "L"}:
        together, held = set(), set()
        by_hand = {h: [n for n in notes if n["hand"] == h and not n.get("grace")] for h in ("R", "L")}
        for r in by_hand["R"]:
            r0, r1 = r["start"], r["start"] + r["duration"]
            for left in by_hand["L"]:
                if left["start"] < r1 - 1e-6 and r0 < left["start"] + left["duration"] - 1e-6:
                    b = bar_of(max(r0, left["start"]))
                    # one hand holding a long note (2 beats or more) while the other plays
                    if "held" in kinds and max(r["duration"], left["duration"]) >= 2 - 1e-6:
                        held.add(b)
                    else:
                        together.add(b)
        for b in held:
            add(("hands", "held"), b)
        for b in together:
            add(("hands", "together"), b)
        for n in notes:
            add(("hands", "turns"), bar_of(n["start"]))
    return out


def describe(beyond: list[tuple]) -> list[str]:
    """What is beyond the map, in words: 'right hand up to E5', '3/4 time'..."""
    out = []
    for hand in ("R", "L"):
        ps = sorted(f[2] for f in beyond if f[0] in ("pitch", "lpitch") and f[1] == hand)
        if ps:
            out.append(f"{HAND_WORD[hand]} hand {name(ps[0])}" + (f" to {name(ps[-1])}" if len(ps) > 1 else ""))
    for hand in ("R", "L"):
        iv = sorted(f[2] for f in beyond if f[0] == "interval" and f[1] == hand)
        if iv:
            out.append(f"{HAND_WORD[hand]} hand intervals of " + ", ".join(INTERVAL_WORD.get(i, f"{i}ths") for i in iv))
    out += [f"two notes at once ({INTERVAL_WORD.get(f[2], f'{f[2]}ths')} apart) in the {HAND_WORD[f[1]]} hand"
            for f in beyond if f[0] == "chord"]
    out += ["ties" for f in beyond if f[0] == "tie"]
    out += ["rests" for f in beyond if f[0] == "rest"]
    durs = sorted(f[1] for f in beyond if f[0] == "dur")
    if durs:
        out.append("note lengths " + ", ".join(f"{d:g}" for d in durs) + " beats")
    out += [f"{f[1]} time" for f in beyond if f[0] == "time"]
    out += [f"key signature {f[1]:+d}" for f in beyond if f[0] == "key"]
    out += [f"hands {HANDS_WORD[f[1]]}" for f in beyond if f[0] == "hands"]
    return out


def analyze(nota: dict, skills: list[dict], parsed: dict[str, Constraints] | None = None,
            written_for: str | None = None) -> dict[str, Any]:
    """The arrangement's required and featured skills, map point, skill measures, and anything
    beyond the map. `skills` are skill-map entries (id, sequence, constraints). `written_for` is
    the skill whose `pieces` list names this piece; it counts only when the notes can't show it."""
    order = sorted(skills, key=lambda s: s["sequence"])
    parsed = parsed or {s["id"]: Constraints(s) for s in order}
    uses = features(nota, set().union(*(c.mentions for c in parsed.values())) if parsed else set())
    bars: dict[str, set[int]] = {}
    note_bars: dict[str, set[int]] = {}           # bars where the skill's pitches or hands are used
    beyond = []
    for f, where in uses.items():
        sid = next((s["id"] for s in order if parsed[s["id"]].allows(f)), None)
        if sid is None:
            beyond.append(f)
        else:
            bars.setdefault(sid, set()).update(where)
            if f[0] in ("pitch", "lpitch", "hands"):
                note_bars.setdefault(sid, set()).update(where)
    seq = {s["id"]: s["sequence"] for s in order}
    required = sorted(bars, key=lambda k: seq[k])
    played_bars = {b for f, w in uses.items() if f[0] == "pitch" for b in w} or {1}
    featured = []
    if required:
        newest = sorted(required, key=lambda k: -seq[k])
        featured.append(newest[0])
        if len(newest) > 1 and len(note_bars.get(newest[1], set()) & played_bars) >= len(played_bars) / 2:
            featured.append(newest[1])
    plays: dict[int, int] = {}
    for p in nota.get("playbackOrder") or [{"measure": i} for i in range(len(nota["measures"]))]:
        num = nota["measures"][p["measure"]]["number"]
        plays[num] = plays.get(num, 0) + 1
    bar_notes: dict[int, int] = {}
    for n in nota["notes"]:
        if not n.get("grace") and not n.get("tieFrom"):
            b = next((m["number"] for m in nota["measures"]
                      if m["start"] - 1e-6 <= n["start"] < m["start"] + m["duration"] - 1e-6), None)
            if b is not None:
                bar_notes[b] = bar_notes.get(b, 0) + plays.get(b, 1)
    if written_for in parsed and parsed[written_for].sees_nothing and written_for not in bars:
        bars[written_for] = {m["number"] for m in nota["measures"]}
        required = sorted(bars, key=lambda k: seq[k])
        featured = [written_for, *featured[:1]]
    return {
        "barNotes": {str(b): c for b, c in sorted(bar_notes.items())},
        "requiredSkills": required,
        "featuredSkills": featured,
        "mapPoint": max((seq[k] for k in required), default=None),
        "skillMeasures": {k: sorted(bars[k]) for k in required},
        "beyondMap": describe(sorted(beyond, key=str)),
    }
