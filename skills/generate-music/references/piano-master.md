# Piano-Master profile

For the Family Piano Tutor app (repo `~/repos/Piano-Master`, architecture v0.15 section 10.5): each arrangement gets a sung **vocal stem** and a **soft accompaniment stem**, so a child can play the piano part along with them. Use `"profile": "piano-master"`.

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
  "seed": 831001,
  "formats": ["flac", "mp3"]
}
```

The profile:
- **requires** `score_abc`, `genre`, `language`, `key`, `meter`, `tempo_bpm`, and forces `stems: true`;
- **builds the style** as `{language}, {vocal}, {accompaniment}, soft, sparse, background, no lead melody, {tempo} BPM`, with the vocal and accompaniment taken from the genre table (override with `vocal_style` / `accompaniment_style` for one song, e.g. a parent's "change vocal style" request);
- **checks** that the ABC's `Q:`, `K:`, `M:` equal `tempo_bpm`, `key`, `meter`, and that the ABC's sung sections (`% verse`, `% chorus`, …) match the lyric sections in order. Instrumental sections (`intro`, `interlude`, `outro`, `instrumental`, `solo`, `break`) are ignored in that comparison.

## Genre defaults (from section 10.5)

| Genre | Vocal | Accompaniment |
|---|---|---|
| Hymns | warm solo voice or small choir, gentle, reverent, smooth phrasing | soft organ and strings |
| Folk | clear, natural acoustic folk singer | acoustic guitar and light bass |
| Nursery and kids' songs | bright, friendly voice with very clear words | light acoustic band, soft percussion |
| Classical | light classical or choral tone | soft strings |
| Holiday | warm and festive voice, choir optional | bells, strings, light percussion |
| Movie/TV, Pop | clean, light, upbeat modern voice | light drums, bass, and pad |
| Lesson pieces | bright, friendly voice with very clear words | light acoustic guitar and soft strings *(not in the architecture table; a placeholder)* |

The table lives in `profiles/piano-master.json`; change it there.

## Building the inputs from an arrangement

- **Melody**: the arrangement's melody line, converted into the native ABC dialect ([abc-quickref.md](abc-quickref.md)), with the arrangement's chord symbols on the `Vocal` voice. `Ins` is usually all rests. The melody must be in a comfortable singing register; transpose by octave if the piano part sits low. *(A MusicXML → native ABC converter is still to be written; until then scores are written by hand.)*
- **Lyrics**: all verses in playback order, read from the song's files. Pass them by `lyrics_path`; don't retype them.
- **Tempo**: the arrangement's written tempo (100% preset). Slower tempo versions (90/75/50%) are made later by time-stretching, not by re-rendering.

## Not done yet (rest of M0-S / M8)

Beat alignment, the pitch check (≥90% of melody notes on pitch), the Whisper word check, the accompaniment harmony check, Rubber Band tempo versions, loudness normalisation, and packaging for the Skill API. Record listening results for now.
