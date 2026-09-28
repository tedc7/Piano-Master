# YuE2 Lyrics & Melody Input — Agent Instructions

## 1. How YuE2 reads the input

YuE2 pairs lyric syllables with Vocal notes by itself; there is no field or notation that binds a syllable to a note. Your job is to hand it a score and lyrics that pair up unambiguously.

- **Request fields:** `style`, `lyrics`, `cot`, `seed`, `abc`. There is no phoneme, alignment, BPM or reference-audio field.
- **Mode:** to keep the exact melody, send chord-free ABC with `cot="melody"`. `cot="melody"` does not strip chords for you; remove them first. Use `full` only with native chord symbols, when chords must be fixed.
- **Lyrics:** plain text in playback order, with section tags such as `[Verse]` and `[Chorus]`. No hyphens, underscores or note markers.
- **Never send** `w:` lyric lines, phoneme annotations, or any non-native ABC to YuE2. Keep `w:` in our own source files and strip it at conversion.
- **Tempo:** set it in the ABC `Q:` field and state the same BPM in `style`.

## 2. Core rule: one Vocal attack per sung syllable

In every section, the number of note attacks in the Vocal voice must equal the number of sung syllables in that section's lyrics. This is our pipeline rule, not a documented YuE2 requirement; it removes the guessing that causes words to drift onto the wrong notes.

**Counting attacks (Vocal voice only):**

- A note token is one attack: `C8`.
- A tied continuation of the same pitch is not a new attack: `C8-C8` is one attack.
- Rests (`z`, `Z`) are not attacks.
- Count after merging ties; never count raw tokens.

**Counting syllables (in this order of preference):**

1. The source file's `w:` lines. The editor's splits, melismas and elisions are ground truth for this tune.
2. A hymnal or published edition of the same text.
3. A pronouncing dictionary (CMU) or hyphenation library (pyphen). Flag words sung with a variable number of syllables for review, for example fire, hour, every, power, heaven.

**Example (4/4, `L:1/32`):**

```
% verse
V: Vocal
C8C8G8G8|A8A8G16|F8F8E8E8|D8D8C16|
V: Ins
Z4|
```

Lyrics: `Twinkle, twinkle, little star, / How I wonder what you are`. Each line has 7 syllables and 7 attacks.

## 3. Native ABC format

YuE2 reads a restricted ABC dialect, not general ABC. Convert every source into it and never send anything outside it.

**Header template:**

```
X:1
T:
M:4/4
L:1/32
Q:1/4=96
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
```

**Required:**

- Two monophonic voices, `Vocal` then `Ins`, written in blocks of 1 to 4 measures.
- The sung melody goes in `Vocal`. `Ins` is all rests (`Z`, `Z2`, `Z4`), because the child's piano is the lead.
- Section comments (`% verse`, `% chorus`, `% bridge`, `% interlude`) that match the lyric tags in order.
- A meter or key change starts a new block, with matching `M:` or `K:` in both voices.
- `L:1/32` by default: a quarter note is 8 units, a 4/4 bar is 32, a 3/4 bar is 24.
- Duration multipliers only from 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48. Other lengths use ties: 10 units = `C8-C2`.
- Accidentals carry through the bar and across octaves: after `^F`, both `F` and `f` are sharp until the barline.

**Rejected (convert per section 4):** repeat signs, alternate endings, tuplets, grace notes, note stacks (chords in the melody), slurs, broken rhythms (`A>B`), decorations, `w:` lines, custom directives.

## 4. Exceptions and how to handle them

Every rule below exists to keep the section 2 count exact. Changes apply to the Vocal line sent to YuE2 only; the child's piano arrangement never changes. Log every change in the sidecar (section 6).

