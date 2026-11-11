# Melisma probe: results (Nov 10, 2026)

**Question:** can the vocal sing a melisma (one syllable over several notes) as the staff shows it? Today the singer holds the first pitch (arch 10.5: YuE2 gets one note per syllable, because given more notes than syllables it puts words on the wrong notes).

**Short answer:** yes, by bending the held pitch onto the written notes after the take is aligned. With Praat's overlap-add resynthesis it works for long and short melismas alike, on vocals that are already approved, with no new render. Sending YuE2 split vowels ("thi-is") gets the notes sung but costs the words; it stays an option, not the default. The parent's listen decides the open choices at the end.

How to build it: [HANDOFF.md](HANDOFF.md).

## How common melismas are

Counted over every song with words in `content/pieces/` and `content/incoming/` (146 songs): **26 have melismas**, all of them carols in the two Christmas batches. Joy to the World and The First Noel have them on 26% of their melody notes, What Child Is This on 20%. Almost every melisma is two notes; the longest is three. None of the curriculum's own songs has one.

Three test songs cover the cases:

| Song | Melismas | Shortest note in them (at 100%) |
| --- | --- | --- |
| The First Noel | 57 | 0.34 s (all "long") |
| Joy to the World | 36 | 0.16 s (21 with a note under 0.3 s, 15 without) |
| What Child Is This | 28 | 0.14 s (all "short") |

## 1. Bending the held pitch (no new render)

