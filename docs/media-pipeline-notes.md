# Media pipeline notes (M8)

Notes from building the media skill (`.claude/skills/make-media/`, `tools/media/`) and running it on
the first batch, five kids' songs (`content/incoming/kids-songs/`, Sep 29, 2026). Each entry says
what got in the way and what fixed it, or what would. They are in the order they came up.

## The batch

| Song | Source (checked against) | Backing | Notes |
| --- | --- | --- | --- |
| Five Little Ducks | NancyMusic.com lead sheet, G major (moved to C) | `kids` | Public-domain status rests on "traditional": no printing before 1930 found. The parent decides |
| The Itsy Bitsy Spider | MakingMusicFun.net lead sheet, G major, 6/8 | `kids` | First printed 1910 |
| London Bridge | MakingMusicFun.net beginner piano, C | `kids` | Four traditional verses |
| Row, Row, Row Your Boat | MakingMusicFun.net guitar sheet (G, 3/4), written in C, 6/8 | `round` | Sung three times; the backing is the round |
| Jesus Loves Me | The Cyber Hymnal's four-part setting, C, marked public domain | `hymn-strings` | Verses 1, 2 and 4; the child plays the melody |

The lead sheets are free for instruction but not openly licensed, so the notes were retyped and the
sheets used only to check them (arch §10.2).

## Issues

1. **Reading the reference scores.** The free lead sheets are PDFs with the notes as graphics, so no
   text or MusicXML could be taken from them. They were read as images, the Cyber Hymnal's at 220 dpi
   to tell the four voices apart. Fine for 8–16 bar songs; a longer piece needs a MusicXML source.
   Hymnary.org's own pages refused scripted fetches (as in the sync probe), but its media links for
   the Cyber Hymnal PDFs worked.
2. **Five Little Ducks' public-domain status.** It's traditional with no known author, but no
   printing before 1930 was found (its fame dates from Raffi's 1982 recording). It's flagged in the
   piece file for the parent.
3. **A hymn needs its four parts for the backing, and the child plays one.** The piece file had no way
   to say "the score has more voices than the child plays". Fixed: `play: melody` builds the child's
   melody-only notation from the full score, and the media skill reads the other voices from the
   full score (`bc.full_notation`).
4. **Rubber Band output 90 ms late.** The words-mode map began with an anchor at 0.05 s (the "Oh").
   After the held-offset trim that became a time-map point at sample 0, and Rubber Band's whole output
   came out about 90 ms late. Fixed: points in the first half second are dropped.
5. **The correcting pass can make things worse.** Fixed: the second pass is kept only when it
   measures better than the first.
6. **The planned bleed check measured the wrong thing.** Measuring the vocal stem in the score's
   rests fails on children's songs, which have almost no rests; the only "rest" was the lead-in,
   where it measured YuE2's timing, not bleed. Replaced by a least-squares estimate of YuE2's
   accompaniment in the vocal's spectrogram, away from the voice's harmonics. It's calibrated by
   mixing known amounts back in (−32 dB as rendered, −22 dB with 10% added). The −25 dB threshold is
   a first guess: tune it from what the parent hears.
7. **The word check was too strict as a pass rule.** A single two-word stretch failed a take that
   was 98% on pitch and 14 ms from the beat, and every song would have rendered a third take.
   Changed: words off the staff fail above 10% or in the first 15 s; a stretch elsewhere is a flag
   for the listen.
8. **Repeated lyrics fool the word map.** The Itsy Bitsy Spider's first and last lines share their
   words, and the lyric aligner put a whole line in the wrong place (1.6 s off). The pitch-DTW map
   was right. Running both maps per take and keeping the better one handles it; the words map alone
   would fail this song.
9. **YuE2 skips the rests after the "Oh".** With a half-beat pickup there are 4 beats of rest between
   the "Oh" and the first word, and YuE2 sang through them, starting about 2 s early. Alignment
   corrects it (the offset is held before the first anchor). A shorter lead-in bar for short
   pickups would give YuE2 less to skip.
10. **Alignment is slow:** about 2.5 minutes per take and map, most of it pitch tracking (pYIN)
    repeated on the same audio. Caching each stem's pitch track would roughly halve it. It runs in
    the background, so it's not urgent.
11. **Short, fast songs are harder for YuE2.** The Itsy Bitsy Spider (36 s, 6/8) needed a third take;
    its first two sang words off the staff early in the song. At its real tempo (issue 12) it passed on the first take.
12. **The first run's tempos were half the sung speed.** The parent heard it at once: "the 100% setting
    sounds like 50%". The tempos had been guessed from the teaching sheets ("Andante",
    "Moderato"), which write these songs in note values twice as long as the sung beat. Published
    recordings put London Bridge and Five Little Ducks at about 100–118 half notes a minute, Row,
    Row at 106–112 dotted quarters, and Itsy Bitsy at 86 dotted quarters. Fixed: new tempos with
    their evidence in `tempoSource:`; London Bridge and Five Little Ducks written in cut time, as
    sung; the import skill's tempo rule (100% is the performance tempo, from a metronome mark or
    recordings) and a `check` warning for a song without a `tempoSource`.
