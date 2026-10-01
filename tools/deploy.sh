#!/usr/bin/env bash
# Test and deploy to the piano server:
#   the App API  -> /opt/piano/api, rebuilt by the server's piano-api-redeploy (Server repo),
#                   with the built skill map in app/content (the lesson engine plans from the same
#                   map the client shows)
#   the client   -> /opt/piano/www/app, i.e. https://192.168.2.128/app/ (swapped in whole)
# Songs aren't deployed: every song is in the server's library (v0.27), and the map may name only
# songs the parent approved (tools/library_check.py stops the deploy otherwise).
# Nothing else on the server is touched; the database in /opt/piano/data is never touched here.
#   tools/deploy.sh            both
#   tools/deploy.sh client     the client only (and the API too if its content is out of date)
#   tools/deploy.sh api        the API only
#   --seed-songs               also bring build/songs/ into the library as approved, when the API
#                              starts (once: the songs built into the app before v0.27)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${PIANO_HOST:-kb}"
URL="https://192.168.2.128/app/"
CA="${CADDY_ROOT_CA:-$HOME/repos/Server/caddy-root-ca.crt}"
export PATH="$ROOT/.tools/node/bin:$PATH"

SEED=no
ARGS=()
for a in "$@"; do if [ "$a" = --seed-songs ]; then SEED=yes; else ARGS+=("$a"); fi; done
WHAT="${ARGS[0]:-all}"
curl_opts=(-s)
if [ -f "$CA" ]; then curl_opts+=(--cacert "$CA"); else curl_opts+=(-k); fi

"$ROOT/tools/.venv/bin/python" "$ROOT/tools/build_content.py"
VERSION=$(python3 -c "import json; print(json.load(open('$ROOT/client/public/content/skillmap.json'))['contentVersion'])")
"$ROOT/tools/.venv/bin/python" "$ROOT/tools/library_check.py" $([ "$SEED" = yes ] && echo --seeding)
if [ "$WHAT" = client ]; then
  served=$(curl "${curl_opts[@]}" https://192.168.2.128/api/health | python3 -c "import json,sys; print(json.load(sys.stdin).get('contentVersion'))" 2>/dev/null || true)
  if [ "$served" != "$VERSION" ]; then
    echo "the API plans from content ${served:-unknown}, the client has $VERSION: deploying the API too"
    WHAT=all
  fi
fi

if [ "$WHAT" = all ] || [ "$WHAT" = api ]; then
  rm -rf "$ROOT/api/app/content"
  mkdir -p "$ROOT/api/app/content"
  cp "$ROOT/client/public/content/skillmap.json" "$ROOT/api/app/content/"
  if [ "$SEED" = yes ]; then cp -r "$ROOT/build/songs" "$ROOT/api/app/content/seed"; fi   # library.adopt_seed
  (cd "$ROOT/api" && "$ROOT/tools/.venv/bin/python" -m pytest -q tests)
  rsync -a --delete --exclude tests --exclude '__pycache__' --exclude '*.pyc' "$ROOT/api/" "$HOST:/tmp/piano-api/"
  ssh "$HOST" 'set -e
    sudo rsync -a --delete /tmp/piano-api/ /opt/piano/api/
    sudo chown -R root:root /opt/piano/api
    sudo find /opt/piano/api -type d -exec chmod 755 {} +
    sudo find /opt/piano/api -type f -exec chmod 644 {} +
    rm -rf /tmp/piano-api
    sudo -n /usr/local/sbin/piano-api-redeploy'
  [ "$WHAT" = api ] && exit 0
fi

(cd "$ROOT/client" && npm run --silent check && npm run --silent test && npm run --silent build)
SRC="$ROOT/client/dist"

rsync -a --delete "$SRC/" "$HOST:/tmp/piano-app/"
ssh "$HOST" 'set -e
  sudo rm -rf /opt/piano/www/app.new
  sudo cp -r /tmp/piano-app /opt/piano/www/app.new
  sudo chown -R root:root /opt/piano/www/app.new
  sudo find /opt/piano/www/app.new -type d -exec chmod 755 {} +
  sudo find /opt/piano/www/app.new -type f -exec chmod 644 {} +
  sudo rm -rf /opt/piano/www/app.old
  if [ -d /opt/piano/www/app ]; then sudo mv /opt/piano/www/app /opt/piano/www/app.old; fi
  sudo mv /opt/piano/www/app.new /opt/piano/www/app
  sudo rm -rf /opt/piano/www/app.old /tmp/piano-app'

# Checks: the page, the skill map, the API and the library, and the map's songs all in the library
curl_opts+=(-o /dev/null -w "%{http_code}")
page=$(curl "${curl_opts[@]}" "$URL")
health=$(curl "${curl_opts[@]}" "https://192.168.2.128/api/health")
map=$(curl "${curl_opts[@]}" "${URL}content/skillmap.json")
lib=$(curl "${curl_opts[@]}" "https://192.168.2.128/api/library")
echo "page $page, skill map $map, library $lib, api $health"
"$ROOT/tools/.venv/bin/python" "$ROOT/tools/library_check.py"
[ "$page" = 200 ] && [ "$map" = 200 ] && [ "$lib" = 200 ] && [ "$health" = 200 ] && echo "deployed: $URL"
