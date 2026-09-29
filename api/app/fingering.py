"""Finger-number generator, first version (arch §8.9).

1. Fingers already in the source are kept; generated numbers fill only the gaps.
2. Fixed position: when the piece's skill defines a hand position (`position: {R: C4}` is the
   five white keys up from C4), every note of that hand inside it gets its position finger
   (right hand C=1 to G=5, left hand C=5 to G=1).
3. Scales and arpeggios: standard fingering tables arrive with the drill generator (M6).
4. Everything else: for each hand, the finger sequence with the lowest total effort, found by
   dynamic programming over the notes. Effort is added for stretches beyond a comfortable span
   for the pair of fingers (more beyond a practical span), crossings other than thumb-under or a
   finger over the thumb in the direction of the melody, the thumb or fifth finger on a black
   key, the same finger on two different notes in a row, and hand-position changes (cheaper at
   rests and phrase ends).
5. Chords: fingers go up with the notes (down in the left hand), spread by the intervals; a
   chord wider than an octave is flagged.

Pure Python on the §5 notation, shared by the content build and (later) the drill generator and
the song import skill. The weights are a first version; the test goal is 80% agreement with the
printed fingering in public-domain editions that have it.
"""
from __future__ import annotations

from .analysis import midi

BLACK = {1, 3, 6, 8, 10}
WHITE_STEPS = [0, 2, 4, 5, 7, 9, 11]
# Spans in semitones from the lower-numbered finger's note up to the higher-numbered finger's
# note (the left hand mirrors it): practical, comfortable and relaxed limits after Parncutt et al.
# (1997). A negative span on a thumb pair is the thumb passing under; other fingers never cross.
#            MinPrac MinComf MinRel MaxRel MaxComf MaxPrac
SPANS = {(1, 2): (-5, -3, 1, 5, 8, 10), (1, 3): (-4, -2, 3, 7, 10, 12), (1, 4): (-3, -1, 5, 9, 12, 14),
         (1, 5): (-1, 1, 7, 10, 13, 15), (2, 3): (1, 1, 1, 2, 3, 5), (2, 4): (1, 1, 3, 4, 5, 7),
         (2, 5): (2, 2, 5, 6, 8, 10), (3, 4): (1, 1, 1, 2, 2, 4), (3, 5): (1, 1, 3, 4, 5, 7), (4, 5): (1, 1, 1, 2, 3, 5)}
FINGERS = (1, 2, 3, 4, 5)
SAME = 3.0          # the same finger moving to a different note (a hand shift)
# the thumb passing under going up is cheap (scales need it); a finger over the thumb coming down
# costs more than a shift, as beginner fingerings shift the hand rather than cross (tuned on the
# printed fingering in twinkle-twinkle.yaml and the standard C major scale)
UNDER, OVER = 1.0, 5.0


