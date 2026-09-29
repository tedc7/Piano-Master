"""Finger-number generator v1 (arch §8.9)."""
from app import fingering
from app.analysis import midi


def nota(names, hand="R", fingers=None, beats=None):
    notes, t = [], 0.0
    for i, n in enumerate(names):
        chord = n.split("+")
        d = beats[i] if beats else 1.0
        for c in chord:
            note = {"pitch": midi(c), "start": t, "duration": d, "hand": hand}
            if fingers and fingers[i]:
                note["finger"] = fingers[i]
            notes.append(note)
        t += d
    return {"notes": notes}


def fingers(n):
    return [x["finger"] for x in sorted(n["notes"], key=lambda x: (x["start"], x["pitch"]))]


def test_c_position_uses_the_position_fingers():
    n = nota(["E4", "D4", "C4", "D4", "G4", "F4"])
    info = fingering.generate(n, {"R": "C4"})
    assert fingers(n) == [3, 2, 1, 2, 5, 4] and info["source"] == "generated"
    left = nota(["C3", "E3", "G3", "D3"], hand="L")
    fingering.generate(left, {"L": "C3"})
    assert fingers(left) == [5, 3, 1, 4]


def test_five_note_runs_without_a_position_fall_under_the_hand():
    n = nota(["C4", "D4", "E4", "F4", "G4", "F4", "E4", "D4", "C4"])
    fingering.generate(n)
    assert fingers(n) == [1, 2, 3, 4, 5, 4, 3, 2, 1]
    left = nota(["C3", "D3", "E3", "F3", "G3"], hand="L")
    fingering.generate(left)
    assert fingers(left) == [5, 4, 3, 2, 1]


def test_a_c_major_scale_passes_the_thumb_under():
    n = nota(["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"])
    fingering.generate(n)
    assert fingers(n) == [1, 2, 3, 1, 2, 3, 4, 5]
    down = nota(["C5", "B4", "A4", "G4", "F4", "E4", "D4", "C4"])
    fingering.generate(down)
    assert fingers(down) == [5, 4, 3, 2, 1, 3, 2, 1]
    left = nota(["C3", "D3", "E3", "F3", "G3", "A3", "B3", "C4"], hand="L")
    fingering.generate(left)
    assert fingers(left) == [5, 4, 3, 2, 1, 3, 2, 1]


def test_existing_fingers_are_kept_and_black_keys_avoid_the_thumb():
    n = nota(["C4", "D4", "E4", "F#4", "G4"], fingers=[None, None, 3, None, None])
    info = fingering.generate(n)
    f = fingers(n)
    assert f[2] == 3 and f[3] != 1 and info["source"] == "mixed"


def test_twinkle_agrees_with_its_printed_fingering():
    # the fingers printed in twinkle-twinkle.yaml: C=1, G=4, A=5, F=3, E=2 (D and C unmarked);
    # the test goal is 80% agreement with printed fingering (arch §8.9)
    names = "C4 C4 G4 G4 A4 A4 G4 F4 F4 E4 E4 D4 D4 C4".split()
    printed = [1, 1, 4, 4, 5, 5, 4, 3, 3, 2, 2, None, None, None]
    n = nota(names)
    fingering.generate(n)
    marked = [(a, b) for a, b in zip(fingers(n), printed) if b]
    assert sum(a == b for a, b in marked) / len(marked) >= 0.8, fingers(n)


def test_chords_go_up_the_hand_and_wide_ones_are_flagged():
    n = nota(["C4+E4+G4", "C4+F4+A4"])
    fingering.generate(n)
    f = fingers(n)
    assert f[:3] == sorted(f[:3]) and len(set(f[:3])) == 3
    wide = nota(["C3+E4"], hand="L")
    info = fingering.generate(wide)
    assert info["flagged"]
