#!/usr/bin/env bash
# Deploy listen-dist/ to the piano server as https://192.168.2.128/listen/
# Touches only /opt/piano/www/listen (swapped in whole); everything else is left alone.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/listen-dist"
HOST="${PIANO_HOST:-kb}"
URL="https://192.168.2.128/listen/"
CA="${CADDY_ROOT_CA:-$HOME/repos/Server/caddy-root-ca.crt}"

[ -f "$SRC/index.html" ] && [ -f "$SRC/manifest.json" ] || { echo "build first: build_listen_site.py" >&2; exit 1; }

rsync -a --delete "$SRC/" "$HOST:/tmp/piano-listen/"
ssh "$HOST" 'set -e
  sudo rm -rf /opt/piano/www/listen.new
  sudo cp -r /tmp/piano-listen /opt/piano/www/listen.new
  sudo chown -R root:root /opt/piano/www/listen.new
  sudo find /opt/piano/www/listen.new -type d -exec chmod 755 {} +
  sudo find /opt/piano/www/listen.new -type f -exec chmod 644 {} +
  sudo rm -rf /opt/piano/www/listen.old
  if [ -d /opt/piano/www/listen ]; then sudo mv /opt/piano/www/listen /opt/piano/www/listen.old; fi
  sudo mv /opt/piano/www/listen.new /opt/piano/www/listen
  sudo rm -rf /opt/piano/www/listen.old /tmp/piano-listen'

# Checks: page and manifest load, and audio supports range requests (iOS needs 206).
curl_opts=(-s -o /dev/null -w "%{http_code}")
if [ -f "$CA" ]; then curl_opts+=(--cacert "$CA"); else curl_opts+=(-k); fi
page=$(curl "${curl_opts[@]}" "$URL")
manifest=$(curl "${curl_opts[@]}" "${URL}manifest.json")
first=$(python3 -c "import json,sys; m=json.load(open('$SRC/manifest.json')); print(next(iter(m['renders'][0]['tracks'].values())))")
range=$(curl "${curl_opts[@]}" -r 0-1023 "${URL}${first}")
echo "page $page, manifest $manifest, range request $range ($first)"
[ "$page" = 200 ] && [ "$manifest" = 200 ] && [ "$range" = 206 ] && echo "deployed: $URL"
