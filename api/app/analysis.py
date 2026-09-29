"""Song analysis (arch §6.8): which skills an arrangement needs, read from its notes.

Every skill's constraints list what a piece may contain once that skill is learned: pitches per
hand (`range`), note lengths (`durations`), time and key signatures, which hands (`hands`), and
whether the hands play at once (`handsTogether`). Each thing an arrangement uses is credited to
the earliest skill (lowest sequence) whose constraints allow it; those skills are its **required
skills**. Anything no skill allows is **beyond the map**: the arrangement can't unlock until the
map grows to cover it. Also recorded: the **map point** (the highest sequence among the required
skills), the **featured skills** (the newest one, and the next newest when its notes or hands
are in at least half the bars; a time signature, key or note length alone doesn't make a skill
featured), the **skill measures** (which bars use each required skill, for implicit review,
§8.4) and the notes to play in each bar, counting repeats (to score those bars on their own).

Pure Python on the §5 notation (no music21), so the content build on the dev box and the App API
share it.
"""
from __future__ import annotations

import re
from typing import Any

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
HAND_WORD = {"R": "right", "L": "left"}


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


class Constraints:
    """One skill's constraints, parsed. Raises ValueError for a bad one (the loader's check)."""

    def __init__(self, skill: dict):
        c = skill.get("constraints") or {}
        self.hands = set(c.get("hands") or [])
        self.range = {h: (midi(lo), midi(hi)) for h, (lo, hi) in (c.get("range") or {}).items()}
        self.durations = {dur_key(d) for d in c.get("durations") or []}
        self.time_sigs = set(c.get("timeSigs") or [])
        self.key_sigs = set(c.get("keySigs") or [])
        self.hands_together = bool(c.get("handsTogether"))
        for h in self.range:
            if h not in ("R", "L"):
                raise ValueError(f"{skill.get('id')}: range for unknown hand {h!r}")
            if self.range[h][0] > self.range[h][1]:
                raise ValueError(f"{skill.get('id')}: range {h} is upside down")

    def allows(self, feature: tuple) -> bool:
        kind = feature[0]
        if kind == "pitch":
            _, hand, p = feature
            r = self.range.get(hand)
            return hand in self.hands and r is not None and r[0] <= p <= r[1]
        if kind == "dur":
            return any(abs(feature[1] - d) < 1e-3 for d in self.durations)
        if kind == "time":
            return feature[1] in self.time_sigs
        if kind == "key":
            return feature[1] in self.key_sigs
        if kind == "hands":
            if feature[1] == "together":
                return self.hands_together
            return {"R", "L"} <= self.hands          # taking turns
        return False


def features(nota: dict) -> dict[tuple, set[int]]:
    """Everything the arrangement uses -> the written bar numbers that use it."""
    measures = nota["measures"]
    notes = nota["notes"]

    def bar_of(beat: float) -> int:
        for m in measures:
            if m["start"] - 1e-6 <= beat < m["start"] + m["duration"] - 1e-6:
                return m["number"]
        return measures[-1]["number"]

    out: dict[tuple, set[int]] = {}

    def add(f: tuple, bar: int) -> None:
        out.setdefault(f, set()).add(bar)

    for n in notes:
        if n.get("grace"):
            continue                        # ornaments are drawn, not played for the score
        b = bar_of(n["start"])
        add(("pitch", n["hand"], int(n["pitch"])), b)
        add(("dur", dur_key(n["duration"])), b)
    time_sig, key_sig = nota["header"]["timeSig"], nota["header"]["keySig"]
    for m in measures:
        time_sig = m.get("timeSig", time_sig)
        key_sig = m.get("keySig", key_sig)
        add(("time", time_sig), m["number"])
        add(("key", key_sig), m["number"])
    hands = {n["hand"] for n in notes}
    if hands >= {"R", "L"}:
        together = set()
        by_hand = {h: [n for n in notes if n["hand"] == h and not n.get("grace")] for h in ("R", "L")}
        for r in by_hand["R"]:
            r0, r1 = r["start"], r["start"] + r["duration"]
            for left in by_hand["L"]:
                if left["start"] < r1 - 1e-6 and r0 < left["start"] + left["duration"] - 1e-6:
                    together.add(bar_of(max(r0, left["start"])))
        if together:
            for b in together:
                add(("hands", "together"), b)
        for n in notes:
            add(("hands", "turns"), bar_of(n["start"]))
    return out


def describe(beyond: list[tuple]) -> list[str]:
    """What is beyond the map, in words: 'right hand up to E5', '3/4 time'..."""
    out = []
    for hand in ("R", "L"):
        ps = sorted(f[2] for f in beyond if f[0] == "pitch" and f[1] == hand)
        if ps:
            out.append(f"{HAND_WORD[hand]} hand {name(ps[0])}" + (f" to {name(ps[-1])}" if len(ps) > 1 else ""))
    durs = sorted(f[1] for f in beyond if f[0] == "dur")
    if durs:
        out.append("note lengths " + ", ".join(f"{d:g}" for d in durs) + " beats")
    out += [f"{f[1]} time" for f in beyond if f[0] == "time"]
    out += [f"key signature {f[1]:+d}" for f in beyond if f[0] == "key"]
    out += [f"hands {'together' if f[1] == 'together' else 'taking turns'}" for f in beyond if f[0] == "hands"]
    return out


def analyze(nota: dict, skills: list[dict], parsed: dict[str, Constraints] | None = None) -> dict[str, Any]:
    """The arrangement's required and featured skills, map point, skill measures, and anything
    beyond the map. `skills` are skill-map entries (id, sequence, constraints)."""
    order = sorted(skills, key=lambda s: s["sequence"])
    parsed = parsed or {s["id"]: Constraints(s) for s in order}
    uses = features(nota)
    bars: dict[str, set[int]] = {}
    note_bars: dict[str, set[int]] = {}           # bars where the skill's pitches or hands are used
    beyond = []
    for f, where in uses.items():
        sid = next((s["id"] for s in order if parsed[s["id"]].allows(f)), None)
        if sid is None:
            beyond.append(f)
        else:
            bars.setdefault(sid, set()).update(where)
            if f[0] in ("pitch", "hands"):
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
    return {
        "barNotes": {str(b): c for b, c in sorted(bar_notes.items())},
        "requiredSkills": required,
        "featuredSkills": featured,
        "mapPoint": max((seq[k] for k in required), default=None),
        "skillMeasures": {k: sorted(bars[k]) for k in required},
        "beyondMap": describe(sorted(beyond, key=str)),
    }
