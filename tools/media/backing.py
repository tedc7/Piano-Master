"""Backing parts from a piece's own notation, in a genre style (arch §10.5 "Backing from notation").

Everything is laid out on the piece's playback order (repeats and verses unrolled), in quarter-note
beats from playback beat 0, so the stems line up with the Play screen's song clock by construction.
Sources of backing notes, in order of preference:
  - the score's own other voices: a hymn's alto, tenor and bass (`hymn-strings`, `hymn-organ`), a
    round's later entries (`round`);
  - chord symbols, or chords taken from the left hand, voiced in a style (`kids`, `pad`, `waltz`).
A style is a function piece -> [Part]; each Part is one General MIDI instrument on its own channel.
Prototype: feasibility/fluid-probe/backing.py (Canon in D's ensemble parts are still only there).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from common import nt

MAJOR = [0, 2, 4, 5, 7, 9, 11]
TRIADS = [(r, q) for r in range(12) for q in ((0, 4, 7), (0, 3, 7))]
SYMBOL_ROOT = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


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
    drum: bool = False   # on the General MIDI drum channel: `pitch` is the kit's instrument

    def describe(self) -> dict:
        return {"name": self.name, "program": self.program, "notes": len(self.notes)}


class StyleError(Exception):
    pass


# ------------------------------------------------------------------------------ notes and chords

def entries(nota: dict) -> list[tuple[float, dict]]:
    """(playback start beat, measure) in playback order."""
    return [(float(e["start"]), nota["measures"][e["measure"]]) for e in nt.unroll(nota)["entries"]]


def in_measure(start, m: dict) -> bool:
    return m["start"] - Fraction(1, 10000) <= start < m["start"] + m["duration"] - Fraction(1, 10000)


def voice(score: dict, order: list[dict], keep, vel: int = 70) -> list[Note]:
    """The notes of `score` for which keep(note) is true, laid out on `order` (a playback order over
    the same measures), ties merged into one long note."""
    tmp = {**score, "playbackOrder": order}
    out: list[Note] = []
    open_: dict[int, Note] = {}
    for t0, m in entries(tmp):
        for n in sorted((n for n in score["notes"] if keep(n) and in_measure(n["start"], m)), key=lambda n: n["start"]):
            beat = t0 + float(n["start"] - m["start"])
            held = open_.pop(n["pitch"], None)
            if held and abs(held.beat + held.dur - beat) < 1e-6:
                held.dur += float(n["duration"])
                note = held
            else:
                note = Note(beat, float(n["duration"]), int(n["pitch"]), vel)
                out.append(note)
            if n.get("tieToNext"):
                open_[n["pitch"]] = note
    return out


def melody(piece) -> list[Note]:
    return voice(piece.nota, piece.nota["playbackOrder"], lambda n: n.get("isMelody"))


def key_tonic(nota: dict) -> int:
    return (7 * nota["header"]["keySig"]) % 12


def symbol_triad(sym: str) -> tuple[int, tuple[int, ...]]:
    root = SYMBOL_ROOT[sym[0]] + (1 if sym[1:2] in ("#", "♯") else -1 if sym[1:2] in ("b", "♭") else 0)
    rest = sym[1:].lstrip("#♯b♭").split("/")[0]
    minor = rest.startswith("m") and not rest.startswith("maj")
    if rest.startswith("dim"):
        ivs = (0, 3, 6)
    elif rest.startswith("aug"):
        ivs = (0, 4, 8)
    else:
        ivs = (0, 3, 7) if minor else (0, 4, 7)
    return root % 12, ivs + ((10,) if "7" in rest and "maj" not in rest else ())


def triad_for(pcs: set[int], bass: int | None, tonic: int) -> tuple[int, tuple[int, ...]]:
    """The triad sharing most tones with `pcs`, preferring the bass as root; a lone bass note gets
    the key's diatonic triad on it."""
    if bass is not None and len(pcs) <= 1:
        deg = MAJOR.index((bass - tonic) % 12) if (bass - tonic) % 12 in MAJOR else 0
        third = (MAJOR[(deg + 2) % 7] - MAJOR[deg]) % 12
        return bass % 12, (0, third, 7)
    return max(TRIADS, key=lambda rq: (len({(rq[0] + i) % 12 for i in rq[1]} & pcs), bass is not None and rq[0] == bass % 12))


