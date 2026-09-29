"""The drill generator (arch §6.6, §8.9)."""
from app import drills
from app.analysis import midi

PASSED = [{"id": "a", "sequence": 10, "constraints": {"hands": ["R"], "range": {"R": ["C4", "G4"]}, "durations": [1, 2, 4],
                                                     "timeSigs": ["4/4"], "keySigs": [0]}},
          {"id": "b", "sequence": 20, "constraints": {"hands": ["L"], "range": {"L": ["C3", "G3"]}, "durations": [1, 2],
                                                     "timeSigs": ["4/4"], "keySigs": [0]}}]


def bars_ok(nota):
    """Every bar is full and no note crosses a bar line."""
    bar = nota["header"]["barLength"]
    for n in nota["notes"]:
        start, end = n["start"], n["start"] + n["duration"]
        assert int(start // bar) == int((end - 1e-6) // bar), n
    return nota["length"] == len(nota["measures"]) * bar


def test_material_merges_the_passed_skills():
    m = drills.Material.from_skills(PASSED)
    assert m.range_for("R") == (60, 67) and m.range_for("L") == (48, 55)
    assert m.pitches("R") == [60, 62, 64, 65, 67]


def test_a_reading_drill_keeps_returning_to_the_confused_note_in_reach():
    m = drills.Material.from_skills(PASSED)
    title, nota = drills.reading(midi("F3"), midi("G3"), "L", m, seed=3)
    ps = [n["pitch"] for n in nota["notes"]]
    assert ps.count(midi("F3")) >= len(ps) // 2 and midi("G3") in ps
    assert all(48 <= p <= 55 for p in ps), "only notes the passed skills allow"
    assert nota["header"]["staves"] == ["bass"] and all(n["finger"] for n in nota["notes"])
    assert "F and G" in title and bars_ok(nota)


def test_a_rhythm_drill_repeats_the_figure_on_one_key():
    m = drills.Material.from_skills(PASSED)
    title, nota, pitch = drills.rhythm("eighths", "R", m)
    durs = [n["duration"] for n in nota["notes"]]
    assert set(n["pitch"] for n in nota["notes"]) == {pitch} and durs.count(0.5) == 16 and bars_ok(nota)
    _, trip, _ = drills.rhythm("triplet", "R", m)
    assert any(n.get("tuplet") == [3, 2] for n in trip["notes"]) and bars_ok(trip)
    _, rest, _ = drills.rhythm("after-rest", "R", m)
    assert [n["start"] for n in rest["notes"]][:2] == [1.0, 3.0]


def test_scales_arpeggios_and_positions_use_the_standard_fingers():
    title, nota = drills.scale(midi("G3"), "major", "L")
    assert [n["finger"] for n in nota["notes"]][:8] == [5, 4, 3, 2, 1, 3, 2, 1]
    assert nota["header"]["keySig"] == 1 and nota["notes"][6]["spelled"] == {"step": "F", "alter": 1, "octave": 4}
    assert bars_ok(nota) and title == "G major scale, left hand"
    _, ar = drills.arpeggio(midi("A3"), "minor", "R")
    assert [n["pitch"] for n in ar["notes"]][:4] == [57, 60, 64, 69] and [n["finger"] for n in ar["notes"]][:4] == [1, 2, 3, 5]
    assert drills.arpeggio(midi("E-3"), "major", "R") is None
    _, ff = drills.five_finger(midi("C3"), "L")
    assert [n["finger"] for n in ff["notes"]] == [5, 4, 3, 2, 1, 2, 3, 4, 5] and bars_ok(ff)
