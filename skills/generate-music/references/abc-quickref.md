# YuE2 native ABC: quick reference

YuE2 accepts a score only in its own **bounded two-voice ABC dialect**. The full rules are upstream, in the engine clone:
`~/engines/yue2/YuE/skills/yue2-music/references/abc-editing.md`. `generate_music.py` validates every score with the upstream checker (`abc_tools.py`) before any GPU work. To check a file by hand:

```bash
python3 ~/engines/yue2/YuE/skills/yue2-music/scripts/abc_tools.py inspect my.abc
```

## Shape (header lines are fixed and in this order)

```abc
X:1
T:
M:4/4
L:1/16
Q:1/4=96
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Vocal
"C"E4E4G4G4|"F"A4A4"C"G8|
V: Ins
Z2|
% chorus
V: Vocal
...
V: Ins
...
```

- `T:` stays blank. `Q:` is an integer quarter-note BPM. `K:` is a standard major or minor key (`C`, `G`, `F#`, `Am`, `Bbm`).
- The music comes in **groups of 1–4 bars**: a `V: Vocal` line, then a `V: Ins` line with the **same number of bars**. Every line ends with `|`.
- `% verse`, `% chorus`, `% bridge`, `% intro`, `% interlude`, `% outro` comments mark sections before a group.
- `Vocal` carries the sung melody **and all chord symbols**. `Ins` is a monophonic instrumental melody or rests (`Z` = one bar of rest, `Z2`…`Z4` = several bars).
- Both voices are **monophonic**: no stacked notes, no tuplets, grace notes, repeats, slurs, decorations, or `w:` lyric lines.

## Notes and durations

- Pitches: `C`=C4 (middle C), `c`=C5, `c'`=C6, `C,`=C3. Accidentals: `^F` sharp, `_B` flat, `=F` natural; they last to the end of the bar (and apply across octaves).
- Length = multiplier × `L:` unit. Allowed multipliers: 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48.
  With `L:1/16`: `C4` quarter, `C8` half, `C2` eighth, `C12` dotted half, `C16` whole. A 4/4 bar totals 16 units (with `L:1/32`, 32 units).
- Tie with `-`: `C8-C4` (12 units as one note). Rests: `z4` (quarter rest). Other lengths: `z8z2`, `C8-C2`.
- Chords: a quoted symbol right before the note or rest where it starts: `"G7"B4`. Qualities: major (none), `m`, `dim`, `aug`, `7`, `maj7`, `m7`, `dim7`, `m7b5`, `sus4`, `sus2`, `6`, `m6`, `7sus4`, `m(maj7)`; slash basses such as `C/E`. A chord change in a held note needs a tie: `"C"E8-"Am"E8`.

## Lyrics and the score

Lyrics go in the separate `lyrics` field, never in the ABC. Keep the same sections, in the same order, in both. YuE2 fits the words to the notes itself; there is no syllable-to-note alignment channel, so give roughly one syllable per melody note and let long notes carry held vowels.
