# Melisma in the vocal: hand-over for building it

**Built in v0.50 (Nov 10, 2026):** the bend is in the media skill's package step (`tools/media/melisma.py`, `media.py package`; arch 10.5 "Melismas"), with tests in `tools/tests/test_media.py`. The split option was left out: it cost the words (RESULTS.md). What follows is kept as the design record.

For the agent (or person) who builds this into the media skill. Read [RESULTS.md](RESULTS.md) first: it has what was tried, the numbers, and what the parent still has to decide by listening. This file says what to build, where, and how to check it.

## What is being built

A melisma is one sung syllable over several notes. Today the media skill sends YuE2 one note per syllable, so the singer holds the first pitch where the staff shows the notes move (`docs/architecture.md` 10.5, "One note per sung syllable"). After this work the vocal sings the written notes:

- **Bend (the default).** YuE2's input doesn't change. Once a take is aligned to the beat and chosen, the held pitch is bent onto the written notes inside the vocal stem, at every tempo preset.
- **Split (an option, off unless the parent chooses it).** A melisma is sent to YuE2 with a syllable on each note, on the same vowel ("thi-is", "Jo-o-oy"). `SHORT_S` chooses which melismas: those with a note shorter than it. RESULTS.md says why it isn't the default.

The staff and the child's piano part never change.

## The probe's code, and what becomes of it

Everything is in this folder and runs with the media skill's own environment (`tools/.venv`), plus Praat through `parselmouth` for the bend.

| File | What it does | In the real pipeline |
| --- | --- | --- |
| `melisma.py` `melismas` | Finds every melisma from the piece, with each note's length at 100% | Move to a new `tools/media/melisma.py`. Better: have `yue2.export` write the list into `abcmap.json` (`melismas`: each one's notes, beats, pitches, kind), since `syllabic_melody` already finds them, so later steps read it and can't disagree with what was sent |
| `melisma.py` `split_syllable`, `hybrid_export` | Splits a syllable onto its vowel; runs the real export with the short melismas split | `hybrid_export` wraps two functions of `yue2.py` at run time, which is right for a probe and wrong for the tool. In `yue2.py`: `syllabic_melody` takes the set of melismas to split and gives those notes their syllables; the lyric assembly in `export` joins them with the hold hyphen (as `vowel_run` does) and keeps the word as written for the aligner and the word check |
| `melisma.py` `contour` | The bend as a curve: for each later note, the written step less how far the take is from the first note's pitch there; raised-cosine slides; the end placed in a gap in the voice | Move as is |
| `psola.py`, `melisma.py` `bend_psola` | Praat's overlap-add resynthesis along the curve | Move as is. `praat-parselmouth` can go into `tools/media/requirements.txt` and be called in-process; the probe used its own venv only so as not to change the project's |
| `melisma.py` `splice` | The bent audio inside each melisma, the original outside, switching where the two are the same | Move, with the stereo rule below. Whether to splice or run the whole vocal through is the parent's choice by ear (RESULTS.md) |
| `melisma.py` `on_pitch`, `melody_on_pitch` | The checks | Move; report them in `media.json` |
| `apply.py` | Bends a song's approved take at every preset and replaces its media, for a live-song update | The model for the package step (point 3 below); stays here as the one-off that made the Nov 10 updates |
| `bend.py`, `render.py`, `build_page.py`, `deploy.sh` | Drivers and the listening page | Stay here |
| `bend_rubberband` | The first trial's method | Drop: it misses short notes and changes the whole file (RESULTS.md) |

## Where it goes in the media skill