**Method.** The approved 100% vocal is already on the beat grid, so the score says where each melisma note starts and ends. For each later note of a melisma, the pitch is moved by the written step from the first note, less how far the take is from the first note's pitch there. The slides between notes are raised cosines, 80 ms long (never more than half the shorter note), centred on the note's beat. The bend ends in a gap in the voice (the next syllable's consonant) when there is one within 0.1 s, else with a slide centred on the syllable's end. `bend.py` does it and measures.

**Measure.** A note is on pitch when the median sung pitch over it (away from its edges) is within half a semitone of the written note, in any octave, as the media skill's own pitch check counts.

| Song | Melisma notes on pitch, as approved | Bent (Praat overlap-add) | Bent (Rubber Band pitch map) | Whole melody on the staff, before → after (Praat) |
| --- | --- | --- | --- | --- |
| The First Noel | 0 of 57 | **53 of 57** | 53 of 57 | 158 of 219 (72%) → 211 (96%) |
| Joy to the World | 4 of 41 | **38 of 41** | 27 of 41 | 125 of 166 (75%) → 159 (96%) |
| What Child Is This | 0 of 24 | **23 of 24** | 3 of 23 | 112 of 138 (81%) → 135 (98%) |

"Whole melody on the staff" is every written melody note, melismas included: what a child hears against what the staff shows. The media skill's own number (97–100% for these takes) is measured against the line that was sent, with the melismas merged, so it never showed this gap.

**The slower presets.** The same bend on the approved 50% and 75% vocals of What Child Is This, with every time and slide stretched by the preset's ratio: 26 of 26 and 24 of 26 melisma notes on pitch.

**The two bend engines.**

- **Praat's overlap-add (PSOLA), through `parselmouth`:** moves the voice's own pitch periods closer or further apart. It follows a fast slide, so it works on sixteenth notes, and the vowel keeps its colour.
- **Rubber Band's pitch map** (the first trial): fine on long notes, but it misses the short ones (3 of 23), it must run in realtime mode, and it changes the whole file a little. Not used.

**The tics in the first trial.** The first bend (version B on the listening page) had straight 50 ms slides, jumped back to the take's own pitch in 10 ms at the end of each melisma, wherever that fell, and ran the whole file through Rubber Band. The smoothed version changes all three: raised-cosine slides, the end placed in a consonant gap (24 of 57 melismas in The First Noel have one within reach), and Praat's resynthesis. Whether the tics are gone is for the ear: versions C and D on the listening page.

**Joining the bent audio to the original.** The resynthesised voice isn't the same waveform as the original even where the pitch is unchanged, so crossfading the two in the middle of a vowel mixes two voices out of phase. Two ways round it, both on the listening page:

- **C, only the melismas changed:** each bent region grows outward to the nearest spot where the two are the same (silence, or consonants the resynthesis copied) and switches there. In The First Noel 79 of 114 joins found such a spot; the other 35 crossfade (equal power, 20 ms) at the quietest spot within 3 s. Outside the regions the stem is exactly the approved one. Because the melismas are so many, 112 of the song's 152 seconds end up inside a region.
- **D, the whole vocal through the resynthesis:** no joins at all; every voiced sound is re-laid, at its own pitch where nothing is bent.

**Stereo.** The vocal stems are stereo (the side signal 7 to 8 dB under the middle). The probe bent the mono sum. Bending each channel by itself was tried on What Child Is This and smears the image: the channels' correlation inside the bent regions fell from 0.64 to 0.07. So: bend the mono sum and put it on both channels inside the regions.

**What the bend can't fix.** A melisma where the take has no voice on the later note, or sang something else (a bend over 9 semitones), is left as sung: 3 or 4 notes in each test song stay off pitch.

## 2. Split vowels in YuE2 (new renders)

**Method.** The v0.33 "Glo-o-o-ria" rule, applied by the tool: a melisma's notes each get a syllable on the same vowel, joined by hyphens in YuE2's lyrics, so the one-note-per-syllable rule still holds. "this" over two notes becomes "thi-is", "heart" over three "hea-ea-eart", "Joy" "Jo-o-oy" (`split_syllable`; the word check and the aligner still get the words as written). `render.py` runs the media skill's own vocal step with this export: 2 takes, a third when neither passes, every take aligned both ways and judged by the usual checks.

**Hybrid rule tested:** melismas with a note under 0.3 s split, the rest left merged and bent afterwards.

| Song | Melismas split / left to bend | Takes passing the media checks | Chosen take: words off the staff (the approved take) | Words heard by Whisper (approved) | Split notes on pitch | Whole melody on the staff, after the bend |
| --- | --- | --- | --- | --- | --- | --- |
| What Child Is This | 28 / 0 | **0 of 3** | 21% (7%) | 89% (96%) | 26 of 28 | 139 of 142 (98%) |
| Joy to the World | 21 / 15 | **0 of 3** | 18% (7%) | 95% (not recorded) | 24 of 30 | 151 of 171 (88%); the bend alone on the approved take: 96% |

- **The notes are sung.** YuE2 follows the split notes: 26 of 28 and 24 of 30 on pitch, and 91–99% of the line sent.
- **The words suffer.** Every one of the six takes failed the word check, with 18% to 82% of words off the staff, where the approved takes of the same songs have 7%. Whisper heard "what childish things, who, lateriest on Mary's love" for "What Child is this, who, laid to rest, on Mary's lap", and "prepare him, ruin heaven and earth" in Joy to the World. YuE2 reads "thi-is" and "roo-oo-oom" as odd words, not as one word held.
- **Part of the word count is the aligner, not the singer.** The forced aligner loses its place in repeated syllables (the Gloria run and "fa la la", media-pipeline-notes 27 and 34), so "words off" overstates it. Whisper's hearing (89% against 96% for What Child Is This) says the loss is real all the same.
- **The long melismas in the hybrid take bent as before:** 3 of 15 on pitch as rendered, 15 of 15 after the bend.
- **Cost:** a new render and its lottery for every song (about 8 minutes of GPU and alignment for three takes), against no render for the bend.

## 3. What this says about the two-part pipeline

The plan was: short melismas (under about 0.3 s) by split vowels, longer ones by the bend. The probe found the split isn't needed for short notes, and costs words:

| | Bend (Praat) | Split vowels in YuE2 |
| --- | --- | --- |
| Melisma notes of 0.14–0.16 s on pitch | 23 of 24 (What Child Is This) | 26 of 28 |
| Words | Unchanged: the approved take's | Worse in every take; 0 of 6 pass the word check |
| New render | No: the approved take is reused | Yes, with the usual 2 to 3 takes |
| Whole melody on the staff | 96–98% | 88–98% |

**Recommendation: bend every melisma, short and long.** Keep the split as a per-song choice (`media: {melisma: split}`, with `SHORT_S` for which melismas) for a song where the parent hears that a bent short melisma doesn't sound right and prefers the split take's words as they are. The two-part pipeline is built in the probe and can be switched on by that one setting; the numbers don't support making it the default. The one thing the numbers can't say is how a bent sixteenth-note melisma sounds (question 3 below).

## Submitted for the parent's review (Nov 10, 2026)

The parent sent the three test songs back through Needs improvement ("Add melisma using the new tools"). `apply.py` bent every melisma (long and short; version C: only the melismas changed) into each approved take at all four presets, and the songs went to the Review list as updates to the live songs. Melisma notes on pitch, at 100 / 90 / 75 / 50%:

| Song | Before | After |
| --- | --- | --- |
| The First Noel | 0 of 57 at every preset | 53 / 54 / 53 / 52 of 57 |
| Joy to the World | 3–4 of 41–42 | 38 / 37 / 37 / 38 of 41–42 |
| What Child Is This | 0 of 24–26 | 23 / 23 / 24 / 26 of 24–26 |

The take, the words, the timing, the level and the backing are the live song's; built without the bend, `apply.py --check` gives the approved MP3s sample for sample. The stems are stereo: inside a bent melisma both channels carry the bent mono sum. Approving the update replaces the live vocal; the children keep their progress (arch 10.7).

## For the parent to decide by listening

Open `feasibility/melisma-probe/out/listen/index.html` on this machine (or run `deploy.sh` to put it on the piano server at `/melisma/`). Each song has a button for every melisma that moves all its players to just before it.

1. **Are the tics gone?** The First Noel, version C or D against B.
2. **C or D?** Only the melismas changed (some joins crossfade), or the whole vocal through the resynthesis (no joins).
3. **Do the short ones sound right bent?** What Child Is This, version C: its melisma notes are 0.14 s. The yellow buttons mark melismas with a short note.
4. **Is a split-vowel take worth its words?** Version F, where there is one.

## Not done

- Nothing was listened to here; every number is from pitch tracking, the word check and Whisper.
- The bend isn't in the media skill. HANDOFF.md says where it goes.
- Only the 100% vocal was bent for the listening page; the 50% and 75% presets were bent and measured for one song.
- The split rule is by spelling ("gua-uard", "my-yrrh"). A pronouncing dictionary would split by sound; not tried.
- Melismas of four notes or more (a run) weren't in the test songs; the one such song, Angels We Have Heard on High, has its own syllables from the source (v0.33).

## Run it again

```bash
bash feasibility/melisma-probe/setup.sh                                   # Praat (parselmouth) in the probe's own venv
tools/.venv/bin/python feasibility/melisma-probe/bend.py content/incoming/christmas/the-first-noel.yaml --kinds bend,split
tools/.venv/bin/python feasibility/melisma-probe/bend.py content/incoming/christmas-2/what-child-is-this.yaml --kinds bend,split --preset 50 --engines psola
tools/.venv/bin/python feasibility/melisma-probe/render.py content/incoming/christmas-2/what-child-is-this.yaml --short 0.3   # GPU, about 8 minutes
tools/.venv/bin/python feasibility/melisma-probe/build_page.py            # out/listen/index.html
```

`out/` (audio, reports, YuE2 takes) and `.venv/` are not in git.
