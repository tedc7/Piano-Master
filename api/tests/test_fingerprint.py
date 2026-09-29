"""Melody fingerprint (arch §10.8)."""
from app import drills, fingerprint
from app.analysis import midi

TWINKLE = "C4 C4 G4 G4 A4 A4 G4 F4 F4 E4 E4 D4 D4 C4".split()


def nota(names, shift=0, bars_of=4):
    ev = [(float(i), 1.0, midi(n) + shift, None) for i, n in enumerate(names)]
    return drills.notation({"R": ev})


def test_the_same_tune_in_another_key_is_the_same_song():
    a, b = fingerprint.fingerprint(nota(TWINKLE)), fingerprint.fingerprint(nota(TWINKLE, shift=7))
    assert fingerprint.similarity(a, b) == 1.0 and fingerprint.verdict(1.0) == "same song"


def test_an_excerpt_matches_and_a_different_tune_does_not():
    whole = fingerprint.fingerprint(nota(TWINKLE * 2))
    part = fingerprint.fingerprint(nota(TWINKLE[:10]))
    assert fingerprint.similarity(part, whole) == 1.0
    other = fingerprint.fingerprint(nota("E4 D4 C4 D4 E4 E4 E4 D4 D4 D4 E4 G4 G4".split()))
    assert fingerprint.verdict(fingerprint.similarity(other, whole)) is None


def test_the_melody_is_the_top_right_hand_note_and_ties_are_merged():
    n = drills.notation({"R": [(0.0, 1.0, 60, None), (0.0, 1.0, 64, None), (1.0, 1.0, 67, None)], "L": [(0.0, 2.0, 48, None)]})
    for x in n["notes"]:
        x.pop("isMelody", None)
    assert fingerprint.melody(n) == [64, 67]
    t = drills.notation({"R": [(0.0, 2.0, 60, None), (2.0, 2.0, 60, None), (4.0, 1.0, 62, None)]})
    t["notes"][0]["tieToNext"] = True
    assert fingerprint.melody(t) == [60, 62]
