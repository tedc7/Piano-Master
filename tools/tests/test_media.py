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


def test_yue2_lyrics_sing_each_note_of_a_vowel_run_and_never_break_inside_a_word(tmp_path):
    yue2 = pytest.importorskip("yue2")
    # "Glo-o-o-ri-a" over a phrase line (phrases of 1 bar: bar 2 starts inside the word)
    run = {**SONG, "phraseBars": 1, "abc": "X:1\nM:4/4\nL:1/4\nQ:1/4=90\nK:C\n"
           "\"C\"c d c B | A B c2 | \"G\"B A G2 |]\nw: Glo- o- o- o- o- o- ri- a, in ex- cel- sis\n"}
    p = piece(tmp_path, run)
    _, lyrics, amap = yue2.export(p.nota)
    lines = lyrics.splitlines()
    assert "Glo-o-o-o-o-oria," in lines[1]                            # every note of the run, in one word
    assert not any(line.startswith(("o", "ria")) for line in lines)   # no line starts inside a word
    assert [w["word"] for w in amap["words"]][1] == "Glooooooria,"    # the aligner's word, as before
    _, plain, _ = yue2.export(piece(tmp_path, SONG, pid="u").nota)
    assert "itsy bitsy" in plain                                      # other words join as before


def test_yue2_lyrics_keep_a_sung_ed_on_its_own_note(tmp_path):
    yue2 = pytest.importorskip("yue2")
    # The First Noel's "look-ed": joined as "looked", YuE2 sang one note and ran a syllable early
    old = {**SONG, "abc": "X:1\nM:4/4\nL:1/4\nQ:1/4=90\nK:C\n"
           "\"C\"E C E G | c B A G | \"G\"F E D2 |]\nw: They look- ed up and saw a star, want- ed to fol- low\n"}
    _, lyrics, amap = yue2.export(piece(tmp_path, old).nota)
    assert "They look-ed up" in lyrics and "wanted" in lyrics        # "want-ed" is two syllables anyway
    assert [w["word"] for w in amap["words"]][2] == "looked"          # the aligner's word stays plain


def test_a_songs_own_oh_stays_on_its_note(tmp_path):
    yue2 = pytest.importorskip("yue2")
    # When the Saints starts with its own "Oh,": leaving it out with the lead-in's paired every
    # later word with the beat of the one before
    saints = {**SONG, "abc": "X:1\nM:4/4\nL:1/4\nQ:1/4=100\nK:C\n"
              "\"C\"C2 E F | G4 | C2 E F | \"G7\"G4 |]\nw: Oh, when the saints, oh, when the saints\n"}
    _, lyrics, amap = yue2.export(piece(tmp_path, saints).nota)
    assert lyrics.splitlines()[1].startswith("Oh, Oh, when")           # the lead-in, then the song's own
    words = amap["words"]
    assert [w["word"] for w in words] == ["Oh,", "Oh,", "when", "the", "saints,", "oh,", "when", "the", "saints"]
    pad = Fraction(amap["padBeats"])
    assert [Fraction(w["beat"]) - pad for w in words[1:4]] == [0, 2, 3]   # each word on its own note


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


def test_holiday_backing_is_strings_harp_cello_and_sleigh_bells_on_the_drum_channel(tmp_path):
    p = piece(tmp_path, {**SONG, "genre": "christmas"})
    name, parts = bk.parts_for(p)
    assert name == "holiday" and [x.name for x in parts] == ["Strings, warm", "Harp arpeggios", "Cello (roots)", "Sleigh bells"]
    bells, harp = parts[3], parts[1]
    # 6/8 after the pickup: the bells ring on the two dotted-quarter beats, louder on the first
    assert bells.drum and [n.beat for n in bells.notes[:3]] == [0.5, 2.0, 3.5] and bells.notes[0].vel > bells.notes[1].vel
    assert {n.pitch for n in bells.notes} == {bk.JINGLE_BELL}
    # the harp breaks the G chord upwards first: G, B, D, then G an octave up
    assert [n.pitch % 12 for n in harp.notes[:4]] == [7, 11, 2, 7]
    # the bells go on MIDI channel 10 (index 9); the other parts never do
    import mido
    import synth
    out = tmp_path / "b.mid"
    synth.midi(parts, 100, out, 1.0)
    chans = [{m.channel for m in t if hasattr(m, "channel")} for t in mido.MidiFile(str(out)).tracks[1:]]
    assert chans[3] == {9} and all(9 not in c for c in chans[:3])
    off = piece(tmp_path, {**SONG, "genre": "christmas", "media": {"backing": {"style": "holiday", "bells": False}}}, pid="u")
    assert [x.name for x in bk.parts_for(off)[1]][-1] == "Cello (roots)"


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


