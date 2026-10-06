"""The lesson voice's lines (arch §10.5, v0.34), without the speech engine: what the lessons read aloud,
how the voice is told to say it, and how the content build hands the recordings to the app."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "voice"))
import build_content as bc  # noqa: E402
import spoken  # noqa: E402


def test_note_a_is_the_letter_and_the_article_a_stays_a_word():
    say = lambda t: spoken.spoken(t, {})  # noqa: E731
    assert say("A is two steps below Middle C.") == "[A](/ˈA/) is two steps below Middle C."
    assert say("Play C, B, A with fingers 1, 2, 3.") == "Play C, B, [A](/ˈA/) with fingers 1, 2, 3."
    assert say("just seven letters, A B C D E F G.").startswith("just seven letters, [A](/ˈA/) B C")
    assert say("Which left-hand finger plays A in Middle C position?") == "Which left-hand finger plays [A](/ˈA/) in Middle C position?"
    assert say("A half note gets two beats. A rest is a beat of silence.") == "A half note gets two beats. A rest is a beat of silence."


def test_a_blank_is_read_the_way_the_voice_says_it_cleanly():
    assert spoken.blanks("A quarter note is...") == "A quarter note is."
    assert spoken.blanks("Piano, soft…") == "Piano, soft."
    assert spoken.blanks("...and mezzo forte, medium loud.") == "and mezzo forte, medium loud."
    assert spoken.blanks("Bass C is a ... below Bass D.") == "Bass C is a blank below Bass D."
    assert spoken.blanks("Play C. Then D.") == "Play C. Then D."


def test_the_lexicon_says_bass_as_base_whole_words_only():
    lex = {"Bass": "bˈAs", "bass": "bˈAs"}
    assert spoken.spoken("Bass F, on the bass staff.", lex) == "[Bass](/bˈAs/) F, on the [bass](/bˈAs/) staff."
    assert spoken.spoken("a bassoon", lex) == "a bassoon"
    assert "bass" in spoken.lexicon() and "Bass" in spoken.lexicon()


def test_a_recording_is_named_by_its_words_and_the_voice():
    k = spoken.line_key("Play C.")
    assert k == spoken.line_key("Play C.") and k != spoken.line_key("Play D.")
    old = dict(spoken.VOICE)
    try:
        spoken.VOICE["speed"] = 0.9
        assert spoken.line_key("Play C.") != k
    finally:
        spoken.VOICE.clear()
        spoken.VOICE.update(old)


def test_every_line_the_lessons_read_is_found_with_the_screens_own_praise():
    lines = spoken.lines()
    phrases = spoken.phrases()
    assert "You did it!" in phrases and "Good try! Listen again and play it back." in phrases
    assert all(p in lines for p in phrases)
    # card text, Check questions and a Hear card's contrast
    assert "Find Middle C and play it." in lines
    assert any(ln["where"].startswith("prep-a.") for ln in lines.values())
    assert all(ln["say"] for ln in lines.values())


def test_the_lesson_screen_speaks_only_lines_from_its_phrases_file():
    """Every fixed line Lesson.svelte says aloud comes from lessonPhrases.ts (so it is recorded)."""
    src = (spoken.ROOT / "client" / "src" / "screens" / "Lesson.svelte").read_text()
    assert "speechSynthesis" not in src and 'say("' not in src and 'speak("' not in src


def test_say_overrides_what_is_read(tmp_path, monkeypatch):
    lessons = tmp_path / "lessons"
    lessons.mkdir()
    (lessons / "x.yaml").write_text("skill: x\ncards:\n- kind: explain\n  text: 4/4 time\n  say: four four time\n")
    monkeypatch.setattr(spoken, "LESSONS", lessons)
    assert spoken.lines()["4/4 time"]["say"] == "four four time"
    (lessons / "y.yaml").write_text("skill: y\ncards:\n- kind: explain\n  text: 4/4 time\n")
    with pytest.raises(ValueError, match="said two ways"):
        spoken.lines()


def test_the_build_copies_up_to_date_recordings_and_leaves_the_rest_to_the_device(tmp_path, monkeypatch):
    lessons, voice = tmp_path / "lessons", tmp_path / "lessons" / "voice"
    voice.mkdir(parents=True)
    (lessons / "x.yaml").write_text("skill: x\ncards:\n- kind: explain\n  text: Play C.\n- kind: explain\n  text: Play D.\n"
                                    "- kind: explain\n  text: Play E.\n")
    monkeypatch.setattr(spoken, "LESSONS", lessons)
    monkeypatch.setattr(spoken, "VOICE_DIR", voice)
    monkeypatch.setattr(spoken, "MANIFEST", voice / "voice.json")
    monkeypatch.setattr(spoken, "phrases", lambda: [])
    c, d, e = (f"{spoken.line_key(t)}.mp3" for t in ("Play C.", "Play D.", "Play E."))
    (voice / c).write_bytes(b"\xff\xfb" + bytes(2000))
    (voice / d).write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:00\nsize 2000\n")   # not pulled
    (voice / "voice.json").write_text(json.dumps({"voice": spoken.VOICE, "lines": {
        "Play C.": {"file": c}, "Play D.": {"file": d}, "Play E.": {"file": "old.mp3"}}}))   # E's words changed
    out = tmp_path / "out"
    out.mkdir()
    missing = bc.lesson_voice(out)
    assert json.loads((out / "voice.json").read_text()) == {"Play C.": f"voice/{c}"}
    assert (out / "voice" / c).exists() and missing == ["Play D.", "Play E."]
    assert e not in [p.name for p in (out / "voice").iterdir()]
