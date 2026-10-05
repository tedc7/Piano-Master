# Piano-Master
Piano App with Parental Controls. Design: [docs/architecture.md](docs/architecture.md) (its version and date are at the top; changes are in [docs/architecture-changelog.md](docs/architecture-changelog.md)).

## Layout

| Folder | What it holds |
| --- | --- |
| `client/` | The web client (Svelte 5, TypeScript, Vite; VexFlow 4.2.5 for the staff; plain Web Audio) |
| `api/` | The App API (FastAPI, SQLite): devices, attempts with raw key presses, client logs, parent login, students, and the lesson engine (`app/engine.py`) |
| `content/` | Authored content: the skill map (`skillmap/*.yaml`) and pieces (`pieces/*.yaml`, ABC inside); import batches wait in `incoming/`, and each piece's vocal and backing stems in `media/` (both gitignored) |
| `tools/` | Python: the notation converter, the content build, the song import tools, the media skill's tools (`media/`: YuE2 vocals, FluidSynth backings, alignment and checks), tests, the browser check, fixtures and deploy |
| `docs/` | Briefs for the Server repo session (server setup is done there, not here), the keyboard-day checklist, and pipeline notes (`media-pipeline-notes.md`) |
| `.claude/skills/` | Project skills Claude Code loads in this repo: `import-song` (arch §10.4) and `make-media` (§10.5) |
| `feasibility/` | The feasibility tests and their results |
| `skills/` | Backup of the `generate-music` Claude skill (YuE2) |
| `client/public/audio/piano/` | The app's piano samples (Salamander Grand Piano, CC BY 3.0) |

The skill map in `content/skillmap/` is the **Prep A map** (arch §6.2): 46 skills in 9 units,
one concept each (one Journey bubble), each labelled Notes, Rhythm, Technique, Theory or Musicianship. Its
concept lessons are in `content/lessons/` (one YAML file per skill, one Explain card,
then show/hear/try/check/echo/watch). Every song's source is in `content/pieces/`: each skill's `pieces` list is
its practice songs, 2 to 4 (Units 1 to 3 are pre-staff pieces, `letters: true`; `dynamics:` marks f, mf, p;
`warmup-*` are the warm-ups). The family's own method-book photos (`Background/`) and page references
(`content/private/book-refs.yaml`, merged into parent mode by the build) stay out of the repository.
`content/incoming/` holds batches being prepared (never built or deployed, never committed): the
classical arrangements and their import notes (`incoming/classical/NOTES.md`), and the kids' songs.

