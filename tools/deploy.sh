#!/usr/bin/env bash
# Test and deploy to the piano server:
#   the App API  -> /opt/piano/api, rebuilt by the server's piano-api-redeploy (Server repo),
#                   with the built skill map in app/content (the lesson engine plans from the same
#                   map the client shows)
#   the client   -> /opt/piano/www/app, i.e. $PIANO_SERVER/app/ (swapped in whole)
# The server's address, ssh host and certificate: ~/.config/piano-master/server.env
# (tools/server.env.example).
# Songs aren't deployed: every song is in the server's library (v0.27), and the map may name only
# songs the parent approved (tools/library_check.py stops the deploy otherwise).
# Nothing else on the server is touched; the database in /opt/piano/data is never touched here.
#   tools/deploy.sh            both
#   tools/deploy.sh client     the client only (and the API too if its content is out of date)
#   tools/deploy.sh api        the API only
#   --seed-songs               also bring content/library/ (the approved curriculum songs the repo
#                              keeps, tools/library_export.py) into the library as approved, when the
#                              API starts: a new server's first deploy (tools/fresh_install.sh). Songs
#                              already in the library, waiting for review or deleted are left alone.
#                              Only with song tools: without them, no song is approved for the parent.
# Song tools (v0.51, api/app/songtools.py): PIANO_SONG_TOOLS=on in server.env, on the dev box that
# makes songs for this server (ours). The deploy then marks the API's content with `song-tools`.
# Without it (another family's install, docs/install-guide.md), every deploy brings the approved
# curriculum songs, and any song packs pulled (content/packs/<pack>/), as "Songs from the app",
# which the parent brings into the Review list and approves there.
# PIANO_HOST=local: the server is this machine (another family's install); no ssh, the same steps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/tools/server_env.sh"
HOST="$PIANO_HOST"
SERVER="$PIANO_SERVER"
URL="$SERVER/app/"
CA="$CADDY_ROOT_CA"
TOOLS="${PIANO_SONG_TOOLS:-off}"
[ -x "$ROOT/.tools/node/bin/node" ] && export PATH="$ROOT/.tools/node/bin:$PATH"
if [ "$HOST" = local ]; then
  to_host() { rsync -a --delete "$1" "$2"; }
  on_host() { bash -c "$1"; }
else
  to_host() { rsync -a --delete "$1" "$HOST:$2"; }
  on_host() { ssh "$HOST" "$1"; }
fi

SEED=no
ARGS=()
for a in "$@"; do if [ "$a" = --seed-songs ]; then SEED=yes; else ARGS+=("$a"); fi; done
WHAT="${ARGS[0]:-all}"
if [ "$SEED" = yes ] && [ "$TOOLS" != on ]; then
  echo "--seed-songs approves songs for the parent; without song tools the parent approves them in the Review list instead" >&2
  exit 1
fi
# The server's own certificate authority, never curl -k: a rebuilt server has a new one.
[ -f "$CA" ] || { echo "no root certificate at $CA (CADDY_ROOT_CA): copy the server certificate authority's root there" >&2; exit 1; }
curl_opts=(-s --cacert "$CA")

"$ROOT/tools/.venv/bin/python" "$ROOT/tools/build_content.py"
if [ "$SEED" = yes ] || [ "$TOOLS" != on ]; then "$ROOT/tools/.venv/bin/python" "$ROOT/tools/library_export.py" --verify; fi
VERSION=$(python3 -c "import json; print(json.load(open('$ROOT/client/public/content/skillmap.json'))['contentVersion'])")
"$ROOT/tools/.venv/bin/python" "$ROOT/tools/library_check.py" $([ "$SEED" = yes ] && echo --seeding) $([ "$TOOLS" != on ] && echo --app-songs)
if [ "$WHAT" = client ]; then
  served=$(curl "${curl_opts[@]}" "$SERVER/api/health" | python3 -c "import json,sys; print(json.load(sys.stdin).get('contentVersion'))" 2>/dev/null || true)
  if [ "$served" != "$VERSION" ]; then
    echo "the API plans from content ${served:-unknown}, the client has $VERSION: deploying the API too"
    WHAT=all
  fi
fi

if [ "$WHAT" = all ] || [ "$WHAT" = api ]; then
  rm -rf "$ROOT/api/app/content"
  mkdir -p "$ROOT/api/app/content"
  cp "$ROOT/client/public/content/skillmap.json" "$ROOT/api/app/content/"
  if [ "$SEED" = yes ]; then cp -r "$ROOT/content/library" "$ROOT/api/app/content/seed"; fi   # library.adopt_seed
  # songs from the app (library.py, v0.51): the curriculum and any packs pulled, for the Review list
  find "$ROOT/api/available" -mindepth 1 -maxdepth 1 ! -name README.md -exec rm -rf {} +
  if [ "$TOOLS" = on ]; then
    echo on > "$ROOT/api/app/content/song-tools"
  else
    mkdir -p "$ROOT/api/available/curriculum"
    cp -r "$ROOT/content/library/." "$ROOT/api/available/curriculum/"
    printf '{"name": "Curriculum", "kind": "curriculum", "description": "The songs the Journey map teaches with, and the songs every install starts with."}\n' \
      > "$ROOT/api/available/curriculum/group.json"
    for pack in "$ROOT"/content/packs/*/; do
      [ -f "$pack/index.json" ] || continue
      name=$(basename "$pack")
      if find "$pack/media" -name '*.mp3' -size -200c 2>/dev/null | grep -q .; then
        echo "song pack $name: its stems aren't downloaded (git lfs pull --include \"content/packs/$name/**\"); left out" >&2
        continue
      fi
      cp -r "$pack" "$ROOT/api/available/pack-$name"
    done
  fi
  (cd "$ROOT/api" && "$ROOT/tools/.venv/bin/python" -m pytest -q tests)
  rsync -a --delete --exclude tests --exclude '__pycache__' --exclude '*.pyc' "$ROOT/api/" \
    "$([ "$HOST" = local ] && echo /tmp/piano-api/ || echo "$HOST:/tmp/piano-api/")"
  on_host 'set -e
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

to_host "$SRC/" /tmp/piano-app/
on_host 'set -e
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
health=$(curl "${curl_opts[@]}" "$SERVER/api/health")
map=$(curl "${curl_opts[@]}" "${URL}content/skillmap.json")
lib=$(curl "${curl_opts[@]}" "$SERVER/api/library")
echo "page $page, skill map $map, library $lib, api $health"
"$ROOT/tools/.venv/bin/python" "$ROOT/tools/library_check.py"
[ "$page" = 200 ] && [ "$map" = 200 ] && [ "$lib" = 200 ] && [ "$health" = 200 ] && echo "deployed: $URL"
