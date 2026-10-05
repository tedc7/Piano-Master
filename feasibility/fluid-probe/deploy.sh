#!/usr/bin/env bash
# Deploy dist/ to the piano server as $PIANO_SERVER/fluid/ (the listening page) and
# /fluid/app/ (the test app). Touches only /opt/piano/www/fluid (swapped in whole).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/dist"
. "$HERE/../../tools/server_env.sh"
HOST="$PIANO_HOST"
URL="$PIANO_SERVER/fluid/"
CA="$CADDY_ROOT_CA"

[ -f "$SRC/index.html" ] && [ -f "$SRC/app/index.html" ] || { echo "build first: render.py, then build_site.py" >&2; exit 1; }

rsync -a --delete "$SRC/" "$HOST:/tmp/piano-fluid/"
ssh "$HOST" 'set -e
  sudo rm -rf /opt/piano/www/fluid.new
  sudo cp -r /tmp/piano-fluid /opt/piano/www/fluid.new
  sudo chown -R root:root /opt/piano/www/fluid.new
  sudo find /opt/piano/www/fluid.new -type d -exec chmod 755 {} +
  sudo find /opt/piano/www/fluid.new -type f -exec chmod 644 {} +
  sudo rm -rf /opt/piano/www/fluid.old
  if [ -d /opt/piano/www/fluid ]; then sudo mv /opt/piano/www/fluid /opt/piano/www/fluid.old; fi
  sudo mv /opt/piano/www/fluid.new /opt/piano/www/fluid
  sudo rm -rf /opt/piano/www/fluid.old /tmp/piano-fluid'

# Checks: page and manifest load, and audio supports range requests (iOS needs 206).
curl_opts=(-s -o /dev/null -w "%{http_code}")
curl_opts+=(--cacert "$CA")
page=$(curl "${curl_opts[@]}" "$URL")
app=$(curl "${curl_opts[@]}" "${URL}app/")
range=$(curl "${curl_opts[@]}" -r 0-1023 "${URL}app/media/canon-in-d--musescore/accompaniment_100.mp3")
echo "page $page, app $app, range request $range"
[ "$page" = 200 ] && [ "$app" = 200 ] && [ "$range" = 206 ] && echo "deployed: $URL"
