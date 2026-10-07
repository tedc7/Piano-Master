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

21. **Row, Row still garbled at 90% (the second parent note, Oct 1).** At dotted quarter = 94 the
    kept take passed (6% of words off), but the parent still heard garbled words and asked for
    another 10%: dotted quarter = 85, about 82% of the recordings' pace, the bottom of the range in
    19. Four takes this time (`--takes 4`): one failed on bleed (-15 dB), one on pitch, and the kept
    one (take 2) sang every note on pitch with no words off the staff and 3 ms from the beat. The
    take-to-take spread is wide, so for a song sent back for its words, render four takes, not two.

22. **Vocals for the curriculum songs (the parent's notes, Oct 1).** The parent sent back 43 live
    Prep A songs, asking for vocals (and for Two-Key Hops, words too). The media tool would have
    given 22 of them a strings pad and cello built from the song's own hands (the `pad` default for
    any genre it doesn't know), and By the Moonlight YuE2's own backing (folk). Whether curriculum
    songs get backings is still undecided (Next steps), so they get the vocal alone: a new backing
    style `none`, the default for `genre: studies`, and set on By the Moonlight in its file. The app
    already plays its own piano with stems, so a vocal-only song still has its music; the client
    needed one change to load stems without a backing (v0.30), deployed before the songs went back
    to the review list.

23. **The curriculum songs sang badly at first: 1 of 13 passed.** Three causes, fixed in the tools:
    - *Key:* `tonal_key` chose only between the written signature's major and minor. The black-key
      songs are written in C with sharps, so YuE2 got K:C and a C-major "Oh" a semitone from a song on
      C♯ and D♯. Now, when the signature names neither, the key comes from the notes: the key on the
      last note that holds most of them, sharps for a song spelled in sharps (C♯ major, D♯ minor).
    - *Range:* the vocal sang the left hand where it's written, down to C♯2 (Steady Steps). Each
      phrase now moves by whole octaves into A3–F5 (`yue2.singable`); the checks compare pitch
      classes, so the vocal still matches the staff.
    - *Repeated notes:* Steady Steps ("walk, walk, walk, walk" on one key) has too few pitch changes
      for any 3 s alignment window, so no take could be aligned at all. In the word mode its words
      now place it, and the take is flagged "timed by its words only" for the listen.
    Also: one song with no usable take no longer stops the batch. After the fixes, Ready to Play went
    from 75% to 94% of notes on pitch and The Finger Number Song from 69% to 100%; the two-note songs
    of four bars (Two-Key Hops) are still poor, which suggests YuE2 needs more song to settle into.

24. **The parent's listen to the first 22 (Oct 3): 18 approved, 4 sent back.** What the checks missed:
    - *Tap and Stretch, Shout and Whisper:* the word check had failed them (33–35% of words off) and
      they went to the review list anyway, as "words drift, the check is least reliable on slow
      songs". The parent heard the drift. Above about 25%, the check is right: don't submit them.
    - *Steady Steps, "garbled the last few words":* the last three "stomp"s were 0.3–0.7 s early and
      two of them were placed with low confidence. The word check left out low-confidence ("forced")
      words, so a garbled word counted for nothing; it reported 6%. Now a word the aligner can't place
      counts as off.
    - *Sleepy Owl, the first "whoo" way too high:* the singer sang the song an octave below what it
      was asked, except that one held note, sung where asked: two octaves above the rest. The pitch
      check compares pitch classes, so it passed. The cause was ours: the range fix of item 23 moved
      whole phrases, and that phrase held the right hand's "whoo" and the left hand's next bar, so
      lifting the left hand lifted the "whoo" to C♯5. Now each run of one hand's notes moves on its
      own, and a new check fails a take with a held note (0.8 s or more) sung in another octave from
      the rest (shorter ones are flagged). The second "whoo" sung as "woaaaa" is YuE2's own vowel on a
      long held word: new takes, and the word check now counts such a word.
    Also: twelve seeds instead of six, so a song can be given up to 12 takes (`--max-takes 12`).
    Re-rendered with up to 12 takes: Shout and Whisper passes; Steady Steps (94% on pitch, 6% of words
    off) and Two-Key Hops (62% → 100% on pitch, with the hand-run fix) fail only on bleed, which the
    parent accepted on four songs; Sleepy Owl has every note on pitch and its two held "whoo"s are the
    20% of words off. Those four went back to the review list. Still held: Tap and Stretch (81% on
    pitch at best) and Pointer and Middle (47% of words off). Both are short songs of identical words
    on the same two keys, repeated, which YuE2 keeps blurring; they likely need different words.

25. **The second listen (Oct 4): octaves, and words that stutter.**
    - *Pattern Up, Pattern Down, "down an octave" sung going up:* our range fix again. Moving
      phrase by phrase put the left hand's two phrases (E3, then E2 "down an octave") onto the same
      pitch, so the leap the words describe vanished. Now each hand's whole passage moves together
      when it fits the range (A3–F5), so a song's own leaps stay leaps; only a passage wider than the
      range is moved phrase by phrase. Two-Key Hops' "hop up high" and "hop down low" now go where
      they say too.
    - *Bouncing Ball, an octave switch on the first "home":* the input was right; YuE2 jumped on the
      held note by itself. That take predates the octave check (item 24), which now fails it.
    - *Steady Steps, "a long stuttering 3/4 through":* the left hand's four "stomp"s in a row, the
      same place as the earlier "garbled". Four identical words on repeated notes are where YuE2
      stumbles (Tap and Stretch and Pointer and Middle too), so the words changed: "Big bear
      march-es, stomp-ing feet, boom!".
    - *Tap and Stretch, Pointer and Middle:* new words at the parent's request, a rainy day and a
      rabbit, with no word repeated four times.
    - *A false failure from item 24's word rule:* counting unplaced words as off failed every take of
      Pattern Up, Pattern Down (73%+), because its words are letter names ("E, D, C"), which the
      aligner can't place however they're sung (16 of 22). Letter names are now left out of the share
      and flagged for the listen; take 1 then passed (every note on pitch, 7 ms from the beat).
    - *A take the parent rejected that the checks passed* (Pointer and Middle, "first word gets mixed
      up"): `--skip-take N` keeps it from being chosen again.

26. **Pattern Up, Pattern Down: YuE2 doesn't follow octave leaps, and our tracker couldn't tell.**
    With the eagle and gopher words (the parent's idea), every take sang the words well, but the
    octave check flagged the same held notes in all 24 takes, in both registers (with
    `media: {vocal_octave: -1}`, a new per-song setting, too). A look at the voice's spectrum
    showed why: the pitch tracker read most notes at C2-E2, an octave or two below any real voice,
    so its octaves meant nothing; the spectrum (energy an octave below, at, and above each note)
    showed the singer taking the right hand's climb *down* ("soaring to the sky" an octave below
    "eagle spreads") while getting the left hand's drop right. The octave check now uses the
    spectrum (`align.sung_octave`): on the takes the parent approved (Bouncing Ball, Sleepy Owl,
    Canyon Echo, Row, Row) it finds no octave errors, and on this one 11. The pitch check itself
    compares pitch classes, so the tracker's octave errors never affected it. Up to 24 seeds now.

27. **The Christmas batch (Oct 5): 4 of 15 pass, and fast repeated-note songs defeat both
    alignments.** Ten hymnal carols (backing: their own alto, tenor and bass) and five songs with the
    new `holiday` style. Every backing was on the beat (worst part 6 ms). With up to 6 takes, Silent
    Night, Hark! The Herald Angels Sing, O Little Town of Bethlehem and Joy to the World passed; seven
    more missed only the word check, by a little (11-20% of words off, the limit is 10%), all on pitch.
    Jingle Bells and Up on the Housetop failed in a new way: aligned by pitch, every take was 89-98% on
    pitch and on the beat with 60-80% of words "off"; aligned by the words, the other way round. Both
    are long runs of one repeated note ("jin-gle bells, jin-gle bells"), which the pitch windows can't
    place (note 23's repeated-note case, at speed). Slowing them (half 100 to 88, quarter 120 to 104)
    didn't change it, so the parent's listen decides. For Up on the Housetop the tool had picked a
    words-aligned take 54% on pitch and a third of a second off the beat; `--skip-take 6` chose the
    pitch-aligned one, on the beat. The Gloria run, sung with an "o" on each note, keeps its melody
    (96% on pitch) and fails the word check, as expected.

28. **The Gloria run, sent back (Oct 6): YuE2 had been given one word.** The parent heard the vocal
    stop singing the "o" run too early, with many words off after it. The export joins a word's
    syllables for YuE2's lyrics ("it-sy" -> "itsy"), so the 16 notes of "Glo-o-o-...-ri-a" reached
    it as "Glooooooooooooooooria", with nothing to say it was 16 notes; and a line break at each
    phrase start had cut words in two ("Gloooooooooo / ooooooria", "De / o!"). Now a run on one vowel
    keeps a hyphen before each note in YuE2's lyrics ("Glo-o-o-o-...-oria"; the aligner still gets
    the plain word), and a phrase that starts inside a word breaks the line at the next word.
    Re-rendered: the first take passed (98% on pitch, 7% of words off, against 31-34% before), and
    went back to the review list under the same id.

29. **The First Noel, sent back (Oct 6): "the 2nd half got 1 syllable behind".** The kept take's
    words drifted from 53 s to 91 s, all of verse 2, which starts "They look-ed up": the hymn sings
    the old "-ed" on its own note (the hymnal's "look-èd"), but the export joined the syllables into
    "looked", which YuE2 sings in one. It ran a syllable early from there to the refrain. Now a sung
    "-ed" keeps its hyphen in YuE2's lyrics, as a vowel run does ("They look-ed up"); after a t or d
    ("want-ed") the word already says it. Re-rendered under the same id.

30. **The second round of curriculum vocals (the parent's notes, Oct 6).** 42 more live songs sent
    back for a vocal, like note 22. Five had no words fit to sing and got new ones at the parent's
    request: hens pecking grain (Thumbs Take Turns), a lazy turtle (Warm-up: Hop to the Next Key), a
    short pig reaching for a pie (Warm-up: Thumb Walk), a game of checkers ending in checkmate
    (Warm-up: Checkers), and green aliens hopping to planet Zorg (Space Hops, whose words were the
    letter names). When the Saints ("popular, should have backing") got chord symbols (C, C7, F, G7)
    and the `kids` style; folk's default is YuE2's own backing, which only follows chords it hears.
    Mary Had a Little Lamb, Twinkle Twinkle and Are You Sleeping get the `kids` backing from their
    chords too, as their genre's default.
    - *A little word before a long note: the aligner's miss, not the singer's.* The off words of the
      new songs kept landing in the same places in take after take: "nib-bles on **a** | leaf",
      "wants **a** | pie", "crowned **a** | king". It looked like YuE2 slurring the article into the
      held word, and three songs got new words for it, but Whisper (below) heard "on a leaf" in five
      of six takes: the lyric aligner can't place a word that short (it gives "a" no length at all),
      and counts it off. The words went back as they were.
    - *Mary Had a Little Lamb: 30% "off", every word sung.* Its first take was on every note and
      17 ms from the beat; the aligner put "fleece" before "its", stretched "little" over the start
      of "lamb" (the same note, both starting with "l"), and couldn't place "a". Most of the batch's
      failures were like this: 9 of 43 passed the first run, nearly all the rest on "words off" alone.
      So each take now has a **words-heard check**: Whisper (small.en, the lesson voice's check,
      `tools/media/hear.py`, in the aligner's venv) transcribes the take, and the share of the song's
      words it heard, in order, goes into the take's checks and the choice between takes. Scattered
      words the aligner can't place no longer fail a take when Whisper hears 90% or more of the
      words; a stretch of 1.5 s or more still fails it anywhere in the song (that's a drift, The
      First Noel's kind, which Whisper can't hear because every word is still sung); and a take
      Whisper hears under 75% of fails however its words were placed (a garble the aligner can
      miss). Between 75% and 90% it's flagged with what Whisper heard. Whisper also catches what
      no check did: takes that sing the song again after it ends ("its fleece was white as snow,
      little pig").
    - *The vocal sang on after the song ended.* The packaged vocal kept everything the take sang
      after the last note: Up and Down the Staff had 4 s at full voice past the end, and five more
      had a loud tail. Packaging now keeps the last note's release (0.6 s), fades it out (0.4 s) and
      silences the rest, at every tempo preset, the file's length unchanged.
    - *Two songs whose words fought the notes.* Pony Trot's "Trot, trot, trot, go!" (three of one
      word, note 25's trap) failed 12 takes; "Clip-pe-ty clop! Gal-lop-ing, whoa!" gave a take on
      every note and 15 ms from the beat. C and G Seesaw's "see-saw, see-saw" on four Gs was sung up
      and down like a seesaw in all 24 takes; with "hold it up, then down!" two takes of the next 12
      sang it as written. Words that describe a different tune from the notes pull YuE2 off them.
    - *Repeated phrases still fool the aligner* (note 8): Kangaroo Skips' "space to space" twice in
      a row put the first onto the second in every take, and its 15 s length puts the whole song in
      the first-15-s rule. Submitted flagged, for the listen.
    - *Result:* 37 of 43 pass, 6 go to the review list flagged (The First Noel's refrain runs, Middle
      C Stomp and Drum Beats just under the line, C and G Seesaw's bleed at -22.9 dB, Pony Trot and
      Kangaroo Skips on the aligner's word share), against 9 of 43 on the first run's rules.
    - *When the Saints: a song's own "Oh," was dropped from the word check.* Every take was 61-89%
      "off", from the first word. The export takes the sung lead-in "Oh," out of the aligner's word
      list by dropping every word equal to "Oh,", so the song's own opening "Oh," went too, and each
      later word was paired with the beat of the one before. Now only the lead-in is dropped. Jingle
      Bells and Up on the Housetop have "Oh," in their refrains, so the same bug shifted their word
      check after each refrain: it likely explains their "new way" of failing in note 27 (on pitch,
      60-80% of words off), more than the repeated notes do. Alignments now record the word list
      they were made with (`wordsIn`), and `vocal` aligns a take again when the words change.

31. **The parent's listen to the 43 (Oct 7): 34 approved, 9 sent back.**
    - *New words asked for:* big dinosaurs stomping (Middle C Stomp: "some vocals didn't come
      through"), two girls on a seesaw (C and G Seesaw, garbled), three frog friends croaking high and
      low (Three Friends: "bass" was sung like the fish), a hungry kangaroo hopping home to dinner
      (Kangaroo Skips: the letters and "space to space" mixed up), and the brother still in bed in
      place of Are You Sleeping's "ding, dang, dong", which garbled. Four of the five had been flagged
      by the checks; the words the parent heard as wrong were the ones the checks pointed at.
    - *A wrong letter name, heard by Whisper and let through.* B and C sang "E and G" for "C and G",
      Bunny Hops "to E" for "to D". Whisper had written exactly that, but the letters' share counted
      each as one letter off in a song's worth. Now a letter name Whisper hears as another letter name
      fails the take ("Whisper heard the wrong letter name: E for C"), with Whisper's spellings of
      sung letters ("middle sea", "bee") counted as the letters they are.
    - *Twinkle Twinkle's backing stopped whenever the left hand did.* The parent guessed YuE2 was
      taking the bass notes for the backing; it was ours. Without chord symbols the `kids` backing
      takes its chords from the left hand, and this arrangement shares the tune between the hands,
      so every right-hand half bar had no chord. It has chord symbols now (G, C, D), and the
      notation builder reads them from every part: it had read only the first, so symbols written
      over the left hand's bars were dropped without a word.
    - *The First Noel, "some vocals didn't sing to lyrics": would a FluidSynth backing let YuE2 focus
      on the vocal?* It has one already (the hymnal's own parts on strings and cello); YuE2 always
      sings over an accompaniment of its own, which is separated out and thrown away. What can be
      changed is what that accompaniment is: its style now asks for "a very soft sustained string
      pad, sparse and quiet in the background" and "very clear words", to see whether a thinner
      arrangement gives a cleaner separated vocal. A render now counts as stale when the piece asks
      for a style it wasn't sung in (only the score and lyrics counted before).
      The result: take 8 passed every check (98% of notes on pitch, 8% of words off, every word
      heard), the first take of this carol to pass in 18; one song isn't proof, but it's the first
      thing to try on a long song that keeps drifting.
    - *Choosing between failing alignments.* Bunny Hops and B and C each kept a take's worse
      alignment (85% on pitch with the first word missing; 81 ms off the beat) over its better one,
      on a score a hundredth higher. Takes are now ranked by passing, then the fewest failed checks,
      then the score.
    - *Result:* all nine re-rendered; eight pass, and B and C's take (the letters right, on the
      beat) is over only on bleed, by under 1 dB.

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
