---
name: lesson-voice
description: Record the spoken words of Piano-Master's concept lessons with the lesson voice (Kokoro-82M, Heart at 80% speed; arch §10.5 "The lesson voice", v0.34), check each recording with Whisper, and hand them to the app. Use whenever a concept lesson in content/lessons/ is written or its words change, when the lesson screen's own spoken lines (client/src/lib/lessonPhrases.ts) change, when a word is said wrong in a lesson, or for any request about how the lessons sound when read aloud.
---

# Lesson voice (Piano-Master, arch §10.5)

Every line a concept lesson reads aloud is a recording made here, ahead of time, in one voice:
Kokoro-82M's **Heart at 80% speed** (chosen by the family by ear; `tools/voice/spoken.py` `VOICE`).
**Writing or changing a lesson isn't finished until its lines are recorded.** A line with no
recording still works, but the iPad's mechanical device voice reads it instead.

All commands run from the repo root.

## 1. Before you start

- The tools: `tools/voice/setup.sh` (once; installs `tools/.voice/`, gitignored, and downloads the pinned
  model and Whisper small.en). They run on the CPU, so they never wait for YuE2.
- The recordings are in Git LFS: run `git lfs pull` first if `content/lessons/voice/*.mp3` are pointers.

## 2. Write the words so they read well aloud

The lines read are: each card's `text`, each Check question's `text`, and a Hear card's
`contrast.text`; plus the lesson screen's own lines in `client/src/lib/lessonPhrases.ts` (praise such as
"You did it!": a new fixed line the screen speaks goes there, as `key: "text",` on its own line, and
the screen uses `SAY.key`).

- Write for the ear as well as the eye: short sentences, and "4/4" or "f" only where the card shows them.
- Avoid one-word spoken lines; three words or more read cleanly. A "..." is fine on screen (a
  fill-in question, a line that runs on): the voice reads it as described in section 3.
- When what is shown and what should be heard differ, add **`say:`** beside the `text` (a card, a
  question or a contrast). The same shown text must be said the same way in every lesson.
- A word the voice gets wrong everywhere goes in **`tools/voice/lexicon.yaml`** (with its phonemes in
  misaki's alphabet; "bass" is there), not in `say:`. The note letter A is handled for you when no noun
  follows it ("A is…", "C, B, A", "A B C"); write `say:` if a sentence still reads it as "a".
- See what the voice will be given: `tools/.venv/bin/python -c "import sys; sys.path.insert(0, 'tools/voice'); import spoken; print(spoken.lines()['<the text>'])"`.

## 3. Record and check

```bash
tools/.voice/bin/python tools/voice/lesson_voice.py plan    # what needs recording
tools/.voice/bin/python -u tools/voice/lesson_voice.py make    # record, check, remove unused recordings
```

`make` records only lines that are new or whose words, `say:`, lexicon entry or voice changed (about 40
lines a minute with the check), writes `content/lessons/voice/<hash>.mp3` and the index `voice.json`,
and reports **flagged** lines: Whisper heard letters more than 10% different from those written. For
each flag, read what was heard (`heard:` in the report): a misread word, a dropped or added word, or a
spelling only Whisper differs on. Fix a real one with `say:` or the lexicon and run `make` again; if
it's only spelling (Whisper writes "base" for bass, "EDC" for "E, D, C"), leave it, and say so.
**Take an added word seriously,** especially at the start of a short line: "Listen." was heard as
"I listen" and the family heard a sound before it too ("a listen"). Kokoro can add a sound to a
one- or two-word line, or around a "..." (which `spoken.blanks` now turns into a plain stop, "blank" in
the middle of a sentence, or nothing at the start). The phonemes it was given don't show these
sounds, so they don't prove a flag wrong. Rephrase (a longer cue: "Here it is." instead of
"Listen."), or give the line a `say:` ("A step goes to the what?"), and record it again until it
passes.
`check` re-runs Whisper on every recording.

## 4. Build, check, deploy

```bash
tools/.venv/bin/python tools/build_content.py     # copies the recordings into the app; warns about lines with none
tools/.venv/bin/python tools/check_app.py         # the lesson checks include the voice
tools/deploy.sh client                            # app deploys are ours
```

The build's warning "N lesson lines have no recording" must be gone before deploying. Commit the
lesson, `voice.json` and the MP3s together (the MP3s go to Git LFS by `.gitattributes`), when the user
asks for a commit.

## 5. Tell the parent

Say which lessons were recorded, anything flagged and what you did about it, and where to listen: the
lesson in parent mode (Journey › the skill's bubble), with Auto-read on.

## Changing the voice

The voice (engine, model revision, voice, speed) is `VOICE` in `tools/voice/spoken.py`. Changing it
records every line again (about 10 minutes) and is the family's decision: make a listening page first,
as `feasibility/voice-probe/` did, put it on the piano server (`feasibility/voice-probe/deploy.sh`),
and let them choose by ear on the iPad. Log the change in `docs/architecture.md` (§10.5) and its
change log.