@dataclass
class Span:
    beat: float
    dur: float
    root: int            # pitch class
    ivs: tuple[int, ...]
    bass: int | None     # the written bass pitch, when it came from the left hand


def chords(nota: dict) -> list[Span]:
    """The harmony in playback order: from chord symbols (each in force until the next), else from
    the left hand, one chord per bar in 3/4 and 6/8 and per half bar in 4/4."""
    spans: list[Span] = []
    tonic = key_tonic(nota)
    syms = sorted(nota.get("chordSymbols") or [], key=lambda c: c["beat"])
    for t0, m in entries(nota):
        bar = float(m["duration"])
        if syms:
            here = [c for c in syms if in_measure(c["beat"], m)]
            before = [c for c in syms if c["beat"] < m["start"]]
            starts = ([(m["start"], before[-1]["symbol"])] if before and (not here or here[0]["beat"] > m["start"]) else []) + \
                     [(c["beat"], c["symbol"]) for c in here]
            for i, (b, sym) in enumerate(starts):
                end = starts[i + 1][0] if i + 1 < len(starts) else m["start"] + m["duration"]
                r, ivs = symbol_triad(sym)
                spans.append(Span(t0 + float(b - m["start"]), float(end - b), r, ivs, None))
            continue
        halves = 2 if nota["header"]["timeSig"] == "4/4" and bar >= 4 else 1
        step = bar / halves
        for h in range(halves):
            a, b = float(m["start"]) + h * step, float(m["start"]) + (h + 1) * step
            sounding = [n for n in nota["notes"] if n["hand"] == "L" and n["start"] < b - 1e-6 and n["start"] + n["duration"] > a + 1e-6]
            if not sounding:
                continue
            first = min(n["start"] for n in sounding)
            bass = min(n["pitch"] for n in sounding if n["start"] == first)
            r, ivs = triad_for({n["pitch"] % 12 for n in sounding}, bass, tonic)
            spans.append(Span(t0 + h * step, step, r, ivs, bass))
    return spans


def near(pc: int, lo: int) -> int:
    """The pitch of class `pc` at or above `lo`."""
    return lo + (pc - lo) % 12


def voicing(span: Span, lo: int, sevenths: bool = True) -> list[int]:
    root = near(span.root, lo)
    return [root + i for i in span.ivs if sevenths or i != 10]


