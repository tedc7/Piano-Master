# Arranging, levelling and the piece file

## The piece file

One YAML file per arrangement, in the batch folder (and later `content/pieces/`):

```yaml
# Header comment: what the piece is, where the notes came from, and what you changed
# (simplified bars, octave moves, cut sections, and why).
title: Minuet in G
composer: Christian Petzold
kind: library              # core = written for a skill (placeholder map only, by us); library = everything imported
genre: classical           # folk, hymns, kids, classical, pop, lesson-pieces…
level: Level 2             # your estimate, shown to people; the analysis decides unlocking
hands: RL                  # R, L or RL, as the student plays it
phraseBars: 4              # rewind phrases: 2 bars at Prep levels, 4 from Level 1
song: minuet-in-g          # several arrangements of one song share this…
songTitle: Minuet in G
version: Intermediate      # …and each has its own version name
source: {site: …, url: …, id: …, file: …}
license: {composition: public-domain, edition: …, evidence: …}
abc: |
  X:1
  T:Minuet in G
  M:3/4
  L:1/8
  Q:1/4=100
  %%score {RH LH}
  K:G
  V:RH clef=treble
  V:LH clef=bass
  [V:RH] |: d2 GABc | …
  [V:LH] |: [G,B,D]4 A,2 | …
```

ABC features the build understands:

| Write | Means |
| --- | --- |
| `!1!C` … `!5!C` | A printed finger number (kept; the generator fills the rest) |
| `w: Twin-kle twin-kle` | Lyrics under the notes above, one syllable per note; `w:` lines for later verses go under the repeat |
| `"C" C2 "G7" G2` | Chord symbols (the chord pad plays them when there are no stems) |
| `{g}A` | A grace note, drawn, not scored |
| `(3ABc` | A triplet |
| `"_L"B` | This note is played by the left hand, though it's on the upper staff (`"_R"` the other way) |
| `[K:clef=treble]` | A clef change partway through a staff |
| `\|: … :\|`, `[1 … :\|[2` | Repeats and first and second endings |
| `Q:1/2=60` | Tempo in any beat unit |
| `%%score {RH LH}` | The grand staff: the first voice is the right hand, the second the left |

## Levelling

Run `check`: its **map point** and **featured skills** come from the skill map's constraints (song
analysis, §6.8), and they decide when the piece unlocks. Your `level:` is the description people
see. Use the method-book levels (Prep A, Prep B, Level 1 … Level 10 for Faber; the RCM levels are
close). If the analysis says **beyond the map**, the piece waits for the map to grow. That's fine
for a library batch, but say so in the review.

Rough guide at the early levels:

| Level | Typical |
| --- | --- |
| Prep A–B | One hand at a time, then hands taking turns; five-finger positions; quarter, half, whole notes; C and G positions |
| Level 1 | Simple hands together (a held note or a fifth under a melody); eighth notes; a hand shift |
| Level 2 | Hands together throughout; one sharp or flat; 3/4 and 4/4; dotted quarters |
| Level 3–4 | Scales in the pieces, broken chords, two-voice textures, a few accidentals |

## Arranging to a level

- **Keep the tune intact** and recognisable; simplify the accompaniment first (block chords to
  single notes, Alberti bass to held chords, octaves to single notes).
- **One idea per arrangement.** A beginner version of a famous piece is usually the theme only, one
  hand, in a comfortable key (C, G or F), 8–16 bars.
- **Stay on 61 keys (C2–C7).** Move low bass notes up an octave where it doesn't spoil the line,
  and say so in the header. `check` warns when a piece needs 88 keys.
- **Several levels of one song** (Beginner, Intermediate, Advanced) share `song:`, each with its
  own `version:`. Make each a real step up, not just longer.
- **Endings**: a cut arrangement should end on the tonic. Add the theme again or a closing bar,
  and say so.
- **Phrases**: `phraseBars: 2` at Prep levels, 4 from Level 1. Rewinds go back a phrase.
- **Fingering**: keep printed fingering from the edition (`!n!`); the generator fills the rest
  (fingeringSource `mixed` or `generated`). Add a finger where the generated one would be awkward:
  it's kept.
- **Chord symbols** in quotes above the melody for melody-only arrangements, so the chord pad has
  something to play. Two-hand pieces don't need them.
- **Lyrics** (songs): one syllable per note, merge melismas onto one note, verses under the repeats.