def take(words_off, stretches=(), heard=None):
    """A take's alignment as verdict() reads it: on pitch and on the beat, only its words vary."""
    return {"phrases": [{"medianMs": 8.0}], "pitch": {"share": 1.0}, "firstWordSung": True, "melodyStretches": [],
            "words": {"shareOver300ms": words_off, "stretches": list(stretches), "firstStretchS": None},
            "tuningCents": 1.0, "bleed": {"db": -35.0}, "octaveJumps": [], "songStartS": 2.0,
            **({"heard": {"heard": "…", "share": heard}} if heard is not None else {})}


def test_whisper_hearing_the_words_clears_the_aligners_scattered_misses_but_not_a_drift():
    align = pytest.importorskip("align")
    # Mary Had a Little Lamb: 30% "off", single words the aligner couldn't place, every word heard
    assert not align.verdict(take(0.30))["pass"]
    assert align.verdict(take(0.30, heard=1.0))["pass"]
    # The First Noel's verse 2: a syllable behind for seconds is a drift, however clearly it's sung
    drift = take(0.30, ["the (62.7 s) .. Noel, (91.4 s)"], heard=0.98)
    assert not align.verdict(drift)["pass"]
    # a take Whisper can't make out fails even when the aligner placed its words, and a take it half
    # hears is flagged for the listen
    v = align.verdict(take(0.05, heard=0.6))
    assert not v["pass"] and any("Whisper heard 60%" in x for x in v["reasons"])
    assert any("Whisper heard 80%" in x for x in align.verdict(take(0.05, heard=0.8))["flags"])
    # and between takes, the one Whisper hears better wins
    a, b = take(0.2, heard=1.0), take(0.15, heard=0.8)
    for r in (a, b):
        r["checks"] = align.verdict(r)
    assert align.score(a) > align.score(b)


def test_a_vocal_ends_with_the_song():
    media = pytest.importorskip("media")
    import numpy as np
    sr = 1000
    y = np.ones((10 * sr, 2))                       # a take still singing at 10 s; the song ends at 5 s
    out = media.song_only(y, sr, 5.0)
    assert len(out) == len(y)                        # the length stays, so the presets line up
    assert out[int(5.5 * sr)].tolist() == [1.0, 1.0]                 # the last note's release is kept
    assert 0 < out[int(5.8 * sr), 0] < 1                             # then faded
    assert not out[int(6.1 * sr):].any() and y.all()                 # then silent; the take untouched


def test_a_wrong_letter_name_fails_the_heard_check():
    align = pytest.importorskip("align")
    # B and C and Bunny Hops, sent back: Whisper had heard "E and G" for "C and G", "to E" for "to D"
    words = "B and C are neighbors, C and G say hi! step down, step up, home.".split()
    assert align.wrong_letters(words, "B and C our neighbors, E and G say hi Step down, step up home") == [("C", "E")]
    assert align.wrong_letters(words, "BNC our neighbors, phi and g, say hi Step down, step up home") == []
    assert align.wrong_letters("Middle C, march with me".split(), "Oh, middle sea, march with me") == []
    r = take(0.05, heard=0.95)
    r["heard"]["wrongLetters"] = [("C", "E")]
    v = align.verdict(r)
    assert not v["pass"] and any("E for C" in x for x in v["reasons"])


def test_a_tune_shared_between_the_hands_is_sung_as_one_line(tmp_path):
    yue2 = pytest.importorskip("yue2")
    # Twinkle Twinkle: the left hand's G3s sit just under the singing range; moved hand by hand, only
    # they went up an octave and the vocal leapt every time the tune changed hands
    shared = {**SONG, "abc": "X:1\nM:4/4\nL:1/4\nQ:1/4=100\n%%score {RH LH}\nK:C\nV:RH clef=treble\nV:LH clef=bass\n"
              "[V:RH] z2 D D | E E D2 |]\nw: twin-kle lit-tle star,\n[V:LH] G, G, z2 | z4 |]\nw: Twin-kle,\n"}
    p = piece(tmp_path, shared)
    sung = lambda amap: [s["pitch"] for s in amap["syllables"]]
    assert sung(yue2.export(p.nota)[2])[:3] == [67, 67, 62]                    # hand by hand: G4 down to D4
    assert sung(yue2.export(p.nota, line="as-written")[2]) == [67, 67, 74, 74, 76, 76, 74]   # G4 up to D5, as written


def test_words_off_on_the_last_word_fail_a_take():
    align = pytest.importorskip("align")
    # Middle C Stomp, sent back "great until the last 3 words": a short stretch at the end was only flagged
    r = take(0.25, ["stomp (18.8 s) .. home! (20.0 s)"], heard=1.0)
    assert align.verdict(r)["pass"]                                   # without the last word's time: as before
    r["lastWordS"] = 20.0
    v = align.verdict(r)
    assert not v["pass"] and any("at the end" in x for x in v["reasons"])
    r["words"]["stretches"] = ["high, (13.8 s) .. roar! (15.0 s)"]  # a short stretch earlier: still a flag
    assert align.verdict(r)["pass"]


