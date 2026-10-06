# Lesson voice probe: results (Oct 5–6, 2026)

**Question:** the concept lessons read their words with the device's built-in voice, which the family
found unnatural and more distracting than helpful. Can a better voice be used?

**Decision (Oct 6):** yes. The family chose **Kokoro-82M, voice Heart, at 80% speed**, by ear on the
iPad. Every lesson line is recorded ahead of time on the dev box (arch §10.5 "The lesson voice",
v0.34; `tools/voice/`, the `lesson-voice` skill).

## What was tried

15 real lesson lines (the hard cases: note letters, finger numbers, "bass", 4/4, f, p and mf,
Allegro) and the screen's praise, in:

| Voice | License | Notes |
| --- | --- | --- |
| Kokoro-82M: Heart, Bella, Emma (British), Michael; Heart at 90% and 80% | Apache-2.0 | 82M parameters; ~100 s of speech in 2 s on the GPU, all 330 lines in 26 s; fine on the CPU too |
| Chatterbox (Resemble AI) | MIT | 0.5B; ~15 s of GPU per minute of speech; faster speech (up to 4.6 words a second against 3.6) and it once added a word ("*Well,* you did it.") |
| The device's own voice | — | The page's "This device" button: what the lessons used |

The listening page (`build_page.py`, `page.html`) was deployed to the piano server with `deploy.sh`
(`$PIANO_SERVER/lesson-voices/`) so the family could compare on the iPad.

## Findings

- **Feasible:** every line is fixed text written in advance, so it can be recorded once and served
  like song media: 330 lines, about 22 minutes at full speed (27 at 80%), 9 to 12 MB as MP3.
- **Pronunciation:** Kokoro reads "bass" as the fish (55 lines) and the note A as the word "a" in
  three lines. Fixed with its pronunciation marks: a lexicon and a note-letter rule.
- **Intelligibility:** Whisper (small.en) transcribed every clip; every word was found in every voice
  (2.6% to 5.8% word differences, nearly all spelling: "base", "EDC"). The real slip was Chatterbox's
  added word. This check became part of recording (`lesson_voice.py`).

## Files

`lines.json` (the test lines and their pronunciation fixes), `kokoro_render.py`,
`chatterbox_render.py`, `scan.py` (Kokoro's phonemes for every lesson line), `full_render.py` (the
whole library's time and size), `asr_check.py` (the Whisper check), `build_page.py` and `page.html`
(the listening page), `deploy.sh`. The renders (`out/`) and the page (`dist/`) are gitignored. The
probe ran in trial environments outside the repo (`~/engines/tts-trial/`); the real tools are
`tools/voice/`.
