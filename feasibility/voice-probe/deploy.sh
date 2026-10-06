#!/usr/bin/env bash
# Deploy dist/ to the piano server as $PIANO_SERVER/lesson-voices/
# Touches only /opt/piano/www/lesson-voices (swapped in whole); everything else is left alone.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/dist"
. "$HERE/../../tools/server_env.sh"
HOST="$PIANO_HOST"
URL="$PIANO_SERVER/lesson-voices/"
CA="$CADDY_ROOT_CA"

[ -f "$SRC/index.html" ] && [ -d "$SRC/audio" ] || { echo "build first: build_page.py dist" >&2; exit 1; }

rsync -a --delete "$SRC/" "$HOST:/tmp/piano-lesson-voices/"
ssh "$HOST" 'set -e
  sudo rm -rf /opt/piano/www/lesson-voices.new
  sudo cp -r /tmp/piano-lesson-voices /opt/piano/www/lesson-voices.new
  sudo chown -R root:root /opt/piano/www/lesson-voices.new
  sudo find /opt/piano/www/lesson-voices.new -type d -exec chmod 755 {} +
  sudo find /opt/piano/www/lesson-voices.new -type f -exec chmod 644 {} +
  sudo rm -rf /opt/piano/www/lesson-voices.old
  if [ -d /opt/piano/www/lesson-voices ]; then sudo mv /opt/piano/www/lesson-voices /opt/piano/www/lesson-voices.old; fi
  sudo mv /opt/piano/www/lesson-voices.new /opt/piano/www/lesson-voices
  sudo rm -rf /opt/piano/www/lesson-voices.old /tmp/piano-lesson-voices'

# Checks: the page loads, and audio supports range requests (iOS needs 206).
curl_opts=(-s -o /dev/null -w "%{http_code}" --cacert "$CA")
page=$(curl "${curl_opts[@]}" "$URL")
first=$(cd "$SRC/audio" && ls | head -1)
range=$(curl "${curl_opts[@]}" -r 0-1023 "${URL}audio/${first}")
echo "page $page, range request $range ($first)"
[ "$page" = 200 ] && [ "$range" = 206 ] && echo "deployed: $URL"