| Situation | Handling | Example |
| --- | --- | --- |
| Repeats, multiple verses | Unroll. Write the melody once per pass, in playback order, each with its own section comment and matching lyric section. | 4 verses = 4 `% verse` blocks + 4 `[Verse]` sections |
| Alternate endings | Write out the ending each pass actually uses. | Pass 1 ends on ending 1, pass 2 on ending 2 |
| Verse with more syllables than notes | Split a note into repeated attacks of the same pitch for that pass only. Follow the source `w:` for that verse. | `C8` → `C4C4` |
| Verse with fewer syllables than notes | Tie same-pitch notes; for different pitches, merge as for a melisma. | `C4C4` → `C4-C4` |
| Melisma (one syllable, several pitches) | Default: merge into one note on the first pitch with the combined length. A tie cannot join different pitches. Source slurs usually mark these. | `B4G4` on "zing" → `B8` |
| Held note across a barline or chord change | Tie the same pitch. | `G16-\|G8` |
| Same pitch, separate syllables | Separate attacks, no tie. | `G8G8` |
| Instrumental intro, interlude, outro | Full-bar rests in Vocal, rests in Ins, a section comment, and no lyrics for that span. | `% interlude` then `Z2\|` in both voices |
| Vocal rest while piano plays | `z` rest in Vocal. Only where the source has a rest or breath mark; never invent one. | `G12z4` |
| Pickup (anacrusis) | Pad the first bar with rests to a full bar. | 4/4 pickup: `z24C8\|` |
| Broken rhythm | Write explicit durations. | `A>B` → `A12B4` |
| Tuplets | No exact form. Approximate on the grid with same-pitch ties for odd lengths, and flag the song. | Half-note triplet: 5 + 5 + 6 units |
| Grace notes | Drop them. | `{g}A8` → `A8` |
| Chord stacks in the melody | Keep the top note. | `[CEG]8` → `G8` |
| Elisions (ev'ry, heav'n) | Count syllables as the source sings them; write the elided spelling in the lyrics. | "ev'ry" = 2 syllables, 2 attacks |
| Key or meter change | Start a new block with matching `K:` or `M:` in both voices. | `K:D` in both `Vocal` and `Ins` |

The merge rule for melismas is the default until the spike test in section 6 picks a winner.

## 5. Checks before and after rendering

A song goes to YuE2 only when every pre-render check passes; a supplied score guides YuE2 but does not force it, so the post-render checks always run.

**Before rendering (all must pass):**

- [ ] `abc_tools.py inspect` accepts the ABC with no errors.
- [ ] Attacks equal syllables in every section (our counter script).
- [ ] ABC section comments and lyric tags match in number and order.
- [ ] No chord symbols in the ABC when `cot="melody"`.
- [ ] `Q:` tempo matches the BPM in `style`.
- [ ] The sidecar accounts for every Vocal note and every syllable.

**After rendering:**

- Word check: Whisper transcript against the lyrics, after normalizing elisions ("ev'ry" = "every").
- Pitch check: against the Vocal line actually sent, not the piano melody.
- Timing check: force-align the lyrics to the vocal stem (WhisperX or MMS) and compare each word's onset with its note onset from the sidecar.
- Keep failed takes with their ABC, lyrics, seed and report.

## 6. Sidecar record and open questions

Each song gets a JSON sidecar, saved beside the ABC and never sent to YuE2, with one row per sung syllable.

| Field | Content |
| --- | --- |
| section | Section tag and pass number, e.g. `verse 2` |
| line | Lyric line number within the section |
| syllable | The syllable as sung |
| note\_index | Index of its Vocal attack, after merging ties |
| pitch | MIDI pitch |
| onset, duration | Quarter-note fractions from the ABC |
| change | Exception applied from section 4 and the original notes, or empty |

**Open questions:**

- [ ] Melisma: compare merge, keep-as-written, and split-vowel lyrics ("Amazi-ing") on 3 to 4 hymns with the same seed; choose by word, pitch and timing pass rates.
- [ ] Planning test: run `pipe.plan()` in `melody` mode with no ABC and count YuE2's own attacks per syllable, to confirm the 1:1 rule matches its habits.
- [ ] Instrumental spans: test whether an empty lyric tag (for example `[Interlude]`) helps or hurts compared with no tag.

**Sources:** [YuE2 generation guide](https://github.com/multimodal-art-projection/YuE/blob/main/docs/generation.md) · [ABC editing reference](https://github.com/multimodal-art-projection/YuE/blob/main/skills/yue2-music/references/abc-editing.md) · [Generation and covers](https://github.com/multimodal-art-projection/YuE/blob/main/skills/yue2-music/references/generation-and-covers.md)
