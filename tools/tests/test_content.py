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


def test_fewer_than_three_pieces_is_an_error_only_on_a_real_map():
    _, errors, warnings = validate([skill("placeholder.a", 10, pieces=["p1"])])
    assert not errors and any("at least 3" in w for w in warnings)
    _, errors, _ = validate([skill("real.a", 10, pieces=["p1"])], placeholder=False)
    assert any("at least 3" in e for e in errors)


def test_abc_converts_with_fingers_lyrics_and_two_bar_phrases():
    nota, warnings = nt.build_notation(nt.parse_abc(ABC), phrase_bars=2)
    assert not warnings
    assert [n["pitch"] for n in nota["notes"]][:5] == [60, 62, 64, 65, 67]
    assert nota["notes"][0]["finger"] == 1
    assert [ly["text"] for ly in nota["lyrics"]][:3] == ["one", "two", "three"]
    assert [float(p) for p in nota["phrases"]] == [0.0, 8.0]
    assert nota["header"]["tempo"] == 100


def test_constraint_check_reports_notes_outside_the_skill():
    nota, _ = nt.build_notation(nt.parse_abc(ABC))
    s = {"id": "placeholder.a", "constraints": {"hands": ["R"], "range": {"R": ["C4", "G4"]}, "durations": [1, 2], "timeSigs": ["4/4"], "keySigs": [0]}}
    found = bc.check_constraints("p", nota, s)
    assert any("C4-A4 is outside C4-G4" in f for f in found)
    assert any("note lengths [4.0]" in f for f in found)
