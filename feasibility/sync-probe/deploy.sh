#!/usr/bin/env bash
# Deploy dist/ to the piano server as $PIANO_SERVER/sync/
# Touches only /opt/piano/www/sync (swapped in whole); everything else is left alone.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/dist"
. "$HERE/../../tools/server_env.sh"
HOST="$PIANO_HOST"
URL="$PIANO_SERVER/sync/"
CA="$CADDY_ROOT_CA"

[ -f "$SRC/index.html" ] && [ -f "$SRC/manifest.json" ] || { echo "build first: build_site.py" >&2; exit 1; }

rsync -a --delete "$SRC/" "$HOST:/tmp/piano-sync/"
ssh "$HOST" 'set -e
  sudo rm -rf /opt/piano/www/sync.new
  sudo cp -r /tmp/piano-sync /opt/piano/www/sync.new
  sudo chown -R root:root /opt/piano/www/sync.new
  sudo find /opt/piano/www/sync.new -type d -exec chmod 755 {} +
  sudo find /opt/piano/www/sync.new -type f -exec chmod 644 {} +
  sudo rm -rf /opt/piano/www/sync.old
  if [ -d /opt/piano/www/sync ]; then sudo mv /opt/piano/www/sync /opt/piano/www/sync.old; fi
  sudo mv /opt/piano/www/sync.new /opt/piano/www/sync
  sudo rm -rf /opt/piano/www/sync.old /tmp/piano-sync'

# Checks: page and manifest load, and audio supports range requests (iOS needs 206).
curl_opts=(-s -o /dev/null -w "%{http_code}")
curl_opts+=(--cacert "$CA")
page=$(curl "${curl_opts[@]}" "$URL")
manifest=$(curl "${curl_opts[@]}" "${URL}manifest.json")
first=$(python3 -c "import json; m=json.load(open('$SRC/manifest.json')); print(next(t['stems']['100']['vocals']['url'] for s in m['songs'] for t in s['takes'].values()))")
range=$(curl "${curl_opts[@]}" -r 0-1023 "${URL}${first}")
echo "page $page, manifest $manifest, range request $range ($first)"
[ "$page" = 200 ] && [ "$manifest" = 200 ] && [ "$range" = 206 ] && echo "deployed: $URL"
