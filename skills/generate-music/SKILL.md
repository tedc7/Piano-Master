---
name: generate-music
description: Generate music with the local YuE2 engine on this machine's GPU — a full song with sung vocals and accompaniment from lyrics plus a style description, optionally following a supplied melody/chord score (ABC), and optionally split into separate vocal and accompaniment stems. Use for any request to create, compose, render or sing a song, jingle, backing track or vocal from text, and for Piano-Master media renders (vocal + soft accompaniment for an arrangement, via the piano-master profile).
---

# Generate music (YuE2)

One script does the work: `scripts/generate_music.py`. It validates a JSON request, runs YuE2 in its own venv (`~/engines/yue2`), and writes audio plus a `report.json`. Your job is to write a good request, run it, and report the result honestly.

## 1. Check the engine

```bash
test -x ~/engines/yue2/.venv/bin/python && test -f ~/engines/yue2/INSTALLED.json && echo ready
```

If it isn't ready, run `bash ~/.claude/skills/generate-music/scripts/install_engine.sh` (downloads ~15 GB; tell the user first). Needs an NVIDIA GPU with BF16; this machine's RTX 5070 Ti (16 GB) is below YuE2's official 24 GB, so settings in `~/engines/yue2/engine.json` were chosen by testing.

## 2. Pick the workflow

| The user wants | Request |
|---|---|
| A new song from an idea | `lyrics` + `style`; no score. YuE2 writes its own melody and chords (`score.abc` is saved so it can be edited and re-rendered) |
| A song that follows a given melody | add `score_abc_path` in native ABC ([references/abc-quickref.md](references/abc-quickref.md)); chords in the score → `plan` full, none → melody |
| Separate vocal / backing tracks, or an instrumental backing track | `"stems": true` → `vocals.*` and `accompaniment.*` (YuE2 always sings; the accompaniment stem is the instrumental) |
| Piano-Master arrangement media | `"profile": "piano-master"`; read [references/piano-master.md](references/piano-master.md) |

Full schema, outputs and exit codes: [references/request-format.md](references/request-format.md).

## 3. Write the request

- **Lyrics**: section tags on their own lines (`[Verse]`, `[Chorus]`, `[Bridge]`, `[Outro]`), all verses in the order sung, only words that should be sung. Keep them singable: short lines, regular syllable counts. Write lyrics to a file and pass `lyrics_path`. Write original lyrics unless the user supplies their own; don't reproduce copyrighted lyrics.
- **Style**: one comma-separated line: language, genre, vocal character, instruments, mood, tempo — e.g. `English, gentle folk ballad, warm male voice, fingerpicked acoustic guitar, soft cello, 84 BPM`. Say what to avoid in positive terms ("sparse", "soft background drums") — there's no negative prompt.
- **Length** follows the lyrics (or the score). A verse–chorus–verse–chorus song is typically 2–3 minutes and takes several minutes to render.
- Save the request next to its lyrics/score files, e.g. in a `renders/requests/` folder of the current project, and choose `formats` (`mp3` for easy listening, `flac`/`wav` for further processing).

## 4. Run

```bash
python3 ~/.claude/skills/generate-music/scripts/generate_music.py --request req.json --out renders/ --dry-run   # validate, no GPU
python3 ~/.claude/skills/generate-music/scripts/generate_music.py --request req.json --out renders/
```

Run the real render in the background (it can take 5–15 minutes) and only one at a time: the GPU holds one render. Parse the last stdout line (JSON).

## 5. Check and report

- Exit 0: give the user the output folder, files, duration and render time. A finished render is not proof of quality: say it still needs a listen.
- Exit 2: fix the request (the `error` says what) and retry.
- Exit 3: read `failure.json`. On out-of-memory, check `nvidia-smi` for other GPU users and retry once; don't change `engine.json` (offload/fp8) or shorten the song without telling the user.
- Exit 4 (truncated): the song may end early; retry with another seed or shorter lyrics.
- If a take is poor (wrong words, off melody, muddy mix), retry with a new `--seed`, up to 3 takes, and keep every take.

## Notes

- YuE2 weights are **CC BY-NC 4.0**: fine for personal and family use, not for commercial products without a license from the authors.
- Upstream docs (editing scores, covers, evaluation): `~/engines/yue2/YuE/skills/yue2-music/`. The upstream skill's SheetSage2 transcription needs a separate environment that isn't installed.
