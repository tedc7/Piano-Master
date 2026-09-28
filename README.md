# Piano-Master
Piano App with Parental Controls. Design: [Family Piano Tutor - Architecture v0.18.md](Family%20Piano%20Tutor%20-%20Architecture%20v0.18.md).

## Layout

| Folder | What it holds |
| --- | --- |
| `client/` | The web client (Svelte 5, TypeScript, Vite; VexFlow 4.2.5 for the staff; plain Web Audio) |
| `api/` | The App API (FastAPI, SQLite): devices, attempts with raw key presses, client logs |
| `content/` | Authored content: the skill map (`skillmap/*.yaml`) and pieces (`pieces/*.yaml`, ABC inside) |
| `tools/` | Python: the notation converter, the content build, tests, the browser check, fixtures and deploy |
| `docs/` | Briefs for the Server repo session (server setup is done there, not here) |
| `feasibility/` | The feasibility tests and their results |
| `skills/` | Backup of the `generate-music` Claude skill (YuE2) |

The skill map in `content/skillmap/` is a **placeholder** (ids start with `placeholder.`) until the
Faber books arrive; replace it with the real Prep A map.

## Develop

```sh
tools/setup.sh                                   # once: Node (local conda env), Python venv, abc2xml
export PATH="$PWD/.tools/node/bin:$PATH"
tools/.venv/bin/python tools/build_content.py    # content/ -> client/public/content (+ test media)
cd client && npm run dev                         # http://localhost:5173 (Web MIDI works on localhost in Chrome)
```

The Amazing Grace test song copies its YuE2 stems from the sync probe's build
(`feasibility/sync-probe/dist`); the build fails with a clear message if that isn't on this machine.

## Test

```sh
(cd client && npm run check && npm test)         # types; unit tests; the performance fixtures
tools/.venv/bin/python -m pytest -q tools/tests  # skill-map validation, converter, constraint checks
(cd api && ../tools/.venv/bin/python -m pytest -q tests)   # the App API
(cd client && npm run build) && tools/.venv/bin/python tools/check_app.py
```

`check_app.py` runs the built app and the API (with a throwaway database) in headless Chromium at
iPad A16 size and plays pieces with a scripted keyboard (a Web MIDI stand-in that exists only in
that test). Screenshots go to `tests-output/`.

**Performance fixtures** (`client/tests/fixtures/*.json`, arch §7.10): each is a performance and
the result it should get, replayed through the same code as live play. Turn a real attempt into
one with `tools/.venv/bin/python tools/fixture_from_attempt.py` (lists recent attempts), then
`... fixture_from_attempt.py <id> <name>`, and review the expected stars before committing.

## Deploy

```sh
tools/deploy.sh             # tests, then the API (/opt/piano/api) and the client (https://192.168.2.128/app/)
tools/deploy.sh client      # or just one of them
tools/deploy.sh api
```

The API container, the Caddy route, the data directory and its backup are set up by the Server
repo ([docs/server-brief-app-api.md](docs/server-brief-app-api.md)); `deploy.sh` only replaces the
code and runs the server's `piano-api-redeploy`.
