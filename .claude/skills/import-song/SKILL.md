---
name: import-song
description: Add songs or pieces to the Piano-Master library - find public-domain scores in a genre, or take a file the parent supplies (MusicXML, MIDI, ABC, Humdrum kern, a MuseScore export), convert, fix, level and arrange them, check them with the repo's own validator, and hand the parent one review list to approve. Use for any request to import, add, find, arrange or level songs or pieces for Piano-Master.
---

# Import songs (Piano-Master, arch §10.4)

You find, fix, arrange and check; the parent approves in the app. **Nothing reaches a child until
the parent has approved it.** Batches are made in `content/incoming/<batch>/`, which the content
build and deploys ignore, then submitted to the piano server's staging area through the Skill API
(M7, arch §10.7, §10.9). The parent listens, chooses and approves in Config › Review list; approved
songs join the library on the server straight away, with no deploy.

All commands run from the repo root with `tools/.venv/bin/python tools/import_song.py …`.

## 1. Before you start

- Read the current skill map (`content/skillmap/*.yaml`): it decides where each piece sits. A piece
  needing something no skill covers yet is **beyond the map** and can't unlock until the map grows;
  that's allowed in a batch, but say so in the review.
- Look at what's already in the library so you don't bring duplicates: the deployed pieces
  (`content/pieces/`) and the songs approved on the piano server (`GET /api/skill/library` with the
  skill token). `check` compares melodies with the deployed pieces; the server's intake compares
  them with everything, and refuses anything on its deleted list (`GET /api/skill/deleted`).

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

**Tempo:** the 100% preset is the song's natural performance tempo, not a practice tempo (the app's
90/75/50% presets are for practice). Take it from a real performance, write where it came from in
`tempoSource:`, and mind which note the source counts ([references/arranging.md](references/arranging.md#tempo)).

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

## 6. Add the media, then submit to the review list

Songs get their vocal and backing from the `make-media` skill first (below). Then:

```bash
tools/.venv/bin/python tools/import_song.py report content/incoming/BATCH   # REVIEW.md: your own record of the batch
tools/.venv/bin/python tools/import_song.py submit content/incoming/BATCH   # or name the ids to send only some
```

`submit` builds each piece (notation, song analysis, finger numbers and its stems) and sends it to
the piano server with what the parent needs to decide: source, license and its evidence, the tempo's
source, level, lyrics, your header notes, the check's warnings and the media checks. The server's
intake checks it again (license, id, melody fingerprint against the library and the deleted list,
the skill map) and stages the pieces that pass; its report comes back straight away. The token is
in `~/.config/piano-master/skill-token` (made in Config › Dev box connection, or with
`docker exec docmost-piano-api-1 python -m app.admin skill-token NAME` on the server).

Then tell the parent in a few lines what's waiting in **Config › Review list**: what was
simplified, what's beyond the current map, and anything flagged or uncertain. **Stop there.** They
listen to each song and approve it, send it back with a note (**Needs improvement**) or never allow
it. Deleted songs (never allowed, or deleted from the library) wait at the bottom of the Review
list, where the parent can send one for improvement: its note then shows up in `feedback` like any
other. A song stays on the list until they decide. A new song reaches each
child once its genre is allowed (Config › Songs and genres).

## 6b. Fix what the parent sent back

```bash
tools/.venv/bin/python tools/import_song.py feedback      # each song sent back, its batch file, and the parent's note
```

Read each note and fix what it says: the arrangement (notes, tempo, key, verses) here, the vocal or
backing with the `make-media` skill (a changed tempo or score renders new takes by itself). Log the
problem and the fix in `docs/media-pipeline-notes.md`. Then submit only the fixed songs,
`import_song.py submit content/incoming/BATCH ID…`: each replaces the one sent back and returns to
the review list with the parent's note beside it, and the parent decides again. Tell the parent
what you changed.

## 7. Approved songs, songs for the skill map, and updates to live songs

Every song reaches the app through the review list (arch §10.7, v0.27), whatever made it.
- **After the parent approves a batch's songs**, `import_song.py promote content/incoming/BATCH ID…`
  moves their sources into `content/pieces/`, so every song's source is kept in git. Commit them.
- **Songs written here for the skill map** (practice songs for a skill's `pieces` list) are written in
  `content/pieces/` (`composer: Piano-Master`, `genre: studies`, `license: {composition: original,
  edition: original}`), then `import_song.py submit content/pieces ID…`. The map that names them is
  deployed only after the parent approves them (`tools/deploy.sh` runs `tools/library_check.py`).
- **Updating a live song:** the parent's Needs improvement on a song in use shows in
  `import_song.py feedback` as a live song, with its source and the submit command. Fix the source,
  check it, and submit it under the same id: it waits in the review list as an update, and the
  children keep the live song until the parent approves it.

## Media

Pieces arrive with notation only. The `make-media` skill (`.claude/skills/make-media/`) adds
them before the parent's review: a YuE2 vocal for songs with words, and a FluidSynth backing from
the piece's own backing notes (arch §10.5, v0.22). So give songs **chord symbols**, and type a
hymn's **four parts** with `play: melody` (the child plays the melody; the alto, tenor and bass
become the backing). A song with words and no backing notes keeps YuE2's backing. A solo piano
piece needs none: the app plays the other hand. Run `make-media` after `check`, then `submit`.

## Log problems as you go

Keep a `NOTES.md` in the batch folder with each problem you hit and what would fix it, in the order
they come up (the classical batch's notes are a model: `content/incoming/classical/NOTES.md`). Stop
and ask when something blocks the batch (a source you can't license, a feature the notation can't
hold).
