"""Content build: skill-map validation, the ABC -> notation converter, and constraint checks."""
import build_content as bc
import notation as nt

ABC = """X:1
M:4/4
L:1/4
Q:1/4=100
K:C
!1!C D E F | G2 G2 | A A G2 | F4 |]
w: one two three four five six sev-en eight nine
"""


def skill(sid, seq, prereq=(), pieces=("p1", "p2", "p3"), placeholder=True):
    return {"id": sid, "name": sid, "sequence": seq, "track": "reading", "prerequisites": list(prereq), "pieces": list(pieces)}


def validate(skills, placeholder=True, pieces=("p1", "p2", "p3")):
    maps = [{"map": "basic", "level": "Prep A", "placeholder": placeholder, "skills": skills}]
    return bc.validate_skill_maps(maps, set(pieces))


def test_the_placeholder_map_is_valid():
    maps = bc.load_skill_maps()
    pieces = {p.stem for p in (bc.CONTENT / "pieces").glob("*.yaml")}
    _, errors, _ = bc.validate_skill_maps(maps, pieces)
    assert errors == []


def test_prerequisites_must_exist_and_come_earlier():
    _, errors, _ = validate([skill("placeholder.a", 20), skill("placeholder.b", 10, ["placeholder.a"]),
                             skill("placeholder.c", 30, ["placeholder.x"])])
    assert any("must have a lower sequence" in e for e in errors)
    assert any("placeholder.x does not exist" in e for e in errors)


def test_ids_and_sequences_are_unique_and_placeholders_are_marked():
    _, errors, _ = validate([skill("placeholder.a", 10), skill("placeholder.a", 10), skill("real.b", 20)])
    assert any("duplicate skill id" in e for e in errors)
    assert any("sequence 10 already used" in e for e in errors)
    assert any("must start with 'placeholder.'" in e for e in errors)


def test_fewer_than_three_core_pieces_is_an_error_only_on_a_real_map():
    an = {"p1": {"featuredSkills": ["placeholder.a"]}, "p2": {"featuredSkills": ["placeholder.a"]},
          "p3": {"featuredSkills": ["placeholder.a"]}}
    errors, warnings, featuring = bc.coverage([{"id": "placeholder.a", "placeholder": True}], an, {"p3": "library"})
    assert not errors and any("2 core piece" in w for w in warnings) and featuring["placeholder.a"] == ["p1", "p2", "p3"]
    errors, _, _ = bc.coverage([{"id": "real.a", "placeholder": False}], an, {"p3": "library"})
    assert any("at least 3" in e for e in errors)


def test_constraints_that_do_not_parse_are_errors():
    bad = {**skill("placeholder.a", 10), "constraints": {"range": {"R": ["C4", "Z9"]}}}
    _, errors, _ = validate([bad])
    assert any("constraints don't parse" in e for e in errors)


def test_abc_converts_with_fingers_lyrics_and_two_bar_phrases():
    nota, warnings = nt.build_notation(nt.parse_abc(ABC), phrase_bars=2)
    assert not warnings
    assert [n["pitch"] for n in nota["notes"]][:5] == [60, 62, 64, 65, 67]
    assert nota["notes"][0]["finger"] == 1
    assert [ly["text"] for ly in nota["lyrics"]][:3] == ["one", "two", "three"]
    assert [float(p) for p in nota["phrases"]] == [0.0, 8.0]
    assert nota["header"]["tempo"] == 100


def test_repeats_are_passes_not_verses_without_lyrics():
    nota, _ = nt.build_notation(nt.parse_abc("X:1\nM:4/4\nL:1/4\nQ:1/2=60\nK:C\n|: C D E F :| G4 |]\n"))
    assert [(p["verse"], p["pass"]) for p in nota["playbackOrder"]] == [(1, 1), (1, 2), (1, 1)]
    assert nota["header"]["tempo"] == 120          # a half-note beat: 60 halves = 120 quarters a minute


def test_a_tie_on_one_chord_note_ties_only_that_note():
    nota, _ = nt.build_notation(nt.parse_abc("X:1\nM:4/4\nL:1/4\nK:C\n[C-E]2 C2 |]\n"))
    tied = {n["pitch"]: bool(n.get("tieToNext")) for n in nota["notes"] if n["start"] == 0}
    assert tied == {60: True, 64: False}


def test_triplets_graces_hands_and_clef_changes():
    abc = """X:1
M:4/4
L:1/8
Q:1/4=90
K:C
%%score {RH LH}
V:RH clef=treble
V:LH clef=bass
[V:RH] (3CDE F2 {g}A2 "_L"B2 | c8 |]
[V:LH] C,8 | [K:clef=treble] c8 |]
"""
    nota, warnings = nt.build_notation(nt.parse_abc(abc))
    rh = [n for n in nota["notes"] if n["staff"] == 0]
    assert [float(n["duration"]) for n in rh[:3]] == [1 / 3] * 3 and rh[0]["tuplet"] == [3, 2]
    assert [n["pitch"] for n in nota["notes"] if n["hand"] == "L" and n["staff"] == 0] == [71]   # B4 by the left hand
    assert [(g["pitch"], float(g["start"])) for g in nota["graces"]] == [(79, 2.0)]
    assert all(n["pitch"] != 79 for n in nota["notes"])                                          # never scored
    assert nota["measures"][1]["clefs"] == {1: "treble"} and "clefs" not in nota["measures"][0]