def white_index(p: int) -> int | None:
    """Position of a white key among white keys (C4 -> 28), None for a black key."""
    pc = p % 12
    return None if pc in BLACK else (p // 12) * 7 + WHITE_STEPS.index(pc)


def position_finger(p: int, base: int, hand: str) -> int | None:
    """The finger for `p` in the five-finger position starting on white key `base`."""
    wi, wb = white_index(p), white_index(base)
    if wi is None or wb is None or not 0 <= wi - wb <= 4:
        return None
    return wi - wb + 1 if hand == "R" else 5 - (wi - wb)


def span_cost(lo: int, hi: int, span: int, going_up: bool = True) -> float:
    """The effort of fingers lo < hi being `span` semitones apart (Parncutt's stretch, small-span
    and large-span rules; beyond the practical span it is very costly)."""
    min_p, min_c, min_r, max_r, max_c, max_p = SPANS[(lo, hi)]
    thumb = lo == 1
    cost = 0.0
    if thumb and span <= 0:
        # the thumb passing under, or a finger over the thumb: a small, fixed effort
        cost += UNDER if going_up else OVER
        if span < min_c:
            cost += (min_c - span) * 2
        return cost + (20 if span < min_p else 0)
    if span < min_r:
        cost += (min_r - span) * (2 if thumb else 1)
    if span > max_r:
        cost += (span - max_r) * (1 if thumb else 2)
    if span < min_c:
        cost += (min_c - span) * 2
    if span > max_c:
        cost += (span - max_c) * 2
    if span < min_p or span > max_p:
        cost += 20
    return cost


def step_cost(p1: int, f1: int, p2: int, f2: int, hand: str, rest: bool) -> float:
    """The effort of going from note p1 on finger f1 to p2 on f2."""
    cost = 0.0
    if f1 == f2:
        cost += SAME + abs(p2 - p1) * 0.5 if p1 != p2 else 0.0   # the same finger on a different note
    else:
        lo, hi = min(f1, f2), max(f1, f2)
        p_lo, p_hi = (p1, p2) if f1 < f2 else (p2, p1)
        span = p_hi - p_lo if hand == "R" else p_lo - p_hi
        cost += span_cost(lo, hi, span, going_up=(p2 > p1) == (hand == "R"))
        if f2 == 4:
            cost += 0.5                              # the weak fourth finger
    if p2 % 12 in BLACK and f2 in (1, 5):
        cost += 1.5
    if rest:
        cost *= 0.5                                  # a hand-position change is easier at a rest
    return cost


def chord_fingers(pitches: list[int], anchor: int, hand: str) -> list[int]:
    """Fingers for a chord (low to high) when its bottom note (right hand) or top note (left hand)
    takes finger `anchor`, spread by the intervals."""
    ps = sorted(pitches) if hand == "R" else sorted(pitches, reverse=True)
    out, f = [anchor], anchor
    for a, b in zip(ps, ps[1:]):
        gap = abs(b - a)
        f = min(5, f + (1 if gap <= 2 else 2 if gap <= 5 else 3))
        out.append(f)
    if len(set(out)) < len(out):                    # squeezed: use the next fingers in order
        out = list(range(anchor, anchor + len(out)))
        if out[-1] > 5:
            return []
    by_pitch = dict(zip(ps, out))
    return [by_pitch[p] for p in sorted(pitches)]


def plan_hand(events: list[dict], hand: str) -> list[list[int]]:
    """Lowest-effort fingers for one hand's events ({pitches, fixed, rest}); returns fingers per
    event, low to high pitch."""
    options: list[list[tuple[int, list[int]]]] = []
    for ev in events:
        ps = ev["pitches"]
        opts = []
        for anchor in FINGERS:
            fs = [anchor] if len(ps) == 1 else chord_fingers(ps, anchor, hand)
            if not fs:
                continue
            fixed = ev["fixed"]
            if any(fixed[i] is not None and fixed[i] != fs[i] for i in range(len(ps))):
                continue
            opts.append((anchor, fs))
        if not opts:                                # the source's fingers don't fit a pattern: keep them
            opts = [(ev["fixed"][0] or 1, [f or 1 for f in ev["fixed"]])]
        options.append(opts)
    if not events:
        return []

    def lead(ev, fs):                               # the note the hand moves from: melody side
        i = len(ev["pitches"]) - 1 if hand == "R" else 0
        return sorted(ev["pitches"])[i], fs[i]

    INF = float("inf")
    best = [[INF] * len(options[0]) for _ in options]
    back = [[0] * len(options[0]) for _ in options]
    for j, (_, fs) in enumerate(options[0]):
        best[0][j] = sum(2.0 for p, f in zip(sorted(events[0]["pitches"]), fs) if p % 12 in BLACK and f in (1, 5))
    for i in range(1, len(events)):
        best[i] = [INF] * len(options[i])
        back[i] = [0] * len(options[i])
        for j, (_, fs) in enumerate(options[i]):
            p2, f2 = lead(events[i], fs)
            for k, (_, gs) in enumerate(options[i - 1]):
                if best[i - 1][k] == INF:
                    continue
                p1, f1 = lead(events[i - 1], gs)
                c = best[i - 1][k] + step_cost(p1, f1, p2, f2, hand, events[i]["rest"])
                if c < best[i][j]:
                    best[i][j], back[i][j] = c, k
    j = min(range(len(options[-1])), key=lambda x: best[-1][x])
    out = []
    for i in range(len(events) - 1, -1, -1):
        out.append(options[i][j][1])
        j = back[i][j]
    return out[::-1]


def generate(nota: dict, position: dict[str, str] | None = None) -> dict:
    """Fill in missing finger numbers in place. Returns {source, generated, flagged}: source is
    imported (nothing added), generated (all added) or mixed."""
    notes = nota["notes"]
    had = sum(1 for n in notes if n.get("finger"))
    flagged = []
    for hand in ("R", "L"):
        mine = [i for i, n in enumerate(notes) if n["hand"] == hand and not n.get("tieFrom")]
        if not mine:
            continue
        base = midi(position[hand]) if position and position.get(hand) else None
        if base is not None and all(position_finger(notes[i]["pitch"], base, hand) for i in mine):
            for i in mine:
                notes[i].setdefault("finger", position_finger(notes[i]["pitch"], base, hand))
            continue
        # events: notes starting together (a chord), in time order; a tied-on note keeps its finger
        groups: dict[float, list[int]] = {}
        for i in mine:
            groups.setdefault(round(float(notes[i]["start"]), 4), []).append(i)
        events, idx, prev_end = [], [], None
        for start in sorted(groups):
            ids = sorted(groups[start], key=lambda i: notes[i]["pitch"])
            ps = [notes[i]["pitch"] for i in ids]
            if ps and max(ps) - min(ps) > 12:
                flagged.append(f"bar at beat {start:g}: {hand} chord wider than an octave")
            events.append({"pitches": ps, "fixed": [notes[i].get("finger") for i in ids],
                           "rest": prev_end is not None and start > prev_end + 1e-6})
            idx.append(ids)
            prev_end = max(float(notes[i]["start"]) + float(notes[i]["duration"]) for i in ids)
        for ids, fs in zip(idx, plan_hand(events, hand)):
            for i, f in zip(ids, fs):
                notes[i].setdefault("finger", f)
        # a note tied from the one before keeps that note's finger
    added = sum(1 for n in notes if n.get("finger")) - had
    return {"source": "imported" if added == 0 else "generated" if had == 0 else "mixed", "generated": added, "flagged": flagged}