**Importing songs** (arch §10.4): ask Claude Code to import or find songs; it follows the
`import-song` skill and uses `tools/import_song.py` (`convert`, `check`, `compare`, `report`,
`submit`, `feedback`, and `promote` to keep an approved song's source in git). A batch is made in
`content/incoming/<batch>/` and submitted to the app's review list; nothing reaches a child before
the parent approves it there. Songs written here for the map are submitted from `content/pieces/`.

**Vocals and backing** (arch §10.5, M8): the `make-media` skill and `tools/media/media.py` (`plan`,
`make`, `report`). A song with words gets a YuE2 vocal (the `generate-music` skill), aligned to the
beat and checked; a piece with chord symbols or other voices gets a backing rendered from them with
FluidSynth and the MuseScore General SoundFont. Stems wait with the batch and go to
the piano server with the song. Setup: `tools/media/setup.sh`.

**The review list and the library** (arch §10.1, §10.7, §10.9; M7): `import_song.py submit` sends a
batch, with its stems, through the Skill API (a token in `~/.config/piano-master/skill-token`). The
server's intake checks every song again and stages the ones that pass; the parent listens and
approves them in Config › Review list, and approved songs join the library on the server at once,
with no deploy. **Every song is in the library** (v0.27), whatever made it; the skill map deploys
with the app and names its practice songs, which must be approved first (`tools/library_check.py`
stops a deploy otherwise). Config › Songs and genres sets what each child sees (the map's practice
songs always; other genres once allowed) and deletes songs. **Needs improvement** in the Play
screen's gear pop-up (parent mode) asks for a fix to a song in use; the fix comes back to the
Review list as an update, and approving it replaces the song in place. The library holds only approved songs; every other song
(waiting, sent back, or deleted) is in the review area, and deleted songs are at the bottom of the
Review list. The files live beside the database in `/opt/piano/data` (`library/`, `staging/`).

**Content build** (`tools/build_content.py`, arch §6.8–6.10): converts every song (to `build/songs/`,
for the library; only the map and lessons deploy with the app), runs **song
analysis** (`api/app/analysis.py`: required and featured skills, map point, skill measures, and
anything beyond the map), fills in finger numbers (`api/app/fingering.py`), builds the concept
lessons, and checks the skill map (ids, sequences, prerequisites, constraints, 2 practice songs per
skill, a lesson per skill). In ABC, `"_L"` below a note gives it to the left hand on the upper
staff; `song:` and `version:` in a piece's YAML make it one arrangement of a song.

**Screens** (arch §3): the player picker (each child, and Parent behind the PIN), then a bottom
tab bar. Students: Today's Practice (the session as a path of items; the start screen), Journey,
Songs and My Progress. Parent: Journey and Songs with everything open, and Config (students,
progress reports, the PIN, the piano check, device settings, app status, the content preview and
the Journey render test; other pages are placeholders marked with their milestone). The Play
screen's Back returns to whichever screen opened the song. The status strip keeps its left 110 px
empty for MIDIWeb Browser's floating full-screen button.

**Students and the lesson engine** (arch §5, §8; M4, M5): the piano server holds the students,
their settings, skill states, today's session and practice days. The engine builds each day's
session on the first request and updates the skill states from every attempt; the client keeps a
copy of the last state so a Wi-Fi drop never stops practice. On a new piano server, tap Parent
and choose a PIN (4 to 8 digits), then add the students under Config > Students. A forgotten PIN
is cleared on the server: `docker exec <piano-api container> python -m app.admin reset-pin`.

**Diagnostics and drills** (arch §8.8, §8.9; M6): every attempt stores each written note's timing
(or that it was missed). When a day's session is built, `api/app/diagnostics.py` looks for five
error patterns in the last 14 days. It adds a remedy as **Focus** items at the head of the
Practice slot: a generated drill (`api/app/drills.py`), or bars of the piece with a hand, preset or
metronome. The parent's progress report lists the patterns, with stuck ones highlighted.

**The keyboard** (the MIDI keyboard is still to come): Config > Piano check and Config > Latency
calibration are ready, and `docs/keyboard-day.md` lists every test that needs the keyboard, in
order.

## Develop

```sh
tools/setup.sh                                   # once: Node (local conda env), Python venv, abc2xml and xml2abc
export PATH="$PWD/.tools/node/bin:$PATH"
tools/.venv/bin/python tools/build_content.py    # content/ -> client/public/content (+ test media)
cd client && npm run dev                         # http://localhost:5173 (Web MIDI works on localhost in Chrome)
```

The Amazing Grace test song copies its YuE2 stems from the sync probe's build
(`feasibility/sync-probe/dist`); the build fails with a clear message if that isn't on this machine.

## Test

```sh
(cd client && npm run check && npm test)         # types; unit tests; the performance fixtures
tools/.venv/bin/python -m pytest -q tools/tests  # skill-map validation, converter, constraint checks, the import and media tools
(cd api && ../tools/.venv/bin/python -m pytest -q tests)   # the App API, the lesson engine and the practice simulator
(cd client && npm run build) && tools/.venv/bin/python tools/check_app.py
```

`check_app.py` runs the built app and the API (with a throwaway database) in headless Chromium at
iPad A16 size and plays pieces with a scripted keyboard (a Web MIDI stand-in that exists only in
that test). It starts from a new server: it chooses the parent PIN, adds two students and plays
their first session. Screenshots go to `tests-output/`.

The **practice simulator** (`api/tests/simulator.py`, arch §11.4) drives the real lesson engine
day by day for simulated learners (fast, slow, inconsistent, one skill much harder) over 8 weeks
on a generated branching map; `test_simulator.py` holds the M5 acceptance checks.
`test_planted.py` is M6's: students with a planted error pattern practise for three weeks, and
each pattern must be found, get the right remedy, and resolve (or be marked stuck).

**Performance fixtures** (`client/tests/fixtures/*.json`, arch §7.10): each is a performance and
the result it should get, replayed through the same code as live play. Turn a real attempt into
one with `tools/.venv/bin/python tools/fixture_from_attempt.py` (lists recent attempts), then
`... fixture_from_attempt.py <id> <name>`, and review the expected stars before committing.

## Deploy

The scripts find your piano server in `~/.config/piano-master/server.env`: copy
[tools/server.env.example](tools/server.env.example) there and fill in the site's address, the ssh
host for deploys and the server's root certificate. It's kept outside the repo, which is public.
A new server from scratch: [docs/fresh-install.md](docs/fresh-install.md).

```sh
tools/deploy.sh             # tests, then the API (/opt/piano/api) and the client (https://<piano-server>/app/)
tools/deploy.sh client      # or just one of them
tools/deploy.sh api
```

The API container, the Caddy route, the data directory and its backup are set up by the Server
repo ([docs/server-brief-app-api.md](docs/server-brief-app-api.md),
[docs/server-brief-m4-backup.md](docs/server-brief-m4-backup.md)); `deploy.sh` only replaces the
code and runs the server's `piano-api-redeploy`. An API deploy bundles the built skill map and
piece index, and every piece's notation, into `api/app/content/`, so the lesson engine plans from the content the client shows;
a client-only deploy redeploys the API too when the content versions differ.
