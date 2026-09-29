"""Backing parts from a piece's own notation (the FluidSynth probe, arch §10.5 open question).

Three sources of backing, one per test piece:
- the score itself: Canon in D's other two violins are the right hand's variations delayed by one
  and two rounds of the ground bass (Pachelbel's canon), with a cello on the ground bass and a
  harpsichord continuo on the chords;
- the arrangement's left hand, orchestrated: the Blue Danube's oom-pah-pah as basses on beat 1 and
  horns and strings on beats 2 and 3;
- chord symbols: Ode to Joy's chords as a string pad and a cello bass.

Chords come from chord symbols when the piece has them, else from the left hand: one chord per bar
in 3/4, per half bar in 4/4 (the notes sounding in it; a single bass note gets the key's diatonic
triad on it). Everything is laid out in playback order (repeats unrolled), in beats, so the stems
line up with the Play screen's song clock by construction: no alignment step.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build_content as bc  # noqa: E402
import notation as nt  # noqa: E402

MAJOR = [0, 2, 4, 5, 7, 9, 11]
TRIADS = [(r, q) for r in range(12) for q in ((0, 4, 7), (0, 3, 7))]


@dataclass
class Note:
    beat: float          # playback beat
    dur: float
    pitch: int
    vel: int


@dataclass
class Part:
    name: str
    program: int         # General MIDI program (0-based)
    notes: list[Note] = field(default_factory=list)
    volume: int = 100    # CC7
    pan: int = 64        # CC10
    reverb: int = 50     # CC91


def load(pid: str, folder: Path = ROOT / "content" / "incoming" / "classical") -> tuple[dict, dict]:
    meta = yaml.safe_load((folder / f"{pid}.yaml").read_text())
    nota = nt.jsonable(bc.build_piece(pid, meta)[0])
    return meta, nota


def entries(nota: dict) -> list[tuple[float, dict]]:
    """(playback start beat, measure) in playback order."""
    out, t = [], 0.0
    for p in nota["playbackOrder"]:
        m = nota["measures"][p["measure"]]
        out.append((t, m))
        t += float(m["duration"])
    return out


def in_measure(n: dict, m: dict) -> bool:
    return m["start"] - 1e-6 <= n["start"] < m["start"] + m["duration"] - 1e-6


def played(nota: dict, hand: str) -> list[Note]:
    """One hand's notes in playback order (ties merged into one long note)."""
    out: list[Note] = []
    open_: dict[int, Note] = {}
    for t0, m in entries(nota):
        for n in sorted((n for n in nota["notes"] if n["hand"] == hand and in_measure(n, m)), key=lambda n: n["start"]):
            beat = t0 + float(n["start"]) - float(m["start"])
            held = open_.pop(n["pitch"], None)
            if held and abs(held.beat + held.dur - beat) < 1e-6:
                held.dur += float(n["duration"])
                note = held
            else:
                note = Note(beat, float(n["duration"]), int(n["pitch"]), 80)
                out.append(note)
            if n.get("tieToNext"):
                open_[n["pitch"]] = note
    return out


def key_tonic(nota: dict) -> int:
    return (7 * nota["header"]["keySig"]) % 12


def triad_for(pcs: set[int], bass: int | None, tonic: int) -> tuple[int, tuple[int, ...]]:
    """(root pitch class, intervals): the triad sharing most tones with `pcs`, preferring the bass
    as root; a lone bass note gets the key's diatonic triad on it."""
    if bass is not None and len(pcs) <= 1:
        deg = MAJOR.index((bass - tonic) % 12) if (bass - tonic) % 12 in MAJOR else 0
        third = (MAJOR[(deg + 2) % 7] - MAJOR[deg]) % 12
        return bass % 12, (0, third, 7)
    best = max(TRIADS, key=lambda rq: (len({(rq[0] + i) % 12 for i in rq[1]} & pcs), bass is not None and rq[0] == bass % 12))
    return best


SYMBOL_ROOT = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def symbol_triad(sym: str) -> tuple[int, tuple[int, ...]]:
    root = SYMBOL_ROOT[sym[0]] + (1 if sym[1:2] in ("#", "♯") else -1 if sym[1:2] in ("b", "♭") else 0)
    rest = sym[1:].lstrip("#♯b♭")
    minor = rest.startswith("m") and not rest.startswith("maj")
    return root % 12, ((0, 3, 7) if minor else (0, 4, 7)) + ((10,) if "7" in rest and "maj" not in rest else ())


@dataclass
class Span:
    beat: float
    dur: float
    root: int            # pitch class
    ivs: tuple[int, ...]
    bass: int | None     # the written bass pitch, when it came from the left hand