def test_a_take_with_most_words_off_is_not_chosen_for_failing_fewer_checks():
    import media
    take = lambda off, failed, score, heard=0.9: {"words": {"shareOver300ms": off}, "score": score, "heard": {"share": heard},
                                                  "checks": {"pass": False, **{f"c{i}": False for i in range(failed)}}}
    drifted, close = take(0.82, 1, -0.02, 0.927), take(0.10, 2, 0.89)
    assert max([drifted, close], key=media.rank) is close
    # the aligner lost in repeated syllables, Whisper hearing every word: usable, and fewer failures win
    lost, off_pitch = take(0.42, 1, 0.41, 0.99), take(0.24, 4, 0.40)
    assert max([lost, off_pitch], key=media.rank) is lost
    # among takes the parent could hear, fewer failed checks still come first
    assert max([take(0.10, 2, 0.9), take(0.12, 1, 0.5)], key=media.rank)["score"] == 0.5


def test_the_words_heard_in_the_song_are_counted_like_the_lyric():
    # v0.40 (Oct 22, 2026): a take that sings words again inside the song fails; Whisper's digits and
    # its sign-offs on silence don't count
    import align
    assert align.words_in("Bun-ny, bun-ny, in the gar-den") == 5 and align.words_in("fa-la-la-la, it's 3") == 3
    assert align.heard_share(["three", "black", "keys"], "3 black keys") == 1.0
    assert align.SIGN_OFF.sub("", "hopping home in time for dinner. Thanks for watching!").strip() == "hopping home in time for dinner"
    base = {"phrases": [], "words": {"shareOver300ms": 0.0, "stretches": []}, "pitch": {"share": 1.0}, "firstWordSung": True,
            "melodyStretches": [], "tuningCents": 0, "bleed": {"db": -40}, "songStartS": 0}
    ok = align.verdict({**base, "songHeard": {"heard": "x", "share": 1.0, "extra": 1, "words": 14}})
    twice = align.verdict({**base, "songHeard": {"heard": "float up and rest, float up and rest", "share": 1.0, "extra": 4, "words": 14}})
    garbled = align.verdict({**base, "songHeard": {"heard": "thank you", "share": 0.2, "extra": -12, "words": 14}})
    assert ok["inSong"] and not twice["inSong"] and "more words than the song has" in twice["reasons"][0]
    assert not garbled["inSong"] and "Whisper heard 20%" in garbled["reasons"][0]


def test_a_take_far_over_on_bleed_ranks_below_one_just_over():
    # Oct 23, 2026: both fail on bleed alone; the score had chosen the one with the backing plainly heard
    import media
    def take(score, db):
        checks = {"timing": True, "pitch": True, "bleed": False, "pass": False}
        return {"checks": checks, "words": {"shareOver300ms": 0.07}, "heard": {"share": 1.0}, "bleed": {"db": db}, "score": score}
    loud, slight = take(0.79, -12.0), take(0.70, -23.0)
    assert max([loud, slight], key=media.rank) is slight


# ------------------------------------------------------------------------------ melismas (v0.50)

MELISMA = {  # "night" over two notes (G then A), "all" over three (E, D, C)
    "title": "Test Melisma", "composer": "Trad.", "kind": "library", "genre": "kids", "level": "Level 1", "hands": "R",
    "phraseBars": 2,
    "abc": "X:1\nM:4/4\nL:1/4\nQ:1/4=60\nK:C\nC E (GA) | (E D C) z |]\nw: Si-lent night_ all__\n",
}


def tone(midi_at, seconds: float, sr: int):
    """A sung-like tone: five harmonics, a little vibrato, its pitch from midi_at(t)."""
    import numpy as np
    t = np.arange(int(seconds * sr)) / sr
    f0 = 440 * 2 ** ((np.array([midi_at(x) for x in t]) - 69) / 12) * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * t))
    ph = 2 * np.pi * np.cumsum(f0) / sr
    return 0.2 * sum(np.sin(k * ph) / k for k in range(1, 6))


def test_melismas_are_found_with_their_notes(tmp_path):
    import melisma
    p = piece(tmp_path, MELISMA)
    found = melisma.melismas(p)
    assert [[n["pitch"] for n in m["notes"]] for m in found] == [[67, 69], [64, 62, 60]]
    assert [m["notes"][0]["lyric"]["text"] for m in found] == ["night", "all"]
    assert found[0]["seconds"] == [1.0, 1.0]                    # quarter notes at 60
    assert melisma.method(p) == "bend"
    with pytest.raises(ValueError):
        melisma.method(piece(tmp_path, {**MELISMA, "media": {"melisma": "split"}}, "u"))