1. **`tools/media/yue2.py`**: write `melismas` into `abcmap.json`. Add the split option. A piece chooses with `media: {melisma: bend | split | hold}` in its file (`hold` is today's behaviour, for a song where neither works); the default is `bend`.
2. **`tools/media/media.py` `vocal`**: unchanged. Takes are still judged on the line that was sent (merged for a bent melisma), by the same checks. Don't bend before choosing: the checks and the alignment rely on the take as sung.
3. **`tools/media/media.py` `package`**: after `align.tempo_versions` and before levelling, bend each preset's `vocals_<preset>.wav`:
   - measure the pitch in that preset's file and build the curve with every time, and the slide length, divided by the preset's ratio (`bend.py --preset` does this; a melisma is short or long by its 100% length, whatever the preset);
   - bend the mono sum; inside the bent regions put that mono on both channels, and keep the stereo original outside them (see "Stereo" below);
   - then `song_only`, the level and the MP3 as now.
4. **`media.json` `check`**: add `melismas` (how many, how many bent or split or left held), `melismaNotesOnPitch` before and after, and `melodyOnStaff`: the share of the whole written melody on pitch, which is what the child hears against the staff. Show them in the review list beside the other checks (`client/src/screens/parent/ReviewPage.svelte`) and in `MEDIA.md` (`media.report`).
5. **A melisma the bend can't fix** (no voice there, or the take sang something else, so the bend would be over `MAX_BEND`) is left as sung and counted. A song with many of them is flagged for the parent's listen, not failed.

## Rules the probe found, to keep

- **Bend toward the written note from what was sung, not by the written interval alone.** The singer doesn't always hold the first pitch through the syllable (37 of 45 times in Joy to the World). The curve uses the pitch measured at each note.
- **Slides are raised cosines centred on the note's beat**, 80 ms long, and never more than half the shorter of the two notes. The first trial's straight 50 ms slides and 10 ms jump back made the tics the parent heard.
- **The bend ends in a gap in the voice** (the next syllable's consonant, a breath) when there is one within 0.1 s of the syllable's end; there it can't be heard. Otherwise a slide centred on the syllable's end.
- **Don't crossfade two versions of a vowel.** The resynthesised voice isn't the same waveform as the original even where the pitch is unchanged. Switch between them where they are the same (silence, consonants the resynthesis copied); with no such place within 3 s, an equal-power crossfade at the quietest spot.
- **Stereo.** The vocal stems are stereo (the side signal is 7 to 8 dB under the middle). Bending each channel by itself smears the image: the channels' correlation inside the bent regions fell from 0.64 to 0.07. Bend the mono sum and use it for both channels inside the regions.
- **Octaves.** YuE2 often sings an octave from the score. Every comparison is to the nearest octave (`near`), as the media skill's own pitch check is.

## How to check the build

- **Unit tests** (`tools/tests/test_media.py`): `split_syllable` on the words in RESULTS.md; the export with split melismas still passes the attack check (`export` raises when the Vocal attacks don't match the syllables) and the `generate-music` syllables check; the curve is 0 outside its regions and continuous; a made tone (a few harmonics with a little vibrato, held, then bent) is found on the written pitches afterwards; the spliced stem is sample-for-sample the original outside the regions.
- **On real songs**: `bend.py` and `render.py` here print the same measures. Expect, for the three test carols at 100%: melisma notes on pitch from almost none to 93% or more, and the whole melody on the staff from 72–81% to 96% or more (RESULTS.md).
- **By ear**: build the listening page (`build_page.py`), and have the parent listen before the method is fixed. The numbers say the notes are right; they don't say it sounds good.

## Bringing it to the songs already approved

26 songs with words have melismas (list them with `melismas()` over `content/incoming/*/` and `content/pieces/`). Three (The First Noel, Joy to the World, What Child Is This) were already bent by `apply.py` and submitted as live-song updates on Nov 10, 2026; it is the reference for the package step: same take, gain and fade as `media.py package`, stereo handled as below, and `--check` proves a rebuild without the bend matches the approved MP3s sample for sample. Don't bend those three again: their media folders now hold the bent stems, and the approved ones are in `out/approved/`. Their chosen takes and alignments are still in `tools/.media/work/<id>/`, so no new render is needed: run `media.py package` again once it bends, and send each song as an update to a live song (`import_song.py submit`; arch 10.7 "Updating a live song"), so the parent hears each one against the live version and approves it. The children keep the current vocal until then.

## Documents to change when it is built

- `docs/architecture.md` 10.5 ("One note per sung syllable", the steps, "Known YuE2 limitations") and 3 ("Vocal stem"), with a new version and change-log entry; tick the Next steps item.
- `.claude/skills/make-media/SKILL.md`, and the `generate-music` skill's `references/piano-master.md` (the one-note-per-syllable rule stays; what happens to a melisma afterwards changes).
- `docs/media-pipeline-notes.md`: a note for the run that brings it to the approved songs.

## Licences

Praat and `parselmouth` are GPL-3. They are used as a tool on the dev box, like Rubber Band (also GPL), which the pipeline already runs; nothing of theirs is shipped in the app or copied into the repository.