13. **YuE2 is told the felt beat.** It only takes quarter-note tempos. A song in cut time at half =
    100 went to it as 2/4 at quarter = 100 (every length halved), so its style says "100 BPM"
    like the songs it learned from, not 200.
14. **Stale renders and stale media.** Changing a tempo didn't make the old YuE2 renders stale, and
    the content build's media guard compared only the playback length, which a tempo change keeps.
    Fixed: a render made from another score or other lyrics is redone, and the build refuses media
    made at another tempo.
15. **At the real tempos, YuE2 misses more often.** Only Itsy Bitsy and Row, Row passed in the first
    three takes. The others kept the melody but put words on other notes. Jesus Loves Me's first
    take was 96% on pitch and 10 ms from the beat, with 60% of its words off the notes. The
    whole-song word alignment had also drifted on its nine repeats of "Yes, Jesus loves me" (21
    words forced, some placed 4.8 s off). Fixed: words are aligned phrase by phrase in the aligned
    vocal, which can't drift. The take still had most words off, so the check was right. Added
    `--max-takes` to render up to three more seeds for the songs that still fail.
16. **Slip rules counted notes, not time.** The pass rules from the sync probe (a run of 4 notes on
    other pitches; any stretch of words off the notes in the first 15 s) were tuned on slow hymns.
    At a children's song's real tempo 4 notes last under a second, and Five Little Ducks failed six
    takes for slips like that while 93% on pitch and 22 ms from the beat. Changed: a slip fails only
    when it lasts 1.5 s or more; shorter ones are flags for the listen.
17. **The side review page went away.** The parent's review now happens in the app itself (M7:
    Config › Review list), so the separate listening page and test app (`/review/`) were removed.
18. **Batch-wide approval lost songs the parent hadn't heard.** The first review list approved the
    ticked songs of a batch and discarded the rest, deleting their staged files. The parent listened
    to two songs, unticked the others to approve just the good one, and the four unheard songs were
    gone (still on the dev box, so they were resubmitted). Fixed: one list of waiting songs, each
    with Approve, Needs improvement (a note stored for the skills: `import_song.py feedback`) and
    Never allow. A song stays until decided, and a fixed song replaces the one sent back.
19. **The recording's tempo was too fast for YuE2's words (the first parent note).** Five Little Ducks at
    Raffi's pace (half = 100) passed every check, but the parent heard words running together and
    sent it back: "probably 80% of this current tempo". Its eighth-note pairs ("lit-tle", "duck-ies")
    come at about 6.7 syllables a second there. Fixed: half = 80, re-made, resubmitted with the note
    beside it (it passed on the first take). The parent sent London Bridge and Row, Row back the same
    way ("90% of current"): half = 97 and dotted quarter = 94. So for YuE2 to sing the words clearly,
    a song's 100% sits about 80–90% of the recordings' pace. The import skill's tempo rule should say
    so, and the word check doesn't hear slurred words that land on time.
20. **Deleted songs moved into the review area.** The first version kept a separate deleted list, and
    the files in `removed/`. Now "Never allow" and "Delete" both make a song deleted in staging (the
    library holds only approved songs). Under Deleted songs in the Review list it can go back to
    review, be sent for improvement (to be corrected), or be forgotten.

## Results (at the real tempos)

| Song | Tempo | Take kept | Notes on pitch | On the beat, 100% / 50% (median) | Tuning | Checks |
| --- | --- | --- | --- | --- | --- | --- |
| Five Little Ducks | cut time, half = 100 | 2 of 4 | 93% | 10 / 23 ms | +3.5 c | pass |
| The Itsy Bitsy Spider | 6/8, dotted quarter = 84 | 1 of 3 | 92% | 10 / 23 ms | +4 c | pass |
| Jesus Loves Me | quarter = 112 | 4 of 4 | 99% | 8 / 21 ms | +3 c | pass; two short word stretches flagged; the cello 24 ms from the beat (target 20) |
| London Bridge | cut time, half = 108 | 4 of 4 | 91% | 8 / 30 ms | +1.5 c | pass; one short word stretch flagged |
| Row, Row, Row Your Boat | 6/8, dotted quarter = 104 | 2 of 2 | 94% | 6 / 32 ms | +2 c | pass; one short word stretch flagged |

The 50% figures are in the stretched time the child hears (the sync probe had 13–34 ms). The media
is 6–23 MB a song for the four presets. The batch was submitted with `import_song.py submit`; all
five passed the server's intake and wait in Config › Review list (package a55bfcd03029). Still to
come: the parent's listen, which tunes the `kids` style, the bleed threshold and the slip rules.
