"""The media skill's tools (arch §10.5), without the GPU: YuE2 inputs, backing parts, the FluidSynth
render, and how the content build and promote carry a piece's media."""
import json
import sys
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "media"))
import backing as bk  # noqa: E402
import build_content as bc  # noqa: E402
import common  # noqa: E402
import import_song as imp  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

SONG = {  # a 6/8 song with a pickup, two verses and chord symbols
    "title": "Test Song", "composer": "Trad.", "kind": "library", "genre": "kids", "level": "Level 1", "hands": "R",
    "phraseBars": 2,
    "abc": "X:1\nM:6/8\nL:1/8\nQ:3/8=60\nK:G\nD | \"G\"G2 G G2 A | B3 B2 z | \"D7\"A2 G A2 B | \"G\"G5 |]\n"
           "w: The it-sy bit-sy spi-der up the wa-ter spout.\nw: A lit-tle ti-ny ro-bin down the gar-den path.\n",
}
HYMN = {  # four parts; the child plays the melody
    "title": "Test Hymn", "composer": "Trad.", "kind": "library", "genre": "hymns", "level": "Level 1", "hands": "R",
    "play": "melody",
    "abc": "X:1\nM:4/4\nL:1/4\nQ:1/4=100\n%%score (S A) (T B)\nV:S clef=treble\nV:A clef=treble\nV:T clef=bass\nV:B clef=bass\nK:C\n"
           "[V:S] \"C\"G E E \"G\"D | \"C\"C4 |]\nw: Je-sus loves me so\n[V:A] E C C B, | C4 |]\n[V:T] G, G, G, G, | E,4 |]\n"
           "[V:B] C, C, C, G,, | C,4 |]\n",
}


def piece(tmp_path, meta, pid="t") -> common.Piece:
    f = tmp_path / f"{pid}.yaml"
    f.write_text(yaml.safe_dump(meta, sort_keys=False))
    return common.load(f)


def test_yue2_inputs_one_attack_per_syllable_after_the_lead_in(tmp_path):
    yue2 = pytest.importorskip("yue2")          # needs YuE2's own ABC parser (~/engines/yue2)
    p = piece(tmp_path, SONG)
    abc, lyrics, amap = yue2.export(p.nota)
    assert "K:G" in abc and "Q:1/4=90" in abc
    # the pickup bar is padded to a whole bar (2.5 beats of rest) and the "Oh" bar goes before it
    assert Fraction(amap["padBeats"]) == Fraction(3) + Fraction(5, 2)
    assert lyrics.startswith("[Verse]\nOh, The itsy bitsy") and lyrics.count("[Verse]") == 2
    assert len(amap["syllables"]) == 2 * 12 and amap["words"][0] == {"word": "Oh,", "beat": "0"}
    assert amap["syllables"][0]["beat"] == str(Fraction(amap["padBeats"]))       # "The", on playback beat 0


def test_kids_backing_follows_the_bar_lines_through_a_pickup(tmp_path):
    p = piece(tmp_path, SONG)
    name, parts = bk.parts_for(p)
    assert name == "kids" and [x.program for x in parts] == [48, 45, 9]
    bass = parts[1]
    # 6/8 after a half-beat pickup: bars start at 0.5, 3.5, 6.5 …; the bass plays on 1 and 4 of each bar
    assert [n.beat for n in bass.notes[:4]] == [0.5, 2.0, 3.5, 5.0]
    assert bass.notes[0].pitch % 12 == 7 and any(n.pitch % 12 == 2 for n in bass.notes)   # G, then D under D7
    assert max(n.beat for n in parts[0].notes) < float(p.nota["length"])


def test_hymn_backing_is_the_alto_tenor_and_bass(tmp_path):
    p = piece(tmp_path, HYMN)
    assert len(p.nota["header"]["staves"]) == 1 and len(p.full["header"]["staves"]) == 2     # the child plays one line
    name, (strings, cello) = bk.parts_for(p)
    assert name == "hymn-strings"
    assert sorted({n.pitch for n in cello.notes}) == [43, 48]                                   # G2, C3
    assert {n.pitch for n in strings.notes} == {64, 60, 59, 55, 52}                             # alto and tenor


def test_a_round_enters_behind_and_ends_on_the_tonic(tmp_path):
    p = piece(tmp_path, {**SONG, "media": {"backing": {"style": "round", "entryBars": [1]}}})
    name, parts = bk.parts_for(p)
    flute = parts[0]
    mel = bk.melody(p)
    assert name == "round" and flute.notes[0].beat == mel[0].beat + 3.0 and flute.notes[0].pitch == mel[0].pitch + 12
    end = float(p.nota["length"])
    assert all(n.beat + n.dur <= end + 1e-6 for n in flute.notes) and flute.notes[-1].pitch % 12 in (11, 2)


def test_a_piece_without_backing_notes_keeps_yue2s(tmp_path):
    import media
    bare = {**SONG, "abc": SONG["abc"].replace('"G"', "").replace('"D7"', "")}
    plan = media.plan_of(piece(tmp_path, bare))
    assert plan["vocal"] and plan["backing"] == "yue2"
    wordless = {**SONG, "abc": SONG["abc"].split("\nw:")[0] + "\n"}
    assert media.plan_of(piece(tmp_path, wordless))["vocal"] is False


