# Piano-Master profile

For the Family Piano Tutor app (repo `~/repos/Piano-Master`, architecture v0.22 section 10.5): each arrangement gets a sung **vocal stem** and an **accompaniment stem**, so a child can play the piano part along with them. Use `"profile": "piano-master"`.

**Which of YuE2's stems the app uses (v0.22):**
- **The vocal: always.**
- **The accompaniment: only for a song with no backing notes.** An arrangement with backing notes (a hymn's four-part harmony, ensemble parts, or chord symbols) gets its backing rendered from those notes with FluidSynth and the MuseScore General SoundFont (Piano-Master's `feasibility/fluid-probe/`). In the listening test it sounded better than YuE2's backing.

Keep giving YuE2 the chord symbols and a named-instrument accompaniment either way. They keep its backing, and so the vocal it sings against, in the written harmony, and the demixed vocal then carries no clashing backing.

## Request

```json
{
  "id": "song-slug-l2",
  "title": "Song title (Level 2, right hand)",
  "profile": "piano-master",
  "genre": "Nursery and kids' songs",
  "language": "English",
  "key": "C",
  "meter": "4/4",
  "tempo_bpm": 96,
  "score_abc_path": "song.abc",
  "lyrics_path": "song.lyrics.txt",
  "syllables_path": "song.syllables.json",
  "seed": 831001,
  "formats": ["flac", "mp3"]
}
```

The profile:
- **requires** `score_abc`, `syllables`, `genre`, `language`, `key`, `meter`, `tempo_bpm`, and forces `stems: true`;
- **builds the style** as `{language}, {genre style}, {vocal}, {accompaniment}, {tempo} BPM` from the genre table (override the vocal or accompaniment with `vocal_style` / `accompaniment_style` for one song, e.g. a parent's "change vocal style" request; follow the same pattern);
- **checks** one `Vocal` attack per sung syllable, on each syllable's beat (see below);
- **checks** that the ABC's `Q:`, `K:`, `M:` equal `tempo_bpm`, `key`, `meter`, and that the ABC's sung sections (`% verse`, `% chorus`, …) match the lyric sections in order. Instrumental sections (`intro`, `interlude`, `outro`, `instrumental`, `solo`, `break`) are ignored in that comparison.

## Genre defaults: name the backing instruments

**Say which instruments the backing should use and how they play; don't leave it to YuE2 to guess.** Use a genre word, one solo voice (no "or choir" alternatives), and named instruments with their playing style. Never put a piano in the backing: the child plays the piano part.

Why (Piano-Master test, 2026-09): with the same score, lyrics and seeds, the backing followed the written chords in 81% of chord spans with specific prompts. The earlier vague defaults ("soft organ and strings", "solo voice or small choir", "soft, sparse, background, no lead melody") managed 58%, and listening preferred the specific takes. The prompt did not change the backing's level: YuE2 mixes long hymn-like songs with a quiet backing whatever the prompt. The app sets the level afterwards.

| Genre | Genre style | Vocal | Accompaniment |
|---|---|---|---|
| Hymns | traditional hymn | warm clear solo voice | soft pipe organ and warm string ensemble playing steady sustained chords, gentle, reverent |
| Holiday | traditional holiday carol | warm clear solo voice | warm string ensemble and harp arpeggios, light sleigh bells, gentle, steady |
| Folk | gentle folk song | clear natural solo folk singer | fingerpicked acoustic guitar, soft upright bass, light brushed percussion, steady |
| Nursery and kids' songs | children's song | bright friendly solo voice with very clear words | strummed acoustic guitar, soft glockenspiel, light hand percussion, steady |
| Classical | light classical art song | light clear classical solo voice | soft string quartet playing sustained chords, gentle, steady |
| Movie/TV, Pop | light pop song | clean light solo voice | light brushed drums, warm bass guitar, soft synth pad chords, steady |
| Lesson pieces | simple lesson song | bright friendly solo voice with very clear words | strummed acoustic guitar and soft string pad playing steady chords |

Hymns and Holiday were tested (Holiday as "traditional Christmas carol"); the other rows follow the same pattern but haven't been listened to yet. The table lives in `profiles/piano-master.json`; change it there.

## Building the inputs from an arrangement

- **Melody**: the arrangement's melody line, converted into the native ABC dialect ([abc-quickref.md](abc-quickref.md)), with the arrangement's chord symbols on the `Vocal` voice (keep them: without chords, `plan` melody, the backing strays from the chords the child plays). `L:1/32`. `Ins` all rests. Unroll repeats and verses in playback order; pad the pickup bar with rests. The melody must be in a comfortable singing register; transpose by octave if the piano part sits low.
- **One Vocal attack per sung syllable** ([abc-quickref.md](abc-quickref.md#lyrics-and-the-score)): merge each melisma onto its first pitch. Take the syllables from the source's own lyric splits (MusicXML lyrics, ABC `w:` lines), not from a dictionary.
- **Syllables sidecar** (`syllables_path`): `{"syllables": [{"syllable": "A", "beat": "5"}, {"syllable": "maz", "beat": "6"}, …]}`, every sung syllable in order, including any throwaway lead-in word; `beat` is the attack's onset in quarter notes from the start of the ABC. Never sent to YuE2.
- A working converter (MusicXML / ABC Plus → notation, native ABC, lyrics, syllables sidecar, with a sung "Oh" lead-in bar) is the Piano-Master repo's `feasibility/sync-probe/convert.py`.
- **Lyrics**: all verses in playback order, read from the song's files. Pass them by `lyrics_path`; don't retype them.
- **Tempo**: the arrangement's written tempo (100% preset). Slower tempo versions (90/75/50%) are made later by time-stretching, not by re-rendering.

## After rendering (not in this skill yet)

Prototypes in the Piano-Master repo's `feasibility/sync-probe/` (see its RESULTS.md): beat alignment (`align.py`: lyric forced alignment plus pitch windows, Rubber Band time map), the pitch and word checks, the harmony check (`harmony.py`), tempo versions (Rubber Band R3), and levels (backing set against the vocal above 250 Hz). Known YuE2 limits: melismas are sung as one held pitch; the first word can be soft or unclear; the backing's level and instruments vary within and between songs.
