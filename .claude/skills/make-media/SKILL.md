---
name: make-media
description: Make the sung vocal and backing tracks for Piano-Master songs and pieces (arch §10.5, M8) - a YuE2 vocal for songs with words, a FluidSynth backing (MuseScore General) from the piece's own chords or parts, aligned to the beat at all four tempo presets and checked - then submit them to the app's review list for the parent. Use for any request to add, redo or restyle vocals, backing, accompaniment or media for Piano-Master pieces or an import batch.
---

# Make media (Piano-Master, arch §10.5)

You make and check; the parent listens and approves in the app's review list. Media for a batch
waits with the batch in `content/incoming/<batch>/media/` until it's submitted with the pieces
(the import skill's `submit`). Nothing reaches a child before the parent's approval.

All commands run from the repo root with `tools/.venv/bin/python tools/media/media.py …`.

## 1. Before you start

- Tools: `tools/media/setup.sh` (FluidSynth, Rubber Band, MuseScore General, the lyric aligner, all in
  `tools/.media/`). YuE2 is the `generate-music` skill's engine (`~/engines/yue2`); check it's ready
  as that skill says. The GPU renders one take at a time: don't run two `make`s at once.
- The pieces must already pass the import skill's `check` (`.claude/skills/import-song/`).

## 2. See what each piece will get

```bash
tools/.venv/bin/python tools/media/media.py plan content/incoming/BATCH
```

The v0.22 decision decides it:

| The piece has | Vocal | Backing |
| --- | --- | --- |
| No words | none | FluidSynth from its backing notes; none for a solo piano piece (the app plays the other hand) |
| Words and backing notes (chord symbols, a hymn's other voices, a round) | YuE2 | FluidSynth, in the genre's style |
| Words and no backing notes | YuE2 | YuE2's own, aligned with the vocal |

Styles (`tools/media/backing.py`): `kids` (soft strings, pizzicato bass, glockenspiel chimes, from the
chords), `hymn-strings` (strings on the alto and tenor, cello on the bass: chosen for Amazing Grace),
`hymn-organ`, `pad` (strings and cello from the chords), `waltz`, `round` (the melody again on flute
and clarinet, entering bars behind), and `yue2` (keep YuE2's backing). The genre sets the default; a
piece can choose, in its file:

```yaml
play: melody                 # a full score (a hymn's four parts): the child plays the top line, the rest is backing
media:
  vocal: yue2                # or none
  backing: {style: round, entryBars: [2, 4]}   # or just `backing: kids`
  vocal_style: warm clear solo voice            # optional: a parent's style change for this song
```

For a hymn, type all four parts (`%%score (S A) (T B)`) and set `play: melody`: the backing then
plays the real harmony.

## 3. Make it

```bash
tools/.venv/bin/python -u tools/media/media.py make content/incoming/BATCH     # run it in the background
```

For each piece: YuE2 inputs (one note per syllable, chords kept, the sung "Oh" lead-in), two takes
(a third if neither passes), each aligned in two ways and checked, the best kept; the FluidSynth
backing at each tempo; then levels, MP3s and `media.json`. About a minute of GPU and five minutes of
alignment per take. Steps can be run alone (`vocal`, `backing`, `package`); finished renders and
alignments are reused.

**The checks** (a take must pass all of them; the best passing take is kept, else the best one,
flagged):
- timing: no phrase more than 50 ms off the beat;
- pitch: 90% of notes on the right pitch;
- words: the first word sung; words more than 0.3 s off their notes, or that the aligner can't
  place (a garbled word), under 10%, and no stretch of them lasting 1.5 s or more in the first 15 s
  (anything shorter, or later, is a *flag*: point the parent to it);
- melody: no run of 4+ notes sung on other pitches lasting 1.5 s or more (a shorter slip is a flag);
- octave: no held note (0.8 s or more) sung in another octave from the rest of the take;
- tuning: within 10 cents of A440 (the FluidSynth backing is exact);
- bleed: YuE2's backing left in the vocal under -25 dB (it would clash with a FluidSynth backing);
- backing: every part within 20 ms of the beat after starting slow instruments early.

A song whose takes all fail: package the best, say so, and let the parent decide (the Vocals
button turns a poor vocal off). Fast songs fail more often; `--max-takes 6` (up to 12) renders more
seeds, stopping at the first take that passes. Don't submit a take with a quarter or more of its
words off: the parent hears that every time (v0.30). A curriculum song (`genre: studies`) gets the
vocal alone, with no backing (style `none`).

## 4. Hand the parent one review, in the app

```bash
tools/.venv/bin/python tools/media/media.py report content/incoming/BATCH     # MEDIA.md: the checks, for you and the notes
tools/.venv/bin/python tools/import_song.py submit content/incoming/BATCH     # to the piano server's review list
```

`submit` (the import skill's) sends each piece with its stems through the Skill API. The server's
intake checks them again and stages the ones that pass; the parent listens in the app, under
**Config › Review list**, where each song opens in the Play screen with its vocal and backing at
every tempo, and shows its checks and flags. Tell the parent what to listen for, especially flags
and anything that failed. Then stop: for each song they choose **Approve**, **Needs improvement**
(with a note) or **Never allow**. No app deploy is needed.

**Songs sent back:** `tools/.venv/bin/python tools/import_song.py feedback` lists the parent's notes.
A note about the vocal or backing ("too fast, the words run together"; "the backing is too loud")
is yours: change the piece (a tempo) or the media (`--max-takes`, a style), run `make` again, and
resubmit that song with `import_song.py submit content/incoming/BATCH ID`. A note about the take itself ("try another rendering", a garbled word the checks passed): render again with `--skip-take N` (the take in its media.json) so that take is never chosen again. It returns to the review
list with the note beside it.

## Log problems as you go

Add each problem to `docs/media-pipeline-notes.md` as it comes up: what got in the way and what
fixed it or would (batch folders are never committed, so the notes live in `docs/`). Things to note:
a style that doesn't suit a song, a vocal the checks passed but that sounds wrong, bleed you can
hear. Stop and ask when something blocks the batch.
