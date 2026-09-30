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


# the real Prep A map's kinds of constraint (v0.24): letter-named notes, intervals, chords, held
# notes under the other hand, ties and rests
PREP_A = [
    {"id": "black", "sequence": 10, "constraints": {"letters": True, "hands": ["R", "L"], "durations": [1, 2, 4],
                                                   "pitches": {"R": ["C#4", "D#4"], "L": ["C#3", "D#3"]},
                                                   "timeSigs": ["4/4"], "keySigs": [0]}},
    {"id": "cde", "sequence": 20, "constraints": {"letters": True, "hands": ["R"], "range": {"R": ["C4", "E4"]}}},
    {"id": "landmarks", "sequence": 30, "constraints": {"hands": ["R", "L"], "pitches": {"R": ["C4", "G4"], "L": ["F3", "C4"]},
                                                       "intervals": [1, 5], "handsTogether": "held"}},
    {"id": "treble", "sequence": 40, "constraints": {"hands": ["R"], "range": {"R": ["C4", "G4"]}, "intervals": [2]}},
    {"id": "skips", "sequence": 50, "constraints": {"hands": ["R", "L"], "intervals": [3], "chords": True}},
    {"id": "tie", "sequence": 60, "constraints": {"ties": True}},
    {"id": "rest", "sequence": 70, "constraints": {"rests": True}},
]


def prep_a(n, letters=False):
    if letters:
        n["header"]["letters"] = True
    return analysis.analyze(n, PREP_A)


def test_letter_named_notes_need_only_the_pre_staff_skills():
    tune = [(0, 64, 1, "R"), (1, 62, 1, "R"), (2, 60, 2, "R"), (4, 61, 4, "R")]
    a = prep_a(nota(tune, bars=2), letters=True)
    assert a["requiredSkills"] == ["black", "cde"] and a["beyondMap"] == []
    # the same notes on the staff need the staff skills: middle C is a landmark, D and E are treble steps
    b = prep_a(nota(tune[:3] + [(4, 60, 4, "R")], bars=2))
    assert "cde" not in b["requiredSkills"] and {"landmarks", "treble"} <= set(b["requiredSkills"])


def test_black_key_pitches_are_not_a_range():
    a = prep_a(nota([(0, 62, 4, "R")], bars=1), letters=True)        # D4: between the two black keys
    assert a["requiredSkills"] == ["black", "cde"]
    a = prep_a(nota([(0, 62, 4, "L")], bars=1), letters=True)        # D3 is nobody's in the left hand
    assert "left hand D4" in a["beyondMap"]


def test_intervals_steps_and_skips():
    steps = prep_a(nota([(0, 60, 1, "R"), (1, 62, 1, "R"), (2, 64, 1, "R"), (3, 62, 1, "R")], bars=1))
    assert steps["requiredSkills"][-1] == "treble" and steps["beyondMap"] == []
    skip = prep_a(nota([(0, 60, 1, "R"), (1, 64, 1, "R"), (2, 67, 2, "R")], bars=1))
    assert skip["featuredSkills"][0] == "skips"
    fourth = prep_a(nota([(0, 60, 2, "R"), (2, 65, 2, "R")], bars=1))
    assert "right hand intervals of 4ths" in fourth["beyondMap"]


def test_spelled_notes_count_intervals_by_letter():
    n = nota([(0, 60, 2, "R"), (2, 64, 2, "R")], bars=1)            # C to E: a 3rd, however it is spelled
    n["notes"][1]["spelled"] = {"step": "F", "alter": -1, "octave": 4}
    assert "right hand intervals of 4ths" in prep_a(n)["beyondMap"]


def test_a_held_note_under_the_melody_is_not_hands_together():
    held = prep_a(nota([(0, 53, 4, "L"), (0, 67, 2, "R"), (2, 67, 2, "R")], bars=1))
    assert held["beyondMap"] == [] and "landmarks" in held["requiredSkills"]
    moving = prep_a(nota([(0, 53, 1, "L"), (0, 67, 1, "R")], bars=1))
    assert "hands together" in moving["beyondMap"]


def test_chords_ties_and_rests():
    chord = prep_a(nota([(0, 60, 2, "R"), (0, 64, 2, "R"), (2, 60, 2, "R")], bars=1))
    assert chord["featuredSkills"][0] == "skips"
    n = nota([(0, 60, 4, "R"), (4, 60, 4, "R")], bars=2)
    n["notes"][0]["tieToNext"] = True
    n["notes"][1]["tieFrom"] = 0
    assert prep_a(n)["featuredSkills"][0] == "tie"
    rest = prep_a(nota([(0, 60, 1, "R"), (2, 60, 2, "R")], bars=1))
    assert rest["featuredSkills"][0] == "rest" and rest["skillMeasures"]["rest"] == [1]
    trailing = prep_a(nota([(0, 60, 2, "R")], bars=1))                 # a half note, then silence to the bar's end
    assert "rest" in trailing["requiredSkills"]


def test_older_maps_ignore_the_new_kinds():
    # no skill names intervals or rests: a skip and a silence are not beyond the map
    a = run(nota([(0, 60, 1, "R"), (2, 67, 2, "R")], bars=1))
    assert a["beyondMap"] == []


def test_bad_prep_a_constraints_are_refused():
    with pytest.raises(ValueError):
        analysis.Constraints({"id": "x", "constraints": {"handsTogether": "sometimes"}})
    with pytest.raises(ValueError):
        analysis.Constraints({"id": "x", "constraints": {"intervals": [0]}})
    with pytest.raises(ValueError):
        analysis.Constraints({"id": "x", "constraints": {"pitches": {"X": ["C4"]}}})


def test_a_chord_counts_by_its_size():
    skills = [PREP_A[0], {**PREP_A[2], "constraints": {**PREP_A[2]["constraints"], "chords": [5]}}, PREP_A[3],
              {**PREP_A[4], "constraints": {**PREP_A[4]["constraints"], "chords": [3]}}]
    fifth = analysis.analyze(nota([(0, 60, 2, "R"), (0, 67, 2, "R")], bars=1), skills)      # C and G together
    assert fifth["requiredSkills"] == ["black", "landmarks"] and fifth["beyondMap"] == []
    third = analysis.analyze(nota([(0, 60, 2, "R"), (0, 64, 2, "R")], bars=1), skills)
    assert third["featuredSkills"][0] == "skips"
    fourth = analysis.analyze(nota([(0, 60, 2, "R"), (0, 65, 2, "R")], bars=1), skills)
    assert "two notes at once (4ths apart) in the right hand" in fourth["beyondMap"]


def test_an_idea_the_notes_cannot_show_is_practised_by_the_pieces_written_for_it():
    """v0.25: a skill with no constraints of its own (the measure, a dynamic mark) never gets
    credit from the notes; the pieces written for it require and feature it."""
    skills = [PREP_A[0], {"id": "measure", "sequence": 15, "constraints": {"position": {"R": "C4"}}}]
    n = nota([(0, 61, 1, "R"), (1, 63, 1, "R"), (2, 61, 1, "R"), (3, 63, 1, "R")], bars=1)
    n["header"]["letters"] = True
    plain = analysis.analyze(n, skills)
    assert plain["requiredSkills"] == ["black"]
    a = analysis.analyze(n, skills, written_for="measure")
    assert a["requiredSkills"] == ["black", "measure"] and a["featuredSkills"] == ["measure", "black"]
    assert a["mapPoint"] == 15 and a["skillMeasures"]["measure"] == [1]
    # a skill the notes can show gets no help: the analysis decides
    assert analysis.analyze(n, skills, written_for="black") == plain
