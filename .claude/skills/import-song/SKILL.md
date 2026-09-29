---
name: import-song
description: Add songs or pieces to the Piano-Master library - find public-domain scores in a genre, or take a file the parent supplies (MusicXML, MIDI, ABC, Humdrum kern, a MuseScore export), convert, fix, level and arrange them, check them with the repo's own validator, and hand the parent one review list to approve. Use for any request to import, add, find, arrange or level songs or pieces for Piano-Master.
---

# Import songs (Piano-Master, arch §10.4)

You find, fix, arrange and check; the parent approves. **Nothing reaches a child until the parent
has said which pieces to add.** Batches wait in `content/incoming/<batch>/`, which the content
build and deploys ignore. Until the Skill API and staging exist (M7), approved pieces are promoted
into `content/pieces/` and go live with the next deploy.

All commands run from the repo root with `tools/.venv/bin/python tools/import_song.py …`.

## 1. Before you start

- Read the current skill map (`content/skillmap/*.yaml`): it decides where each piece sits. A piece
  needing something no skill covers yet is **beyond the map** and can't unlock until the map grows;
  that's allowed in a batch, but say so in the review.
- Look at what's already in the library (`content/pieces/`) so you don't bring duplicates; `check`
  also compares melodies.
- Check `content/deleted.yaml` (songs the parent said never to add, if it exists).

## 2. Find or take the source

Follow [references/sources-and-licenses.md](references/sources-and-licenses.md). In short: the
**composition** must be public domain in the US (published in 1930 or earlier, as of 2026), unless
the parent supplied the file for private family use, **and** the **edition** must be openly
licensed (public domain, CC0, CC BY, CC BY-SA). Otherwise **retype** the notes and use the edition
only to check them (`license.edition: "retyped from <edition> (<its license>), checked only"`).
Prefer MusicXML, Humdrum kern or ABC. Use MIDI only to check pitches (no spelling, voices or ties),
and don't use LilyPond sources (python-ly can't convert them).

## 3. Convert to a draft

```bash
tools/.venv/bin/python tools/import_song.py convert SOURCE --id ID --batch BATCH --title "…" --composer "…" --genre GENRE
```

This writes `content/incoming/BATCH/ID.yaml` with the score as ABC and TODOs for the metadata. Ids
are lowercase with dashes, unique, and never reused. For a song you write out by hand, create the
YAML directly in the same format ([references/arranging.md](references/arranging.md#the-piece-file)).

## 4. Arrange, level and fix

Follow [references/arranging.md](references/arranging.md): which level, how to simplify, keep it
on 61 keys (C2–C7), repeats, phrases, fingering, chord symbols, lyrics, and several arrangements of
one song (`song:` and `version:`). Say in the file's header comment what you changed from the
source. Known traps are in [references/pitfalls.md](references/pitfalls.md).

## 5. Check and compare

```bash
tools/.venv/bin/python tools/import_song.py check content/incoming/BATCH
tools/.venv/bin/python tools/import_song.py compare content/incoming/BATCH/ID.yaml SOURCE --line melody   # or R, L, all
```

- `check` builds each piece with the content build's own code (notation, song analysis against the
  current map, finger numbers, keyboard range). It also checks bar lengths, the metadata, source and
  license fields, the deleted list, and duplicates by melody fingerprint. Fix every **error**;
  read every **warning** and either fix it or explain it in the header comment.
- `compare` lines the piece's notes up with the reference file and lists the differences by bar.
  An unchanged conversion should be 100%. A simplified arrangement should match on the line it
  keeps (usually `--line melody` or `--line R`). Use `--transpose N` if you changed the key and
  `--part N` to choose the reference's part. Every difference must be one you made on purpose.
- Then build and draw everything: `tools/.venv/bin/python tools/build_content.py` doesn't read the
  batch, so to see a piece on the Play screen, copy it into `content/pieces/` temporarily, run the
  build and `tools/check_app.py` (it draws every piece and reports staff problems), then move it
  back. Don't leave it there unapproved.

## 6. Hand the parent one review

```bash
tools/.venv/bin/python tools/import_song.py report content/incoming/BATCH
```

This writes `content/incoming/BATCH/REVIEW.md`: one row per piece, with its level, range, where it
sits on the map, source, license and any remaining problems. Tell the parent in a few lines what's
in the batch, what was simplified, what's beyond the current map, and anything uncertain. Then
**stop and wait for their answer.**

## 7. Promote what the parent approved

```bash
tools/.venv/bin/python tools/import_song.py promote content/incoming/BATCH ID1 ID2 …   # or --all, only if they approved all
```

`promote` re-checks and refuses anything with errors. Then run the content build and the tests,
and deploy with `tools/deploy.sh` (the app deploy is ours to run; see the deployment notes). A
piece the parent rejects for good goes on `content/deleted.yaml` (title, composer, reason), so it's
never offered again.

## Media

Pieces arrive with notation only. Sung vocals and backing come from the `generate-music` skill
(YuE2), which needs lyrics, so it's only for songs with words. A backing track for wordless pieces
is an open question, being tested separately with FluidSynth (arch §15). Don't promise media for
instrumental pieces.

## Log problems as you go

Keep a `NOTES.md` in the batch folder with each problem you hit and what would fix it, in the order
they come up (the classical batch's notes are a model: `content/incoming/classical/NOTES.md`). Stop
and ask when something blocks the batch (a source you can't license, a feature the notation can't
hold).