def test_fluidsynth_renders_every_preset_on_the_beat(tmp_path):
    if not common.FLUIDSYNTH.exists() or not common.SOUNDFONT.exists():
        pytest.skip("tools/media/setup.sh not run")
    import synth
    p = piece(tmp_path, SONG)
    _, parts = bk.parts_for(p)
    rep = synth.render(parts, p.bpm, 1.0, tmp_path / "out", {"100": 1.0, "50": 0.5})
    assert rep["timing"]["pass"] and set(rep["presets"]) == {"100", "50"}
    # the 50% render is natively twice as long, not stretched (the release tails differ a little)
    notated = (float(p.nota["length"]) + 1.0) * 60 / p.bpm
    assert abs(rep["presets"]["50"]["seconds"] - rep["presets"]["100"]["seconds"] - notated) < 1.0


def write_media(folder: Path, beats: float) -> None:
    folder.mkdir(parents=True)
    presets = {}
    for k, r in common.PRESETS.items():
        (folder / f"accompaniment_{k}.mp3").write_bytes(b"x" * 10)
        presets[k] = {"ratio": r, "accompaniment": f"accompaniment_{k}.mp3"}
    (folder / "media.json").write_text(json.dumps({"engine": "FluidSynth", "take": "kids", "padBeats": 1.0, "bpm": 90,
                                                   "beats": beats, "presets": presets}))


def test_the_build_carries_media_and_refuses_stale_media(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "MEDIA", tmp_path / "client-media")
    nota, _, _ = bc.build_piece("t", {**SONG, "_noMedia": True})
    write_media(tmp_path / "media" / "t", float(nota["length"]))
    _, media, _ = bc.build_piece("t", SONG, tmp_path / "media")
    assert media["presets"]["50"]["accompaniment"]["url"] == "media/t/accompaniment_50.mp3"
    assert "vocals" not in media["presets"]["50"] and (tmp_path / "client-media" / "t" / "accompaniment_50.mp3").exists()
    shorter = {**SONG, "abc": SONG["abc"].replace("w: A lit-tle ti-ny ro-bin down the gar-den path.\n", "")}
    with pytest.raises(bc.ContentError, match="re-run the media skill"):
        bc.build_piece("t", shorter, tmp_path / "media")
    faster = {**SONG, "abc": SONG["abc"].replace("Q:3/8=60", "Q:3/8=84")}
    with pytest.raises(bc.ContentError, match="re-run the media skill"):
        bc.build_piece("t", faster, tmp_path / "media")


def test_promote_moves_a_pieces_media_with_it(tmp_path, monkeypatch):
    import shutil
    c = tmp_path / "content"
    shutil.copytree(ROOT / "content" / "pieces", c / "pieces")
    monkeypatch.setattr(imp, "CONTENT", c)
    monkeypatch.setattr(imp, "DELETED", c / "deleted.yaml")
    monkeypatch.setattr(bc, "MEDIA", tmp_path / "client-media")
    b = c / "incoming" / "b"
    b.mkdir(parents=True)
    meta = {**SONG, "source": {"site": "test", "url": "https://example.org"}, "license": {"composition": "public-domain", "edition": "public-domain"}}
    (b / "t.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
    nota, _, _ = bc.build_piece("t", {**SONG, "_noMedia": True})
    write_media(b / "media" / "t", float(nota["length"]))
    assert imp.main(["promote", str(b), "t"]) == 0
    assert (c / "media" / "t" / "media.json").exists() and not (b / "media" / "t").exists()


def test_submit_packages_each_piece_with_its_stems_and_what_the_parent_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "MEDIA", tmp_path / "client-media")
    b = tmp_path / "batch"
    b.mkdir()
    meta = {**SONG, "tempoSource": "a recording at 60", "source": {"site": "test", "url": "https://example.org", "id": "x1"},
            "license": {"composition": "public-domain", "edition": "public-domain"}}
    (b / "t.yaml").write_text("# A test song, retyped.\n" + yaml.safe_dump(meta, sort_keys=False))
    nota, _, _ = bc.build_piece("t", {**SONG, "_noMedia": True})
    write_media(b / "media" / "t", float(nota["length"]))
    items, problems = imp.package_items(b, [])
    assert problems == [] and len(items) == 1
    it = items[0]
    assert it["piece"]["id"] == "t" and it["piece"]["media"]["presets"]["100"]["accompaniment"]["url"] == "media/t/accompaniment_100.mp3"
    assert set(it["files"]) == {f"accompaniment_{k}.mp3" for k in common.PRESETS} and all(f.exists() for f in it["files"].values())
    assert it["info"]["tempoSource"] == "a recording at 60" and it["info"]["notes"] == ["A test song, retyped."]
    assert it["info"]["lyrics"].startswith("1. The itsy bitsy spider") and "\n2. A little tiny robin" in it["info"]["lyrics"]
