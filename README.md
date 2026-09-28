# Piano-Master
Piano App with Parental Controls. Design: [Family Piano Tutor - Architecture v0.17.md](Family%20Piano%20Tutor%20-%20Architecture%20v0.17.md).

## Layout

| Folder | What it holds |
| --- | --- |
| `client/` | The web client (Svelte 5, TypeScript, Vite; VexFlow 4.2.5 for the staff; plain Web Audio) |
| `content/` | Authored content: the skill map (`skillmap/*.yaml`) and pieces (`pieces/*.yaml`, ABC inside) |
| `tools/` | Python: the notation converter, the content build, tests, the browser check and the deploy script |
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
(cd client && npm run check && npm test)         # types, and unit tests: matcher, rewind rules, timeline, MIDI
tools/.venv/bin/python -m pytest -q tools/tests  # skill-map validation, converter, constraint checks
(cd client && npm run build) && tools/.venv/bin/python tools/check_app.py
```

`check_app.py` runs the built app in headless Chromium at iPad A16 size and plays pieces with a
scripted keyboard (a Web MIDI stand-in that exists only in that test). Screenshots go to `tests-output/`.

## Deploy

```sh
tools/deploy.sh                                  # builds, tests, and deploys to https://192.168.2.128/app/
```
