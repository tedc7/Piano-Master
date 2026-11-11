#!/usr/bin/env bash
# Deploy out/listen/ to the piano server as $PIANO_SERVER/melisma/
# Touches only /opt/piano/www/melisma (swapped in whole); everything else is left alone.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/out/listen"
. "$HERE/../../tools/server_env.sh"
HOST="$PIANO_HOST"
URL="$PIANO_SERVER/melisma/"
CA="$CADDY_ROOT_CA"

[ -f "$SRC/index.html" ] && [ -f "$SRC/manifest.json" ] || { echo "build first: build_page.py" >&2; exit 1; }

rsync -a --delete "$SRC/" "$HOST:/tmp/piano-melisma/"
ssh "$HOST" 'set -e
  sudo rm -rf /opt/piano/www/melisma.new
  sudo cp -r /tmp/piano-melisma /opt/piano/www/melisma.new
  sudo chown -R root:root /opt/piano/www/melisma.new
  sudo find /opt/piano/www/melisma.new -type d -exec chmod 755 {} +
  sudo find /opt/piano/www/melisma.new -type f -exec chmod 644 {} +
  sudo rm -rf /opt/piano/www/melisma.old
  if [ -d /opt/piano/www/melisma ]; then sudo mv /opt/piano/www/melisma /opt/piano/www/melisma.old; fi
  sudo mv /opt/piano/www/melisma.new /opt/piano/www/melisma
  sudo rm -rf /opt/piano/www/melisma.old /tmp/piano-melisma'

# Checks: page and manifest load, and audio supports range requests (iOS needs 206).
curl_opts=(-s -o /dev/null -w "%{http_code}")
curl_opts+=(--cacert "$CA")
page=$(curl "${curl_opts[@]}" "$URL")
manifest=$(curl "${curl_opts[@]}" "${URL}manifest.json")
first=$(python3 -c "import json,sys; m=json.load(open('$SRC/manifest.json')); print(next(iter([v['file'] for v in m['songs'][0]['versions']])))")
range=$(curl "${curl_opts[@]}" -r 0-1023 "${URL}${first}")
echo "page $page, manifest $manifest, range request $range ($first)"
[ "$page" = 200 ] && [ "$manifest" = 200 ] && [ "$range" = 206 ] && echo "deployed: $URL"
