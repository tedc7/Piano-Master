"""Song analysis (arch §6.8): required and featured skills, map point, skill measures, and what
is beyond the map."""
import pytest

from app import analysis

SKILLS = [
    {"id": "rh-c", "sequence": 10, "constraints": {"hands": ["R"], "range": {"R": ["C4", "G4"]}, "durations": [1, 2, 4],
                                                  "timeSigs": ["4/4"], "keySigs": [0]}},
    {"id": "lh-c", "sequence": 20, "constraints": {"hands": ["L"], "range": {"L": ["C3", "G3"]}, "durations": [1, 2, 4]}},
    {"id": "reach-a", "sequence": 30, "constraints": {"hands": ["R"], "range": {"R": ["C4", "A4"]}}},
    {"id": "turns", "sequence": 40, "constraints": {"hands": ["R", "L"], "range": {"R": ["C4", "G4"], "L": ["C3", "G3"]}}},
    {"id": "eighths", "sequence": 50, "constraints": {"durations": [0.5]}},
    {"id": "three-four", "sequence": 60, "constraints": {"timeSigs": ["3/4"]}},
    {"id": "together", "sequence": 70, "constraints": {"hands": ["R", "L"], "handsTogether": True}},
]


def nota(notes, bars=4, time="4/4", key=0):
    """notes: (start beat, pitch, duration, hand)."""
    bar = 4 if time == "4/4" else 3
    return {
        "header": {"timeSig": time, "keySig": key},
        "measures": [{"number": i + 1, "start": i * bar, "duration": bar} for i in range(bars)],
        "notes": [{"start": s, "pitch": p, "duration": d, "hand": h} for s, p, d, h in notes],
    }


def run(n):
    return analysis.analyze(n, SKILLS)


def test_note_names():
    assert [analysis.midi(x) for x in ("C4", "F#3", "Bb2", "E♭5", "B♯3")] == [60, 54, 46, 75, 60]
    assert analysis.name(61) == "C♯4"
    with pytest.raises(ValueError):
        analysis.midi("H2")


def test_a_c_position_tune_needs_only_the_first_skill():
    a = run(nota([(0, 64, 1, "R"), (1, 62, 1, "R"), (2, 60, 2, "R"), (4, 67, 4, "R")], bars=2))
    assert a["requiredSkills"] == ["rh-c"] and a["featuredSkills"] == ["rh-c"] and a["mapPoint"] == 10
    assert a["skillMeasures"] == {"rh-c": [1, 2]} and a["beyondMap"] == []


def test_one_high_note_makes_the_reach_the_newest_skill():
    a = run(nota([(0, 60, 1, "R"), (1, 69, 1, "R"), (4, 67, 4, "R")], bars=2))
    assert a["requiredSkills"] == ["rh-c", "reach-a"] and a["mapPoint"] == 30
    assert a["featuredSkills"] == ["reach-a", "rh-c"]          # C position is used in every bar too
    assert a["skillMeasures"]["reach-a"] == [1]


def test_hands_taking_turns_and_together():
    turns = run(nota([(0, 60, 4, "R"), (4, 48, 4, "L")], bars=2))
    assert "turns" in turns["requiredSkills"] and turns["featuredSkills"][0] == "turns" and "together" not in turns["requiredSkills"]
    both = run(nota([(0, 60, 4, "R"), (0, 48, 4, "L")], bars=1))
    assert both["featuredSkills"][0] == "together" and both["skillMeasures"]["together"] == [1]


def test_rhythms_and_meters_credit_their_skills_but_do_not_feature_old_ones():
    a = run(nota([(0, 60, 0.5, "R"), (0.5, 62, 0.5, "R"), (1, 64, 2, "R")], bars=1, time="3/4"))
    assert a["requiredSkills"] == ["rh-c", "eighths", "three-four"]
    # the newest is 3/4 time; the next newest, eighths, is only a note length, so it isn't featured
    assert a["featuredSkills"] == ["three-four"]


def test_what_no_skill_covers_is_beyond_the_map():
    a = run(nota([(0, 76, 1, "R"), (1, 36, 1, "L"), (2, 60, 1.5, "R")], bars=1, time="4/4", key=2))
    assert a["beyondMap"] == ["right hand E5", "left hand C2", "note lengths 1.5 beats", "key signature +2"]


def test_grace_notes_are_not_required():
    n = nota([(0, 60, 4, "R")], bars=1)
    n["notes"].append({"start": 0, "pitch": 77, "duration": 0.125, "hand": "R", "grace": True})
    a = run(n)
    assert a["beyondMap"] == [] and a["requiredSkills"] == ["rh-c"]


def test_bad_constraints_are_reported():
    with pytest.raises(ValueError):
        analysis.Constraints({"id": "x", "constraints": {"range": {"R": ["G4", "C4"]}}})
    with pytest.raises(ValueError):
        analysis.Constraints({"id": "x", "constraints": {"range": {"Q": ["C4", "G4"]}}})