def chords(nota: dict) -> list[Span]:
    spans: list[Span] = []
    tonic = key_tonic(nota)
    syms = sorted(nota.get("chordSymbols") or [], key=lambda c: c["beat"])
    for t0, m in entries(nota):
        bar = float(m["duration"])
        if syms:
            # the chord in force at each chord change in the bar (written beats)
            here = [c for c in syms if in_measure({"start": c["beat"]}, m)]
            before = [c for c in syms if c["beat"] < m["start"] - 1e-6]
            starts = ([(m["start"], before[-1]["symbol"])] if before and (not here or here[0]["beat"] > m["start"] + 1e-6) else []) + \
                     [(c["beat"], c["symbol"]) for c in here]
            for i, (b, sym) in enumerate(starts):
                end = starts[i + 1][0] if i + 1 < len(starts) else m["start"] + bar
                r, ivs = symbol_triad(sym)
                spans.append(Span(t0 + b - m["start"], end - b, r, ivs, None))
            continue
        halves = 2 if nota["header"]["timeSig"] == "4/4" and bar >= 4 else 1
        step = bar / halves
        for h in range(halves):
            a, b = m["start"] + h * step, m["start"] + (h + 1) * step
            sounding = [n for n in nota["notes"] if n["hand"] == "L" and n["start"] < b - 1e-6 and n["start"] + n["duration"] > a + 1e-6]
            if not sounding:
                continue
            first = min(n["start"] for n in sounding)
            bass = min(n["pitch"] for n in sounding if abs(n["start"] - first) < 1e-6)
            r, ivs = triad_for({n["pitch"] % 12 for n in sounding}, bass, tonic)
            spans.append(Span(t0 + h * step, step, r, ivs, bass))
    return spans


def near(pc: int, lo: int) -> int:
    """The pitch of class `pc` at or above `lo`."""
    return lo + (pc - lo) % 12


def voicing(span: Span, lo: int) -> list[int]:
    root = near(span.root, lo)
    return [root + i for i in span.ivs]


# ------------------------------------------------------------------------------ the three pieces

def canon(nota: dict) -> list[Part]:
    rh, lh = played(nota, "R"), played(nota, "L")
    round_beats = 16.0                                  # one round of the ground bass: 4 bars
    end = nota["length"] - float(nota["measures"][-1]["duration"])   # the final chord bar
    v2 = Part("Violin 2 (one round behind)", 40, volume=90, pan=40)
    v3 = Part("Violin 3 (two rounds behind)", 40, volume=85, pan=88)
    for part, lag in ((v2, round_beats), (v3, 2 * round_beats)):
        for n in rh:
            b = n.beat + lag
            if b < end - 1e-6:
                part.notes.append(Note(b, min(n.dur, end - b), n.pitch, 70))
    cello = Part("Cello (ground bass)", 42, volume=100)
    cello.notes = [Note(n.beat, n.dur, n.pitch, 78) for n in lh]
    cont = Part("Harpsichord continuo", 6, volume=70, pan=70)
    for s in chords(nota):
        for p in voicing(s, 55):
            cont.notes.append(Note(s.beat, s.dur * 0.9, p, 60))
    # the last bar: everyone on the tonic chord
    last = nota["length"] - float(nota["measures"][-1]["duration"])
    for part, lo in ((v2, 66), (v3, 62)):
        part.notes.append(Note(last, 4.0, near(key_tonic(nota) + (4 if lo == 66 else 7), lo), 70))
    return [v2, v3, cello, cont]


def waltz(nota: dict) -> list[Part]:
    basses = Part("Basses, pizzicato (beat 1)", 45, volume=100)
    horns = Part("Horns (beats 2 and 3)", 60, volume=75, pan=48)
    strings = Part("Strings, sustained", 48, volume=60, pan=80)
    for s in chords(nota):
        bass = (s.bass if s.bass is not None else near(s.root, 36))
        while bass >= 48:
            bass -= 12
        basses.notes.append(Note(s.beat, 0.8, bass, 88))
        if s.dur >= 3 - 1e-6:
            for off in (1.0, 2.0):
                for p in voicing(s, 53):
                    horns.notes.append(Note(s.beat + off, 0.6, p, 62))
        for p in voicing(s, 57):
            strings.notes.append(Note(s.beat, s.dur, p, 52))
    return [basses, horns, strings]


def pad(nota: dict) -> list[Part]:
    strings = Part("Strings pad", 48, volume=70)
    cello = Part("Cello (roots)", 42, volume=95)
    for s in chords(nota):
        for p in voicing(s, 55):
            strings.notes.append(Note(s.beat, s.dur, p, 55))
        root = near(s.root, 36)
        cello.notes.append(Note(s.beat, min(2.0, s.dur), root, 72))
        if s.dur >= 4 - 1e-6:
            cello.notes.append(Note(s.beat + 2, 2.0, root + 7 if root + 7 < 50 else root - 5, 64))
    return [strings, cello]


PIECES = {"canon-in-d": canon, "blue-danube": waltz, "ode-to-joy": pad}
