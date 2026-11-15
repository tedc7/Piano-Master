#!/usr/bin/env bash
# Rebuild the dev tools (all gitignored): Node for the client, a Python venv for the content
# build and browser checks. Needs internet, and Node 22 on the PATH or ~/miniconda3.
#   tools/setup.sh                 everything
#   tools/setup.sh --no-browser    without Playwright's Chromium (only tools/check_app.py uses it):
#                                  another family's server (docs/install-guide.md)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BROWSER=yes
[ "${1:-}" = --no-browser ] && BROWSER=no
# Node 22: this repo's own (conda-forge, .tools/node/bin; nothing system-wide), else the system's
# Node 22 if it has one (v0.51: another family's server), else make the repo's own
node22() { "$1" -e 'process.exit(+process.versions.node.split(".")[0] === 22 ? 0 : 1)' 2>/dev/null; }
if [ -x .tools/node/bin/node ]; then
  NODE_BIN="$ROOT/.tools/node/bin"
elif command -v node >/dev/null && node22 node; then
  NODE_BIN="$(dirname "$(command -v node)")"
else
  ~/miniconda3/bin/conda create -q -y -p "$ROOT/.tools/node" -c conda-forge --override-channels "nodejs>=22,<23"
  NODE_BIN="$ROOT/.tools/node/bin"
fi
(cd client && PATH="$NODE_BIN:$PATH" npm ci --no-fund --no-audit)
# Python: music21 (notation converter), PyYAML (content), pytest, Playwright (headless checks)
python3 -m venv tools/.venv
tools/.venv/bin/pip install -q --upgrade pip
tools/.venv/bin/pip install -q -r tools/requirements.txt
if [ "$BROWSER" = yes ]; then tools/.venv/bin/python -m playwright install chromium; fi
# abc2xml 268 and xml2abc 177 (LGPL) are in the repo, in tools/vendor/: the author's site keeps only
# the newest version
echo "ready: tools/.venv/bin/python tools/build_content.py, then (cd client && npm run build)"