def test_a_held_melisma_is_bent_onto_its_notes_and_the_rest_is_left_alone(tmp_path):
    import numpy as np
    import melisma
    p = piece(tmp_path, MELISMA)
    found = melisma.melismas(p)
    sr = melisma.SR
    at = melisma.stem_time(p, 0.0)
    # the take as YuE2 sings it: one pitch per syllable (C E G G | E E E), then silence
    held = [(0, 60), (1, 64), (2, 67), (3, 67), (4, 64), (5, 64), (6, 64)]
    y = tone(lambda t: next(m for s, m in reversed(held) if t >= s), 7.0, sr)
    for gap in (1, 2, 4):                                     # a consonant before each new syllable
        y[int((gap - 0.04) * sr):int((gap + 0.02) * sr)] = 0
    y[int(6.95 * sr):] = 0
    stereo = np.stack([y, 0.9 * y], axis=1)
    out, rep = melisma.bend(stereo, sr, p, found, at)
    assert rep["bent"] == 2 and rep["notesOnPitchBefore"][0] == 0
    assert rep["notesOnPitch"] == [3, 3]                       # A, then D and C
    f, v = melisma.pitch_track(out.mean(axis=1))
    for beat, want in ((3, 69), (5, 62), (6, 60)):
        assert abs(melisma.sung(f, v, at(beat), at(beat + 1)) - want) < 0.3
    # outside the melismas (the first two syllables), the stem is the original, sample for sample
    a = int(at(1.6) * sr)
    assert np.array_equal(out[:a], stereo[:a])
    assert out.shape == stereo.shape


def test_a_hold_piece_and_a_take_with_no_voice_there_are_left_as_sung(tmp_path):
    import numpy as np
    import melisma
    p = piece(tmp_path, MELISMA)
    found = melisma.melismas(p)
    sr = melisma.SR
    silent = np.zeros((7 * sr, 2))
    out, rep = melisma.bend(silent, sr, p, found, melisma.stem_time(p, 0.0))
    assert rep["bent"] == 0 and np.array_equal(out, silent)
    pts, regions = melisma.contour(found, melisma.stem_time(p, 0.0), np.zeros(700), np.zeros(700, bool))
    assert pts == [] and regions == []


def test_the_bend_curve_is_zero_outside_its_regions_and_has_no_jumps(tmp_path):
    import numpy as np
    import melisma
    p = piece(tmp_path, MELISMA)
    found = melisma.melismas(p)
    at = melisma.stem_time(p, 0.0)
    frames = np.arange(800) / 100
    sung = np.array([60 if t < 1 else 64 if t < 2 else 67 if t < 4 else 64 for t in frames], float)
    pts, regions = melisma.contour(found, at, sung, np.ones(800, bool))
    ts = np.array([q[0] for q in pts]); ss = np.array([q[1] for q in pts])
    assert ts[0] > 2.9 and ss[0] == 0 and ss[-1] == 0
    grid = np.interp(np.arange(0, 8, 0.001), ts, ss, left=0, right=0)
    assert np.max(np.abs(np.diff(grid))) < 0.2              # semitones per millisecond: slides, not steps
    assert max(abs(x) for x in ss) == pytest.approx(4.0, abs=0.01)   # E down to C


def test_a_quiet_melisma_in_a_loud_song_is_still_bent(tmp_path):
    """Praat's voicing threshold is relative to the loudest part of what it analyses: on a whole
    song a quiet phrase could come back unbent (Up on the Housetop, Nov 11, 2026). Each melisma is
    resynthesised on its own stretch of the take."""
    import numpy as np
    import melisma
    p = piece(tmp_path, {**MELISMA, "abc": MELISMA["abc"].replace("(E D C) z |]", "(E D C) z | G4 | G4 | G4 |]")})
    found = melisma.melismas(p)
    sr = melisma.SR
    at = melisma.stem_time(p, 0.0)
    held = [(0, 60), (1, 64), (2, 67), (3, 67), (4, 64), (5, 64), (6, 64), (7, 64), (8, 67)]
    y = tone(lambda t: next(m for s, m in reversed(held) if t >= s), 20.0, sr)
    for gap in (1, 2, 4):
        y[int((gap - 0.04) * sr):int((gap + 0.02) * sr)] = 0
    y[int(6.95 * sr):int(10 * sr)] = 0                        # a rest, then the loud end, well after the melismas
    y[:int(7 * sr)] *= 0.01                                   # the melismas 46 dB under it
    y[int(10 * sr):] *= 2.0
    out, rep = melisma.bend(np.stack([y, y], axis=1), sr, p, found, at)
    assert rep["bent"] == 2 and rep["notesOnPitch"] == [3, 3]
