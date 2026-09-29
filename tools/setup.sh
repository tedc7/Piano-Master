#!/usr/bin/env bash
# Rebuild the dev tools (all gitignored): Node for the client, a Python venv for the content
# build and browser checks, and abc2xml. Needs ~/miniconda3 and internet.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Node 22 (conda-forge), used as .tools/node/bin on the PATH; nothing is installed system-wide
[ -x .tools/node/bin/node ] || ~/miniconda3/bin/conda create -q -y -p "$ROOT/.tools/node" -c conda-forge --override-channels "nodejs>=22,<23"
(cd client && PATH="$ROOT/.tools/node/bin:$PATH" npm ci --no-fund --no-audit)
# Python: music21 (notation converter), PyYAML (content), pytest, Playwright (headless checks)
python3 -m venv tools/.venv
tools/.venv/bin/pip install -q --upgrade pip
tools/.venv/bin/pip install -q -r tools/requirements.txt
tools/.venv/bin/python -m playwright install chromium
# abc2xml 268 by Willem Vree (LGPL): ABC with several voices -> MusicXML (music21's ABC reader merges voices)
mkdir -p tools/.vendor && curl -sL -o tools/.vendor/abc2xml.zip https://wim.vree.org/svgParse/abc2xml.py-268.zip
# xml2abc 177 by the same author (LGPL): MusicXML -> ABC, for the song import skill (tools/import_song.py convert)
curl -sL -o tools/.vendor/xml2abc.zip https://wim.vree.org/svgParse/xml2abc.py-177.zip
(cd tools/.vendor && unzip -o -q abc2xml.zip && unzip -o -q xml2abc.zip)
echo "ready: tools/.venv/bin/python tools/build_content.py, then (cd client && npm run build)"
