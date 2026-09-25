# Request format, output, and exit codes

`generate_music.py` takes one JSON request file. Paths inside it are relative to the request file.

```json
{
  "id": "autumn-folk",
  "title": "Autumn Road (test)",
  "lyrics_path": "autumn.lyrics.txt",
  "style": "English, clear natural folk singer, acoustic guitar and light bass, warm and unhurried, 92 BPM",
  "score_abc_path": null,
  "plan": "auto",
  "seed": 831001,
  "stems": true,
  "formats": ["flac", "mp3"]
}
```

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Filename-safe name; output goes to `<out>/<id>/` |
| `lyrics` or `lyrics_path` | yes | Lyrics with section tags on their own lines: `[Verse]`, `[Chorus]`, `[Bridge]`, `[Outro]`… All verses in the order they are sung |
| `style` | yes, unless a profile builds it | Free text: language, genre, vocal character, instruments, mood, tempo in BPM |
| `score_abc` or `score_abc_path` | no | A melody (and optionally chords) in YuE2's native ABC dialect; see [abc-quickref.md](abc-quickref.md) |
| `plan` | no (`auto`) | `auto`, `full`, `melody`, `off`. `auto` = `full` if the score has chord symbols, `melody` if it has none, `full` if there's no score (the model writes its own melody and chords, saved as `score.abc`). `off` = no symbolic plan, no score |
| `seed` | no (831001) | Integer. Same request + seed + engine settings gives the same `request_id` |
| `stems` | no (false) | Also write `vocals.*` and `accompaniment.*` (Demucs htdemucs; accompaniment = drums + bass + other) |
| `formats` | no (`["flac"]`) | Any of `flac`, `wav`, `mp3` (48 kHz; FLAC/WAV 24-bit) |
| `profile` | no | Name of a file in `profiles/` that adds fields and rules, e.g. `piano-master` |
| `title`, `notes` | no | Free text, carried into the report |

Profile fields (used only by a profile): `genre`, `language`, `key`, `meter`, `tempo_bpm`, `vocal_style`, `accompaniment_style`.

## Command

```bash
python3 ~/.claude/skills/generate-music/scripts/generate_music.py --request req.json --out renders/ [--seed N] [--profile NAME] [--dry-run]
```

`--dry-run` validates and prints the engine job without touching the GPU. Progress goes to stderr; the **last stdout line** is one JSON object.

## Output folder `<out>/<id>/`

| File | What |
|---|---|
| `mix.<fmt>` | The full song |
| `vocals.<fmt>`, `accompaniment.<fmt>` | Stems, when `stems` is true |
| `score.abc` | The score the song was generated from (supplied, or planned by the model) |
| `report.json` | Status, style string used, cot, seed, `request_id`, truncation, audio seconds, per-stage timings, peak VRAM, levels (RMS/peak dBFS), engine commit/revisions/settings |
| `job.json` | The exact validated job sent to the engine |
| `yue2/` | YuE2's own reproducibility artifacts (tokens, latents, hashes) |
| `failure.json` | Only on failure: stage, error type, reason, out-of-memory flag, hint |

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Complete | Listen / check the report |
| 2 | Invalid request (nothing ran) | Fix the request; the JSON `error` says what |
| 3 | Engine error | Read `failure.json`. If `out_of_memory`, close other GPU apps and retry; only change `engine.json` with the user's agreement and say so |
| 4 | Complete but truncated | The model hit a token limit; the song may stop early. Shorten the lyrics/score or retry with another seed |

The script refuses to write into a non-empty output folder. It never shortens a song or lowers quality settings on its own.