def beats_of(nota: dict) -> tuple[float, list[float]]:
    """(bar length, the strong beats' offsets in the bar), in quarter notes."""
    num, den = (int(x) for x in nota["header"]["timeSig"].split("/"))
    bar = num * 4 / den
    if den == 8 and num % 3 == 0:
        return bar, [i * 1.5 for i in range(num // 3)]
    return bar, [float(i) * 4 / den for i in range(num)]


BASS_BEATS = {"4/4": [0.0, 2.0], "2/2": [0.0, 2.0], "3/4": [0.0], "2/4": [0.0], "6/8": [0.0, 1.5], "9/8": [0.0, 1.5, 3.0],
              "12/8": [0.0, 1.5, 3.0, 4.5]}


def bass_line(nota: dict, spans: list[Span], name: str, program: int, vel: int = 80, **kw) -> Part:
    """Roots on the bass beats, the fifth on a repeated chord's later beats."""
    bar, strong = beats_of(nota)
    beats = BASS_BEATS.get(nota["header"]["timeSig"], strong[:1])
    step = beats[1] - beats[0] if len(beats) > 1 else bar
    part = Part(name, program, **kw)
    for b, k in grid(nota, beats):
        s = span_at(spans, b)
        if s:
            root = near(s.root, 36)
            fresh = abs(s.beat - b) < 1e-6
            p = root if fresh or k % 2 == 0 else (root + 7 if root + 7 < 48 else root - 5)
            part.notes.append(Note(b, min(step, s.beat + s.dur - b) * 0.7, p, vel if fresh else vel - 10))
    return part


def grid(nota: dict, offsets: list[float]) -> list[tuple[float, int]]:
    """(playback beat, index in the bar) of each offset in every bar, in playback order. A short bar
    (a pickup) is the end of a full bar: its offsets count back from its bar line."""
    bar, _ = beats_of(nota)
    out = []
    first = nota["measures"][0]
    for t0, m in entries(nota):
        dur = float(m["duration"])
        start = t0 + dur - bar if m is first and dur < bar - 1e-6 else t0
        for k, o in enumerate(offsets):
            b = start + o
            if t0 - 1e-6 <= b < t0 + dur - 1e-6:
                out.append((b, k))
    return out


def span_at(spans: list[Span], beat: float) -> Span | None:
    return next((s for s in spans if s.beat - 1e-6 <= beat < s.beat + s.dur - 1e-6), None)


def clip_end(parts: list[Part], end: float) -> None:
    for p in parts:
        p.notes = [Note(n.beat, min(n.dur, end - n.beat), n.pitch, n.vel) for n in p.notes if n.beat < end - 1e-6]


# ------------------------------------------------------------------------------ styles

def kids(piece) -> list[Part]:
    """Children's songs: a soft string pad on the chords, a pizzicato bass on the strong beats (root,
    then the fifth), and a glockenspiel chiming chord tones between them (arch §10.5, "to test")."""
    nota = piece.nota
    pad = Part("Strings, soft pad", 48, volume=62, pan=76, reverb=60)
    glock = Part("Glockenspiel", 9, volume=58, pan=84, reverb=70)
    num = nota["header"]["timeSig"]
    # the chimes: between the strong beats (2 and 4 in 4/4; 2 and 3 in 3/4; the lilt of 6/8)
    chime = {"4/4": [1.0, 3.0], "3/4": [1.0, 2.0], "2/4": [1.0], "6/8": [1.0, 2.5], "2/2": [1.0, 3.0]}.get(num, [])
    spans = chords(nota)
    for s in spans:
        for p in voicing(s, 52, sevenths=False):
            pad.notes.append(Note(s.beat, s.dur, p, 50))
    bass = bass_line(nota, spans, "Pizzicato bass", 45, vel=84, volume=100, pan=56)
    for b, k in grid(nota, chime):
        s = span_at(spans, b)
        if s:
            glock.notes.append(Note(b, 0.5, voicing(s, 72, sevenths=False)[1 + k % 2], 46))
    return [pad, bass, glock]


def pad(piece) -> list[Part]:
    """A string pad on the chords with a cello on the roots (the probe's Ode to Joy)."""
    strings = Part("Strings pad", 48, volume=70)
    cello = Part("Cello (roots)", 42, volume=95)
    for s in chords(piece.nota):
        for p in voicing(s, 55):
            strings.notes.append(Note(s.beat, s.dur, p, 55))
        root = near(s.root, 36)
        cello.notes.append(Note(s.beat, min(2.0, s.dur), root, 72))
        if s.dur >= 4 - 1e-6:
            cello.notes.append(Note(s.beat + 2, 2.0, root + 7 if root + 7 < 50 else root - 5, 64))
    return [strings, cello]


def waltz(piece) -> list[Part]:
    """Basses on beat 1, horns and strings on beats 2 and 3 (the probe's Blue Danube)."""
    basses = Part("Basses, pizzicato (beat 1)", 45, volume=100)
    horns = Part("Horns (beats 2 and 3)", 60, volume=75, pan=48)
    strings = Part("Strings, sustained", 48, volume=60, pan=80)
    for s in chords(piece.nota):
        b = s.bass if s.bass is not None else near(s.root, 36)
        while b >= 48:
            b -= 12
        basses.notes.append(Note(s.beat, 0.8, b, 88))
        if s.dur >= 3 - 1e-6:
            for off in (1.0, 2.0):
                for p in voicing(s, 53):
                    horns.notes.append(Note(s.beat + off, 0.6, p, 62))
        for p in voicing(s, 57):
            strings.notes.append(Note(s.beat, s.dur, p, 52))
    return [basses, horns, strings]


def atb(piece) -> dict[str, list[Note]]:
    """A hymn's alto, tenor and bass from the full score (upper staff voice 2, lower staff voices 1
    and 2), on the child's playback order."""
    full, order = piece.full, piece.nota["playbackOrder"]
    if len(full["header"]["staves"]) < 2:
        raise StyleError("the hymn styles need the four-part score (alto, tenor and bass); this piece has one staff")
    parts = {"alto": (0, 2), "tenor": (1, 1), "bass": (1, 2)}
    out = {k: voice(full, order, lambda n, sv=sv: (n["staff"], n["voice"]) == sv) for k, sv in parts.items()}
    if not out["bass"]:                 # tenor and bass as chords in one voice: the lowest note is the bass
        low = voice(full, order, lambda n: n["staff"] == 1)
        out["bass"] = [n for n in low if n.pitch == min(m.pitch for m in low if abs(m.beat - n.beat) < 1e-6)]
        out["tenor"] = [n for n in low if n not in out["bass"]]
    return out


def hymn_strings(piece) -> list[Part]:
    """Strings on the alto and tenor, cello on the bass: chosen by listening for Amazing Grace (v0.22)."""
    v = atb(piece)
    strings = Part("Strings (alto, tenor)", 48, volume=85, pan=76)
    cello = Part("Cello (bass)", 42, volume=95, pan=52)
    strings.notes = [Note(n.beat, n.dur, n.pitch, 62) for k in ("alto", "tenor") for n in v[k]]
    cello.notes = [Note(n.beat, n.dur, n.pitch, 70) for n in v["bass"]]
    return [strings, cello]


def hymn_organ(piece) -> list[Part]:
    """Church organ on the alto, tenor and bass, with the bass an octave down on the pedal."""
    v = atb(piece)
    organ = Part("Church organ (alto, tenor, bass)", 19, volume=80, reverb=70)
    pedal = Part("Organ pedal (bass an octave down)", 19, volume=70, reverb=70)
    organ.notes = [Note(n.beat, n.dur, n.pitch, 64) for k in ("alto", "tenor", "bass") for n in v[k]]
    pedal.notes = [Note(n.beat, n.dur, n.pitch - 12, 60) for n in v["bass"]]
    return [organ, pedal]


def round_(piece) -> list[Part]:
    """A round: the melody again on a flute (an octave up) and a clarinet, entering `entryBars` bars
    behind the child (default 2 and 4), with a pizzicato bass on the chords. At the child's last bar
    every voice stops and holds the tonic chord."""
    nota = piece.nota
    bar, strong = beats_of(nota)
    entry = piece.spec.get("backing", {}).get("entryBars", [2, 4]) if isinstance(piece.spec.get("backing"), dict) else [2, 4]
    mel = melody(piece)
    last = float(nota["length"]) - float(nota["measures"][nota["playbackOrder"][-1]["measure"]]["duration"])
    kinds = [("Flute (round, an octave up)", 73, 12, 40), ("Clarinet (round)", 71, 0, 88)]
    parts = []
    for (name, program, shift, pan), bars in zip(kinds, entry):
        p = Part(f"{name}, {bars} bars behind", program, volume=78, pan=pan, reverb=55)
        p.notes = [Note(n.beat + bars * bar, n.dur, n.pitch + shift, 64) for n in mel]
        parts.append(p)
    clip_end(parts, last)
    tonic = key_tonic(nota)
    end_dur = float(nota["length"]) - last
    for p, iv in zip(parts, (4, 7)):                   # the third and fifth of the tonic chord
        p.notes.append(Note(last, end_dur, near(tonic + iv, 64 + (12 if "Flute" in p.name else 0)), 60))
    bass = bass_line(nota, chords(nota), "Pizzicato bass", 45, vel=80, volume=96, pan=64)
    return parts + [bass]


JINGLE_BELL = 83         # the General MIDI drum kit's jingle bell (sleigh bells)


def holiday(piece) -> list[Part]:
    """Christmas songs: warm strings on the chords, a harp breaking each chord upwards and back in
    eighth notes (quarter notes in a fast song), a cello on the roots, and light sleigh bells on the
    beat, louder on the bar's strong beats (arch §10.5 genre table). `backing: {style: holiday,
    bells: false}` leaves the bells out."""
    nota = piece.nota
    b = piece.spec.get("backing")
    bells = not (isinstance(b, dict) and b.get("bells") is False)
    strings = Part("Strings, warm", 48, volume=66, pan=72, reverb=65)
    harp = Part("Harp arpeggios", 46, volume=74, pan=40, reverb=60)
    cello = Part("Cello (roots)", 42, volume=88, pan=58)
    sleigh = Part("Sleigh bells", 0, volume=48, pan=88, reverb=40, drum=True)
    step = 0.5 if piece.bpm <= 132 else 1.0
    spans = chords(nota)
    for s in spans:
        for p in voicing(s, 55):
            strings.notes.append(Note(s.beat, s.dur, p, 48))
        root = near(s.root, 36)
        cello.notes.append(Note(s.beat, min(2.0, s.dur), root, 70))
        if s.dur >= 4 - 1e-6:
            cello.notes.append(Note(s.beat + 2, 2.0, root + 7 if root + 7 < 50 else root - 5, 62))
        tones = voicing(s, 60, sevenths=False)
        up = tones + [tones[0] + 12]
        cycle = up + up[-2:0:-1]                       # up and back: 1 3 5 8 5 3
        k, t = 0, 0.0
        while t < s.dur - 1e-6:
            harp.notes.append(Note(s.beat + t, min(step * 2, s.dur - t), cycle[k % len(cycle)], 50 if k % len(cycle) else 58))
            k, t = k + 1, t + step
    if bells:
        bar, strong = beats_of(nota)
        compound = nota["header"]["timeSig"].endswith("/8")
        beats = strong if compound else [float(i) for i in range(int(round(bar)))]   # every quarter, or 6/8's two beats
        for t, k in grid(nota, beats):
            sleigh.notes.append(Note(t, 0.25, JINGLE_BELL, 64 if k == 0 else 44))
    return [strings, harp, cello] + ([sleigh] if bells else [])


STYLES = {"kids": kids, "pad": pad, "holiday": holiday, "waltz": waltz, "hymn-strings": hymn_strings, "hymn-organ": hymn_organ, "round": round_}


def style_of(piece) -> str:
    """The piece's backing style: `media: {backing: STYLE}` or `{backing: {style: STYLE}}`, else the
    genre's default. A hymn without its four parts falls back to the chord pad."""
    b = piece.spec.get("backing")
    name = (b.get("style") if isinstance(b, dict) else b) or piece.genre[1]
    if name.startswith("hymn") and len(piece.full["header"]["staves"]) < 2:
        return "pad"
    return name


def parts_for(piece) -> tuple[str, list[Part]]:
    name = style_of(piece)
    if name == "yue2":
        return name, []
    if name not in STYLES:
        raise StyleError(f"unknown backing style {name!r} (known: {', '.join(STYLES)}, yue2)")
    parts = [p for p in STYLES[name](piece) if p.notes]
    if not parts:
        raise StyleError(f"style {name!r} found no backing notes (no chord symbols, left hand or other voices)")
    return name, parts
