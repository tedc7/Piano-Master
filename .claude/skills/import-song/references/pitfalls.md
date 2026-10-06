# Known pitfalls (from the classical batch, content/incoming/classical/NOTES.md)

- **LilyPond sources**: python-ly shifts bars (it mishandles `\partial` and volta alternatives), and
  LilyPond isn't installed. Use the edition's MIDI to check pitches, and take the notes from
  another format.
- **ABC accidentals carry through the bar.** A score generated from MIDI needs its accidentals
  re-checked: `^F` early in a bar sharpens every later F in that bar unless you write `=F`.
- **MIDI** has no spelling (F♯ vs G♭), no voices and no ties, and its rhythm is quantized. Use it to
  check, not as the source, unless nothing else exists; then check every bar by eye.
- **Grace notes** are drawn but never scored. Write them as `{g}` before the note they lead into.
- **Tempo**: `Q:1/2=66` and `Q:3/8=60` are read correctly (beats per minute of that note). Say the
  tempo the child should aim for, not the concert tempo, if they differ, and explain it in the header.
- **Repeats** show as passes, not verses, unless there are lyrics (verses come from `w:` lines).
- **D.C., D.S., segno, coda and Fine aren't read yet** (only repeat signs and first and second
  endings are). Write the jump out as plain measures, or the song plays without the repeated part.
- **Two arrangements of one song** share `song:` and have their own `version:`, or the Library
  shows them as two songs.
- **The matcher** takes a wrong key that matches the *next* note's pitch as that note played early.
  For example, F played as G, just before a written G. Diagnostics then can't see the mix-up. This
  isn't an import problem, but it is why a very stepwise beginner piece can hide note confusions.
- **Wide first bars** (all sixteenths) are fine now: the idle view keeps bar 1 on screen.
- **Things the notation can't hold yet**: trills and other ornaments beyond grace notes (write the
  main note), pedal markings (kept out until the pedal scorer, Phase 3), dynamics (kept for later,
  not scored), and 8va lines (write the real octave).
- **Open Hymnal ABC files are Latin-1**, not UTF-8 (`Kinderchöre`): re-encode them
  (`iconv -f latin1 -t utf-8`) before `convert`. Their four-part settings work with `play: melody` as
  they are. Under the music they print a refrain's words once, and later verses' lines show `*` where
  the refrain's pickup words go: repeat the refrain under every verse. `compare` can't read their
  four voices: build both the source and the piece with `notation.parse_abc` and `build_notation`
  and compare their notes (the melody is the notes marked `isMelody`).
- **A long melisma** ("Glo-o-o-ria") is sung as one held note by YuE2. To keep the run, write a
  syllable under each note ("Glo- o- o- …"); the word check then fails it, so say so in the review.
